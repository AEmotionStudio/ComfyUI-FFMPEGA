"""Skill composition engine for building FFMPEG pipelines."""

from dataclasses import dataclass, field
from typing import Optional, Any
from pathlib import Path

from .registry import SkillRegistry, Skill, SkillCategory, ParameterType, get_registry
try:
    from ..core.executor.command_builder import CommandBuilder, FFMPEGCommand
    from ..core.sanitize import sanitize_text_param
except ImportError:
    from core.executor.command_builder import CommandBuilder, FFMPEGCommand
    from core.sanitize import sanitize_text_param


@dataclass
class PipelineStep:
    """A single step in a processing pipeline."""
    skill_name: str
    params: dict[str, Any] = field(default_factory=dict)
    enabled: bool = True
    notes: Optional[str] = None


@dataclass
class Pipeline:
    """A complete processing pipeline."""
    steps: list[PipelineStep] = field(default_factory=list)
    input_path: Optional[str] = None
    output_path: Optional[str] = None
    extra_inputs: list[str] = field(default_factory=list)
    extra_audio_inputs: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def add_step(
        self,
        skill_name: str,
        params: Optional[dict] = None,
        notes: Optional[str] = None,
    ) -> "Pipeline":
        """Add a step to the pipeline.

        Args:
            skill_name: Name of the skill to apply.
            params: Parameters for the skill.
            notes: Optional notes about this step.

        Returns:
            Self for chaining.
        """
        self.steps.append(PipelineStep(
            skill_name=skill_name,
            params=params or {},
            notes=notes,
        ))
        return self

    def remove_step(self, index: int) -> "Pipeline":
        """Remove a step from the pipeline.

        Args:
            index: Index of the step to remove.

        Returns:
            Self for chaining.
        """
        if 0 <= index < len(self.steps):
            self.steps.pop(index)
        return self

    def clear(self) -> "Pipeline":
        """Clear all steps from the pipeline.

        Returns:
            Self for chaining.
        """
        self.steps.clear()
        return self


