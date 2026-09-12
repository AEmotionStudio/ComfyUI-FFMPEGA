# coding: utf-8
"""No-LLM mode: effects pipeline.

Moved verbatim from nodes/nollm_modes.py, which is now a re-export facade.
"""

from __future__ import annotations

from ._shared import (
    Optional,
    _CRF_MAP,
    _PRESET_MAP,
    build_output_path,
    collect_frame_output,
    json,
    logger,
    os,
    shutil,
    torch,
)


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
        from ...skills.composer import Pipeline  # type: ignore[import-not-found]
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
                    from ...core.sam3_masker import generate_mask_overlay
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
