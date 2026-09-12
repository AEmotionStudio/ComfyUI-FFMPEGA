"""No-LLM mode handlers extracted from FFMPEGAgentNode.

Provides ``inject_effects_hints()``, ``process_effects_pipeline()``,
``process_sam3_only()``, ``process_whisper_only()``,
``process_mmaudio_only()``, ``process_lip_sync_only()``,
``process_animate_portrait_only()``, and ``process_flux_klein_only()``
— all the codepaths that run without an LLM.
"""

import json
import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

import torch  # type: ignore[import-not-found]

from ..output_handler import (
    build_output_path,
    collect_frame_output,
)

try:
    from ...core.bin_paths import get_ffmpeg_bin as _get_ffmpeg_bin
except ImportError:
    from core.bin_paths import get_ffmpeg_bin as _get_ffmpeg_bin  # type: ignore


logger = logging.getLogger("ffmpega")

# Quality encoding constants — shared by SAM3, Whisper, and MMAudio modes
_CRF_MAP = {"draft": 28, "standard": 23, "high": 18, "lossless": 0}
_PRESET_MAP = {"draft": "ultrafast", "standard": "medium", "high": "slow", "lossless": "veryslow"}


def inject_effects_hints(prompt: str, pipeline_json: str) -> str:
    """Inject FFMPEGAEffectsBuilder parameters into the prompt.

    This converts the pipeline_json from the effects builder node
    into explicit instructions for the LLM to follow.
    """
    try:
        data = json.loads(pipeline_json)
    except (ValueError, TypeError):
        return prompt

    steps = data.get("pipeline", [])
    raw = data.get("raw_ffmpeg", "")
    if not steps and not raw:
        return prompt

    hint_lines = [
        "\n\n--- EFFECTS BUILDER (pre-selected by user) ---",
        "The user has pre-selected the following effects. You MUST include",
        "these EXACT skills in your pipeline with the specified parameters.",
        "You may add additional skills if the user's prompt requires them.",
    ]

    for step in steps:
        skill = step.get("skill", "")
        params = step.get("params", {})
        if skill:
            params_str = ", ".join(f"{k}={v}" for k, v in params.items()) if params else "defaults"
            hint_lines.append(f"  - {skill} ({params_str})")

    if raw:
        hint_lines.append(f"  - RAW FFMPEG FILTERS: {raw}")

    hint_lines.append("--- END EFFECTS BUILDER ---")

    return prompt + "\n".join(hint_lines)


# ── SAM3 + Effects Builder merge ────────────────────────────────── #

# Skills that should NOT be wrapped in auto_mask (they're already
# mask-aware, meta-skills, or don't make sense applied to a region).
_SAM3_PASSTHROUGH_SKILLS = frozenset({
    "auto_mask", "auto_segment", "segment", "smart_mask",
    "sam2", "sam_mask", "ai_mask", "object_mask",
    "quality", "trim", "speed", "slowmo", "reverse",
    "concat", "xfade", "split_screen", "grid", "slideshow",
    "auto_transcribe", "transcribe", "karaoke_subtitles",
    "generate_audio", "generate_music",
    "normalize", "noise_reduction", "volume",
    "fade",
})

# Effects Builder effects that map directly to auto_mask effect names
_SKILL_TO_AUTOMASK_EFFECT = {
    "blur": "blur",
    "pixelate": "pixelate",
    "grayscale": "grayscale",
    "black_and_white": "grayscale",
    "remove": "remove",
    "highlight": "highlight",
    "greenscreen": "greenscreen",
    "thermal": "thermal",
}


# ── Shared SAM3 pre-masking helpers ─────────────────────────────── #

def sam3_premask(
    video_path: str,
    prompt: str,
    sam3_device: str = "gpu",
    sam3_max_objects: int = 5,
    sam3_det_threshold: float = 0.7,
    sam_version: str = "sam3.1",
) -> Optional[str]:
    """Run SAM3 / SAM 3.1 to generate a mask video from a text prompt.

    Returns the path to the mask video, or None if SAM is unavailable
    or the prompt is empty.
    """
    if not prompt or not prompt.strip():
        return None

    try:
        try:
            from ...core.sam3_masker import mask_video_subprocess as sam3_mask
        except ImportError:
            from core.sam3_masker import mask_video_subprocess as sam3_mask  # type: ignore
    except ImportError:
        logger.warning("SAM3 not available for pre-masking — skipping mask generation")
        return None

    try:
        logger.info("SAM pre-mask: generating mask for '%s' (version=%s)",
                    prompt.strip(), sam_version)
        mask_path = sam3_mask(
            video_path=video_path,
            prompt=prompt.strip(),
            device=sam3_device,
            max_objects=sam3_max_objects,
            det_threshold=sam3_det_threshold,
            version=sam_version or "sam3.1",
        )
        if mask_path and os.path.isfile(mask_path):
            logger.info("SAM3 pre-mask: mask video ready: %s", mask_path)
            return mask_path
        logger.warning("SAM3 pre-mask: no mask produced")
        return None
    except Exception as e:
        logger.error("SAM3 pre-mask failed: %s — proceeding without mask", e)
        return None


