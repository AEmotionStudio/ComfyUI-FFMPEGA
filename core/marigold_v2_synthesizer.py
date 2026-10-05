# coding: utf-8
"""Marigold V2 dense geometry estimation for FFMPEGA.

Marigold V2 is a *frozen* Qwen-Image-Edit-2509 DiT plus a per-task LoRA, a
per-task VAE and a precomputed conditioning embedding. Inference is a single
deterministic Euler step with no CFG, no text encoder and no seed.

Unlike Marigold v1.1 (``core/marigold_synthesizer.py``, a diffusers pipeline),
V2's weights ship in ComfyUI single-file format and upstream has no diffusers
pipeline, so this module rebuilds the graph against ``comfy.*`` in-process.
Going through ``comfy.samplers`` rather than calling the DiT directly is what
buys us Wan21 latent scaling, LoRA-at-cast-time, int8_convrot matmul dispatch
and the lowvram block streaming that makes a 20.5 GB model run on a 12 GB card.

Nothing is imported at module scope beyond the stdlib: CI runs without torch.

Upstream: https://github.com/huawei-bayerlab/marigold-v2
Weights:  https://huggingface.co/Comfy-Org/marigold-v2-0

License:
    Apache-2.0 (code and weights). Qwen-Image-Edit-2509 keeps its own license.
"""

from __future__ import annotations

import gc
import logging
import os
import subprocess
import tempfile
from typing import Optional

try:
    from .bin_paths import get_ffmpeg_bin as _get_ffmpeg_bin
except ImportError:  # pragma: no cover - direct-script fallback
    from core.bin_paths import get_ffmpeg_bin as _get_ffmpeg_bin  # type: ignore

log = logging.getLogger("ffmpega")


# ---------------------------------------------------------------------------
#  Model registry
# ---------------------------------------------------------------------------

HF_REPO = "Comfy-Org/marigold-v2-0"

#: Pinned because Comfy-Org is a third-party repo — see core/hf_pins.py.
HF_REVISION = "70e2127d026c8f6b62d8049b73f5392e1e81ebfa"

#: The frozen base DiT, shared by every task. ~20.5 GB.
BASE_UNET = "qwen_image_edit_2509_int8_convrot.safetensors"

#: Qwen-Image transformer depth, for the block-swap size estimate.
NUM_BLOCKS = 60

#: The single Euler step. Do NOT "correct" this to 0.499: the reference's
#: ``torch.full((B,), 499.0, dtype=bfloat16)`` rounds ties-to-even to 500.0,
#: so its effective timestep is exactly 0.5.
SIGMA = 0.5

#: Filenames are listed explicitly rather than built with f-strings — depth's
#: LoRA and VAE carry a ``_log_stage2`` suffix that its conditioning does not.
_TASKS: dict[str, dict[str, str]] = {
    "depth": {
        "lora": "marigold_v2_depth_log_stage2.safetensors",
        "vae": "marigold_v2_depth_log_stage2_vae.safetensors",
        "conditioning": "marigold_v2_depth_conditioning.safetensors",
        "description": "Affine-invariant log depth",
    },
    "normals": {
        "lora": "marigold_v2_normals.safetensors",
        "vae": "marigold_v2_normals_vae.safetensors",
        "conditioning": "marigold_v2_normals_conditioning.safetensors",
        "description": "Camera-space surface normals",
    },
    "albedo": {
        "lora": "marigold_v2_albedo.safetensors",
        "vae": "marigold_v2_albedo_vae.safetensors",
        "conditioning": "marigold_v2_albedo_conditioning.safetensors",
        "description": "Linear-RGB albedo (intrinsic decomposition)",
    },
}

#: ComfyUI ``models/`` subfolder for each artefact kind. The HuggingFace repo
#: uses these same names at its top level, so one snapshot lands everything.
_FOLDERS = {
    "unet": "diffusion_models",
    "lora": "loras",
    "vae": "vae",
    "conditioning": "embeddings",
}

TASKS = tuple(_TASKS)


def task_names() -> tuple[str, ...]:
    """Public accessor for the supported modality names."""
    return TASKS


# ---------------------------------------------------------------------------
#  File resolution & download
# ---------------------------------------------------------------------------


