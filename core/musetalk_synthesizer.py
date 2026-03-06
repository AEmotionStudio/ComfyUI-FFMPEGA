"""MuseTalk integration for AI-powered lip synchronization in FFMPEGA.

Synchronizes lip movements in video with a provided audio track using
the MuseTalk V15 model. Works by detecting faces, extracting audio
features through Whisper, and inpainting the lower face region in
latent space.

Supports:
- **Video-to-Video**: Takes existing video + audio → lip-synced video
- **Image-to-Video**: Takes a single image + audio → talking head video
- **Multi-face**: Can process all faces or select a specific one

License:
    MuseTalk code: MIT License
    SD-VAE ft-mse: CreativeML Open RAIL-M (commercial OK with restrictions)
    Whisper: MIT License

Based on: https://github.com/TMElyralab/MuseTalk
"""

import copy
import gc
import json
import logging
import math
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
import torch
from tqdm import tqdm

log = logging.getLogger("ffmpega")

# ---------------------------------------------------------------------------
#  Model directory & checkpoint discovery
# ---------------------------------------------------------------------------

_HF_REPO = "TMElyralab/MuseTalk"
_MIRROR_REPO = "AEmotionStudio/musetalk-models"
_WHISPER_REPO = "openai/whisper-tiny"

# Files on the mirror (safetensors)
_MODEL_FILES = {
    "unet_fp16": "musetalkV15/unet_fp16.safetensors",
    "unet": "musetalkV15/unet.safetensors",
    "unet_config": "musetalkV15/musetalk.json",
}

# Legacy .pth filename on upstream repo
_UPSTREAM_UNET = "musetalkV15/unet.pth"

_VAE_TYPE = "sd-vae-ft-mse"

_HAS_MUSETALK = True  # All deps are built-in


def _get_model_dir() -> str:
    """Return the MuseTalk model directory, creating if needed.

    Checks (in order):
    1. FFMPEGA_MUSETALK_MODEL_DIR env var
    2. ComfyUI/models/musetalk/ (standard convention)
    3. Extension's own models/musetalk/ (fallback)
    """
    env_dir = os.environ.get("FFMPEGA_MUSETALK_MODEL_DIR")
    if env_dir and os.path.isdir(env_dir):
        return env_dir

    # ComfyUI standard path
    ext_dir = Path(__file__).resolve().parent.parent
    comfy_root = ext_dir.parent.parent
    comfy_models = comfy_root / "models" / "musetalk"
    if comfy_models.exists() or not ext_dir.name.startswith("ComfyUI"):
        comfy_models.mkdir(parents=True, exist_ok=True)
        return str(comfy_models)

    # Fallback to extension's own models/
    local = ext_dir / "models" / "musetalk"
    local.mkdir(parents=True, exist_ok=True)
    return str(local)


def _find_or_download_model(model_key: str, *, use_float16: bool = True) -> str:
    """Find or download a model file.

    Args:
        model_key: One of "unet", "unet_config".
        use_float16: If True and model_key is "unet", prefer the fp16
            safetensors variant (half the size).

    Returns:
        Path to the model file.
    """
    try:
        from .model_manager import (
            require_downloads_allowed,
            try_mirror_download,
            download_with_progress,
        )
    except ImportError:
        from core.model_manager import (
            require_downloads_allowed,
            try_mirror_download,
            download_with_progress,
        )

    model_dir = _get_model_dir()

    # For unet, try fp16 first when requested
    if model_key == "unet" and use_float16:
        fp16_file = _MODEL_FILES["unet_fp16"]
        fp16_local = os.path.join(model_dir, fp16_file)
        if os.path.isfile(fp16_local):
            return fp16_local

    # Check for the standard file
    filename = _MODEL_FILES[model_key]
    local_path = os.path.join(model_dir, filename)
    if os.path.isfile(local_path):
        return local_path

    # Also check for legacy .pth (user may have downloaded manually)
    if model_key in ("unet", "unet_fp16"):
        pth_path = os.path.join(model_dir, _UPSTREAM_UNET)
        if os.path.isfile(pth_path):
            return pth_path

    require_downloads_allowed("musetalk")

    # Ensure subdirectories exist
    os.makedirs(os.path.dirname(local_path), exist_ok=True)

    # Try mirror — fp16 first if applicable
    if model_key == "unet" and use_float16:
        fp16_file = _MODEL_FILES["unet_fp16"]
        fp16_local = os.path.join(model_dir, fp16_file)
        os.makedirs(os.path.dirname(fp16_local), exist_ok=True)
        mirror_path = try_mirror_download(
            "musetalk", fp16_file, model_dir,
        )
        if mirror_path and os.path.isfile(mirror_path):
            return mirror_path

    # Try mirror — full-precision safetensors
    mirror_path = try_mirror_download(
        "musetalk", filename, model_dir,
    )
    if mirror_path and os.path.isfile(mirror_path):
        return mirror_path

    # Fallback to upstream HF (.pth)
    upstream_file = _UPSTREAM_UNET if model_key in ("unet", "unet_fp16") else filename

    def _download():
        from huggingface_hub import hf_hub_download

        return hf_hub_download(
            repo_id=_HF_REPO,
            filename=upstream_file,
            local_dir=model_dir,
        )

    path = download_with_progress("musetalk", _download, extra=upstream_file)
    return path


