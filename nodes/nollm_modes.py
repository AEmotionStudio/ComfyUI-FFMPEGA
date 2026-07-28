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

from .output_handler import (
    build_output_path,
    collect_frame_output,
)

try:
    from ..core.bin_paths import get_ffmpeg_bin as _get_ffmpeg_bin
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
            from ..core.sam3_masker import mask_video_subprocess as sam3_mask
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


async def process_effects_pipeline(
    # dependencies (injected from agent node)
    composer,
    process_manager,
    media_converter,
    # parameters
    pipeline_json: str,
    prompt: str,
    effective_video_path: str,
    video_metadata,
    save_output: bool,
    output_path: str,
    preview_mode: bool,
    quality_preset: str,
    crf: int,
    encoding_preset: str,
    whisper_device: str = "cpu",
    whisper_model: str = "large-v3",
    sam3_device: str = "gpu",
    sam3_max_objects: int = 5,
    sam3_det_threshold: float = 0.7,
    mask_points: str = "",
    use_flux_klein: bool = False,
    use_minimax_remover: bool = False,
    flux_smoothing: str = "none",
    temp_video_from_images: Optional[str] = None,
    temp_video_with_audio: Optional[str] = None,
    image_a=None,
    audio_a=None,
    _all_video_paths: Optional[list] = None,
    _all_image_paths: Optional[list] = None,
    _all_text_inputs: Optional[list] = None,
    # inject_extra_inputs needs self-like access to composer
    _inject_extra_inputs_fn=None,
    **kwargs,
) -> tuple[torch.Tensor, dict, str, str, str, str]:
    """Execute an Effects Builder pipeline directly (no LLM).

    Parses the JSON from the Effects Builder node and constructs a
    Pipeline from the skill steps + optional raw FFmpeg filters.

    Returns the standard 6-tuple.
    """
    try:
        from ..skills.composer import Pipeline  # type: ignore[import-not-found]
    except ImportError:
        from skills.composer import Pipeline  # type: ignore

    try:
        data = json.loads(pipeline_json)
    except (ValueError, TypeError) as exc:
        raise RuntimeError(f"Effects Builder: invalid pipeline JSON: {exc}") from exc

    steps = data.get("pipeline", [])
    raw_ffmpeg = data.get("raw_ffmpeg", "")
    effects_mode = data.get("effects_mode", "empty")
    overlay_text = data.get("overlay_text", "")
    use_prompt_text = data.get("use_prompt_as_text", False)

    # When mode is empty but text is available, auto-inject a text_overlay step
    if effects_mode == "empty" and not raw_ffmpeg:
        has_text = bool(overlay_text and overlay_text.strip())
        has_prompt_text = bool(use_prompt_text and prompt and prompt.strip())
        if has_text or has_prompt_text:
            steps = [{"skill": "text_overlay", "params": {}}]
            effects_mode = "skills"
            logger.info("Effects Builder: auto-injected text_overlay step from text input")
        else:
            raise RuntimeError(
                "Effects Builder: no effects selected and no raw FFmpeg filters. "
                "Please select at least one effect or provide raw filters."
            )

    logger.info(
        "Effects Builder mode: %s — %d skills, raw=%s",
        effects_mode, len(steps), bool(raw_ffmpeg),
    )

    # --- Build output path ---
    output_path, temp_render_dir = build_output_path(
        effective_video_path=effective_video_path,
        save_output=save_output,
        output_path=output_path,
        preview_mode=preview_mode,
    )

    # --- Construct Pipeline from effects JSON ---
    pipeline = Pipeline(input_path=effective_video_path, output_path=output_path)

    # Set metadata
    input_fps = (
        video_metadata.primary_video.frame_rate
        if video_metadata.primary_video and video_metadata.primary_video.frame_rate
        else 24
    )
    pipeline.metadata["_input_fps"] = int(round(input_fps))
    if video_metadata.primary_video:
        pipeline.metadata["_input_width"] = video_metadata.primary_video.width
        pipeline.metadata["_input_height"] = video_metadata.primary_video.height

    # SAM3 preferences (for auto_mask steps)
    pipeline.metadata["_sam3_device"] = sam3_device
    pipeline.metadata["_sam3_max_objects"] = sam3_max_objects
    pipeline.metadata["_sam3_det_threshold"] = sam3_det_threshold
    if mask_points and mask_points.strip():
        pipeline.metadata["_mask_points"] = mask_points.strip()
    pipeline.metadata["_enable_flux_klein"] = use_flux_klein
    pipeline.metadata["_flux_klein_model"] = kwargs.get("flux_klein_model", "4b")
    pipeline.metadata["_enable_kiwi_edit"] = kwargs.get("use_kiwi_edit", False)
    pipeline.metadata["_enable_minimax_remover"] = use_minimax_remover
    if flux_smoothing and flux_smoothing != "none":
        pipeline.metadata["_flux_smoothing"] = flux_smoothing

    # Whisper preferences (for transcription steps)
    pipeline.metadata["_whisper_device"] = whisper_device
    pipeline.metadata["_whisper_model"] = whisper_model

    # Add skill steps from the effects builder
    for step in steps:
        skill_name = step.get("skill", "")
        params = step.get("params", {})
        if skill_name:
            pipeline.add_step(skill_name, params)

    # --- Inject overlay text into text_overlay steps ---
    # Priority: overlay_text (from raw_ffmpeg box) > prompt (when use_prompt_as_text)
    effective_text = overlay_text.strip() if overlay_text else ""
    if not effective_text and use_prompt_text and prompt:
        effective_text = prompt.strip()

    if effective_text:
        _TEXT_OVERLAY_SKILLS = {"text_overlay", "text", "drawtext", "title", "subtitle", "caption"}
        for step in steps:
            skill = step.get("skill", "")
            params = step.get("params", {})
            if skill in _TEXT_OVERLAY_SKILLS and not params.get("text"):
                params["text"] = effective_text
        logger.info("Effects Builder: injected overlay text (%d chars) into text_overlay steps",
                     len(effective_text))

    # --- Inject extra inputs (multi-input for concat/grid/etc.) ---
    assert _inject_extra_inputs_fn is not None, "_inject_extra_inputs_fn must be provided"
    (
        effective_video_path,
        temp_multi_videos,
        temp_audio_files,
        temp_frames_dirs,
        temp_audio_input,
    ) = _inject_extra_inputs_fn(
        pipeline=pipeline,
        effective_video_path=effective_video_path,
        image_a=image_a,
        _all_image_paths=_all_image_paths or [],
        _all_video_paths=_all_video_paths or [],
        _all_text_inputs=_all_text_inputs or [],
        audio_a=audio_a,
        **kwargs,
    )
    pipeline.input_path = effective_video_path

    # Quality preset (unless overridden by skills)
    _NO_QUALITY_PRESET_SKILLS = {"gif", "webm"}
    if quality_preset and not any(
        s.skill_name in _NO_QUALITY_PRESET_SKILLS for s in pipeline.steps
    ):
        pipeline.add_step("quality", {
            "crf": crf if crf >= 0 else _CRF_MAP.get(quality_preset, 23),
            "preset": encoding_preset if encoding_preset != "auto" else _PRESET_MAP.get(quality_preset, "medium"),
        })

    # --- Compose & execute ---
    command = composer.compose(pipeline)

    # Inject raw FFmpeg filters (appended to video filter chain)
    if raw_ffmpeg and raw_ffmpeg.strip():
        # Collapse newlines → commas so multi-line input is treated
        # as comma-separated filters instead of breaking the command.
        sanitized = raw_ffmpeg.replace("\r", "").replace("\n", ",")
        for raw_filter in sanitized.strip().split(","):
            raw_filter = raw_filter.strip()
            if not raw_filter:
                continue
            # Basic validation: a valid filter is either "name=params"
            # or a standalone filter name (alphanumeric/underscores).
            if "=" in raw_filter:
                name, _, param_str = raw_filter.partition("=")
                if name.strip().replace("_", "").isalnum():
                    command.video_filters.add_filter(name.strip(), {"": param_str})
                else:
                    logger.warning("Effects Builder: skipped invalid raw filter: %s", raw_filter)
            elif raw_filter.replace("_", "").isalnum():
                command.video_filters.add_filter(raw_filter)
            else:
                logger.warning("Effects Builder: skipped invalid raw filter: %s", raw_filter)
        logger.info("Effects Builder: appended raw filters: %s", sanitized.strip())

    logger.debug("Effects Builder command: %s", command.to_string())

    if preview_mode:
        if command.complex_filter:
            command.output_options.extend(["-s", "480x270"])
        else:
            command.video_filters.add_filter("scale", {"w": 480, "h": -1})
        command.output_options.extend(["-t", "10"])

    result = process_manager.execute(command, timeout=600)
    if not result.success:
        raise RuntimeError(
            f"Effects Builder: FFMPEG execution failed: {result.error_message}\n"
            f"Command: {command.to_string()}"
        )

    # --- Collect frame/audio output ---
    unique_id = str(kwargs.get("unique_id", ""))
    hidden_prompt = kwargs.get("hidden_prompt") or {}
    # Resample audio if user toggled the option (e.g. 96kHz → 48kHz for MP3)
    _resample = kwargs.get("audio_resample_rate", "off")
    _resample_rate = int(_resample) if _resample and _resample != "off" else None
    images_tensor, audio_out = collect_frame_output(
        media_converter=media_converter,
        output_path=output_path,
        unique_id=unique_id,
        hidden_prompt=hidden_prompt,
        removes_audio="-an" in command.output_options,
        resample_rate=_resample_rate,
    )

    # --- Mask overlay (if auto_mask was used) ---
    mask_overlay_path = ""
    mask_video_path = pipeline.metadata.get("_mask_video_path", "")
    if mask_video_path and os.path.isfile(mask_video_path):
        mask_type = kwargs.get("mask_output_type", "colored_overlay")
        if mask_type == "black_white":
            mask_overlay_path = mask_video_path
        else:
            try:
                try:
                    from ..core.sam3_masker import generate_mask_overlay
                except ImportError:
                    from core.sam3_masker import generate_mask_overlay  # type: ignore
                mask_overlay_path = generate_mask_overlay(
                    video_path=effective_video_path,
                    mask_video_path=mask_video_path,
                )
            except Exception as e:
                logger.warning("Effects Builder: mask overlay failed: %s", e)

    # --- Build analysis string ---
    step_summary = "\n".join(
        f"  {i+1}. {s.get('skill', '?')} {s.get('params', {})}"
        for i, s in enumerate(steps)
    )
    analysis = (
        f"Effects Builder Mode (no LLM)\n"
        f"Mode: {effects_mode}\n"
        f"Steps:\n{step_summary}\n"
        f"{'Raw filters: ' + raw_ffmpeg if raw_ffmpeg else ''}\n\n"
        f"Pipeline:\n{composer.explain_pipeline(pipeline)}"
    )

    # --- Cleanup temp files ---
    for tmp_path in [temp_video_from_images, temp_video_with_audio, temp_audio_input]:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
    for tmp_path in temp_multi_videos + temp_audio_files:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
    for tmp_dir in temp_frames_dirs:
        if tmp_dir and os.path.isdir(tmp_dir):
            shutil.rmtree(tmp_dir, ignore_errors=True)
    if not save_output and temp_render_dir and os.path.isdir(temp_render_dir):
        if not os.listdir(temp_render_dir):
            shutil.rmtree(temp_render_dir, ignore_errors=True)

    return (images_tensor, audio_out, output_path, command.to_string(), analysis, mask_overlay_path)


async def process_sam3_only(
    # dependencies
    media_converter,
    # parameters
    prompt: str,
    effective_video_path: str,
    video_metadata,
    save_output: bool,
    output_path: str,
    preview_mode: bool,
    quality_preset: str,
    crf: int,
    encoding_preset: str,
    sam3_device: str,
    sam3_max_objects: int,
    sam3_det_threshold: float,
    mask_points: str,
    temp_video_from_images: Optional[str],
    temp_video_with_audio: Optional[str],
    **kwargs,
) -> tuple[torch.Tensor, dict, str, str, str, str]:
    """Run SAM3 masking directly without any LLM involvement.

    Calls ``mask_video_subprocess`` directly — the main video output is
    a clean copy of the source (no effects applied).  The SAM3 mask is
    output via the ``mask_overlay_path`` (colored overlay or raw B&W).

    Returns the standard 6-tuple:
        (images_tensor, audio, output_path, command_log, analysis, mask_overlay_path)
    """
    logger.info("SAM3-only mode: using prompt as text target → '%s'", prompt)

    # --- Build output path ---
    output_path, temp_render_dir = build_output_path(
        effective_video_path=effective_video_path,
        save_output=save_output,
        output_path=output_path,
        preview_mode=preview_mode,
    )

    # --- Parse point prompts (from the JS point selector) ---
    point_coords = None
    point_labels = None
    point_src_w = 0
    point_src_h = 0
    if mask_points and mask_points.strip():
        try:
            pt_data = json.loads(mask_points)
            if isinstance(pt_data, dict):
                point_coords = pt_data.get("points")
                point_labels = pt_data.get("labels")
                point_src_w = int(pt_data.get("image_width", 0))
                point_src_h = int(pt_data.get("image_height", 0))
                if point_coords and point_labels:
                    logger.info("SAM3-only: using %d point prompt(s) (src %dx%d)",
                                len(point_coords), point_src_w, point_src_h)
        except (ValueError, TypeError) as exc:
            logger.warning("SAM3-only: failed to parse mask_points JSON: %s", exc)

    # --- Run SAM3 directly (no auto_mask handler, no effects) ---
    try:
        from ..core.sam3_masker import mask_video_subprocess as sam3_mask_video
    except ImportError:
        from core.sam3_masker import mask_video_subprocess as sam3_mask_video  # type: ignore

    try:
        mask_video_path = sam3_mask_video(
            video_path=effective_video_path,
            prompt=prompt,
            device=sam3_device,
            max_objects=sam3_max_objects,
            det_threshold=sam3_det_threshold,
            points=point_coords,
            labels=point_labels,
            point_src_width=point_src_w,
            point_src_height=point_src_h,
        )
    except Exception as e:
        logger.error("SAM3-only: mask generation failed: %s", e)
        raise RuntimeError(f"SAM3 mask generation failed: {e}") from e

    # --- Copy source video through as the main output (no effects) ---
    effective_crf = crf if crf >= 0 else _CRF_MAP.get(quality_preset, 23)
    effective_preset = encoding_preset if encoding_preset != "auto" else _PRESET_MAP.get(quality_preset, "medium")

    _ffmpeg = _get_ffmpeg_bin()
    ffmpeg_cmd = [
        _ffmpeg, "-y",
        "-i", effective_video_path,
        "-c:v", "libx264",
        "-crf", str(effective_crf),
        "-preset", effective_preset,
        "-pix_fmt", "yuv420p",
        "-c:a", "copy",
        output_path,
    ]

    if preview_mode:
        # Insert scale + duration limit before output path
        ffmpeg_cmd = [
            _ffmpeg, "-y",
            "-i", effective_video_path,
            "-vf", "scale=480:trunc(ow/a/2)*2",
            "-t", "10",
            "-c:v", "libx264",
            "-crf", str(effective_crf),
            "-preset", effective_preset,
            "-pix_fmt", "yuv420p",
            "-c:a", "copy",
            output_path,
        ]

    logger.debug("SAM3-only passthrough command: %s", " ".join(ffmpeg_cmd))
    proc = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"SAM3-only mode: video passthrough failed:\n{proc.stderr[-500:]}"
        )

    # --- Collect frame/audio output ---
    unique_id = str(kwargs.get("unique_id", ""))
    hidden_prompt = kwargs.get("hidden_prompt") or {}
    images_tensor, audio_out = collect_frame_output(
        media_converter=media_converter,
        output_path=output_path,
        unique_id=unique_id,
        hidden_prompt=hidden_prompt,
        removes_audio=False,
    )

    # --- Generate mask overlay ---
    mask_overlay_path = ""
    if mask_video_path and os.path.isfile(mask_video_path):
        mask_type = kwargs.get("mask_output_type", "colored_overlay")
        if mask_type == "black_white":
            mask_overlay_path = mask_video_path
            logger.info("SAM3-only: B&W mask video → %s", mask_overlay_path)
        else:
            try:
                try:
                    from ..core.sam3_masker import generate_mask_overlay
                except ImportError:
                    from core.sam3_masker import generate_mask_overlay  # type: ignore
                mask_overlay_path = generate_mask_overlay(
                    video_path=effective_video_path,
                    mask_video_path=mask_video_path,
                )
                logger.info("SAM3-only: colored overlay → %s", mask_overlay_path)
            except Exception as e:
                logger.warning("SAM3-only: mask overlay generation failed: %s", e)

    # --- Build analysis string ---
    cmd_log = " ".join(ffmpeg_cmd)
    analysis = (
        f"SAM3-Only Mode (no LLM)\n"
        f"Text target: {prompt}\n"
        f"Device: {sam3_device}\n"
        f"Max objects: {sam3_max_objects}\n"
        f"Detection threshold: {sam3_det_threshold}\n"
        f"Point prompts: {'yes' if mask_points else 'no'}\n\n"
        f"Main output: clean passthrough (no effects)\n"
        f"Mask output: {mask_overlay_path or mask_video_path or 'none'}"
    )

    # --- Cleanup temp files ---
    for tmp_path in [temp_video_from_images, temp_video_with_audio]:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
    if not save_output and temp_render_dir and os.path.isdir(temp_render_dir):
        if not os.listdir(temp_render_dir):
            shutil.rmtree(temp_render_dir, ignore_errors=True)

    return (images_tensor, audio_out, output_path, cmd_log, analysis, mask_overlay_path)


async def process_whisper_only(
    # dependencies
    media_converter,
    # parameters
    mode: str,
    effective_video_path: str,
    video_metadata,
    save_output: bool,
    output_path: str,
    preview_mode: bool,
    quality_preset: str,
    crf: int,
    encoding_preset: str,
    whisper_device: str = "cpu",
    whisper_model: str = "large-v3",
    temp_video_from_images: Optional[str] = None,
    temp_video_with_audio: Optional[str] = None,
    **kwargs,
) -> tuple[torch.Tensor, dict, str, str, str, str]:
    """Run Whisper transcription directly without any LLM involvement.

    Transcribes the video audio using Whisper and burns subtitles
    (SRT or karaoke ASS) into the output video.  The full transcription
    text is included in the ``analysis`` return field.

    Args:
        mode: "transcribe" for SRT subtitles, "karaoke_subtitles" for
              word-by-word karaoke ASS subtitles.

    Returns the standard 6-tuple:
        (images_tensor, audio, output_path, command_log, analysis, mask_overlay_path)
    """
    try:
        from ..core.whisper_transcriber import (
            transcribe_audio,
            segments_to_srt,
            words_to_karaoke_ass,
        )
    except ImportError:
        from core.whisper_transcriber import (  # type: ignore
            transcribe_audio,
            segments_to_srt,
            words_to_karaoke_ass,
        )

    logger.info(
        "Whisper-only mode (%s): device=%s, model=%s",
        mode, whisper_device, whisper_model,
    )

    # --- Build output path ---
    output_path, temp_render_dir = build_output_path(
        effective_video_path=effective_video_path,
        save_output=save_output,
        output_path=output_path,
        preview_mode=preview_mode,
    )

    # --- Transcribe ---
    result = transcribe_audio(
        effective_video_path,
        model_size=whisper_model,
        device=whisper_device,
    )

    # --- Generate subtitle file ---
    sub_tmp_path = None  # track for cleanup after ffmpeg
    if mode == "karaoke_subtitles":
        if not result.words:
            logger.warning("Whisper found no words — producing clean passthrough")
            sub_filter = None
        else:
            ass_content = words_to_karaoke_ass(result.words)
            tmp = tempfile.NamedTemporaryFile(
                mode="w", suffix=".ass", delete=False, encoding="utf-8",
            )
            tmp.write(ass_content)
            tmp.close()
            sub_tmp_path = tmp.name

            try:
                from ..core.sanitize import ffmpeg_escape_path
            except ImportError:
                from core.sanitize import ffmpeg_escape_path  # type: ignore
            escaped_path = ffmpeg_escape_path(tmp.name)
            sub_filter = f"ass={escaped_path}"
    else:
        # mode == "transcribe"
        if not result.segments:
            logger.warning("Whisper found no speech — producing clean passthrough")
            sub_filter = None
        else:
            srt_content = segments_to_srt(result.segments)
            tmp = tempfile.NamedTemporaryFile(
                mode="w", suffix=".srt", delete=False, encoding="utf-8",
            )
            tmp.write(srt_content)
            tmp.close()
            sub_tmp_path = tmp.name

            try:
                from ..core.sanitize import ffmpeg_escape_path
            except ImportError:
                from core.sanitize import ffmpeg_escape_path  # type: ignore
            escaped_path = ffmpeg_escape_path(tmp.name)
            sub_filter = f"subtitles={escaped_path}"

    # --- Build ffmpeg command ---
    effective_crf = crf if crf >= 0 else _CRF_MAP.get(quality_preset, 23)
    effective_preset = encoding_preset if encoding_preset != "auto" else _PRESET_MAP.get(quality_preset, "medium")

    _ffmpeg = _get_ffmpeg_bin()
    ffmpeg_cmd = [_ffmpeg, "-y", "-i", effective_video_path]

    if sub_filter:
        ffmpeg_cmd.extend(["-vf", sub_filter])

    ffmpeg_cmd.extend([
        "-c:v", "libx264",
        "-crf", str(effective_crf),
        "-preset", effective_preset,
        "-pix_fmt", "yuv420p",
        "-c:a", "copy",
    ])

    if preview_mode:
        # Insert scale + duration limit
        if sub_filter:
            # Append scale to existing vf
            vf_idx = ffmpeg_cmd.index("-vf")
            ffmpeg_cmd[vf_idx + 1] += ",scale=480:trunc(ow/a/2)*2"
        else:
            ffmpeg_cmd.extend(["-vf", "scale=480:trunc(ow/a/2)*2"])
        ffmpeg_cmd.extend(["-t", "10"])

    ffmpeg_cmd.append(output_path)

    logger.debug("Whisper-only command: %s", " ".join(ffmpeg_cmd))
    proc = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"Whisper-only mode: ffmpeg failed:\n{proc.stderr[-500:]}"
        )

    # --- Collect frame/audio output ---
    unique_id = str(kwargs.get("unique_id", ""))
    hidden_prompt = kwargs.get("hidden_prompt") or {}
    images_tensor, audio_out = collect_frame_output(
        media_converter=media_converter,
        output_path=output_path,
        unique_id=unique_id,
        hidden_prompt=hidden_prompt,
        removes_audio=False,
    )

    # --- Build analysis string (includes full transcription) ---
    cmd_log = " ".join(ffmpeg_cmd)
    mode_label = "Karaoke Subtitles" if mode == "karaoke_subtitles" else "SRT Subtitles"
    analysis = (
        f"Whisper-Only Mode (no LLM)\n"
        f"Mode: {mode_label}\n"
        f"Model: {whisper_model}\n"
        f"Device: {whisper_device}\n"
        f"Language: {result.language or 'auto-detected'}\n"
        f"Segments: {len(result.segments)}\n"
        f"Words: {len(result.words)}\n\n"
        f"--- Transcription ---\n"
        f"{result.full_text or '(no speech detected)'}"
    )

    # --- Cleanup temp files ---
    for tmp_path in [temp_video_from_images, temp_video_with_audio, sub_tmp_path]:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
    if not save_output and temp_render_dir and os.path.isdir(temp_render_dir):
        if not os.listdir(temp_render_dir):
            shutil.rmtree(temp_render_dir, ignore_errors=True)

    return (images_tensor, audio_out, output_path, cmd_log, analysis, "")


async def process_mmaudio_only(
    # dependencies
    media_converter,
    # parameters
    prompt: str,
    audio_output_mode: str,
    effective_video_path: str,
    video_metadata,
    save_output: bool,
    output_path: str,
    preview_mode: bool,
    quality_preset: str,
    crf: int,
    encoding_preset: str,
    temp_video_from_images: Optional[str] = None,
    temp_video_with_audio: Optional[str] = None,
    **kwargs,
) -> tuple[torch.Tensor, dict, str, str, str, str]:
    """Run MMAudio audio generation directly without any LLM involvement.

    Generates audio from the video (and optional text prompt) using MMAudio,
    then muxes the result into the output video.

    Args:
        prompt: Text description to guide audio generation (can be empty
                for pure video-to-audio).
        audio_output_mode: "auto"/"replace" to discard original audio,
                           "mix" to blend, "save_only" to skip muxing.

    Returns the standard 6-tuple:
        (images_tensor, audio, output_path, command_log, analysis, mask_overlay_path)
    """
    # Treat "auto" as "replace" in no-LLM context
    if audio_output_mode == "auto":
        audio_output_mode = "replace"
    logger.info(
        "MMAudio-only mode: prompt=%r, mode=%s", prompt, audio_output_mode,
    )

    # --- Import MMAudio ---
    try:
        try:
            from ..core.mmaudio_synthesizer import generate_audio
        except ImportError:
            from core.mmaudio_synthesizer import generate_audio  # type: ignore
    except ImportError:
        raise RuntimeError(
            "MMAudio is not installed. Install with: "
            "pip install --no-deps git+https://github.com/hkchengrex/MMAudio.git && "
            "pip install torchdiffeq"
        )

    # --- Build output path ---
    output_path, temp_render_dir = build_output_path(
        effective_video_path=effective_video_path,
        save_output=save_output,
        output_path=output_path,
        preview_mode=preview_mode,
    )

    # --- Generate audio via MMAudio (in-process with offloading) ---
    audio_file = None  # ensure defined for finally block
    try:
        audio_file = generate_audio(
            video_path=effective_video_path,
            prompt=prompt,
        )
    except Exception as e:
        logger.error("MMAudio-only: audio generation failed: %s", e)
        # Free VRAM from loaded MMAudio models on failure
        try:
            try:
                from ..core.mmaudio_synthesizer import cleanup as _mm_cleanup
            except ImportError:
                from core.mmaudio_synthesizer import cleanup as _mm_cleanup  # type: ignore
            _mm_cleanup()
        except Exception:
            pass
        raise RuntimeError(f"MMAudio audio generation failed: {e}") from e

    # --- Detect if source video has audio ---
    has_audio = False
    if video_metadata.primary_audio:
        has_audio = True

    # --- save_only: skip muxing, just return the audio file path ---
    if audio_output_mode == "save_only":
        output_path, temp_render_dir = build_output_path(
            effective_video_path=effective_video_path,
            save_output=save_output,
            output_path=output_path,
            preview_mode=preview_mode,
        )
        # Copy original video to output (no audio changes)
        _ffmpeg = _get_ffmpeg_bin()
        shutil.copy2(effective_video_path, output_path)
        unique_id = str(kwargs.get("unique_id", ""))
        hidden_prompt = kwargs.get("hidden_prompt") or {}
        images_tensor, audio_out = collect_frame_output(
            media_converter=media_converter,
            output_path=output_path,
            unique_id=unique_id,
            hidden_prompt=hidden_prompt,
            removes_audio=False,
        )
        analysis = (
            f"MMAudio-Only Mode (no LLM) — save_only\n"
            f"Prompt: {prompt or '(video-to-audio, no text prompt)'}\n"
            f"Generated audio saved to: {audio_file}\n"
            f"(Audio was NOT muxed into the video)"
        )
        return (images_tensor, audio_out, output_path, "", analysis, "")

    # --- Build ffmpeg command to mux generated audio ---
    _ffmpeg = _get_ffmpeg_bin()
    effective_crf = crf if crf >= 0 else _CRF_MAP.get(quality_preset, 23)
    effective_preset = encoding_preset if encoding_preset != "auto" else _PRESET_MAP.get(quality_preset, "medium")

    if audio_output_mode == "mix" and has_audio:
        # Mix generated audio with original audio
        logger.info(
            "MMAudio-only: 'mix' mode requires video re-encoding (slower than 'replace')"
        )
        ffmpeg_cmd = [
            _ffmpeg, "-y",
            "-i", effective_video_path,
            "-i", audio_file,
            "-filter_complex",
            "[0:a][1:a]amix=inputs=2:duration=shortest[aout]",
            "-map", "0:v",
            "-map", "[aout]",
            "-c:v", "libx264",
            "-crf", str(effective_crf),
            "-preset", effective_preset,
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "192k",
        ]
    else:
        # Replace mode (or mix with no existing audio) — pass through
        # the video codec since only the audio track is changing.
        ffmpeg_cmd = [
            _ffmpeg, "-y",
            "-i", effective_video_path,
            "-i", audio_file,
            "-map", "0:v",
            "-map", "1:a",
            "-c:v", "copy",
            "-c:a", "aac",
            "-b:a", "192k",
            "-shortest",
        ]

    if preview_mode:
        if audio_output_mode == "mix" and has_audio:
            # Mix mode already re-encodes — just add scale + time limit
            ffmpeg_cmd.extend(["-vf", "scale=480:trunc(ow/a/2)*2", "-t", "10"])
        else:
            # Replace mode uses -c:v copy — rebuild with re-encode for scaling
            ffmpeg_cmd = [
                _ffmpeg, "-y",
                "-i", effective_video_path,
                "-i", audio_file,
                "-map", "0:v",
                "-map", "1:a",
                "-vf", "scale=480:trunc(ow/a/2)*2",
                "-t", "10",
                "-c:v", "libx264",
                "-crf", str(effective_crf),
                "-preset", effective_preset,
                "-pix_fmt", "yuv420p",
                "-c:a", "aac",
                "-b:a", "192k",
                "-shortest",
            ]

    ffmpeg_cmd.append(output_path)

    logger.debug("MMAudio-only ffmpeg command: %s", " ".join(ffmpeg_cmd))
    try:
        proc = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(
                f"MMAudio-only mode: ffmpeg mux failed:\n{proc.stderr[-500:]}"
            )

        # --- Collect frame/audio output ---
        unique_id = str(kwargs.get("unique_id", ""))
        hidden_prompt = kwargs.get("hidden_prompt") or {}
        images_tensor, audio_out = collect_frame_output(
            media_converter=media_converter,
            output_path=output_path,
            unique_id=unique_id,
            hidden_prompt=hidden_prompt,
            removes_audio=False,
        )

        # --- Build analysis string ---
        cmd_log = " ".join(ffmpeg_cmd)
        analysis = (
            f"MMAudio-Only Mode (no LLM)\n"
            f"Prompt: {prompt or '(video-to-audio, no text prompt)'}\n"
            f"Audio mode: {audio_output_mode}\n"
            f"Source had audio: {has_audio}\n\n"
            f"Generated audio: {audio_file}\n"
            f"Output: {output_path}"
        )

        return (images_tensor, audio_out, output_path, cmd_log, analysis, "")
    finally:
        # --- Cleanup temp files (always runs, even on error) ---
        for tmp_path in [temp_video_from_images, temp_video_with_audio]:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
        # Clean up generated audio file
        if audio_file and os.path.exists(audio_file):
            try:
                os.remove(audio_file)
            except OSError:
                pass
        if not save_output and temp_render_dir and os.path.isdir(temp_render_dir):
            if not os.listdir(temp_render_dir):
                shutil.rmtree(temp_render_dir, ignore_errors=True)


