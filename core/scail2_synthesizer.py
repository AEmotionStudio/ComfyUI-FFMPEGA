# coding: utf-8
"""SCAIL-2 pose-driven character animation — ComfyUI-native, in-process.

Rebuilds the reference ``Wan21_SCAIL2`` workflow inside a single synthesizer:

1. Load the SCAIL-2 fp8 diffusion model (``comfy.sd.load_diffusion_model``),
   the Wan 2.1 VAE, the UMT5 text encoder (``comfy.sd.load_clip``) and the
   CLIP-vision (ViT-H) encoder — reusing the SVI/Wan-Animate discovery helpers.
2. Apply any number of model-only LoRAs (lightx2v distill, DPO, …) and a
   ModelSamplingSD3 shift.
3. Track the driving pose video and the reference image with the native SAM 3.1
   model (``core.sam3_masker.track_images_native_sam31``), then colorize the
   per-identity masks with ``comfy_extras.nodes_scail.SCAIL2ColoredMask``.
4. Build the SCAIL-2 conditioning bundle with
   ``comfy_extras.nodes_scail.WanSCAILToVideo`` and sample with
   ``comfy.samplers`` / ``comfy.sample``.
5. VAE-decode and encode two videos: the animation output and the colored
   pose-video mask.

Everything runs under ComfyUI's VRAM management (no subprocess), the approach
that fixed the SAM 3.1 OOM. Replaces the vendored ``core/scail`` pipeline.
"""
from __future__ import annotations

import gc
import logging
import os
import subprocess
import tempfile
from typing import List, Optional, Tuple

import numpy as np
import torch

log = logging.getLogger("ComfyUI-FFMPEGA.scail2")

# HuggingFace source for the tested fp8 model.
_HF_REPO = "Comfy-Org/SCAIL-2"
_HF_MODEL_FILE = "diffusion_models/wan2.1_14B_SCAIL_2_fp8_scaled.safetensors"

# Cached state (module-level, freed via cleanup()).
_model = None
_vae_model = None
_clip_model = None
_clip_vision = None


# ---------------------------------------------------------------------------
#  Helper imports (reuse SVI / Wan-Animate discovery + LoRA helpers)
# ---------------------------------------------------------------------------

def _svi_helpers():
    try:
        from .svi_synthesizer import (
            _find_wan_vae, _find_wan_text_encoder, _apply_lora_to_model,
        )
    except ImportError:
        from core.svi_synthesizer import (  # type: ignore
            _find_wan_vae, _find_wan_text_encoder, _apply_lora_to_model,
        )
    return _find_wan_vae, _find_wan_text_encoder, _apply_lora_to_model


def _vram_free():
    try:
        from . import _vram_utils
    except ImportError:
        try:
            from core import _vram_utils  # type: ignore
        except ImportError:
            _vram_utils = None
    if _vram_utils is not None:
        _vram_utils.free_for_module(exclude="scail2_synthesizer")


# ---------------------------------------------------------------------------
#  Model discovery / download
# ---------------------------------------------------------------------------

def _find_scail2_model() -> Optional[str]:
    """Locate a SCAIL-2 diffusion model already present on disk."""
    try:
        import folder_paths  # type: ignore[import-not-found]
    except ImportError:
        return None
    search_dirs: List[str] = []
    for folder_name in ("diffusion_models", "unet"):
        try:
            search_dirs.extend(folder_paths.get_folder_paths(folder_name))
        except Exception:
            pass
    for search_dir in search_dirs:
        if not os.path.isdir(search_dir):
            continue
        for root, _dirs, files in os.walk(search_dir):
            for f in files:
                fl = f.lower()
                if fl.endswith(".safetensors") and "scail" in fl:
                    return os.path.join(root, f)
    return None