def _get_vae_path() -> str:
    """Get or download the SD-VAE ft-mse model directory."""
    model_dir = _get_model_dir()
    vae_dir = os.path.join(model_dir, _VAE_TYPE)

    if os.path.isdir(vae_dir) and os.path.isfile(
        os.path.join(vae_dir, "config.json")
    ):
        return vae_dir

    # Check ComfyUI's standard vae directory
    ext_dir = Path(__file__).resolve().parent.parent
    comfy_root = ext_dir.parent.parent
    comfy_vae = comfy_root / "models" / "vae" / _VAE_TYPE
    if comfy_vae.is_dir() and (comfy_vae / "config.json").is_file():
        return str(comfy_vae)

    # Download from HuggingFace
    try:
        from .model_manager import require_downloads_allowed, download_with_progress
    except ImportError:
        from core.model_manager import require_downloads_allowed, download_with_progress  # type: ignore[no-redef]

    require_downloads_allowed("musetalk")

    def _download():
        from huggingface_hub import snapshot_download

        return snapshot_download(
            repo_id=f"stabilityai/{_VAE_TYPE}",
            local_dir=vae_dir,
        )

    path = download_with_progress("musetalk", _download, extra=_VAE_TYPE)
    return path


def _get_whisper_path() -> str:
    """Get or download the Whisper-tiny model directory."""
    model_dir = _get_model_dir()
    whisper_dir = os.path.join(model_dir, "whisper-tiny")

    if os.path.isdir(whisper_dir) and os.path.isfile(
        os.path.join(whisper_dir, "config.json")
    ):
        return whisper_dir

    # It might already be cached by transformers
    try:
        from transformers import WhisperModel

        model = WhisperModel.from_pretrained(_WHISPER_REPO)
        del model
        # If this works, transformers will use its cache
        return _WHISPER_REPO
    except Exception:
        pass

    # Download explicitly
    try:
        from .model_manager import require_downloads_allowed, download_with_progress
    except ImportError:
        from core.model_manager import require_downloads_allowed, download_with_progress  # type: ignore[no-redef]

    require_downloads_allowed("musetalk")

    def _download():
        from huggingface_hub import snapshot_download

        return snapshot_download(
            repo_id=_WHISPER_REPO,
            local_dir=whisper_dir,
        )

    path = download_with_progress("musetalk", _download, extra="whisper-tiny")
    return path


# ---------------------------------------------------------------------------
#  VRAM management
# ---------------------------------------------------------------------------

_freeing_vram = False


