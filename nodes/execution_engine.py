"""Pipeline execution engine extracted from FFMPEGAgentNode.

Provides ``execute_pipeline()`` and ``verify_output()``
which were formerly ``_execute_pipeline`` and ``_verify_output``
on the agent node class.
"""

import asyncio
import json
import logging
import re
from typing import Optional

logger = logging.getLogger("ffmpega")

# Model-based skills that are too expensive to retry via LLM re-generation
_MODEL_SKILLS = frozenset({
    "auto_mask", "auto_segment", "segment", "smart_mask",
    "sam2", "sam_mask", "ai_mask", "object_mask",
})


async def execute_pipeline(
    pipeline,
    command,
    connector,
    composer,
    process_manager,
    pipeline_generator,
    prompt: str,
    metadata_str: str,
    connected_inputs_str: str,
    effective_video_path: str,
    output_path: str,
    quality_preset: str,
    crf: int,
    encoding_preset: str,
    preview_mode: bool,
    verify_output: bool,
    use_vision: bool,
    ptc_mode: str,
    video_metadata,
    _all_text_inputs: list,
):
    """Dry-run validate, execute, retry on error, and optionally verify output.

    Parameters
    ----------
    composer : SkillComposer
    process_manager : ProcessManager
    pipeline_generator : PipelineGenerator

    Returns
    -------
    (result, pipeline, command)
    """
    try:
        from ..skills.composer import Pipeline  # type: ignore[import-not-found]
    except ImportError:
        from skills.composer import Pipeline  # type: ignore

    # FPS normalization for speed changes
    vf_str = command.video_filters.to_string()
    if "setpts=" in vf_str and not command.complex_filter:
        input_fps = (
            video_metadata.primary_video.frame_rate
            if video_metadata.primary_video and video_metadata.primary_video.frame_rate
            else 30
        )
        command.video_filters.add_filter("fps", {"fps": int(round(input_fps))})

    logger.debug("Command: %s", command.to_string())
    logger.debug("Audio filters: '%s'", command.audio_filters.to_string())
    logger.debug("Video filters: '%s'", command.video_filters.to_string())
    if command.complex_filter:
        logger.debug("Complex filter: '%s'", command.complex_filter)
    logger.debug("Pipeline steps: %s", [(s.skill_name, s.params) for s in pipeline.steps])

    # Dry-run validation
    dry_result = process_manager.dry_run(command, timeout=30)
    if not dry_result.success:
        logger.warning("Dry-run failed: %s (will attempt execution anyway)", dry_result.error_message)

    # Preview downscale
    if preview_mode:
        if command.complex_filter:
            command.output_options.extend(["-s", "480x270"])
        else:
            command.video_filters.add_filter("scale", {"w": 480, "h": -1})
        command.output_options.extend(["-t", "10"])

    # Execute with error-feedback retry
    max_attempts = 2
    result = None

    # Detect pipelines with expensive model-based skills.  When ffmpeg
    # fails for these pipelines, re-generating via LLM typically produces
    # the same broken filter graph while also re-running SAM3/FLUX Klein
    # (minutes of GPU time).  Skip retry — fail fast with a clear error.
    _has_model_skills = any(
        s.skill_name in _MODEL_SKILLS for s in pipeline.steps
    )
    if _has_model_skills:
        max_attempts = 1

    for attempt in range(max_attempts):
        result = process_manager.execute(command, timeout=600)
        if result.success:
            break
        if attempt < max_attempts - 1:
            logger.warning(
                "FFMPEG failed (attempt %d), feeding error back to LLM: %s",
                attempt + 1, result.error_message,
            )
            error_prompt = (
                f"The previous FFMPEG command failed.\n"
                f"Original request: {prompt}\n"
                f"Failed command: {command.to_string()}\n"
                f"Error: {result.error_message}\n"
                f"Stderr: {result.stderr[-500:] if result.stderr else 'N/A'}\n\n"
                f"Please fix the pipeline to avoid this error. "
                f"Return only the corrected pipeline JSON."
            )
            try:
                retry_spec = await pipeline_generator.generate(
                    connector, error_prompt, metadata_str,
                    connected_inputs=connected_inputs_str,
                    video_path=effective_video_path,
                    use_vision=use_vision,
                    ptc_mode=ptc_mode,
                )
                pipeline = Pipeline(
                    input_path=effective_video_path,
                    output_path=output_path,
                    extra_inputs=pipeline.extra_inputs,
                    metadata=pipeline.metadata,
                )
                pipeline.text_inputs = _all_text_inputs
                for step in retry_spec.get("pipeline", []):
                    skill_name = step.get("skill")
                    params = step.get("params", {})
                    if skill_name:
                        pipeline.add_step(skill_name, params)
                if quality_preset and not any(
                    s.skill_name in ["quality", "compress"] for s in pipeline.steps
                ):
                    _crf_map = {"draft": 28, "standard": 23, "high": 18, "lossless": 0}
                    _preset_map = {"draft": "ultrafast", "standard": "medium", "high": "slow", "lossless": "veryslow"}
                    pipeline.add_step("quality", {
                        "crf": crf if crf >= 0 else _crf_map.get(quality_preset, 23),
                        "preset": encoding_preset if encoding_preset != "auto" else _preset_map.get(quality_preset, "medium"),
                    })
                command = composer.compose(pipeline)
                retry_vf = command.video_filters.to_string()
                if "setpts=" in retry_vf and not command.complex_filter:
                    _input_fps = (
                        video_metadata.primary_video.frame_rate
                        if video_metadata.primary_video and video_metadata.primary_video.frame_rate
                        else 30
                    )
                    command.video_filters.add_filter("fps", {"fps": int(round(_input_fps))})
                logger.debug("Retry command: %s", command.to_string())
                if preview_mode:
                    if command.complex_filter:
                        command.output_options.extend(["-s", "480x270"])
                    else:
                        command.video_filters.add_filter("scale", {"w": 480, "h": -1})
                    command.output_options.extend(["-t", "10"])
            except Exception as retry_err:
                logger.warning("Error feedback retry failed: %s", retry_err)
                break


    assert result is not None, "No execution attempt was made"
    if not result.success:
        if hasattr(connector, 'close'):
            await connector.close()
        raise RuntimeError(
            f"FFMPEG execution failed: {result.error_message}\n"
            f"Command: {command.to_string()}"
        )

    # Output verification
    _VERIFICATION_TIMEOUT = 90.0
    _MAX_CORRECTION_ATTEMPTS = 2
    _skill_degraded = pipeline.metadata.get("_skill_degraded", False)
    if _skill_degraded:
        logger.info("Skipping output verification — skill handler reported degraded output (e.g. SAM3 OOM fallback)")
    elif _has_model_skills:
        logger.info("Skipping output verification — pipeline has model-based skills (SAM3/FLUX Klein); re-execution too expensive")
    elif verify_output and result.success:
        logger.info("Output verification enabled — inspecting result...")
        for attempt in range(_MAX_CORRECTION_ATTEMPTS):
            try:
                verification_result = await asyncio.wait_for(
                    _verify_output(
                        connector=connector,
                        output_path=output_path,
                        prompt=prompt,
                        pipeline=pipeline,
                        effective_video_path=effective_video_path,
                        use_vision=use_vision,
                        composer=composer,
                        process_manager=process_manager,
                        pipeline_generator=pipeline_generator,
                    ),
                    timeout=_VERIFICATION_TIMEOUT,
                )
                if verification_result is not None:
                    result, pipeline, command = verification_result
                    logger.info("Correction attempt %d applied — re-verifying...", attempt + 1)
                    continue
                else:
                    logger.info("Verification PASS (attempt %d)", attempt + 1)
                    break
            except asyncio.TimeoutError:
                logger.warning(
                    "Output verification timed out after %.0fs — keeping current output",
                    _VERIFICATION_TIMEOUT,
                )
                break
            except Exception as verify_err:
                logger.warning("Output verification failed: %s", verify_err)
                break

    return result, pipeline, command