def _ensure_scail2_model() -> str:
    """Return a path to the SCAIL-2 model, downloading the fp8 file if needed."""
    found = _find_scail2_model()
    if found:
        return found

    try:
        from . import model_manager as _mm
    except ImportError:
        from core import model_manager as _mm  # type: ignore
    _mm.require_downloads_allowed("scail2")

    try:
        import folder_paths  # type: ignore[import-not-found]
        dest_dir = folder_paths.get_folder_paths("diffusion_models")[0]
    except Exception as exc:
        raise FileNotFoundError(
            "Could not resolve ComfyUI diffusion_models directory") from exc

    try:
        from huggingface_hub import hf_hub_download
    except ImportError as exc:
        raise ImportError(
            "huggingface_hub is required to download the SCAIL-2 model.") from exc

    os.makedirs(dest_dir, exist_ok=True)
    _mm.download_with_progress(
        "scail2",
        lambda: hf_hub_download(
            repo_id=_HF_REPO, filename=_HF_MODEL_FILE, local_dir=dest_dir,
        ),
        extra=os.path.basename(_HF_MODEL_FILE),
    )
    found = _find_scail2_model()
    if not found:
        # hf_hub_download keeps the repo subfolder layout under dest_dir.
        candidate = os.path.join(dest_dir, _HF_MODEL_FILE)
        if os.path.isfile(candidate):
            return candidate
        raise FileNotFoundError("SCAIL-2 model download did not produce a file")
    return found


def _is_native_umt5(path: str) -> bool:
    """True for a ComfyUI-native UMT5 encoder, False for WanVideoWrapper format.

    The native file exposes T5 keys (``shared.weight`` / ``encoder.block.*``);
    the WanVideoWrapper ``*-enc-*`` file uses ``blocks.0.attn.*`` keys that
    ``comfy.sd.load_clip(CLIPType.WAN)`` cannot detect — it silently falls back
    to a 768-dim SD1 CLIP-L, which then fails inside the SCAIL-2 model with
    "mat1 and mat2 shapes cannot be multiplied (...x768 and 4096x...)".
    """
    try:
        from safetensors import safe_open
        with safe_open(path, "pt") as f:
            for k in f.keys():
                if k == "shared.weight" or k.startswith("encoder.block"):
                    return True
                if k.startswith("blocks.0.attn"):
                    return False
    except Exception:
        return False
    return False


def _find_native_umt5() -> Optional[str]:
    """Find a ComfyUI-native UMT5 text encoder, skipping WanVideoWrapper files."""
    try:
        import folder_paths  # type: ignore[import-not-found]
    except ImportError:
        return None
    search_dirs: List[str] = []
    for folder_name in ("text_encoders", "clip"):
        try:
            search_dirs.extend(folder_paths.get_folder_paths(folder_name))
        except Exception:
            pass
    fallback = None
    for search_dir in search_dirs:
        if not os.path.isdir(search_dir):
            continue
        for root, _dirs, files in os.walk(search_dir):
            for f in files:
                fl = f.lower()
                if not fl.endswith(".safetensors") or "umt5" not in fl:
                    continue
                full = os.path.join(root, f)
                if _is_native_umt5(full):
                    return full
                fallback = fallback or full
    return fallback


def _find_sam3_multiplex() -> Optional[str]:
    """Locate the SAM 3.1 multiplex checkpoint SCAIL-2's producers recommend.

    Prefers ``sam3.1_multiplex_fp16.safetensors`` (the file used in the reference
    SCAIL-2 workflow); searches the ``checkpoints`` folder (incl. a ``sam3``
    subfolder) and the ``SAM3.1`` folder. Returns ``None`` so the SAM3 masker
    falls back to its own checkpoint resolution when not found.
    """
    try:
        import folder_paths  # type: ignore[import-not-found]
    except ImportError:
        return None
    search_dirs: List[str] = []
    for folder_name in ("checkpoints", "diffusion_models"):
        try:
            search_dirs.extend(folder_paths.get_folder_paths(folder_name))
        except Exception:
            pass
    try:
        models_dir = folder_paths.models_dir
        search_dirs.append(os.path.join(models_dir, "SAM3.1"))
        search_dirs.append(os.path.join(models_dir, "checkpoints", "sam3"))
    except Exception:
        pass
    preferred = None  # *_multiplex_fp16
    any_multiplex = None
    for search_dir in search_dirs:
        if not os.path.isdir(search_dir):
            continue
        for root, _dirs, files in os.walk(search_dir):
            for f in files:
                fl = f.lower()
                if not fl.endswith(".safetensors") or "multiplex" not in fl:
                    continue
                full = os.path.join(root, f)
                if "fp16" in fl:
                    preferred = preferred or full
                any_multiplex = any_multiplex or full
    return preferred or any_multiplex