def _find_existing(kind: str, filename: str) -> Optional[str]:
    """Look for ``filename`` in every registered path for its model folder.

    ``folder_paths.get_full_path`` consults a cached filename index that can be
    stale right after a download, so walk the directories directly.
    """
    import folder_paths  # type: ignore[import-not-found]

    for root in folder_paths.get_folder_paths(_FOLDERS[kind]):
        candidate = os.path.join(root, filename)
        if os.path.isfile(candidate):
            return candidate
    return None


def _required_files(output_type: str) -> dict[str, str]:
    """Map artefact kind -> filename for one task, including the shared base."""
    cfg = _TASKS[output_type]
    return {
        "unet": BASE_UNET,
        "lora": cfg["lora"],
        "vae": cfg["vae"],
        "conditioning": cfg["conditioning"],
    }


def _resolve_files(output_type: str) -> dict[str, str]:
    """Return absolute paths for every file this task needs, downloading once.

    The download is gated on what is actually missing, so users who already
    have the ~26 GB never hit the permission prompt.
    """
    wanted = _required_files(output_type)
    found: dict[str, str] = {}
    missing: dict[str, str] = {}

    for kind, filename in wanted.items():
        path = _find_existing(kind, filename)
        if path:
            found[kind] = path
        else:
            missing[kind] = filename

    if missing:
        _download(output_type, missing)
        for kind, filename in missing.items():
            path = _find_existing(kind, filename)
            if not path:
                raise RuntimeError(
                    f"Marigold V2: {filename} is still missing after download. "
                    f"Expected it in ComfyUI/models/{_FOLDERS[kind]}/."
                )
            found[kind] = path

    return found


def _download(output_type: str, missing: dict[str, str]) -> None:
    """Fetch only the missing artefacts from the pinned HF revision."""
    try:
        from .model_manager import require_downloads_allowed_for_missing
    except ImportError:  # pragma: no cover
        from core.model_manager import require_downloads_allowed_for_missing  # type: ignore

    import folder_paths  # type: ignore[import-not-found]

    expected = [
        os.path.join(folder_paths.models_dir, _FOLDERS[k], v)
        for k, v in missing.items()
    ]
    require_downloads_allowed_for_missing("marigold_v2", expected)

    patterns = [f"{_FOLDERS[k]}/{v}" for k, v in missing.items()]
    total_gb = 20.5 if "unet" in missing else 2.0
    log.info(
        "[MarigoldV2] Downloading %d file(s) for '%s' (~%.1f GB): %s",
        len(patterns), output_type, total_gb, ", ".join(missing.values()),
    )

    try:
        from .hf_pins import pinned_snapshot_download
    except ImportError:  # pragma: no cover
        from core.hf_pins import pinned_snapshot_download  # type: ignore

    pinned_snapshot_download(
        repo_id=HF_REPO,
        local_dir=folder_paths.models_dir,
        allow_patterns=patterns,
    )

    log.info("[MarigoldV2] Download complete")


# ---------------------------------------------------------------------------
#  Cached model state
# ---------------------------------------------------------------------------

#: (unet_filename, ModelPatcher) for the shared 20.5 GB base DiT.
_base_dit: Optional[tuple] = None

#: (output_type, sampling_mode, blocks_to_swap) -> _Loaded
_cache: dict = {}


class _Loaded:
    """One task's ready-to-sample bundle."""

    __slots__ = ("model", "vae", "conditioning")

    def __init__(self, model, vae, conditioning):
        self.model = model
        self.vae = vae
        self.conditioning = conditioning


def _free_vram() -> None:
    """Evict other FFMPEGA models before we claim VRAM."""
    try:
        from ._vram_utils import free_for_module
    except ImportError:  # pragma: no cover
        from core._vram_utils import free_for_module  # type: ignore
    free_for_module(exclude="marigold_v2_synthesizer")