async def _verify_output(
    connector,
    output_path: str,
    prompt: str,
    pipeline,
    effective_video_path: str,
    use_vision: bool,
    composer,
    process_manager,
    pipeline_generator,
) -> Optional[tuple]:
    """Run output verification via LLM and optionally correct the pipeline.

    Returns:
        A tuple of (result, pipeline, command) if a correction was applied,
        or None if the original output is fine (PASS or unparseable).
    """
    try:
        from ..mcp.tools import extract_frames as _extract_frames
        from ..mcp.tools import analyze_colors as _analyze_colors
        from ..mcp.tools import cleanup_vision_frames as _cleanup_frames
        from ..mcp.vision import frames_to_base64 as _frames_to_b64
        from ..mcp.vision import frames_to_base64_raw_strings as _frames_to_b64_raw
        from ..mcp.vision import generate_audio_visualization as _gen_audio_viz
        from ..prompts.system import get_verification_prompt
        from ..skills.composer import Pipeline
        from ..core.llm.ollama import OllamaConnector as _OllamaConnector
    except ImportError:
        from mcp.tools import extract_frames as _extract_frames
        from mcp.tools import analyze_colors as _analyze_colors
        from mcp.tools import cleanup_vision_frames as _cleanup_frames
        from mcp.vision import frames_to_base64 as _frames_to_b64
        from mcp.vision import frames_to_base64_raw_strings as _frames_to_b64_raw
        from mcp.vision import generate_audio_visualization as _gen_audio_viz
        from prompts.system import get_verification_prompt
        from skills.composer import Pipeline
        from core.llm.ollama import OllamaConnector as _OllamaConnector

    # Extract 3 frames from output — fewer to save tokens for audio viz
    verify_frames = _extract_frames(
        video_path=output_path,
        start=2.0,
        duration=9999,  # full video
        fps=0.5,
        max_frames=3,
    )
    verify_run_id = verify_frames.get("run_id")

    # --- Audio visualization (only for pipelines with audio skills) ---
    _AUDIO_SKILLS = {
        "normalize", "fade_audio", "replace_audio", "bass", "treble",
        "echo", "noise_reduction", "volume", "audio_bitrate",
        "compress_audio", "lowpass", "highpass", "remove_audio",
        "loudnorm", "audio_speed", "reverb",
    }
    has_audio_skills = any(
        s.skill_name in _AUDIO_SKILLS for s in pipeline.steps
    )
    audio_viz = None
    audio_viz_folder = None
    if has_audio_skills:
        try:
            audio_viz = _gen_audio_viz(output_path)
            audio_viz_folder = audio_viz.get("folder")
        except Exception as e:
            logger.warning(f"Audio visualization failed: {e}")

    try:
        # Build output analysis data
        if use_vision and verify_frames.get("paths"):
            b64_data = _frames_to_b64(verify_frames["paths"], max_size=256)
            output_data = (
                f"Extracted {len(verify_frames['paths'])} frames from output.\n"
                f"[Vision frames are embedded in this message]"
            )

            # Add audio visualization images if available
            if audio_viz:
                audio_image_paths = []
                if audio_viz.get("waveform_path"):
                    audio_image_paths.append(audio_viz["waveform_path"])
                if audio_viz.get("spectrogram_path"):
                    audio_image_paths.append(audio_viz["spectrogram_path"])
                if audio_image_paths:
                    audio_b64 = _frames_to_b64(audio_image_paths, max_size=256)
                    b64_data.extend(audio_b64)

                # Add audio metrics as text
                metrics = audio_viz.get("audio_metrics", {})
                if metrics.get("has_audio"):
                    output_data += (
                        f"\n\n## Audio Analysis\n"
                        f"[Waveform and spectrogram images are embedded — "
                        f"the waveform shows amplitude over time (fades visible "
                        f"as tapered ends, silence as flat lines), the spectrogram "
                        f"shows frequency content (bass=bottom, treble=top)]\n"
                        f"{json.dumps(metrics, indent=2)}"
                    )
                elif not metrics.get("has_audio"):
                    output_data += (
                        "\n\n## Audio Analysis\n"
                        "No audio stream found in output."
                    )
        else:
            color_data = _analyze_colors(video_path=output_path)
            output_data = (
                f"Color analysis of output:\n"
                f"{json.dumps(color_data, indent=2)}"
            )
            b64_data = None

            # Add audio metrics as text even without vision
            if audio_viz:
                metrics = audio_viz.get("audio_metrics", {})
                if metrics:
                    output_data += (
                        f"\n\nAudio analysis:\n"
                        f"{json.dumps(metrics, indent=2)}"
                    )

        # Build pipeline summary
        pipeline_summary = composer.explain_pipeline(pipeline)

        # Build verification prompt
        verify_prompt = get_verification_prompt(
            prompt=prompt,
            pipeline_summary=pipeline_summary,
            output_data=output_data,
        )

        # Send to LLM — use chat_with_tools for vision (multimodal),
        # or generate() for text-only
        if b64_data:
            _is_ollama = isinstance(connector, _OllamaConnector)
            if _is_ollama:
                # Ollama requires raw base64 strings in an 'images'
                # field — NOT OpenAI-style multimodal content blocks.
                raw_b64 = _frames_to_b64_raw(
                    verify_frames["paths"], max_size=256
                )
                # Add audio viz frames if available
                if audio_viz:
                    audio_paths = []
                    if audio_viz.get("waveform_path"):
                        audio_paths.append(audio_viz["waveform_path"])
                    if audio_viz.get("spectrogram_path"):
                        audio_paths.append(audio_viz["spectrogram_path"])
                    if audio_paths:
                        raw_b64.extend(_frames_to_b64_raw(
                            audio_paths, max_size=256
                        ))
                verify_msg = {
                    "role": "user",
                    "content": verify_prompt,
                    "images": raw_b64,
                }
                verify_messages = [verify_msg]
                logger.info(
                    "Verification: sending %d images via Ollama "
                    "native format", len(raw_b64),
                )
            else:
                content_parts = [{"type": "text", "text": verify_prompt}]
                for img_block in b64_data:
                    content_parts.append(img_block)
                verify_messages = [
                    {"role": "user", "content": content_parts}
                ]
            verify_response = await connector.chat_with_tools(
                verify_messages, tools=[],
            )
        else:
            verify_response = await connector.generate(
                verify_prompt,
                system_prompt="You are a video and audio quality reviewer.",
            )

        verify_text = (verify_response.content or "").strip()
        logger.info(f"Verification result: {verify_text}")

        if verify_text.upper() == "PASS":
            logger.info("Output verification: PASS — output looks good")
            return None

        # Try to parse corrected pipeline — strip markdown fences first
        cleaned = verify_text
        # Remove ```json ... ``` or ``` ... ``` fencing
        fence_match = re.search(
            r'```(?:json)?\s*(\{.*\})\s*```', cleaned, re.DOTALL
        )
        if fence_match:
            cleaned = fence_match.group(1).strip()

        corrected = None
        try:
            corrected = json.loads(cleaned)
        except (json.JSONDecodeError, ValueError):
            # Fall back to the general extractor
            corrected = pipeline_generator.parse_response(verify_text)

        if corrected and corrected.get("pipeline"):
            logger.warning(
                "Output verification: NEEDS CORRECTION — "
                "re-executing with corrected pipeline"
            )
            # Rebuild and re-execute
            fix_pipeline = Pipeline(
                input_path=effective_video_path,
                output_path=output_path,
                extra_inputs=pipeline.extra_inputs,
                metadata=pipeline.metadata,
            )
            for step in corrected.get("pipeline", []):
                skill_name = step.get("skill")
                params = step.get("params", {})
                if skill_name:
                    fix_pipeline.add_step(skill_name, params)
            fix_command = composer.compose(fix_pipeline)
            fix_result = process_manager.execute(
                fix_command, timeout=600
            )
            if fix_result.success:
                logger.info(
                    "Verification fix succeeded — using corrected output"
                )
                logger.info(
                    "Corrected command: %s", fix_command.to_string()
                )
                logger.info(
                    "Corrected pipeline:\n%s",
                    composer.explain_pipeline(fix_pipeline),
                )
                return (fix_result, fix_pipeline, fix_command)
            else:
                logger.warning(
                    f"Verification fix failed: {fix_result.error_message} "
                    "— keeping original output"
                )
                return None
        else:
            logger.info(
                "Verification response was not PASS or valid JSON "
                "— keeping original output"
            )
            if corrected:
                logger.debug(
                    f"Parsed verification response (no pipeline key): "
                    f"{corrected}"
                )
            else:
                logger.debug(
                    f"Could not parse verification response: "
                    f"{verify_text[:500]}"
                )
            return None
    finally:
        # Cleanup verification frames
        if verify_run_id:
            try:
                _cleanup_frames(verify_run_id)
            except Exception:
                pass
        # Cleanup audio visualization files
        if audio_viz_folder:
            try:
                import shutil
                shutil.rmtree(audio_viz_folder, ignore_errors=True)
            except Exception:
                pass