async def process_audiox_music_only(
    # dependencies
    media_converter,
    # parameters
    prompt: str,
    audio_output_mode: str,
    effective_video_path: str,
    video_metadata,
    save_output: bool,
    output_path: str,
    preview_mode: bool,
    quality_preset: str,
    crf: int,
    encoding_preset: str,
    temp_video_from_images: Optional[str] = None,
    temp_video_with_audio: Optional[str] = None,
    **kwargs,
) -> tuple[torch.Tensor, dict, str, str, str, str]:
    """Run AudioX music generation directly without any LLM involvement.

    Generates music from the video (and optional text prompt) using AudioX,
    then muxes the result into the output video.

    Args:
        prompt: Text description to guide music generation.
        audio_output_mode: "auto"/"replace" to discard original audio,
                           "mix" to blend, "save_only" to skip muxing.

    Returns the standard 6-tuple:
        (images_tensor, audio, output_path, command_log, analysis, mask_overlay_path)
    """
    # Treat "auto" as "replace" in no-LLM context
    if audio_output_mode == "auto":
        audio_output_mode = "replace"
    logger.info(
        "AudioX music-only mode: prompt=%r, mode=%s", prompt, audio_output_mode,
    )

    # --- Import AudioX ---
    try:
        try:
            from ..core.audiox_synthesizer import generate_music
        except ImportError:
            from core.audiox_synthesizer import generate_music  # type: ignore
    except ImportError:
        raise RuntimeError(
            "AudioX is not installed. Install with: "
            "pip install --no-deps stable-audio-tools && "
            "pip install alias-free-torch x-transformers einops-exts k-diffusion"
        )

    # --- Build output path ---
    output_path, temp_render_dir = build_output_path(
        effective_video_path=effective_video_path,
        save_output=save_output,
        output_path=output_path,
        preview_mode=preview_mode,
    )

    # --- Generate music via AudioX (in-process with offloading) ---
    audio_file = None
    try:
        audio_file = generate_music(
            video_path=effective_video_path,
            prompt=prompt,
        )
    except Exception as e:
        logger.error("AudioX music-only: generation failed: %s", e)
        try:
            try:
                from ..core.audiox_synthesizer import cleanup as _ax_cleanup
            except ImportError:
                from core.audiox_synthesizer import cleanup as _ax_cleanup  # type: ignore
            _ax_cleanup()
        except Exception:
            pass
        raise RuntimeError(f"AudioX music generation failed: {e}") from e

    # --- Detect if source video has audio ---
    has_audio = False
    if video_metadata.primary_audio:
        has_audio = True

    # --- save_only: skip muxing, just return the audio file path ---
    if audio_output_mode == "save_only":
        shutil.copy2(effective_video_path, output_path)
        unique_id = str(kwargs.get("unique_id", ""))
        hidden_prompt = kwargs.get("hidden_prompt") or {}
        images_tensor, audio_out = collect_frame_output(
            media_converter=media_converter,
            output_path=output_path,
            unique_id=unique_id,
            hidden_prompt=hidden_prompt,
            removes_audio=False,
        )
        analysis = (
            f"AudioX Music-Only Mode (no LLM) — save_only\n"
            f"Prompt: {prompt or '(video-to-music, no text prompt)'}\n"
            f"Generated music saved to: {audio_file}\n"
            f"(Audio was NOT muxed into the video)"
        )
        return (images_tensor, audio_out, output_path, "", analysis, "")

    # --- Build ffmpeg command to mux generated audio ---
    _ffmpeg = _get_ffmpeg_bin()
    effective_crf = crf if crf >= 0 else _CRF_MAP.get(quality_preset, 23)
    effective_preset = encoding_preset if encoding_preset != "auto" else _PRESET_MAP.get(quality_preset, "medium")

    if audio_output_mode == "mix" and has_audio:
        ffmpeg_cmd = [
            _ffmpeg, "-y",
            "-i", effective_video_path,
            "-i", audio_file,
            "-filter_complex",
            "[0:a][1:a]amix=inputs=2:duration=shortest[aout]",
            "-map", "0:v",
            "-map", "[aout]",
            "-c:v", "libx264",
            "-crf", str(effective_crf),
            "-preset", effective_preset,
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "192k",
        ]
    else:
        ffmpeg_cmd = [
            _ffmpeg, "-y",
            "-i", effective_video_path,
            "-i", audio_file,
            "-map", "0:v",
            "-map", "1:a",
            "-c:v", "copy",
            "-c:a", "aac",
            "-b:a", "192k",
            "-shortest",
        ]

    if preview_mode:
        if audio_output_mode == "mix" and has_audio:
            ffmpeg_cmd.extend(["-vf", "scale=480:trunc(ow/a/2)*2", "-t", "10"])
        else:
            ffmpeg_cmd = [
                _ffmpeg, "-y",
                "-i", effective_video_path,
                "-i", audio_file,
                "-map", "0:v",
                "-map", "1:a",
                "-vf", "scale=480:trunc(ow/a/2)*2",
                "-t", "10",
                "-c:v", "libx264",
                "-crf", str(effective_crf),
                "-preset", effective_preset,
                "-pix_fmt", "yuv420p",
                "-c:a", "aac",
                "-b:a", "192k",
                "-shortest",
            ]

    ffmpeg_cmd.append(output_path)

    logger.debug("AudioX music-only ffmpeg command: %s", " ".join(ffmpeg_cmd))
    try:
        proc = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(
                f"AudioX music-only mode: ffmpeg mux failed:\n{proc.stderr[-500:]}"
            )

        unique_id = str(kwargs.get("unique_id", ""))
        hidden_prompt = kwargs.get("hidden_prompt") or {}
        images_tensor, audio_out = collect_frame_output(
            media_converter=media_converter,
            output_path=output_path,
            unique_id=unique_id,
            hidden_prompt=hidden_prompt,
            removes_audio=False,
        )

        cmd_log = " ".join(ffmpeg_cmd)
        analysis = (
            f"AudioX Music-Only Mode (no LLM)\n"
            f"Prompt: {prompt or '(video-to-music, no text prompt)'}\n"
            f"Audio mode: {audio_output_mode}\n"
            f"Source had audio: {has_audio}\n\n"
            f"Generated music: {audio_file}\n"
            f"Output: {output_path}"
        )

        return (images_tensor, audio_out, output_path, cmd_log, analysis, "")
    finally:
        for tmp_path in [temp_video_from_images, temp_video_with_audio]:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
        if audio_file and os.path.exists(audio_file):
            try:
                os.remove(audio_file)
            except OSError:
                pass
        if not save_output and temp_render_dir and os.path.isdir(temp_render_dir):
            if not os.listdir(temp_render_dir):
                shutil.rmtree(temp_render_dir, ignore_errors=True)

async def process_foundation1_only(
    # dependencies
    media_converter,
    # parameters
    prompt: str,
    audio_output_mode: str,
    effective_video_path: str,
    video_metadata,
    save_output: bool,
    output_path: str,
    preview_mode: bool,
    quality_preset: str,
    crf: int,
    encoding_preset: str,
    temp_video_from_images: Optional[str] = None,
    temp_video_with_audio: Optional[str] = None,
    **kwargs,
) -> tuple[torch.Tensor, dict, str, str, str, str]:
    """Run Foundation-1 sample generation directly without any LLM involvement.

    Generates a music sample/loop from a text prompt using Foundation-1,
    then muxes the result into the output video.

    Args:
        prompt: Text description to guide sample generation (or preset name).
        audio_output_mode: "auto"/"replace" to discard original audio,
                           "mix" to blend, "save_only" to skip muxing.

    Returns the standard 6-tuple:
        (images_tensor, audio, output_path, command_log, analysis, mask_overlay_path)
    """
    # Treat "auto" as "replace" in no-LLM context
    if audio_output_mode == "auto":
        audio_output_mode = "replace"
    logger.info(
        "Foundation-1 sample-only mode: prompt=%r, mode=%s", prompt, audio_output_mode,
    )

    # --- Import Foundation-1 ---
    try:
        try:
            from ..core.foundation1_synthesizer import generate_sample
        except ImportError:
            from core.foundation1_synthesizer import generate_sample  # type: ignore
    except ImportError:
        raise RuntimeError(
            "Foundation-1 is not available. Install with: "
            "pip install --no-deps stable-audio-tools"
        )

    # --- Build output path ---
    output_path, temp_render_dir = build_output_path(
        effective_video_path=effective_video_path,
        save_output=save_output,
        output_path=output_path,
        preview_mode=preview_mode,
    )

    # --- Extract Foundation-1 widget params ---
    f1_preset = kwargs.pop("f1_preset", "none")
    f1_instrument = kwargs.pop("f1_instrument", "none")
    f1_fx = kwargs.pop("f1_fx", "none")
    f1_structure = kwargs.pop("f1_structure", "none")
    f1_negative_prompt = kwargs.pop("f1_negative_prompt", "")
    f1_bpm_str = kwargs.pop("f1_bpm", "auto")
    f1_bars_str = kwargs.pop("f1_bars", "auto")
    f1_key = kwargs.pop("f1_key", "")
    f1_duration = kwargs.pop("f1_duration", 0.0)
    f1_steps = kwargs.pop("f1_steps", 100)
    f1_cfg_scale = kwargs.pop("f1_cfg_scale", 7.0)
    f1_style_transfer = kwargs.pop("f1_style_transfer", False)
    f1_noise_level = kwargs.pop("f1_noise_level", 0.7)
    audio_a = kwargs.pop("audio_a", None)

    # Convert string dropdowns to ints
    f1_bpm = int(f1_bpm_str) if f1_bpm_str != "auto" else 0
    f1_bars = int(f1_bars_str) if f1_bars_str != "auto" else 0

    # Build enhanced prompt from instrument/FX/structure dropdowns
    prompt_parts = []
    if f1_instrument and f1_instrument != "none":
        # Capitalize for Foundation-1's tag format
        prompt_parts.append(f1_instrument.replace("_", " ").title())
    if f1_fx and f1_fx != "none":
        # Convert underscored names to Foundation-1 tag format
        prompt_parts.append(f1_fx.replace("_", " ").title())
    if f1_structure and f1_structure != "none":
        prompt_parts.append(f1_structure.replace("_", " ").title())
    if prompt_parts:
        # Prepend instrument/FX/structure tags to user prompt
        tags = ", ".join(prompt_parts)
        prompt = f"{tags}, {prompt}" if prompt.strip() else tags

    logger.info(
        "Foundation-1 params: preset=%s, instrument=%s, fx=%s, structure=%s, "
        "bpm=%s, bars=%s, key=%r, duration=%.1f, steps=%d, cfg=%.1f, "
        "style_transfer=%s, noise_level=%.2f",
        f1_preset, f1_instrument, f1_fx, f1_structure,
        f1_bpm, f1_bars, f1_key, f1_duration, f1_steps, f1_cfg_scale,
        f1_style_transfer, f1_noise_level,
    )

    # --- Generate audio via Foundation-1 ---
    audio_file = None
    try:
        if f1_style_transfer and audio_a is not None:
            # Style transfer mode: restyle connected audio_a
            try:
                try:
                    from ..core.foundation1_synthesizer import style_transfer_audio
                except ImportError:
                    from core.foundation1_synthesizer import style_transfer_audio  # type: ignore
            except ImportError:
                raise RuntimeError(
                    "Foundation-1 style_transfer_audio not available. "
                    "Ensure foundation1_synthesizer.py is up-to-date."
                )

            # Extract audio_a waveform to a temp wav file for the synthesizer
            import tempfile as _tf
            import numpy as _np
            from scipy.io import wavfile as _wavfile

            waveform = audio_a.get("waveform")  # shape: [batch, channels, samples]
            sr = audio_a.get("sample_rate", 44100)
            if waveform is None:
                raise RuntimeError("audio_a has no waveform — connect an audio source")

            # Write to temp file
            tmp_audio = _tf.NamedTemporaryFile(suffix=".wav", delete=False)
            tmp_audio.close()
            audio_np = waveform.squeeze(0).cpu().numpy()  # [channels, samples]
            if audio_np.ndim == 2:
                audio_np = audio_np.T  # → [samples, channels]
            audio_np = _np.clip(audio_np, -1.0, 1.0).astype(_np.float32)
            _wavfile.write(tmp_audio.name, int(sr), audio_np)

            audio_file = style_transfer_audio(
                input_audio_path=tmp_audio.name,
                prompt=prompt,
                negative_prompt=f1_negative_prompt,
                preset=f1_preset if f1_preset != "none" else "",
                bpm=f1_bpm,
                bars=f1_bars,
                key=f1_key,
                init_noise_level=f1_noise_level,
                steps=f1_steps,
                cfg_scale=f1_cfg_scale,
            )

            # Clean up temp input
            try:
                os.remove(tmp_audio.name)
            except OSError:
                pass
        else:
            # Standard generation mode
            audio_file = generate_sample(
                prompt=prompt,
                negative_prompt=f1_negative_prompt,
                preset=f1_preset if f1_preset != "none" else "",
                bpm=f1_bpm,
                bars=f1_bars,
                key=f1_key,
                duration=f1_duration if f1_duration > 0 else None,
                steps=f1_steps,
                cfg_scale=f1_cfg_scale,
            )
    except Exception as e:
        logger.error("Foundation-1 sample-only: generation failed: %s", e)
        try:
            try:
                from ..core.foundation1_synthesizer import cleanup as _f1_cleanup
            except ImportError:
                from core.foundation1_synthesizer import cleanup as _f1_cleanup  # type: ignore
            _f1_cleanup()
        except Exception:
            pass
        raise RuntimeError(f"Foundation-1 sample generation failed: {e}") from e

    # --- Detect if source video has audio ---
    has_audio = False
    has_real_video = bool(effective_video_path and effective_video_path.strip()
                         and os.path.isfile(effective_video_path))
    if has_real_video and video_metadata and video_metadata.primary_audio:
        has_audio = True

    # --- Audio-only output (no video connected) or save_only ---
    if audio_output_mode == "save_only" or not has_real_video:
        # Just output the generated audio file directly
        shutil.copy2(audio_file, output_path)
        unique_id = str(kwargs.get("unique_id", ""))
        hidden_prompt = kwargs.get("hidden_prompt") or {}
        images_tensor, audio_out = collect_frame_output(
            media_converter=media_converter,
            output_path=output_path,
            unique_id=unique_id,
            hidden_prompt=hidden_prompt,
            removes_audio=False,
        )
        mode_label = "save_only" if audio_output_mode == "save_only" else "audio-only"
        analysis = (
            f"Foundation-1 Sample-Only Mode (no LLM) — {mode_label}\n"
            f"Prompt: {prompt or '(no text prompt)'}\n"
            f"Generated sample: {audio_file}\n"
            f"Output: {output_path}"
        )
        return (images_tensor, audio_out, output_path, "", analysis, "")

    # --- Build ffmpeg command to mux generated audio into real video ---
    _ffmpeg = _get_ffmpeg_bin()
    effective_crf = crf if crf >= 0 else _CRF_MAP.get(quality_preset, 23)
    effective_preset = encoding_preset if encoding_preset != "auto" else _PRESET_MAP.get(quality_preset, "medium")

    if audio_output_mode == "mix" and has_audio:
        ffmpeg_cmd = [
            _ffmpeg, "-y",
            "-i", effective_video_path,
            "-i", audio_file,
            "-filter_complex",
            "[0:a][1:a]amix=inputs=2:duration=shortest[aout]",
            "-map", "0:v",
            "-map", "[aout]",
            "-c:v", "libx264",
            "-crf", str(effective_crf),
            "-preset", effective_preset,
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "192k",
        ]
    else:
        ffmpeg_cmd = [
            _ffmpeg, "-y",
            "-i", effective_video_path,
            "-i", audio_file,
            "-map", "0:v",
            "-map", "1:a",
            "-c:v", "copy",
            "-c:a", "aac",
            "-b:a", "192k",
        ]

    if preview_mode:
        if audio_output_mode == "mix" and has_audio:
            ffmpeg_cmd.extend(["-vf", "scale=480:trunc(ow/a/2)*2", "-t", "10"])
        else:
            ffmpeg_cmd = [
                _ffmpeg, "-y",
                "-i", effective_video_path,
                "-i", audio_file,
                "-map", "0:v",
                "-map", "1:a",
                "-vf", "scale=480:trunc(ow/a/2)*2",
                "-t", "10",
                "-c:v", "libx264",
                "-crf", str(effective_crf),
                "-preset", effective_preset,
                "-pix_fmt", "yuv420p",
                "-c:a", "aac",
                "-b:a", "192k",
                "-shortest",
            ]

    ffmpeg_cmd.append(output_path)

    logger.debug("Foundation-1 sample-only ffmpeg command: %s", " ".join(ffmpeg_cmd))
    try:
        proc = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(
                f"Foundation-1 sample-only mode: ffmpeg mux failed:\n{proc.stderr[-500:]}"
            )

        unique_id = str(kwargs.get("unique_id", ""))
        hidden_prompt = kwargs.get("hidden_prompt") or {}
        images_tensor, audio_out = collect_frame_output(
            media_converter=media_converter,
            output_path=output_path,
            unique_id=unique_id,
            hidden_prompt=hidden_prompt,
            removes_audio=False,
        )

        cmd_log = " ".join(ffmpeg_cmd)
        analysis = (
            f"Foundation-1 Sample-Only Mode (no LLM)\n"
            f"Prompt: {prompt or '(no text prompt)'}\n"
            f"Audio mode: {audio_output_mode}\n"
            f"Source had audio: {has_audio}\n\n"
            f"Generated sample: {audio_file}\n"
            f"Output: {output_path}"
        )

        return (images_tensor, audio_out, output_path, cmd_log, analysis, "")
    finally:
        for tmp_path in [temp_video_from_images, temp_video_with_audio]:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
        if audio_file and os.path.exists(audio_file):
            try:
                os.remove(audio_file)
            except OSError:
                pass
        if not save_output and temp_render_dir and os.path.isdir(temp_render_dir):
            if not os.listdir(temp_render_dir):
                shutil.rmtree(temp_render_dir, ignore_errors=True)


async def process_fish_speech_only(
    # dependencies
    media_converter,
    # parameters
    prompt: str,
    audio_output_mode: str,
    effective_video_path: str,
    video_metadata,
    save_output: bool,
    output_path: str,
    preview_mode: bool,
    quality_preset: str,
    crf: int,
    encoding_preset: str,
    temp_video_from_images: Optional[str] = None,
    temp_video_with_audio: Optional[str] = None,
    **kwargs,
) -> tuple[torch.Tensor, dict, str, str, str, str]:
    """Run Fish Speech TTS directly without any LLM involvement.

    Generates speech audio from text using Fish Speech S2 Pro,
    then muxes the result into the output video.

    Args:
        prompt: Text to synthesize. Supports inline tags like ``[whisper]``,
                ``[excited]``, ``<|speaker:0|>``, etc.
        audio_output_mode: "auto"/"replace" to discard original audio,
                           "mix" to blend, "save_only" to skip muxing.

    Returns the standard 6-tuple:
        (images_tensor, audio, output_path, command_log, analysis, mask_overlay_path)
    """
    # Treat "auto" as "replace" in no-LLM context
    if audio_output_mode == "auto":
        audio_output_mode = "replace"
    logger.info(
        "Fish Speech TTS mode: prompt=%r, mode=%s", prompt[:80], audio_output_mode,
    )

    # --- Import Fish Speech synthesizer ---
    try:
        try:
            from ..core.fish_speech_synthesizer import generate_speech
        except ImportError:
            from core.fish_speech_synthesizer import generate_speech  # type: ignore
    except ImportError:
        raise RuntimeError(
            "Fish Speech is not available. Install with: "
            "pip install --no-deps fish-speech"
        )

    # --- Build output path ---
    output_path, temp_render_dir = build_output_path(
        effective_video_path=effective_video_path,
        save_output=save_output,
        output_path=output_path,
        preview_mode=preview_mode,
    )

    # --- Extract Fish Speech widget params ---
    fish_model_variant = kwargs.pop("fish_model_variant", "bf16")
    fish_voice = kwargs.pop("fish_voice", "")
    fish_emotion = kwargs.pop("fish_emotion", "(none)")
    fish_temperature = kwargs.pop("fish_temperature", 0.7)
    fish_top_p = kwargs.pop("fish_top_p", 0.7)
    fish_repetition_penalty = kwargs.pop("fish_repetition_penalty", 1.2)

    # Normalize emotion tag
    emotion_tag = ""
    if fish_emotion and fish_emotion != "(none)":
        emotion_tag = fish_emotion

    # Resolve voice references — priority: audio inputs > fish_voice library
    # Supports multi-speaker: audio_a → speaker:0, audio_b → speaker:1
    reference_audio = None
    reference_audios = None
    voice_name = None

    # 1. Check for connected audio inputs (direct reference audio)
    from .output_handler import audio_dict_to_wav
    audio_a = kwargs.pop("audio_a", None)
    audio_b = kwargs.pop("audio_b", None)

    ref_paths = []  # list of (wav_path, label) tuples
    for label, audio_dict in [("speaker_0", audio_a), ("speaker_1", audio_b)]:
        if audio_dict is not None and isinstance(audio_dict, dict):
            try:
                wav_path = audio_dict_to_wav(audio_dict)
                if wav_path and os.path.isfile(wav_path):
                    ref_paths.append((wav_path, label))
                    logger.info(
                        "Fish Speech: %s reference voice → %s", label, wav_path,
                    )
            except Exception as e:
                logger.warning(
                    "Fish Speech: could not extract %s for voice cloning: %s",
                    label, e,
                )

    if len(ref_paths) >= 2:
        # Multi-speaker mode
        reference_audios = ref_paths
        logger.info("Fish Speech: multi-speaker mode with %d references", len(ref_paths))
    elif len(ref_paths) == 1:
        # Single speaker mode
        reference_audio = ref_paths[0][0]

    # 2. Fallback: voice library name or direct path
    if not reference_audio and not reference_audios and fish_voice and fish_voice.strip():
        voice_str = fish_voice.strip()
        if os.path.isfile(voice_str):
            reference_audio = voice_str
        else:
            voice_name = voice_str

    logger.info(
        "Fish Speech params: variant=%s, voice=%s, emotion=%s, "
        "temperature=%.2f, top_p=%.2f, rep_penalty=%.2f",
        fish_model_variant, fish_voice or "(default)",
        fish_emotion, fish_temperature, fish_top_p, fish_repetition_penalty,
    )

    # --- Generate speech ---
    audio_file = None
    try:
        audio_file = generate_speech(
            text=prompt,
            reference_audio=reference_audio,
            reference_audios=reference_audios,
            voice_name=voice_name,
            emotion_tag=emotion_tag,
            variant=fish_model_variant,
            temperature=fish_temperature,
            top_p=fish_top_p,
            repetition_penalty=fish_repetition_penalty,
        )
    except Exception as e:
        logger.error("Fish Speech TTS: generation failed: %s", e)
        try:
            try:
                from ..core.fish_speech_synthesizer import cleanup as _fs_cleanup
            except ImportError:
                from core.fish_speech_synthesizer import cleanup as _fs_cleanup  # type: ignore
            _fs_cleanup()
        except Exception:
            pass
        raise RuntimeError(f"Fish Speech generation failed: {e}") from e

    # --- Detect if source video has audio ---
    has_audio = False
    has_real_video = bool(effective_video_path and effective_video_path.strip()
                         and os.path.isfile(effective_video_path))
    if has_real_video and video_metadata and video_metadata.primary_audio:
        has_audio = True

    # --- Audio-only output (no video connected) or save_only ---
    if audio_output_mode == "save_only" or not has_real_video:
        # Just output the generated audio file directly
        shutil.copy2(audio_file, output_path)
        unique_id = str(kwargs.get("unique_id", ""))
        hidden_prompt = kwargs.get("hidden_prompt") or {}
        images_tensor, audio_out = collect_frame_output(
            media_converter=media_converter,
            output_path=output_path,
            unique_id=unique_id,
            hidden_prompt=hidden_prompt,
            removes_audio=False,
        )
        mode_label = "save_only" if audio_output_mode == "save_only" else "audio-only"
        analysis = (
            f"Fish Speech TTS Mode (no LLM) — {mode_label}\n"
            f"Text: {prompt[:100] or '(no text)'}{'...' if len(prompt) > 100 else ''}\n"
            f"Voice: {fish_voice or '(default)'}\n"
            f"Emotion: {fish_emotion}\n"
            f"Generated audio: {audio_file}\n"
            f"Output: {output_path}"
        )
        return (images_tensor, audio_out, output_path, "", analysis, "")

    # --- Build ffmpeg command to mux generated audio into real video ---
    _ffmpeg = _get_ffmpeg_bin()
    effective_crf = crf if crf >= 0 else _CRF_MAP.get(quality_preset, 23)
    effective_preset = encoding_preset if encoding_preset != "auto" else _PRESET_MAP.get(quality_preset, "medium")

    if audio_output_mode == "mix" and has_audio:
        ffmpeg_cmd = [
            _ffmpeg, "-y",
            "-i", effective_video_path,
            "-i", audio_file,
            "-filter_complex",
            "[0:a][1:a]amix=inputs=2:duration=shortest[aout]",
            "-map", "0:v",
            "-map", "[aout]",
            "-c:v", "libx264",
            "-crf", str(effective_crf),
            "-preset", effective_preset,
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "192k",
        ]
    else:
        ffmpeg_cmd = [
            _ffmpeg, "-y",
            "-i", effective_video_path,
            "-i", audio_file,
            "-map", "0:v",
            "-map", "1:a",
            "-c:v", "copy",
            "-c:a", "aac",
            "-b:a", "192k",
        ]

    if preview_mode:
        if audio_output_mode == "mix" and has_audio:
            ffmpeg_cmd.extend(["-vf", "scale=480:trunc(ow/a/2)*2", "-t", "10"])
        else:
            ffmpeg_cmd = [
                _ffmpeg, "-y",
                "-i", effective_video_path,
                "-i", audio_file,
                "-map", "0:v",
                "-map", "1:a",
                "-vf", "scale=480:trunc(ow/a/2)*2",
                "-t", "10",
                "-c:v", "libx264",
                "-crf", str(effective_crf),
                "-preset", effective_preset,
                "-pix_fmt", "yuv420p",
                "-c:a", "aac",
                "-b:a", "192k",
                "-shortest",
            ]

    ffmpeg_cmd.append(output_path)

    logger.debug("Fish Speech TTS ffmpeg command: %s", " ".join(ffmpeg_cmd))
    try:
        proc = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(
                f"Fish Speech TTS mode: ffmpeg mux failed:\n{proc.stderr[-500:]}"
            )

        unique_id = str(kwargs.get("unique_id", ""))
        hidden_prompt = kwargs.get("hidden_prompt") or {}
        images_tensor, audio_out = collect_frame_output(
            media_converter=media_converter,
            output_path=output_path,
            unique_id=unique_id,
            hidden_prompt=hidden_prompt,
            removes_audio=False,
        )

        cmd_log = " ".join(ffmpeg_cmd)
        analysis = (
            f"Fish Speech TTS Mode (no LLM)\n"
            f"Text: {prompt[:100] or '(no text)'}{'...' if len(prompt) > 100 else ''}\n"
            f"Voice: {fish_voice or '(default)'}\n"
            f"Emotion: {fish_emotion}\n"
            f"Audio mode: {audio_output_mode}\n"
            f"Source had audio: {has_audio}\n\n"
            f"Generated audio: {audio_file}\n"
            f"Output: {output_path}"
        )

        return (images_tensor, audio_out, output_path, cmd_log, analysis, "")
    finally:
        for tmp_path in [temp_video_from_images, temp_video_with_audio]:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
        if audio_file and os.path.exists(audio_file):
            try:
                os.remove(audio_file)
            except OSError:
                pass
        if not save_output and temp_render_dir and os.path.isdir(temp_render_dir):
            if not os.listdir(temp_render_dir):
                shutil.rmtree(temp_render_dir, ignore_errors=True)