def sam3_composite(
    original_path: str,
    effect_path: str,
    mask_path: str,
    output_path: str,
    crf: int = 23,
    preset: str = "medium",
) -> str:
    """Composite effect output onto original using SAM3 mask via maskedmerge.

    Uses FFmpeg's ``maskedmerge`` filter:
    - Where mask is white → show effect_path
    - Where mask is black → show original_path

    Returns the path to the composited output.
    """
    _ffmpeg = _get_ffmpeg_bin()

    # maskedmerge: [base][overlay][mask] → output
    # base = original, overlay = effect result, mask = SAM3 grayscale
    fc = (
        "[0:v]format=yuv420p[base];"
        "[1:v]scale=iw:ih,format=yuv420p[fx];"
        "[2:v]scale=iw:ih,format=gray[mask];"
        "[base][fx][mask]maskedmerge[vout]"
    )

    composite_path = output_path + ".sam3_composite.mp4"
    cmd = [
        _ffmpeg, "-y",
        "-i", original_path,
        "-i", effect_path,
        "-i", mask_path,
        "-filter_complex", fc,
        "-map", "[vout]",
        "-map", "1:a?",
        "-c:v", "libx264",
        "-crf", str(crf),
        "-preset", preset,
        "-pix_fmt", "yuv420p",
        "-shortest",
        composite_path,
    ]

    logger.debug("SAM3 composite command: %s", " ".join(cmd))
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        logger.error("SAM3 composite failed: %s", proc.stderr[-500:])
        raise RuntimeError(f"SAM3 composite ffmpeg failed:\n{proc.stderr[-500:]}")

    # Replace the original output with the composited version
    if os.path.isfile(composite_path):
        os.replace(composite_path, output_path)
        logger.info("SAM3 composite: merged effect onto original → %s", output_path)
    return output_path


def merge_sam3_into_effects_pipeline(
    pipeline_json: str,
    prompt: str,
) -> str:
    """Wrap Effects Builder skill steps as auto_mask steps for SAM3 masking.

    When ``no_llm_mode=sam3_masking`` and the Effects Builder is connected,
    this function converts each visual effect step into an ``auto_mask`` step
    that applies the effect only to the SAM3-masked region.

    Steps that are already mask-aware (e.g. ``auto_mask``) or non-visual
    (e.g. ``quality``, ``trim``, ``fade``) are passed through unchanged.

    Args:
        pipeline_json: The raw JSON string from the Effects Builder node.
        prompt: The user's prompt text, used as the SAM3 text target.

    Returns:
        Modified pipeline JSON string with visual steps wrapped as auto_mask.
    """
    try:
        data = json.loads(pipeline_json)
    except (ValueError, TypeError):
        return pipeline_json

    steps = data.get("pipeline", [])
    if not steps:
        # No skills selected — inject a single auto_mask step with blur
        # so the user gets a useful result from sam3_masking mode
        data["pipeline"] = [{
            "skill": "auto_mask",
            "params": {
                "target": prompt.strip() or "the subject",
                "effect": "blur",
            },
        }]
        data["effects_mode"] = "skills"
        return json.dumps(data)

    new_steps = []
    target = prompt.strip() or "the subject"

    for step in steps:
        skill = step.get("skill", "")
        params = step.get("params", {})

        # Already an auto_mask step or a non-visual skill → pass through
        if skill in _SAM3_PASSTHROUGH_SKILLS:
            new_steps.append(step)
            continue

        # Map known skill names to auto_mask effect names
        effect = _SKILL_TO_AUTOMASK_EFFECT.get(skill)
        if effect:
            new_steps.append({
                "skill": "auto_mask",
                "params": {
                    "target": target,
                    "effect": effect,
                    "strength": params.get("strength", 50),
                    "invert": params.get("invert", False),
                },
            })
        else:
            # Any other visual/outcome skill — wrap as auto_mask with
            # the original skill name for dynamic filter resolution.
            # The auto_mask handler will call the skill's handler to
            # get its FFmpeg filter, then apply it through the mask.
            new_steps.append({
                "skill": "auto_mask",
                "params": {
                    "target": target,
                    "effect": skill,
                    "_original_skill": skill,
                    "_original_params": params,
                    "strength": params.get("strength", 50),
                    "invert": params.get("invert", False),
                },
            })

    data["pipeline"] = new_steps
    # Inject SAM3 config for downstream metadata
    data["sam3"] = {"target": target, "effect": "blur"}
    return json.dumps(data)


