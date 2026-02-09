"""Skill composition engine for building FFMPEG pipelines."""

from dataclasses import dataclass, field
from typing import Optional, Any
from pathlib import Path

from .registry import SkillRegistry, Skill, SkillCategory, ParameterType, get_registry
from ..core.executor.command_builder import CommandBuilder, FFMPEGCommand


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

            skill = self.registry.get(step.skill_name)
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

            # Inject multi-input metadata for handlers that need it
            if pipeline.extra_inputs:
                step.params["_extra_input_count"] = len(pipeline.extra_inputs)

            # Get filters/options for this skill
            vf, af, opts, fc = self._skill_to_filters(skill, step.params)
            video_filters.extend(vf)
            audio_filters.extend(af)
            output_options.extend(opts)
            if fc:
                complex_filters.append(fc)

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
                    # apply video filters as a separate chain on the output
                    fc_graph += f";[0:v]{vf_chain}[_vout]"

            # If filter_complex consumes [0:a] (e.g. waveform), we cannot
            # also use -af — fold audio filters into the graph instead.
            if "[0:a]" in fc_graph and audio_filters:
                af_chain = ",".join(audio_filters)
                fc_graph += f";[0:a]{af_chain}[_aout]"
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

        # Apply output options
        builder.output_options(*output_options)
        builder.output(pipeline.output_path)

        return builder.build()

    def _skill_to_filters(
        self,
        skill: Skill,
        params: dict,
    ) -> tuple[list[str], list[str], list[str], str]:
        """Convert a skill invocation to FFMPEG filters.

        Args:
            skill: Skill to convert.
            params: Parameters for the skill.

        Returns:
            Tuple of (video_filters, audio_filters, output_options, filter_complex).
            filter_complex is an empty string if not needed.
        """
        video_filters = []
        audio_filters = []
        output_options = []
        filter_complex = ""

        # If skill has a template, use it
        if skill.ffmpeg_template:
            template = skill.ffmpeg_template
            for key, value in params.items():
                template = template.replace(f"{{{key}}}", str(value))

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
                    vf, af, opts, fc = self._skill_to_filters(sub_skill, sub_params)
                    video_filters.extend(vf)
                    audio_filters.extend(af)
                    output_options.extend(opts)
                    if fc:
                        filter_complex = fc if not filter_complex else f"{filter_complex};{fc}"

        # Handle specific skill types
        else:
            vf, af, opts, fc = self._builtin_skill_filters(skill.name, params)
            video_filters.extend(vf)
            audio_filters.extend(af)
            output_options.extend(opts)
            if fc:
                filter_complex = fc

        return video_filters, audio_filters, output_options, filter_complex

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
    ) -> tuple[list[str], list[str], list[str], str]:
        """Generate filters for built-in skills using dispatch table.

        Args:
            skill_name: Name of the skill.
            params: Parameters.

        Returns:
            Tuple of (video_filters, audio_filters, output_options, filter_complex).
        """
        handler = _SKILL_DISPATCH.get(skill_name)
        if handler is None:
            return [], [], [], ""
        result = handler(params)
        # Handlers may return 3-tuple (vf, af, opts) or 4-tuple (vf, af, opts, fc)
        if len(result) == 4:
            return result
        vf, af, opts = result
        return vf, af, opts, ""


# ====================================================================== #
#  Per-skill filter handlers                                               #
#  Each returns (video_filters: list, audio_filters: list, opts: list)     #
# ====================================================================== #

def _f_trim(p):
    opts = []
    if p.get("start"):
        opts.extend(["-ss", str(p["start"])])
    if p.get("end"):
        opts.extend(["-to", str(p["end"])])
    if p.get("duration"):
        opts.extend(["-t", str(p["duration"])])
    return [], [], opts


def _f_speed(p):
    factor = p.get("factor", 1.0)
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
    count = p.get("count", 2)
    return [f"loop=loop={count}:size=32767"], [], []


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
    color = p.get("color", "black")
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
    intensity = p.get("intensity", 0.3)
    return [f"vignette=PI/4*{intensity}"], [], []


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


