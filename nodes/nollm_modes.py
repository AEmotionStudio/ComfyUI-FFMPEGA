"""No-LLM mode handlers extracted from FFMPEGAgentNode.

Provides ``inject_effects_hints()``, ``process_effects_pipeline()``,
``process_sam3_only()``, ``process_whisper_only()``, and
``process_mmaudio_only()`` — all the codepaths that run without an LLM.
"""

import atexit
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

    if effects_mode == "empty" and not raw_ffmpeg:
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
        for raw_filter in raw_ffmpeg.strip().split(","):
            raw_filter = raw_filter.strip()
            if raw_filter:
                # Parse "name=params" into a Filter object
                if "=" in raw_filter:
                    name, _, param_str = raw_filter.partition("=")
                    command.video_filters.add_filter(name.strip(), {"": param_str})
                else:
                    command.video_filters.add_filter(raw_filter)
        logger.info("Effects Builder: appended raw filters: %s", raw_ffmpeg.strip())

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
    images_tensor, audio_out = collect_frame_output(
        media_converter=media_converter,
        output_path=output_path,
        unique_id=unique_id,
        hidden_prompt=hidden_prompt,
        removes_audio="-an" in command.output_options,
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
            atexit.register(os.unlink, tmp.name)

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
            atexit.register(os.unlink, tmp.name)

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


async def process_mmaudio_only(
    # dependencies
    media_converter,
    # parameters
    prompt: str,
    mmaudio_mode: str,
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
        mmaudio_mode: "replace" to discard original audio, "mix" to blend.

    Returns the standard 6-tuple:
        (images_tensor, audio, output_path, command_log, analysis, mask_overlay_path)
    """
    logger.info(
        "MMAudio-only mode: prompt=%r, mode=%s", prompt, mmaudio_mode,
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

    # --- Build ffmpeg command to mux generated audio ---
    _ffmpeg = _get_ffmpeg_bin()
    effective_crf = crf if crf >= 0 else _CRF_MAP.get(quality_preset, 23)
    effective_preset = encoding_preset if encoding_preset != "auto" else _PRESET_MAP.get(quality_preset, "medium")

    if mmaudio_mode == "mix" and has_audio:
        # Mix generated audio with original audio
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
        if mmaudio_mode == "mix" and has_audio:
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
            f"Audio mode: {mmaudio_mode}\n"
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
