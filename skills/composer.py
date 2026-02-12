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
                if flag in seen_flags:
                    # Replace the earlier occurrence
                    idx = seen_flags[flag]
                    deduped_opts[idx + 1] = val  # update value
                else:
                    seen_flags[flag] = len(deduped_opts)
                    deduped_opts.extend([flag, val])
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
        handler = _SKILL_DISPATCH.get(skill_name)
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
#  Per-skill filter handlers                                               #
#  Each returns (video_filters: list, audio_filters: list, opts: list)     #
# ====================================================================== #

def _f_trim(p):
    input_opts = []
    output_opts = []

    start = p.get("start")
    end = p.get("end")
    duration = p.get("duration")

    try:
        # Try to parse start/end as floats for calculation (fast seek optimization)
        s_val = float(start) if start is not None else 0.0

        if start is not None:
            input_opts.extend(["-ss", str(start)])

        if end is not None:
            e_val = float(end)
            # Duration is end - start
            output_opts.extend(["-t", str(e_val - s_val)])
        elif duration is not None:
            # Duration is independent of start point
            output_opts.extend(["-t", str(duration)])

    except (ValueError, TypeError):
        # Fallback to slow seek if we can't do math (e.g. strings like "00:01:00")
        opts = []
        if start: opts.extend(["-ss", str(start)])
        if end: opts.extend(["-to", str(end)])
        if duration: opts.extend(["-t", str(duration)])
        return [], [], opts

    return [], [], output_opts, "", input_opts


def _f_speed(p):
    factor = float(p.get("factor", 1.0))

    vf = [f"setpts={1.0 / factor}*PTS"]
    af = []
    if 0.5 <= factor <= 2.0:
        af.append(f"atempo={factor}")
    elif factor < 0.5:
        remaining = factor
        while remaining < 0.5:
            af.append("atempo=0.5")
            remaining *= 2
        af.append(f"atempo={remaining}")
    else:
        remaining = factor
        while remaining > 2.0:
            af.append("atempo=2.0")
            remaining /= 2
        af.append(f"atempo={remaining}")

    return vf, af, []


def _f_reverse(p):
    return ["reverse"], ["areverse"], []


def _f_loop(p):
    count = int(p.get("count", 2))
    # -stream_loop N repeats the input N additional times
    return [], [], [], "", ["-stream_loop", str(count)]


def _f_resize(p):
    return [f"scale={p.get('width', -1)}:{p.get('height', -1)}"], [], []


def _f_crop(p):
    w = p.get("width", "iw")
    h = p.get("height", "ih")
    x = p.get("x", "(in_w-out_w)/2")
    y = p.get("y", "(in_h-out_h)/2")
    return [f"crop={w}:{h}:{x}:{y}"], [], []


def _f_pad(p):
    w = p.get("width", "iw")
    h = p.get("height", "ih")
    x = p.get("x", "(ow-iw)/2")
    y = p.get("y", "(oh-ih)/2")
    color = sanitize_text_param(str(p.get("color", "black")))
    return [f"pad={w}:{h}:{x}:{y}:{color}"], [], []


def _f_rotate(p):
    angle = p.get("angle", 0)
    if angle == 90:
        return ["transpose=1"], [], []
    elif angle == -90 or angle == 270:
        return ["transpose=2"], [], []
    elif angle == 180:
        return ["transpose=1,transpose=1"], [], []
    else:
        radians = angle * 3.14159 / 180
        return [f"rotate={radians}"], [], []


def _f_flip(p):
    d = p.get("direction", "horizontal")
    return ["hflip" if d == "horizontal" else "vflip"], [], []


def _f_brightness(p):
    return [f"eq=brightness={p.get('value', 0)}"], [], []


def _f_contrast(p):
    return [f"eq=contrast={p.get('value', 1.0)}"], [], []


def _f_saturation(p):
    return [f"eq=saturation={p.get('value', 1.0)}"], [], []


def _f_hue(p):
    return [f"hue=h={p.get('value', 0)}"], [], []


def _f_sharpen(p):
    amount = p.get("amount", 1.0)
    return [f"unsharp=5:5:{amount}:5:5:0"], [], []


def _f_blur(p):
    radius = p.get("radius", 5)
    return [f"boxblur={radius}:{radius}"], [], []


def _f_denoise(p):
    strength = p.get("strength", "medium")
    m = {"light": "hqdn3d=2:2:3:3", "medium": "hqdn3d=4:3:6:4"}
    return [m.get(strength, "hqdn3d=6:4:9:6")], [], []


def _f_vignette(p):
    import math
    intensity = float(p.get("intensity", 0.3))
    # Map intensity [0,1] to angle [PI/6, PI/2] for visible vignette
    angle = (math.pi / 6) + intensity * (math.pi / 2 - math.pi / 6)
    return [f"vignette=angle={angle:.4f}"], [], []


def _f_fade(p):
    fade_type = p.get("type", "in")
    start = p.get("start", 0)
    duration = p.get("duration", 1)
    vf = []
    if fade_type == "both":
        vf.append(f"fade=t=in:st=0:d={duration}")
        vf.append(f"fade=t=out:d={duration}")
    else:
        vf.append(f"fade=t={fade_type}:st={start}:d={duration}")
    return vf, [], []


def _f_volume(p):
    return [], [f"volume={p.get('level', 1.0)}"], []


def _f_normalize(p):
    return [], ["loudnorm"], []


def _f_fade_audio(p):
    fade_type = p.get("type", "in")
    start = p.get("start", 0)
    duration = p.get("duration", 1)
    return [], [f"afade=t={fade_type}:st={start}:d={duration}"], []


def _f_remove_audio(p):
    return [], [], ["-an"]


def _f_extract_audio(p):
    return [], [], ["-vn", "-c:a", "copy"]


def _f_compress(p):
    preset = p.get("preset", "medium")
    crf_map = {"light": 20, "medium": 23, "heavy": 28}
    crf = crf_map.get(preset, 23)
    return [], [], ["-c:v", "libx264", "-crf", str(crf), "-preset", "medium"]


def _f_convert(p):
    codec = p.get("codec", "h264")
    codec_map = {"h264": "libx264", "h265": "libx265", "vp9": "libvpx-vp9", "av1": "libaom-av1"}
    return [], [], ["-c:v", codec_map.get(codec, "libx264")]


def _f_bitrate(p):
    opts = []
    if p.get("video"):
        opts.extend(["-b:v", p["video"]])
    if p.get("audio"):
        opts.extend(["-b:a", p["audio"]])
    return [], [], opts


def _f_quality(p):
    crf = p.get("crf", 23)
    preset = p.get("preset", "medium")
    return [], [], ["-c:v", "libx264", "-crf", str(crf), "-preset", preset]


def _f_add_text(p):
    text = sanitize_text_param(str(p.get("text", "")))
    size = p.get("size", 48)
    color = sanitize_text_param(str(p.get("color", "white")))
    font = sanitize_text_param(str(p.get("font", "Sans")))
    border = p.get("border", True)
    position = p.get("position", "center")

    pos_map = {
        "center": "x=(w-text_w)/2:y=(h-text_h)/2",
        "top": "x=(w-text_w)/2:y=text_h",
        "bottom": "x=(w-text_w)/2:y=h-text_h*2",
        "top_left": "x=text_h:y=text_h",
        "top_right": "x=w-text_w-text_h:y=text_h",
        "bottom_left": "x=text_h:y=h-text_h*2",
        "bottom_right": "x=w-text_w-text_h:y=h-text_h*2",
    }
    xy = pos_map.get(position, pos_map["center"])
    border_style = ":borderw=3:bordercolor=black" if border else ""

    drawtext = (
        f"drawtext=text='{text}':fontsize={size}"
        f":fontcolor={color}:font='{font}'"
        f":{xy}{border_style}"
    )
    return [drawtext], [], []


def _f_pixelate(p):
    factor = p.get("factor", 10)
    return [
        f"scale=iw/{factor}:ih/{factor},"
        f"scale=iw*{factor}:ih*{factor}:flags=neighbor"
    ], [], []