class SkillComposer:
    """Composes skills into executable FFMPEG pipelines."""

    def __init__(self, registry: Optional[SkillRegistry] = None):
        """Initialize the composer.

        Args:
            registry: Skill registry to use. Uses global registry if not provided.
        """
        self.registry = registry or get_registry()

    def compose(self, pipeline: Pipeline) -> FFMPEGCommand:
        """Compose a pipeline into an FFMPEG command.

        Args:
            pipeline: Pipeline to compose.

        Returns:
            FFMPEGCommand ready for execution.

        Raises:
            ValueError: If pipeline is invalid.
        """
        if not pipeline.input_path:
            raise ValueError("Pipeline must have an input path")
        if not pipeline.output_path:
            raise ValueError("Pipeline must have an output path")

        builder = CommandBuilder()
        builder.input(pipeline.input_path)

        # Register extra inputs for multi-input skills (grid, slideshow, overlay)
        for extra in pipeline.extra_inputs:
            builder.input(extra)

        # Process each step
        video_filters = []
        audio_filters = []
        output_options = []
        complex_filters = []  # filter_complex strings from multi-stream skills

        for step in pipeline.steps:
            if not step.enabled:
                continue

            # Resolve common aliases LLMs tend to use
            _SKILL_ALIASES = {
                "overlay": "overlay_image",
                "stabilize": "deshake",
                "grayscale": "monochrome",
                "greyscale": "monochrome",
                "black_and_white": "monochrome",
                "bw": "monochrome",
                "concatenate": "concat",
                "join": "concat",
                "transition": "xfade",
                "splitscreen": "split_screen",
                "side_by_side": "split_screen",
                "moving_overlay": "animated_overlay",
                "chroma_key": "chromakey",
                "green_screen": "chromakey",
                "luma_key": "lumakey",
                "color_hold": "colorhold",
                "sin_city": "colorhold",
                "color_key": "colorkey",
                "de_spill": "despill",
                "color_spill": "despill",
                "remove_bg": "remove_background",
                "background_removal": "remove_background",
                "text": "text_overlay",
                "drawtext": "text_overlay",
                "title": "text_overlay",
                "subtitle": "text_overlay",
                "caption": "text_overlay",
            }
            resolved_name = _SKILL_ALIASES.get(step.skill_name, step.skill_name)
            skill = self.registry.get(resolved_name)
            if skill:
                step.skill_name = resolved_name  # update for debug output
            if not skill:
                import logging
                logging.getLogger("ffmpega").warning(
                    f"Skipping unknown skill '{step.skill_name}' — "
                    "not found in registry"
                )
                continue

            # Auto-fill missing params with defaults from skill definition
            for param in skill.parameters:
                if param.name not in step.params and param.default is not None:
                    step.params[param.name] = param.default

            # Auto-coerce types from LLM (e.g. float 2.0 → int 2)
            for param in skill.parameters:
                if param.name in step.params:
                    val = step.params[param.name]
                    if param.type == ParameterType.INT:
                        try:
                            step.params[param.name] = int(float(val))
                        except (ValueError, TypeError):
                            pass
                    elif param.type == ParameterType.FLOAT:
                        try:
                            step.params[param.name] = float(val)
                        except (ValueError, TypeError):
                            pass
                    elif param.type == ParameterType.BOOL:
                        if isinstance(val, str):
                            step.params[param.name] = val.lower() in ("true", "1", "yes")

            # Auto-clamp numeric values to valid range
            for param in skill.parameters:
                if param.name in step.params:
                    val = step.params[param.name]
                    if param.type in (ParameterType.INT, ParameterType.FLOAT):
                        if isinstance(val, (int, float)):
                            if param.min_value is not None and val < param.min_value:
                                step.params[param.name] = type(val)(param.min_value)
                            if param.max_value is not None and val > param.max_value:
                                step.params[param.name] = type(val)(param.max_value)

            # Validate parameters (warn but don't fail — LLMs are imprecise)
            is_valid, errors = skill.validate_params(step.params)
            if not is_valid:
                import logging
                logger = logging.getLogger("ffmpega")
                for err in errors:
                    logger.warning(f"Skill '{step.skill_name}': {err} (continuing anyway)")

            # Enforce validation: Drop invalid parameters to prevent injection
            # (e.g. invalid CHOICE values used directly in filter strings)
            for param in skill.parameters:
                if param.name in step.params:
                    val = step.params[param.name]
                    # Note: validate_params already handled auto-correction
                    p_valid, _ = param.validate(val)
                    if not p_valid:
                        import logging
                        logger = logging.getLogger("ffmpega")
                        logger.warning(
                            f"Security/Validation: Dropping invalid parameter '{param.name}' "
                            f"value '{val}' for skill '{step.skill_name}'. Using default."
                        )
                        del step.params[param.name]

            # Inject multi-input metadata for handlers that need it
            if pipeline.extra_inputs:
                step.params["_extra_input_count"] = len(pipeline.extra_inputs)
                step.params["_extra_input_paths"] = pipeline.extra_inputs
            if pipeline.metadata.get("_has_embedded_audio"):
                step.params["_has_embedded_audio"] = True
            if "_input_fps" in pipeline.metadata:
                step.params["_input_fps"] = pipeline.metadata["_input_fps"]
            if "_video_duration" in pipeline.metadata:
                step.params["_video_duration"] = pipeline.metadata["_video_duration"]

            # Get filters/options for this skill
            vf, af, opts, fc, input_opts = self._skill_to_filters(skill, step.params)
            video_filters.extend(vf)
            audio_filters.extend(af)
            output_options.extend(opts)
            if fc:
                complex_filters.append(fc)
            if input_opts:
                # Add input options to the main input (index 0)
                builder.add_input_options(pipeline.input_path, input_opts)

        # If the pipeline strips audio (-an), discard any audio filters to
        # avoid the -af/-an conflict that causes ffmpeg to include audio.
        if "-an" in output_options:
            audio_filters.clear()

        # Apply filter_complex if any skill needs multi-stream processing
        if complex_filters:
            fc_graph = ";".join(complex_filters)

            # Merge simple video filters into the filter_complex graph
            # only when the graph actually references [0:v]
            if video_filters:
                vf_chain = ",".join(video_filters)
                if "[0:v]" in fc_graph:
                    # Prepend simple filters before the complex graph
                    fc_graph = f"[0:v]{vf_chain}[_pre];" + fc_graph.replace("[0:v]", "[_pre]")
                else:
                    # Graph doesn't use [0:v] (e.g. grid/slideshow) —
                    # apply video filters as a separate unlabeled chain
                    fc_graph += f";[0:v]{vf_chain}"

            # If filter_complex consumes [0:a] (e.g. waveform), we cannot
            # also use -af — fold audio filters into the graph instead.
            # BUT: skip this when audio is already embedded by xfade/concat
            # (their filter_complex already produced the final audio stream).
            audio_embedded = pipeline.metadata.get("_has_embedded_audio", False)
            if "[0:a]" in fc_graph and audio_filters and not audio_embedded:
                af_chain = ",".join(audio_filters)
                fc_graph += f";[0:a]{af_chain}"
                audio_filters = []  # Don't also emit -af

            builder.complex_filter(fc_graph)
            # Audio filters go via -af when not consumed by filter_complex
            for af in audio_filters:
                builder.af(af)
        else:
            # Apply filters
            for vf in video_filters:
                builder.vf(vf)
            for af in audio_filters:
                builder.af(af)

        # Apply output options — deduplicate key-value flags like -c:v, -crf,
        # -preset etc.  When multiple skills emit the same flag (e.g. two
        # quality steps) FFMPEG can error on the duplicates.
        # Strategy: last writer wins for any flag starting with '-'.
        seen_flags: dict[str, int] = {}  # flag -> index in deduped list
        deduped_opts: list[str] = []
        i = 0
        while i < len(output_options):
            opt = output_options[i]
            if opt.startswith("-") and i + 1 < len(output_options) and not output_options[i + 1].startswith("-"):
                # Key-value pair like "-c:v libx264" or "-crf 23"
                flag, val = opt, output_options[i + 1]
                # -map intentionally allows duplicates (e.g. -map 0:v -map 1:a)
                if flag == "-map" or flag not in seen_flags:
                    seen_flags[flag] = len(deduped_opts)
                    deduped_opts.extend([flag, val])
                else:
                    # Replace the earlier occurrence
                    idx = seen_flags[flag]
                    deduped_opts[idx + 1] = val  # update value
                i += 2
            else:
                # Standalone flag like "-an" or "-y"
                if opt not in seen_flags:
                    seen_flags[opt] = len(deduped_opts)
                    deduped_opts.append(opt)
                i += 1

        builder.output_options(*deduped_opts)
        builder.output(pipeline.output_path)

        return builder.build()

    def _skill_to_filters(
        self,
        skill: Skill,
        params: dict,
    ) -> tuple[list[str], list[str], list[str], str, list[str]]:
        """Convert a skill invocation to FFMPEG filters.

        Args:
            skill: Skill to convert.
            params: Parameters for the skill.

        Returns:
            Tuple of (video_filters, audio_filters, output_options, filter_complex, input_options).
            filter_complex is an empty string if not needed.
        """
        video_filters = []
        audio_filters = []
        output_options = []
        input_options = []
        filter_complex = ""

        # If skill has a template, use it
        if skill.ffmpeg_template:
            template = skill.ffmpeg_template
            for key, value in params.items():
                val_str = str(value)
                if isinstance(value, str):
                    val_str = sanitize_text_param(val_str)
                template = template.replace(f"{{{key}}}", val_str)

            # Determine if it's a video filter, audio filter, or output option
            if template.startswith("-"):
                output_options.extend(template.split())
            elif skill.category == SkillCategory.AUDIO:
                audio_filters.append(template)
            else:
                video_filters.append(template)

        # If skill has a pipeline, recursively compose
        elif skill.pipeline:
            for step_str in skill.pipeline:
                # Substitute {placeholder} values from parent params
                for key, value in params.items():
                    step_str = step_str.replace(f"{{{key}}}", str(value))

                # Parse step string (format: "skill_name:param1=val1,param2=val2")
                if ":" in step_str:
                    sub_skill_name, params_str = step_str.split(":", 1)
                    sub_params = {}
                    for p in params_str.split(","):
                        if "=" in p:
                            k, v = p.split("=", 1)
                            sub_params[k] = v
                else:
                    sub_skill_name = step_str
                    sub_params = {}

                sub_skill = self.registry.get(sub_skill_name)
                if sub_skill:
                    vf, af, opts, fc, io = self._skill_to_filters(sub_skill, sub_params)
                    video_filters.extend(vf)
                    audio_filters.extend(af)
                    output_options.extend(opts)
                    input_options.extend(io)
                    if fc:
                        filter_complex = fc if not filter_complex else f"{filter_complex};{fc}"

        # Handle specific skill types
        else:
            # Check for custom Python handler from skill packs first
            custom_handlers = getattr(self.registry, "_custom_handlers", {})
            handler = custom_handlers.get(skill.name)
            if handler is not None:
                result = handler(params)
                if len(result) == 5:
                    vf, af, opts, fc, io = result
                elif len(result) == 4:
                    vf, af, opts, fc = result
                    io = []
                else:
                    vf, af, opts = result
                    fc, io = "", []
            else:
                vf, af, opts, fc, io = self._builtin_skill_filters(skill.name, params)
            video_filters.extend(vf)
            audio_filters.extend(af)
            output_options.extend(opts)
            input_options.extend(io)
            if fc:
                filter_complex = fc

        return video_filters, audio_filters, output_options, filter_complex, input_options

    def validate_pipeline(self, pipeline: Pipeline) -> tuple[bool, list[str]]:
        """Validate a pipeline before execution.

        Args:
            pipeline: Pipeline to validate.

        Returns:
            Tuple of (is_valid, list of error messages).
        """
        errors = []

        if not pipeline.input_path:
            errors.append("No input path specified")
        elif not Path(pipeline.input_path).exists():
            errors.append(f"Input file not found: {pipeline.input_path}")

        if not pipeline.output_path:
            errors.append("No output path specified")
        elif not Path(pipeline.output_path).parent.exists():
            errors.append(f"Output directory not found: {Path(pipeline.output_path).parent}")

        for i, step in enumerate(pipeline.steps):
            if not step.enabled:
                continue

            skill = self.registry.get(step.skill_name)
            if not skill:
                errors.append(f"Step {i}: Unknown skill '{step.skill_name}'")
                continue

            is_valid, param_errors = skill.validate_params(step.params)
            if not is_valid:
                for err in param_errors:
                    errors.append(f"Step {i} ({step.skill_name}): {err}")

        return len(errors) == 0, errors

    def explain_pipeline(self, pipeline: Pipeline) -> str:
        """Generate a human-readable explanation of a pipeline.

        Args:
            pipeline: Pipeline to explain.

        Returns:
            Explanation string.
        """
        lines = ["Pipeline explanation:\n"]

        for i, step in enumerate(pipeline.steps):
            status = "" if step.enabled else " (disabled)"
            skill = self.registry.get(step.skill_name)

            if skill:
                lines.append(f"{i+1}. {skill.name}{status}")
                lines.append(f"   {skill.description}")
                if step.params:
                    params_str = ", ".join(f"{k}={v}" for k, v in step.params.items())
                    lines.append(f"   Parameters: {params_str}")
                if step.notes:
                    lines.append(f"   Notes: {step.notes}")
            else:
                lines.append(f"{i+1}. Unknown skill: {step.skill_name}{status}")

            lines.append("")

        return "\n".join(lines)

    # ------------------------------------------------------------------ #
    #  Dispatch table for built-in skill filters                           #
    # ------------------------------------------------------------------ #

    def _builtin_skill_filters(
        self,
        skill_name: str,
        params: dict,
    ) -> tuple[list[str], list[str], list[str], str, list[str]]:
        """Generate filters for built-in skills using dispatch table.

        Args:
            skill_name: Name of the skill.
            params: Parameters.

        Returns:
            Tuple of (video_filters, audio_filters, output_options, filter_complex, input_options).
        """
        handler = _get_dispatch().get(skill_name)
        if handler is None:
            return [], [], [], "", []
        result = handler(params)
        # Handlers may return 3-tuple, 4-tuple, or 5-tuple
        if len(result) == 5:
            return result
        if len(result) == 4:
            return result + ([],)
        vf, af, opts = result
        return vf, af, opts, "", []


