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

        # Process each step
        video_filters = []
        audio_filters = []
        output_options = []

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

            # Get filters/options for this skill
            vf, af, opts = self._skill_to_filters(skill, step.params)
            video_filters.extend(vf)
            audio_filters.extend(af)
            output_options.extend(opts)

        # If the pipeline strips audio (-an), discard any audio filters to
        # avoid the -af/-an conflict that causes ffmpeg to include audio.
        if "-an" in output_options:
            audio_filters.clear()

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
    ) -> tuple[list[str], list[str], list[str]]:
        """Convert a skill invocation to FFMPEG filters.

        Args:
            skill: Skill to convert.
            params: Parameters for the skill.

        Returns:
            Tuple of (video_filters, audio_filters, output_options).
        """
        video_filters = []
        audio_filters = []
        output_options = []

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
                    vf, af, opts = self._skill_to_filters(sub_skill, sub_params)
                    video_filters.extend(vf)
                    audio_filters.extend(af)
                    output_options.extend(opts)

        # Handle specific skill types
        else:
            vf, af, opts = self._builtin_skill_filters(skill.name, params)
            video_filters.extend(vf)
            audio_filters.extend(af)
            output_options.extend(opts)

        return video_filters, audio_filters, output_options

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
    ) -> tuple[list[str], list[str], list[str]]:
        """Generate filters for built-in skills using dispatch table.

        Args:
            skill_name: Name of the skill.
            params: Parameters.

        Returns:
            Tuple of (video_filters, audio_filters, output_options).
        """
        handler = _SKILL_DISPATCH.get(skill_name)
        if handler is None:
            return [], [], []
        return handler(params)


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
    d = {
        "right": f"pad=iw+{amount}:ih:0:0:black,crop=iw-{amount}:ih:{amount}*t/duration:0",
        "left": f"pad=iw+{amount}:ih:{amount}:0:black,crop=iw-{amount}:ih:{amount}*(1-t/duration):0",
        "down": f"pad=iw:ih+{amount}:0:0:black,crop=iw:ih-{amount}:0:{amount}*t/duration",
        "up": f"pad=iw:ih+{amount}:0:{amount}:black,crop=iw:ih-{amount}:0:{amount}*(1-t/duration)",
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
        "left": f"pad=iw*2:ih:iw:0:black,crop=iw/2:ih:iw/2*min(T/{duration},1):0",
        "right": f"pad=iw*2:ih:0:0:black,crop=iw/2:ih:iw/2*(1-min(T/{duration},1)):0",
        "down": f"pad=iw:ih*2:0:ih:black,crop=iw:ih/2:0:ih/2*min(T/{duration},1)",
        "up": f"pad=iw:ih*2:0:0:black,crop=iw:ih/2:0:ih/2*(1-min(T/{duration},1))",
    }
    return [d.get(direction, d["left"])], [], []


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
}