async def process_ace_step_only(
    # dependencies
    media_converter,
    # parameters
    prompt: str,
    audio_output_mode: str,
    effective_video_path: str,
    video_metadata,
    save_output: bool,
    output_path: str,
    preview_mode: bool,
    quality_preset: str,
    crf: int,
    encoding_preset: str,
    temp_video_from_images: Optional[str] = None,
    temp_video_with_audio: Optional[str] = None,
    **kwargs,
) -> tuple[torch.Tensor, dict, str, str, str, str]:
    """Run ACE-Step music generation directly without any LLM involvement.

    Generates high-quality music from a text prompt (and optional lyrics) using
    ACE-Step 1.5, then muxes the result into the output video. If the source
    video has existing audio and the prompt is empty, ACE-Step will attempt
    to cover/repaint the existing audio for higher quality.

    Args:
        prompt: Text description to guide music generation.
        audio_output_mode: "auto"/"replace" to discard original audio,
                           "mix" to blend, "save_only" to skip muxing.

    Returns the standard 6-tuple:
        (images_tensor, audio, output_path, command_log, analysis, mask_overlay_path)
    """
    # Treat "auto" as "replace" in no-LLM context
    if audio_output_mode == "auto":
        audio_output_mode = "replace"
    logger.info(
        "ACE-Step music-only mode: prompt=%r, mode=%s", prompt, audio_output_mode,
    )

    # --- Import ACE-Step ---
    try:
        try:
            from ..core.acestep_synthesizer import (
                generate_music_acestep,
                cover_audio,
                generate_lyrics as _ace_generate_lyrics,
                cleanup as _ace_cleanup,
            )
        except ImportError:
            from core.acestep_synthesizer import (  # type: ignore
                generate_music_acestep,
                cover_audio,
                generate_lyrics as _ace_generate_lyrics,
                cleanup as _ace_cleanup,
            )
    except ImportError:
        raise RuntimeError(
            "ACE-Step is not installed. Install with: "
            "pip install --no-deps git+https://github.com/ace-step/ACE-Step-1.5.git"
        )

    # --- Build output path ---
    output_path, temp_render_dir = build_output_path(
        effective_video_path=effective_video_path,
        save_output=save_output,
        output_path=output_path,
        preview_mode=preview_mode,
    )

    # --- Resolve lyrics: text_a = manual lyrics, auto-generate if empty ---
    text_a = kwargs.get("text_a", "") or ""
    lyrics = text_a.strip()

    # --- Extract ACE-Step advanced params ---
    ace_cover_strength = float(kwargs.get("ace_cover_strength", 0.5))
    ace_steps = int(kwargs.get("ace_steps", 8))
    ace_cfg_scale = float(kwargs.get("ace_cfg_scale", 7.0))
    ace_bpm = (kwargs.get("ace_bpm", "") or "").strip()
    ace_key = (kwargs.get("ace_key", "") or "").strip()
    ace_time_sig = (kwargs.get("ace_time_sig", "") or "").strip()

    # --- Resolve reference audio from audio_a ---
    reference_audio_path = None
    audio_a = kwargs.get("audio_a")
    if audio_a and isinstance(audio_a, dict):
        try:
            import torchaudio
            import tempfile as _tf
            waveform = audio_a.get("waveform")
            sample_rate = audio_a.get("sample_rate", 48000)
            if waveform is not None:
                fd, ref_wav = _tf.mkstemp(suffix=".wav", prefix="ace_ref_")
                os.close(fd)
                if waveform.dim() == 3:
                    waveform = waveform.squeeze(0)  # (batch, channels, samples) → (channels, samples)
                torchaudio.save(ref_wav, waveform.cpu(), sample_rate)
                reference_audio_path = ref_wav
                logger.info("ACE-Step: Using audio_a as reference audio")
        except Exception as e:
            logger.warning("ACE-Step: Could not extract reference audio from audio_a: %s", e)

    # --- Build user metadata for LM (BPM/Key/TimeSig) ---
    user_metadata = {}
    if ace_bpm:
        user_metadata["bpm"] = ace_bpm
    if ace_key:
        user_metadata["keyscale"] = ace_key
    if ace_time_sig:
        user_metadata["timesignature"] = ace_time_sig

    # --- Determine mode: repaint existing audio or generate fresh ---
    has_audio = bool(video_metadata.primary_audio)
    audio_file = None
    duration = float(video_metadata.duration) if video_metadata.duration else 60.0

    try:
        if has_audio and not prompt.strip():
            # Repaint existing audio: extract → cover with ACE-Step
            logger.info("ACE-Step: No prompt + video has audio → repaint mode (strength=%.2f)", ace_cover_strength)
            import tempfile as _tf
            fd, src_wav = _tf.mkstemp(suffix=".wav", prefix="ace_src_")
            os.close(fd)
            _ffmpeg = _get_ffmpeg_bin()
            subprocess.run(
                [_ffmpeg, "-y", "-i", effective_video_path,
                 "-vn", "-acodec", "pcm_s16le", "-ar", "48000", "-ac", "2",
                 src_wav],
                capture_output=True, timeout=60,
            )
            if os.path.isfile(src_wav) and os.path.getsize(src_wav) > 100:
                audio_file = cover_audio(
                    audio_path=src_wav,
                    prompt="high quality music",
                    lyrics=lyrics,
                    cover_strength=ace_cover_strength,
                )
            try:
                os.unlink(src_wav)
            except OSError:
                pass
            if not audio_file:
                raise RuntimeError("ACE-Step repaint failed — no output generated")
        else:
            # Auto-generate lyrics if none provided and we have a prompt
            if not lyrics and prompt.strip():
                logger.info("ACE-Step: No manual lyrics — auto-generating from prompt")
                lyrics = _ace_generate_lyrics(
                    prompt=prompt,
                    duration=duration,
                    user_metadata=user_metadata if user_metadata else None,
                )
                if lyrics:
                    logger.info("ACE-Step: Auto-generated lyrics: %r", lyrics[:120])
                else:
                    logger.info("ACE-Step: No lyrics generated — proceeding instrumental")

            # Generate fresh music from prompt
            audio_file = generate_music_acestep(
                prompt=prompt or "background music",
                lyrics=lyrics,
                duration=duration,
                steps=ace_steps,
                cfg_scale=ace_cfg_scale,
                reference_audio=reference_audio_path,
            )
    except Exception as e:
        logger.error("ACE-Step music-only: generation failed: %s", e)
        try:
            _ace_cleanup()
        except Exception:
            pass
        raise RuntimeError(f"ACE-Step music generation failed: {e}") from e

    # --- save_only: skip muxing, just return the audio file path ---
    if audio_output_mode == "save_only":
        shutil.copy2(effective_video_path, output_path)
        unique_id = str(kwargs.get("unique_id", ""))
        hidden_prompt = kwargs.get("hidden_prompt") or {}
        images_tensor, audio_out = collect_frame_output(
            media_converter=media_converter,
            output_path=output_path,
            unique_id=unique_id,
            hidden_prompt=hidden_prompt,
            removes_audio=False,
        )
        lyrics_section = ""
        if lyrics:
            lyrics_source = "manual (text_a)" if text_a.strip() else "auto-generated"
            lyrics_section = f"\nLyrics ({lyrics_source}):\n{lyrics}\n"
        analysis = (
            f"ACE-Step Music-Only Mode (no LLM) — save_only\n"
            f"Prompt: {prompt or '(repaint mode — improving existing audio)'}\n"
            f"{lyrics_section}\n"
            f"Generated music saved to: {audio_file}\n"
            f"(Audio was NOT muxed into the video)"
        )
        return (images_tensor, audio_out, output_path, "", analysis, "")

    # --- Build ffmpeg command to mux generated audio ---
    _ffmpeg = _get_ffmpeg_bin()
    effective_crf = crf if crf >= 0 else _CRF_MAP.get(quality_preset, 23)
    effective_preset = encoding_preset if encoding_preset != "auto" else _PRESET_MAP.get(quality_preset, "medium")

    if audio_output_mode == "mix" and has_audio:
        ffmpeg_cmd = [
            _ffmpeg, "-y",
            "-i", effective_video_path,
            "-i", audio_file,
            "-filter_complex",
            "[0:a][1:a]amix=inputs=2:duration=shortest[aout]",
            "-map", "0:v",
            "-map", "[aout]",
            "-c:v", "libx264",
            "-crf", str(effective_crf),
            "-preset", effective_preset,
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "192k",
        ]
    else:
        ffmpeg_cmd = [
            _ffmpeg, "-y",
            "-i", effective_video_path,
            "-i", audio_file,
            "-map", "0:v",
            "-map", "1:a",
            "-c:v", "copy",
            "-c:a", "aac",
            "-b:a", "192k",
            "-shortest",
        ]

    if preview_mode:
        if audio_output_mode == "mix" and has_audio:
            ffmpeg_cmd.extend(["-vf", "scale=480:trunc(ow/a/2)*2", "-t", "10"])
        else:
            ffmpeg_cmd = [
                _ffmpeg, "-y",
                "-i", effective_video_path,
                "-i", audio_file,
                "-map", "0:v",
                "-map", "1:a",
                "-vf", "scale=480:trunc(ow/a/2)*2",
                "-t", "10",
                "-c:v", "libx264",
                "-crf", str(effective_crf),
                "-preset", effective_preset,
                "-pix_fmt", "yuv420p",
                "-c:a", "aac",
                "-b:a", "192k",
                "-shortest",
            ]

    ffmpeg_cmd.append(output_path)

    logger.debug("ACE-Step music-only ffmpeg command: %s", " ".join(ffmpeg_cmd))
    try:
        proc = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(
                f"ACE-Step music-only mode: ffmpeg mux failed:\n{proc.stderr[-500:]}"
            )

        unique_id = str(kwargs.get("unique_id", ""))
        hidden_prompt = kwargs.get("hidden_prompt") or {}
        images_tensor, audio_out = collect_frame_output(
            media_converter=media_converter,
            output_path=output_path,
            unique_id=unique_id,
            hidden_prompt=hidden_prompt,
            removes_audio=False,
        )

        cmd_log = " ".join(ffmpeg_cmd)
        lyrics_section = ""
        if lyrics:
            lyrics_source = "manual (text_a)" if text_a.strip() else "auto-generated"
            lyrics_section = f"\nLyrics ({lyrics_source}):\n{lyrics}\n"
        analysis = (
            f"ACE-Step Music-Only Mode (no LLM)\n"
            f"Prompt: {prompt or '(repaint mode — improving existing audio)'}\n"
            f"Audio mode: {audio_output_mode}\n"
            f"Source had audio: {has_audio}\n"
            f"{lyrics_section}\n"
            f"Generated music: {audio_file}\n"
            f"Output: {output_path}"
        )

        return (images_tensor, audio_out, output_path, cmd_log, analysis, "")
    finally:
        for tmp_path in [temp_video_from_images, temp_video_with_audio]:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
        if audio_file and os.path.exists(audio_file):
            try:
                os.remove(audio_file)
            except OSError:
                pass
        if not save_output and temp_render_dir and os.path.isdir(temp_render_dir):
            if not os.listdir(temp_render_dir):
                shutil.rmtree(temp_render_dir, ignore_errors=True)


async def process_audiox_inpaint_only(
    # dependencies
    media_converter,
    # parameters
    prompt: str,
    audio_output_mode: str,
    effective_video_path: str,
    video_metadata,
    save_output: bool,
    output_path: str,
    preview_mode: bool,
    quality_preset: str,
    crf: int,
    encoding_preset: str,
    temp_video_from_images: Optional[str] = None,
    temp_video_with_audio: Optional[str] = None,
    **kwargs,
) -> tuple[torch.Tensor, dict, str, str, str, str]:
    """Run AudioX audio inpainting directly without any LLM involvement.

    Extracts audio from the video, inpaints the second half (for completion),
    then muxes the result back.

    Args:
        prompt: Text description to guide inpainted audio.
        audio_output_mode: "auto"/"replace" to discard original audio,
                           "mix" to blend, "save_only" to skip muxing.

    Returns the standard 6-tuple:
        (images_tensor, audio, output_path, command_log, analysis, mask_overlay_path)
    """
    # Treat "auto" as "replace" in no-LLM context
    if audio_output_mode == "auto":
        audio_output_mode = "replace"
    logger.info("AudioX inpaint-only mode: prompt=%r, mode=%s", prompt, audio_output_mode)

    # --- Import AudioX ---
    try:
        try:
            from ..core.audiox_synthesizer import inpaint_audio
        except ImportError:
            from core.audiox_synthesizer import inpaint_audio  # type: ignore
    except ImportError:
        raise RuntimeError(
            "AudioX is not installed. Install with: "
            "pip install --no-deps stable-audio-tools && "
            "pip install alias-free-torch x-transformers einops-exts k-diffusion"
        )

    # --- Extract audio for inpainting ---
    _ffmpeg = _get_ffmpeg_bin()
    tmp_wav = tempfile.NamedTemporaryFile(
        suffix=".wav", delete=False, prefix="ffmpega_ax_"
    )
    tmp_wav_path = tmp_wav.name
    tmp_wav.close()

    extract_result = subprocess.run(
        [_ffmpeg, "-y", "-i", effective_video_path,
         "-vn", "-acodec", "pcm_f32le", "-ar", "44100", "-ac", "2",
         tmp_wav_path],
        capture_output=True, timeout=60,
    )
    if extract_result.returncode != 0:
        raise RuntimeError(
            "AudioX inpaint-only: failed to extract audio from video. "
            "Ensure the input video has an audio track."
        )

    # --- Build output path ---
    output_path, temp_render_dir = build_output_path(
        effective_video_path=effective_video_path,
        save_output=save_output,
        output_path=output_path,
        preview_mode=preview_mode,
    )

    # --- Inpaint audio via AudioX ---
    audio_file = None
    try:
        audio_file = inpaint_audio(
            audio_path=tmp_wav_path,
            prompt=prompt,
            mask_start=50.0,  # Default: inpaint second half (audio completion)
            mask_end=100.0,
        )
    except Exception as e:
        logger.error("AudioX inpaint-only: generation failed: %s", e)
        try:
            try:
                from ..core.audiox_synthesizer import cleanup as _ax_cleanup
            except ImportError:
                from core.audiox_synthesizer import cleanup as _ax_cleanup  # type: ignore
            _ax_cleanup()
        except Exception:
            pass
        raise RuntimeError(f"AudioX audio inpainting failed: {e}") from e

    # --- Detect if source has audio (for mix mode) ---
    has_audio = bool(video_metadata.primary_audio)

    # --- save_only: skip muxing, just return the audio file path ---
    if audio_output_mode == "save_only":
        shutil.copy2(effective_video_path, output_path)
        unique_id = str(kwargs.get("unique_id", ""))
        hidden_prompt = kwargs.get("hidden_prompt") or {}
        images_tensor, audio_out = collect_frame_output(
            media_converter=media_converter,
            output_path=output_path,
            unique_id=unique_id,
            hidden_prompt=hidden_prompt,
            removes_audio=False,
        )
        analysis = (
            f"AudioX Inpaint-Only Mode (no LLM) — save_only\n"
            f"Prompt: {prompt or '(no text prompt)'}\n"
            f"Inpainted audio saved to: {audio_file}\n"
            f"(Audio was NOT muxed into the video)"
        )
        return (images_tensor, audio_out, output_path, "", analysis, "")

    # --- Mux inpainted audio back into video ---
    effective_crf = crf if crf >= 0 else _CRF_MAP.get(quality_preset, 23)
    effective_preset = encoding_preset if encoding_preset != "auto" else _PRESET_MAP.get(quality_preset, "medium")

    if audio_output_mode == "mix" and has_audio:
        ffmpeg_cmd = [
            _ffmpeg, "-y",
            "-i", effective_video_path,
            "-i", audio_file,
            "-filter_complex",
            "[0:a][1:a]amix=inputs=2:duration=shortest[aout]",
            "-map", "0:v",
            "-map", "[aout]",
            "-c:v", "libx264",
            "-crf", str(effective_crf),
            "-preset", effective_preset,
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "192k",
        ]
    else:
        ffmpeg_cmd = [
            _ffmpeg, "-y",
            "-i", effective_video_path,
            "-i", audio_file,
            "-map", "0:v",
            "-map", "1:a",
            "-c:v", "copy",
            "-c:a", "aac",
            "-b:a", "192k",
            "-shortest",
        ]

    if preview_mode:
        if audio_output_mode == "mix" and has_audio:
            ffmpeg_cmd.extend(["-vf", "scale=480:trunc(ow/a/2)*2", "-t", "10"])
        else:
            ffmpeg_cmd = [
                _ffmpeg, "-y",
                "-i", effective_video_path,
                "-i", audio_file,
                "-map", "0:v",
                "-map", "1:a",
                "-vf", "scale=480:trunc(ow/a/2)*2",
                "-t", "10",
                "-c:v", "libx264",
                "-crf", str(effective_crf),
                "-preset", effective_preset,
                "-pix_fmt", "yuv420p",
                "-c:a", "aac",
                "-b:a", "192k",
                "-shortest",
            ]

    ffmpeg_cmd.append(output_path)

    logger.debug("AudioX inpaint-only ffmpeg command: %s", " ".join(ffmpeg_cmd))
    try:
        proc = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(
                f"AudioX inpaint-only mode: ffmpeg mux failed:\n{proc.stderr[-500:]}"
            )

        unique_id = str(kwargs.get("unique_id", ""))
        hidden_prompt = kwargs.get("hidden_prompt") or {}
        images_tensor, audio_out = collect_frame_output(
            media_converter=media_converter,
            output_path=output_path,
            unique_id=unique_id,
            hidden_prompt=hidden_prompt,
            removes_audio=False,
        )

        cmd_log = " ".join(ffmpeg_cmd)
        analysis = (
            f"AudioX Inpaint-Only Mode (no LLM)\n"
            f"Prompt: {prompt or '(no text prompt)'}\n"
            f"Audio mode: {audio_output_mode}\n"
            f"Mask: 50-100% (audio completion)\n\n"
            f"Inpainted audio: {audio_file}\n"
            f"Output: {output_path}"
        )

        return (images_tensor, audio_out, output_path, cmd_log, analysis, "")
    finally:
        for tmp_path in [temp_video_from_images, temp_video_with_audio, tmp_wav_path]:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
        if audio_file and os.path.exists(audio_file):
            try:
                os.remove(audio_file)
            except OSError:
                pass
        if not save_output and temp_render_dir and os.path.isdir(temp_render_dir):
            if not os.listdir(temp_render_dir):
                shutil.rmtree(temp_render_dir, ignore_errors=True)


async def process_sam_audio_separate(
    # dependencies
    media_converter,
    # parameters
    prompt: str,
    audio_output_mode: str,
    effective_video_path: str,
    video_metadata,
    save_output: bool,
    output_path: str,
    preview_mode: bool,
    quality_preset: str,
    crf: int,
    encoding_preset: str,
    temp_video_from_images: Optional[str] = None,
    temp_video_with_audio: Optional[str] = None,
    **kwargs,
) -> tuple[torch.Tensor, dict, str, str, str, str]:
    """Run SAM-Audio separation directly without any LLM involvement.

    Extracts audio from the video, separates the target sound described by
    the prompt, then muxes the isolated audio back into the video.

    Args:
        prompt: Text description of the sound to isolate, e.g. "drums",
                "vocals", "piano". Use lowercase noun-phrase format.
        audio_output_mode: "auto"/"replace" to discard original audio,
                           "mix" to blend, "save_only" to skip muxing.

    Returns the standard 6-tuple:
        (images_tensor, audio, output_path, command_log, analysis, mask_overlay_path)
    """
    # Treat "auto" as "replace" in no-LLM context
    if audio_output_mode == "auto":
        audio_output_mode = "replace"
    logger.info("SAM-Audio separate mode: prompt=%r, mode=%s", prompt, audio_output_mode)

    # --- Import SAM-Audio ---
    try:
        try:
            from ..core.sam_audio_synthesizer import separate_audio
        except ImportError:
            from core.sam_audio_synthesizer import separate_audio  # type: ignore
    except ImportError:
        raise RuntimeError(
            "SAM-Audio is not installed. Install with: "
            "pip install --no-deps git+https://github.com/facebookresearch/sam-audio.git"
        )

    # --- Extract audio for separation ---
    _ffmpeg = _get_ffmpeg_bin()
    tmp_wav = tempfile.NamedTemporaryFile(
        suffix=".wav", delete=False, prefix="ffmpega_sa_"
    )
    tmp_wav_path = tmp_wav.name
    tmp_wav.close()

    extract_result = subprocess.run(
        [_ffmpeg, "-y", "-i", effective_video_path,
         "-vn", "-acodec", "pcm_f32le", "-ar", "48000", "-ac", "1",
         tmp_wav_path],
        capture_output=True, timeout=60,
    )
    if extract_result.returncode != 0:
        raise RuntimeError(
            "SAM-Audio separate mode: failed to extract audio from video. "
            "Ensure the input video has an audio track."
        )

    # --- Build output path ---
    output_path, temp_render_dir = build_output_path(
        effective_video_path=effective_video_path,
        save_output=save_output,
        output_path=output_path,
        preview_mode=preview_mode,
    )

    # --- Separate audio via SAM-Audio ---
    sam_audio_model = kwargs.get("sam_audio_model", "base")
    result = None
    try:
        result = separate_audio(
            audio_path=tmp_wav_path,
            description=prompt,
            video_path=effective_video_path,
            predict_spans=False,
            model_variant=sam_audio_model,
        )
    except Exception as e:
        logger.error("SAM-Audio separate mode: separation failed: %s", e)
        try:
            try:
                from ..core.sam_audio_synthesizer import unload_models as _sa_unload
            except ImportError:
                from core.sam_audio_synthesizer import unload_models as _sa_unload  # type: ignore
            _sa_unload()
        except Exception:
            pass
        raise RuntimeError(f"SAM-Audio separation failed: {e}") from e

    # --- Mux separated target audio back into video ---
    target_audio_file = result["target"]
    residual_audio_file = result["residual"]

    # --- Detect if source has audio (for mix mode) ---
    has_audio = bool(video_metadata.primary_audio)

    # --- save_only: skip muxing, just return the audio file paths ---
    if audio_output_mode == "save_only":
        shutil.copy2(effective_video_path, output_path)
        unique_id = str(kwargs.get("unique_id", ""))
        hidden_prompt = kwargs.get("hidden_prompt") or {}
        images_tensor, audio_out = collect_frame_output(
            media_converter=media_converter,
            output_path=output_path,
            unique_id=unique_id,
            hidden_prompt=hidden_prompt,
            removes_audio=False,
        )
        analysis = (
            f"SAM-Audio Separate Mode (no LLM) — save_only\n"
            f"Description: {prompt or '(no text prompt)'}\n"
            f"Target audio saved to: {target_audio_file}\n"
            f"Residual audio saved to: {residual_audio_file}\n"
            f"(Audio was NOT muxed into the video)"
        )
        return (images_tensor, audio_out, output_path, "", analysis, "")

    effective_crf = crf if crf >= 0 else _CRF_MAP.get(quality_preset, 23)
    effective_preset = encoding_preset if encoding_preset != "auto" else _PRESET_MAP.get(quality_preset, "medium")

    if audio_output_mode == "mix" and has_audio:
        ffmpeg_cmd = [
            _ffmpeg, "-y",
            "-i", effective_video_path,
            "-i", target_audio_file,
            "-filter_complex",
            "[0:a][1:a]amix=inputs=2:duration=shortest[aout]",
            "-map", "0:v",
            "-map", "[aout]",
            "-c:v", "libx264",
            "-crf", str(effective_crf),
            "-preset", effective_preset,
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "192k",
        ]
    else:
        ffmpeg_cmd = [
            _ffmpeg, "-y",
            "-i", effective_video_path,
            "-i", target_audio_file,
            "-map", "0:v",
            "-map", "1:a",
            "-c:v", "copy",
            "-c:a", "aac",
            "-b:a", "192k",
            "-shortest",
        ]

    if preview_mode:
        if audio_output_mode == "mix" and has_audio:
            ffmpeg_cmd.extend(["-vf", "scale=480:trunc(ow/a/2)*2", "-t", "10"])
        else:
            ffmpeg_cmd = [
                _ffmpeg, "-y",
                "-i", effective_video_path,
                "-i", target_audio_file,
                "-map", "0:v",
                "-map", "1:a",
                "-vf", "scale=480:trunc(ow/a/2)*2",
                "-t", "10",
                "-c:v", "libx264",
                "-crf", str(effective_crf),
                "-preset", effective_preset,
                "-pix_fmt", "yuv420p",
                "-c:a", "aac",
                "-b:a", "192k",
                "-shortest",
            ]

    ffmpeg_cmd.append(output_path)

    logger.debug("SAM-Audio separate ffmpeg command: %s", " ".join(ffmpeg_cmd))
    try:
        proc = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(
                f"SAM-Audio separate mode: ffmpeg mux failed:\n{proc.stderr[-500:]}"
            )

        unique_id = str(kwargs.get("unique_id", ""))
        hidden_prompt = kwargs.get("hidden_prompt") or {}
        images_tensor, audio_out = collect_frame_output(
            media_converter=media_converter,
            output_path=output_path,
            unique_id=unique_id,
            hidden_prompt=hidden_prompt,
            removes_audio=False,
        )

        cmd_log = " ".join(ffmpeg_cmd)
        analysis = (
            f"SAM-Audio Separate Mode (no LLM)\n"
            f"Description: {prompt or '(no text prompt)'}\n"
            f"Audio mode: {audio_output_mode}\n\n"
            f"Target audio: {target_audio_file}\n"
            f"Residual audio: {residual_audio_file}\n"
            f"Output: {output_path}"
        )

        return (images_tensor, audio_out, output_path, cmd_log, analysis, "")
    finally:
        for tmp_path in [temp_video_from_images, temp_video_with_audio, tmp_wav_path]:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
        for tmp_path in [target_audio_file, residual_audio_file]:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
        if not save_output and temp_render_dir and os.path.isdir(temp_render_dir):
            if not os.listdir(temp_render_dir):
                shutil.rmtree(temp_render_dir, ignore_errors=True)


async def process_lip_sync_only(
    # dependencies
    media_converter,
    # parameters
    effective_video_path: str,
    video_metadata,
    save_output: bool,
    output_path: str,
    preview_mode: bool,
    quality_preset: str,
    crf: int,
    encoding_preset: str,
    audio_a=None,
    temp_video_from_images: Optional[str] = None,
    temp_video_with_audio: Optional[str] = None,
    **kwargs,
) -> tuple[torch.Tensor, dict, str, str, str, str]:
    """Run MuseTalk lip sync directly without any LLM involvement.

    Converts the connected audio_a input to a WAV file and runs
    MuseTalk lip_sync in-process to synchronize lip movements.

    Requires audio_a to be connected — raises RuntimeError if missing.

    Returns the standard 6-tuple:
        (images_tensor, audio, output_path, command_log, analysis, mask_overlay_path)
    """
    logger.info("Lip sync mode: starting MuseTalk lip sync")

    if audio_a is None:
        raise RuntimeError(
            "Lip sync mode requires an audio input. "
            "Connect an audio source to the audio_a input."
        )

    # --- Convert audio_a to WAV ---
    from .output_handler import audio_dict_to_wav
    audio_wav_path = audio_dict_to_wav(audio_a)
    if not audio_wav_path:
        raise RuntimeError(
            "Lip sync mode: failed to convert audio_a to WAV. "
            "Check that the audio input is valid."
        )

    # --- Import MuseTalk ---
    try:
        try:
            from ..core.musetalk_synthesizer import lip_sync
        except ImportError:
            from core.musetalk_synthesizer import lip_sync  # type: ignore
    except ImportError:
        raise RuntimeError(
            "MuseTalk lip sync is not available. "
            "All dependencies should be built into ComfyUI — "
            "check that core/musetalk_synthesizer.py exists."
        )

    # --- Build output path ---
    output_path, temp_render_dir = build_output_path(
        effective_video_path=effective_video_path,
        save_output=save_output,
        output_path=output_path,
        preview_mode=preview_mode,
    )

    # --- Run MuseTalk lip sync (in-process) ---
    lip_synced_video = None
    try:
        lip_synced_video = lip_sync(
            video_path=effective_video_path,
            audio_path=audio_wav_path,
            batch_size=8,
            face_index=-1,
        )
    except Exception as e:
        logger.error("Lip sync mode: MuseTalk failed: %s", e)
        raise RuntimeError(f"MuseTalk lip sync failed: {e}") from e

    # --- Re-encode to output path ---
    _ffmpeg = _get_ffmpeg_bin()
    effective_crf = crf if crf >= 0 else _CRF_MAP.get(quality_preset, 23)
    effective_preset = encoding_preset if encoding_preset != "auto" else _PRESET_MAP.get(quality_preset, "medium")

    ffmpeg_cmd = [
        _ffmpeg, "-y",
        "-i", lip_synced_video,
        "-c:v", "libx264",
        "-crf", str(effective_crf),
        "-preset", effective_preset,
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "192k",
    ]

    if preview_mode:
        ffmpeg_cmd.extend(["-vf", "scale=480:trunc(ow/a/2)*2", "-t", "10"])

    ffmpeg_cmd.append(output_path)

    logger.debug("Lip sync ffmpeg command: %s", " ".join(ffmpeg_cmd))
    try:
        proc = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(
                f"Lip sync mode: ffmpeg encoding failed:\n{proc.stderr[-500:]}"
            )

        # --- Collect frame/audio output ---
        unique_id = str(kwargs.get("unique_id", ""))
        hidden_prompt = kwargs.get("hidden_prompt") or {}
        images_tensor, audio_out = collect_frame_output(
            media_converter=media_converter,
            output_path=output_path,
            unique_id=unique_id,
            hidden_prompt=hidden_prompt,
            removes_audio=False,
        )

        # --- Build analysis string ---
        cmd_log = " ".join(ffmpeg_cmd)
        analysis = (
            f"Lip Sync Mode (no LLM)\n"
            f"Audio source: connected audio_a\n"
            f"Audio WAV: {audio_wav_path}\n"
            f"Lip-synced video: {lip_synced_video}\n\n"
            f"Output: {output_path}"
        )

        return (images_tensor, audio_out, output_path, cmd_log, analysis, "")
    finally:
        # --- Cleanup temp files (always runs, even on error) ---
        for tmp_path in [temp_video_from_images, temp_video_with_audio, audio_wav_path]:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
        # Clean up MuseTalk temp output
        if lip_synced_video and os.path.exists(lip_synced_video):
            try:
                os.remove(lip_synced_video)
            except OSError:
                pass
        if not save_output and temp_render_dir and os.path.isdir(temp_render_dir):
            if not os.listdir(temp_render_dir):
                shutil.rmtree(temp_render_dir, ignore_errors=True)