def _free_vram():
    """Free all GPU VRAM before loading MuseTalk models.

    Follows the MMAudio/WanVideo pattern:
    1. Tell ComfyUI to unload ALL cached models from GPU
    2. Free MMAudio models if loaded
    3. Free SAM3 models if loaded
    4. Free FLUX Klein pipeline if loaded
    5. Empty CUDA cache + gc.collect

    Uses a re-entrancy guard to prevent infinite recursion.
    """
    global _freeing_vram
    if _freeing_vram:
        return
    _freeing_vram = True
    try:
        try:
            from .platform import free_comfyui_vram
        except ImportError:
            from core.platform import free_comfyui_vram  # type: ignore
        free_comfyui_vram()

        # Free MMAudio if loaded
        try:
            try:
                from . import mmaudio_synthesizer
            except ImportError:
                from core import mmaudio_synthesizer  # type: ignore
            mmaudio_synthesizer.cleanup()
        except Exception:
            pass

        # Free SAM3 if loaded
        try:
            try:
                from . import sam3_masker
            except ImportError:
                from core import sam3_masker  # type: ignore
            sam3_masker.cleanup()
        except Exception:
            pass

        # Free FLUX Klein if loaded
        try:
            try:
                from . import flux_klein_editor
            except ImportError:
                from core import flux_klein_editor  # type: ignore
            flux_klein_editor.cleanup()
        except Exception:
            pass

        # Free LivePortrait if loaded
        try:
            try:
                from . import liveportrait_synthesizer
            except ImportError:
                from core import liveportrait_synthesizer  # type: ignore
            liveportrait_synthesizer.cleanup()
        except Exception:
            pass

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        gc.collect()
    finally:
        _freeing_vram = False


def _get_device() -> torch.device:
    """Get the best available device."""
    if torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


def _get_offload_device():
    """Get the ComfyUI offload device (CPU), or fallback to 'cpu'."""
    try:
        import comfy.model_management as mm  # type: ignore[import-not-found]
        return mm.unet_offload_device()
    except ImportError:
        return torch.device("cpu")


# ---------------------------------------------------------------------------
#  Cached model state (in-process offloading)
# ---------------------------------------------------------------------------

_models: Optional[dict] = None


def load_models() -> dict:
    """Load and cache all MuseTalk models.

    On first call, downloads models if needed, frees VRAM from other
    AI models (ComfyUI, MMAudio, SAM3, FLUX Klein), and loads all 4
    components (VAE, UNet, PositionalEncoding, Whisper) into a cached dict.

    Subsequent calls return the cached models immediately.

    Returns:
        Dict with keys: vae, unet, pe, whisper, audio_processor,
        device, offload_device.
    """
    global _models
    if _models is not None:
        return _models

    try:
        from .musetalk.vae import VAE
        from .musetalk.unet import UNet, PositionalEncoding
        from .musetalk.audio_processor import AudioProcessor
    except ImportError:
        from core.musetalk.vae import VAE
        from core.musetalk.unet import UNet, PositionalEncoding
        from core.musetalk.audio_processor import AudioProcessor

    from transformers import WhisperModel

    use_float16 = True
    device = _get_device()
    offload_device = _get_offload_device()
    weight_dtype = torch.float16 if use_float16 else torch.float32

    # Resolve model paths (downloads if needed)
    vae_path = _get_vae_path()
    unet_path = _find_or_download_model("unet", use_float16=use_float16)
    unet_config_path = _find_or_download_model("unet_config")
    whisper_path = _get_whisper_path()

    # Free VRAM from other models
    _free_vram()

    log.info("[MuseTalk] Loading models (offload_device=%s)...", offload_device)

    # Load VAE → offload device
    vae = VAE(
        model_path=vae_path,
        use_float16=use_float16,
        device=offload_device,
    )

    # Load UNet → offload device
    unet = UNet(
        unet_config=unet_config_path,
        model_path=unet_path,
        use_float16=use_float16,
        device=offload_device,
    )

    # Load PositionalEncoding → offload device
    pe = PositionalEncoding(d_model=384)
    if use_float16:
        pe = pe.half()
    pe = pe.to(offload_device)

    # Load Whisper → offload device
    whisper = WhisperModel.from_pretrained(whisper_path)
    whisper = whisper.to(device=offload_device, dtype=weight_dtype).eval()
    whisper.requires_grad_(False)

    audio_processor = AudioProcessor(feature_extractor_path=whisper_path)  # pyright: ignore[reportCallIssue]

    log.info("[MuseTalk] All models loaded and cached (offloaded to %s)", offload_device)

    _models = {
        "vae": vae,
        "unet": unet,
        "pe": pe,
        "whisper": whisper,
        "audio_processor": audio_processor,
        "device": device,
        "offload_device": offload_device,
        "use_float16": use_float16,
    }
    return _models