def _find_clip_vision() -> Optional[str]:
    """Find the CLIP-vision ViT-H encoder (clip_vision_h.safetensors)."""
    try:
        import folder_paths  # type: ignore[import-not-found]
    except ImportError:
        return None
    candidates: List[Tuple[int, str]] = []
    for folder_name in ("clip_vision",):
        try:
            search_dirs = folder_paths.get_folder_paths(folder_name)
        except Exception:
            search_dirs = []
        for search_dir in search_dirs:
            if not os.path.isdir(search_dir):
                continue
            for root, _dirs, files in os.walk(search_dir):
                for f in files:
                    fl = f.lower()
                    if not fl.endswith(".safetensors"):
                        continue
                    if "clip_vision_h" in fl:
                        candidates.append((0, os.path.join(root, f)))
                    elif "clip_vision" in fl or "vit_h" in fl or "vit-h" in fl:
                        candidates.append((1, os.path.join(root, f)))
    if candidates:
        candidates.sort(key=lambda x: x[0])
        return candidates[0][1]
    return None


# ---------------------------------------------------------------------------
#  Loading
# ---------------------------------------------------------------------------

def _load_models():
    """Load and cache (diffusion model, VAE, text-CLIP, clip-vision)."""
    global _model, _vae_model, _clip_model, _clip_vision
    if _model is not None and _vae_model is not None:
        return _model, _vae_model, _clip_model, _clip_vision

    import comfy.sd  # type: ignore[import-not-found]
    import comfy.utils  # type: ignore[import-not-found]
    import comfy.clip_vision  # type: ignore[import-not-found]

    _find_wan_vae, _, _ = _svi_helpers()

    _vram_free()

    model_path = _ensure_scail2_model()
    log.info("SCAIL2: loading diffusion model %s", model_path)
    _model = comfy.sd.load_diffusion_model(model_path)

    vae_path = _find_wan_vae()
    if vae_path is None:
        raise FileNotFoundError(
            "Wan VAE not found. Place wan*.safetensors in ComfyUI/models/vae/")
    log.info("SCAIL2: loading VAE %s", vae_path)
    _vae_model = comfy.sd.VAE(sd=comfy.utils.load_torch_file(vae_path))

    te_path = _find_native_umt5()
    if te_path is None:
        raise FileNotFoundError(
            "Native UMT5 text encoder not found. Place "
            "umt5_xxl_fp8_e4m3fn_scaled.safetensors in ComfyUI/models/text_encoders/ "
            "(or models/clip/). NOTE: the WanVideoWrapper 'umt5-xxl-enc-*.safetensors' "
            "format is NOT compatible — SCAIL-2 needs the ComfyUI-native UMT5.")
    if not _is_native_umt5(te_path):
        log.warning(
            "SCAIL2: '%s' looks like a WanVideoWrapper-format UMT5 (incompatible). "
            "Expect a conditioning-dim error; install the ComfyUI-native "
            "umt5_xxl_fp8_e4m3fn_scaled.safetensors instead.", os.path.basename(te_path))
    log.info("SCAIL2: loading text encoder %s", te_path)
    _clip_model = comfy.sd.load_clip(
        ckpt_paths=[te_path], embedding_directory=None,
        clip_type=comfy.sd.CLIPType.WAN,
    )

    cv_path = _find_clip_vision()
    if cv_path is None:
        raise FileNotFoundError(
            "CLIP-vision encoder not found. Place clip_vision_h.safetensors in "
            "ComfyUI/models/clip_vision/")
    log.info("SCAIL2: loading clip_vision %s", cv_path)
    _clip_vision = comfy.clip_vision.load(cv_path)

    log.info("SCAIL2: all models loaded")
    return _model, _vae_model, _clip_model, _clip_vision


# ---------------------------------------------------------------------------
#  Frame I/O
# ---------------------------------------------------------------------------