async def process_animate_portrait_only(
    # dependencies
    media_converter,
    # parameters
    effective_video_path: str,
    video_metadata,
    save_output: bool,
    output_path: str,
    preview_mode: bool,
    quality_preset: str,
    crf: int,
    encoding_preset: str,
    driving_video: str = "",
    driving_multiplier: float = 1.0,
    relative_motion: bool = True,
    # Expression controls
    lp_rotate_pitch: float = 0.0,
    lp_rotate_yaw: float = 0.0,
    lp_rotate_roll: float = 0.0,
    lp_blink: float = 0.0,
    lp_eyebrow: float = 0.0,
    lp_wink: float = 0.0,
    lp_pupil_x: float = 0.0,
    lp_pupil_y: float = 0.0,
    lp_aaa: float = 0.0,
    lp_eee: float = 0.0,
    lp_woo: float = 0.0,
    lp_smile: float = 0.0,
    # Retargeting
    lp_retargeting_eyes: float = 1.0,
    lp_retargeting_mouth: float = 1.0,
    # Crop
    lp_crop_factor: float = 1.6,
    # Expression transfer
    lp_sample_image: str = "",
    lp_sample_ratio: float = 1.0,
    lp_sample_parts: str = "all",
    temp_video_from_images: Optional[str] = None,
    temp_video_with_audio: Optional[str] = None,
    **kwargs,
) -> tuple[torch.Tensor, dict, str, str, str, str]:
    """Run LivePortrait face animation directly without any LLM involvement.

    Animates the face in the source video/image using motion from a
    driving video, or using expression sliders alone (no driving video).
    The source is ``effective_video_path`` (from ``video_path`` or
    ``images_a``) and the driving video comes from ``video_a``.

    Returns the standard 6-tuple:
        (images_tensor, audio, output_path, command_log, analysis, mask_overlay_path)
    """
    logger.info("Animate portrait mode: starting LivePortrait")

    # Build expression kwargs dict (strip lp_ prefix)
    _expr_kwargs = dict(
        rotate_pitch=lp_rotate_pitch, rotate_yaw=lp_rotate_yaw,
        rotate_roll=lp_rotate_roll, blink=lp_blink, eyebrow=lp_eyebrow,
        wink=lp_wink, pupil_x=lp_pupil_x, pupil_y=lp_pupil_y,
        aaa=lp_aaa, eee=lp_eee, woo=lp_woo, smile=lp_smile,
    )
    _has_expr = any(v != 0.0 for v in _expr_kwargs.values())
    _has_driving = driving_video and os.path.isfile(driving_video)
    _has_sample = lp_sample_image and os.path.isfile(lp_sample_image)

    if not _has_driving and not _has_expr and not _has_sample:
        raise RuntimeError(
            "Animate portrait mode requires a driving video "
            "or at least one expression control to be set. "
            "Connect a driving video to the video_a input, "
            "or adjust the expression sliders."
        )

    # --- Import LivePortrait ---
    try:
        try:
            from ..core.liveportrait_synthesizer import (
                animate_portrait, animate_portrait_static,
            )
        except ImportError:
            from core.liveportrait_synthesizer import (  # type: ignore
                animate_portrait, animate_portrait_static,
            )
    except ImportError:
        raise RuntimeError(
            "LivePortrait is not available. "
            "Ensure all dependencies are installed and "
            "core/liveportrait_synthesizer.py exists."
        )

    # --- Build output path ---
    output_path, temp_render_dir = build_output_path(
        effective_video_path=effective_video_path,
        save_output=save_output,
        output_path=output_path,
        preview_mode=preview_mode,
    )

    # --- Run LivePortrait (in-process with offloading) ---
    animated_video = None
    try:
        if _has_driving:
            animated_video = animate_portrait(
                source_path=effective_video_path,
                driving_path=driving_video,
                driving_multiplier=driving_multiplier,
                relative_motion=relative_motion,
                retargeting_eyes=lp_retargeting_eyes,
                retargeting_mouth=lp_retargeting_mouth,
                crop_factor=lp_crop_factor,
                sample_image=lp_sample_image if _has_sample else None,
                sample_ratio=lp_sample_ratio,
                sample_parts=lp_sample_parts,
                **_expr_kwargs,
            )
        else:
            animated_video = animate_portrait_static(
                source_path=effective_video_path,
                crop_factor=lp_crop_factor,
                **_expr_kwargs,
            )
    except Exception as e:
        logger.error("Animate portrait mode: LivePortrait failed: %s", e)
        # Free VRAM on failure
        try:
            try:
                from ..core.liveportrait_synthesizer import cleanup as _lp_cleanup
            except ImportError:
                from core.liveportrait_synthesizer import cleanup as _lp_cleanup  # type: ignore
            _lp_cleanup()
        except Exception:
            pass
        raise RuntimeError(f"LivePortrait animation failed: {e}") from e

    # --- Re-encode to output path ---
    _ffmpeg = _get_ffmpeg_bin()
    effective_crf = crf if crf >= 0 else _CRF_MAP.get(quality_preset, 23)
    effective_preset = encoding_preset if encoding_preset != "auto" else _PRESET_MAP.get(quality_preset, "medium")

    ffmpeg_cmd = [
        _ffmpeg, "-y",
        "-i", animated_video,
        "-c:v", "libx264",
        "-crf", str(effective_crf),
        "-preset", effective_preset,
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "192k",
    ]

    if preview_mode:
        ffmpeg_cmd.extend(["-vf", "scale=480:trunc(ow/a/2)*2", "-t", "10"])

    ffmpeg_cmd.append(output_path)

    logger.debug("Animate portrait ffmpeg command: %s", " ".join(ffmpeg_cmd))
    try:
        proc = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(
                f"Animate portrait mode: ffmpeg encoding failed:\n"
                f"{proc.stderr[-500:]}"
            )

        # --- Collect frame/audio output ---
        unique_id = str(kwargs.get("unique_id", ""))
        hidden_prompt = kwargs.get("hidden_prompt") or {}
        images_tensor, audio_out = collect_frame_output(
            media_converter=media_converter,
            output_path=output_path,
            unique_id=unique_id,
            hidden_prompt=hidden_prompt,
            removes_audio=False,
        )

        # --- Build analysis string ---
        cmd_log = " ".join(ffmpeg_cmd)
        analysis = (
            f"Animate Portrait Mode (no LLM)\n"
            f"Source: {effective_video_path}\n"
            f"Driving video: {driving_video}\n"
            f"Motion multiplier: {driving_multiplier}\n"
            f"Relative motion: {relative_motion}\n\n"
            f"Animated video: {animated_video}\n"
            f"Output: {output_path}"
        )

        return (images_tensor, audio_out, output_path, cmd_log, analysis, "")
    finally:
        # --- Cleanup temp files (always runs, even on error) ---
        for tmp_path in [temp_video_from_images, temp_video_with_audio]:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
        # Clean up LivePortrait temp output
        if animated_video and os.path.exists(animated_video):
            try:
                os.remove(animated_video)
            except OSError:
                pass
        if not save_output and temp_render_dir and os.path.isdir(temp_render_dir):
            if not os.listdir(temp_render_dir):
                shutil.rmtree(temp_render_dir, ignore_errors=True)