def cleanup() -> None:
    """Free GPU memory and clear cached MuseTalk models.

    Moves models to CPU offload device, clears the cache, empties
    CUDA cache, and runs garbage collection.
    """
    global _models
    if _models is None:
        return

    # Capture and clear the global ref first so gc.collect() can reclaim
    models = _models
    _models = None

    try:
        offload = models["offload_device"]
        for key in ("vae", "unet", "pe", "whisper"):
            obj = models.get(key)
            if obj is not None and hasattr(obj, "to"):
                try:
                    obj.to(offload)
                except Exception:
                    pass
    except Exception:
        pass
    del models

    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    gc.collect()
    try:
        import comfy.model_management as mm  # type: ignore[import-not-found]
        mm.soft_empty_cache()
    except (ImportError, AttributeError):
        pass
    log.info("[MuseTalk] Models unloaded")


# ---------------------------------------------------------------------------
#  Data generation helper
# ---------------------------------------------------------------------------


def _datagen(whisper_chunks, vae_latents, batch_size=8, device="cuda"):
    """Yield batches of (audio_features, face_latents) for inference."""
    whisper_batch, latent_batch = [], []

    for i, w in enumerate(whisper_chunks):
        idx = i % len(vae_latents)
        latent = vae_latents[idx]
        whisper_batch.append(w)
        latent_batch.append(latent)

        if len(latent_batch) >= batch_size:
            yield (
                torch.stack(whisper_batch).to(device),
                torch.cat(latent_batch, dim=0).to(device),
            )
            whisper_batch, latent_batch = [], []

    if latent_batch:
        yield (
            torch.stack(whisper_batch).to(device),
            torch.cat(latent_batch, dim=0).to(device),
        )


# ---------------------------------------------------------------------------
#  Core inference
# ---------------------------------------------------------------------------