def _video_fps(video_path: str) -> float:
    try:
        from .sam3_masker import _get_video_fps
    except ImportError:
        try:
            from core.sam3_masker import _get_video_fps  # type: ignore
        except ImportError:
            return 16.0
    try:
        return float(_get_video_fps(video_path)) or 16.0
    except Exception:
        return 16.0


def _load_video_frames(video_path: str, max_frames: int) -> torch.Tensor:
    """Decode a video to a ComfyUI IMAGE tensor ``[T, H, W, 3]`` float 0-1."""
    from PIL import Image
    tmp_dir = tempfile.mkdtemp(prefix="scail2_frames_")
    try:
        subprocess.run(
            ["ffmpeg", "-i", video_path, "-q:v", "2",
             os.path.join(tmp_dir, "%06d.jpg")],
            capture_output=True, check=True,
        )
        from pathlib import Path
        files = sorted(Path(tmp_dir).glob("*.jpg"))
        if max_frames and max_frames > 0:
            files = files[:max_frames]
        if not files:
            raise RuntimeError(f"No frames extracted from {video_path}")
        arrs = [np.asarray(Image.open(f).convert("RGB"), dtype=np.float32) / 255.0
                for f in files]
        return torch.from_numpy(np.stack(arrs))
    finally:
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _load_image(image_path: str) -> torch.Tensor:
    """Load an image to a ComfyUI IMAGE tensor ``[1, H, W, 3]`` float 0-1."""
    from PIL import Image
    arr = np.asarray(Image.open(image_path).convert("RGB"), dtype=np.float32) / 255.0
    return torch.from_numpy(arr).unsqueeze(0)


def _extend_frame_indices(n_src: int, n_total: int, mode: str) -> list:
    """Build an index list of length ``n_total`` into ``[0, n_src)`` for
    extending the pose video (and its colored mask) past the driving footage.

    ``loop`` wraps back to the start; ``pingpong`` bounces forward then backward
    (no seam jump); ``hold_last`` freezes on the final frame; ``none`` (or when
    no extension is needed) returns just the source range so the tail
    hallucinates as before.
    """
    if n_total <= n_src or mode in ("none", ""):
        return list(range(min(n_src, n_total)))
    if mode == "hold_last":
        return list(range(n_src)) + [n_src - 1] * (n_total - n_src)
    if mode == "loop":
        return [i % n_src for i in range(n_total)]
    # pingpong: 0,1,…,n-1,n-2,…,1,0,1,…
    if n_src <= 1:
        return [0] * n_total
    period = 2 * (n_src - 1)
    return [(p if (p := i % period) < n_src else period - p) for i in range(n_total)]


def _reinhard_color_match(frames: torch.Tensor, ref_frame: torch.Tensor) -> torch.Tensor:
    """Per-frame Reinhard color transfer of ``frames`` toward ``ref_frame``.

    Matches each frame's per-channel mean/std to the reference frame's — the
    same idea as the reference workflow's ColorTransfer (reinhard, per_frame),
    used between extend chunks to stop slow color/exposure drift.

    Args:
        frames: ``[T, H, W, 3]`` float 0-1.
        ref_frame: ``[H, W, 3]`` float 0-1 (the previous chunk's last frame).
    """
    eps = 1e-5
    ref = ref_frame.reshape(-1, 3)
    ref_mean = ref.mean(0)               # [3]
    ref_std = ref.std(0)                 # [3]
    flat = frames.reshape(frames.shape[0], -1, 3)        # [T, HW, 3]
    f_mean = flat.mean(1, keepdim=True)                  # [T, 1, 3]
    f_std = flat.std(1, keepdim=True)                    # [T, 1, 3]
    out = (flat - f_mean) / (f_std + eps) * ref_std + ref_mean
    return out.reshape(frames.shape).clamp(0, 1)


