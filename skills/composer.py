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

    def _builtin_skill_filters(
        self,
        skill_name: str,
        params: dict,
    ) -> tuple[list[str], list[str], list[str]]:
        """Generate filters for built-in skills.

        Args:
            skill_name: Name of the skill.
            params: Parameters.

        Returns:
            Tuple of (video_filters, audio_filters, output_options).
        """
        video_filters = []
        audio_filters = []
        output_options = []

        # Temporal skills
        if skill_name == "trim":
            if params.get("start"):
                output_options.extend(["-ss", str(params["start"])])
            if params.get("end"):
                output_options.extend(["-to", str(params["end"])])
            if params.get("duration"):
                output_options.extend(["-t", str(params["duration"])])

        elif skill_name == "speed":
            factor = params.get("factor", 1.0)
            pts_factor = 1.0 / factor
            video_filters.append(f"setpts={pts_factor}*PTS")

            # Audio tempo adjustment
            if 0.5 <= factor <= 2.0:
                audio_filters.append(f"atempo={factor}")
            elif factor < 0.5:
                remaining = factor
                while remaining < 0.5:
                    audio_filters.append("atempo=0.5")
                    remaining *= 2
                audio_filters.append(f"atempo={remaining}")
            else:
                remaining = factor
                while remaining > 2.0:
                    audio_filters.append("atempo=2.0")
                    remaining /= 2
                audio_filters.append(f"atempo={remaining}")

        elif skill_name == "reverse":
            video_filters.append("reverse")
            audio_filters.append("areverse")

        elif skill_name == "loop":
            count = params.get("count", 2)
            video_filters.append(f"loop=loop={count}:size=32767")

        # Spatial skills
        elif skill_name == "resize":
            width = params.get("width", -1)
            height = params.get("height", -1)
            video_filters.append(f"scale={width}:{height}")

        elif skill_name == "crop":
            w = params.get("width", "iw")
            h = params.get("height", "ih")
            x = params.get("x", "(in_w-out_w)/2")
            y = params.get("y", "(in_h-out_h)/2")
            video_filters.append(f"crop={w}:{h}:{x}:{y}")

        elif skill_name == "pad":
            w = params.get("width", "iw")
            h = params.get("height", "ih")
            x = params.get("x", "(ow-iw)/2")
            y = params.get("y", "(oh-ih)/2")
            color = params.get("color", "black")
            video_filters.append(f"pad={w}:{h}:{x}:{y}:{color}")

        elif skill_name == "rotate":
            angle = params.get("angle", 0)
            if angle == 90:
                video_filters.append("transpose=1")
            elif angle == -90 or angle == 270:
                video_filters.append("transpose=2")
            elif angle == 180:
                video_filters.append("transpose=1,transpose=1")
            else:
                radians = angle * 3.14159 / 180
                video_filters.append(f"rotate={radians}")

        elif skill_name == "flip":
            direction = params.get("direction", "horizontal")
            if direction == "horizontal":
                video_filters.append("hflip")
            else:
                video_filters.append("vflip")

        # Visual skills
        elif skill_name == "brightness":
            value = params.get("value", 0)
            video_filters.append(f"eq=brightness={value}")

        elif skill_name == "contrast":
            value = params.get("value", 1.0)
            video_filters.append(f"eq=contrast={value}")

        elif skill_name == "saturation":
            value = params.get("value", 1.0)
            video_filters.append(f"eq=saturation={value}")

        elif skill_name == "hue":
            value = params.get("value", 0)
            video_filters.append(f"hue=h={value}")

        elif skill_name == "sharpen":
            amount = params.get("amount", 1.0)
            video_filters.append(f"unsharp=5:5:{amount}:5:5:0")

        elif skill_name == "blur":
            radius = params.get("radius", 5)
            video_filters.append(f"boxblur={radius}:{radius}")

        elif skill_name == "denoise":
            strength = params.get("strength", "medium")
            if strength == "light":
                video_filters.append("hqdn3d=2:2:3:3")
            elif strength == "medium":
                video_filters.append("hqdn3d=4:3:6:4")
            else:  # strong
                video_filters.append("hqdn3d=6:4:9:6")

        elif skill_name == "vignette":
            intensity = params.get("intensity", 0.3)
            video_filters.append(f"vignette=PI/4*{intensity}")

        elif skill_name == "fade":
            fade_type = params.get("type", "in")
            start = params.get("start", 0)
            duration = params.get("duration", 1)
            if fade_type == "both":
                # Fade in at start, fade out at end
                video_filters.append(f"fade=t=in:st=0:d={duration}")
                video_filters.append(f"fade=t=out:d={duration}")
            else:
                video_filters.append(f"fade=t={fade_type}:st={start}:d={duration}")

        # Audio skills
        elif skill_name == "volume":
            level = params.get("level", 1.0)
            audio_filters.append(f"volume={level}")

        elif skill_name == "normalize":
            audio_filters.append("loudnorm")

        elif skill_name == "fade_audio":
            fade_type = params.get("type", "in")
            start = params.get("start", 0)
            duration = params.get("duration", 1)
            audio_filters.append(f"afade=t={fade_type}:st={start}:d={duration}")

        elif skill_name == "remove_audio":
            output_options.append("-an")

        elif skill_name == "extract_audio":
            output_options.extend(["-vn", "-c:a", "copy"])

        # Encoding skills
        elif skill_name == "compress":
            preset = params.get("preset", "medium")
            crf_map = {"light": 20, "medium": 23, "heavy": 28}
            crf = crf_map.get(preset, 23)
            output_options.extend(["-c:v", "libx264", "-crf", str(crf), "-preset", "medium"])

        elif skill_name == "convert":
            codec = params.get("codec", "h264")
            codec_map = {
                "h264": "libx264",
                "h265": "libx265",
                "vp9": "libvpx-vp9",
                "av1": "libaom-av1",
            }
            output_options.extend(["-c:v", codec_map.get(codec, "libx264")])

        elif skill_name == "bitrate":
            video_br = params.get("video")
            audio_br = params.get("audio")
            if video_br:
                output_options.extend(["-b:v", video_br])
            if audio_br:
                output_options.extend(["-b:a", audio_br])

        elif skill_name == "quality":
            crf = params.get("crf", 23)
            preset = params.get("preset", "medium")
            output_options.extend(["-c:v", "libx264", "-crf", str(crf), "-preset", preset])

        # Text overlay skill (needs special escaping)
        elif skill_name == "text_overlay":
            text = str(params.get("text", "")).replace("'", "\\'").replace(":", "\\:")
            size = params.get("size", 48)
            color = params.get("color", "white")
            font = params.get("font", "Sans")
            border = params.get("border", True)
            position = params.get("position", "center")

            # Map position to x:y coordinates
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

            border_style = ""
            if border:
                border_style = ":borderw=3:bordercolor=black"

            drawtext = (
                f"drawtext=text='{text}':fontsize={size}"
                f":fontcolor={color}:font='{font}'"
                f":{xy}{border_style}"
            )
            video_filters.append(drawtext)

        # Pixelate skill (scale down then scale back up with nearest neighbor)
        elif skill_name == "pixelate":
            factor = params.get("factor", 10)
            video_filters.append(
                f"scale=iw/{factor}:ih/{factor},"
                f"scale=iw*{factor}:ih*{factor}:flags=neighbor"
            )

        # Posterize skill (quantize colors using lutrgb)
        elif skill_name == "posterize":
            levels = int(params.get("levels", 4))
            step = max(1, 256 // levels)
            lut_expr = f"trunc(val/{step})*{step}"
            video_filters.append(
                f"lutrgb=r='{lut_expr}':g='{lut_expr}':b='{lut_expr}'"
            )

        # === Transition effects ===

        elif skill_name == "fade_to_black":
            in_dur = float(params.get("in_duration", 1.0))
            out_dur = float(params.get("out_duration", 1.0))
            if in_dur > 0:
                video_filters.append(f"fade=t=in:st=0:d={in_dur}")
            if out_dur > 0:
                # Use negative start time trick: fade=t=out with special handling
                # The composer will need video duration, so use a large end value
                # In practice, the user or LLM should provide the actual timing
                video_filters.append(f"fade=t=out:d={out_dur}")

        elif skill_name == "fade_to_white":
            in_dur = float(params.get("in_duration", 1.0))
            out_dur = float(params.get("out_duration", 1.0))
            if in_dur > 0:
                video_filters.append(f"fade=t=in:st=0:d={in_dur}:c=white")
            if out_dur > 0:
                video_filters.append(f"fade=t=out:d={out_dur}:c=white")

        elif skill_name == "flash":
            time = float(params.get("time", 0))
            duration = float(params.get("duration", 0.3))
            end_time = time + duration
            mid = time + duration / 2
            # Flash = quick fade-out then fade-in using curves
            video_filters.append(
                f"fade=t=out:st={time}:d={duration/2}:c=white,"
                f"fade=t=in:st={mid}:d={duration/2}:c=white"
            )

        # === Motion effects ===

        elif skill_name == "spin":
            speed = float(params.get("speed", 90.0))
            direction = params.get("direction", "cw")
            # Convert degrees/sec to radians/sec
            rad_per_sec = speed * 3.14159 / 180
            if direction == "ccw":
                rad_per_sec = -rad_per_sec
            video_filters.append(
                f"rotate={rad_per_sec}*t:fillcolor=black"
            )

        elif skill_name == "shake":
            intensity = params.get("intensity", "medium")
            # Amount of random pixel offset per frame
            shake_map = {"light": 5, "medium": 12, "heavy": 25}
            amount = shake_map.get(intensity, 12)
            # Use crop with random offsets to simulate shake
            video_filters.append(
                f"crop=iw-{amount*2}:ih-{amount*2}"
                f":{amount}+{amount}*random(1)"
                f":{amount}+{amount}*random(2),"
                f"scale=iw+{amount*2}:ih+{amount*2}"
            )

        elif skill_name == "pulse":
            rate = float(params.get("rate", 1.0))
            amount = float(params.get("amount", 0.05))
            # Use setpts+scale with expression-based zoom for pulsing effect
            # Scale up slightly then crop to original size with sine modulation
            margin = int(amount * 100) + 10  # extra pixels for zoom headroom
            video_filters.append(
                f"pad=iw+{margin*2}:ih+{margin*2}:{margin}:{margin}:color=black"
            )
            offset_expr = f"{margin}+{margin}*{amount}*10*sin(2*PI*{rate}*t)"
            video_filters.append(
                f"crop=iw-{margin*2}:ih-{margin*2}:'{offset_expr}':'{offset_expr}'"
            )

        elif skill_name == "bounce":
            height = int(params.get("height", 30))
            speed = float(params.get("speed", 2.0))
            # Use pad + crop with sine-based vertical offset
            video_filters.append(
                f"pad=iw:ih+{height*2}:(ow-iw)/2:{height}:black,"
                f"crop=iw:ih-{height*2}:0:{height}*abs(sin({speed}*PI*t))"
            )

        elif skill_name == "drift":
            direction = params.get("direction", "right")
            amount = int(params.get("amount", 50))
            # Pad the frame and slowly pan across using crop with time expression
            if direction == "right":
                video_filters.append(
                    f"pad=iw+{amount}:ih:0:0:black,"
                    f"crop=iw-{amount}:ih:{amount}*t/duration:0"
                )
            elif direction == "left":
                video_filters.append(
                    f"pad=iw+{amount}:ih:{amount}:0:black,"
                    f"crop=iw-{amount}:ih:{amount}*(1-t/duration):0"
                )
            elif direction == "down":
                video_filters.append(
                    f"pad=iw:ih+{amount}:0:0:black,"
                    f"crop=iw:ih-{amount}:0:{amount}*t/duration"
                )
            elif direction == "up":
                video_filters.append(
                    f"pad=iw:ih+{amount}:0:{amount}:black,"
                    f"crop=iw:ih-{amount}:0:{amount}*(1-t/duration)"
                )

        # === Reveal effects ===

        elif skill_name == "iris_reveal":
            duration = float(params.get("duration", 2.0))
            # Expanding circle mask using geq (pixel math)
            # radius grows from 0 to diagonal over duration
            video_filters.append(
                f"geq="
                f"lum='if(lte(sqrt(pow(X-W/2,2)+pow(Y-H/2,2)),sqrt(pow(W/2,2)+pow(H/2,2))*min(T/{duration},1)),lum(X,Y),0)'"
                f":cb='if(lte(sqrt(pow(X-W/2,2)+pow(Y-H/2,2)),sqrt(pow(W/2,2)+pow(H/2,2))*min(T/{duration},1)),cb(X,Y),128)'"
                f":cr='if(lte(sqrt(pow(X-W/2,2)+pow(Y-H/2,2)),sqrt(pow(W/2,2)+pow(H/2,2))*min(T/{duration},1)),cr(X,Y),128)'"
            )

        elif skill_name == "wipe":
            direction = params.get("direction", "left")
            duration = float(params.get("duration", 1.5))
            # Directional wipe using geq with animated threshold
            if direction == "left":
                cond = f"lte(X,W*min(T/{duration},1))"
            elif direction == "right":
                cond = f"gte(X,W*(1-min(T/{duration},1)))"
            elif direction == "down":
                cond = f"lte(Y,H*min(T/{duration},1))"
            else:  # up
                cond = f"gte(Y,H*(1-min(T/{duration},1)))"
            video_filters.append(
                f"geq="
                f"lum='if({cond},lum(X,Y),0)'"
                f":cb='if({cond},cb(X,Y),128)'"
                f":cr='if({cond},cr(X,Y),128)'"
            )

        elif skill_name == "slide_in":
            direction = params.get("direction", "left")
            duration = float(params.get("duration", 1.0))
            # Pad + animated crop to simulate sliding in
            if direction == "left":
                video_filters.append(
                    f"pad=iw*2:ih:iw:0:black,"
                    f"crop=iw/2:ih:iw/2*min(T/{duration},1):0"
                )
            elif direction == "right":
                video_filters.append(
                    f"pad=iw*2:ih:0:0:black,"
                    f"crop=iw/2:ih:iw/2*(1-min(T/{duration},1)):0"
                )
            elif direction == "down":
                video_filters.append(
                    f"pad=iw:ih*2:0:ih:black,"
                    f"crop=iw:ih/2:0:ih/2*min(T/{duration},1)"
                )
            else:  # up
                video_filters.append(
                    f"pad=iw:ih*2:0:0:black,"
                    f"crop=iw:ih/2:0:ih/2*(1-min(T/{duration},1))"
                )

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
