# coding: utf-8
"""PhyFPS Synthesizer — Physical Frame Rate analysis via Visual Chronometer.

Predicts the *physical* frame rate (PhyFPS) implied by a video's motion
patterns using the Pulse-of-Motion Visual Chronometer model. Optionally
re-times the video so playback matches the detected PhyFPS.

Architecture follows the established synthesizer pattern:
- In-process GPU inference with cached model state
- ``_vram_utils.free_for_module()`` VRAM coordination
- safetensors model loading from HuggingFace

Source: https://github.com/taco-group/Pulse-of-Motion
License: Apache 2.0
"""

from __future__ import annotations

import gc
import logging
import os
import subprocess
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
import torch
import yaml

log = logging.getLogger("ffmpega")

# ---------------------------------------------------------------------------
#  Constants
# ---------------------------------------------------------------------------

_HF_REPO_PRIMARY = "AEmotionStudio/Visual_Chronometer"
_HF_REPO_UPSTREAM = "xiangbog/Visual_Chronometer"
_SAFETENSORS_FILENAME = "vc_common_10_60fps.safetensors"
_CKPT_FILENAME = "vc_common_10_60fps.ckpt"
_CONFIG_FILENAME = "config_fps.yaml"

# Model is ~100 MB — very lightweight
_MODEL_VRAM_BUDGET = 512 * 1024**2  # 512 MiB generous overestimate

# ---------------------------------------------------------------------------
#  Module-level state
# ---------------------------------------------------------------------------

_model: Optional[torch.nn.Module] = None
_device: Optional[str] = None


# ---------------------------------------------------------------------------
#  Model directory resolution
# ---------------------------------------------------------------------------


def _get_model_dir() -> Path:
    """Resolve model directory.

    Order:
    1. ``FFMPEGA_PHYFPS_MODEL_DIR`` env var
    2. ``ComfyUI/models/visual_chronometer/``
    3. Extension-local ``models/visual_chronometer/``
    """
    env_dir = os.environ.get("FFMPEGA_PHYFPS_MODEL_DIR")
    if env_dir:
        return Path(env_dir)

    # ComfyUI models folder
    comfy_root = Path(__file__).resolve().parent.parent.parent.parent  # ComfyUI/
    comfy_dir = comfy_root / "models" / "visual_chronometer"
    if comfy_dir.exists():
        return comfy_dir

    # Extension-local fallback
    ext_dir = Path(__file__).resolve().parent.parent / "models" / "visual_chronometer"
    ext_dir.mkdir(parents=True, exist_ok=True)
    return ext_dir


# ---------------------------------------------------------------------------
#  Download
# ---------------------------------------------------------------------------


def _download_model(model_dir: Path) -> Path:
    """Download safetensors from AEmotionStudio HF. Falls back to upstream .ckpt."""
    safetensors_path = model_dir / _SAFETENSORS_FILENAME
    ckpt_path = model_dir / _CKPT_FILENAME

    if safetensors_path.exists():
        return safetensors_path
    if ckpt_path.exists():
        return ckpt_path

    model_dir.mkdir(parents=True, exist_ok=True)

    from huggingface_hub import hf_hub_download

    # Try safetensors from mirror first
    try:
        log.info("Downloading Visual Chronometer (safetensors) from %s …", _HF_REPO_PRIMARY)
        downloaded = hf_hub_download(
            repo_id=_HF_REPO_PRIMARY,
            filename=_SAFETENSORS_FILENAME,
            local_dir=str(model_dir),
        )
        log.info("Downloaded to %s", downloaded)
        return Path(downloaded)
    except Exception as e:
        log.warning("Mirror download failed (%s), trying upstream .ckpt …", e)

    # Fallback to upstream .ckpt
    downloaded = hf_hub_download(
        repo_id=_HF_REPO_UPSTREAM,
        filename=_CKPT_FILENAME,
        local_dir=str(model_dir),
    )
    log.info("Downloaded upstream checkpoint to %s", downloaded)
    return Path(downloaded)


# ---------------------------------------------------------------------------
#  VRAM management
# ---------------------------------------------------------------------------


def _free_vram():
    """Ask other synthesizers to release VRAM before we load."""
    try:
        from ._vram_utils import free_for_module
    except ImportError:
        from core._vram_utils import free_for_module  # type: ignore
    free_for_module(exclude="phyfps_synthesizer", memory_needed=_MODEL_VRAM_BUDGET)


# ---------------------------------------------------------------------------
#  Model construction
# ---------------------------------------------------------------------------