def _composite_images(images: List[torch.Tensor], direction: str = "horizontal") -> torch.Tensor:
    """Composite multiple ``[1, H, W, 3]`` images into one — the single
    multi-character reference SCAIL-2 expects.

    ``horizontal`` resizes each to the tallest height and concatenates
    left-to-right; ``vertical`` resizes each to the widest width and stacks
    top-to-bottom. Returns ``[1, H, W, 3]`` float 0-1.
    """
    from PIL import Image
    pil = [
        Image.fromarray((im[0].cpu().numpy() * 255).clip(0, 255).astype(np.uint8))
        for im in images
    ]
    if str(direction).lower().startswith("v"):
        target_w = max(p.width for p in pil)
        resized = [
            p if p.width == target_w
            else p.resize((target_w, max(1, round(p.height * target_w / p.width))), Image.LANCZOS)
            for p in pil
        ]
        total_h = sum(p.height for p in resized)
        canvas = Image.new("RGB", (target_w, total_h), (0, 0, 0))
        y = 0
        for p in resized:
            canvas.paste(p, (0, y))
            y += p.height
    else:
        target_h = max(p.height for p in pil)
        resized = [
            p if p.height == target_h
            else p.resize((max(1, round(p.width * target_h / p.height)), target_h), Image.LANCZOS)
            for p in pil
        ]
        total_w = sum(p.width for p in resized)
        canvas = Image.new("RGB", (total_w, target_h), (0, 0, 0))
        x = 0
        for p in resized:
            canvas.paste(p, (x, 0))
            x += p.width
    arr = np.asarray(canvas, dtype=np.float32) / 255.0
    return torch.from_numpy(arr).unsqueeze(0)


def _encode_video(frames: torch.Tensor, out_path: str, fps: float) -> str:
    """Encode an IMAGE tensor ``[T, H, W, 3]`` float 0-1 to an H.264 mp4."""
    from PIL import Image
    frames = frames.detach().float().clamp(0, 1).cpu()
    tmp_dir = tempfile.mkdtemp(prefix="scail2_out_")
    try:
        for i in range(frames.shape[0]):
            arr = (frames[i].numpy() * 255).astype(np.uint8)
            Image.fromarray(arr).save(os.path.join(tmp_dir, f"{i:06d}.png"))
        os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
        subprocess.run(
            ["ffmpeg", "-y", "-framerate", str(fps),
             "-i", os.path.join(tmp_dir, "%06d.png"),
             "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", out_path],
            capture_output=True, check=True,
        )
        return out_path
    finally:
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
#  Main entry point
# ---------------------------------------------------------------------------

def _register_blockswap(model_patcher, blocks_to_swap: int) -> None:
    """Keep ~blocks_to_swap transformer blocks' worth of DiT weights off-GPU."""
    try:
        from .vram_utils import register_blockswap
    except ImportError:
        from core.vram_utils import register_blockswap  # type: ignore

    register_blockswap(
        model_patcher, blocks_to_swap, key="scail2_blockswap", label="SCAIL2",
    )


