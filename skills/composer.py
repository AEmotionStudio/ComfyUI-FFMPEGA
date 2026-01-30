"""Skill composition engine for building FFMPEG pipelines."""

from dataclasses import dataclass, field
from typing import Optional, Any
from pathlib import Path

from .registry import SkillRegistry, Skill, get_registry
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
                raise ValueError(f"Unknown skill: {step.skill_name}")

            # Validate parameters
            is_valid, errors = skill.validate_params(step.params)
            if not is_valid:
                raise ValueError(f"Invalid params for {step.skill_name}: {errors}")

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
                output_options.append(template)
            elif any(af in template for af in ["atempo", "volume", "aecho", "afade"]):
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