async def process_marigold_only(
    # dependencies
    media_converter,
    # parameters
    effective_video_path: str,
    video_metadata,
    save_output: bool,
    output_path: str,
    preview_mode: bool,
    quality_preset: str,
    crf: int,
    encoding_preset: str,
    marigold_output_type: str = "depth",
    marigold_colormap: str = "Spectral",
    marigold_num_steps: int = 4,
    marigold_ensemble_size: int = 1,
    temp_video_from_images: Optional[str] = None,
    temp_video_with_audio: Optional[str] = None,
    **kwargs,
) -> tuple[torch.Tensor, dict, str, str, str, str]:
    """Run Marigold dense vision analysis directly without any LLM involvement.

    Produces depth maps, surface normals, or intrinsic image decomposition
    (appearance or lighting) from the input image or video.

    Args:
        marigold_output_type: One of 'depth', 'normals', 'appearance', 'lighting'.
        marigold_num_steps: Number of denoising steps (1-50).
        marigold_ensemble_size: Number of ensemble predictions (1-10).

    Returns the standard 6-tuple:
        (images_tensor, audio, output_path, command_log, analysis, mask_overlay_path)
    """
    logger.info(
        "Marigold mode: type=%s, steps=%d, ensemble=%d",
        marigold_output_type, marigold_num_steps, marigold_ensemble_size,
    )

    # --- Import Marigold synthesizer ---
    try:
        try:
            from ..core.marigold_synthesizer import run_marigold, cleanup as _mg_cleanup
        except ImportError:
            from core.marigold_synthesizer import run_marigold, cleanup as _mg_cleanup  # type: ignore
    except ImportError:
        raise RuntimeError(
            "Marigold is not available. "
            "Ensure diffusers >= 0.28.0 is installed and "
            "core/marigold_synthesizer.py exists."
        )

    # --- Build output path ---
    output_path, temp_render_dir = build_output_path(
        effective_video_path=effective_video_path,
        save_output=save_output,
        output_path=output_path,
        preview_mode=preview_mode,
    )

    # --- Run Marigold (in-process with GPU offloading) ---
    marigold_output = None
    try:
        marigold_output = run_marigold(
            input_path=effective_video_path,
            output_type=marigold_output_type,
            colormap=marigold_colormap,
            num_steps=marigold_num_steps,
            ensemble_size=marigold_ensemble_size,
        )
    except Exception as e:
        logger.error("Marigold mode: inference failed: %s", e)
        # Free VRAM on failure
        try:
            _mg_cleanup()
        except Exception:
            pass
        raise RuntimeError(f"Marigold inference failed: {e}") from e

    # --- Re-encode to output path ---
    _ffmpeg = _get_ffmpeg_bin()
    effective_crf = crf if crf >= 0 else _CRF_MAP.get(quality_preset, 23)
    effective_preset = encoding_preset if encoding_preset != "auto" else _PRESET_MAP.get(quality_preset, "medium")

    # Determine if output is image or video
    ext = os.path.splitext(marigold_output)[1].lower()
    is_image = ext in (".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".webp")

    if is_image:
        # For images, just copy to output path (change extension)
        import shutil as _shutil
        output_path = str(Path(output_path).with_suffix(ext))
        _shutil.copy2(marigold_output, output_path)
        cmd_log = f"cp {marigold_output} {output_path}"
    else:
        # For video, re-encode
        ffmpeg_cmd = [
            _ffmpeg, "-y",
            "-i", marigold_output,
            "-c:v", "libx264",
            "-crf", str(effective_crf),
            "-preset", effective_preset,
            "-pix_fmt", "yuv420p",
            "-an",  # Marigold output has no audio
        ]

        if preview_mode:
            ffmpeg_cmd.extend(["-vf", "scale=480:trunc(ow/a/2)*2", "-t", "10"])

        ffmpeg_cmd.append(output_path)

        logger.debug("Marigold ffmpeg command: %s", " ".join(ffmpeg_cmd))
        proc = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(
                f"Marigold mode: ffmpeg encoding failed:\n{proc.stderr[-500:]}"
            )
        cmd_log = " ".join(ffmpeg_cmd)

    try:
        # --- Collect frame/audio output ---
        unique_id = str(kwargs.get("unique_id", ""))
        hidden_prompt = kwargs.get("hidden_prompt") or {}
        images_tensor, audio_out = collect_frame_output(
            media_converter=media_converter,
            output_path=output_path,
            unique_id=unique_id,
            hidden_prompt=hidden_prompt,
            removes_audio=True,
        )

        # --- Build analysis string ---
        _type_desc = {
            "depth": "Monocular depth estimation",
            "normals": "Surface normals estimation",
            "appearance": "Intrinsic decomposition (albedo, roughness, metallicity)",
            "lighting": "Intrinsic decomposition (albedo, shading, residual)",
        }
        analysis = (
            f"Marigold Mode (no LLM)\n"
            f"Output type: {marigold_output_type} — "
            f"{_type_desc.get(marigold_output_type, marigold_output_type)}\n"
            f"Denoising steps: {marigold_num_steps}\n"
            f"Ensemble size: {marigold_ensemble_size}\n\n"
            f"Source: {effective_video_path}\n"
            f"Marigold output: {marigold_output}\n"
            f"Output: {output_path}"
        )

        return (images_tensor, audio_out, output_path, cmd_log, analysis, "")
    finally:
        # --- Cleanup temp files (always runs, even on error) ---
        for tmp_path in [temp_video_from_images, temp_video_with_audio]:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
        # Clean up Marigold temp output
        if marigold_output and os.path.exists(marigold_output):
            try:
                os.remove(marigold_output)
            except OSError:
                pass
        if not save_output and temp_render_dir and os.path.isdir(temp_render_dir):
            if not os.listdir(temp_render_dir):
                shutil.rmtree(temp_render_dir, ignore_errors=True)


async def process_sapiens2_only(
    # dependencies
    media_converter,
    # parameters
    effective_video_path: str,
    video_metadata,
    save_output: bool,
    output_path: str,
    preview_mode: bool,
    quality_preset: str,
    crf: int,
    encoding_preset: str,
    sapiens2_task: str = "pose",
    sapiens2_size: str = "1b",
    sapiens2_precision: str = "auto",
    sapiens2_seg_alpha: float = 0.5,
    sapiens2_pose_kpt_thr: float = 0.3,
    sapiens2_pose_radius: int = 6,
    sapiens2_pose_thickness: int = 4,
    temp_video_from_images: Optional[str] = None,
    temp_video_with_audio: Optional[str] = None,
    **kwargs,
) -> tuple[torch.Tensor, dict, str, str, str, str]:
    """Run Meta Sapiens2 human-centric vision without LLM involvement.

    Produces per-frame visualizations for one of six tasks: 308-keypoint
    pose, 29-class body-part segmentation, surface normals, 3D pointmap,
    human matting, or raw backbone features.

    Returns the standard 6-tuple:
        (images_tensor, audio, output_path, command_log, analysis, mask_overlay_path)

    License:
        Sapiens2 / Meta Proprietary.  Not for surveillance, biometric
        identification, deepfake generation, or weapons / critical-
        infrastructure use.  Attribution required on publications.
    """
    # The size dropdown folds the fp8 model choice into its value (e.g.
    # "5b (fp8)"); split it back out so a trailing precision suffix wins over
    # the (default "auto") sapiens2_precision value.
    try:
        from ..core.sapiens2 import _registry as _sap_reg
    except ImportError:
        from core.sapiens2 import _registry as _sap_reg  # type: ignore
    parsed_size, prec_override = _sap_reg.parse_size_selector(sapiens2_size)
    effective_precision = prec_override or sapiens2_precision

    logger.info(
        "Sapiens2 mode: task=%s size=%s precision=%s",
        sapiens2_task, parsed_size, effective_precision,
    )

    # --- Import synthesizer ---
    try:
        try:
            from ..core.sapiens2_synthesizer import (
                run_sapiens2,
                cleanup as _sap_cleanup,
            )
        except ImportError:
            from core.sapiens2_synthesizer import (  # type: ignore
                run_sapiens2,
                cleanup as _sap_cleanup,
            )
    except ImportError as exc:
        raise RuntimeError(
            "Sapiens2 is not available — "
            f"{exc}. Run install.py inside the ComfyUI venv or "
            "`pip install --no-deps git+https://github.com/facebookresearch/sapiens2.git`."
        )

    # --- Build output path ---
    output_path, temp_render_dir = build_output_path(
        effective_video_path=effective_video_path,
        save_output=save_output,
        output_path=output_path,
        preview_mode=preview_mode,
    )

    # --- Validate-and-coerce numeric params (the UI sends strings/floats) ---
    try:
        seg_alpha = float(sapiens2_seg_alpha)
        pose_kpt_thr = float(sapiens2_pose_kpt_thr)
        pose_radius = max(1, int(sapiens2_pose_radius))
        pose_thickness = max(1, int(sapiens2_pose_thickness))
    except (TypeError, ValueError) as exc:
        raise RuntimeError(
            f"Sapiens2 mode: invalid numeric parameter — {exc}"
        ) from exc

    effective_crf = crf if crf >= 0 else _CRF_MAP.get(quality_preset, 23)
    effective_preset = (
        encoding_preset if encoding_preset != "auto"
        else _PRESET_MAP.get(quality_preset, "medium")
    )

    # --- Run inference ---
    sapiens_output: Optional[str] = None
    try:
        sapiens_output = run_sapiens2(
            effective_video_path,
            task=sapiens2_task,
            size=parsed_size,
            precision=effective_precision,
            seg_alpha=seg_alpha,
            pose_kpt_thr=pose_kpt_thr,
            pose_radius=pose_radius,
            pose_thickness=pose_thickness,
            crf=effective_crf,
            preset=effective_preset,
        )
    except Exception as exc:
        logger.error("Sapiens2 mode: inference failed: %s", exc)
        try:
            _sap_cleanup()
        except Exception:
            pass
        raise RuntimeError(f"Sapiens2 inference failed: {exc}") from exc

    # --- Re-encode preview / move to output path ---
    ext = os.path.splitext(sapiens_output)[1].lower()
    is_image = ext in (".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".webp")
    if is_image:
        import shutil as _shutil
        output_path = str(Path(output_path).with_suffix(ext))
        _shutil.copy2(sapiens_output, output_path)
        cmd_log = f"cp {sapiens_output} {output_path}"
    else:
        ffmpeg = _get_ffmpeg_bin()
        ffmpeg_cmd = [
            ffmpeg, "-y",
            "-i", sapiens_output,
            "-c:v", "libx264",
            "-crf", str(effective_crf),
            "-preset", effective_preset,
            "-pix_fmt", "yuv420p",
            "-an",
        ]
        if preview_mode:
            ffmpeg_cmd.extend(["-vf", "scale=480:trunc(ow/a/2)*2", "-t", "10"])
        ffmpeg_cmd.append(output_path)

        logger.debug("Sapiens2 ffmpeg command: %s", " ".join(ffmpeg_cmd))
        proc = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(
                f"Sapiens2 mode: ffmpeg encoding failed:\n{proc.stderr[-500:]}"
            )
        cmd_log = " ".join(ffmpeg_cmd)

    try:
        # --- Collect frame/audio output ---
        unique_id = str(kwargs.get("unique_id", ""))
        hidden_prompt = kwargs.get("hidden_prompt") or {}
        images_tensor, audio_out = collect_frame_output(
            media_converter=media_converter,
            output_path=output_path,
            unique_id=unique_id,
            hidden_prompt=hidden_prompt,
            removes_audio=True,
        )

        _task_desc = {
            "pose": "308-keypoint top-down pose (body + face + hands + feet)",
            "seg": "29-class human body-part segmentation overlay",
            "normal": "per-pixel surface normals",
            "pointmap": "3D pointmap (z-channel turbo colormap)",
            "matting": "human matting (alpha composited on green)",
            "pretrain": "raw backbone features (PCA-visualized RGB)",
        }
        analysis = (
            f"Sapiens2 Mode (no LLM)\n"
            f"Task: {sapiens2_task} — {_task_desc.get(sapiens2_task, sapiens2_task)}\n"
            f"Size: {sapiens2_size} (precision: {sapiens2_precision})\n"
            f"Source: {effective_video_path}\n"
            f"Sapiens2 output: {sapiens_output}\n"
            f"Output: {output_path}\n"
            f"License: Sapiens2/Meta Proprietary — no surveillance, biometric "
            f"identification, or deepfake use; attribution required."
        )

        return (images_tensor, audio_out, output_path, cmd_log, analysis, "")
    finally:
        # --- Cleanup temp files (always runs) ---
        for tmp_path in [temp_video_from_images, temp_video_with_audio]:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
        if sapiens_output and os.path.exists(sapiens_output):
            try:
                os.remove(sapiens_output)
            except OSError:
                pass
        if not save_output and temp_render_dir and os.path.isdir(temp_render_dir):
            if not os.listdir(temp_render_dir):
                shutil.rmtree(temp_render_dir, ignore_errors=True)


async def process_normalcrafter_only(
    # dependencies
    media_converter,
    # parameters
    effective_video_path: str,
    video_metadata,
    save_output: bool,
    output_path: str,
    preview_mode: bool,
    quality_preset: str,
    crf: int,
    encoding_preset: str,
    normalcrafter_max_res: str = "auto",
    normalcrafter_window_size: int = 14,
    normalcrafter_process_length: int = -1,
    normalcrafter_target_fps: int = -1,
    normalcrafter_seed: int = 42,
    temp_video_from_images: Optional[str] = None,
    temp_video_with_audio: Optional[str] = None,
    **kwargs,
) -> tuple[torch.Tensor, dict, str, str, str, str]:
    """Run NormalCrafter video normal map generation without LLM involvement.

    Produces temporally consistent surface normal map videos using video
    diffusion priors (NormalCrafter).

    Args:
        normalcrafter_max_res: Maximum processing resolution. One of
            'auto', '1024', '768', '512'.  'auto' detects GPU VRAM and
            picks a safe resolution.
        normalcrafter_window_size: Temporal window size for sliding inference.
        normalcrafter_process_length: Max frames to process (-1 = all).
        normalcrafter_target_fps: Target FPS (-1 = use original).
        normalcrafter_seed: Random seed for reproducibility.

    Returns the standard 6-tuple:
        (images_tensor, audio, output_path, command_log, analysis, mask_overlay_path)
    """
    logger.info(
        "NormalCrafter mode: max_res=%s, window=%d, seed=%d",
        normalcrafter_max_res, normalcrafter_window_size, normalcrafter_seed,
    )

    # --- Import NormalCrafter synthesizer ---
    try:
        try:
            from ..core.normalcrafter_synthesizer import run_normalcrafter, cleanup as _nc_cleanup
        except ImportError:
            from core.normalcrafter_synthesizer import run_normalcrafter, cleanup as _nc_cleanup  # type: ignore
    except ImportError:
        raise RuntimeError(
            "NormalCrafter is not available. "
            "Install with: pip install --no-deps "
            "git+https://github.com/Binyr/NormalCrafter.git"
        )

    # --- Build output path ---
    output_path, temp_render_dir = build_output_path(
        effective_video_path=effective_video_path,
        save_output=save_output,
        output_path=output_path,
        preview_mode=preview_mode,
    )

    # --- Run NormalCrafter (in-process with GPU offloading) ---
    nc_output = None
    try:
        nc_output = run_normalcrafter(
            video_path=effective_video_path,
            max_res=normalcrafter_max_res,
            window_size=normalcrafter_window_size,
            process_length=normalcrafter_process_length,
            target_fps=normalcrafter_target_fps,
            seed=normalcrafter_seed,
        )
    except Exception as e:
        logger.error("NormalCrafter mode: inference failed: %s", e)
        try:
            _nc_cleanup()
        except Exception:
            pass
        raise RuntimeError(f"NormalCrafter inference failed: {e}") from e

    # --- Re-encode to output path ---
    _ffmpeg = _get_ffmpeg_bin()
    effective_crf = crf if crf >= 0 else _CRF_MAP.get(quality_preset, 23)
    effective_preset = encoding_preset if encoding_preset != "auto" else _PRESET_MAP.get(quality_preset, "medium")

    ffmpeg_cmd = [
        _ffmpeg, "-y",
        "-i", nc_output,
        "-c:v", "libx264",
        "-crf", str(effective_crf),
        "-preset", effective_preset,
        "-pix_fmt", "yuv420p",
        "-an",  # NormalCrafter output has no audio
    ]

    if preview_mode:
        ffmpeg_cmd.extend(["-vf", "scale=480:trunc(ow/a/2)*2", "-t", "10"])

    ffmpeg_cmd.append(output_path)

    logger.debug("NormalCrafter ffmpeg command: %s", " ".join(ffmpeg_cmd))
    proc = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"NormalCrafter mode: ffmpeg encoding failed:\n{proc.stderr[-500:]}"
        )
    cmd_log = " ".join(ffmpeg_cmd)

    try:
        # --- Collect frame/audio output ---
        unique_id = str(kwargs.get("unique_id", ""))
        hidden_prompt = kwargs.get("hidden_prompt") or {}
        images_tensor, audio_out = collect_frame_output(
            media_converter=media_converter,
            output_path=output_path,
            unique_id=unique_id,
            hidden_prompt=hidden_prompt,
            removes_audio=True,
        )

        # --- Build analysis string ---
        analysis = (
            f"NormalCrafter Mode (no LLM)\n"
            f"Temporally consistent video surface normals\n"
            f"Max resolution: {normalcrafter_max_res}\n"
            f"Window size: {normalcrafter_window_size}\n"
            f"Seed: {normalcrafter_seed}\n\n"
            f"Source: {effective_video_path}\n"
            f"NormalCrafter output: {nc_output}\n"
            f"Output: {output_path}"
        )

        return (images_tensor, audio_out, output_path, cmd_log, analysis, "")
    finally:
        # --- Cleanup temp files (always runs, even on error) ---
        for tmp_path in [temp_video_from_images, temp_video_with_audio]:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
        # Clean up NormalCrafter temp output
        if nc_output and os.path.exists(nc_output):
            try:
                os.remove(nc_output)
            except OSError:
                pass
        if not save_output and temp_render_dir and os.path.isdir(temp_render_dir):
            if not os.listdir(temp_render_dir):
                shutil.rmtree(temp_render_dir, ignore_errors=True)


async def process_video_depth_only(
    # dependencies
    media_converter,
    # parameters
    effective_video_path: str,
    video_metadata,
    save_output: bool,
    output_path: str,
    preview_mode: bool,
    quality_preset: str,
    crf: int,
    encoding_preset: str,
    video_depth_encoder: str = "vits",
    video_depth_colormap: str = "gray",
    temp_video_from_images: Optional[str] = None,
    temp_video_with_audio: Optional[str] = None,
    **kwargs,
) -> tuple[torch.Tensor, dict, str, str, str, str]:
    """Run Video Depth Anything directly without any LLM involvement.

    Produces temporally-consistent depth videos using native temporal
    attention layers.

    Returns:
        Standard 6-tuple: (images_tensor, audio_dict, output_path,
                          ffmpeg_log, analysis_text, error_text)
    """
    import shutil

    vda_output = None
    temp_render_dir = None
    try:
        if not effective_video_path or not os.path.isfile(effective_video_path):
            raise RuntimeError("No valid video provided for depth estimation")

        # Import synthesizer
        try:
            from ..core.vda_synthesizer import run_video_depth
        except ImportError:
            from core.vda_synthesizer import run_video_depth

        logger.info("[VideoDepth] Running depth estimation (encoder=%s)", video_depth_encoder)

        vda_output = run_video_depth(
            input_path=effective_video_path,
            encoder=video_depth_encoder,
            colormap=video_depth_colormap,
        )

        if not vda_output or not os.path.isfile(vda_output):
            raise RuntimeError("Video Depth Anything produced no output")

        logger.info("[VideoDepth] Depth output: %s", vda_output)

        # VDA synthesizer already produces a properly encoded mp4,
        # so just copy it — no re-encode needed.
        temp_render_dir = tempfile.mkdtemp(prefix="ffmpega_vda_")
        final_video = os.path.join(temp_render_dir, "vda_depth.mp4")
        shutil.copy2(vda_output, final_video)
        cmd_log = f"cp {vda_output} {final_video}"

        # Copy to output path if saving
        if save_output and output_path:
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            shutil.copy2(final_video, output_path)
        else:
            output_path = final_video

        # --- Collect frame/audio output ---
        unique_id = str(kwargs.get("unique_id", ""))
        hidden_prompt = kwargs.get("hidden_prompt") or {}
        images_tensor, audio_out = collect_frame_output(
            media_converter=media_converter,
            output_path=output_path,
            unique_id=unique_id,
            hidden_prompt=hidden_prompt,
            removes_audio=True,
        )

        analysis = (
            f"Video Depth Anything — Temporal Depth Estimation\n"
            f"Encoder: {video_depth_encoder}\n"
            f"Colormap: {video_depth_colormap}\n"
            f"Input: {effective_video_path}\n"
            f"Output: {output_path}"
        )

        return (images_tensor, audio_out, output_path, cmd_log, analysis, "")
    finally:
        # Cleanup temp files
        for tmp_path in [temp_video_from_images, temp_video_with_audio]:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
        if vda_output and os.path.exists(vda_output):
            try:
                os.remove(vda_output)
            except OSError:
                pass
        if not save_output and temp_render_dir and os.path.isdir(temp_render_dir):
            if not os.listdir(temp_render_dir):
                shutil.rmtree(temp_render_dir, ignore_errors=True)


async def process_minimax_remover_only(
    # dependencies
    media_converter,
    # parameters
    prompt: str,
    effective_video_path: str,
    video_metadata,
    save_output: bool,
    output_path: str,
    preview_mode: bool,
    quality_preset: str,
    crf: int,
    encoding_preset: str,
    temp_video_from_images: Optional[str] = None,
    temp_video_with_audio: Optional[str] = None,
    **kwargs,
) -> tuple[torch.Tensor, dict, str, str, str, str]:
    """Run MiniMax-Remover directly without any LLM involvement.

    Auto-detects whether the input is a single image or a video and
    performs full-frame object removal.  The prompt is used as the SAM3
    text target to generate a mask, then MiniMax-Remover inpaints the
    masked region.

    When no prompt is provided, performs full-frame removal using the
    entire frame as a mask (useful for background replacement).

    Returns the standard 6-tuple:
        (images_tensor, audio, output_path, command_log, analysis, mask_overlay_path)
    """
    logger.info("MiniMax-Remover mode: prompt=%r", prompt)

    # --- Import MiniMax-Remover ---
    try:
        try:
            from ..core.minimax_remover import (
                remove_object as minimax_remove,
                cleanup as _mm_cleanup,
            )
        except ImportError:
            from core.minimax_remover import (  # type: ignore
                remove_object as minimax_remove,
                cleanup as _mm_cleanup,
            )
    except ImportError:
        raise RuntimeError(
            "MiniMax-Remover is not available. "
            "Ensure diffusers >= 0.33.0 is installed and "
            "core/minimax_remover.py exists."
        )

    # --- Build output path ---
    output_path, temp_render_dir = build_output_path(
        effective_video_path=effective_video_path,
        save_output=save_output,
        output_path=output_path,
        preview_mode=preview_mode,
    )

    # NOTE: VRAM is freed internally by minimax_remover.load_pipeline()
    # via _vram_utils.free_for_module() — no manual clearing needed here.

    # --- Generate mask with SAM3 (if prompt provided) ---
    mask_video_path = None
    mask_tmpdir = None  # track fallback mask temp dir for cleanup
    if prompt and prompt.strip():
        try:
            try:
                from ..core.sam3_masker import mask_video_subprocess as sam3_mask
            except ImportError:
                from core.sam3_masker import mask_video_subprocess as sam3_mask  # type: ignore
            logger.info("MiniMax-Remover: generating SAM3 mask for '%s'", prompt)
            mask_video_path = sam3_mask(
                video_path=effective_video_path,
                prompt=prompt,
            )
        except ImportError:
            logger.warning(
                "SAM3 not available — performing full-frame removal"
            )
        except Exception as e:
            logger.warning("SAM3 masking failed: %s — performing full-frame removal", e)

    # --- If no mask, create a full-white mask (full-frame removal) ---
    if mask_video_path is None or not os.path.isfile(mask_video_path):
        if not prompt or not prompt.strip():
            logger.warning(
                "MiniMax-Remover: no prompt provided — creating full-white mask. "
                "This will attempt to inpaint the ENTIRE frame, which may produce "
                "artifacts. Consider providing a text prompt to target specific objects."
            )
        import cv2
        import numpy as np

        cap = cv2.VideoCapture(effective_video_path)
        fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        n_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        cap.release()

        # Pad dimensions to even values so the mask matches the
        # pad=ceil(iw/2)*2:ceil(ih/2)*2 encoding used downstream,
        # preventing pixel misalignment with the source video.
        w = int(np.ceil(w / 2) * 2)
        h = int(np.ceil(h / 2) * 2)

        mask_tmpdir = tempfile.mkdtemp(prefix="ffmpega_mm_mask_")
        mask_video_path = os.path.join(mask_tmpdir, "mask.mp4")
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(mask_video_path, fourcc, fps, (w, h))
        white = np.full((h, w, 3), 255, dtype=np.uint8)
        for _ in range(max(1, n_frames)):
            writer.write(white)
        writer.release()

        # Re-encode with ffmpeg for proper MP4 container (mp4v can
        # produce files that ffmpeg/PIL decoders struggle with).
        _ffmpeg = _get_ffmpeg_bin()
        reencoded = mask_video_path + ".tmp.mp4"
        _re = subprocess.run(
            [_ffmpeg, "-y", "-i", mask_video_path,
             "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p",
             reencoded],
            capture_output=True,
        )
        if _re.returncode == 0 and os.path.isfile(reencoded):
            os.replace(reencoded, mask_video_path)
        else:
            # Clean up failed re-encode attempt
            try:
                os.remove(reencoded)
            except OSError:
                pass
            logger.warning("Mask re-encode failed (rc=%d), using mp4v original", _re.returncode)

        logger.info("MiniMax-Remover: created full-white mask (%dx%d, %d frames)", w, h, n_frames)

    removed_path = None
    try:
        removed_path = minimax_remove(
            video_path=effective_video_path,
            mask_video_path=mask_video_path,
            output_path=output_path,
        )
        output_path = removed_path

        # Re-encode for preview if needed
        if preview_mode:
            _ffmpeg = _get_ffmpeg_bin()
            effective_crf = crf if crf >= 0 else _CRF_MAP.get(quality_preset, 23)
            effective_preset = (
                encoding_preset if encoding_preset != "auto"
                else _PRESET_MAP.get(quality_preset, "medium")
            )
            preview_path = output_path + ".preview.mp4"
            ffmpeg_cmd = [
                _ffmpeg, "-y",
                "-i", output_path,
                "-vf", "scale=480:trunc(ow/a/2)*2",
                "-t", "10",
                "-c:v", "libx264",
                "-crf", str(effective_crf),
                "-preset", effective_preset,
                "-pix_fmt", "yuv420p",
                "-an",
                preview_path,
            ]
            proc = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
            if proc.returncode == 0:
                os.replace(preview_path, output_path)
            else:
                logger.warning(
                    "MiniMax-Remover preview downscale failed: %s",
                    proc.stderr[-300:],
                )

        cmd_log = f"minimax_remover remove_object → {output_path}"

    except Exception as e:
        logger.error("MiniMax-Remover mode failed: %s", e)
        try:
            _mm_cleanup()
        except Exception:
            pass
        raise RuntimeError(f"MiniMax-Remover removal failed: {e}") from e

    try:
        # --- Collect frame/audio output ---
        unique_id = str(kwargs.get("unique_id", ""))
        hidden_prompt = kwargs.get("hidden_prompt") or {}
        images_tensor, audio_out = collect_frame_output(
            media_converter=media_converter,
            output_path=output_path,
            unique_id=unique_id,
            hidden_prompt=hidden_prompt,
            removes_audio=True,
        )

        # --- Build analysis string ---
        analysis = (
            f"MiniMax-Remover Mode (no LLM)\n"
            f"Target: {prompt or '(full-frame removal)'}\n"
            f"Mask: {mask_video_path}\n\n"
            f"Source: {effective_video_path}\n"
            f"Output: {output_path}"
        )

        return (images_tensor, audio_out, output_path, cmd_log, analysis, "")
    finally:
        # --- Cleanup temp files (always runs, even on error) ---
        for tmp_path in [temp_video_from_images, temp_video_with_audio]:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
        # Clean up the fallback white-mask temp directory
        if mask_tmpdir and os.path.isdir(mask_tmpdir):
            shutil.rmtree(mask_tmpdir, ignore_errors=True)
        if not save_output and temp_render_dir and os.path.isdir(temp_render_dir):
            if not os.listdir(temp_render_dir):
                shutil.rmtree(temp_render_dir, ignore_errors=True)


async def process_flux_klein_only(
    # dependencies
    media_converter,
    # parameters
    prompt: str,
    effective_video_path: str,
    video_metadata,
    save_output: bool,
    output_path: str,
    preview_mode: bool,
    quality_preset: str,
    crf: int,
    encoding_preset: str,
    flux_smoothing: str = "none",
    image_a=None,
    _all_image_paths=None,
    temp_video_from_images: Optional[str] = None,
    temp_video_with_audio: Optional[str] = None,
    **kwargs,
) -> tuple[torch.Tensor, dict, str, str, str, str]:
    """Run FLUX Klein editing directly without any LLM involvement.

    Auto-detects whether the input is a single image or a video:
    - **Image**: calls ``edit_single_image()`` for a one-shot edit
    - **Video**: calls ``edit_video()`` in maskless (full-frame) mode,
      applying the prompt to every frame via Klein's reference conditioning

    The prompt is sent directly to FLUX Klein as the edit instruction.

    Returns the standard 6-tuple:
        (images_tensor, audio, output_path, command_log, analysis, mask_overlay_path)
    """
    logger.info("FLUX Klein mode: prompt=%r", prompt)

    flux_image_source = kwargs.get("flux_image_source", False)
    flux_klein_steps = kwargs.get("flux_klein_steps", 4)
    flux_klein_guidance = kwargs.get("flux_klein_guidance", 1.0)
    flux_klein_seed = kwargs.get("flux_klein_seed", 42)
    flux_klein_width = kwargs.get("flux_klein_width", 1024)
    flux_klein_height = kwargs.get("flux_klein_height", 1024)
    flux_klein_model = kwargs.get("flux_klein_model", "4b")

    if not prompt or not prompt.strip():
        raise RuntimeError(
            "FLUX Klein mode requires a prompt describing the desired edit. "
            "Enter your edit instruction in the prompt field (e.g. "
            "'a person wearing a chrome bodysuit')."
        )

    # --- Image-source mode: use first image input as source ---
    # When flux_image_source is on, the first connected image becomes
    # effective_video_path and the rest become references.
    _temp_source_image = None  # track for cleanup
    if flux_image_source:
        if image_a is not None:
            # Convert image_a tensor → temp PNG for use as source
            from PIL import Image as _PILImage
            import numpy as _np

            if hasattr(image_a, 'shape') and len(image_a.shape) == 4:
                arr = (image_a[0].cpu().numpy() * 255).clip(0, 255).astype(_np.uint8)
            elif hasattr(image_a, 'shape') and len(image_a.shape) == 3:
                arr = (image_a.cpu().numpy() * 255).clip(0, 255).astype(_np.uint8)
            else:
                arr = None

            if arr is not None:
                _temp_source_image = os.path.join(
                    tempfile.mkdtemp(prefix="fk_src_"), "source.png"
                )
                _PILImage.fromarray(arr).save(_temp_source_image)
                effective_video_path = _temp_source_image
                image_a = None  # consumed — don't also use as reference
                logger.info("FLUX Klein image-source mode: using image_a tensor as source → %s", _temp_source_image)
            else:
                logger.warning("FLUX Klein image-source mode: image_a has unexpected shape, falling back to video_path")
        elif _all_image_paths and os.path.isfile(_all_image_paths[0]):
            # Use image_path_a as source, rest as references
            effective_video_path = _all_image_paths[0]
            _all_image_paths = _all_image_paths[1:]
            logger.info("FLUX Klein image-source mode: using image_path_a as source → %s", effective_video_path)
        else:
            logger.warning(
                "FLUX Klein image-source mode is on but no image inputs connected. "
                "Falling back to video_path as source."
            )

    # --- Import FLUX Klein editor ---
    try:
        try:
            from ..core.flux_klein_editor import (
                edit_single_image,
                edit_video,
                cleanup as _fk_cleanup,
            )
        except ImportError:
            from core.flux_klein_editor import (  # type: ignore
                edit_single_image,
                edit_video,
                cleanup as _fk_cleanup,
            )
    except ImportError:
        raise RuntimeError(
            "FLUX Klein is not available. "
            "Ensure diffusers >= 0.32.0 is installed and "
            "core/flux_klein_editor.py exists."
        )

    # --- Build output path ---
    output_path, temp_render_dir = build_output_path(
        effective_video_path=effective_video_path,
        save_output=save_output,
        output_path=output_path,
        preview_mode=preview_mode,
    )

    # --- Detect image vs video ---
    ext = os.path.splitext(effective_video_path)[1].lower()
    is_image = ext in (".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".webp")

    # NOTE: VRAM is freed internally by flux_klein_editor when loading
    # the pipeline via _vram_utils.free_for_module() — no manual clearing
    # needed here.

    # --- Convert image_a tensor → PIL reference images ---
    reference_images = None
    if image_a is not None:
        from PIL import Image as _PILImage
        import numpy as _np
        reference_images = []
        if hasattr(image_a, 'shape') and len(image_a.shape) == 4:
            # Batch of images (B, H, W, C) — ComfyUI IMAGE tensor
            for idx in range(image_a.shape[0]):
                arr = (image_a[idx].cpu().numpy() * 255).clip(0, 255).astype(_np.uint8)
                reference_images.append(_PILImage.fromarray(arr))
        elif hasattr(image_a, 'shape') and len(image_a.shape) == 3:
            # Single image (H, W, C)
            arr = (image_a.cpu().numpy() * 255).clip(0, 255).astype(_np.uint8)
            reference_images.append(_PILImage.fromarray(arr))
        if not reference_images:
            reference_images = None
        else:
            logger.info("FLUX Klein: using %d reference image(s) from image_a", len(reference_images))

    # --- Load image_path_a / image_path_b / ... as PIL references ---
    if _all_image_paths:
        from PIL import Image as _PILImage
        if reference_images is None:
            reference_images = []
        for img_path in _all_image_paths:
            if os.path.isfile(img_path):
                reference_images.append(_PILImage.open(img_path).convert("RGB"))
                logger.info("FLUX Klein: loaded reference image from %s", img_path)
        if not reference_images:
            reference_images = None

    edited_path = None
    try:
        if is_image:
            # Single-image edit
            logger.info("FLUX Klein: single-image mode")
            img_output = os.path.splitext(output_path)[0] + ".png"
            edited_path = edit_single_image(
                image_path=effective_video_path,
                prompt=prompt,
                output_path=img_output,
                seed=flux_klein_seed,
                reference_images=reference_images,
                num_steps=flux_klein_steps,
                guidance_scale=flux_klein_guidance,
                width=flux_klein_width,
                height=flux_klein_height,
                model=flux_klein_model,
            )
            output_path = edited_path
            cmd_log = f"flux_klein edit_single_image → {output_path}"
        else:
            # Video edit — full-frame (no mask)
            logger.info("FLUX Klein: full-frame video mode (no mask)")
            edited_path = edit_video(
                video_path=effective_video_path,
                mask_video_path=None,
                prompt=prompt,
                output_path=output_path,
                mode="edit",
                smoothing=flux_smoothing,
                reference_images=reference_images,
                seed=flux_klein_seed,
                num_steps=flux_klein_steps,
                guidance_scale=flux_klein_guidance,
                width=flux_klein_width,
                height=flux_klein_height,
                model=flux_klein_model,
            )
            output_path = edited_path

            # Re-encode for preview if needed
            if preview_mode:
                _ffmpeg = _get_ffmpeg_bin()
                effective_crf = crf if crf >= 0 else _CRF_MAP.get(quality_preset, 23)
                effective_preset = (
                    encoding_preset if encoding_preset != "auto"
                    else _PRESET_MAP.get(quality_preset, "medium")
                )
                preview_path = output_path + ".preview.mp4"
                ffmpeg_cmd = [
                    _ffmpeg, "-y",
                    "-i", output_path,
                    "-vf", "scale=480:trunc(ow/a/2)*2",
                    "-t", "10",
                    "-c:v", "libx264",
                    "-crf", str(effective_crf),
                    "-preset", effective_preset,
                    "-pix_fmt", "yuv420p",
                    "-an",
                    preview_path,
                ]
                proc = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
                if proc.returncode == 0:
                    os.replace(preview_path, output_path)
                else:
                    logger.warning(
                        "FLUX Klein preview downscale failed: %s",
                        proc.stderr[-300:],
                    )

            cmd_log = f"flux_klein edit_video (maskless) → {output_path}"

    except Exception as e:
        logger.error("FLUX Klein mode failed: %s", e)
        try:
            _fk_cleanup()
        except Exception:
            pass
        raise RuntimeError(f"FLUX Klein editing failed: {e}") from e

    try:
        # --- Collect frame/audio output ---
        unique_id = str(kwargs.get("unique_id", ""))
        hidden_prompt = kwargs.get("hidden_prompt") or {}
        images_tensor, audio_out = collect_frame_output(
            media_converter=media_converter,
            output_path=output_path,
            unique_id=unique_id,
            hidden_prompt=hidden_prompt,
            removes_audio=True,
        )

        # --- Build analysis string ---
        input_type = "Image" if is_image else "Video"
        analysis = (
            f"FLUX Klein Mode (no LLM)\n"
            f"Input type: {input_type}\n"
            f"Prompt: {prompt}\n"
            f"Mask: none (full-frame edit)\n"
            f"Smoothing: {flux_smoothing}\n\n"
            f"Source: {effective_video_path}\n"
            f"Output: {output_path}"
        )

        return (images_tensor, audio_out, output_path, cmd_log, analysis, "")
    finally:
        # --- Cleanup temp files (always runs, even on error) ---
        for tmp_path in [temp_video_from_images, temp_video_with_audio, _temp_source_image]:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
        # Clean up temp source image directory
        if _temp_source_image:
            _src_dir = os.path.dirname(_temp_source_image)
            if _src_dir and os.path.isdir(_src_dir):
                shutil.rmtree(_src_dir, ignore_errors=True)
        if not save_output and temp_render_dir and os.path.isdir(temp_render_dir):
            if not os.listdir(temp_render_dir):
                shutil.rmtree(temp_render_dir, ignore_errors=True)

async def process_kiwi_edit_only(
    # dependencies
    media_converter,
    # parameters
    prompt: str,
    effective_video_path: str,
    video_metadata,
    save_output: bool,
    output_path: str,
    preview_mode: bool,
    quality_preset: str,
    crf: int,
    encoding_preset: str,
    image_a=None,
    _all_image_paths=None,
    temp_video_from_images: Optional[str] = None,
    temp_video_with_audio: Optional[str] = None,
    **kwargs,
) -> tuple[torch.Tensor, dict, str, str, str, str]:
    """Run Kiwi-Edit video editing directly without any LLM involvement.

    Auto-detects model variant based on available inputs:
    - Prompt only → instruct-only
    - Reference image only → reference-only
    - Both → instruct-reference

    The prompt is sent directly to Kiwi-Edit as the edit instruction.
    Reference images come from image_a input or image_path_a/b/c.

    Returns the standard 6-tuple:
        (images_tensor, audio, output_path, command_log, analysis, mask_overlay_path)
    """
    logger.info("Kiwi-Edit mode: prompt=%r", prompt)

    kiwi_model = kwargs.get("kiwi_model", "auto")
    kiwi_precision = kwargs.get("kiwi_precision", "auto")
    kiwi_resolution = kwargs.get("kiwi_resolution", "640")
    kiwi_width = kwargs.get("kiwi_width", 640)
    kiwi_height = kwargs.get("kiwi_height", 640)
    kiwi_max_frames = kwargs.get("kiwi_max_frames", 0)
    if int(kiwi_max_frames) <= 0:
        # Auto: match input video frame count
        input_frames = None
        if video_metadata and video_metadata.primary_video:
            input_frames = video_metadata.primary_video.nb_frames
        if input_frames and input_frames > 0:
            kiwi_max_frames = min(input_frames, 161)  # Cap at model max
            logger.info("Kiwi-Edit auto max_frames=%d (from input video)", kiwi_max_frames)
        else:
            kiwi_max_frames = 81  # Fallback default
            logger.info("Kiwi-Edit auto max_frames=%d (fallback, no frame count in metadata)", kiwi_max_frames)
    kiwi_steps = kwargs.get("kiwi_steps", 50)
    kiwi_guidance = kwargs.get("kiwi_guidance", 5.0)
    kiwi_block_swap = kwargs.get("kiwi_block_swap", 0)
    kiwi_long_video = kwargs.get("kiwi_long_video", False)
    kiwi_seed = kwargs.get("kiwi_seed", 0)
    kiwi_flow_shift = kwargs.get("kiwi_flow_shift", 5.0)
    kiwi_task_type = kwargs.get("kiwi_task_type", "auto")
    kiwi_scheduler = kwargs.get("kiwi_scheduler", "unipc")


    # --- Import Kiwi-Edit synthesizer ---
    try:
        try:
            from ..core.kiwi_edit_synthesizer import (
                edit_video as _kiwi_edit,
                cleanup as _kiwi_cleanup,
                auto_select_variant,
            )
        except ImportError:
            from core.kiwi_edit_synthesizer import (  # type: ignore
                edit_video as _kiwi_edit,
                cleanup as _kiwi_cleanup,
                auto_select_variant,
            )
    except ImportError:
        raise RuntimeError(
            "Kiwi-Edit is not available. "
            "Ensure diffusers >= 0.32.0 is installed and "
            "core/kiwi_edit_synthesizer.py exists."
        )

    # --- Build output path ---
    output_path, temp_render_dir = build_output_path(
        effective_video_path=effective_video_path,
        save_output=save_output,
        output_path=output_path,
        preview_mode=preview_mode,
    )

    if not effective_video_path or not os.path.isfile(effective_video_path):
        raise RuntimeError("No valid video provided for Kiwi-Edit")

    # --- Convert image_a tensor → PIL reference images ---
    reference_images = None
    if image_a is not None:
        from PIL import Image as _PILImage
        import numpy as _np
        reference_images = []
        if hasattr(image_a, 'shape') and len(image_a.shape) == 4:
            for idx in range(image_a.shape[0]):
                arr = (image_a[idx].cpu().numpy() * 255).clip(0, 255).astype(_np.uint8)
                reference_images.append(_PILImage.fromarray(arr))
        elif hasattr(image_a, 'shape') and len(image_a.shape) == 3:
            arr = (image_a.cpu().numpy() * 255).clip(0, 255).astype(_np.uint8)
            reference_images.append(_PILImage.fromarray(arr))
        if not reference_images:
            reference_images = None
        else:
            logger.info("Kiwi-Edit: using %d reference image(s) from image_a", len(reference_images))

    # --- Load image_path_a / image_path_b / ... as PIL references ---
    ref_image_paths = None
    if _all_image_paths:
        ref_image_paths = [p for p in _all_image_paths if os.path.isfile(p)]
        if ref_image_paths:
            logger.info("Kiwi-Edit: %d reference image path(s)", len(ref_image_paths))

    # --- Determine variant for analysis ---
    variant = auto_select_variant(prompt, reference_images or [], kiwi_model)

    edited_path = None
    try:
        edited_path = _kiwi_edit(
            video_path=effective_video_path,
            prompt=prompt if prompt and prompt.strip() else None,
            ref_image_paths=ref_image_paths,
            ref_images_pil=reference_images,
            output_path=output_path,
            model_variant=kiwi_model,
            resolution_preset=kiwi_resolution,
            custom_width=int(kiwi_width),
            custom_height=int(kiwi_height),
            max_frames=int(kiwi_max_frames),
            steps=int(kiwi_steps),
            guidance_scale=float(kiwi_guidance),
            seed=int(kiwi_seed),
            precision=kiwi_precision,
            long_video=bool(kiwi_long_video),
            block_swap_blocks=int(kiwi_block_swap),
            flow_shift=float(kiwi_flow_shift),
            task_type=str(kiwi_task_type),
            scheduler=str(kiwi_scheduler),
        )
        output_path = edited_path

        # Re-encode for preview if needed
        if preview_mode:
            _ffmpeg = _get_ffmpeg_bin()
            effective_crf = crf if crf >= 0 else _CRF_MAP.get(quality_preset, 23)
            effective_preset = (
                encoding_preset if encoding_preset != "auto"
                else _PRESET_MAP.get(quality_preset, "medium")
            )
            preview_path = output_path + ".preview.mp4"
            ffmpeg_cmd = [
                _ffmpeg, "-y",
                "-i", output_path,
                "-vf", "scale=480:trunc(ow/a/2)*2",
                "-t", "10",
                "-c:v", "libx264",
                "-crf", str(effective_crf),
                "-preset", effective_preset,
                "-pix_fmt", "yuv420p",
                "-an",
                preview_path,
            ]
            proc = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
            if proc.returncode == 0:
                os.replace(preview_path, output_path)
            else:
                logger.warning(
                    "Kiwi-Edit preview downscale failed: %s",
                    proc.stderr[-300:],
                )

        cmd_log = f"kiwi_edit edit_video ({variant}) → {output_path}"

    except Exception as e:
        logger.error("Kiwi-Edit mode failed: %s", e)
        try:
            _kiwi_cleanup()
        except Exception:
            pass
        raise RuntimeError(f"Kiwi-Edit editing failed: {e}") from e

    try:
        # --- Collect frame/audio output ---
        unique_id = str(kwargs.get("unique_id", ""))
        hidden_prompt = kwargs.get("hidden_prompt") or {}
        images_tensor, audio_out = collect_frame_output(
            media_converter=media_converter,
            output_path=output_path,
            unique_id=unique_id,
            hidden_prompt=hidden_prompt,
            removes_audio=True,
        )

        # --- Build analysis string ---
        has_prompt = bool(prompt and prompt.strip())
        has_ref = bool(reference_images or ref_image_paths)
        analysis = (
            f"Kiwi-Edit Mode (no LLM)\n"
            f"Model variant: {variant}\n"
            f"Precision: {kiwi_precision}\n"
            f"Resolution: {kiwi_resolution}\n"
            f"Max frames: {kiwi_max_frames}\n"
            f"Steps: {kiwi_steps}\n"
            f"Guidance: {kiwi_guidance}\n"
            f"Seed: {kiwi_seed}\n"
            f"Flow shift: {kiwi_flow_shift}\n"
            f"Task type: {kiwi_task_type}\n"
            f"Scheduler: {kiwi_scheduler}\n"

            f"Long video: {kiwi_long_video}\n"
            f"Prompt: {prompt or '(none)'}\n"
            f"Reference images: {'yes' if has_ref else 'no'}\n\n"
            f"Source: {effective_video_path}\n"
            f"Output: {output_path}"
        )

        return (images_tensor, audio_out, output_path, cmd_log, analysis, "")
    finally:
        # --- Cleanup temp files (always runs, even on error) ---
        for tmp_path in [temp_video_from_images, temp_video_with_audio]:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
        if not save_output and temp_render_dir and os.path.isdir(temp_render_dir):
            if not os.listdir(temp_render_dir):
                shutil.rmtree(temp_render_dir, ignore_errors=True)


async def process_dreamid_omni_only(
    # parameters
    prompt: str,
    effective_video_path: str,
    video_metadata,
    save_output: bool,
    output_path: str,
    preview_mode: bool,
    quality_preset: str,
    crf: int,
    encoding_preset: str,
    image_a=None,
    audio_a=None,
    temp_video_from_images: Optional[str] = None,
    temp_video_with_audio: Optional[str] = None,
    **kwargs,
) -> tuple[torch.Tensor, dict, str, str, str, str]:
    """Run DreamID-Omni identity-preserving talking-head video generation without LLM.

    Requires face image(s) on image_a and reference audio on audio_a.
    The prompt describes the scene/action for the generated video.

    Returns the standard 6-tuple:
        (images_tensor, audio, output_path, command_log, analysis, mask_overlay_path)
    """
    logger.info("DreamID-Omni mode: prompt=%r", prompt)

    # --- Extract DreamID parameters from kwargs ---
    dreamid_resolution = kwargs.get("dreamid_resolution", "auto")
    dreamid_precision = kwargs.get("dreamid_precision", "auto")
    dreamid_steps = int(kwargs.get("dreamid_steps", 50))
    dreamid_seed = int(kwargs.get("dreamid_seed", 100))
    dreamid_solver = kwargs.get("dreamid_solver", "unipc")
    dreamid_video_cfg = float(kwargs.get("dreamid_video_cfg", 3.0))
    dreamid_video_ref_cfg = float(kwargs.get("dreamid_video_ref_cfg", 1.5))
    dreamid_audio_cfg = float(kwargs.get("dreamid_audio_cfg", 4.0))
    dreamid_audio_ref_cfg = float(kwargs.get("dreamid_audio_ref_cfg", 2.0))

    # --- Import DreamID-Omni synthesizer ---
    try:
        try:
            from ..core.dreamid_omni_synthesizer import (
                generate_video as _dreamid_generate,
                cleanup as _dreamid_cleanup,
                _audio_dict_to_wav,
                _tensor_to_image,
            )
        except ImportError:
            from core.dreamid_omni_synthesizer import (  # type: ignore
                generate_video as _dreamid_generate,
                cleanup as _dreamid_cleanup,
                _audio_dict_to_wav,
                _tensor_to_image,
            )
    except ImportError:
        raise RuntimeError(
            "DreamID-Omni is not available. "
            "Ensure core/dreamid_omni_synthesizer.py "
            "and core/dreamid_omni/ exist."
        )

    # --- Validate inputs ---
    if image_a is None:
        raise RuntimeError(
            "DreamID-Omni requires at least one face reference image. "
            "Connect a face image to image_a."
        )
    if audio_a is None:
        raise RuntimeError(
            "DreamID-Omni requires reference audio. "
            "Connect an audio clip to audio_a."
        )

    # --- Build output path ---
    output_path, temp_render_dir = build_output_path(
        effective_video_path=effective_video_path,
        save_output=save_output,
        output_path=output_path,
        preview_mode=preview_mode,
    )

    # --- Convert image_a tensor → temp PNG files ---
    import numpy as _np
    face_image_paths = []
    temp_files = []
    try:
        if hasattr(image_a, 'shape') and len(image_a.shape) == 4:
            # Batch: [B, H, W, C]
            for idx in range(min(image_a.shape[0], 2)):  # Max 2 faces
                tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
                tmp.close()
                _tensor_to_image(image_a[idx], tmp.name)
                face_image_paths.append(tmp.name)
                temp_files.append(tmp.name)
        elif hasattr(image_a, 'shape') and len(image_a.shape) == 3:
            # Single: [H, W, C]
            tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
            tmp.close()
            _tensor_to_image(image_a, tmp.name)
            face_image_paths.append(tmp.name)
            temp_files.append(tmp.name)

        if not face_image_paths:
            raise RuntimeError("Could not extract face images from image_a tensor")

        logger.info("DreamID-Omni: %d face image(s) extracted", len(face_image_paths))

        # --- Convert audio_a AUDIO dict → temp WAV ---
        audio_wav = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        audio_wav.close()
        _audio_dict_to_wav(audio_a, audio_wav.name)
        audio_paths = [audio_wav.name]
        temp_files.append(audio_wav.name)
        logger.info("DreamID-Omni: audio extracted to %s", audio_wav.name)

        # --- Generate ---
        generated_path = _dreamid_generate(
            prompt=prompt or "",
            face_image_paths=face_image_paths,
            audio_paths=audio_paths,
            output_path=output_path,
            resolution_preset=dreamid_resolution,
            seed=dreamid_seed,
            steps=dreamid_steps,
            solver_name=dreamid_solver,
            shift=5.0,
            video_cfg_scale=dreamid_video_cfg,
            video_ref_cfg_scale=dreamid_video_ref_cfg,
            audio_cfg_scale=dreamid_audio_cfg,
            audio_ref_cfg_scale=dreamid_audio_ref_cfg,
            precision=dreamid_precision,
        )
        output_path = generated_path

        cmd_log = f"dreamid_omni generate_video → {output_path}"

    except Exception as e:
        logger.error("DreamID-Omni mode failed: %s", e)
        try:
            _dreamid_cleanup()
        except Exception:
            pass
        raise RuntimeError(f"DreamID-Omni generation failed: {e}") from e

    finally:
        # Clean up temp face/audio files
        for fp in temp_files:
            try:
                if os.path.exists(fp):
                    os.remove(fp)
            except OSError:
                pass

    try:
        # --- Collect frame/audio output ---
        try:
            try:
                from ..core.media_converter import MediaConverter
            except ImportError:
                from core.media_converter import MediaConverter  # type: ignore
            media_converter = MediaConverter()
        except Exception:
            media_converter = None

        unique_id = str(kwargs.get("unique_id", ""))
        hidden_prompt = kwargs.get("hidden_prompt") or {}
        images_tensor, audio_out = collect_frame_output(
            media_converter=media_converter,
            output_path=output_path,
            unique_id=unique_id,
            hidden_prompt=hidden_prompt,
            removes_audio=False,
        )

        # --- Build analysis string ---
        analysis = (
            f"⚠️ DreamID-Omni Mode (WIP / Experimental)\n"
            f"Resolution: {dreamid_resolution}\n"
            f"Steps: {dreamid_steps}\n"
            f"Seed: {dreamid_seed}\n"
            f"Solver: {dreamid_solver}\n"
            f"Video CFG: {dreamid_video_cfg}\n"
            f"Video Ref CFG: {dreamid_video_ref_cfg}\n"
            f"Audio CFG: {dreamid_audio_cfg}\n"
            f"Audio Ref CFG: {dreamid_audio_ref_cfg}\n"
            f"Faces: {len(face_image_paths)}\n"
            f"Prompt: {prompt or '(none)'}\n\n"
            f"Output: {output_path}"
        )

        return (images_tensor, audio_out, output_path, cmd_log, analysis, "")
    finally:
        # --- Cleanup temp files (always runs, even on error) ---
        for tmp_path in [temp_video_from_images, temp_video_with_audio]:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
        if not save_output and temp_render_dir and os.path.isdir(temp_render_dir):
            if not os.listdir(temp_render_dir):
                shutil.rmtree(temp_render_dir, ignore_errors=True)


async def process_ai_upscale_only(
    # dependencies
    media_converter,
    # parameters
    effective_video_path: str,
    video_metadata,
    save_output: bool,
    output_path: str,
    preview_mode: bool,
    quality_preset: str,
    crf: int,
    encoding_preset: str,
    upscale_model: str = "realesrgan_x4plus",
    upscale_scale: int = 4,
    tile_size: int = 512,
    blockswap_blocks: int = 0,
    seedvr_resolution: int = 1080,
    rtx_quality: str = "ULTRA",
    vae_tiling: bool = True,
    vae_tile_preset: str = "auto",
    vae_tile_size: int = 512,
    vae_tile_overlap: int = 64,
    flashvsr_processing: str = "whole",
    flashvsr_frame_window: int = 0,
    flashvsr_color_fix: bool = True,
    flashvsr_decode_tile: int = 512,
    temp_video_from_images: Optional[str] = None,
    temp_video_with_audio: Optional[str] = None,
    **kwargs,
) -> tuple[torch.Tensor, dict, str, str, str, str]:
    """Run AI upscaling directly without any LLM involvement.

    Upscales images and videos using Real-ESRGAN, HAT, DAT, or SwinIR
    via spandrel.

    Returns:
        Standard 6-tuple: (images_tensor, audio_dict, output_path,
                          ffmpeg_log, analysis_text, error_text)
    """
    import shutil

    upscale_output = None
    temp_render_dir = None
    _SEEDVR_MODELS = {"seedvr2_3b_fp8", "seedvr2_3b_gguf", "seedvr2_7b_fp8", "seedvr2_7b_fp8_mixed", "seedvr2_7b_gguf"}
    _FLASHVSR_MODELS = {"flashvsr_full", "flashvsr_tiny", "flashvsr_tiny_long"}

    # --- Build output path (same pattern as flux_klein and other no-LLM modes) ---
    output_path, temp_render_dir = build_output_path(
        effective_video_path=effective_video_path,
        save_output=save_output,
        output_path=output_path,
        preview_mode=preview_mode,
    )

    try:
        if not effective_video_path or not os.path.isfile(effective_video_path):
            raise RuntimeError("No valid input provided for AI upscaling")

        # Determine if input is video or image
        ext = os.path.splitext(effective_video_path)[1].lower()
        _video_exts = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".flv", ".wmv"}
        is_video = ext in _video_exts

        # Image source -> image output: switch the output extension so the file
        # is saved as an image and the Agent's image_path output (which only
        # forwards image-extension paths) picks it up. (build_output_path always
        # emits .mp4.)
        if not is_video:
            _img_out_ext = ext if ext in (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff", ".tif") else ".png"
            output_path = os.path.splitext(output_path)[0] + _img_out_ext

        # Normalize VAE tiling request for diffusion upscalers (SeedVR2 / FlashVSR).
        # _tile_sz / _tile_ov are None for "auto" (let the model decide its own defaults).
        if not vae_tiling:
            _tile_on, _tile_sz, _tile_ov = False, None, None
        elif vae_tile_preset == "auto":
            _tile_on, _tile_sz, _tile_ov = True, None, None
        elif vae_tile_preset == "custom":
            _tile_on, _tile_sz, _tile_ov = True, int(vae_tile_size), int(vae_tile_overlap)
        else:  # numeric preset, e.g. "512"
            _tile_sz = int(vae_tile_preset)
            _tile_on, _tile_ov = True, max(0, _tile_sz // 8)

        # Import the appropriate synthesizer
        if upscale_model in _FLASHVSR_MODELS:
            try:
                from ..core.flashvsr_synthesizer import upscale_image, upscale_video
            except ImportError:
                from core.flashvsr_synthesizer import upscale_image, upscale_video  # type: ignore

            logger.info("[AIUpscale] FlashVSR upscaling with model=%s, is_video=%s",
                        upscale_model, is_video)

            if is_video:
                # processing selects how activation/decode memory is bounded:
                #   whole    → one whole-frame pass (best quality; tiny_long streams
                #              over time internally).
                #   temporal → sliding frame-window (no spatial tiling); manual
                #              frame_window bounds memory for full/tiny.
                #   spatial  → per-tile (opt-in; lowest quality). Uses the chosen
                #              VAE tile size when set.
                _fv_proc = str(flashvsr_processing or "whole").lower()
                _flashvsr_kwargs = {
                    "processing": _fv_proc,
                    "frame_window": int(flashvsr_frame_window),
                    "block_swap_blocks": blockswap_blocks,
                    "color_fix": bool(flashvsr_color_fix),
                    "decode_tile": int(flashvsr_decode_tile),
                }
                if _fv_proc == "spatial" and _tile_sz is not None:
                    _flashvsr_kwargs["tile_size"] = _tile_sz
                    _flashvsr_kwargs["tile_overlap"] = _tile_ov
                upscale_output = upscale_video(
                    input_path=effective_video_path,
                    model_name=upscale_model,
                    scale=upscale_scale,
                    **_flashvsr_kwargs,
                )
            else:
                upscale_output = upscale_image(
                    input_path=effective_video_path,
                    model_name=upscale_model,
                    scale=upscale_scale,
                    block_swap_blocks=blockswap_blocks,
                    color_fix=bool(flashvsr_color_fix),
                    decode_tile=int(flashvsr_decode_tile),
                )
        elif upscale_model in _SEEDVR_MODELS:
            try:
                from ..core.seedvr_synthesizer import upscale_image, upscale_video
            except ImportError:
                from core.seedvr_synthesizer import upscale_image, upscale_video  # type: ignore

            logger.info("[AIUpscale] SeedVR2 upscaling with model=%s, is_video=%s",
                        upscale_model, is_video)

            if is_video:
                upscale_output = upscale_video(
                    input_path=effective_video_path,
                    model_name=upscale_model,
                    resolution=seedvr_resolution,
                    blockswap_blocks=blockswap_blocks,
                    vae_tiling=_tile_on,
                    vae_tile_size=_tile_sz,
                    vae_tile_overlap=_tile_ov,
                )
            else:
                upscale_output = upscale_image(
                    input_path=effective_video_path,
                    model_name=upscale_model,
                    resolution=seedvr_resolution,
                    blockswap_blocks=blockswap_blocks,
                    vae_tiling=_tile_on,
                    vae_tile_size=_tile_sz,
                    vae_tile_overlap=_tile_ov,
                )
        elif upscale_model == "rtx_vsr":
            try:
                from ..core.rtx_vsr_synthesizer import upscale_image, upscale_video
            except ImportError:
                from core.rtx_vsr_synthesizer import upscale_image, upscale_video  # type: ignore

            logger.info("[AIUpscale] RTX VSR upscaling (quality=%s, scale=%dx, is_video=%s)",
                        rtx_quality, upscale_scale, is_video)

            if is_video:
                upscale_output = upscale_video(
                    input_path=effective_video_path,
                    scale=upscale_scale,
                    quality=rtx_quality,
                )
            else:
                upscale_output = upscale_image(
                    input_path=effective_video_path,
                    scale=upscale_scale,
                    quality=rtx_quality,
                )
        else:
            try:
                from ..core.upscaler import upscale_image, upscale_video
            except ImportError:
                from core.upscaler import upscale_image, upscale_video  # type: ignore

            logger.info("[AIUpscale] Upscaling with model=%s, scale=%dx, is_video=%s",
                        upscale_model, upscale_scale, is_video)

            if is_video:
                upscale_output = upscale_video(
                    input_path=effective_video_path,
                    model_name=upscale_model,
                    scale_factor=upscale_scale,
                    tile_size=tile_size,
                )
            else:
                upscale_output = upscale_image(
                    input_path=effective_video_path,
                    model_name=upscale_model,
                    scale_factor=upscale_scale,
                    tile_size=tile_size,
                )

        if not upscale_output or not os.path.isfile(upscale_output):
            raise RuntimeError("AI upscaler produced no output")

        logger.info("[AIUpscale] Upscale output: %s", upscale_output)

        # Always save upscale output to the ComfyUI output folder.
        # Upscaling is expensive — the result should always be persisted.
        if not save_output or not output_path:
            # Force an output path even if save_output was False
            import folder_paths  # type: ignore[import-not-found]
            out_dir = folder_paths.get_output_directory()
            stem = os.path.splitext(os.path.basename(effective_video_path))[0]
            _forced_ext = ".mp4" if is_video else (os.path.splitext(output_path)[1] or ".png")
            output_path = os.path.join(out_dir, f"{stem}_upscaled{_forced_ext}")
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        shutil.copy2(upscale_output, output_path)
        cmd_log = f"ai_upscale → {output_path}"
        logger.info("[AIUpscale] Saved to: %s", output_path)

        # --- Collect frame/audio output ---
        unique_id = str(kwargs.get("unique_id", ""))
        hidden_prompt = kwargs.get("hidden_prompt") or {}
        images_tensor, audio_out = collect_frame_output(
            media_converter=media_converter,
            output_path=output_path,
            unique_id=unique_id,
            hidden_prompt=hidden_prompt,
            removes_audio=not is_video,
        )

        analysis = (
            f"AI Upscale — Super-Resolution\n"
            f"Model: {upscale_model}\n"
            f"Scale: {upscale_scale}×\n"
            f"Input: {effective_video_path}\n"
            f"Output: {output_path}"
        )

        return (images_tensor, audio_out, output_path, cmd_log, analysis, "")
    finally:
        # Cleanup temp files
        for tmp_path in [temp_video_from_images, temp_video_with_audio]:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
        if upscale_output and os.path.exists(upscale_output):
            try:
                os.remove(upscale_output)
            except OSError:
                pass


# ====================================================================== #
#  Rembg background removal (no LLM)                                      #
# ====================================================================== #

async def process_rembg_only(
    # dependencies
    media_converter,
    # parameters
    effective_video_path: str,
    video_metadata,
    save_output: bool,
    output_path: str,
    preview_mode: bool,
    quality_preset: str,
    crf: int,
    encoding_preset: str,
    rembg_model: str = "bria-rmbg",
    rembg_background: str = "transparent",
    temp_video_from_images: Optional[str] = None,
    temp_video_with_audio: Optional[str] = None,
    _all_image_paths: Optional[list] = None,
    **kwargs,
) -> tuple[torch.Tensor, dict, str, str, str, str]:
    """Remove background from video/image using rembg without any LLM.

    For single images (detected by file extension or via ``_all_image_paths``),
    processes the single frame directly — outputting a PNG with alpha
    (transparent) or a composited PNG (solid background).

    For videos, uses the existing ``_f_remove_background`` skill handler to
    generate per-frame alpha masks and composite via FFmpeg filter_complex.

    Returns:
        Standard 6-tuple: (images_tensor, audio_dict, output_path,
                          ffmpeg_log, analysis_text, mask_overlay_path)
    """
    import asyncio

    logger.info("Rembg mode: model=%s, background=%s", rembg_model, rembg_background)

    is_transparent = rembg_background == "transparent"

    # --- Detect single-image input ---
    # Priority: _all_image_paths (from LoadImagePath) > file extension check
    _IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tiff", ".tif", ".gif"}
    source_image_paths: list[str] = []

    if _all_image_paths:
        source_image_paths = [p for p in _all_image_paths if os.path.isfile(p)]
    else:
        ext = os.path.splitext(effective_video_path)[1].lower()
        if ext in _IMAGE_EXTS and os.path.isfile(effective_video_path):
            source_image_paths = [effective_video_path]

    # ================================================================== #
    #  Image fast path — process N images directly, output PNGs           #
    # ================================================================== #
    if source_image_paths:
        n_images = len(source_image_paths)
        logger.info(
            "Rembg: image mode — processing %d image(s) (model=%s)",
            n_images, rembg_model,
        )

        # --- Build output path (based on first image) ---
        output_path, temp_render_dir = build_output_path(
            effective_video_path=source_image_paths[0],
            save_output=save_output,
            output_path=output_path,
            preview_mode=preview_mode,
        )
        # Force PNG output for images
        base, _ = os.path.splitext(output_path)
        output_path = base + ".png"

        try:
            from rembg import remove as rembg_remove, new_session
        except ImportError:
            raise RuntimeError(
                "rembg is not installed. Install with: "
                "pip install 'comfyui-ffmpega[masking]'"
            )

        try:
            from PIL import Image as PILImage
            import numpy as np

            # Create session once — reuse for all images
            session = new_session(rembg_model)

            bg_color_map = {
                "white": (255, 255, 255),
                "black": (0, 0, 0),
                "green": (0, 177, 64),
                "blue": (0, 0, 255),
                "red": (255, 0, 0),
                "gray": (128, 128, 128),
                "grey": (128, 128, 128),
            }

            image_tensors = []
            output_paths = []
            for idx, src_path in enumerate(source_image_paths):
                pil_img = PILImage.open(src_path).convert("RGB")

                # Run rembg — returns RGBA PIL image
                result_rgba = await asyncio.to_thread(
                    rembg_remove, pil_img, session=session,
                )

                # Build per-image output path
                if idx == 0:
                    img_output = output_path
                else:
                    img_output = f"{base}_{idx}.png"

                if is_transparent:
                    result_rgba.save(img_output, "PNG")
                else:
                    bg_rgb = bg_color_map.get(rembg_background, (0, 0, 0))
                    bg = PILImage.new("RGBA", result_rgba.size, bg_rgb + (255,))
                    composited = PILImage.alpha_composite(bg, result_rgba)
                    composited.convert("RGB").save(img_output, "PNG")

                output_paths.append(img_output)
                logger.info(
                    "Rembg: image %d/%d complete: %s", idx + 1, n_images, img_output,
                )

                # Build per-image tensor — for transparent PNGs,
                # composite onto white so the IMAGE preview looks correct.
                # (ComfyUI IMAGE type is RGB-only, alpha is always lost.)
                if is_transparent and result_rgba.mode == "RGBA":
                    white_bg = PILImage.new("RGBA", result_rgba.size, (255, 255, 255, 255))
                    preview = PILImage.alpha_composite(white_bg, result_rgba)
                    result_np = np.array(preview.convert("RGB"))
                else:
                    result_np = np.array(PILImage.open(img_output).convert("RGB"))
                image_tensors.append(
                    torch.from_numpy(result_np.astype(np.float32) / 255.0)
                )

            # Stack into batched IMAGE tensor (N, H, W, 3)
            if len(image_tensors) == 1:
                images_tensor = image_tensors[0].unsqueeze(0)
            else:
                # Resize all images to match the first image's dimensions
                target_h, target_w = image_tensors[0].shape[:2]
                resized = [image_tensors[0]]
                for t in image_tensors[1:]:
                    if t.shape[0] != target_h or t.shape[1] != target_w:
                        # Resize via PIL for quality (Lanczos)
                        t_np = (t.numpy() * 255).astype(np.uint8)
                        t_pil = PILImage.fromarray(t_np)
                        t_pil = t_pil.resize((target_w, target_h), PILImage.LANCZOS)
                        t_arr = np.array(t_pil).astype(np.float32) / 255.0
                        resized.append(torch.from_numpy(t_arr))
                    else:
                        resized.append(t)
                images_tensor = torch.stack(resized, dim=0)

            cmd_log = f"rembg {rembg_model} → {', '.join(output_paths)}"
            audio_out = {"waveform": torch.zeros(1, 1, 0), "sample_rate": 44100}

            input_list = "\n".join(f"  {p}" for p in source_image_paths)
            output_list = "\n".join(f"  {p}" for p in output_paths)
            analysis = (
                f"Rembg Background Removal ({n_images} Image{'s' if n_images > 1 else ''})\n"
                f"Model: {rembg_model}\n"
                f"Background: {rembg_background}\n"
                f"Inputs:\n{input_list}\n"
                f"Outputs:\n{output_list}"
            )

            return (images_tensor, audio_out, output_path, cmd_log, analysis, "")

        finally:
            # Cleanup temp files
            for tmp_path in [temp_video_from_images, temp_video_with_audio]:
                if tmp_path and os.path.exists(tmp_path):
                    try:
                        os.remove(tmp_path)
                    except OSError:
                        pass
            if not save_output and temp_render_dir and os.path.isdir(temp_render_dir):
                if not os.listdir(temp_render_dir):
                    shutil.rmtree(temp_render_dir, ignore_errors=True)

    # ================================================================== #
    #  Video path — per-frame mask + FFmpeg composite (existing logic)     #
    # ================================================================== #

    # --- Build output path ---
    output_path, temp_render_dir = build_output_path(
        effective_video_path=effective_video_path,
        save_output=save_output,
        output_path=output_path,
        preview_mode=preview_mode,
    )

    if is_transparent:
        base, _ = os.path.splitext(output_path)
        output_path = base + ".webm"

    mask_video_path = None
    try:
        # --- Import and call the remove_background handler ---
        try:
            from ..skills.handlers.visual import _f_remove_background
        except ImportError:
            from skills.handlers.visual import _f_remove_background  # type: ignore

        # Use a dedicated dict so we can read the mask path back reliably
        # without re-extracting from handler_params (reduces coupling).
        metadata_ref: dict = {}
        handler_params = {
            "model": rembg_model,
            "background": rembg_background,
            "_input_path": effective_video_path,
            "_metadata_ref": metadata_ref,
        }

        # Per-frame rembg inference is CPU/GPU-heavy — run in a thread
        # so the event loop stays responsive.
        result = await asyncio.to_thread(_f_remove_background, handler_params)

        # Extract mask path for cleanup (written by the handler into
        # our metadata_ref dict under "_mask_video_path").
        mask_video_path = metadata_ref.get("_mask_video_path")

        # HandlerResult is a dataclass, not a dict
        fc = result.filter_complex
        extra_opts = result.output_options

        if not fc:
            raise RuntimeError(
                "rembg handler returned no filter_complex — "
                "is rembg installed? (pip install 'comfyui-ffmpega[masking]')"
            )

        # --- Build FFmpeg command ---
        ffmpeg_bin = _get_ffmpeg_bin()

        effective_crf = crf if crf >= 0 else _CRF_MAP.get(quality_preset, 23)
        effective_preset = (
            encoding_preset if encoding_preset != "auto"
            else _PRESET_MAP.get(quality_preset, "medium")
        )

        cmd = [ffmpeg_bin, "-y", "-i", effective_video_path]

        if is_transparent:
            # VP9 with alpha — opts from handler already include codec flags
            cmd += ["-filter_complex", fc]
            cmd += extra_opts
            cmd += [output_path]
        else:
            # Solid background — standard H.264
            cmd += ["-filter_complex", fc]
            cmd += [
                "-c:v", "libx264",
                "-crf", str(effective_crf),
                "-preset", effective_preset,
                "-pix_fmt", "yuv420p",
            ]
            # Preserve audio if present
            has_audio = bool(
                video_metadata and video_metadata.get("audio_codec")
            )
            if has_audio:
                cmd += ["-c:a", "aac", "-b:a", "192k"]
            else:
                cmd += ["-an"]
            cmd += [output_path]

        logger.info("Rembg FFmpeg cmd: %s", " ".join(cmd))
        # Run FFmpeg in a thread to avoid blocking the event loop
        proc = await asyncio.to_thread(
            subprocess.run, cmd, capture_output=True, text=True,
        )
        cmd_log = proc.stdout + proc.stderr

        if proc.returncode != 0:
            raise RuntimeError(
                f"FFmpeg rembg render failed (exit {proc.returncode}):\n"
                f"{proc.stderr[-500:]}"
            )

        # --- Collect frame/audio output ---
        unique_id = str(kwargs.get("unique_id", ""))
        hidden_prompt = kwargs.get("hidden_prompt") or {}
        images_tensor, audio_out = collect_frame_output(
            media_converter=media_converter,
            output_path=output_path,
            unique_id=unique_id,
            hidden_prompt=hidden_prompt,
            removes_audio=is_transparent,
        )

        analysis = (
            f"Rembg Background Removal\n"
            f"Model: {rembg_model}\n"
            f"Background: {rembg_background}\n"
            f"Input: {effective_video_path}\n"
            f"Output: {output_path}"
        )

        return (images_tensor, audio_out, output_path, cmd_log, analysis, "")

    finally:
        # Cleanup temp files
        for tmp_path in [temp_video_from_images, temp_video_with_audio]:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
        if mask_video_path and os.path.exists(mask_video_path):
            try:
                os.remove(mask_video_path)
            except OSError:
                pass
        if not save_output and temp_render_dir and os.path.isdir(temp_render_dir):
            if not os.listdir(temp_render_dir):
                shutil.rmtree(temp_render_dir, ignore_errors=True)


async def process_onion_skin_only(
    # dependencies (injected from agent node)
    composer,
    process_manager,
    media_converter,
    # parameters
    effective_video_path: str,
    video_metadata,
    save_output: bool,
    output_path: str,
    preview_mode: bool,
    quality_preset: str,
    crf: int,
    encoding_preset: str,
    onion_blend_mode: str = "screen",
    onion_opacity: float = 0.5,
    onion_decay: float = 0.97,
    _all_video_paths: Optional[list] = None,
    temp_video_from_images: Optional[str] = None,
    temp_video_with_audio: Optional[str] = None,
    **kwargs,
) -> tuple[torch.Tensor, dict, str, str, str, str]:
    """Run Onion Skin effect directly without any LLM involvement.

    Auto-detects connected extra video inputs:
    - **Composite mode** (extra inputs): Blends extra videos onto the main
      video using ``filter_complex`` with FFmpeg ``blend`` filters.
    - **Temporal mode** (no extra inputs): Applies ghost-trail self-blend
      using the ``lagfun`` filter on a single video.

    Returns the standard 6-tuple:
        (images_tensor, audio, output_path, command_log, analysis, mask_overlay_path)
    """
    extra_videos = _all_video_paths or []
    has_extra = len(extra_videos) > 0
    mode_label = "composite" if has_extra else "temporal"

    logger.info(
        "Onion Skin mode: %s, blend_mode=%s, opacity=%.2f, decay=%.3f, extra_inputs=%d",
        mode_label, onion_blend_mode, onion_opacity, onion_decay, len(extra_videos),
    )

    # --- Validate blend mode ---
    _valid_modes = {
        "normal", "screen", "addition", "difference",
        "multiply", "overlay", "softlight",
    }
    if onion_blend_mode not in _valid_modes:
        onion_blend_mode = "screen"

    # --- Build output path ---
    output_path, temp_render_dir = build_output_path(
        effective_video_path=effective_video_path,
        save_output=save_output,
        output_path=output_path,
        preview_mode=preview_mode,
    )

    _ffmpeg = _get_ffmpeg_bin()
    effective_crf = crf if crf >= 0 else _CRF_MAP.get(quality_preset, 23)
    effective_preset = (
        encoding_preset if encoding_preset != "auto"
        else _PRESET_MAP.get(quality_preset, "medium")
    )

    if has_extra:
        # ── Composite mode: blend extra videos onto main ─────────────
        ffmpeg_cmd = [_ffmpeg, "-y", "-i", effective_video_path]
        for vp in extra_videos:
            ffmpeg_cmd.extend(["-i", vp])

        # Build filter_complex chain
        n_layers = len(extra_videos)
        fc_parts = []

        # Scale and prepare each overlay input to match main video
        for i in range(n_layers):
            idx = i + 1  # ffmpeg input index (0 = main)
            fc_parts.append(
                f"[{idx}:v]scale=iw:ih:force_original_aspect_ratio=decrease,"
                f"pad=iw:ih:(ow-iw)/2:(oh-ih)/2:black,setsar=1[_os{i}]"
            )

        # Chain blend operations with decaying opacity per layer
        prev = "[0:v]"
        for i in range(n_layers):
            layer_opacity = onion_opacity * (0.5 ** i) if n_layers > 1 else onion_opacity
            layer_opacity = max(0.01, min(1.0, layer_opacity))

            if i < n_layers - 1:
                out_label = f"[_osm{i}]"
                fc_parts.append(
                    f"{prev}[_os{i}]blend=all_mode={onion_blend_mode}"
                    f":all_opacity={layer_opacity:.3f}{out_label}"
                )
                prev = out_label
            else:
                fc_parts.append(
                    f"{prev}[_os{i}]blend=all_mode={onion_blend_mode}"
                    f":all_opacity={layer_opacity:.3f}[vout]"
                )

        filter_complex = ";".join(fc_parts)
        ffmpeg_cmd.extend(["-filter_complex", filter_complex])
        ffmpeg_cmd.extend(["-map", "[vout]"])

        # Copy audio from main input if present
        if video_metadata.primary_audio:
            ffmpeg_cmd.extend(["-map", "0:a?", "-c:a", "aac", "-b:a", "192k"])

        ffmpeg_cmd.extend([
            "-c:v", "libx264",
            "-crf", str(effective_crf),
            "-preset", effective_preset,
            "-pix_fmt", "yuv420p",
        ])

        if preview_mode:
            ffmpeg_cmd.extend(["-s", "480x270", "-t", "10"])

        ffmpeg_cmd.append(output_path)
        cmd_log = " ".join(ffmpeg_cmd)

        logger.debug("Onion Skin composite command: %s", cmd_log)
        proc = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(
                f"Onion Skin composite mode: ffmpeg failed:\n{proc.stderr[-500:]}"
            )

        analysis = (
            f"Onion Skin Mode — Composite (no LLM)\n"
            f"Blend mode: {onion_blend_mode}\n"
            f"Opacity: {onion_opacity:.0%}\n"
            f"Extra inputs: {n_layers}\n"
            f"Layers blended with decay factor 0.5 per layer\n\n"
            f"Inputs:\n  Main: {effective_video_path}\n"
            + "\n".join(f"  Layer {i+1}: {v}" for i, v in enumerate(extra_videos))
        )

    else:
        # ── Temporal mode: single-video ghost trail ──────────────────
        decay = max(0.9, min(0.999, onion_decay))

        ffmpeg_cmd = [
            _ffmpeg, "-y",
            "-i", effective_video_path,
            "-vf", f"lagfun=decay={decay}",
            "-c:v", "libx264",
            "-crf", str(effective_crf),
            "-preset", effective_preset,
            "-pix_fmt", "yuv420p",
        ]

        # Preserve audio
        if video_metadata.primary_audio:
            ffmpeg_cmd.extend(["-c:a", "aac", "-b:a", "192k"])
        else:
            ffmpeg_cmd.append("-an")

        if preview_mode:
            # Insert scale filter before lagfun
            for i, arg in enumerate(ffmpeg_cmd):
                if arg == "-vf":
                    ffmpeg_cmd[i + 1] = f"scale=480:-1,{ffmpeg_cmd[i + 1]}"
                    break
            ffmpeg_cmd.extend(["-t", "10"])

        ffmpeg_cmd.append(output_path)
        cmd_log = " ".join(ffmpeg_cmd)

        logger.debug("Onion Skin temporal command: %s", cmd_log)
        proc = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(
                f"Onion Skin temporal mode: ffmpeg failed:\n{proc.stderr[-500:]}"
            )

        analysis = (
            f"Onion Skin Mode — Temporal (no LLM)\n"
            f"Decay: {decay:.3f}\n"
            f"Input: {effective_video_path}\n"
            f"Output: {output_path}"
        )

    # --- Collect frame/audio output ---
    unique_id = str(kwargs.get("unique_id", ""))
    hidden_prompt = kwargs.get("hidden_prompt") or {}
    images_tensor, audio_out = collect_frame_output(
        media_converter=media_converter,
        output_path=output_path,
        unique_id=unique_id,
        hidden_prompt=hidden_prompt,
        removes_audio=not bool(video_metadata.primary_audio),
    )

    # --- Cleanup temp files ---
    for tmp_path in [temp_video_from_images, temp_video_with_audio]:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
    if not save_output and temp_render_dir and os.path.isdir(temp_render_dir):
        if not os.listdir(temp_render_dir):
            shutil.rmtree(temp_render_dir, ignore_errors=True)

    return (images_tensor, audio_out, output_path, cmd_log, analysis, "")


async def process_comparison_only(
    # dependencies (injected from agent node)
    composer,
    process_manager,
    media_converter,
    # parameters
    effective_video_path: str,
    video_metadata,
    save_output: bool,
    output_path: str,
    preview_mode: bool,
    quality_preset: str,
    crf: int,
    encoding_preset: str,
    comparison_style: str = "swipe",
    comparison_labels: bool = False,
    comparison_label_a: str = "Before",
    comparison_label_b: str = "After",
    _all_video_paths: Optional[list] = None,
    temp_video_from_images: Optional[str] = None,
    temp_video_with_audio: Optional[str] = None,
    **kwargs,
) -> tuple[torch.Tensor, dict, str, str, str, str]:
    """Run Comparison effect directly without any LLM involvement.

    Creates a comparison video from the main video and a connected extra video
    input. Supports styles: swipe, split, side_by_side, diagonal,
    circular_reveal, difference.

    Returns the standard 6-tuple:
        (images_tensor, audio, output_path, command_log, analysis, mask_overlay_path)
    """
    extra_videos = _all_video_paths or []
    if not extra_videos:
        raise RuntimeError(
            "Comparison mode requires a second video input. "
            "Connect a video to video_a (the 'after' input)."
        )

    video_b_path = extra_videos[0]
    logger.info(
        "Comparison mode: style=%s, labels=%s, video_a=%s, video_b=%s",
        comparison_style, comparison_labels, effective_video_path, video_b_path,
    )

    # --- Build output path ---
    output_path, temp_render_dir = build_output_path(
        effective_video_path=effective_video_path,
        save_output=save_output,
        output_path=output_path,
        preview_mode=preview_mode,
    )

    _ffmpeg = _get_ffmpeg_bin()
    effective_crf = crf if crf >= 0 else _CRF_MAP.get(quality_preset, 23)
    effective_preset = (
        encoding_preset if encoding_preset != "auto"
        else _PRESET_MAP.get(quality_preset, "medium")
    )

    # --- Probe input dimensions ---
    try:
        from ..core.bin_paths import get_ffprobe_bin
    except ImportError:
        from core.bin_paths import get_ffprobe_bin  # type: ignore

    w, h, fps_val, dur = 1280, 720, 25, 10.0
    ffprobe = get_ffprobe_bin()
    if ffprobe:
        try:
            probe_result = subprocess.run(
                [ffprobe, "-v", "error", "-select_streams", "v:0",
                 "-show_entries", "stream=width,height,r_frame_rate",
                 "-show_entries", "format=duration",
                 "-of", "csv=p=0", effective_video_path],
                capture_output=True, text=True, timeout=10,
            )
            lines = probe_result.stdout.strip().split("\n")
            if lines and lines[0]:
                parts = lines[0].split(",")
                if len(parts) >= 2:
                    w = int(parts[0])
                    h = int(parts[1])
                if len(parts) >= 3 and "/" in parts[2]:
                    num, den = parts[2].split("/")
                    fps_val = int(num) // max(1, int(den))
            if len(lines) > 1 and lines[1]:
                try:
                    dur = float(lines[1])
                except ValueError:
                    pass
        except Exception:
            pass

    # Ensure even dimensions
    w = w // 2 * 2
    h = h // 2 * 2

    # --- Build filter_complex ---
    style = comparison_style.lower()

    prep_a = (f"[0:v]scale={w}:{h}:force_original_aspect_ratio=decrease,"
              f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:black,setsar=1,fps={fps_val}[_ca]")
    prep_b = (f"[1:v]scale={w}:{h}:force_original_aspect_ratio=decrease,"
              f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:black,setsar=1,fps={fps_val}[_cb]")

    fc_parts = [prep_a, prep_b]

    if style == "swipe":
        # Reveal B left→right over the clip duration. A time-animated crop width
        # can't be used here: crop evaluates w once at init, where t=0 yields a
        # zero-width frame and libx264 fails with "Could not open encoder before
        # EOF" (-22). blend evaluates the expression per-pixel/per-frame instead.
        fc_parts.append(
            f"[_ca][_cb]blend=all_expr='if(lt(X,{w}*T/{dur}),B,A)':shortest=1[_cmp]"
        )

    elif style == "split":
        half = (w // 2) // 2 * 2
        fc_parts.append(f"[_cb]crop=w={half}:h={h}:x=0:y=0[_cb_half]")
        fc_parts.append(f"[_ca][_cb_half]overlay=x=0:y=0:shortest=1[_cmp_raw]")
        fc_parts.append(f"[_cmp_raw]drawbox=x={half}:y=0:w=2:h={h}:color=white:t=fill[_cmp]")

    elif style == "side_by_side":
        fc_parts.append(f"[_ca][_cb]hstack=inputs=2:shortest=1[_cmp]")

    elif style == "diagonal":
        fc_parts.append(
            f"[_ca][_cb]blend=all_expr='if(lt(X/{w}+Y/{h},1),B,A)':shortest=1[_cmp]"
        )

    elif style == "circular_reveal":
        max_r = max(w, h)
        cx, cy = w // 2, h // 2
        fc_parts.append(
            f"[_ca][_cb]blend=all_expr='if(lte(hypot(X-{cx},Y-{cy}),{max_r}*T/{dur}),B,A)':shortest=1[_cmp]"
        )

    elif style == "difference":
        fc_parts.append(f"[_ca][_cb]blend=all_mode=difference:all_opacity=1.0:shortest=1[_cmp]")

    else:
        # Default to swipe (see swipe branch for why blend, not crop+overlay)
        fc_parts.append(
            f"[_ca][_cb]blend=all_expr='if(lt(X,{w}*T/{dur}),B,A)':shortest=1[_cmp]"
        )

    # --- Optional labels ---
    if comparison_labels:
        safe_a = comparison_label_a.replace(":", r"\:")
        safe_b = comparison_label_b.replace(":", r"\:")
        fc_parts.append(
            f"[_cmp]drawtext=text='{safe_a}':fontsize=36:"
            f"fontcolor=white:borderw=2:bordercolor=black:x=20:y=20,"
            f"drawtext=text='{safe_b}':fontsize=36:"
            f"fontcolor=white:borderw=2:bordercolor=black:x=w-text_w-20:y=20[vout]"
        )
        map_label = "[vout]"
    else:
        fc_parts.append("[_cmp]null[vout]")
        map_label = "[vout]"

    filter_complex = ";".join(fc_parts)

    # --- Build FFmpeg command ---
    ffmpeg_cmd = [
        _ffmpeg, "-y",
        "-i", effective_video_path,
        "-stream_loop", "-1", "-i", video_b_path,
        "-filter_complex", filter_complex,
        "-map", map_label,
    ]

    # Copy audio from main input if present
    if video_metadata.primary_audio:
        ffmpeg_cmd.extend(["-map", "0:a?", "-c:a", "aac", "-b:a", "192k"])

    ffmpeg_cmd.extend([
        "-c:v", "libx264",
        "-crf", str(effective_crf),
        "-preset", effective_preset,
        "-pix_fmt", "yuv420p",
        "-shortest",
    ])

    if preview_mode:
        ffmpeg_cmd.extend(["-s", "480x270", "-t", "10"])

    ffmpeg_cmd.append(output_path)
    cmd_log = " ".join(ffmpeg_cmd)

    logger.debug("Comparison command: %s", cmd_log)
    proc = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"Comparison mode: ffmpeg failed:\n{proc.stderr[-500:]}"
        )

    analysis = (
        f"Comparison Mode — {style} (no LLM)\n"
        f"Labels: {'Yes' if comparison_labels else 'No'}\n"
        f"Input A (before): {effective_video_path}\n"
        f"Input B (after): {video_b_path}\n"
        f"Output: {output_path}"
    )

    # --- Collect frame/audio output ---
    unique_id = str(kwargs.get("unique_id", ""))
    hidden_prompt = kwargs.get("hidden_prompt") or {}
    images_tensor, audio_out = collect_frame_output(
        media_converter=media_converter,
        output_path=output_path,
        unique_id=unique_id,
        hidden_prompt=hidden_prompt,
        removes_audio=not bool(video_metadata.primary_audio),
    )

    # --- Cleanup temp files ---
    for tmp_path in [temp_video_from_images, temp_video_with_audio]:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
    if not save_output and temp_render_dir and os.path.isdir(temp_render_dir):
        if not os.listdir(temp_render_dir):
            shutil.rmtree(temp_render_dir, ignore_errors=True)

    return (images_tensor, audio_out, output_path, cmd_log, analysis, "")


async def process_video_matting_only(
    # dependencies
    media_converter,
    # parameters
    prompt: str,
    effective_video_path: str,
    video_metadata,
    save_output: bool,
    output_path: str,
    preview_mode: bool,
    quality_preset: str,
    crf: int,
    encoding_preset: str,
    matting_output: str = "foreground",
    matting_background: str = "green",
    matting_max_size: int = 0,
    mask_output_type: str = "black_white",
    sam3_device: str = "gpu",
    sam3_max_objects: int = 5,
    sam3_det_threshold: float = 0.7,
    mask_points: str = "",
    temp_video_from_images: Optional[str] = None,
    temp_video_with_audio: Optional[str] = None,
    **kwargs,
) -> tuple[torch.Tensor, dict, str, str, str, str]:
    """Run MatAnyone2 video matting directly without any LLM involvement.

    If no manual mask is provided (via image_a tensor or image_path_a file path),
    generates a first-frame mask from SAM3 using the prompt text. Then runs
    MatAnyone2 for production-quality alpha matting with temporal coherence.

    Returns the standard 6-tuple:
        (images_tensor, audio, output_path, command_log, analysis, mask_overlay_path)
    """
    import asyncio

    logger.info("Video Matting mode: prompt='%s', output_type=%s", prompt, matting_output)

    # If effective_video_path is a temp video created from IMAGE tensors,
    # prefer the original video_path for matting (full frame count).
    # IMAGE tensors are often a subset of frames (e.g. 25 out of 192).
    if temp_video_from_images and effective_video_path == temp_video_from_images:
        original_video = kwargs.get("video_path", "")
        if original_video and isinstance(original_video, str) and os.path.isfile(original_video.strip()):
            logger.info(
                "Video Matting: using original video '%s' instead of IMAGE-derived temp '%s'",
                original_video.strip(), effective_video_path,
            )
            effective_video_path = original_video.strip()

    # --- Build output path ---
    output_path, temp_render_dir = build_output_path(
        effective_video_path=effective_video_path,
        save_output=save_output,
        output_path=output_path,
        preview_mode=preview_mode,
    )
    output_dir = os.path.dirname(output_path)

    # --- Generate or locate the first-frame mask ---
    mask_path = None
    mask_source = "auto (SAM3)"

    # Check if a manual mask was provided via image_a
    image_a = kwargs.get("image_a")
    if image_a is not None:
        # image_a is a torch tensor (B, H, W, C) — save first frame as grayscale PNG
        try:
            import numpy as np
            from PIL import Image as PILImage

            if hasattr(image_a, "cpu"):
                mask_np = image_a[0].cpu().numpy()
            else:
                mask_np = np.array(image_a[0])

            # Convert to grayscale if needed
            if mask_np.ndim == 3 and mask_np.shape[-1] >= 3:
                mask_np = np.mean(mask_np[:, :, :3], axis=-1)

            # Normalize to 0-255
            if mask_np.max() <= 1.0:
                mask_np = (mask_np * 255).astype(np.uint8)
            else:
                mask_np = mask_np.astype(np.uint8)

            mask_tmp = tempfile.NamedTemporaryFile(suffix="_matting_mask.png", delete=False)
            PILImage.fromarray(mask_np, mode="L").save(mask_tmp.name)
            mask_path = mask_tmp.name
            mask_source = "manual (image_a)"
            logger.info("Video Matting: using manual mask from image_a → %s", mask_path)
        except Exception as e:
            logger.warning("Video Matting: failed to extract mask from image_a: %s — falling back to SAM3", e)
            mask_path = None

    # Check if a mask file path was provided via image_path_a
    if mask_path is None:
        image_path_a = kwargs.get("image_path_a", "")
        if image_path_a and isinstance(image_path_a, str) and image_path_a.strip() and os.path.isfile(image_path_a.strip()):
            mask_path = image_path_a.strip()
            mask_source = "manual (image_path_a)"
            logger.info("Video Matting: using mask from image_path_a → %s", mask_path)

    # Auto-generate mask from SAM3 if no manual mask
    if mask_path is None:
        # Parse point prompts from the JS point selector
        point_coords = None
        point_labels = None
        point_src_w = 0
        point_src_h = 0
        if mask_points and mask_points.strip():
            try:
                pt_data = json.loads(mask_points)
                if isinstance(pt_data, dict):
                    point_coords = pt_data.get("points")
                    point_labels = pt_data.get("labels")
                    point_src_w = int(pt_data.get("image_width", 0))
                    point_src_h = int(pt_data.get("image_height", 0))
                    if point_coords and point_labels:
                        logger.info("Video Matting: using %d point prompt(s) (src %dx%d)",
                                    len(point_coords), point_src_w, point_src_h)
            except (ValueError, TypeError) as exc:
                logger.warning("Video Matting: failed to parse mask_points JSON: %s", exc)

        has_points = bool(point_coords and point_labels)
        has_prompt = bool(prompt and prompt.strip())

        if not has_points and not has_prompt:
            raise RuntimeError(
                "Video Matting: no mask provided and no prompt text or point prompts "
                "for SAM3 auto-masking. Either connect a mask to image_a, provide a "
                "text prompt, or use the point selector to click on the subject."
            )

        # Extract first frame from video
        import cv2
        import numpy as np
        from PIL import Image as PILImage

        cap = cv2.VideoCapture(effective_video_path)
        ret, first_frame = cap.read()
        cap.release()
        if not ret:
            raise RuntimeError(f"Video Matting: failed to read first frame from {effective_video_path}")

        first_frame_rgb = cv2.cvtColor(first_frame, cv2.COLOR_BGR2RGB)

        # Save first frame to temp file (both APIs expect a file path)
        first_frame_tmp = tempfile.NamedTemporaryFile(suffix="_first_frame.png", delete=False)
        PILImage.fromarray(first_frame_rgb).save(first_frame_tmp.name)

        try:
            if has_points:
                # Point-based masking (click-to-select)
                logger.info("Video Matting: generating mask via SAM3 point prompts (%d points)",
                            len(point_coords))
                try:
                    try:
                        from ..core.sam3_masker import mask_image_with_points as sam3_mask_points
                    except ImportError:
                        from core.sam3_masker import mask_image_with_points as sam3_mask_points  # type: ignore
                except ImportError:
                    raise RuntimeError(
                        "Video Matting: SAM3 not available for point-based masking. "
                        "Either install SAM3 or connect a manual mask to image_a."
                    )

                sam3_result = await asyncio.to_thread(
                    sam3_mask_points,
                    first_frame_tmp.name,
                    point_coords,
                    point_labels,
                    point_src_w,
                    point_src_h,
                    sam3_device,
                )
            else:
                # Text-based masking (prompt)
                logger.info("Video Matting: generating first-frame mask via SAM3 for '%s'", prompt.strip())
                try:
                    try:
                        from ..core.sam3_masker import mask_image_with_text as sam3_mask_image
                    except ImportError:
                        from core.sam3_masker import mask_image_with_text as sam3_mask_image  # type: ignore
                except ImportError:
                    raise RuntimeError(
                        "Video Matting: SAM3 not available for auto-masking. "
                        "Either install SAM3 or connect a manual mask to image_a."
                    )

                sam3_result = await asyncio.to_thread(
                    sam3_mask_image,
                    first_frame_tmp.name,
                    prompt.strip(),
                    sam3_device,
                )

            # sam3 result → numpy array (H, W) with 255=masked, 0=unmasked
            if isinstance(sam3_result, PILImage.Image):
                mask_np = np.array(sam3_result.convert("L"))
            else:
                mask_np = np.array(sam3_result)
                if mask_np.ndim == 3:
                    mask_np = mask_np[:, :, 0]

            mask_tmp = tempfile.NamedTemporaryFile(suffix="_sam3_mask.png", delete=False)
            PILImage.fromarray(mask_np, mode="L").save(mask_tmp.name)
            mask_path = mask_tmp.name
            logger.info("Video Matting: SAM3 mask generated → %s", mask_path)
        except Exception as e:
            raise RuntimeError(
                f"Video Matting: SAM3 mask generation failed: {e}. "
                "Try providing a manual mask via image_a instead."
            ) from e
        finally:
            # Clean up temp first frame
            try:
                os.unlink(first_frame_tmp.name)
            except OSError:
                pass

    # --- Run MatAnyone2 matting ---
    try:
        try:
            from ..core.matanyone2_synthesizer import process_video as matanyone2_process
        except ImportError:
            from core.matanyone2_synthesizer import process_video as matanyone2_process  # type: ignore

        max_size = matting_max_size if matting_max_size > 0 else -1

        matting_results = await asyncio.to_thread(
            matanyone2_process,
            video_path=effective_video_path,
            mask_path=mask_path,
            output_dir=output_dir,
            output_type=matting_output,
            background_color=matting_background,
            max_size=max_size,
        )
    except Exception as e:
        raise RuntimeError(f"Video Matting: MatAnyone2 processing failed: {e}") from e

    # --- Determine the primary output video ---
    if "foreground" in matting_results:
        matted_video = matting_results["foreground"]
    elif "alpha" in matting_results:
        matted_video = matting_results["alpha"]
    else:
        raise RuntimeError("Video Matting: no output produced")

    # Copy the matted video to the expected output path
    if matted_video != output_path:
        _ffmpeg = _get_ffmpeg_bin()
        effective_crf = crf if crf >= 0 else _CRF_MAP.get(quality_preset, 23)
        effective_preset = encoding_preset if encoding_preset != "auto" else _PRESET_MAP.get(quality_preset, "medium")

        ffmpeg_cmd = [
            _ffmpeg, "-y",
            "-i", matted_video,
            "-c:v", "libx264",
            "-crf", str(effective_crf),
            "-preset", effective_preset,
            "-pix_fmt", "yuv420p",
            output_path,
        ]

        if preview_mode:
            ffmpeg_cmd = [
                _ffmpeg, "-y",
                "-i", matted_video,
                "-vf", "scale=480:trunc(ow/a/2)*2",
                "-t", "10",
                "-c:v", "libx264",
                "-crf", str(effective_crf),
                "-preset", effective_preset,
                "-pix_fmt", "yuv420p",
                output_path,
            ]

        proc = await asyncio.to_thread(
            subprocess.run, ffmpeg_cmd, capture_output=True, text=True
        )
        if proc.returncode != 0:
            raise RuntimeError(
                f"Video Matting: FFmpeg re-encode failed:\n{proc.stderr[-500:]}"
            )

    # --- Collect frame/audio output ---
    unique_id = str(kwargs.get("unique_id", ""))
    hidden_prompt = kwargs.get("hidden_prompt") or {}
    images_tensor, audio_out = collect_frame_output(
        media_converter=media_converter,
        output_path=output_path,
        unique_id=unique_id,
        hidden_prompt=hidden_prompt,
        removes_audio=True,  # matting removes audio
    )

    # --- Output the mask image so the user can see what was generated ---
    # Always return the SAM3/manual mask PNG; fall back to alpha video if available
    mask_overlay_path = mask_path or ""
    if not mask_overlay_path and "alpha" in matting_results:
        mask_overlay_path = matting_results["alpha"]

    # Generate colored overlay if requested
    if mask_overlay_path and mask_output_type == "colored_overlay" and os.path.isfile(mask_overlay_path):
        try:
            import cv2
            import numpy as np
            from PIL import Image as PILImage

            # Read the mask
            mask_img = np.array(PILImage.open(mask_overlay_path).convert("L"))

            # Read the first frame from the video
            cap = cv2.VideoCapture(effective_video_path)
            ret, first_frame = cap.read()
            cap.release()

            if ret:
                first_frame_rgb = cv2.cvtColor(first_frame, cv2.COLOR_BGR2RGB)

                # Resize mask to match frame if needed
                if mask_img.shape[:2] != first_frame_rgb.shape[:2]:
                    mask_img = cv2.resize(mask_img, (first_frame_rgb.shape[1], first_frame_rgb.shape[0]), interpolation=cv2.INTER_NEAREST)

                # Create colored overlay (SAM3-style blue-green)
                overlay_color = np.array([30, 180, 230], dtype=np.uint8)  # teal
                binary = (mask_img > 127).astype(np.uint8)
                overlay = first_frame_rgb.copy()
                mask_region = binary.astype(bool)
                overlay[mask_region] = (
                    overlay[mask_region].astype(np.float32) * 0.5
                    + overlay_color.astype(np.float32) * 0.5
                ).astype(np.uint8)

                # Draw contour
                contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                overlay_bgr = cv2.cvtColor(overlay, cv2.COLOR_RGB2BGR)
                cv2.drawContours(overlay_bgr, contours, -1, (0, 255, 255), 2)
                overlay = cv2.cvtColor(overlay_bgr, cv2.COLOR_BGR2RGB)

                # Save colored overlay
                overlay_tmp = tempfile.NamedTemporaryFile(suffix="_mask_overlay.png", delete=False)
                PILImage.fromarray(overlay).save(overlay_tmp.name)
                mask_overlay_path = overlay_tmp.name
                logger.info("Video Matting: colored mask overlay → %s", mask_overlay_path)
        except Exception as e:
            logger.warning("Video Matting: colored overlay generation failed: %s — using raw mask", e)

    # --- Build analysis string ---
    cmd_log = f"matanyone2 process_video → {matted_video}"
    analysis = (
        f"Video Matting Mode (MatAnyone2, no LLM)\n"
        f"Mask source: {mask_source}\n"
        f"Output type: {matting_output}\n"
        f"Background: {matting_background}\n"
        f"Max size: {matting_max_size or 'unlimited'}\n"
        f"Output: {output_path}\n"
        f"Alpha: {matting_results.get('alpha', 'not generated')}"
    )

    # --- Cleanup temp files ---
    for tmp_path in [temp_video_from_images, temp_video_with_audio]:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
    if not save_output and temp_render_dir and os.path.isdir(temp_render_dir):
        if not os.listdir(temp_render_dir):
            shutil.rmtree(temp_render_dir, ignore_errors=True)

    return (images_tensor, audio_out, output_path, cmd_log, analysis, mask_overlay_path)


# ╔══════════════════════════════════════════════════════════════════╗
# ║  SCAIL — Pose-Driven Character Animation  (WIP)                 ║
# ╚══════════════════════════════════════════════════════════════════╝


async def process_scail2_only(
    prompt: str,
    effective_video_path: str,
    video_metadata,
    save_output: bool,
    output_path: str,
    preview_mode: bool,
    quality_preset: str,
    crf: int,
    encoding_preset: str,
    image_a=None,
    **kwargs,
) -> tuple[torch.Tensor, dict, str, str, str, str]:
    """Run native SCAIL-2 pose-driven character animation without an LLM.

    Requires:
    - Reference character image on ``image_a`` (or ``image_path_a``)
    - Driving/pose video on ``effective_video_path``

    SAM 3.1 tracks the subject(s) (driven by ``prompt``/``mask_points``) in both
    the driving video and the reference image; the colored masks feed the native
    ``WanSCAILToVideo`` conditioning. Returns the standard 6-tuple with the
    colored pose-video mask in the ``mask_overlay_path`` slot so a second Save
    Video node can save it:
        (images_tensor, audio, output_path, command_log, analysis, mask_video_path)
    """
    logger.info("SCAIL2 mode: prompt=%r", prompt)

    # --- Parameters from advanced widgets ---
    scail2_steps = int(kwargs.get("scail2_steps", 6))
    scail2_cfg = float(kwargs.get("scail2_cfg", 1.0))
    scail2_shift = float(kwargs.get("scail2_shift", 5.0))
    scail2_length = int(kwargs.get("scail2_length", 81))
    scail2_width = int(kwargs.get("scail2_width", 512))
    scail2_height = int(kwargs.get("scail2_height", 896))
    scail2_seed = int(kwargs.get("scail2_seed", kwargs.get("seed", 0)))
    scail2_sampler = str(kwargs.get("scail2_sampler", "euler"))
    scail2_scheduler = str(kwargs.get("scail2_scheduler", "simple"))
    scail2_denoise = float(kwargs.get("scail2_denoise", 1.0))
    scail2_replacement = bool(kwargs.get("scail2_replacement_mode", False))
    scail2_sort_by = str(kwargs.get("scail2_sort_by", "left_to_right"))
    scail2_object_indices = str(kwargs.get("scail2_object_indices", ""))
    scail2_subject = str(kwargs.get("scail2_subject", "person")).strip()
    scail2_max_objects = int(kwargs.get("scail2_max_objects", 1))
    scail2_det_threshold = float(kwargs.get("scail2_detection_threshold", 0.5))
    scail2_detect_interval = int(kwargs.get("scail2_detect_interval", 2))
    scail2_point_src_w = int(kwargs.get("scail2_point_src_width", 0))
    scail2_point_src_h = int(kwargs.get("scail2_point_src_height", 0))
    scail2_composite_direction = str(kwargs.get("scail2_composite_direction", "horizontal"))
    scail2_main_reference = str(kwargs.get("scail2_main_reference", "last"))
    scail2_color_match = bool(kwargs.get("scail2_color_match", False))
    scail2_pose_extend = str(kwargs.get("scail2_pose_extend", "pingpong"))
    scail2_blockswap = int(kwargs.get("scail2_blockswap_blocks", 0))
    scail2_tiled_vae = bool(kwargs.get("scail2_tiled_vae", False))

    # --- Import SCAIL-2 synthesizer ---
    try:
        from ..core.scail2_synthesizer import (
            generate_video as _scail2_generate, cleanup as _scail2_cleanup,
        )
    except ImportError:
        try:
            from core.scail2_synthesizer import (  # type: ignore
                generate_video as _scail2_generate, cleanup as _scail2_cleanup,
            )
        except ImportError as exc:
            raise RuntimeError(
                "SCAIL-2 is not available. Ensure core/scail2_synthesizer.py "
                "exists and ComfyUI ships comfy_extras/nodes_scail.py."
            ) from exc

    # --- Validate inputs (image_a tensor or image_path_a file) ---
    image_path_a = kwargs.get("image_path_a", "")
    if image_a is None and image_path_a and os.path.isfile(image_path_a.strip()):
        image_a = image_path_a.strip()
        logger.info("SCAIL2: using image_path_a as reference: %s", image_a)
    if image_a is None:
        raise RuntimeError(
            "SCAIL-2 requires a reference character image. "
            "Connect an image to image_a or image_path_a.")
    if not effective_video_path or not os.path.isfile(effective_video_path):
        raise RuntimeError(
            "SCAIL-2 requires a driving/pose video. Connect a video input.")

    # --- Parse point prompts (from the JS point selector) ---
    sam_points = sam_labels = None
    point_src_w = point_src_h = 0
    mask_points = kwargs.get("mask_points", "")
    if mask_points and str(mask_points).strip():
        try:
            pt_data = json.loads(mask_points)
            if isinstance(pt_data, dict):
                sam_points = pt_data.get("points")
                sam_labels = pt_data.get("labels")
                point_src_w = int(pt_data.get("image_width", 0))
                point_src_h = int(pt_data.get("image_height", 0))
        except (ValueError, TypeError) as exc:
            logger.warning("SCAIL2: failed to parse mask_points JSON: %s", exc)
    # Manual point-source overrides (0 = keep the value from the point selector).
    if scail2_point_src_w > 0:
        point_src_w = scail2_point_src_w
    if scail2_point_src_h > 0:
        point_src_h = scail2_point_src_h

    # --- Collect LoRA entries from dynamic slots (a → d) ---
    lora_entries = []  # list of (path, strength)
    lora_log = ""
    for slot in ("a", "b", "c", "d"):
        lora_name = str(kwargs.get(f"scail2_lora_{slot}", "none"))
        if not lora_name or lora_name == "none":
            break
        lora_strength = float(kwargs.get(f"scail2_lora_strength_{slot}", 1.0))
        lora_path = None
        try:
            import folder_paths  # type: ignore
            lora_path = folder_paths.get_full_path("loras", lora_name)
        except Exception:
            lora_path = None
        if lora_path:
            lora_entries.append((lora_path, lora_strength))
            lora_log += f"LoRA {slot.upper()}: {lora_name} (strength={lora_strength})\n"
        else:
            lora_log += f"⚠️ LoRA {slot.upper()} not found: {lora_name} — skipping\n"

    # --- Build output path ---
    output_path, temp_render_dir = build_output_path(
        effective_video_path=effective_video_path,
        save_output=save_output,
        output_path=output_path,
        preview_mode=preview_mode,
    )

    # --- Convert image_a tensor → temp PNG file ---
    import numpy as _np
    ref_image_path = None
    temp_files = []
    try:
        if hasattr(image_a, "shape") and len(image_a.shape) == 4:
            tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
            tmp.close()
            from PIL import Image
            arr = (image_a[0].cpu().numpy() * 255).clip(0, 255).astype(_np.uint8)
            Image.fromarray(arr).save(tmp.name)
            ref_image_path = tmp.name
            temp_files.append(tmp.name)
        elif hasattr(image_a, "shape") and len(image_a.shape) == 3:
            tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
            tmp.close()
            from PIL import Image
            arr = (image_a.cpu().numpy() * 255).clip(0, 255).astype(_np.uint8)
            Image.fromarray(arr).save(tmp.name)
            ref_image_path = tmp.name
            temp_files.append(tmp.name)
        elif isinstance(image_a, str) and os.path.isfile(image_a):
            ref_image_path = image_a
        else:
            raise RuntimeError(
                f"Unexpected image_a type: {type(image_a)}. "
                "Expected ComfyUI IMAGE tensor or file path.")

        logger.info("SCAIL2: ref=%s driving=%s", ref_image_path, effective_video_path)

        # --- Collect extra reference images (image_b/image_path_b, c, d …) ---
        # Multiple references are composited onto one image so SAM gives each
        # subject its own color (2nd subject → red). Reuses the same temp_files
        # cleanup list as the primary reference.
        extra_ref_paths = []
        for suffix in ("b", "c", "d", "e"):
            img_t = kwargs.get(f"image_{suffix}")
            img_p = kwargs.get(f"image_path_{suffix}", "")
            extra_path = None
            if img_t is not None and hasattr(img_t, "shape"):
                frame = img_t[0] if len(img_t.shape) == 4 else img_t
                tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
                tmp.close()
                from PIL import Image
                arr = (frame.cpu().numpy() * 255).clip(0, 255).astype(_np.uint8)
                Image.fromarray(arr).save(tmp.name)
                extra_path = tmp.name
                temp_files.append(tmp.name)
            elif isinstance(img_p, str) and img_p.strip() and os.path.isfile(img_p.strip()):
                extra_path = img_p.strip()
            if extra_path:
                extra_ref_paths.append(extra_path)
        if extra_ref_paths:
            logger.info("SCAIL2: %d extra reference image(s) → composited",
                        len(extra_ref_paths))

        cmd_log = (
            f"scail2 generate --ref {ref_image_path} "
            f"--driving {effective_video_path}\n{lora_log}"
        )

        # --- Generate (returns animation + colored mask video paths) ---
        # SAM 3.1 detection target is the dedicated subject noun, NOT the
        # animation prompt — a full sentence makes SAM over-detect and produces
        # splotchy multi-colored masks. mask_points (if supplied) override it.
        sam_prompt = scail2_subject or "person"
        try:
            animation_path, mask_video_path = _scail2_generate(
                prompt=prompt,
                reference_image_path=ref_image_path,
                driving_video_path=effective_video_path,
                output_path=output_path,
                width=scail2_width,
                height=scail2_height,
                length=scail2_length,
                steps=scail2_steps,
                cfg=scail2_cfg,
                shift=scail2_shift,
                seed=scail2_seed,
                sampler_name=scail2_sampler,
                scheduler=scail2_scheduler,
                denoise=scail2_denoise,
                replacement_mode=scail2_replacement,
                sort_by=scail2_sort_by,
                object_indices=scail2_object_indices,
                sam_prompt=sam_prompt,
                sam_points=sam_points,
                sam_labels=sam_labels,
                sam_max_objects=scail2_max_objects,
                sam_det_threshold=scail2_det_threshold,
                sam_detect_interval=scail2_detect_interval,
                extra_reference_paths=extra_ref_paths,
                composite_direction=scail2_composite_direction,
                main_reference=scail2_main_reference,
                color_match=scail2_color_match,
                pose_extend=scail2_pose_extend,
                point_src_width=point_src_w,
                point_src_height=point_src_h,
                lora_entries=lora_entries,
                blockswap_blocks=scail2_blockswap,
                tiled_vae=scail2_tiled_vae,
            )
        finally:
            _scail2_cleanup()

        output_path = animation_path

        # --- Collect output frames/audio ---
        try:
            from ..ffmpega_media_converter import MediaConverter
            media_converter = MediaConverter()
        except ImportError:
            try:
                from ffmpega_media_converter import MediaConverter  # type: ignore
                media_converter = MediaConverter()
            except Exception:
                media_converter = None

        unique_id = str(kwargs.get("unique_id", ""))
        hidden_prompt = kwargs.get("hidden_prompt") or {}
        images_tensor, audio_out = collect_frame_output(
            media_converter=media_converter,
            output_path=output_path,
            unique_id=unique_id,
            hidden_prompt=hidden_prompt,
            removes_audio=False,
        )

        analysis = (
            f"🎭 SCAIL-2 Character Animation\n"
            f"Mode: {'replacement' if scail2_replacement else 'animation'}\n"
            f"Resolution: {scail2_width}x{scail2_height}, frames={scail2_length} "
            f"(extend pose: {scail2_pose_extend})\n"
            f"Steps: {scail2_steps}, CFG: {scail2_cfg}, Shift: {scail2_shift}\n"
            f"Sampler: {scail2_sampler}/{scail2_scheduler}, Denoise: {scail2_denoise}\n"
            f"Seed: {scail2_seed}\n"
            f"SAM3 subject: {sam_prompt} (max {scail2_max_objects}, "
            f"det {scail2_det_threshold}, interval {scail2_detect_interval})"
            f"{' (point prompts)' if sam_points else ''}\n"
            f"References: {1 + len(extra_ref_paths)}"
            f"{f' ({scail2_composite_direction}, main={scail2_main_reference})' if extra_ref_paths else ''}\n"
            f"Mask sort: {scail2_sort_by}, object_indices: "
            f"{scail2_object_indices or '(all)'}\n"
            f"{lora_log}"
            f"Output: {output_path}\n"
            f"Mask video: {mask_video_path}"
        )

        return (images_tensor, audio_out, output_path, cmd_log, analysis, mask_video_path)
    finally:
        for tmp_path in temp_files:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
        if not save_output and temp_render_dir and os.path.isdir(temp_render_dir):
            if not os.listdir(temp_render_dir):
                shutil.rmtree(temp_render_dir, ignore_errors=True)


# ================================================================== #
#  SHARP — single-image 3D Gaussian view synthesis                     #
# ================================================================== #

async def process_sharp_only(
    # dependencies
    media_converter,
    # parameters
    effective_video_path: str,
    video_metadata,
    save_output: bool,
    output_path: str,
    preview_mode: bool,
    quality_preset: str,
    crf: int,
    encoding_preset: str,
    image_a=None,
    temp_video_from_images: Optional[str] = None,
    temp_video_with_audio: Optional[str] = None,
    **kwargs,
) -> tuple[torch.Tensor, dict, str, str, str, str]:
    """Run Apple SHARP 3D Gaussian view synthesis without any LLM involvement.

    Takes a single image from ``image_a`` (ComfyUI IMAGE tensor) and:
    1. Predicts 3D Gaussian splat parameters (<1s)
    2. Renders a camera trajectory video via gsplat (CUDA only)
    3. Optionally exports the .ply file

    ⚠️ Model weights are Apple ML Research License (non-commercial/research only).

    Returns the standard 6-tuple:
        (images_tensor, audio, output_path, command_log, analysis, mask_overlay_path)
    """
    # --- Extract SHARP parameters from kwargs ---
    sharp_trajectory = str(kwargs.pop("sharp_trajectory", "rotate_forward"))
    sharp_num_frames = int(kwargs.pop("sharp_num_frames", 60))
    sharp_max_disparity = float(kwargs.pop("sharp_max_disparity", 0.08))
    sharp_max_zoom = float(kwargs.pop("sharp_max_zoom", 0.15))
    sharp_save_ply = str(kwargs.pop("sharp_save_ply", "false")).lower() in ("true", "1", "yes")
    sharp_device = str(kwargs.pop("sharp_device", "auto"))

    logger.info(
        "SHARP mode: trajectory=%s, frames=%d, disparity=%.3f, zoom=%.3f, ply=%s, device=%s",
        sharp_trajectory, sharp_num_frames, sharp_max_disparity, sharp_max_zoom,
        sharp_save_ply, sharp_device,
    )

    # --- Extract input image from image_a tensor or image_path_a ---
    # Accept from tensor (image_a) or file path (image_path_a from LoadImagePath)
    image_path_a = kwargs.pop("image_path_a", "")
    if image_a is None or (hasattr(image_a, "shape") and image_a.shape[0] == 0):
        if image_path_a and isinstance(image_path_a, str) and image_path_a.strip() and os.path.isfile(image_path_a.strip()):
            from PIL import Image as _PILImage
            import numpy as np
            pil_img = _PILImage.open(image_path_a.strip()).convert("RGB")
            image_a = np.array(pil_img)
            logger.info("SHARP: loaded image from image_path_a → %s", image_path_a.strip())
        else:
            raise RuntimeError(
                "SHARP mode requires an image connected to the image_a or image_path_a input. "
                "Connect an image source (Load Image, LoadImagePath, etc.)."
            )

    # Convert ComfyUI IMAGE tensor (B, H, W, C) float32 [0,1] → numpy HWC uint8
    if isinstance(image_a, torch.Tensor):
        if image_a.dim() == 4:
            image_np = (image_a[0].cpu().numpy() * 255.0).clip(0, 255).astype(np.uint8)
        elif image_a.dim() == 3:
            image_np = (image_a.cpu().numpy() * 255.0).clip(0, 255).astype(np.uint8)
        else:
            raise RuntimeError(f"Unexpected image_a tensor shape: {image_a.shape}")
    elif isinstance(image_a, np.ndarray):
        if image_a.max() <= 1.0:
            image_np = (image_a * 255.0).clip(0, 255).astype(np.uint8)
        else:
            image_np = image_a.astype(np.uint8)
    else:
        raise RuntimeError(f"Unsupported image_a type: {type(image_a)}")

    # Ensure RGB (3 channels)
    if image_np.ndim == 2:
        image_np = np.stack([image_np] * 3, axis=-1)
    elif image_np.shape[-1] == 4:
        image_np = image_np[..., :3]

    logger.info("SHARP: input image shape: %s", image_np.shape)

    # --- Import SHARP synthesizer ---
    try:
        try:
            from ..core.sharp_synthesizer import run_sharp_pipeline, TRAJECTORY_TYPES
        except ImportError:
            from core.sharp_synthesizer import run_sharp_pipeline, TRAJECTORY_TYPES  # type: ignore
    except ImportError:
        raise RuntimeError(
            "SHARP is not available. Install with:\n"
            "  pip install --no-deps git+https://github.com/apple/ml-sharp.git\n"
            "See requirements-optional.txt for details."
        )

    if sharp_trajectory not in TRAJECTORY_TYPES:
        logger.warning(
            "SHARP: unknown trajectory '%s', falling back to 'rotate_forward'",
            sharp_trajectory,
        )
        sharp_trajectory = "rotate_forward"

    # --- Build output path ---
    output_path, temp_render_dir = build_output_path(
        effective_video_path=effective_video_path,
        save_output=save_output,
        output_path=output_path,
        preview_mode=preview_mode,
    )

    # --- Resolve PLY output path ---
    ply_output_path = None
    if sharp_save_ply:
        try:
            import folder_paths  # type: ignore[import-not-found]
            out_dir = folder_paths.get_output_directory()
        except ImportError:
            out_dir = os.path.dirname(output_path)
        ply_basename = os.path.splitext(os.path.basename(output_path))[0] + ".ply"
        ply_output_path = os.path.join(out_dir, ply_basename)

    # --- Run SHARP pipeline (in-process with GPU) ---
    frames_dir = None
    ply_path = None
    try:
        frames_dir, ply_path = run_sharp_pipeline(
            image_np=image_np,
            output_video_path=output_path,
            trajectory_type=sharp_trajectory,
            num_frames=sharp_num_frames,
            max_disparity=sharp_max_disparity,
            max_zoom=sharp_max_zoom,
            device=sharp_device,
            export_ply=sharp_save_ply,
            ply_output_path=ply_output_path,
        )
    except Exception as e:
        logger.error("SHARP mode: inference failed: %s", e)
        raise RuntimeError(f"SHARP inference failed: {e}") from e

    if not frames_dir:
        # CPU/MPS mode — only PLY was exported, no video rendered
        raise RuntimeError(
            "SHARP video rendering requires a CUDA GPU (gsplat limitation). "
            f"PLY file exported to: {ply_path}" if ply_path else
            "SHARP requires CUDA for video rendering. Enable sharp_save_ply for PLY-only mode on CPU."
        )

    # --- Encode frames through FFmpeg with user quality settings ---
    _ffmpeg = _get_ffmpeg_bin()
    effective_crf = crf if crf >= 0 else _CRF_MAP.get(quality_preset, 23)
    effective_preset = encoding_preset if encoding_preset != "auto" else _PRESET_MAP.get(quality_preset, "medium")

    # Detect FPS: use 30 fps for rendered trajectories
    render_fps = 30

    ffmpeg_cmd = [
        _ffmpeg, "-y",
        "-framerate", str(render_fps),
        "-i", os.path.join(frames_dir, "frame_%05d.png"),
        "-c:v", "libx264",
        "-crf", str(effective_crf),
        "-preset", effective_preset,
        "-pix_fmt", "yuv420p",
        "-color_range", "pc",
        "-an",  # No audio for rendered trajectories
    ]

    if preview_mode:
        ffmpeg_cmd.extend(["-vf", "scale=480:trunc(ow/a/2)*2", "-t", "10"])

    ffmpeg_cmd.append(output_path)

    logger.debug("SHARP ffmpeg command: %s", " ".join(ffmpeg_cmd))
    proc = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"SHARP mode: ffmpeg encoding failed:\n{proc.stderr[-500:]}"
        )
    cmd_log = " ".join(ffmpeg_cmd)

    try:
        # --- Collect frame/audio output ---
        unique_id = str(kwargs.get("unique_id", ""))
        hidden_prompt = kwargs.get("hidden_prompt") or {}
        images_tensor, audio_out = collect_frame_output(
            media_converter=media_converter,
            output_path=output_path,
            unique_id=unique_id,
            hidden_prompt=hidden_prompt,
            removes_audio=True,
        )

        # --- Build analysis string ---
        analysis = (
            f"SHARP Mode (no LLM) — 3D Gaussian View Synthesis\n"
            f"⚠️ Model weights: Apple ML Research License (research/non-commercial only)\n\n"
            f"Trajectory: {sharp_trajectory}\n"
            f"Frames: {sharp_num_frames}\n"
            f"Max disparity: {sharp_max_disparity}\n"
            f"Max zoom: {sharp_max_zoom}\n"
            f"Device: {sharp_device}\n"
            f"Image size: {image_np.shape[1]}×{image_np.shape[0]}\n\n"
            f"Output: {output_path}"
        )
        if ply_path:
            analysis += f"\nPLY export: {ply_path}"

        return (images_tensor, audio_out, output_path, cmd_log, analysis, "")
    finally:
        # --- Cleanup temp files ---
        import shutil as _shutil
        for tmp_path in [temp_video_from_images, temp_video_with_audio]:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
        # Clean up rendered PNG frames (no longer needed after FFmpeg encode)
        if frames_dir and os.path.isdir(frames_dir):
            try:
                _shutil.rmtree(frames_dir, ignore_errors=True)
            except OSError:
                pass
        # NOTE: Do NOT delete temp_render_dir here — the output video
        # lives inside it when save_output=False and downstream nodes
        # (save/preview) still need to read it.


# ================================================================== #
#  SVI 2.0 Pro — infinite-length video generation                      #
# ================================================================== #

async def process_svi_only(
    # parameters
    prompt: str,
    effective_video_path: str,
    video_metadata,
    save_output: bool,
    output_path: str,
    preview_mode: bool,
    quality_preset: str,
    crf: int,
    encoding_preset: str,
    image_a=None,
    image_path_a: Optional[str] = None,
    temp_video_from_images: Optional[str] = None,
    temp_video_with_audio: Optional[str] = None,
    **kwargs,
) -> tuple[torch.Tensor, dict, str, str, str, str]:
    """Run SVI 2.0 Pro infinite video generation without any LLM involvement.

    The reference image comes from ``image_a`` (ComfyUI IMAGE tensor).
    Per-clip prompts are newline-separated in the ``prompt`` field.

    Returns the standard 6-tuple:
        (images_tensor, audio, output_path, command_log, analysis, mask_overlay_path)
    """
    logger.info("SVI mode: prompt=%r", prompt)

    # --- Extract SVI parameters from kwargs ---
    svi_num_clips = int(kwargs.pop("svi_num_clips", 10))
    svi_height = int(kwargs.pop("svi_height", 480))
    svi_width = int(kwargs.pop("svi_width", 832))
    svi_fps = int(kwargs.pop("svi_fps", 15))
    svi_cfg_scale = float(kwargs.pop("svi_cfg_scale", 4.0))
    svi_overlap_frames = int(kwargs.pop("svi_overlap_frames", 5))
    svi_seed_multiplier = int(kwargs.pop("svi_seed_multiplier", 42))
    svi_steps = int(kwargs.pop("svi_steps", 30))
    svi_high_model_ratio = float(kwargs.pop("svi_high_model_ratio", 0.875))
    svi_frames_per_clip = int(kwargs.pop("svi_frames_per_clip", 81))
    svi_variant = str(kwargs.pop("svi_variant", "pro"))
    svi_model_high = str(kwargs.pop("svi_model_high", "auto"))
    svi_model_low = str(kwargs.pop("svi_model_low", "auto"))
    svi_lora_high = str(kwargs.pop("svi_lora_high", "SVI_Wan2.2-I2V-A14B_high_noise_lora_v2.0_pro.safetensors"))
    svi_lora_low = str(kwargs.pop("svi_lora_low", "SVI_Wan2.2-I2V-A14B_low_noise_lora_v2.0_pro.safetensors"))
    svi_extra_lora_high = str(kwargs.pop("svi_extra_lora_high", "none"))
    svi_extra_lora_low = str(kwargs.pop("svi_extra_lora_low", "none"))
    svi_vae = str(kwargs.pop("svi_vae", "auto"))
    svi_text_encoder = str(kwargs.pop("svi_text_encoder", "auto"))
    svi_sampler = str(kwargs.pop("svi_sampler", "euler"))
    svi_scheduler = str(kwargs.pop("svi_scheduler", "normal"))
    svi_blockswap_blocks = int(kwargs.pop("svi_blockswap_blocks", 0))
    svi_tiled_vae = bool(kwargs.pop("svi_tiled_vae", False))

    # Derive variant from the selected LoRA filenames
    if "_pro" in svi_lora_high.lower():
        svi_variant = "pro"
    else:
        svi_variant = "standard"

    # --- Import SVI synthesizer ---
    try:
        try:
            from ..core.svi_synthesizer import (
                generate_infinite_video,
                cleanup as _svi_cleanup,
            )
        except ImportError:
            from core.svi_synthesizer import (  # type: ignore
                generate_infinite_video,
                cleanup as _svi_cleanup,
            )
    except ImportError:
        raise RuntimeError(
            "SVI synthesizer is not available. "
            "Ensure core/svi_synthesizer.py exists."
        )

    # --- Convert image_a tensor → saved reference image ---
    ref_image_path = None
    if image_a is not None:
        from PIL import Image as _PILImage
        import numpy as _np
        if hasattr(image_a, 'shape') and len(image_a.shape) >= 3:
            if len(image_a.shape) == 4:
                arr = (image_a[0].cpu().numpy() * 255).clip(0, 255).astype(_np.uint8)
            else:
                arr = (image_a.cpu().numpy() * 255).clip(0, 255).astype(_np.uint8)
            import tempfile as _tmp
            ref_dir = _tmp.mkdtemp(prefix="svi_ref_")
            ref_image_path = os.path.join(ref_dir, "reference.png")
            _PILImage.fromarray(arr).save(ref_image_path)
            logger.info("SVI: saved reference image from image_a → %s", ref_image_path)

    # Fall back to image_path_a (string path from LoadImagePath)
    if ref_image_path is None and image_path_a:
        path_a = str(image_path_a)
        if os.path.isfile(path_a):
            ext_a = os.path.splitext(path_a)[1].lower()
            if ext_a in (".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".webp"):
                ref_image_path = path_a
                logger.info("SVI: using image_path_a as reference → %s", ref_image_path)

    # Fall back to effective_video_path (or video_path from kwargs) if it's an image/video
    if ref_image_path is None:
        # Try multiple sources for a video/image path
        candidate_paths = [
            effective_video_path,
            str(kwargs.get("video_path", "")),
        ]
        video_candidate = None
        for cand in candidate_paths:
            if cand and os.path.isfile(cand):
                video_candidate = cand
                break

        if video_candidate:
            ext = os.path.splitext(video_candidate)[1].lower()
            if ext in (".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".webp"):
                ref_image_path = video_candidate
            elif ext in (".mp4", ".mov", ".avi", ".mkv", ".webm", ".flv"):
                # Extract last frame from previous video for continuation chaining
                import subprocess, tempfile as _tmp
                ref_dir = _tmp.mkdtemp(prefix="svi_ref_")
                last_frame_path = os.path.join(ref_dir, "last_frame.png")
                try:
                    subprocess.run(
                        [
                            "ffmpeg", "-y", "-sseof", "-0.1",
                            "-i", video_candidate,
                            "-frames:v", "1", "-update", "1",
                            last_frame_path,
                        ],
                        capture_output=True, timeout=30,
                    )
                    if os.path.isfile(last_frame_path):
                        ref_image_path = last_frame_path
                        logger.info(
                            "SVI: extracted last frame from video for continuation → %s",
                            ref_image_path,
                        )
                    else:
                        raise RuntimeError("ffmpeg did not produce last frame")
                except Exception as e:
                    raise RuntimeError(
                        f"SVI mode: could not extract last frame from video "
                        f"'{video_candidate}': {e}. "
                        "Connect an image to image_a instead."
                    )

        if ref_image_path is None:
            raise RuntimeError(
                "SVI mode requires a reference image. "
                "Connect an image to image_a, provide an image_path_a, "
                "or connect a previous SVI video output to auto-extract "
                f"its last frame for continuation. "
                f"(effective_video_path='{effective_video_path}')"
            )

    # --- Parse prompts (newline-separated) ---
    prompts = [line.strip() for line in prompt.strip().split("\n") if line.strip()]
    if not prompts:
        prompts = ["A beautiful cinematic scene with natural motion"]

    # --- Build output path ---
    output_path, temp_render_dir = build_output_path(
        effective_video_path=effective_video_path,
        save_output=save_output,
        output_path=output_path,
        preview_mode=preview_mode,
    )

    cmd_log = ""
    try:
        result_path = generate_infinite_video(
            ref_image_path=ref_image_path,
            prompts=prompts,
            output_path=output_path,
            num_clips=svi_num_clips,
            height=svi_height,
            width=svi_width,
            fps=svi_fps,
            cfg_scale=svi_cfg_scale,
            num_overlap_frame=svi_overlap_frames,
            seed_multiplier=svi_seed_multiplier,
            num_inference_steps=svi_steps,
            switch_boundary=svi_high_model_ratio,
            frames_per_clip=svi_frames_per_clip,
            variant=svi_variant,
            model_path_high=svi_model_high,
            model_path_low=svi_model_low,
            lora_high=svi_lora_high,
            lora_low=svi_lora_low,
            extra_lora_high=svi_extra_lora_high if svi_extra_lora_high != "none" else None,
            extra_lora_low=svi_extra_lora_low if svi_extra_lora_low != "none" else None,
            vae_path=svi_vae,
            text_encoder_path=svi_text_encoder,
            sampler_name=svi_sampler,
            scheduler=svi_scheduler,
            blockswap_blocks=svi_blockswap_blocks,
            tiled_vae=svi_tiled_vae,
        )
        output_path = result_path
        cmd_log = f"svi generate_infinite_video → {output_path}"

    except Exception as e:
        logger.error("SVI mode failed: %s", e)
        try:
            _svi_cleanup()
        except Exception:
            pass
        raise RuntimeError(f"SVI generation failed: {e}") from e

    try:
        # --- Collect frame/audio output ---
        try:
            from ..ffmpega_media_converter import MediaConverter
            media_converter = MediaConverter()
        except ImportError:
            try:
                from ffmpega_media_converter import MediaConverter  # type: ignore
                media_converter = MediaConverter()
            except Exception:
                media_converter = None

        unique_id = str(kwargs.get("unique_id", ""))
        hidden_prompt = kwargs.get("hidden_prompt") or {}
        images_tensor, audio_out = collect_frame_output(
            media_converter=media_converter,
            output_path=output_path,
            unique_id=unique_id,
            hidden_prompt=hidden_prompt,
            removes_audio=False,
        )

        # --- Build analysis string ---
        analysis = (
            f"🎬 SVI 2.0 Pro — Infinite Video Generation\n"
            f"Clips: {svi_num_clips}\n"
            f"Resolution: {svi_width}×{svi_height}\n"
            f"FPS: {svi_fps}\n"
            f"CFG Scale: {svi_cfg_scale}\n"
            f"Overlap Frames: {svi_overlap_frames}\n"
            f"Variant: {svi_variant}\n"
            f"Prompts:\n" + "\n".join(f"  {i+1}. {p}" for i, p in enumerate(prompts[:svi_num_clips]))
            + f"\n\nOutput: {output_path}"
        )

        return (images_tensor, audio_out, output_path, cmd_log, analysis, "")

    finally:
        if not save_output and temp_render_dir and os.path.isdir(temp_render_dir):
            if not os.listdir(temp_render_dir):
                shutil.rmtree(temp_render_dir, ignore_errors=True)


# ═══════════════════════════════════════════════════════════════════════════
#  Wan-Animate  — Video-driven character animation (no-LLM mode)
# ═══════════════════════════════════════════════════════════════════════════

async def process_wan_animate_only(
    # dependencies
    media_converter,
    # parameters
    effective_video_path: str,
    video_metadata,
    save_output: bool,
    output_path: str,
    preview_mode: bool,
    quality_preset: str,
    crf: int,
    encoding_preset: str,
    image_a=None,
    image_path_a: str = "",
    temp_video_from_images: Optional[str] = None,
    temp_video_with_audio: Optional[str] = None,
    **kwargs,
) -> tuple:
    """Run Wan-Animate video-driven character animation without any LLM involvement.

    Workflow:
    1. Extract driving frames from video_a (effective_video_path).
    2. Load reference character image from image_a or image_path_a.
    3. Run YOLO+ViTPose preprocessing to extract pose, face, bg, masks.
    4. Generate debug overlay video (skeleton + face bbox).
    5. Run WanAnimatePipeline inference.
    6. Encode output video.

    Returns:
        Standard 6-tuple: (images_tensor, audio_out, output_path, cmd_log, analysis, mask_overlay_path)
    """
    import asyncio
    import tempfile

    cmd_log = "🎭 Wan-Animate Mode\n"

    # ── Validate inputs ──────────────────────────────────────────────────
    driving_video = effective_video_path
    if not driving_video or not os.path.isfile(driving_video):
        raise ValueError(
            "Wan-Animate requires a driving video. Connect a video to video_a "
            "or provide a valid video path."
        )

    # Resolve reference image
    ref_image = None
    if image_a is not None:
        if isinstance(image_a, torch.Tensor):
            if image_a.dim() == 4:
                img_np = (image_a[0].cpu().numpy() * 255).astype(np.uint8)
            else:
                img_np = (image_a.cpu().numpy() * 255).astype(np.uint8)
            ref_image = img_np
        elif isinstance(image_a, np.ndarray):
            ref_image = image_a if image_a.max() > 1 else (image_a * 255).astype(np.uint8)

    if ref_image is None and image_path_a and os.path.isfile(image_path_a):
        import cv2
        ref_image = cv2.imread(image_path_a)
        if ref_image is not None:
            ref_image = cv2.cvtColor(ref_image, cv2.COLOR_BGR2RGB)

    if ref_image is None:
        raise ValueError(
            "Wan-Animate requires a reference character image. "
            "Connect an image to image_a or provide image_path_a."
        )

    cmd_log += f"Driving video: {driving_video}\n"
    cmd_log += f"Reference image shape: {ref_image.shape}\n"

    # ── Extract driving frames ───────────────────────────────────────────
    import cv2
    cap = cv2.VideoCapture(driving_video)
    frames = []
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        frames.append(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    cap.release()

    if not frames:
        raise ValueError("Could not read any frames from driving video.")

    cmd_log += f"Driving frames: {len(frames)}, FPS: {fps:.1f}\n"

    # ── Preprocessing ────────────────────────────────────────────────────
    from ..core.wan_animate_preprocess import WanAnimatePreprocessor

    preprocessor = WanAnimatePreprocessor(device="cuda")
    mode = kwargs.get("wan_animate_mode", "animate")
    cmd_log += f"Mode: {mode}\n"

    try:
        preprocess_result = preprocessor.preprocess(
            frames=frames,
            refer_image=ref_image,
            mode=mode,
        )
    except FileNotFoundError as e:
        raise RuntimeError(
            f"Wan-Animate model files missing: {e}\n"
            "Download the ONNX models to models/wan_animate/det/ and models/wan_animate/pose2d/"
        ) from e

    pose_frames = preprocess_result["pose_frames"]
    face_frames = preprocess_result["face_frames"]
    debug_frames = preprocess_result["debug_frames"]
    ref_processed = preprocess_result["ref_image"]

    cmd_log += f"Preprocessed: {len(pose_frames)} pose, {len(face_frames)} face frames\n"

    # ── Debug overlay video ──────────────────────────────────────────────
    debug_video_path = ""
    if debug_frames:
        debug_dir = tempfile.mkdtemp(prefix="wan_animate_debug_")
        debug_video_path = os.path.join(debug_dir, "debug_overlay.mp4")
        _encode_frames_to_video(debug_frames, debug_video_path, fps=fps)
        cmd_log += f"Debug overlay: {debug_video_path}\n"

    # ── Inference ────────────────────────────────────────────────────────
    from ..core.wan_animate_synthesizer import animate as wan_animate_infer, cleanup as wan_cleanup

    num_steps = int(kwargs.get("wan_animate_steps", 20))
    guidance = float(kwargs.get("wan_animate_guidance", 1.0))
    seed = int(kwargs.get("wan_animate_seed", 42))
    num_frames = int(kwargs.get("wan_animate_num_frames", min(len(pose_frames), 81)))
    target_h = int(kwargs.get("wan_animate_height", 480))
    target_w = int(kwargs.get("wan_animate_width", 832))
    pose_strength = float(kwargs.get("wan_animate_pose_strength", 1.0))
    face_strength = float(kwargs.get("wan_animate_face_strength", 1.0))
    prompt = str(kwargs.get("prompt", ""))

    # Collect LoRA entries from dynamic slots (a → d)
    lora_entries = []  # list of (path, strength) tuples
    for slot in ("a", "b", "c", "d"):
        lora_name = str(kwargs.get(f"wan_animate_lora_{slot}", "none"))
        if not lora_name or lora_name == "none":
            break  # stop at first empty slot
        lora_strength = float(kwargs.get(f"wan_animate_lora_strength_{slot}", 1.0))
        lora_path = None
        try:
            import folder_paths  # type: ignore
            lora_path = folder_paths.get_full_path("loras", lora_name)
        except Exception:
            for search_dir in [
                os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
                    os.path.dirname(os.path.abspath(__file__))))), "models", "loras"),
            ]:
                candidate = os.path.join(search_dir, lora_name)
                if os.path.isfile(candidate):
                    lora_path = candidate
                    break
        if lora_path:
            lora_entries.append((lora_path, lora_strength))
            cmd_log += f"LoRA {slot.upper()}: {lora_name} (strength={lora_strength})\n"
        else:
            cmd_log += f"⚠️ LoRA {slot.upper()} not found: {lora_name} — skipping\n"

    h, w = target_h, target_w

    cmd_log += f"Inference: {num_frames} frames, {w}x{h}, steps={num_steps}, cfg={guidance}\n"
    if prompt:
        cmd_log += f"Prompt: {prompt[:80]}{'...' if len(prompt) > 80 else ''}\n"

    try:
        output_frames = wan_animate_infer(
            ref_image=ref_processed,
            pose_frames=pose_frames,
            face_frames=face_frames,
            bg_frames=preprocess_result.get("bg_frames"),
            mask_frames=preprocess_result.get("mask_frames"),
            mode=mode,
            prompt=prompt,
            num_inference_steps=num_steps,
            guidance_scale=guidance,
            seed=seed,
            width=w,
            height=h,
            num_frames=num_frames,
            pose_strength=pose_strength,
            face_strength=face_strength,
            lora_entries=lora_entries,
        )
    finally:
        preprocessor.cleanup()
        wan_cleanup()

    cmd_log += f"Generated {len(output_frames)} output frames\n"

    # ── Encode output ────────────────────────────────────────────────────
    # Build the output path if not provided (common in no-LLM modes)
    if not output_path:
        output_path, _temp_render_dir = build_output_path(
            effective_video_path=effective_video_path,
            video_metadata=video_metadata,
            output_path=output_path,
            save_output=save_output,
        )
    _encode_frames_to_video(output_frames, output_path, fps=fps)
    cmd_log += f"Output: {output_path}\n"

    # ── Collect output tensor/audio ──────────────────────────────────────
    try:
        from ..ffmpega_media_converter import MediaConverter
        mc = MediaConverter()
    except ImportError:
        try:
            from ffmpega_media_converter import MediaConverter  # type: ignore
            mc = MediaConverter()
        except Exception:
            mc = None

    unique_id = str(kwargs.get("unique_id", ""))
    hidden_prompt = kwargs.get("hidden_prompt") or {}
    images_tensor, audio_out = collect_frame_output(
        media_converter=mc,
        output_path=output_path,
        unique_id=unique_id,
        hidden_prompt=hidden_prompt,
        removes_audio=False,
    )

    # ── Analysis string ──────────────────────────────────────────────────
    analysis = (
        f"🎭 Wan-Animate — Video-Driven Character Animation\n"
        f"Mode: {mode}\n"
        f"Driving frames: {len(frames)}\n"
        f"Output frames: {len(output_frames)}\n"
        f"Resolution: {w}×{h}\n"
        f"Steps: {num_steps}, CFG: {guidance}\n"
        f"Seed: {seed}\n"
    )
    if debug_video_path:
        analysis += f"\nDebug overlay: {debug_video_path}"

    return (images_tensor, audio_out, output_path, cmd_log, analysis, debug_video_path)


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
        from ..core.bin_paths import get_ffmpeg_bin
        ffmpeg_bin = get_ffmpeg_bin()
    except (ImportError, Exception):
        ffmpeg_bin = "ffmpeg"

    cmd = [
        ffmpeg_bin, "-y", "-f", "rawvideo",
        "-vcodec", "rawvideo", "-s", f"{w}x{h}",
        "-pix_fmt", "rgb24",
        # Explicit full-range BT.709 color space to prevent
        # color darkening during RGB → YUV conversion.
        "-color_range", "pc",
        "-colorspace", "rgb",
        "-color_primaries", "bt709",
        "-color_trc", "iec61966-2-1",  # sRGB transfer
        "-r", str(fps),
        "-i", "-",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        # Preserve full color range in output
        "-color_range", "pc",
        "-crf", "18", "-preset", "fast",
        output_path,
    ]
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

async def process_phyfps_only(
    # dependencies
    media_converter,
    # parameters
    effective_video_path: str,
    video_metadata,
    save_output: bool,
    output_path: str,
    preview_mode: bool,
    quality_preset: str,
    crf: int,
    encoding_preset: str,
    phyfps_action: str = "analyze_only",
    temp_video_from_images: Optional[str] = None,
    temp_video_with_audio: Optional[str] = None,
    **kwargs,
) -> tuple[torch.Tensor, dict, str, str, str, str]:
    """Run Visual Chronometer PhyFPS analysis and optional re-timing correction.

    Returns the standard 6-tuple:
        (images_tensor, audio, output_path, command_log, analysis, mask_overlay_path)
    """
    try:
        from ..core import phyfps_synthesizer
    except ImportError:
        from core import phyfps_synthesizer  # type: ignore

    try:
        from ..core.bin_paths import get_ffprobe_bin
    except ImportError:
        from core.bin_paths import get_ffprobe_bin  # type: ignore

    logger.info("PhyFPS mode: action=%s, video=%s", phyfps_action, effective_video_path)

    # --- Build output path ---
    output_path, temp_render_dir = build_output_path(
        effective_video_path=effective_video_path,
        save_output=save_output,
        output_path=output_path,
        preview_mode=preview_mode,
    )

    # --- Get container FPS ---
    container_fps = 24.0
    ffprobe = get_ffprobe_bin()
    if ffprobe:
        try:
            probe_result = subprocess.run(
                [ffprobe, "-v", "error", "-select_streams", "v:0",
                 "-show_entries", "stream=r_frame_rate",
                 "-of", "csv=p=0", effective_video_path],
                capture_output=True, text=True, timeout=10,
            )
            fps_str = probe_result.stdout.strip().split("\n")[0].strip()
            if "/" in fps_str:
                num, den = fps_str.split("/")
                container_fps = float(num) / float(den) if float(den) > 0 else 24.0
            elif fps_str:
                container_fps = float(fps_str)
        except Exception as e:
            logger.warning("Failed to probe container FPS: %s", e)

    # --- Run PhyFPS prediction ---
    results, avg_phyfps, total_frames = phyfps_synthesizer.predict_phyfps(
        video_path=effective_video_path,
        clip_length=30,
        stride=4,
        resolution=216,
    )

    corrected = False
    cmd_log = ""

    if phyfps_action == "correct" and abs(avg_phyfps / container_fps - 1.0) >= 0.05:
        # Re-time the video
        phyfps_synthesizer.correct_video(
            video_path=effective_video_path,
            container_fps=container_fps,
            phyfps=avg_phyfps,
            output_path=output_path,
        )
        corrected = True
        cmd_log = f"PhyFPS correction: {container_fps:.1f} → {avg_phyfps:.1f} fps (factor={avg_phyfps/container_fps:.3f})"
    else:
        # Just copy the video through
        _ffmpeg = _get_ffmpeg_bin()
        copy_cmd = [_ffmpeg, "-y", "-i", effective_video_path, "-c", "copy", output_path]
        subprocess.run(copy_cmd, capture_output=True, check=True)
        cmd_log = " ".join(copy_cmd)

    # Offload model after inference
    phyfps_synthesizer.offload_to_cpu()

    # --- Build analysis string ---
    video_name = os.path.basename(effective_video_path)
    analysis = phyfps_synthesizer.build_analysis_string(
        video_name=video_name,
        results=results,
        avg_phyfps=avg_phyfps,
        container_fps=container_fps,
        total_frames=total_frames,
        corrected=corrected,
    )

    # --- Collect frame/audio output ---
    unique_id = str(kwargs.get("unique_id", ""))
    hidden_prompt = kwargs.get("hidden_prompt") or {}
    images_tensor, audio_out = collect_frame_output(
        media_converter=media_converter,
        output_path=output_path,
        unique_id=unique_id,
        hidden_prompt=hidden_prompt,
        removes_audio=not bool(video_metadata.primary_audio),
    )

    # --- Cleanup temp files ---
    for tmp_path in [temp_video_from_images, temp_video_with_audio]:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
    if not save_output and temp_render_dir and os.path.isdir(temp_render_dir):
        if not os.listdir(temp_render_dir):
            shutil.rmtree(temp_render_dir, ignore_errors=True)

    return (images_tensor, audio_out, output_path, cmd_log, analysis, "")