# ====================================================================== #
#  Rembg background removal (no LLM)                                      #
# ====================================================================== #


# ╔══════════════════════════════════════════════════════════════════╗
# ║  SCAIL — Pose-Driven Character Animation  (WIP)                 ║
# ╚══════════════════════════════════════════════════════════════════╝


# ================================================================== #
#  SHARP — single-image 3D Gaussian view synthesis                     #
# ================================================================== #

        # NOTE: Do NOT delete temp_render_dir here — the output video
        # lives inside it when save_output=False and downstream nodes
        # (save/preview) still need to read it.


# ================================================================== #
#  SVI 2.0 Pro — infinite-length video generation                      #
# ================================================================== #


# ═══════════════════════════════════════════════════════════════════════════
#  Wan-Animate  — Video-driven character animation (no-LLM mode)
# ═══════════════════════════════════════════════════════════════════════════


def _encode_frames_to_video(frames, output_path, fps=30):
    """Encode list of RGB numpy frames to MP4 using FFmpeg.

    Mirrors the color-space and dimension-padding logic from
    ``MediaConverter.images_to_video`` to ensure consistent output.
    """
    import subprocess
    import numpy as np

    if not frames:
        return

    # Ensure frames are RGB uint8
    first = frames[0]
    if first.ndim != 3 or first.shape[2] != 3:
        raise ValueError(
            f"_encode_frames_to_video: expected (H, W, 3) frames, got shape {first.shape}"
        )

    h, w = first.shape[:2]

    # yuv420p requires even dimensions — pad with edge replication if needed
    pad_w = (-w) % 2
    pad_h = (-h) % 2
    need_pad = pad_w > 0 or pad_h > 0
    if need_pad:
        w += pad_w
        h += pad_h

    try:
        from ...core.bin_paths import get_ffmpeg_bin
        ffmpeg_bin = get_ffmpeg_bin()
    except (ImportError, Exception):
        ffmpeg_bin = "ffmpeg"

    # Colour handling is shared with every other FFMPEGA encoder.  This used
    # to tag the output full-range while swscale wrote limited-range samples,
    # so players re-expanded levels that were never compressed.
    try:
        from ...core.video import encode_opts as _eo
    except (ImportError, Exception):
        from core.video import encode_opts as _eo  # type: ignore

    _spec = _eo.EncodeSpec(
        format="h264-mp4", crf=18, preset="fast", faststart=False,
    )
    cmd = [ffmpeg_bin, "-y"]
    cmd += _eo.raw_input_args(w, h, fps, _spec.bit_depth)
    _vf = _eo.video_filter(_spec)
    if _vf:
        cmd += ["-vf", _vf]
    cmd += _eo.video_output_args(_spec)
    cmd.append(output_path)
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        for frame in frames:
            f_uint8 = frame if frame.dtype == np.uint8 else (np.clip(frame, 0, 255)).astype(np.uint8)
            if need_pad:
                f_uint8 = np.pad(
                    f_uint8,
                    ((0, pad_h), (0, pad_w), (0, 0)),
                    mode="edge",
                )
            proc.stdin.write(np.ascontiguousarray(f_uint8).tobytes())
        proc.stdin.close()
    except BrokenPipeError:
        pass  # FFmpeg died early — capture stderr below
    proc.wait()
    if proc.returncode != 0:
        stderr = proc.stderr.read().decode(errors="replace")
        raise RuntimeError(
            f"FFmpeg encoding failed (rc={proc.returncode}), "
            f"frame shape=({h},{w},3), {len(frames)} frames:\n{stderr[-800:]}"
        )


# ---------------------------------------------------------------------------
#  PhyFPS (Visual Chronometer) — Physical Frame Rate Analysis
# ---------------------------------------------------------------------------