def _make_model_sampling(model, sampling_mode: str):
    """Build the model_sampling object patch.

    ``img_to_img_velocity`` reproduces the reference implementation exactly:
    the DiT receives the un-scaled encoded latent ``z`` and the result is
    ``z - v``. The blueprint ComfyUI ships uses ``flow`` (plain ``CONST``),
    which feeds the DiT ``0.5 * z`` and returns ``0.5 * (z - v)`` — a
    half-scale, off-distribution latent. ``flow`` is kept only so the stock
    template's output can be reproduced for comparison.

    ``ModelSamplingFlux`` is QwenImage's own base class; ``shift`` is inert
    here because the sigmas are supplied explicitly rather than by a scheduler.
    """
    import comfy.model_sampling as cms  # type: ignore[import-not-found]

    velocity = cms.CONST if sampling_mode == "flow" else cms.IMG_TO_IMG_VELOCITY

    class _MarigoldModelSampling(cms.ModelSamplingFlux, velocity):  # type: ignore[misc,valid-type]
        pass

    return _MarigoldModelSampling(model.model.model_config)


def _load(output_type: str, sampling_mode: str, blocks_to_swap: int) -> _Loaded:
    """Load (or reuse) the patched model, VAE and conditioning for one task."""
    global _base_dit

    if output_type not in _TASKS:
        raise ValueError(
            f"Invalid Marigold V2 output_type '{output_type}'. "
            f"Must be one of: {list(_TASKS)}"
        )

    key = (output_type, sampling_mode, blocks_to_swap)
    cached = _cache.get(key)
    if cached is not None:
        log.info("[MarigoldV2] Reusing cached %s model", output_type)
        return cached

    import comfy.sd  # type: ignore[import-not-found]
    import comfy.utils  # type: ignore[import-not-found]

    paths = _resolve_files(output_type)
    _free_vram()

    # The 20.5 GB base is shared by all three tasks, so it is loaded once and
    # every task gets a cheap clone carrying only its own ~1.7 GB of patches.
    if _base_dit is None or _base_dit[0] != BASE_UNET:
        log.info("[MarigoldV2] Loading base DiT %s (~20.5 GB, first load is slow)", BASE_UNET)
        # model_options MUST stay empty: passing a dtype here bypasses the
        # int8_convrot quantisation path and blows the model up to bf16.
        _base_dit = (BASE_UNET, comfy.sd.load_diffusion_model(paths["unet"], model_options={}))

    log.info("[MarigoldV2] Applying %s LoRA + VAE + conditioning", output_type)

    lora_sd = comfy.utils.load_torch_file(paths["lora"], safe_load=True)
    model, _ = comfy.sd.load_lora_for_models(_base_dit[1], None, lora_sd, 1.0, 0)
    del lora_sd

    model.add_object_patch("model_sampling", _make_model_sampling(model, sampling_mode))

    if blocks_to_swap > 0:
        try:
            from .blockswap import register_blockswap
        except ImportError:  # pragma: no cover
            from core.blockswap import register_blockswap  # type: ignore
        register_blockswap(
            model, blocks_to_swap,
            key="marigold_v2", label="Marigold V2", num_blocks=NUM_BLOCKS,
        )

    vae_sd = comfy.utils.load_torch_file(paths["vae"], safe_load=True)
    vae = comfy.sd.VAE(sd=vae_sd)
    del vae_sd

    cond_sd = comfy.utils.load_torch_file(paths["conditioning"], safe_load=True)
    cond = cond_sd.get("conditioning")
    if cond is None:
        raise RuntimeError(
            f"{os.path.basename(paths['conditioning'])} has no 'conditioning' tensor"
        )
    conditioning = [[cond, {}]]

    loaded = _Loaded(model, vae, conditioning)
    _cache[key] = loaded
    log.info("[MarigoldV2] %s ready (sampling=%s)", output_type, sampling_mode)
    return loaded


def cleanup() -> None:
    """Drop every cached model and let ComfyUI reclaim the VRAM."""
    global _base_dit

    if not _cache and _base_dit is None:
        return

    _cache.clear()
    _base_dit = None

    gc.collect()
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except ImportError:  # pragma: no cover
        pass
    try:
        import comfy.model_management as mm  # type: ignore[import-not-found]
        mm.soft_empty_cache()
    except (ImportError, AttributeError):  # pragma: no cover
        pass

    log.info("[MarigoldV2] Models unloaded")


# ---------------------------------------------------------------------------
#  Inference
# ---------------------------------------------------------------------------

#: Qwen-Image patchifies latents 2x2 on top of the VAE's 8x spatial downscale,
#: so both dimensions must be a multiple of 16.
_GRID = 16