@torch.no_grad()
def lip_sync(
    video_path: str,
    audio_path: str,
    output_dir: Optional[str] = None,
    batch_size: int = 8,
    face_index: int = -1,
    use_float16: bool = True,
    extra_margin: int = 10,
    fps: Optional[float] = None,
) -> str:
    """Generate a lip-synced video from an input video/image and audio.

    Uses cached in-process models with GPU↔CPU offloading.
    Models are loaded on first call and cached for reuse.
    After inference, models are offloaded back to CPU.

    Args:
        video_path: Path to input video or image.
        audio_path: Path to audio file for lip sync.
        output_dir: Output directory (uses temp dir if None).
        batch_size: Frames per inference batch.
        face_index: -1 for all faces, 0+ for specific face.
        use_float16: Use fp16 for lower VRAM.
        extra_margin: Extra pixels below face bbox.
        fps: Override video FPS (used when input is an image).

    Returns:
        Path to the output lip-synced video file.
    """
    try:
        from .musetalk.face_detection import (
            get_landmarks_and_bboxes,
            read_frames_from_video,
            read_image_as_frames,
            COORD_PLACEHOLDER,
        )
        from .musetalk.blending import blend_face
    except ImportError:
        from core.musetalk.face_detection import (
            get_landmarks_and_bboxes,
            read_frames_from_video,
            read_image_as_frames,
            COORD_PLACEHOLDER,
        )
        from core.musetalk.blending import blend_face

    # ── Determine output path ──
    if output_dir is None:
        output_dir = tempfile.mkdtemp(prefix="ffmpega_lipsync_")
    os.makedirs(output_dir, exist_ok=True)

    base = os.path.splitext(os.path.basename(video_path))[0]
    audio_base = os.path.splitext(os.path.basename(audio_path))[0]
    output_path = os.path.join(output_dir, f"{base}_{audio_base}_lipsync.mp4")

    # ── Load or reuse cached models ──
    models = load_models()
    vae = models["vae"]
    unet = models["unet"]
    pe = models["pe"]
    whisper = models["whisper"]
    audio_processor = models["audio_processor"]
    device = models["device"]
    offload_device = models["offload_device"]
    weight_dtype = torch.float16 if models["use_float16"] else torch.float32

    # Move models to GPU for inference
    log.info("[MuseTalk] Moving models to %s for inference", device)
    vae.to(device)
    unet.to(device)
    pe.to(device)
    whisper.to(device)

    try:
        timesteps = torch.tensor([0], device=device)

        # ── Extract frames ──
        log.info("[MuseTalk] Reading input frames...")
        ext = os.path.splitext(video_path)[1].lower()
        is_image = ext in (".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff")

        if is_image:
            # Get audio duration to determine frame count
            import librosa

            audio_data, sr = librosa.load(audio_path, sr=16000)
            audio_duration = len(audio_data) / sr
            frame_fps = fps or 25.0
            num_frames = int(audio_duration * frame_fps)
            frames, vid_fps = read_image_as_frames(video_path, num_frames)
            vid_fps = frame_fps
        else:
            frames, vid_fps = read_frames_from_video(video_path)
            if fps:
                vid_fps = fps

        log.info(f"[MuseTalk] Loaded {len(frames)} frames at {vid_fps} FPS")

        # ── Detect faces ──
        log.info("[MuseTalk] Detecting faces...")
        bbox_lists, frames = get_landmarks_and_bboxes(
            frames,
            bbox_shift=0,
            extra_margin=extra_margin,
            face_index=face_index,
        )

        # ── Extract audio features ──
        log.info("[MuseTalk] Extracting audio features...")
        whisper_features, librosa_length = audio_processor.get_audio_feature(
            audio_path, weight_dtype=weight_dtype
        )
        whisper_chunks = audio_processor.get_whisper_chunks(
            whisper_features,
            device,
            weight_dtype,
            whisper,
            librosa_length,
            fps=int(vid_fps),
        )

        # ── Process faces ──
        # For multi-face: process each face independently
        num_faces = max(len(bboxes) for bboxes in bbox_lists)
        log.info(f"[MuseTalk] Processing {num_faces} face(s)...")

        # Start with copies of the original frames as output
        result_frames = [frame.copy() for frame in frames]

        for face_idx in range(num_faces):
            # Collect bboxes and latents for this face across all frames
            face_bboxes = []
            face_latents = []

            for frame_idx, (bboxes, frame) in enumerate(zip(bbox_lists, frames)):
                if face_idx < len(bboxes) and bboxes[face_idx] != COORD_PLACEHOLDER:
                    bbox = bboxes[face_idx]
                elif len(bboxes) > 0 and bboxes[0] != COORD_PLACEHOLDER:
                    bbox = bboxes[0]  # fallback to first face
                else:
                    bbox = COORD_PLACEHOLDER

                face_bboxes.append(bbox)

                if bbox != COORD_PLACEHOLDER:
                    x1, y1, x2, y2 = bbox
                    crop = frame[y1:y2, x1:x2]
                    crop = cv2.resize(
                        crop, (256, 256), interpolation=cv2.INTER_LANCZOS4
                    )
                    latent = vae.get_latents_for_unet(crop)
                    face_latents.append(latent)

            if not face_latents:
                log.warning(f"[MuseTalk] No face detected for face index {face_idx}")
                continue

            # Create cycled lists for looping
            face_latents_cycle = face_latents + face_latents[::-1]
            face_bboxes_cycle = face_bboxes + face_bboxes[::-1]

            # ── Batch inference ──
            video_num = len(whisper_chunks)
            gen = _datagen(
                whisper_chunks=whisper_chunks,
                vae_latents=face_latents_cycle,
                batch_size=batch_size,
                device=str(device),
            )

            gen_faces = []
            total_batches = int(np.ceil(float(video_num) / batch_size))

            for whisper_batch, latent_batch in tqdm(
                gen, total=total_batches, desc=f"[MuseTalk] Face {face_idx}"
            ):
                audio_features = pe(whisper_batch)
                latent_batch = latent_batch.to(dtype=unet.model.dtype)

                pred = unet.model(
                    latent_batch,
                    timesteps,
                    encoder_hidden_states=audio_features,
                ).sample

                decoded = vae.decode_latents(pred)
                for face_img in decoded:
                    gen_faces.append(face_img)

            # ── Blend generated faces back ──
            for i, gen_face in enumerate(gen_faces):
                if i >= len(result_frames):
                    break

                bbox = face_bboxes_cycle[i % len(face_bboxes_cycle)]
                if bbox == COORD_PLACEHOLDER:
                    continue

                result_frames[i] = blend_face(
                    result_frames[i],
                    gen_face,
                    bbox,
                )

        # ── Write output video ──
        log.info("[MuseTalk] Writing output video...")
        temp_video = os.path.join(output_dir, "_temp_lipsync.mp4")

        h, w = result_frames[0].shape[:2]
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")  # type: ignore[attr-defined]
        writer = cv2.VideoWriter(temp_video, fourcc, vid_fps, (w, h))

        for frame in result_frames:
            writer.write(frame)
        writer.release()

        # Mux with audio using ffmpeg
        cmd = [
            "ffmpeg", "-y", "-v", "warning",
            "-i", temp_video,
            "-i", audio_path,
            "-c:v", "libx264",
            "-crf", "18",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-shortest",
            output_path,
        ]
        subprocess.run(cmd, check=True)

        # Clean up temp
        if os.path.isfile(temp_video):
            os.remove(temp_video)

        log.info(f"[MuseTalk] Lip-synced video saved to {output_path}")

        return output_path
    finally:
        # ── Offload models back to CPU ──
        log.info("[MuseTalk] Offloading models to %s", offload_device)
        try:
            vae.to(offload_device)
            unet.to(offload_device)
            pe.to(offload_device)
            whisper.to(offload_device)
        except Exception:
            pass
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        try:
            import comfy.model_management as mm  # type: ignore[import-not-found]
            mm.soft_empty_cache()
        except (ImportError, AttributeError):
            pass