def _build_model_from_config() -> torch.nn.Module:
    """Build FPSPredictor from the vendored config.

    The config references ``ckpt_path`` for the inner VAE. We set it to None
    since we load the full state dict externally (safetensors).
    """
    from .visual_chronometer.fps_predictor import FPSPredictor

    config_path = Path(__file__).resolve().parent / "visual_chronometer" / _CONFIG_FILENAME
    with open(config_path, "r") as f:
        config = yaml.safe_load(f)

    params = config["model"]["params"]
    # Don't let inner VAE try to load its own checkpoint
    params["ckpt_path"] = None
    params["freeze_encoder"] = False  # We set requires_grad=False ourselves after loading

    model = FPSPredictor(**params)
    return model


def load_model(device: str = "cuda") -> torch.nn.Module:
    """Load and cache the FPSPredictor model."""
    global _model, _device

    if _model is not None:
        if _device == device:
            return _model
        _model.to(device)
        _device = device
        return _model

    _free_vram()

    log.info("Loading Visual Chronometer FPSPredictor …")
    model_dir = _get_model_dir()
    weights_path = _download_model(model_dir)

    model = _build_model_from_config()

    # Load weights
    if weights_path.suffix == ".safetensors":
        from safetensors.torch import load_file
        sd = load_file(str(weights_path), device="cpu")
    else:
        ckpt = torch.load(str(weights_path), map_location="cpu", weights_only=True)
        sd = ckpt.get("state_dict", ckpt)

    model.load_state_dict(sd, strict=False)
    model.to(device)
    model.eval()

    # Freeze everything for inference
    for p in model.parameters():
        p.requires_grad = False

    _model = model
    _device = device
    log.info("Visual Chronometer loaded on %s (%.1f MB params)",
             device, sum(p.numel() for p in model.parameters()) * 4 / 1024**2)
    return model


# ---------------------------------------------------------------------------
#  Video preprocessing
# ---------------------------------------------------------------------------