def _round_to_grid(value: int) -> int:
    return max(_GRID, (int(value) // _GRID) * _GRID)


def _resize(images, width: int, height: int, method: str = "lanczos"):
    """Resize an (N,H,W,C) batch with ComfyUI's own resampler."""
    import comfy.utils  # type: ignore[import-not-found]

    if images.shape[2] == width and images.shape[1] == height:
        return images
    # common_upscale works on (N,C,H,W).
    return comfy.utils.common_upscale(
        images.movedim(-1, 1), width, height, method, "disabled",
    ).movedim(1, -1)


def _predict_raw(loaded: _Loaded, image):
    """Run one image through the DiT and return the raw decoded prediction.

    Args:
        loaded: Bundle from ``_load``.
        image: (1,H,W,3) float tensor in [0,1].

    Returns:
        (1,H,W,3) float tensor, the decoder's raw ~[-1,1] output. The VAE's
        usual ``(x+1)/2`` clamp is bypassed: clamping before the normals are
        L2-normalised rotates them on axis-aligned surfaces.
    """
    import torch
    import comfy.sample  # type: ignore[import-not-found]
    import comfy.samplers  # type: ignore[import-not-found]
    from comfy_extras.nodes_custom_sampler import Guider_Basic  # type: ignore[import-not-found]

    vae = loaded.vae

    latent = vae.encode(image)

    guider = Guider_Basic(loaded.model)
    guider.set_conds(loaded.conditioning)

    sigmas = torch.tensor([SIGMA, 0.0], dtype=torch.float32)
    noise = comfy.sample.prepare_empty_noise(latent)

    samples = guider.sample(
        noise,
        latent,
        comfy.samplers.sampler_object("euler"),
        sigmas,
        denoise_mask=None,
        callback=None,
        disable_pbar=True,
        seed=0,
    )

    original_process_output = vae.process_output
    try:
        vae.process_output = lambda x: x
        decoded = vae.decode(samples)
    finally:
        vae.process_output = original_process_output

    # A 3-D-latent VAE decodes to (N,T,H,W,C); our T is always 1.
    if decoded.ndim == 5:
        decoded = decoded[:, 0]
    return decoded


def predict_images(
    images,
    output_type: str = "depth",
    sampling_mode: str = "img_to_img_velocity",
    blocks_to_swap: int = 0,
    max_res: int = 0,
    progress: bool = True,
):
    """Predict raw Marigold V2 output for a batch of images.

    This is the tensor-level entry point, kept separate from the file-level
    ``run_marigold_v2`` so other FFMPEGA subsystems can reuse it.

    Args:
        images: (N,H,W,3) float tensor in [0,1].
        output_type: 'depth', 'normals' or 'albedo'.
        sampling_mode: 'img_to_img_velocity' (correct) or 'flow' (stock blueprint).
        blocks_to_swap: Extra blocks to keep off-GPU. 0 is right on most cards.
        max_res: Longest-edge cap before the multiple-of-16 rounding. 0 = native.
        progress: Emit a ComfyUI progress bar.

    Returns:
        (N,H,W,3) float tensor of raw predictions at the input resolution.
    """
    import torch

    loaded = _load(output_type, sampling_mode, blocks_to_swap)

    n, src_h, src_w = images.shape[0], images.shape[1], images.shape[2]

    work_w, work_h = src_w, src_h
    if max_res and max(work_w, work_h) > max_res:
        scale = max_res / float(max(work_w, work_h))
        work_w, work_h = int(work_w * scale), int(work_h * scale)
    work_w, work_h = _round_to_grid(work_w), _round_to_grid(work_h)

    pbar = None
    if progress:
        try:
            import comfy.utils  # type: ignore[import-not-found]
            pbar = comfy.utils.ProgressBar(n)
        except (ImportError, AttributeError):  # pragma: no cover
            pbar = None

    out = []
    for i in range(n):
        frame = images[i:i + 1]
        # Lanczos down / bilinear back, matching the reference's
        # ReshapeToMultiple + resize_to_orig_res.
        resized = _resize(frame, work_w, work_h, "lanczos")
        raw = _predict_raw(loaded, resized)
        raw = _resize(raw, src_w, src_h, "bilinear")
        out.append(raw.float().cpu())

        if pbar is not None:
            pbar.update(1)
        if n > 1 and ((i + 1) % 25 == 0 or i == 0):
            log.info("[MarigoldV2] Frame %d/%d", i + 1, n)

    return torch.cat(out, dim=0)


# ---------------------------------------------------------------------------
#  Post-processing
# ---------------------------------------------------------------------------


def postprocess(
    raw,
    output_type: str = "depth",
    depth_polarity: str = "near_bright",
    depth_range: str = "global",
):
    """Turn raw predictions into a displayable (N,H,W,3) image batch in [0,1].

    Reimplements ComfyUI's ``MarigoldV2PostProcess`` with two deliberate
    differences: depth normalisation can span the whole batch (the stock node
    renormalises every frame against its own min/max, which strobes on video),
    and the depth polarity is selectable.

    Args:
        raw: (N,H,W,3) raw decoder output from ``predict_images``.
        output_type: 'depth', 'normals' or 'albedo'.
        depth_polarity: 'near_bright' (ComfyUI/MiDaS convention) or
            'far_bright' (what core/depth_shader_bridge.py expects).
        depth_range: 'global' (one range for the batch) or 'per_frame'
            (bit-identical to the stock node).
    """
    import torch

    if output_type == "normals":
        # Explicit epsilon, not F.normalize: its default eps=1e-12 amplifies
        # near-zero vectors to unit length instead of zeroing them, which
        # renders as noise rather than neutral grey.
        magnitude = raw.pow(2).sum(dim=-1, keepdim=True).sqrt()
        unit = raw / magnitude.clamp(min=1e-6)
        unit = torch.where(magnitude <= 1e-6, torch.zeros_like(unit), unit)
        return ((unit + 1.0) * 0.5).clamp(0.0, 1.0)

    if output_type == "albedo":
        linear = ((raw + 1.0) * 0.5).clamp(0.0, 1.0)
        # Gamma 2.2, matching the reference's _linear_to_srgb, which is
        # explicitly labelled "the Marigold V1 gamma-2.2 conversion".
        return linear.pow(1.0 / 2.2)

    # depth: mean over channels gives affine-invariant log depth, increasing
    # with distance.
    depth = raw.mean(dim=-1, keepdim=True)
    if depth_range == "per_frame":
        lo = depth.amin(dim=(1, 2, 3), keepdim=True)
        hi = depth.amax(dim=(1, 2, 3), keepdim=True)
    else:
        lo = depth.amin()
        hi = depth.amax()

    normalized = (depth - lo) / (hi - lo).clamp(min=1e-6)
    if depth_polarity == "near_bright":
        normalized = 1.0 - normalized
    return normalized.clamp(0.0, 1.0).repeat(1, 1, 1, 3)


# ---------------------------------------------------------------------------
#  Media I/O
# ---------------------------------------------------------------------------

_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".webp"}


def _read_frames(input_path: str, max_frames: int = 0):
    """Decode a video or still into an (N,H,W,3) float tensor in [0,1].

    Returns ``(images, fps, truncated)``. An IMAGE tensor reaching FFMPEGA is
    always materialised as a temp mp4, so callers must branch on the returned
    frame count rather than on the file extension.
    """
    import cv2
    import numpy as np
    import torch

    ext = os.path.splitext(input_path)[1].lower()
    if ext in _IMAGE_EXTS:
        bgr = cv2.imread(input_path, cv2.IMREAD_COLOR)
        if bgr is None:
            raise RuntimeError(f"Cannot read image: {input_path}")
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        arr = np.asarray(rgb, dtype=np.float32) / 255.0
        return torch.from_numpy(arr).unsqueeze(0), 0.0, False

    cap = cv2.VideoCapture(input_path)
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {input_path}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 24.0

    frames = []
    truncated = False
    try:
        while True:
            ok, bgr = cap.read()
            if not ok:
                break
            if max_frames and len(frames) >= max_frames:
                truncated = True
                break
            rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
            frames.append(np.asarray(rgb, dtype=np.float32) / 255.0)
    finally:
        cap.release()

    if not frames:
        raise RuntimeError(f"No frames decoded from: {input_path}")

    return torch.from_numpy(np.stack(frames)), fps, truncated


def _write_output(images, output_path: str, fps: float) -> None:
    """Write an (N,H,W,3) [0,1] batch out as a PNG (N==1) or an MP4."""
    import cv2
    import numpy as np

    arr = (images.clamp(0.0, 1.0) * 255.0).round().to("cpu").numpy().astype(np.uint8)

    if arr.shape[0] == 1:
        cv2.imwrite(output_path, cv2.cvtColor(arr[0], cv2.COLOR_RGB2BGR))
        return

    tmp_dir = tempfile.mkdtemp(prefix="marigold_v2_")
    try:
        for i, frame in enumerate(arr):
            cv2.imwrite(
                os.path.join(tmp_dir, f"{i:06d}.png"),
                cv2.cvtColor(frame, cv2.COLOR_RGB2BGR),
            )
        rate = fps if fps and fps > 0 else 24.0
        fps_str = str(int(round(rate))) if round(rate, 2) == int(round(rate)) else f"{rate:.2f}"
        cmd = [
            _get_ffmpeg_bin(), "-y",
            "-framerate", fps_str,
            "-i", os.path.join(tmp_dir, "%06d.png"),
            "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2",
            "-c:v", "libx264",
            "-crf", "18",
            "-pix_fmt", "yuv420p",
            output_path,
        ]
        subprocess.run(cmd, check=True, capture_output=True)
    finally:
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
#  Main entry point
# ---------------------------------------------------------------------------


def run_marigold_v2(
    input_path: str,
    output_type: str = "depth",
    depth_polarity: str = "near_bright",
    depth_range: str = "auto",
    sampling_mode: str = "img_to_img_velocity",
    max_res: int = 0,
    max_frames: int = 0,
    blocks_to_swap: int = 0,
) -> str:
    """Run Marigold V2 on an image or video and return the output path.

    Mirrors ``core.marigold_synthesizer.run_marigold``'s file-in/file-out
    contract so the no-LLM mode and skill handler can route to either version.

    Args:
        input_path: Source image or video.
        output_type: 'depth', 'normals' or 'albedo'.
        depth_polarity: 'near_bright' or 'far_bright' (depth only).
        depth_range: 'auto' (global for clips, per-frame for stills),
            'global' or 'per_frame'.
        sampling_mode: 'img_to_img_velocity' (matches the reference) or
            'flow' (reproduces ComfyUI's shipped blueprint).
        max_res: Longest-edge cap. 0 = native resolution.
        max_frames: Stop after this many frames. 0 = no limit.
        blocks_to_swap: Extra transformer blocks to keep off-GPU.

    Returns:
        Path to the rendered output (PNG for a still, MP4 for a clip).
    """
    if output_type not in _TASKS:
        raise ValueError(
            f"Invalid Marigold V2 output_type '{output_type}'. "
            f"Must be one of: {list(_TASKS)}"
        )
    if not os.path.isfile(input_path):
        raise RuntimeError(f"Input file not found: {input_path}")

    images, fps, truncated = _read_frames(input_path, max_frames)
    n = images.shape[0]
    if truncated:
        log.warning("[MarigoldV2] Input truncated to max_frames=%d", max_frames)

    log.info(
        "[MarigoldV2] %s on %d frame(s) at %dx%d (sampling=%s)",
        output_type, n, images.shape[2], images.shape[1], sampling_mode,
    )
    if n > 1:
        log.info(
            "[MarigoldV2] Marigold V2 is a per-frame model with no temporal "
            "component; expect roughly 3-4 s/frame. Video Depth Anything or "
            "Marigold v1.1 are faster and temporally consistent."
        )

    raw = predict_images(
        images,
        output_type=output_type,
        sampling_mode=sampling_mode,
        blocks_to_swap=blocks_to_swap,
        max_res=max_res,
    )

    effective_range = depth_range
    if effective_range == "auto":
        effective_range = "global" if n > 1 else "per_frame"

    rendered = postprocess(
        raw,
        output_type=output_type,
        depth_polarity=depth_polarity,
        depth_range=effective_range,
    )

    suffix = f"_marigold_v2_{output_type}" + (".png" if n == 1 else ".mp4")
    fd, output_path = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
    _write_output(rendered, output_path, fps)

    log.info("[MarigoldV2] Output saved to %s", output_path)
    return output_path