# ====================================================================== #
#  Dispatch table — built lazily to avoid circular imports               #
# ====================================================================== #

_SKILL_DISPATCH: dict | None = None


def _get_dispatch() -> dict:
    """Return the skill dispatch table, building it on first access."""
    global _SKILL_DISPATCH
    if _SKILL_DISPATCH is not None:
        return _SKILL_DISPATCH

    from .handlers import (  # noqa: F401
        # temporal
        _f_trim, _f_speed, _f_reverse, _f_loop, _f_boomerang,
        _f_jump_cut, _f_beat_sync,
        # spatial
        _f_resize, _f_crop, _f_pad, _f_rotate, _f_flip, _f_zoom,
        _f_ken_burns, _f_mirror, _f_caption_space, _f_lens_correction,
        _f_deinterlace, _f_frame_interpolation, _f_scroll, _f_aspect,
        _f_perspective, _f_fill_borders, _f_deshake, _f_frame_blend,
        # visual
        _f_brightness, _f_contrast, _f_saturation, _f_hue,
        _f_sharpen, _f_blur, _f_denoise, _f_vignette, _f_fade,
        _f_pixelate, _f_posterize, _f_color_grade, _f_chromakey_simple,
        _f_deband, _f_color_temperature, _f_selective_color, _f_monochrome,
        _f_chromatic_aberration, _f_sketch, _f_glow, _f_ghost_trail,
        _f_color_channel_swap, _f_tilt_shift, _f_false_color, _f_halftone,
        _f_neon_enhanced, _f_thermal_enhanced, _f_comic_book_enhanced,
        _f_waveform, _f_chromakey, _f_colorkey, _f_lumakey, _f_colorhold,
        _f_despill, _f_remove_background, _f_blend, _f_color_match,
        _f_datamosh, _f_mask_blur, _f_lut_apply,
        # audio
        _f_volume, _f_normalize, _f_fade_audio, _f_remove_audio,
        _f_extract_audio, _f_replace_audio, _f_audio_crossfade,
        # encoding
        _f_compress, _f_convert, _f_bitrate, _f_quality, _f_gif,
        _f_container, _f_two_pass, _f_audio_codec, _f_hwaccel,
        _f_thumbnail, _f_extract_frames,
        # composite
        _f_add_text, _f_grid, _f_slideshow, _f_overlay_image, _f_watermark,
        _f_concat, _f_xfade, _f_split_screen, _f_animated_overlay,
        _f_text_overlay, _f_pip, _f_burn_subtitles, _f_countdown,
        _f_animated_text, _f_scrolling_text, _f_ticker, _f_lower_third,
        _f_typewriter_text, _f_bounce_text, _f_fade_text, _f_karaoke_text,
        # presets
        _f_fade_to_black, _f_fade_to_white, _f_flash,
        _f_spin, _f_shake, _f_pulse, _f_bounce, _f_drift,
        _f_iris_reveal, _f_wipe, _f_slide_in,
    )

    _SKILL_DISPATCH = {
        # Temporal
        "trim": _f_trim,
        "speed": _f_speed,
        "reverse": _f_reverse,
        "loop": _f_loop,
        "boomerang": _f_boomerang,
        "jump_cut": _f_jump_cut,
        "beat_sync": _f_beat_sync,
        # Spatial
        "resize": _f_resize,
        "crop": _f_crop,
        "pad": _f_pad,
        "rotate": _f_rotate,
        "flip": _f_flip,
        "zoom": _f_zoom,
        "ken_burns": _f_ken_burns,
        "mirror": _f_mirror,
        "caption_space": _f_caption_space,
        "lens_correction": _f_lens_correction,
        "deinterlace": _f_deinterlace,
        "frame_interpolation": _f_frame_interpolation,
        "scroll": _f_scroll,
        "aspect": _f_aspect,
        "perspective": _f_perspective,
        "fill_borders": _f_fill_borders,
        "deshake": _f_deshake,
        "frame_blend": _f_frame_blend,
        # Visual
        "brightness": _f_brightness,
        "contrast": _f_contrast,
        "saturation": _f_saturation,
        "hue": _f_hue,
        "sharpen": _f_sharpen,
        "blur": _f_blur,
        "denoise": _f_denoise,
        "vignette": _f_vignette,
        "fade": _f_fade,
        "pixelate": _f_pixelate,
        "posterize": _f_posterize,
        "color_grade": _f_color_grade,
        "deband": _f_deband,
        "color_temperature": _f_color_temperature,
        "selective_color": _f_selective_color,
        "monochrome": _f_monochrome,
        "chromatic_aberration": _f_chromatic_aberration,
        "sketch": _f_sketch,
        "glow": _f_glow,
        "ghost_trail": _f_ghost_trail,
        "color_channel_swap": _f_color_channel_swap,
        "tilt_shift": _f_tilt_shift,
        "false_color": _f_false_color,
        "halftone": _f_halftone,
        "neon": _f_neon_enhanced,
        "thermal": _f_thermal_enhanced,
        "comic_book": _f_comic_book_enhanced,
        "waveform": _f_waveform,
        "datamosh": _f_datamosh,
        "mask_blur": _f_mask_blur,
        "lut_apply": _f_lut_apply,
        "color_match": _f_color_match,
        "blend": _f_blend,
        "double_exposure": _f_blend,
        # Audio
        "volume": _f_volume,
        "normalize": _f_normalize,
        "fade_audio": _f_fade_audio,
        "remove_audio": _f_remove_audio,
        "extract_audio": _f_extract_audio,
        "replace_audio": _f_replace_audio,
        "audio_crossfade": _f_audio_crossfade,
        # Encoding
        "compress": _f_compress,
        "convert": _f_convert,
        "bitrate": _f_bitrate,
        "quality": _f_quality,
        "gif": _f_gif,
        "container": _f_container,
        "two_pass": _f_two_pass,
        "audio_codec": _f_audio_codec,
        "hwaccel": _f_hwaccel,
        "thumbnail": _f_thumbnail,
        "extract_frames": _f_extract_frames,
        # Composite / Overlay
        "text_overlay": _f_text_overlay,
        "add_text": _f_add_text,
        "text": _f_text_overlay,
        "drawtext": _f_text_overlay,
        "title": _f_text_overlay,
        "subtitle": _f_text_overlay,
        "caption": _f_text_overlay,
        "grid": _f_grid,
        "slideshow": _f_slideshow,
        "overlay_image": _f_overlay_image,
        "overlay": _f_overlay_image,
        "watermark": _f_watermark,
        "concat": _f_concat,
        "concatenate": _f_concat,
        "join": _f_concat,
        "xfade": _f_xfade,
        "transition": _f_xfade,
        "split_screen": _f_split_screen,
        "splitscreen": _f_split_screen,
        "side_by_side": _f_split_screen,
        "animated_overlay": _f_animated_overlay,
        "moving_overlay": _f_animated_overlay,
        "picture_in_picture": _f_pip,
        "pip": _f_pip,
        "burn_subtitles": _f_burn_subtitles,
        "hardcode_subtitles": _f_burn_subtitles,
        "countdown": _f_countdown,
        "timer": _f_countdown,
        "animated_text": _f_animated_text,
        "scrolling_text": _f_scrolling_text,
        "credits_roll": _f_scrolling_text,
        "vertical_scroll": _f_scrolling_text,
        "ticker": _f_ticker,
        "horizontal_scroll": _f_ticker,
        "news_ticker": _f_ticker,
        "lower_third": _f_lower_third,
        "name_plate": _f_lower_third,
        "typewriter_text": _f_typewriter_text,
        "typewriter": _f_typewriter_text,
        "bounce_text": _f_bounce_text,
        "fade_text": _f_fade_text,
        "karaoke_text": _f_karaoke_text,
        "karaoke": _f_karaoke_text,
        # Keying / Masking
        "chromakey": _f_chromakey,
        "chroma_key": _f_chromakey,
        "chroma_key_simple": _f_chromakey_simple,
        "green_screen": _f_chromakey,
        "colorkey": _f_colorkey,
        "color_key": _f_colorkey,
        "lumakey": _f_lumakey,
        "luma_key": _f_lumakey,
        "colorhold": _f_colorhold,
        "color_hold": _f_colorhold,
        "despill": _f_despill,
        "de_spill": _f_despill,
        "remove_background": _f_remove_background,
        "remove_bg": _f_remove_background,
        "background_removal": _f_remove_background,
        # Presets / Transitions
        "fade_to_black": _f_fade_to_black,
        "fade_to_white": _f_fade_to_white,
        "flash": _f_flash,
        "spin": _f_spin,
        "shake": _f_shake,
        "pulse": _f_pulse,
        "bounce": _f_bounce,
        "drift": _f_drift,
        "iris_reveal": _f_iris_reveal,
        "wipe": _f_wipe,
        "slide_in": _f_slide_in,
    }
    return _SKILL_DISPATCH