def _extract_segments(
    video_path: str,
    clip_length: int = 30,
    stride: int = 4,
    resolution: int = 216,
) -> tuple[list[tuple[int, torch.Tensor]], int]:
    """Extract overlapping clips as normalized tensors.

    Returns:
        (segments, total_frames) where each segment is (start_frame, tensor[C,T,H,W])
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {video_path}")

    frames = []
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        frame = cv2.resize(frame, (resolution, resolution))
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        frames.append(frame)
    cap.release()

    total_frames = len(frames)
    if total_frames < clip_length:
        # Pad by repeating last frame
        pad_count = clip_length - total_frames
        last = frames[-1] if frames else np.zeros((resolution, resolution, 3), dtype=np.uint8)
        frames.extend([last] * pad_count)
        log.warning("Video has only %d frames, padded to %d", total_frames, len(frames))

    segments = []
    for start in range(0, len(frames) - clip_length + 1, stride):
        clip = np.stack(frames[start:start + clip_length])
        clip = clip.astype(np.float32) / 127.5 - 1.0  # normalize to [-1, 1]
        clip = torch.from_numpy(clip).permute(3, 0, 1, 2)  # [C, T, H, W]
        segments.append((start, clip))

    # Ensure at least one segment
    if not segments:
        clip = np.stack(frames[:clip_length])
        clip = clip.astype(np.float32) / 127.5 - 1.0
        clip = torch.from_numpy(clip).permute(3, 0, 1, 2)
        segments.append((0, clip))

    return segments, total_frames


# ---------------------------------------------------------------------------
#  Inference
# ---------------------------------------------------------------------------


@torch.no_grad()
def predict_phyfps(
    video_path: str,
    clip_length: int = 30,
    stride: int = 4,
    resolution: int = 216,
    device: str = "cuda",
) -> tuple[list[dict], float, int]:
    """Predict PhyFPS for a video.

    Returns:
        (per_segment_results, avg_phyfps, total_frames)
        Each segment dict: {start_frame, mid_frame, end_frame, predicted_phyfps}
    """
    model = load_model(device)

    segments, total_frames = _extract_segments(video_path, clip_length, stride, resolution)
    results = []

    for start_frame, clip in segments:
        clip_tensor = clip.unsqueeze(0).to(device)
        pred_log_fps = model(clip_tensor)
        fps = torch.exp(pred_log_fps).item()
        mid_frame = start_frame + clip_length // 2
        results.append({
            "start_frame": start_frame,
            "mid_frame": mid_frame,
            "end_frame": start_frame + clip_length - 1,
            "predicted_phyfps": round(fps, 1),
        })

    avg_fps = round(float(np.mean([r["predicted_phyfps"] for r in results])), 1)
    log.info("PhyFPS prediction: avg=%.1f fps (%d segments)", avg_fps, len(results))
    return results, avg_fps, total_frames


# ---------------------------------------------------------------------------
#  Correction (FFmpeg retiming)
# ---------------------------------------------------------------------------


def correct_video(
    video_path: str,
    container_fps: float,
    phyfps: float,
    output_path: str,
) -> str:
    """Re-time a video so playback matches PhyFPS.

    If PhyFPS > container FPS, the motion is too fast → slow down.
    If PhyFPS < container FPS, the motion is too slow → speed up.
    """
    try:
        from .bin_paths import get_ffmpeg_bin as _get_ffmpeg_bin
    except ImportError:
        from core.bin_paths import get_ffmpeg_bin as _get_ffmpeg_bin  # type: ignore

    ffmpeg = _get_ffmpeg_bin()

    speed_factor = phyfps / container_fps
    if abs(speed_factor - 1.0) < 0.05:
        log.info("PhyFPS ≈ container FPS (factor=%.3f), skipping correction", speed_factor)
        # Just copy the video
        cmd = [ffmpeg, "-y", "-i", video_path, "-c", "copy", output_path]
    else:
        # setpts adjusts video timing: PTS * factor
        # atempo adjusts audio: 1/factor (atempo range 0.5–2.0, chain if needed)
        setpts = f"PTS*{speed_factor:.6f}"

        cmd = [
            ffmpeg, "-y", "-i", video_path,
            "-filter:v", f"setpts={setpts}",
            "-r", str(container_fps),
        ]

        # Handle audio re-timing (skip if no audio)
        atempo_val = 1.0 / speed_factor
        if 0.5 <= atempo_val <= 2.0:
            cmd.extend(["-filter:a", f"atempo={atempo_val:.6f}"])
        elif atempo_val > 0:
            # Chain atempo filters for extreme values
            filters = []
            remaining = atempo_val
            while remaining > 2.0:
                filters.append("atempo=2.0")
                remaining /= 2.0
            while remaining < 0.5:
                filters.append("atempo=0.5")
                remaining /= 0.5
            filters.append(f"atempo={remaining:.6f}")
            cmd.extend(["-filter:a", ",".join(filters)])

        cmd.append(output_path)

    log.info("Correcting video: speed_factor=%.3f, cmd=%s", speed_factor, " ".join(cmd))
    subprocess.run(cmd, check=True, capture_output=True)
    return output_path


# ---------------------------------------------------------------------------
#  Analysis string builder
# ---------------------------------------------------------------------------


def build_analysis_string(
    video_name: str,
    results: list[dict],
    avg_phyfps: float,
    container_fps: float,
    total_frames: int,
    corrected: bool = False,
) -> str:
    """Build a human-readable analysis string for the CoT output."""
    lines = [
        f"═══ PhyFPS Analysis: {video_name} ═══",
        f"  Container FPS: {container_fps:.1f}",
        f"  Average PhyFPS: {avg_phyfps:.1f}",
        f"  Total Frames: {total_frames}",
        f"  Segments Analyzed: {len(results)}",
        "",
    ]

    speed_factor = avg_phyfps / container_fps if container_fps > 0 else 1.0
    if abs(speed_factor - 1.0) < 0.05:
        lines.append("  ✓ Motion matches declared frame rate")
    elif speed_factor > 1.0:
        lines.append(f"  ⚠ Motion appears {speed_factor:.1f}x FASTER than declared FPS")
    else:
        lines.append(f"  ⚠ Motion appears {1/speed_factor:.1f}x SLOWER than declared FPS")

    if corrected:
        lines.append(f"  ✓ Video re-timed to match PhyFPS (factor: {speed_factor:.3f})")

    lines.append("")
    lines.append(f"  {'Seg':>5}  {'Frames':>12}  {'Mid':>6}  {'PhyFPS':>8}")
    lines.append(f"  {'─'*5}  {'─'*12}  {'─'*6}  {'─'*8}")
    for i, r in enumerate(results):
        lines.append(
            f"  {i:>5d}  {r['start_frame']:>5d}-{r['end_frame']:<5d}  "
            f"{r['mid_frame']:>6d}  {r['predicted_phyfps']:>8.1f}"
        )
    lines.append(f"  {'─'*5}  {'─'*12}  {'─'*6}  {'─'*8}")
    lines.append(f"  {'AVG':>5}  {'':>12}  {'':>6}  {avg_phyfps:>8.1f}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
#  Cleanup / offload
# ---------------------------------------------------------------------------


def offload_to_cpu():
    """Move model to CPU to free VRAM but keep it cached for quick reload."""
    global _model, _device
    if _model is not None:
        _model.cpu()
        _device = "cpu"
        torch.cuda.empty_cache()
        log.info("PhyFPS model offloaded to CPU")


def cleanup():
    """Full cleanup — release model and free all memory.

    Called by ``_vram_utils.free_for_module()`` when another synthesizer
    needs VRAM.
    """
    global _model, _device
    if _model is not None:
        _model.cpu()
        del _model
        _model = None
        _device = None
        gc.collect()
        torch.cuda.empty_cache()
        log.info("PhyFPS model fully cleaned up")