# ---------------------------------------------------------------------------
#  Subprocess wrapper (prevents CUDA memory leaks)
# ---------------------------------------------------------------------------


def lip_sync_subprocess(
    video_path: str,
    audio_path: str,
    output_dir: Optional[str] = None,
    batch_size: int = 8,
    face_index: int = -1,
    use_float16: bool = True,
) -> str:
    """Run lip_sync() in a subprocess to avoid CUDA memory leaks.

    Same interface as lip_sync(). All args are JSON-serialized to the
    child process via stdin, and the output path is returned via stdout.
    """
    import json as _json

    args = {
        "video_path": video_path,
        "audio_path": audio_path,
        "output_dir": output_dir or tempfile.mkdtemp(prefix="ffmpega_lipsync_"),
        "batch_size": batch_size,
        "face_index": face_index,
        "use_float16": use_float16,
    }

    # Pass model dir via env var so the child process can find models
    env = os.environ.copy()
    env["FFMPEGA_MUSETALK_MODEL_DIR"] = _get_model_dir()

    # Build the child process command
    child_script = f"""
import sys, json
args = json.loads(sys.stdin.read())

# Add the extension to sys.path so imports work
import os
ext_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ext_dir not in sys.path:
    sys.path.insert(0, ext_dir)

# Need to set up the path for the child process
base_dir = {repr(str(Path(__file__).resolve().parent.parent))}
if base_dir not in sys.path:
    sys.path.insert(0, base_dir)

from core.musetalk_synthesizer import lip_sync
result = lip_sync(**args)
print("RESULT:" + result)
"""

    log.info("[MuseTalk] Starting lip sync subprocess...")

    proc = subprocess.Popen(
        [sys.executable, "-c", child_script],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        cwd=str(Path(__file__).resolve().parent.parent),
    )

    stdout, stderr = proc.communicate(
        input=_json.dumps(args).encode("utf-8"),
        timeout=600,  # 10 minute timeout
    )

    if proc.returncode != 0:
        err_msg = stderr.decode("utf-8", errors="replace")
        log.error("[MuseTalk] Subprocess failed:\n%s", err_msg)
        raise RuntimeError(f"MuseTalk lip sync subprocess failed: {err_msg}")

    # Extract result path from stdout
    stdout_text = stdout.decode("utf-8")
    for line in stdout_text.strip().split("\n"):
        if line.startswith("RESULT:"):
            result_path = line[7:].strip()
            if os.path.isfile(result_path):
                return result_path

    raise RuntimeError(
        f"MuseTalk subprocess did not produce output. "
        f"stdout: {stdout_text}, stderr: {stderr.decode('utf-8', errors='replace')}"
    )