def _f_text_overlay(p):
    from ..core.sanitize import sanitize_text_param
    text = sanitize_text_param(str(p.get("text", "")))
    size = p.get("size", 48)
    color = p.get("color", "white")
    font = p.get("font", "Sans")
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
    amount = float(p.get("amount", 0.2))
    # Animated zoom/pan using crop with time-varying expressions
    # Amount is the fraction of the frame to travel (0.2 = 20%)
    margin = int(amount * 200)  # extra pixels to pad
    speed = max(1, margin // 10)
    if direction == "zoom_in":
        # Start wide (padded), crop inward over time
        return [
            f"pad=iw+{margin}:ih+{margin}:{margin//2}:{margin//2}:black,"
            f"crop=iw-{margin}+min({speed}*t\\,{margin}):"
            f"ih-{margin}+min({speed}*t\\,{margin}):"
            f"max({margin//2}-{speed//2}*t\\,0):"
            f"max({margin//2}-{speed//2}*t\\,0),"
            f"scale=iw:ih"
        ], [], []
    elif direction == "zoom_out":
        # Start cropped, expand outward over time
        return [
            f"pad=iw+{margin}:ih+{margin}:{margin//2}:{margin//2}:black,"
            f"crop=iw-min({speed}*t\\,{margin}):"
            f"ih-min({speed}*t\\,{margin}):"
            f"min({speed//2}*t\\,{margin//2}):"
            f"min({speed//2}*t\\,{margin//2}),"
            f"scale=iw:ih"
        ], [], []
    elif direction == "pan_right":
        return _f_drift({"direction": "right", "amount": margin})
    elif direction == "pan_left":
        return _f_drift({"direction": "left", "amount": margin})
    else:
        return _f_drift({"direction": "right", "amount": margin})


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
    color = p.get("color", "black")
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


def _f_chromakey(p):
    color = p.get("color", "green")
    # Map common names to hex
    color_map = {"green": "0x00FF00", "blue": "0x0000FF", "red": "0xFF0000"}
    color_hex = color_map.get(color.lower(), color)
    similarity = float(p.get("similarity", 0.3))
    blend = float(p.get("blend", 0.1))
    return [f"chromakey=color={color_hex}:similarity={similarity}:blend={blend}"], [], []


def _f_deband(p):
    thr = float(p.get("threshold", 0.04))
    rng = int(p.get("range", 16))
    return [f"deband=1thr={thr}:2thr={thr}:3thr={thr}:range={rng}"], [], []


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
    color = p.get("color", "black")
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
    return [], [], ["-hwaccel", accel_type]


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
    "text_overlay": _f_text_overlay,
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
    "chromakey": _f_chromakey,
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
}