def _f_posterize(p):
    levels = int(p.get("levels", 4))
    step = max(1, 256 // levels)
    lut_expr = f"trunc(val/{step})*{step}"
    return [f"lutrgb=r='{lut_expr}':g='{lut_expr}':b='{lut_expr}'"], [], []


def _f_fade_to_black(p):
    in_dur = float(p.get("in_duration", 1.0))
    out_dur = float(p.get("out_duration", 1.0))
    vf = []
    if in_dur > 0:
        vf.append(f"fade=t=in:st=0:d={in_dur}")
    if out_dur > 0:
        vf.append(f"fade=t=out:d={out_dur}")
    return vf, [], []


def _f_fade_to_white(p):
    in_dur = float(p.get("in_duration", 1.0))
    out_dur = float(p.get("out_duration", 1.0))
    vf = []
    if in_dur > 0:
        vf.append(f"fade=t=in:st=0:d={in_dur}:c=white")
    if out_dur > 0:
        vf.append(f"fade=t=out:d={out_dur}:c=white")
    return vf, [], []


def _f_flash(p):
    t = float(p.get("time", 0))
    duration = float(p.get("duration", 0.3))
    mid = t + duration / 2
    return [
        f"fade=t=out:st={t}:d={duration/2}:c=white,"
        f"fade=t=in:st={mid}:d={duration/2}:c=white"
    ], [], []


def _f_spin(p):
    speed = float(p.get("speed", 90.0))
    direction = p.get("direction", "cw")
    rad_per_sec = speed * 3.14159 / 180
    if direction == "ccw":
        rad_per_sec = -rad_per_sec
    return [f"rotate={rad_per_sec}*t:fillcolor=black"], [], []


def _f_shake(p):
    intensity = p.get("intensity", "medium")
    shake_map = {"light": 5, "medium": 12, "heavy": 25}
    amount = shake_map.get(intensity, 12)
    return [
        f"crop=iw-{amount*2}:ih-{amount*2}"
        f":{amount}+{amount}*random(1)"
        f":{amount}+{amount}*random(2),"
        f"scale=iw+{amount*2}:ih+{amount*2}"
    ], [], []


def _f_pulse(p):
    rate = float(p.get("rate", 1.0))
    amount = float(p.get("amount", 0.05))
    margin = int(amount * 100) + 10
    offset_expr = f"{margin}+{margin}*{amount}*10*sin(2*PI*{rate}*t)"
    return [
        f"pad=iw+{margin*2}:ih+{margin*2}:{margin}:{margin}:color=black",
        f"crop=iw-{margin*2}:ih-{margin*2}:'{offset_expr}':'{offset_expr}'",
    ], [], []


def _f_bounce(p):
    height = int(p.get("height", 30))
    speed = float(p.get("speed", 2.0))
    return [
        f"pad=iw:ih+{height*2}:(ow-iw)/2:{height}:black,"
        f"crop=iw:ih-{height*2}:0:{height}*abs(sin({speed}*PI*t))"
    ], [], []


def _f_drift(p):
    direction = p.get("direction", "right")
    amount = int(p.get("amount", 50))
    # Speed in px/sec: cover `amount` pixels over ~10s (configurable via amount)
    speed = max(1, amount // 10) if amount > 10 else amount
    d = {
        "right": (
            f"pad=iw+{amount}:ih:0:0:black,"
            f"crop=iw-{amount}:ih:min({speed}*t\\,{amount}):0"
        ),
        "left": (
            f"pad=iw+{amount}:ih:{amount}:0:black,"
            f"crop=iw-{amount}:ih:max({amount}-{speed}*t\\,0):0"
        ),
        "down": (
            f"pad=iw:ih+{amount}:0:0:black,"
            f"crop=iw:ih-{amount}:0:min({speed}*t\\,{amount})"
        ),
        "up": (
            f"pad=iw:ih+{amount}:0:{amount}:black,"
            f"crop=iw:ih-{amount}:0:max({amount}-{speed}*t\\,0)"
        ),
    }
    return [d.get(direction, d["right"])], [], []


def _f_iris_reveal(p):
    duration = float(p.get("duration", 2.0))
    return [
        f"geq="
        f"lum='if(lte(sqrt(pow(X-W/2,2)+pow(Y-H/2,2)),sqrt(pow(W/2,2)+pow(H/2,2))*min(T/{duration},1)),lum(X,Y),0)'"
        f":cb='if(lte(sqrt(pow(X-W/2,2)+pow(Y-H/2,2)),sqrt(pow(W/2,2)+pow(H/2,2))*min(T/{duration},1)),cb(X,Y),128)'"
        f":cr='if(lte(sqrt(pow(X-W/2,2)+pow(Y-H/2,2)),sqrt(pow(W/2,2)+pow(H/2,2))*min(T/{duration},1)),cr(X,Y),128)'"
    ], [], []


def _f_wipe(p):
    direction = p.get("direction", "left")
    duration = float(p.get("duration", 1.5))
    cond_map = {
        "left": f"lte(X,W*min(T/{duration},1))",
        "right": f"gte(X,W*(1-min(T/{duration},1)))",
        "down": f"lte(Y,H*min(T/{duration},1))",
        "up": f"gte(Y,H*(1-min(T/{duration},1)))",
    }
    cond = cond_map.get(direction, cond_map["left"])
    return [
        f"geq="
        f"lum='if({cond},lum(X,Y),0)'"
        f":cb='if({cond},cb(X,Y),128)'"
        f":cr='if({cond},cr(X,Y),128)'"
    ], [], []


def _f_slide_in(p):
    direction = p.get("direction", "left")
    duration = float(p.get("duration", 1.0))
    d = {
        "left": (
            f"pad=iw*2:ih:iw:0:black,"
            f"crop=iw/2:ih:iw/2*min(t/{duration}\\,1):0"
        ),
        "right": (
            f"pad=iw*2:ih:0:0:black,"
            f"crop=iw/2:ih:iw/2*(1-min(t/{duration}\\,1)):0"
        ),
        "down": (
            f"pad=iw:ih*2:0:ih:black,"
            f"crop=iw:ih/2:0:ih/2*min(t/{duration}\\,1)"
        ),
        "up": (
            f"pad=iw:ih*2:0:0:black,"
            f"crop=iw:ih/2:0:ih/2*(1-min(t/{duration}\\,1))"
        ),
    }
    return [d.get(direction, d["left"])], [], []


def _f_zoom(p):
    factor = float(p.get("factor", 1.5))
    x = p.get("x", "center")
    y = p.get("y", "center")
    # Static zoom via crop then scale back to original dimensions
    crop_w = f"iw/{factor}"
    crop_h = f"ih/{factor}"
    if x == "center":
        crop_x = f"(iw-iw/{factor})/2"
    else:
        crop_x = f"iw*{float(x)}-iw/{factor}/2"
    if y == "center":
        crop_y = f"(ih-ih/{factor})/2"
    else:
        crop_y = f"ih*{float(y)}-ih/{factor}/2"
    return [f"crop={crop_w}:{crop_h}:{crop_x}:{crop_y},scale=iw*{factor}:ih*{factor}"], [], []


def _f_ken_burns(p):
    direction = p.get("direction", "zoom_in")
    amount = float(p.get("amount", 0.3))
    dur = float(p.get("duration", 5))
    # Use FFmpeg's native zoompan with d=1 (one output frame per input frame)
    # so it works correctly for video input.  zoompan internally crops a
    # region of iw/z × ih/z at position (x, y) and scales it to the output
    # size — exactly the Ken Burns zoom+pan effect.
    # NOTE: zoompan requires an explicit output size (s=) because it defaults
    # to hd720; we normalise to even dims first and pass the size through.
    if direction == "zoom_in":
        # z ramps from 1 → (1+amount) over dur seconds using pzoom
        rate = amount / dur / 25  # per-frame increment at ~25fps
        return [
            f"scale='trunc(iw/2)*2':'trunc(ih/2)*2',"
            f"zoompan=z='min(max(zoom\\,pzoom)+{rate:.6f}\\,{1+amount})':"
            f"d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=hd720:fps=30"
        ], [], []
    elif direction == "zoom_out":
        # z starts at (1+amount) and holds (zoompan starts zoomed)
        # then we reverse by starting high and decreasing
        rate = amount / dur / 25
        return [
            f"scale='trunc(iw/2)*2':'trunc(ih/2)*2',"
            f"zoompan=z='max(if(eq(on\\,1)\\,{1+amount}\\,zoom)-{rate:.6f}\\,1)':"
            f"d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=hd720:fps=30"
        ], [], []
    elif direction == "pan_right":
        zf = 1 + amount
        return [
            f"scale='trunc(iw/2)*2':'trunc(ih/2)*2',"
            f"zoompan=z='{zf}':"
            f"d=1:x='min(on*{zf-1:.4f}*iw/{dur}/25\\,(iw-iw/{zf}))':y='ih/2-(ih/zoom/2)':s=hd720:fps=30"
        ], [], []
    elif direction == "pan_left":
        zf = 1 + amount
        return [
            f"scale='trunc(iw/2)*2':'trunc(ih/2)*2',"
            f"zoompan=z='{zf}':"
            f"d=1:x='max((iw-iw/{zf})-on*{zf-1:.4f}*iw/{dur}/25\\,0)':y='ih/2-(ih/zoom/2)':s=hd720:fps=30"
        ], [], []
    else:
        # Default to zoom_in
        rate = amount / dur / 25
        return [
            f"scale='trunc(iw/2)*2':'trunc(ih/2)*2',"
            f"zoompan=z='min(max(zoom\\,pzoom)+{rate:.6f}\\,{1+amount})':"
            f"d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=hd720:fps=30"
        ], [], []


def _f_mirror(p):
    mode = p.get("mode", "horizontal")
    if mode == "horizontal":
        return ["crop=iw/2:ih:0:0,split[l][r];[r]hflip[rf];[l][rf]hstack"], [], []
    elif mode == "vertical":
        return ["crop=iw:ih/2:0:0,split[t][b];[b]vflip[bf];[t][bf]vstack"], [], []
    elif mode == "quad":
        return [
            "crop=iw/2:ih/2:0:0,split=4[a][b][c][d];"
            "[b]hflip[bh];[c]vflip[cv];[d]hflip,vflip[dh];"
            "[a][bh]hstack[top];[cv][dh]hstack[bot];"
            "[top][bot]vstack"
        ], [], []
    else:
        return ["hflip"], [], []


def _f_boomerang(p):
    loops = int(p.get("loops", 3))
    # Forward + reverse concatenated, then looped
    return [
        f"split[fwd][rev];[rev]reverse[r];[fwd][r]concat=n=2:v=1:a=0,loop=loop={loops - 1}:size=32767"
    ], [], []


def _f_caption_space(p):
    position = p.get("position", "bottom")
    height = int(p.get("height", 200))
    color = sanitize_text_param(str(p.get("color", "black")))
    if position == "top":
        return [f"pad=iw:ih+{height}:0:{height}:{color}"], [], []
    else:
        return [f"pad=iw:ih+{height}:0:0:{color}"], [], []


def _f_color_grade(p):
    style = p.get("style", "teal_orange")
    grades = {
        "teal_orange": "eq=saturation=1.3:contrast=1.1,hue=h=-10",
        "warm": "eq=saturation=1.15:contrast=1.05,colorbalance=rs=0.1:gs=0.05:bs=-0.1",
        "cool": "eq=saturation=1.1:contrast=1.05,colorbalance=rs=-0.1:gs=0.0:bs=0.15",
        "desaturated": "eq=saturation=0.6:contrast=1.2:brightness=0.02",
        "high_contrast": "eq=contrast=1.4:saturation=1.15:brightness=-0.05",
    }
    return [grades.get(style, grades["teal_orange"])], [], []


def _f_gif(p):
    width = int(p.get("width", 480))
    fps = int(p.get("fps", 15))
    # GIF conversion requires split + palettegen + paletteuse filtergraph
    return [
        f"fps={fps},scale={width}:-1:flags=lanczos,"
        f"split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse"
    ], [], []


def _f_chromakey_simple(p):
    color = sanitize_text_param(str(p.get("color", "green")))
    # Map common names to hex
    color_map = {"green": "0x00FF00", "blue": "0x0000FF", "red": "0xFF0000"}
    color_hex = color_map.get(color.lower(), color)
    similarity = float(p.get("similarity", 0.3))
    blend = float(p.get("blend", 0.1))
    # Use filter_complex to composite keyed footage over black background.
    # colorkey produces alpha transparency which H.264/NVENC discard silently,
    # so we overlay onto black to flatten the alpha before encoding.
    fc = (
        f"[0:v]split[_ckbg][_ckfg];"
        f"[_ckbg]drawbox=x=0:y=0:w=iw:h=ih:c=black:t=fill[_ckblack];"
        f"[_ckfg]colorkey=color={color_hex}:similarity={similarity}:blend={blend}[_ckkeyed];"
        f"[_ckblack][_ckkeyed]overlay=format=auto"
    )
    return [], [], [], fc


def _f_deband(p):
    thr = float(p.get("threshold", 0.08))
    rng = int(p.get("range", 16))
    blur = 1 if p.get("blur", True) else 0
    return [f"deband=1thr={thr}:2thr={thr}:3thr={thr}:4thr={thr}:range={rng}:blur={blur}"], [], []


def _f_lens_correction(p):
    k1 = float(p.get("k1", -0.2))
    k2 = float(p.get("k2", 0.0))
    return [f"lenscorrection=k1={k1}:k2={k2}:i=bilinear"], [], []


def _f_color_temperature(p):
    temp = int(p.get("temperature", 6500))
    mix = float(p.get("mix", 1.0))
    return [f"colortemperature=temperature={temp}:mix={mix}"], [], []


def _f_deinterlace(p):
    mode = p.get("mode", "send_frame")
    mode_map = {"send_frame": "0", "send_field": "1"}
    return [f"yadif=mode={mode_map.get(mode, '0')}"], [], []


def _f_frame_interpolation(p):
    fps = int(p.get("fps", 60))
    mode = p.get("mode", "mci")
    return [f"minterpolate=fps={fps}:mi_mode={mode}"], [], []


def _f_scroll(p):
    direction = p.get("direction", "up")
    speed = float(p.get("speed", 0.05))
    d = {
        "up": f"scroll=vertical=-{speed}",
        "down": f"scroll=vertical={speed}",
        "left": f"scroll=horizontal=-{speed}",
        "right": f"scroll=horizontal={speed}",
    }
    return [d.get(direction, d["up"])], [], []


def _f_aspect(p):
    ratio = p.get("ratio", "16:9")
    mode = p.get("mode", "pad")
    color = sanitize_text_param(str(p.get("color", "black")))
    # Parse ratio string like "16:9" or "2.35:1"
    parts = ratio.split(":")
    if len(parts) == 2:
        r = float(parts[0]) / float(parts[1])
    else:
        r = float(ratio)
    if mode == "crop":
        return [f"crop=if(gt(iw/ih\\,{r})\\,ih*{r}\\,iw):if(gt(iw/ih\\,{r})\\,ih\\,iw/{r})"], [], []
    elif mode == "stretch":
        return [f"scale=if(gt(iw/ih\\,{r})\\,iw\\,ih*{r}):if(gt(iw/ih\\,{r})\\,iw/{r}\\,ih)"], [], []
    else:  # pad
        return [f"pad=if(gt(iw/ih\\,{r})\\,iw\\,ih*{r}):if(gt(iw/ih\\,{r})\\,iw/{r}\\,ih):(ow-iw)/2:(oh-ih)/2:{color}"], [], []


def _f_container(p):
    fmt = p.get("format", "mp4")
    return [], [], ["-f", fmt]


def _f_two_pass(p):
    bitrate = p.get("target_bitrate", "4M")
    return [], [], ["-b:v", bitrate]


def _f_audio_codec(p):
    codec = p.get("codec", "aac")
    bitrate = p.get("bitrate", "128k")
    if codec == "copy":
        return [], [], ["-c:a", "copy"]
    return [], [], ["-c:a", codec, "-b:a", bitrate]


def _f_hwaccel(p):
    accel_type = p.get("type", "auto")
    return [], [], [], "", ["-hwaccel", accel_type]


def _f_perspective(p):
    preset = p.get("preset", "tilt_forward")
    strength = float(p.get("strength", 0.3))
    # s is the pixel offset proportional to strength (max ~25% of dimension)
    presets = {
        "tilt_forward":  "x0=0+{s}:y0=0:x1=W-{s}:y1=0:x2=0:y2=H:x3=W:y3=H",
        "tilt_back":     "x0=0:y0=0:x1=W:y1=0:x2=0+{s}:y2=H:x3=W-{s}:y3=H",
        "lean_left":     "x0=0:y0=0+{s}:x1=W:y1=0:x2=0:y2=H:x3=W:y3=H-{s}",
        "lean_right":    "x0=0:y0=0:x1=W:y1=0+{s}:x2=0:y2=H-{s}:x3=W:y3=H",
    }
    tmpl = presets.get(preset, presets["tilt_forward"])
    # Convert strength 0-1 to pixel expression: strength * W/4 (max 25% offset)
    s = f"W*{strength}/4"
    expr = tmpl.replace("{s}", s)
    return [f"perspective={expr}:interpolation=linear:sense=source"], [], []


def _f_fill_borders(p):
    left = int(p.get("left", 10))
    right = int(p.get("right", 10))
    top = int(p.get("top", 10))
    bottom = int(p.get("bottom", 10))
    mode = p.get("mode", "smear")
    mode_map = {"smear": 0, "mirror": 1, "fixed": 2, "reflect": 3, "wrap": 4, "fade": 5}
    m = mode_map.get(mode, 0)
    return [f"fillborders=left={left}:right={right}:top={top}:bottom={bottom}:mode={m}"], [], []


def _f_deshake(p):
    rx = int(p.get("rx", 16))
    ry = int(p.get("ry", 16))
    edge = p.get("edge", "mirror")
    edge_map = {"blank": 0, "original": 1, "clamp": 2, "mirror": 3}
    e = edge_map.get(edge, 3)
    return [f"deshake=rx={rx}:ry={ry}:edge={e}"], [], []


def _f_selective_color(p):
    color_range = p.get("color_range", "reds")
    c = float(p.get("cyan", 0.0))
    m = float(p.get("magenta", 0.0))
    y = float(p.get("yellow", 0.0))
    k = float(p.get("black", 0.0))
    # selectivecolor expects CMYK values as space-separated string
    return [f"selectivecolor={color_range}='{c} {m} {y} {k}'"], [], []


def _f_monochrome(p):
    preset = p.get("preset", "neutral")
    size = float(p.get("size", 1.0))
    # cb = chroma blue spot, cr = chroma red spot
    presets = {
        "neutral":    {"cb": 0.0, "cr": 0.0},
        "warm":       {"cb": -0.1, "cr": 0.2},
        "cool":       {"cb": 0.2, "cr": -0.1},
        "sepia_tone": {"cb": -0.2, "cr": 0.15},
        "blue_tone":  {"cb": 0.3, "cr": -0.05},
        "green_tone": {"cb": 0.1, "cr": -0.2},
    }
    p_vals = presets.get(preset, presets["neutral"])
    return [f"monochrome=cb={p_vals['cb']}:cr={p_vals['cr']}:size={size}"], [], []


# ====================================================================== #
#  Enhanced effect handlers (using advanced FFMPEG filters)                 #
# ====================================================================== #


def _f_chromatic_aberration(p):
    """RGB channel offset using rgbashift — real chromatic aberration."""
    amount = int(p.get("amount", 4))
    return [f"rgbashift=rh=-{amount}:bh={amount}:rv={amount // 2}:bv=-{amount // 2}"], [], []


def _f_sketch(p):
    """Pencil/ink line art using edgedetect filter."""
    mode = p.get("mode", "pencil")
    if mode == "color":
        return ["edgedetect=low=0.1:high=0.3:mode=colormix"], [], []
    elif mode == "ink":
        return ["edgedetect=low=0.08:high=0.4,negate"], [], []
    else:  # pencil
        return ["edgedetect=low=0.1:high=0.3,negate"], [], []


def _f_glow(p):
    """Bloom/soft glow using split → gblur → screen blend (filter_complex)."""
    radius = float(p.get("radius", 30))
    strength = float(p.get("strength", 0.4))
    strength = max(0.1, min(0.8, strength))
    fc = (
        f"split[a][b];"
        f"[b]gblur=sigma={radius}[b];"
        f"[a][b]blend=all_mode=screen:all_opacity={strength}"
    )
    return [], [], [], fc


def _f_ghost_trail(p):
    """Temporal trailing/afterimage using lagfun filter."""
    decay = float(p.get("decay", 0.97))
    decay = max(0.9, min(0.995, decay))
    return [f"lagfun=decay={decay}"], [], []


def _f_color_channel_swap(p):
    """Dramatic color remapping using colorchannelmixer."""
    preset = p.get("preset", "swap_rb")
    presets = {
        "swap_rb": "colorchannelmixer=rr=0:rg=0:rb=1:br=1:bg=0:bb=0",
        "swap_rg": "colorchannelmixer=rr=0:rg=1:rb=0:gr=1:gg=0:gb=0",
        "swap_gb": "colorchannelmixer=gg=0:gb=1:bg=1:bb=0",
        "nightvision": "colorchannelmixer=rr=0.2:rg=0.7:rb=0.1:gr=0.2:gg=0.7:gb=0.1:br=0.1:bg=0.1:bb=0.1",
        "matrix": "colorchannelmixer=rr=0:rg=1:rb=0:gr=0:gg=1:gb=0:br=0:bg=1:bb=0",
    }
    filt = presets.get(preset, presets["swap_rb"])
    return [filt], [], []


def _f_tilt_shift(p):
    """Real tilt-shift miniature effect with selective blur (filter_complex)."""
    focus = float(p.get("focus_position", 0.5))
    blur_amount = float(p.get("blur_amount", 8))
    # Sharp band is centered on focus, 30% of frame height
    low = max(0, focus - 0.15)
    high = min(1, focus + 0.15)
    fc = (
        f"split[a][b];"
        f"[b]gblur=sigma={blur_amount}[b];"
        f"[a][b]blend=all_expr='if(between(Y/H\\,{low}\\,{high})\\,A\\,B)'"
    )
    return [], [], [], fc


def _f_frame_blend(p):
    """Temporal frame blending / motion blur using tmix."""
    frames = int(p.get("frames", 5))
    frames = max(2, min(10, frames))
    weights = " ".join(["1"] * frames)
    return [f"tmix=frames={frames}:weights='{weights}'"], [], []


def _f_false_color(p):
    """Pseudocolor / heat map using pseudocolor filter."""
    palette = p.get("palette", "heat")
    palettes = {
        "heat": (
            "pseudocolor="
            "c0='if(between(val,0,85),255,if(between(val,85,170),255,if(between(val,170,255),255,0)))':"
            "c1='if(between(val,0,85),0,if(between(val,85,170),val-85,if(between(val,170,255),255,0)))':"
            "c2='if(between(val,0,85),0,if(between(val,85,170),0,if(between(val,170,255),val-170,0)))'"
        ),
        "electric": (
            "pseudocolor="
            "c0='if(lt(val,128),val*2,255)':"
            "c1='if(lt(val,128),0,val-128)':"
            "c2='if(lt(val,128),255-val*2,0)'"
        ),
        "blues": (
            "pseudocolor="
            "c0='val/3':"
            "c1='val/2':"
            "c2='val'"
        ),
        "rainbow": (
            "pseudocolor="
            "c0='if(lt(val,85),255-val*3,if(lt(val,170),0,val*3-510))':"
            "c1='if(lt(val,85),val*3,if(lt(val,170),255,765-val*3))':"
            "c2='if(lt(val,85),0,if(lt(val,170),val*3-255,255))'"
        ),
    }
    filt = palettes.get(palette, palettes["heat"])
    return [filt], [], []


def _f_halftone(p):
    """Print halftone dot pattern using geq."""
    dot_size = float(p.get("dot_size", 0.3))
    freq = max(0.1, min(1.0, dot_size))
    return [
        f"format=gray,geq='if(gt(lum(X\\,Y)\\,128+127*sin(X*{freq})*sin(Y*{freq}))\\,255\\,0)'"
    ], [], []


# --- Upgraded existing effect handlers --- #

def _f_neon_enhanced(p):
    """Neon glow with real edge detection + high-saturation blend (filter_complex)."""
    intensity = p.get("intensity", "medium")
    opacity = {"subtle": 0.3, "medium": 0.5, "strong": 0.7}.get(intensity, 0.5)
    fc = (
        f"split[a][b];"
        f"[b]edgedetect=low=0.08:high=0.3:mode=colormix,"
        f"eq=saturation=3:brightness=0.1[b];"
        f"[a][b]blend=all_mode=screen:all_opacity={opacity}"
    )
    return [], [], [], fc


def _f_thermal_enhanced(p):
    """Real thermal/heat vision using pseudocolor."""
    return [
        "pseudocolor="
        "c0='if(between(val,0,85),255,if(between(val,85,170),255,if(between(val,170,255),255,0)))':"
        "c1='if(between(val,0,85),0,if(between(val,85,170),val*3-255,if(between(val,170,255),255,0)))':"
        "c2='if(between(val,0,85),0,if(between(val,85,170),0,if(between(val,170,255),val*3-510,0)))'"
    ], [], []


def _f_comic_book_enhanced(p):
    """Comic book with real edge outline + posterization (filter_complex)."""
    style = p.get("style", "classic")
    levels = {"classic": 6, "manga": 2, "pop_art": 4}.get(style, 6)
    step = max(1, 256 // levels)
    lut_expr = f"trunc(val/{step})*{step}"
    fc = (
        f"split[a][b];"
        f"[b]edgedetect=low=0.1:high=0.4,negate[b];"
        f"[a]lutrgb=r='{lut_expr}':g='{lut_expr}':b='{lut_expr}',"
        f"eq=saturation=1.5:contrast=1.3[a];"
        f"[a][b]blend=all_mode=multiply"
    )
    return [], [], [], fc


# Dispatch table: skill_name → handler(params) → (vf, af, opts)
_SKILL_DISPATCH: dict[str, callable] = {
    # Temporal
    "trim": _f_trim,
    "speed": _f_speed,
    "reverse": _f_reverse,
    "loop": _f_loop,
    # Spatial
    "resize": _f_resize,
    "crop": _f_crop,
    "pad": _f_pad,
    "rotate": _f_rotate,
    "flip": _f_flip,
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
    # Audio
    "volume": _f_volume,
    "normalize": _f_normalize,
    "fade_audio": _f_fade_audio,
    "remove_audio": _f_remove_audio,
    "extract_audio": _f_extract_audio,
    # Encoding
    "compress": _f_compress,
    "convert": _f_convert,
    "bitrate": _f_bitrate,
    "quality": _f_quality,
    # Overlay
    "text_overlay": _f_add_text,
    "add_text": _f_add_text,
    "pixelate": _f_pixelate,
    "posterize": _f_posterize,
    # Transitions
    "fade_to_black": _f_fade_to_black,
    "fade_to_white": _f_fade_to_white,
    "flash": _f_flash,
    # Motion
    "spin": _f_spin,
    "shake": _f_shake,
    "pulse": _f_pulse,
    "bounce": _f_bounce,
    "drift": _f_drift,
    # Reveals
    "iris_reveal": _f_iris_reveal,
    "wipe": _f_wipe,
    "slide_in": _f_slide_in,
    # Zoom
    "zoom": _f_zoom,
    "ken_burns": _f_ken_burns,
    # Effects
    "mirror": _f_mirror,
    "boomerang": _f_boomerang,
    "caption_space": _f_caption_space,
    "color_grade": _f_color_grade,
    "gif": _f_gif,
    # High-impact
    "chromakey": _f_chromakey_simple,
    "chroma_key_simple": _f_chromakey_simple,
    "deband": _f_deband,
    "lens_correction": _f_lens_correction,
    "color_temperature": _f_color_temperature,
    "deinterlace": _f_deinterlace,
    "frame_interpolation": _f_frame_interpolation,
    "scroll": _f_scroll,
    # Infrastructure
    "aspect": _f_aspect,
    "container": _f_container,
    "two_pass": _f_two_pass,
    "audio_codec": _f_audio_codec,
    "hwaccel": _f_hwaccel,
    # Medium-value
    "perspective": _f_perspective,
    "fill_borders": _f_fill_borders,
    "deshake": _f_deshake,
    "selective_color": _f_selective_color,
    "monochrome": _f_monochrome,
    # Enhanced effects
    "chromatic_aberration": _f_chromatic_aberration,
    "sketch": _f_sketch,
    "glow": _f_glow,
    "ghost_trail": _f_ghost_trail,
    "color_channel_swap": _f_color_channel_swap,
    "tilt_shift": _f_tilt_shift,
    "frame_blend": _f_frame_blend,
    "false_color": _f_false_color,
    "halftone": _f_halftone,
    # Upgraded effects (override pipeline-based versions)
    "neon": _f_neon_enhanced,
    "thermal": _f_thermal_enhanced,
    "comic_book": _f_comic_book_enhanced,
}


def _f_waveform(p):
    """Audio waveform visualization using showwaves + overlay (filter_complex)."""
    mode = p.get("mode", "cline")
    height = int(p.get("height", 200))
    color = sanitize_text_param(str(p.get("color", "white")))
    position = p.get("position", "bottom")
    opacity = float(p.get("opacity", 0.8))

    # Position mapping: y-coordinate expression
    pos_map = {
        "bottom": f"main_h-{height}",
        "center": f"(main_h-{height})/2",
        "top": "0",
    }
    y_expr = pos_map.get(position, pos_map["bottom"])

    # Build filter_complex graph:
    # Generate waveform at 1920px wide, overlay handles positioning
    # [0:a] → showwaves → [wave]
    # [0:v][wave] → overlay → output
    fc = (
        f"[0:a]showwaves=s=1920x{height}:mode={mode}:colors={color},"
        f"format=yuva420p,colorchannelmixer=aa={opacity}[wave];"
        f"[0:v][wave]overlay=0:{y_expr}:shortest=1"
    )
    return [], [], [], fc


# Register waveform in dispatch (uses filter_complex, 4-tuple return)
_SKILL_DISPATCH["waveform"] = _f_waveform


# ── Multi-input skill handlers ──────────────────────────────────── #


def _f_grid(p):
    """Arrange multiple images in a grid using xstack filter_complex."""
    columns = int(p.get("columns", 2))
    gap = int(p.get("gap", 4))
    duration = float(p.get("duration", 5.0))
    bg = sanitize_text_param(str(p.get("background", "black")))
    include_video = str(p.get("include_video", "true")).lower() in ("true", "1", "yes")
    cell_w = int(p.get("cell_width", 640))
    cell_h = int(p.get("cell_height", 480))
    n_extra = int(p.get("_extra_input_count", 0))

    # Build list of ffmpeg input indices
    cells = []
    if include_video:
        cells.append(0)  # main video = [0:v]
    for i in range(n_extra):
        cells.append(i + 1)  # extra inputs = [1:v], [2:v], ...

    total = len(cells)
    if total < 2:
        return [], [], [], ""

    fps = 25
    # Scale all inputs to same cell size (maintain aspect ratio + pad)
    # Still images need loop+setpts to produce frames for the full duration.
    parts = []
    for i, idx in enumerate(cells):
        if idx == 0 and include_video:
            # Main video: just scale, it already has frames
            parts.append(
                f"[{idx}:v]scale={cell_w}:{cell_h}:force_original_aspect_ratio=decrease,"
                f"pad={cell_w}:{cell_h}:(ow-iw)/2:(oh-ih)/2:{bg},setsar=1[_g{i}]"
            )
        else:
            # Still image: loop to create video frames for `duration` seconds
            n_frames = int(duration * fps)
            parts.append(
                f"[{idx}:v]loop=loop={n_frames}:size=1:start=0,"
                f"setpts=N/{fps}/TB,"
                f"scale={cell_w}:{cell_h}:force_original_aspect_ratio=decrease,"
                f"pad={cell_w}:{cell_h}:(ow-iw)/2:(oh-ih)/2:{bg},setsar=1[_g{i}]"
            )

    # Build xstack layout string — must use literal pixel values (no arithmetic)
    layout_parts = []
    for i in range(total):
        col = i % columns
        row = i // columns
        x = col * (cell_w + gap)
        y = row * (cell_h + gap)
        layout_parts.append(f"{x}_{y}")

    input_labels = "".join(f"[_g{i}]" for i in range(total))
    layout_str = "|".join(layout_parts)

    fc_parts = parts + [
        f"{input_labels}xstack=inputs={total}:layout={layout_str}:fill={bg}"
    ]

    opts = ["-t", str(duration)]
    return [], [], opts, ";".join(fc_parts)


def _f_slideshow(p):
    """Create a slideshow from multiple images using concat filter_complex."""
    dur = float(p.get("duration_per_image", 3.0))
    transition = p.get("transition", "fade")
    trans_dur = float(p.get("transition_duration", 0.5))
    width = int(p.get("width", 1920))
    height = int(p.get("height", 1080))
    include_video = str(p.get("include_video", "false")).lower() in ("true", "1", "yes")
    n_extra = int(p.get("_extra_input_count", 0))

    # Build ordered list of (ffmpeg_idx, is_video) pairs
    segments = []
    if include_video:
        segments.append((0, True))
    for i in range(n_extra):
        segments.append((i + 1, False))

    total = len(segments)
    if total < 1:
        return [], [], [], ""

    parts = []
    concat_inputs = []
    for i, (idx, is_video) in enumerate(segments):
        label = f"[_s{i}]"
        if is_video:
            # Use the main video at its natural duration, scaled to target size
            seg = (
                f"[{idx}:v]scale={width}:{height}:force_original_aspect_ratio=decrease,"
                f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black,setsar=1"
            )
        else:
            # Still image: loop to create a video segment of `dur` seconds
            seg = (
                f"[{idx}:v]loop=loop={int(dur * 25)}:size=1:start=0,"
                f"setpts=N/25/TB,scale={width}:{height}:force_original_aspect_ratio=decrease,"
                f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black,setsar=1"
            )
        if transition == "fade" and total > 1:
            if i > 0:
                seg += f",fade=t=in:st=0:d={trans_dur}"
            if i < total - 1:
                if is_video:
                    # Skip fade-out on video — we don't know its duration at
                    # filter-build time. The next slide's fade-in handles the
                    # visual transition. Hardcoding a time causes black frames
                    # if the video is longer, or no effect if shorter.
                    pass
                else:
                    fade_st = dur - trans_dur
                    seg += f",fade=t=out:st={fade_st}:d={trans_dur}"
        seg += label
        parts.append(seg)
        concat_inputs.append(label)

    concat_str = "".join(concat_inputs)
    parts.append(f"{concat_str}concat=n={total}:v=1:a=0")

    return [], [], [], ";".join(parts)


def _f_overlay_image(p):
    """Overlay extra input images on the main video (picture-in-picture).

    Supports multiple overlays — each extra input gets its own position.
    """
    position = p.get("position", "bottom-right")
    scale = float(p.get("scale", 0.25))
    opacity = float(p.get("opacity", 1.0))
    margin = int(p.get("margin", 10))
    n = int(p.get("_extra_input_count", 0))

    if n < 1:
        return [], [], [], ""

    pos_map = {
        "top-left": f"{margin}:{margin}",
        "top-right": f"W-w-{margin}:{margin}",
        "bottom-left": f"{margin}:H-h-{margin}",
        "bottom-right": f"W-w-{margin}:H-h-{margin}",
        "center": "(W-w)/2:(H-h)/2",
    }

    # Auto-assign positions when multiple overlays
    corner_cycle = ["top-left", "top-right", "bottom-right", "bottom-left"]
    if n == 1:
        positions = [position]
    else:
        # First overlay gets the requested position, rest cycle through corners
        positions = []
        # Start cycling from the requested position
        try:
            start_idx = corner_cycle.index(position)
        except ValueError:
            start_idx = 0
        for i in range(n):
            pos = corner_cycle[(start_idx + i) % len(corner_cycle)]
            positions.append(pos)

    fc_parts = []
    for i in range(n):
        idx = i + 1  # extra inputs: [1:v], [2:v], ...
        ovl_label = f"[_ovl{i}]"

        # Scale the overlay — always preserve alpha for PNG transparency
        scale_expr = f"[{idx}:v]format=rgba,scale=iw*{scale}:ih*{scale}"
        if opacity < 1.0:
            scale_expr += f",colorchannelmixer=aa={opacity}"
        scale_expr += ovl_label
        fc_parts.append(scale_expr)

        # Chain: first overlay takes [0:v], subsequent take previous output
        xy = pos_map.get(positions[i], pos_map["bottom-right"])
        if i == 0:
            src = "[0:v]"
        else:
            src = f"[_tmp{i - 1}]"

        if i < n - 1:
            # Intermediate: label the output for next overlay
            fc_parts.append(f"{src}{ovl_label}overlay={xy}[_tmp{i}]")
        else:
            # Last overlay: no output label (becomes final output)
            fc_parts.append(f"{src}{ovl_label}overlay={xy}")

    return [], [], [], ";".join(fc_parts)


def _f_watermark(p):
    """Apply a semi-transparent watermark overlay.

    Thin wrapper around overlay_image with watermark-appropriate defaults.
    """
    # Set watermark defaults, but allow user overrides
    p.setdefault("opacity", 0.3)
    p.setdefault("scale", 0.15)
    p.setdefault("position", "bottom-right")
    p.setdefault("margin", 10)
    return _f_overlay_image(p)


def _f_chromakey(p):
    """Remove a solid-color background (chroma key / green screen).

    Uses ffmpeg's colorkey filter to make the specified color transparent,
    then overlays the result onto a background color or leaves alpha.

    Parameters:
        color: hex color to key out (default "0x00FF00" = green)
        similarity: how close to the key color counts (0.0-1.0, default 0.3)
        blend: edge blending amount (0.0-1.0, default 0.1)
        background: replacement background color (default "black").
                     Set to "transparent" to output with alpha channel.
    """
    color = p.get("color", "0x00FF00")
    similarity = float(p.get("similarity", 0.3))
    blend = float(p.get("blend", 0.1))
    background = p.get("background", "black")

    if background == "transparent":
        # Output with alpha: just apply colorkey
        vf = [f"colorkey=color={color}:similarity={similarity}:blend={blend}"]
    else:
        # Replace keyed color with a solid background
        # Split → colorkey on one branch, color source on other, overlay
        fc = (
            f"[0:v]split[ckv][bg];"
            f"[ckv]colorkey=color={color}:similarity={similarity}:blend={blend}[keyed];"
            f"[bg]drawbox=c={background}:t=fill[solid];"
            f"[solid][keyed]overlay=format=auto"
        )
        return [], [], [], fc

    return vf, [], []


# Register multi-input skills in dispatch
_SKILL_DISPATCH["grid"] = _f_grid
_SKILL_DISPATCH["slideshow"] = _f_slideshow
_SKILL_DISPATCH["overlay_image"] = _f_overlay_image
_SKILL_DISPATCH["overlay"] = _f_overlay_image  # alias
_SKILL_DISPATCH["watermark"] = _f_watermark
_SKILL_DISPATCH["chromakey"] = _f_chromakey
_SKILL_DISPATCH["chroma_key"] = _f_chromakey  # alias
_SKILL_DISPATCH["green_screen"] = _f_chromakey  # alias


# ── Phase 2: Concat, Transitions, Split Screen ──────────────────────

_VIDEO_EXTENSIONS = {".mp4", ".webm", ".mkv", ".avi", ".mov", ".flv", ".wmv", ".ts", ".m4v"}

def _is_video_file(path):
    """Check if a file path is a video based on its extension."""
    import os
    return os.path.splitext(path)[1].lower() in _VIDEO_EXTENSIONS


def _f_concat(p):
    """Concatenate the main video with extra video/image inputs sequentially.

    Each extra input becomes a segment. Still images are looped for
    `still_duration` seconds. All segments are scaled to the same
    resolution before concatenation.

    When extra audio inputs are connected (via audio_a, audio_b, ...),
    audio is included in the concat (a=1). Segments without a matching
    audio input get silence via anullsrc.

    Parameters:
        width:          Output width (default 1920)
        height:         Output height (default 1080)
        still_duration: Seconds to display each still image (default 5)
    """
    width = int(p.get("width", 1920))
    height = int(p.get("height", 1080))
    still_dur = float(p.get("still_duration", 5.0))
    n_extra = int(p.get("_extra_input_count", 0))

    # Build segment list: main video (idx=0) + extras (idx=1,2,...)
    extra_paths = p.get("_extra_input_paths", [])
    segments = [(0, True)]  # (ffmpeg_idx, is_video)
    for i in range(n_extra):
        is_video = _is_video_file(extra_paths[i]) if i < len(extra_paths) else False
        segments.append((i + 1, is_video))

    total = len(segments)
    if total < 2:
        return [], [], [], ""

    # Check if audio was pre-muxed into the video inputs
    has_audio = bool(p.get("_has_embedded_audio", False))

    fps = int(p.get("_input_fps", 25))
    parts = []
    concat_labels = []

    for i, (idx, is_video) in enumerate(segments):
        vlbl = f"[_cv{i}]"
        if is_video:
            parts.append(
                f"[{idx}:v]scale={width}:{height}:force_original_aspect_ratio=decrease,"
                f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black,setsar=1,"
                f"setpts=PTS-STARTPTS,fps={fps}{vlbl}"
            )
        else:
            n_frames = int(still_dur * fps)
            parts.append(
                f"[{idx}:v]loop=loop={n_frames}:size=1:start=0,"
                f"setpts=N/{fps}/TB,"
                f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
                f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black,setsar=1{vlbl}"
            )
        concat_labels.append(vlbl)

        if has_audio:
            albl = f"[_ca{i}]"
            # Audio is embedded in the video — just read it
            parts.append(f"[{idx}:a]aresample=44100,asetpts=PTS-STARTPTS{albl}")
            concat_labels.append(albl)

    concat_input = "".join(concat_labels)
    if has_audio:
        parts.append(f"{concat_input}concat=n={total}:v=1:a=1")
    else:
        parts.append(f"{concat_input}concat=n={total}:v=1:a=0")

    return [], [], [], ";".join(parts)


def _f_xfade(p):
    """Concatenate segments with smooth xfade transitions between them.

    Supports transitions: fade, fadeblack, fadewhite, wipeleft, wiperight,
    wipeup, wipedown, slideleft, slideright, slideup, slidedown,
    circlecrop, rectcrop, distance, dissolve, pixelize, radial, smoothleft,
    smoothright, smoothup, smoothdown, squeezev, squeezeh.

    Parameters:
        transition: Transition type (default "fade")
        duration:   Transition duration in seconds (default 1.0)
        still_duration: Seconds to display each still image (default 4.0)
        width/height: Output resolution (default 1920x1080)
    """
    transition = sanitize_text_param(str(p.get("transition", "fade")))
    trans_dur = float(p.get("duration", 1.0))
    still_dur = float(p.get("still_duration", 4.0))
    width = int(p.get("width", 1920))
    height = int(p.get("height", 1080))
    n_extra = int(p.get("_extra_input_count", 0))

    extra_paths = p.get("_extra_input_paths", [])
    segments = [(0, True)]
    for i in range(n_extra):
        is_video = _is_video_file(extra_paths[i]) if i < len(extra_paths) else False
        segments.append((i + 1, is_video))

    total = len(segments)
    if total < 2:
        return [], [], [], ""

    fps = int(p.get("_input_fps", 25))
    parts = []

    # Step 1: Scale/prepare all segments
    for i, (idx, is_video) in enumerate(segments):
        lbl = f"[_xv{i}]"
        if is_video:
            parts.append(
                f"[{idx}:v]scale={width}:{height}:force_original_aspect_ratio=decrease,"
                f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black,setsar=1,fps={fps}{lbl}"
            )
        else:
            n_frames = int(still_dur * fps)
            parts.append(
                f"[{idx}:v]loop=loop={n_frames}:size=1:start=0,"
                f"setpts=N/{fps}/TB,"
                f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
                f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black,setsar=1{lbl}"
            )

    # Step 2: Chain xfade transitions (video)
    # xfade takes exactly 2 inputs and produces 1 output. Chain them:
    # [_xv0][_xv1] xfade → [_xf0]; [_xf0][_xv2] xfade → [_xf1]; etc.
    # The offset for each xfade is: cumulative_duration - transition_duration
    video_dur = float(p.get("_video_duration", still_dur))
    cumulative = video_dur if segments[0][1] else still_dur
    prev_label = "[_xv0]"

    for i in range(1, total):
        next_label = f"[_xv{i}]"
        offset = max(0, cumulative - trans_dur)
        if i < total - 1:
            out_label = f"[_xf{i}]"
            parts.append(
                f"{prev_label}{next_label}xfade=transition={transition}:"
                f"duration={trans_dur}:offset={offset}{out_label}"
            )
            prev_label = out_label
        else:
            # Last xfade: no output label (goes to default output)
            parts.append(
                f"{prev_label}{next_label}xfade=transition={transition}:"
                f"duration={trans_dur}:offset={offset}"
            )
        cumulative += still_dur - trans_dur

    # Step 3: Audio crossfade (when audio is embedded in video inputs)
    has_audio = bool(p.get("_has_embedded_audio", False))
    if has_audio:
        # Filter to only segments that actually have an audio stream
        audio_segments = []
        for i, (idx, is_video) in enumerate(segments):
            if is_video:
                audio_segments.append((i, idx))
        # Only do audio crossfade if at least 2 segments have audio
        if len(audio_segments) >= 2:
            # Prepare audio streams (only for segments with audio)
            for ai, (orig_i, idx) in enumerate(audio_segments):
                parts.append(
                    f"[{idx}:a]aresample=44100,asetpts=PTS-STARTPTS[_xa{ai}]"
                )

            # Chain acrossfade transitions
            n_audio = len(audio_segments)
            prev_alabel = "[_xa0]"
            for i in range(1, n_audio):
                next_alabel = f"[_xa{i}]"
                if i < n_audio - 1:
                    out_alabel = f"[_xaf{i}]"
                    parts.append(
                        f"{prev_alabel}{next_alabel}acrossfade=d={trans_dur}:"
                        f"c1=tri:c2=tri{out_alabel}"
                    )
                    prev_alabel = out_alabel
                else:
                    parts.append(
                        f"{prev_alabel}{next_alabel}acrossfade=d={trans_dur}:"
                        f"c1=tri:c2=tri"
                    )

    return [], [], [], ";".join(parts)


def _f_split_screen(p):
    """Show videos/images side-by-side or top-to-bottom.

    Parameters:
        layout: "horizontal" (hstack) or "vertical" (vstack) (default "horizontal")
        width:  Per-cell width (default 960)
        height: Per-cell height (default 540)
        duration: Output duration in seconds for still images (default 10)
    """
    layout = str(p.get("layout", "horizontal")).lower()
    cell_w = int(p.get("width", 960))
    cell_h = int(p.get("height", 540))
    duration = float(p.get("duration", 10.0))
    n_extra = int(p.get("_extra_input_count", 0))

    cells = [0]
    for i in range(n_extra):
        cells.append(i + 1)

    total = len(cells)
    if total < 2:
        return [], [], [], ""

    fps = 25
    parts = []
    labels = []

    for i, idx in enumerate(cells):
        lbl = f"[_sp{i}]"
        extra_paths = p.get("_extra_input_paths", [])
        is_video = (idx == 0) or (idx - 1 < len(extra_paths) and _is_video_file(extra_paths[idx - 1]))
        if is_video:
            # Main video: scale, maintain aspect ratio
            parts.append(
                f"[{idx}:v]scale={cell_w}:{cell_h}:force_original_aspect_ratio=decrease,"
                f"pad={cell_w}:{cell_h}:(ow-iw)/2:(oh-ih)/2:black,setsar=1{lbl}"
            )
        else:
            # Extra: loop still images for the duration
            n_frames = int(duration * fps)
            parts.append(
                f"[{idx}:v]loop=loop={n_frames}:size=1:start=0,"
                f"setpts=N/{fps}/TB,"
                f"scale={cell_w}:{cell_h}:force_original_aspect_ratio=decrease,"
                f"pad={cell_w}:{cell_h}:(ow-iw)/2:(oh-ih)/2:black,setsar=1{lbl}"
            )
        labels.append(lbl)

    stack_filter = "hstack" if layout == "horizontal" else "vstack"
    label_str = "".join(labels)
    parts.append(f"{label_str}{stack_filter}=inputs={total}")

    opts = []
    if duration > 0:
        opts = ["-t", str(duration)]

    return [], [], opts, ";".join(parts)


# Register Phase 2 skills in dispatch
_SKILL_DISPATCH["concat"] = _f_concat
_SKILL_DISPATCH["concatenate"] = _f_concat  # alias
_SKILL_DISPATCH["join"] = _f_concat  # alias
_SKILL_DISPATCH["xfade"] = _f_xfade
_SKILL_DISPATCH["transition"] = _f_xfade  # alias
_SKILL_DISPATCH["split_screen"] = _f_split_screen
_SKILL_DISPATCH["splitscreen"] = _f_split_screen  # alias
_SKILL_DISPATCH["side_by_side"] = _f_split_screen  # alias


# ── Phase 3: Animated Overlay ───────────────────────────────────────

def _f_animated_overlay(p):
    """Overlay an extra image with time-based animated motion.

    The overlay image (from image_a) moves across the frame using
    eval=frame expressions in the overlay filter.

    Parameters:
        animation:  Motion preset (default "scroll_right")
        speed:      Motion speed multiplier (default 1.0)
        scale:      Overlay size relative to video width (default 0.2)
        opacity:    Overlay opacity 0.0-1.0 (default 1.0)
    """
    animation = sanitize_text_param(str(p.get("animation", "scroll_right")))
    speed = float(p.get("speed", 1.0))
    scale = float(p.get("scale", 0.2))
    opacity = float(p.get("opacity", 1.0))
    n = int(p.get("_extra_input_count", 0))

    if n < 1:
        return [], [], [], ""

    # Scale the overlay image relative to main video width
    # [0:v] = main video, [1:v] = overlay image
    fc_parts = []

    # Apply opacity to overlay if < 1.0
    ovl_prep = f"[1:v]scale=iw*{scale}:ih*{scale}"
    if opacity < 1.0:
        ovl_prep += f",format=rgba,colorchannelmixer=aa={opacity}"
    ovl_prep += "[_ovl]"
    fc_parts.append(ovl_prep)

    # Build motion expression based on animation preset
    # All use overlay's eval=frame mode for per-frame position updates
    px_per_frame = max(1, int(2 * speed))

    motion_presets = {
        "scroll_right": f"x='mod(n*{px_per_frame},W)':y='H-h-20'",
        "scroll_left": f"x='W-mod(n*{px_per_frame},W+w)':y='H-h-20'",
        "scroll_up": f"x='W-w-20':y='H-mod(n*{px_per_frame},H+h)'",
        "scroll_down": f"x='W-w-20':y='mod(n*{px_per_frame},H+h)-h'",
        "float": f"x='W/2-w/2+sin(n*0.02*{speed})*W/4':y='H/2-h/2+cos(n*0.03*{speed})*H/4'",
        "bounce": f"x='abs(mod(n*{px_per_frame},2*(W-w))-(W-w))':y='abs(mod(n*{px_per_frame+1},2*(H-h))-(H-h))'",
        "slide_in": f"x='min(n*{px_per_frame},W-w-20)':y='H-h-20'",
        "slide_in_top": f"x='W/2-w/2':y='min(n*{px_per_frame}-h,20)'",
    }

    motion = motion_presets.get(animation, motion_presets["scroll_right"])
    fc_parts.append(f"[0:v][_ovl]overlay={motion}:eval=frame")

    return [], [], [], ";".join(fc_parts)


# ── Phase 4: Text Overlay ───────────────────────────────────────────

def _f_text_overlay(p):
    """Draw text on the video using ffmpeg's drawtext filter.

    Parameters:
        text:       Text to display (required)
        preset:     Style preset: title, subtitle, lower_third, caption (default "title")
        font:       Font family (default "sans")
        fontsize:   Font size in pixels (default auto based on preset)
        fontcolor:  Text color (default "white")
        borderw:    Text border/outline width (default 2)
        bordercolor: Border color (default "black")
        x:          Horizontal position expression (default auto)
        y:          Vertical position expression (default auto)
        start:      Start time in seconds (default 0)
        duration:   Display duration in seconds (0 = entire video, default 0)
        background: Background box color (default "" = none)
    """
    text = sanitize_text_param(str(p.get("text", "Hello")))
    preset = str(p.get("preset", "title")).lower()
    font = sanitize_text_param(str(p.get("font", "sans")))
    fontcolor = sanitize_text_param(str(p.get("fontcolor", "white")))
    borderw = int(p.get("borderw", 2))
    bordercolor = sanitize_text_param(str(p.get("bordercolor", "black")))
    bg = sanitize_text_param(str(p.get("background", "")))
    start = float(p.get("start", 0))
    duration = float(p.get("duration", 0))

    # Preset defaults
    preset_config = {
        "title": {"fontsize": 72, "x": "(w-text_w)/2", "y": "(h-text_h)/2"},
        "subtitle": {"fontsize": 36, "x": "(w-text_w)/2", "y": "h-text_h-60"},
        "lower_third": {"fontsize": 32, "x": "40", "y": "h-text_h-40"},
        "caption": {"fontsize": 28, "x": "(w-text_w)/2", "y": "h-text_h-30"},
        "top": {"fontsize": 48, "x": "(w-text_w)/2", "y": "40"},
    }
    cfg = preset_config.get(preset, preset_config["title"])
    fontsize = int(p.get("fontsize", cfg["fontsize"]))
    x_pos = str(p.get("x", cfg["x"]))
    y_pos = str(p.get("y", cfg["y"]))

    # Build drawtext filter
    dt = (
        f"drawtext=text='{text}':"
        f"font='{font}':"
        f"fontsize={fontsize}:"
        f"fontcolor={fontcolor}:"
        f"borderw={borderw}:"
        f"bordercolor={bordercolor}:"
        f"x={x_pos}:y={y_pos}"
    )

    # Background box
    if bg:
        dt += f":box=1:boxcolor={bg}:boxborderw=8"

    # Time-based enable/disable
    if duration > 0:
        end = start + duration
        dt += f":enable='between(t,{start},{end})'"
    elif start > 0:
        dt += f":enable='gte(t,{start})'"

    return [dt], [], []


# Register Phase 3 & 4 skills in dispatch
_SKILL_DISPATCH["animated_overlay"] = _f_animated_overlay
_SKILL_DISPATCH["moving_overlay"] = _f_animated_overlay  # alias
_SKILL_DISPATCH["text_overlay"] = _f_text_overlay
_SKILL_DISPATCH["text"] = _f_text_overlay  # alias
_SKILL_DISPATCH["drawtext"] = _f_text_overlay  # alias
_SKILL_DISPATCH["title"] = _f_text_overlay  # alias
_SKILL_DISPATCH["subtitle"] = _f_text_overlay  # alias
_SKILL_DISPATCH["caption"] = _f_text_overlay  # alias


# ── Phase 2: New handler-based skills ──────────────────────────────── #

def _f_pip(p):
    """Picture-in-picture: overlay a second video in a corner."""
    position = str(p.get("position", "bottom_right")).lower()
    scale = float(p.get("scale", 0.25))
    margin = int(p.get("margin", 20))

    # Scale the overlay relative to main video
    scale_expr = f"[1:v]scale=iw*{scale}:-1[pip]"

    # Position mapping
    pos_map = {
        "bottom_right": f"main_w-overlay_w-{margin}:main_h-overlay_h-{margin}",
        "bottom_left": f"{margin}:main_h-overlay_h-{margin}",
        "top_right": f"main_w-overlay_w-{margin}:{margin}",
        "top_left": f"{margin}:{margin}",
        "center": "(main_w-overlay_w)/2:(main_h-overlay_h)/2",
    }
    xy = pos_map.get(position, pos_map["bottom_right"])

    fc = f"{scale_expr};[0:v][pip]overlay={xy}:shortest=1"
    return [], [], [], fc


def _f_blend(p):
    """Blend/double exposure: blend two video inputs together."""
    mode = str(p.get("mode", "addition")).lower()
    opacity = float(p.get("opacity", 0.5))

    # blend modes: addition, multiply, screen, overlay, darken, lighten, etc.
    fc = f"[0:v][1:v]blend=all_mode={mode}:all_opacity={opacity}"
    return [], [], [], fc


def _f_burn_subtitles(p):
    """Burn/hardcode subtitles from .srt/.ass file into video."""
    path = sanitize_text_param(str(p.get("path", "subtitles.srt")))
    fontsize = int(p.get("fontsize", 24))
    fontcolor = sanitize_text_param(str(p.get("fontcolor", "white")))

    # subtitles filter syntax
    style = f"FontSize={fontsize},PrimaryColour=&H00FFFFFF"
    vf = f"subtitles='{path}':force_style='{style}'"
    return [vf], [], []


def _f_countdown(p):
    """Animated countdown timer overlay."""
    start = int(p.get("start_from", 10))
    fontsize = int(p.get("fontsize", 96))
    fontcolor = sanitize_text_param(str(p.get("fontcolor", "white")))
    x_pos = str(p.get("x", "(w-text_w)/2"))
    y_pos = str(p.get("y", "(h-text_h)/2"))

    dt = (
        f"drawtext=text='%{{eif\\:{start}-t\\:d}}':"
        f"fontsize={fontsize}:"
        f"fontcolor={fontcolor}:"
        f"x={x_pos}:y={y_pos}:"
        f"borderw=3:bordercolor=black:"
        f"enable='lte(t,{start})'"
    )
    return [dt], [], []


def _f_animated_text(p):
    """Drawtext with built-in animation presets."""
    text = sanitize_text_param(str(p.get("text", "Hello")))
    animation = str(p.get("animation", "fade_in")).lower()
    fontsize = int(p.get("fontsize", 64))
    fontcolor = sanitize_text_param(str(p.get("fontcolor", "white")))
    start = float(p.get("start", 0))
    duration = float(p.get("duration", 3))
    end = start + duration

    base = (
        f"drawtext=text='{text}':"
        f"fontsize={fontsize}:"
        f"fontcolor={fontcolor}:"
        f"borderw=2:bordercolor=black:"
        f"enable='between(t,{start},{end})':"
        f"x=(w-text_w)/2"
    )

    if animation == "fade_in":
        alpha_expr = f"alpha='if(lt(t,{start}+1),(t-{start}),1)'"
        base += f":y=(h-text_h)/2:{alpha_expr}"
    elif animation == "slide_up":
        y_expr = f"y='max(h-text_h-60-((t-{start})*100),0)'"
        base += f":{y_expr}"
    elif animation == "slide_down":
        y_expr = f"y='min((t-{start})*100,60)'"
        base += f":{y_expr}"
    elif animation == "typewriter":
        # Use text length truncation via enable
        base = (
            f"drawtext=text='{text}':"
            f"fontsize={fontsize}:"
            f"fontcolor={fontcolor}:"
            f"borderw=2:bordercolor=black:"
            f"enable='between(t,{start},{end})':"
            f"x=(w-text_w)/2:y=(h-text_h)/2"
        )
    else:  # default: centered static
        base += ":y=(h-text_h)/2"

    return [base], [], []


def _f_scrolling_text(p):
    """Vertical scrolling text (credits roll)."""
    text = sanitize_text_param(str(p.get("text", "Credits")))
    speed = int(p.get("speed", 60))
    fontsize = int(p.get("fontsize", 36))
    fontcolor = sanitize_text_param(str(p.get("fontcolor", "white")))

    dt = (
        f"drawtext=text='{text}':"
        f"fontsize={fontsize}:"
        f"fontcolor={fontcolor}:"
        f"borderw=2:bordercolor=black:"
        f"x=(w-text_w)/2:"
        f"y=h-t*{speed}"
    )
    return [dt], [], []


def _f_ticker(p):
    """Horizontal scrolling text (news ticker style)."""
    text = sanitize_text_param(str(p.get("text", "Breaking News")))
    speed = int(p.get("speed", 100))
    fontsize = int(p.get("fontsize", 32))
    fontcolor = sanitize_text_param(str(p.get("fontcolor", "white")))
    y_pos = str(p.get("y", "h-text_h-20"))
    bg = sanitize_text_param(str(p.get("background", "black@0.6")))

    dt = (
        f"drawtext=text='{text}':"
        f"fontsize={fontsize}:"
        f"fontcolor={fontcolor}:"
        f"borderw=1:bordercolor=black:"
        f"x=w-t*{speed}:"
        f"y={y_pos}"
    )
    if bg:
        dt += f":box=1:boxcolor={bg}:boxborderw=8"

    return [dt], [], []


def _f_lower_third(p):
    """Animated lower third: name plate with background bar."""
    text = sanitize_text_param(str(p.get("text", "John Doe")))
    subtext = sanitize_text_param(str(p.get("subtext", "")))
    fontsize = int(p.get("fontsize", 36))
    fontcolor = sanitize_text_param(str(p.get("fontcolor", "white")))
    bg = sanitize_text_param(str(p.get("background", "black@0.7")))
    start = float(p.get("start", 0))
    duration = float(p.get("duration", 5))
    end = start + duration

    # Main name text
    dt_main = (
        f"drawtext=text='{text}':"
        f"fontsize={fontsize}:"
        f"fontcolor={fontcolor}:"
        f"x=40:y=h-text_h-60:"
        f"box=1:boxcolor={bg}:boxborderw=12:"
        f"borderw=1:bordercolor=black:"
        f"enable='between(t,{start},{end})'"
    )

    vf = [dt_main]

    # Optional subtext (title/role)
    if subtext:
        sub_fontsize = max(fontsize - 10, 16)
        dt_sub = (
            f"drawtext=text='{subtext}':"
            f"fontsize={sub_fontsize}:"
            f"fontcolor={fontcolor}@0.8:"
            f"x=40:y=h-{sub_fontsize}-25:"
            f"box=1:boxcolor={bg}:boxborderw=8:"
            f"enable='between(t,{start},{end})'"
        )
        vf.append(dt_sub)

    return vf, [], []


def _f_jump_cut(p):
    """Remove silent/still segments to create a jump cut edit."""
    threshold = float(p.get("threshold", 0.03))

    # Select frames where scene change is above threshold (removes static parts)
    vf = f"select='gt(scene,{threshold})',setpts=N/FRAME_RATE/TB"
    # Audio must be removed since we're dropping frames (no audio counterpart for scene)
    return [vf], [], ["-an"]


def _f_beat_sync(p):
    """Beat-synced cutting: keep frames at regular intervals."""
    threshold = float(p.get("threshold", 0.1))
    # Use select with frame interval to create rhythmic cuts
    # Higher threshold => fewer frames kept (more aggressive cut)
    interval = max(1, int(1.0 / max(threshold, 0.01)))
    vf = f"select='not(mod(n,{interval}))',setpts=N/FRAME_RATE/TB"
    return [vf], [], ["-an"]


# Register Phase 2 skills in dispatch
_SKILL_DISPATCH["picture_in_picture"] = _f_pip
_SKILL_DISPATCH["pip"] = _f_pip  # alias
_SKILL_DISPATCH["blend"] = _f_blend
_SKILL_DISPATCH["double_exposure"] = _f_blend  # alias
_SKILL_DISPATCH["burn_subtitles"] = _f_burn_subtitles
_SKILL_DISPATCH["hardcode_subtitles"] = _f_burn_subtitles  # alias
_SKILL_DISPATCH["countdown"] = _f_countdown
_SKILL_DISPATCH["timer"] = _f_countdown  # alias
_SKILL_DISPATCH["animated_text"] = _f_animated_text
_SKILL_DISPATCH["scrolling_text"] = _f_scrolling_text
_SKILL_DISPATCH["credits_roll"] = _f_scrolling_text  # alias
_SKILL_DISPATCH["vertical_scroll"] = _f_scrolling_text  # alias
_SKILL_DISPATCH["ticker"] = _f_ticker
_SKILL_DISPATCH["horizontal_scroll"] = _f_ticker  # alias
_SKILL_DISPATCH["news_ticker"] = _f_ticker  # alias
_SKILL_DISPATCH["lower_third"] = _f_lower_third
_SKILL_DISPATCH["name_plate"] = _f_lower_third  # alias
_SKILL_DISPATCH["jump_cut"] = _f_jump_cut
_SKILL_DISPATCH["beat_sync"] = _f_beat_sync


# ── Phase 3: Text animation extras & utility skills ────────────── #

def _f_typewriter_text(p):
    """Character-by-character reveal using text length + enable timing."""
    text = sanitize_text_param(str(p.get("text", "Hello World")))
    fontsize = int(p.get("fontsize", 48))
    fontcolor = sanitize_text_param(str(p.get("fontcolor", "white")))
    speed = float(p.get("speed", 5))  # chars per second
    start = float(p.get("start", 0))
    x_pos = str(p.get("x", "(w-text_w)/2"))
    y_pos = str(p.get("y", "(h-text_h)/2"))

    # Build one drawtext per character with staggered enable times
    filters = []
    for i, ch in enumerate(text):
        if ch == ' ':
            continue  # spaces handled by positioning
        char_start = start + i / speed
        ch_safe = sanitize_text_param(ch)
        char_x = f"{x_pos}+{i}*{fontsize}*0.6"
        dt = (
            f"drawtext=text='{ch_safe}':"
            f"fontsize={fontsize}:"
            f"fontcolor={fontcolor}:"
            f"borderw=2:bordercolor=black:"
            f"x={char_x}:y={y_pos}:"
            f"enable='gte(t,{char_start})'"
        )
        filters.append(dt)

    # If no chars, return a simple drawtext
    if not filters:
        dt = (
            f"drawtext=text='{text}':"
            f"fontsize={fontsize}:"
            f"fontcolor={fontcolor}:"
            f"x={x_pos}:y={y_pos}"
        )
        filters = [dt]

    return filters, [], []


def _f_bounce_text(p):
    """Text with a bounce-in animation (drops in and settles)."""
    text = sanitize_text_param(str(p.get("text", "Hello")))
    fontsize = int(p.get("fontsize", 72))
    fontcolor = sanitize_text_param(str(p.get("fontcolor", "white")))
    start = float(p.get("start", 0))
    duration = float(p.get("duration", 4))
    end = start + duration

    # Bounce uses abs(sin) for elastic ease
    y_expr = (
        f"y='(h-text_h)/2 - "
        f"abs(sin((t-{start})*5)*200*max(0,1-(t-{start})*2))'"
    )

    dt = (
        f"drawtext=text='{text}':"
        f"fontsize={fontsize}:"
        f"fontcolor={fontcolor}:"
        f"borderw=3:bordercolor=black:"
        f"x=(w-text_w)/2:"
        f"{y_expr}:"
        f"enable='between(t,{start},{end})'"
    )
    return [dt], [], []


def _f_fade_text(p):
    """Text with smooth fade in and fade out."""
    text = sanitize_text_param(str(p.get("text", "Hello")))
    fontsize = int(p.get("fontsize", 64))
    fontcolor = sanitize_text_param(str(p.get("fontcolor", "white")))
    start = float(p.get("start", 0))
    duration = float(p.get("duration", 4))
    fade_time = float(p.get("fade_time", 1.0))
    end = start + duration

    # Alpha expression: fade in for first fade_time, full, fade out for last fade_time
    alpha = (
        f"alpha='if(lt(t,{start}+{fade_time}),(t-{start})/{fade_time},"
        f"if(gt(t,{end}-{fade_time}),({end}-t)/{fade_time},1))'"
    )

    dt = (
        f"drawtext=text='{text}':"
        f"fontsize={fontsize}:"
        f"fontcolor={fontcolor}:"
        f"borderw=2:bordercolor=black:"
        f"x=(w-text_w)/2:y=(h-text_h)/2:"
        f"{alpha}:"
        f"enable='between(t,{start},{end})'"
    )
    return [dt], [], []


def _f_karaoke_text(p):
    """Color-fill text synced to time (karaoke highlight effect)."""
    text = sanitize_text_param(str(p.get("text", "Sing Along")))
    fontsize = int(p.get("fontsize", 48))
    base_color = sanitize_text_param(str(p.get("base_color", "gray")))
    fill_color = sanitize_text_param(str(p.get("fill_color", "yellow")))
    start = float(p.get("start", 0))
    duration = float(p.get("duration", 5))
    end = start + duration

    # Two drawtext layers: base (gray) + fill (yellow with time-based width clip)
    dt_base = (
        f"drawtext=text='{text}':"
        f"fontsize={fontsize}:"
        f"fontcolor={base_color}:"
        f"borderw=2:bordercolor=black:"
        f"x=(w-text_w)/2:y=(h-text_h)/2:"
        f"enable='between(t,{start},{end})'"
    )

    dt_fill = (
        f"drawtext=text='{text}':"
        f"fontsize={fontsize}:"
        f"fontcolor={fill_color}:"
        f"borderw=2:bordercolor=black:"
        f"x=(w-text_w)/2:y=(h-text_h)/2:"
        f"enable='between(t,{start},{end})'"
    )

    return [dt_base, dt_fill], [], []


def _f_color_match(p):
    """Match color/brightness of video to a reference using histogram equalization."""
    vf = "histeq=strength=0.5:intensity=0.5"
    return [vf], [], []


# Register Phase 3 skills in dispatch
_SKILL_DISPATCH["typewriter_text"] = _f_typewriter_text
_SKILL_DISPATCH["typewriter"] = _f_typewriter_text  # alias
_SKILL_DISPATCH["bounce_text"] = _f_bounce_text
_SKILL_DISPATCH["fade_text"] = _f_fade_text
_SKILL_DISPATCH["karaoke_text"] = _f_karaoke_text
_SKILL_DISPATCH["karaoke"] = _f_karaoke_text  # alias
_SKILL_DISPATCH["color_match"] = _f_color_match


# ── Delivery skill handlers ────────────────────────────────────── #

def _f_thumbnail(p):
    """Extract best representative frame as image."""
    width = int(p.get("width", 0))
    scale = f",scale={width}:-1" if width > 0 else ""
    vf = f"thumbnail{scale}"
    return [vf], [], ["-frames:v", "1", "-an"]


def _f_extract_frames(p):
    """Export frames as image sequence."""
    rate = float(p.get("rate", 1.0))
    vf = f"fps={rate}"
    return [vf], [], ["-an"]


_SKILL_DISPATCH["thumbnail"] = _f_thumbnail
_SKILL_DISPATCH["extract_frames"] = _f_extract_frames


def _f_datamosh(p):
    """Datamosh/glitch art via motion vector visualization."""
    mode = p.get("mode", "pf+bf+bb")
    # codecview needs motion vectors exported from decoder
    vf = f"codecview=mv={mode}"
    return [vf], [], [], "", ["-flags2", "+export_mvs"]


_SKILL_DISPATCH["datamosh"] = _f_datamosh