def generate_video(
    *,
    prompt: str,
    reference_image_path: str,
    driving_video_path: str,
    output_path: str,
    mask_output_path: Optional[str] = None,
    width: int = 512,
    height: int = 896,
    length: int = 81,
    steps: int = 6,
    cfg: float = 1.0,
    shift: float = 5.0,
    seed: int = 0,
    sampler_name: str = "euler",
    scheduler: str = "simple",
    denoise: float = 1.0,
    replacement_mode: bool = False,
    sort_by: str = "left_to_right",
    object_indices: str = "",
    sam_prompt: str = "person",
    sam_points: Optional[list] = None,
    sam_labels: Optional[list] = None,
    sam_max_objects: int = 1,
    sam_det_threshold: float = 0.5,
    sam_detect_interval: int = 2,
    extra_reference_paths: Optional[List[str]] = None,
    composite_direction: str = "horizontal",
    main_reference: str = "last",
    color_match: bool = False,
    pose_extend: str = "pingpong",
    point_src_width: int = 0,
    point_src_height: int = 0,
    lora_entries: Optional[List[Tuple[str, float]]] = None,
    blockswap_blocks: int = 0,
    tiled_vae: bool = False,
    fps: Optional[float] = None,
) -> Tuple[str, str]:
    """Run SCAIL-2 animation and return ``(animation_path, mask_video_path)``."""
    import comfy.sample  # type: ignore[import-not-found]
    from comfy_extras.nodes_scail import WanSCAILToVideo, SCAIL2ColoredMask

    try:
        from .sam3_masker import track_images_native_sam31
    except ImportError:
        from core.sam3_masker import track_images_native_sam31  # type: ignore

    # 4n+1 total frame count and 32px-aligned resolution (model constraints).
    total_length = ((max(1, length) - 1) // 4) * 4 + 1
    width = (width // 32) * 32 or 32
    height = (height // 32) * 32 or 32

    # SCAIL-2 is trained on 81-frame chunks with a 5-frame anchor (76-frame
    # step). Longer requests are generated chunk-by-chunk, each anchored on the
    # previous chunk's tail via WanSCAILToVideo's previous_frames input.
    CHUNK = 81
    PREV_ANCHOR = 5

    model, vae, clip, clip_vision = _load_models()

    # --- LoRAs (model-only) + ModelSamplingSD3 shift ---
    _, _, _apply_lora = _svi_helpers()
    # `model` is the module-level cache handed back by _load_models(); clone so
    # nothing below (LoRA, shift, block-swap wrapper) can leak into later runs.
    working_model = model.clone()
    for lora_path, strength in (lora_entries or []):
        if not lora_path or not os.path.isfile(lora_path):
            log.warning("SCAIL2: LoRA not found, skipping: %s", lora_path)
            continue
        try:
            working_model = _apply_lora(working_model, lora_path, strength)
        except Exception as exc:
            log.warning("SCAIL2: failed to apply LoRA %s: %s", lora_path, exc)
    try:
        from comfy_extras.nodes_model_advanced import ModelSamplingSD3
        working_model = ModelSamplingSD3().patch(working_model, shift)[0]
    except Exception as exc:
        log.warning("SCAIL2: ModelSamplingSD3 shift failed: %s", exc)

    # Optional block swap — registered on the final patched clone so the wrapper
    # sees the same patcher that comfy.sample.sample() prepares.
    _register_blockswap(working_model, blockswap_blocks)

    # --- Load driving frames + reference image(s) ---
    pose_video = _load_video_frames(driving_video_path, total_length)
    if fps is None:
        fps = _video_fps(driving_video_path)

    # `length` may exceed the driving video — SCAIL-2 keeps extending past where
    # the pose runs out, making up the remaining frames from the previous
    # chunk's anchor + reference + prompt (WanSCAILToVideo drops pose_video for
    # chunks beyond the driving footage).
    chunk_len = min(total_length, CHUNK)

    # Multiple references → composite onto ONE image (SCAIL-2 convention:
    # "for multiple references composite all on single image"). SAM then
    # segments each subject as its own identity → blue, red, green, …
    ref_paths = [reference_image_path] + [
        p for p in (extra_reference_paths or []) if p and os.path.isfile(p)
    ]
    n_refs = len(ref_paths)
    # The "main" reference drives identity most strongly (it's the one
    # CLIP-vision encodes). Convention from the multiref workflow: the LAST
    # connected reference is the main/closest one.
    main_ref_path = ref_paths[-1] if str(main_reference).lower() == "last" else ref_paths[0]
    if n_refs > 1:
        reference_image = _composite_images(
            [_load_image(p) for p in ref_paths], composite_direction)
        log.info("SCAIL2: composited %d references (%s, main=%s)",
                 n_refs, composite_direction, os.path.basename(main_ref_path))
    else:
        reference_image = _load_image(reference_image_path)
    main_reference_image = _load_image(main_ref_path)

    # With N references we need at least N tracked identities so each gets a color.
    eff_max_objects = max(int(sam_max_objects), n_refs)

    # Subject prompt may list several subject types (";" or newline separated),
    # e.g. "man; dog" — each becomes its own SAM text prompt.
    import re as _re
    sam_prompts = [s.strip() for s in _re.split(r"[;\n]", sam_prompt) if s.strip()] or ["person"]

    # --- SAM 3.1 tracking → colored masks ---
    sam_ckpt = _find_sam3_multiplex()
    log.info("SCAIL2: tracking driving video with SAM 3.1 (subjects=%r, max_objects=%d, "
             "det_thresh=%.2f, detect_interval=%d, ckpt=%s)",
             sam_prompts, eff_max_objects, sam_det_threshold, sam_detect_interval,
             sam_ckpt or "(default)")
    driving_track = track_images_native_sam31(
        pose_video, prompt=sam_prompts, points=sam_points, labels=sam_labels,
        max_objects=eff_max_objects, det_threshold=sam_det_threshold,
        detect_interval=sam_detect_interval,
        point_src_width=point_src_width, point_src_height=point_src_height,
        checkpoint_path=sam_ckpt,
    )
    log.info("SCAIL2: tracking reference image with SAM 3.1")
    ref_track = track_images_native_sam31(
        reference_image, prompt=sam_prompts, max_objects=eff_max_objects,
        det_threshold=sam_det_threshold, checkpoint_path=sam_ckpt)

    mask_out = SCAIL2ColoredMask.execute(
        driving_track, object_indices, sort_by, replacement_mode, ref_track)
    pose_video_mask, reference_image_mask = mask_out[0], mask_out[1]

    # If the output is longer than the driving footage, extend the pose video
    # AND its colored mask to the full length so the made-up tail keeps
    # following real motion (loop/pingpong/hold) instead of hallucinating.
    if pose_extend != "none" and total_length > pose_video.shape[0]:
        n_src = pose_video.shape[0]
        idx = torch.as_tensor(
            _extend_frame_indices(n_src, total_length, pose_extend), dtype=torch.long)
        pose_video = pose_video[idx]
        # The colored mask is rendered at the driving track's frame count (n_src),
        # so it indexes with the same sequence.
        if pose_video_mask is not None and pose_video_mask.shape[0] == n_src:
            pose_video_mask = pose_video_mask[idx]
        log.info("SCAIL2: extended pose %d→%d frames via %s",
                 n_src, total_length, pose_extend)

    # --- CLIP-vision encode the MAIN reference (strongest identity effect;
    #     SCAIL trained with stretch resize, so crop=False) ---
    clip_vision_output = clip_vision.encode_image(main_reference_image, crop=False)

    # --- Text conditioning ---
    pos_tokens = clip.tokenize(prompt or "")
    positive = clip.encode_from_tokens_scheduled(pos_tokens)
    neg_tokens = clip.tokenize("")
    negative = clip.encode_from_tokens_scheduled(neg_tokens)

    # Guard: SCAIL-2 (Wan 2.1) needs 4096-dim UMT5 conditioning. A 768-dim
    # embedding means the wrong text encoder loaded (e.g. a WanVideoWrapper
    # UMT5 mis-detected as SD1 CLIP-L) — fail early with a clear message
    # instead of the cryptic "mat1 and mat2 shapes cannot be multiplied".
    try:
        cond_dim = int(positive[0][0].shape[-1])
    except Exception:
        cond_dim = 0
    if cond_dim and cond_dim < 4096:
        raise RuntimeError(
            f"SCAIL-2 text conditioning is {cond_dim}-dim but the model needs "
            "4096-dim UMT5 embeddings. The loaded text encoder is not a "
            "ComfyUI-native UMT5. Install umt5_xxl_fp8_e4m3fn_scaled.safetensors "
            "into ComfyUI/models/text_encoders/ (the WanVideoWrapper "
            "'umt5-xxl-enc-*.safetensors' format is incompatible).")

    # --- Evict the encoders before sampling ---
    # Conditioning is fully computed by this point, so UMT5 and CLIP-vision are
    # dead weight. They are not small: UMT5-XXL stages ~10.8 GB (a 6.4 GB fp8
    # file upcast to bf16) and CLIP-vision another ~1.2 GB. Left resident, they
    # eat a 12 GB card before the 16.8 GB DiT is even considered, and no amount
    # of block swap recovers it — block swap only shrinks the DiT's own weight
    # budget, it cannot evict a model held by someone else. Same reason SVI
    # unloads here (see svi_synthesizer.py).
    # unload_all_models() moves weights to the offload device but keeps the
    # patchers alive, so the module-level cache stays valid for the next run.
    del pos_tokens, neg_tokens
    try:
        import comfy.model_management as _mm  # type: ignore[import-not-found]
        _mm.unload_all_models()
        _mm.soft_empty_cache()
    except Exception as exc:
        log.warning("SCAIL2: could not unload encoders before sampling: %s", exc)
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        log.info("SCAIL2: %.1f GB free after evicting encoders",
                 torch.cuda.mem_get_info()[0] / 1024**3)

    # --- Generate chunk-by-chunk (extend) ---
    # Each chunk produces `chunk_len` frames; subsequent chunks anchor on the
    # previous chunk's decoded tail (previous_frames) so the video stays
    # coherent past 81 frames. WanSCAILToVideo handles the offset math and
    # slices pose_video/pose_video_mask internally.
    n_chunks = 1 if total_length <= chunk_len else (
        1 + -(-(total_length - chunk_len) // (chunk_len - PREV_ANCHOR)))
    log.info("SCAIL2: %d frame(s) → %d chunk(s) of %d; %d steps, cfg=%.2f, %dx%d",
             total_length, n_chunks, chunk_len, steps, cfg, width, height)

    decoded_chunks: List[torch.Tensor] = []
    previous_frames = None
    video_frame_offset = 0
    for chunk_idx in range(n_chunks):
        scail_out = WanSCAILToVideo.execute(
            positive, negative, vae, width, height, chunk_len, 1,
            pose_strength=1.0, pose_start=0.0, pose_end=1.0,
            video_frame_offset=video_frame_offset, previous_frame_count=PREV_ANCHOR,
            replacement_mode=replacement_mode,
            reference_image=reference_image, clip_vision_output=clip_vision_output,
            pose_video=pose_video, pose_video_mask=pose_video_mask,
            reference_image_mask=reference_image_mask, previous_frames=previous_frames,
        )
        c_pos, c_neg, latent = scail_out[0], scail_out[1], scail_out[2]
        video_frame_offset = int(scail_out[3])

        latent_image = latent["samples"]
        noise_mask = latent.get("noise_mask")
        chunk_seed = seed + chunk_idx
        noise = comfy.sample.prepare_noise(latent_image, chunk_seed)
        samples = comfy.sample.sample(
            working_model, noise, steps, cfg, sampler_name, scheduler,
            c_pos, c_neg, latent_image,
            denoise=denoise, noise_mask=noise_mask, seed=chunk_seed,
        )
        full_chunk = vae.decode_tiled(samples) if tiled_vae else vae.decode(samples)
        if full_chunk.ndim == 5:
            full_chunk = full_chunk[0]  # [T, H, W, C]
        # Optional: color-match this chunk to the previous chunk's last frame to
        # stop slow exposure/hue drift across a long extend.
        if color_match and decoded_chunks:
            ref_frame = decoded_chunks[-1][-1].to(full_chunk.device, full_chunk.dtype)
            full_chunk = _reinhard_color_match(full_chunk, ref_frame)
        # Stitch: keep the first chunk whole; on later chunks drop the leading
        # anchor frames that overlap the previous chunk's tail.
        decoded_chunks.append(full_chunk if not decoded_chunks else full_chunk[PREV_ANCHOR:])
        # The next chunk anchors on this chunk's full decoded tail.
        previous_frames = full_chunk

    decoded = torch.cat(decoded_chunks, dim=0)[:total_length]

    # --- Encode outputs ---
    if mask_output_path is None:
        base, ext = os.path.splitext(output_path)
        mask_output_path = f"{base}_mask{ext or '.mp4'}"

    animation_path = _encode_video(decoded, output_path, fps)
    mask_video_path = _encode_video(pose_video_mask, mask_output_path, fps)
    log.info("SCAIL2: wrote animation=%s mask=%s", animation_path, mask_video_path)
    return animation_path, mask_video_path


def cleanup():
    """Release cached models and free GPU memory."""
    global _model, _vae_model, _clip_model, _clip_vision
    _model = None
    _vae_model = None
    _clip_model = None
    _clip_vision = None
    gc.collect()
    try:
        import comfy.model_management as mm  # type: ignore[import-not-found]
        mm.soft_empty_cache()
    except Exception:
        pass
    try:
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        pass
    log.info("SCAIL2: cleaned up GPU memory.")