def _f_waveform(p):
    """Audio waveform visualization using showwaves + overlay (filter_complex)."""
    mode = p.get("mode", "cline")
    height = int(p.get("height", 200))
    color = p.get("color", "white")
    position = p.get("position", "bottom")
    opacity = float(p.get("opacity", 0.8))

    # Position mapping: y-coordinate expression
    pos_map = {
        "bottom": f"H-{height}",
        "center": f"(H-{height})/2",
        "top": "0",
    }
    y_expr = pos_map.get(position, pos_map["bottom"])

    # Build filter_complex graph:
    # [0:a] → showwaves → [wave]
    # [0:v][wave] → overlay → output
    fc = (
        f"[0:a]showwaves=s=Wx{height}:mode={mode}:colors={color},"
        f"format=yuva420p,colorchannelmixer=aa={opacity}[wave];"
        f"[0:v][wave]overlay=0:{y_expr}"
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
    bg = p.get("background", "black")
    n = int(p.get("_extra_input_count", 0))

    if n < 2:
        # Not enough images — fall back to single input passthrough
        return [], [], [], ""

    rows = (n + columns - 1) // columns  # ceil division

    # Scale all extra inputs to same size and pad for gap
    # Use the first extra input's dimensions as target (scale all to match)
    parts = []
    for i in range(n):
        idx = i + 1  # extra inputs start at [1:v]
        parts.append(
            f"[{idx}:v]scale=iw:ih,setsar=1[_g{i}]"
        )

    # Build xstack layout string
    # layout format: "x0_y0|x1_y1|..." where positions are expressions
    layout_parts = []
    for i in range(n):
        col = i % columns
        row = i // columns
        x = f"{col}*(w0+{gap})" if col > 0 else "0"
        y = f"{row}*(h0+{gap})" if row > 0 else "0"
        layout_parts.append(f"{x}_{y}")

    input_labels = "".join(f"[_g{i}]" for i in range(n))
    layout_str = "|".join(layout_parts)

    fc_parts = parts + [
        f"{input_labels}xstack=inputs={n}:layout={layout_str}:fill={bg}"
    ]

    # Add duration control via output options
    opts = ["-t", str(duration)]
    return [], [], opts, ";".join(fc_parts)


def _f_slideshow(p):
    """Create a slideshow from multiple images using concat filter_complex."""
    dur = float(p.get("duration_per_image", 3.0))
    transition = p.get("transition", "fade")
    trans_dur = float(p.get("transition_duration", 0.5))
    width = int(p.get("width", 1920))
    height = int(p.get("height", 1080))
    n = int(p.get("_extra_input_count", 0))

    if n < 1:
        return [], [], [], ""

    # Scale each extra input to target size and set duration
    parts = []
    concat_inputs = []
    for i in range(n):
        idx = i + 1
        scale = f"[{idx}:v]loop=loop={int(dur * 25)}:size=1:start=0,"
        scale += f"setpts=N/25/TB,scale={width}:{height}:force_original_aspect_ratio=decrease,"
        scale += f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black,setsar=1"
        if transition == "fade" and n > 1:
            # Add fade out at end (except last) and fade in at start (except first)
            if i > 0:
                scale += f",fade=t=in:st=0:d={trans_dur}"
            if i < n - 1:
                fade_st = dur - trans_dur
                scale += f",fade=t=out:st={fade_st}:d={trans_dur}"
        label = f"[_s{i}]"
        scale += label
        parts.append(scale)
        concat_inputs.append(label)

    # Concatenate all scaled inputs
    concat_str = "".join(concat_inputs)
    parts.append(f"{concat_str}concat=n={n}:v=1:a=0")

    return [], [], [], ";".join(parts)


def _f_overlay_image(p):
    """Overlay an extra input image on the main video (picture-in-picture)."""
    position = p.get("position", "bottom-right")
    scale = float(p.get("scale", 0.25))
    opacity = float(p.get("opacity", 1.0))
    margin = int(p.get("margin", 10))
    n = int(p.get("_extra_input_count", 0))

    if n < 1:
        return [], [], [], ""

    # Scale the overlay image (first extra input = [1:v])
    scale_expr = f"[1:v]scale=iw*{scale}:ih*{scale}"
    if opacity < 1.0:
        scale_expr += f",format=yuva420p,colorchannelmixer=aa={opacity}"
    scale_expr += "[_ovl]"

    # Position mapping
    pos_map = {
        "top-left": f"{margin}:{margin}",
        "top-right": f"W-w-{margin}:{margin}",
        "bottom-left": f"{margin}:H-h-{margin}",
        "bottom-right": f"W-w-{margin}:H-h-{margin}",
        "center": "(W-w)/2:(H-h)/2",
    }
    xy = pos_map.get(position, pos_map["bottom-right"])

    fc = f"{scale_expr};[0:v][_ovl]overlay={xy}"
    return [], [], [], fc


# Register multi-input skills in dispatch
_SKILL_DISPATCH["grid"] = _f_grid
_SKILL_DISPATCH["slideshow"] = _f_slideshow
_SKILL_DISPATCH["overlay_image"] = _f_overlay_image
