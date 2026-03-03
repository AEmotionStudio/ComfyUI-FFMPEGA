"""Pipeline assembly helpers extracted from FFMPEGAgentNode.

Provides ``generate_pipeline_spec()`` and ``assemble_pipeline()``
which were formerly inline in the ``process()`` method of the agent node.
"""

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger("ffmpega")


async def generate_pipeline_spec(
    pipeline_generator,
    prompt: str,
    metadata_str: str,
    connected_inputs_str: str,
    effective_video_path: str,
    llm_model: str,
    custom_model: str,
    ollama_url: str,
    api_key: str,
    use_vision: bool,
    ptc_mode: str,
) -> tuple[dict, object]:
    """Create LLM connector, generate pipeline spec, return (spec, connector).

    Parameters
    ----------
    pipeline_generator : PipelineGenerator
        The pipeline generator to use.

    Returns
    -------
    (spec, connector)
        The LLM-generated pipeline spec dict and the connector (for later close).

    Raises
    ------
    ValueError
        If ``llm_model`` is ``"custom"`` but ``custom_model`` is empty.
    RuntimeError
        If the LLM call fails and the error contains an API key.
    """
    if not ollama_url or not ollama_url.startswith(("http://", "https://")):
        ollama_url = "http://localhost:11434"
    effective_model = llm_model
    if llm_model == "custom":
        if not custom_model or not custom_model.strip():
            raise ValueError(
                "Please enter a model name in the 'custom_model' field "
                "when using 'custom' mode."
            )
        effective_model = custom_model.strip()
    connector = pipeline_generator.create_connector(effective_model, ollama_url, api_key)

    try:
        spec = await pipeline_generator.generate(
            connector, prompt, metadata_str,
            connected_inputs=connected_inputs_str,
            video_path=effective_video_path,
            use_vision=use_vision,
            ptc_mode=ptc_mode,
        )
    except Exception as e:
        if hasattr(connector, 'close'):
            await connector.close()  # type: ignore[union-attr]
        if api_key and api_key in str(e):
            from core.sanitize import sanitize_api_key
            raise RuntimeError(sanitize_api_key(str(e), api_key)) from None
        raise

    return spec, connector


def assemble_pipeline(
    Pipeline,
    spec: dict,
    effective_video_path: str,
    output_path: str,
    video_metadata,
    quality_preset: str,
    crf: int,
    encoding_preset: str,
    whisper_device: str,
    whisper_model: str,
    sam3_device: str,
    sam3_max_objects: int,
    sam3_det_threshold: float,
    mask_points: str,
    composer,
) -> tuple:
    """Build a Pipeline from the LLM spec and apply quality/format/metadata.

    Parameters
    ----------
    Pipeline : type
        The Pipeline class to instantiate.
    spec : dict
        LLM-generated pipeline spec with ``pipeline``, ``interpretation``, etc.
    composer : SkillComposer
        Used for pipeline validation.

    Returns
    -------
    (pipeline, output_path, interpretation, warnings, estimated_changes,
     audio_source, audio_mode)
    """
    interpretation = spec.get("interpretation", "")
    warnings = spec.get("warnings", [])
    estimated_changes = spec.get("estimated_changes", "")
    pipeline_steps = spec.get("pipeline", [])
    audio_source = spec.get("audio_source", "mix")
    audio_mode = spec.get("audio_mode", "loop")
    if audio_mode not in ("loop", "pad", "trim"):
        audio_mode = "loop"
    logger.debug("audio_source from LLM: %s, audio_mode: %s", audio_source, audio_mode)

    # --- Assemble pipeline object ---
    pipeline = Pipeline(input_path=effective_video_path, output_path=output_path)
    input_fps = (
        video_metadata.primary_video.frame_rate
        if video_metadata.primary_video and video_metadata.primary_video.frame_rate
        else 24
    )
    pipeline.metadata["_input_fps"] = int(round(input_fps))
    input_duration = (
        video_metadata.primary_video.duration
        if video_metadata.primary_video and video_metadata.primary_video.duration
        else 0
    )
    if input_duration:
        pipeline.metadata["_video_duration"] = input_duration
    if video_metadata.primary_video:
        pipeline.metadata["_input_width"] = video_metadata.primary_video.width
        pipeline.metadata["_input_height"] = video_metadata.primary_video.height

    for step in pipeline_steps:
        skill_name = step.get("skill")
        params = step.get("params", {})
        if skill_name:
            pipeline.add_step(skill_name, params)

    # Fix format-changing skill output extension
    _FORMAT_SKILLS = {"gif": ".gif", "webm": ".webm"}
    new_ext: Optional[str] = None
    for step in pipeline.steps:
        if step.skill_name in _FORMAT_SKILLS:
            new_ext = _FORMAT_SKILLS[step.skill_name]
        elif step.skill_name == "container":
            fmt = step.params.get("format", "mp4")
            new_ext = f".{fmt}"
    if new_ext and not output_path.endswith(new_ext):
        old_path = output_path
        output_path = str(Path(output_path).with_suffix(new_ext))
        pipeline.output_path = output_path
        logger.debug("Output format changed: %s → %s", old_path, output_path)

    # Add quality preset
    _NO_QUALITY_PRESET_SKILLS = {"gif", "webm"}
    has_incompatible_format = any(
        s.skill_name in _NO_QUALITY_PRESET_SKILLS for s in pipeline.steps
    ) or (new_ext and new_ext in {".gif", ".webm"})
    if quality_preset and not has_incompatible_format and not any(
        s.skill_name in ["quality", "compress"] for s in pipeline.steps
    ):
        crf_map = {"draft": 28, "standard": 23, "high": 18, "lossless": 0}
        preset_map = {"draft": "ultrafast", "standard": "medium", "high": "slow", "lossless": "veryslow"}
        pipeline.add_step("quality", {
            "crf": crf if crf >= 0 else crf_map.get(quality_preset, 23),
            "preset": encoding_preset if encoding_preset != "auto" else preset_map.get(quality_preset, "medium"),
        })

    # Validate pipeline
    is_valid, errors = composer.validate_pipeline(pipeline)
    if not is_valid:
        for err in errors:
            logger.warning("Pipeline validation: %s (continuing anyway)", err)

    # Pass whisper/SAM3 preferences
    has_transcribe_skill = any(
        s.skill_name in {"auto_transcribe", "transcribe", "speech_to_text",
                         "karaoke_subtitles", "whisper", "auto_subtitle", "auto_caption"}
        for s in pipeline.steps
    )
    if has_transcribe_skill:
        pipeline.metadata["_whisper_device"] = whisper_device
        pipeline.metadata["_whisper_model"] = whisper_model
    pipeline.metadata["_sam3_device"] = sam3_device
    pipeline.metadata["_sam3_max_objects"] = sam3_max_objects
    pipeline.metadata["_sam3_det_threshold"] = sam3_det_threshold
    if mask_points and mask_points.strip():
        pipeline.metadata["_mask_points"] = mask_points.strip()

    return (pipeline, output_path, interpretation, warnings, estimated_changes,
            audio_source, audio_mode)
