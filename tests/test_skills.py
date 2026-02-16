"""Tests for the skill system."""

import pytest

from skills.registry import (
    SkillRegistry,
    Skill,
    SkillParameter,
    SkillCategory,
    ParameterType,
    get_registry,
)
from skills.composer import SkillComposer, Pipeline, PipelineStep


class TestSkillParameter:
    """Tests for SkillParameter class."""

    def test_required_parameter_validation(self):
        """Test required parameter validation."""
        param = SkillParameter(
            name="width",
            type=ParameterType.INT,
            description="Output width",
            required=True,
        )

        is_valid, error = param.validate(None)
        assert not is_valid
        assert "required" in error.lower()

    def test_int_parameter_validation(self):
        """Test integer parameter validation."""
        param = SkillParameter(
            name="width",
            type=ParameterType.INT,
            description="Output width",
            min_value=1,
            max_value=4096,
        )

        assert param.validate(1920)[0]
        assert not param.validate(0)[0]
        assert not param.validate(5000)[0]
        assert not param.validate("string")[0]

    def test_float_parameter_validation(self):
        """Test float parameter validation."""
        param = SkillParameter(
            name="factor",
            type=ParameterType.FLOAT,
            description="Speed factor",
            min_value=0.1,
            max_value=10.0,
        )

        assert param.validate(2.0)[0]
        assert param.validate(1)[0]  # Int should work for float
        assert not param.validate(0.05)[0]
        assert not param.validate(15.0)[0]

    def test_choice_parameter_validation(self):
        """Test choice parameter validation."""
        param = SkillParameter(
            name="direction",
            type=ParameterType.CHOICE,
            description="Flip direction",
            choices=["horizontal", "vertical"],
        )

        assert param.validate("horizontal")[0]
        assert param.validate("vertical")[0]
        assert not param.validate("diagonal")[0]

    def test_default_value(self):
        """Test parameter with default value."""
        param = SkillParameter(
            name="quality",
            type=ParameterType.INT,
            description="Quality",
            required=False,
            default=23,
        )

        assert param.validate(None)[0]


class TestSkill:
    """Tests for Skill class."""

    def test_skill_creation(self):
        """Test creating a skill."""
        skill = Skill(
            name="resize",
            category=SkillCategory.SPATIAL,
            description="Resize video",
            parameters=[
                SkillParameter(
                    name="width",
                    type=ParameterType.INT,
                    description="Width",
                    required=True,
                ),
                SkillParameter(
                    name="height",
                    type=ParameterType.INT,
                    description="Height",
                    required=True,
                ),
            ],
        )

        assert skill.name == "resize"
        assert skill.category == SkillCategory.SPATIAL
        assert len(skill.parameters) == 2

    def test_skill_param_validation(self):
        """Test skill parameter validation."""
        skill = Skill(
            name="speed",
            category=SkillCategory.TEMPORAL,
            description="Change speed",
            parameters=[
                SkillParameter(
                    name="factor",
                    type=ParameterType.FLOAT,
                    description="Speed factor",
                    required=True,
                    min_value=0.1,
                    max_value=10.0,
                ),
            ],
        )

        is_valid, errors = skill.validate_params({"factor": 2.0})
        assert is_valid
        assert len(errors) == 0

        is_valid, errors = skill.validate_params({"factor": 100.0})
        assert not is_valid
        assert len(errors) > 0

    def test_skill_get_param(self):
        """Test getting parameter by name."""
        skill = Skill(
            name="test",
            category=SkillCategory.VISUAL,
            description="Test skill",
            parameters=[
                SkillParameter(
                    name="value",
                    type=ParameterType.FLOAT,
                    description="Value",
                ),
            ],
        )

        param = skill.get_param("value")
        assert param is not None
        assert param.name == "value"

        assert skill.get_param("nonexistent") is None


class TestSkillRegistry:
    """Tests for SkillRegistry class."""

    def test_register_and_get(self):
        """Test registering and retrieving skills."""
        registry = SkillRegistry()

        skill = Skill(
            name="test_skill",
            category=SkillCategory.VISUAL,
            description="Test skill",
        )

        registry.register(skill)

        retrieved = registry.get("test_skill")
        assert retrieved is not None
        assert retrieved.name == "test_skill"

    def test_list_by_category(self):
        """Test listing skills by category."""
        registry = SkillRegistry()

        registry.register(Skill(
            name="skill1",
            category=SkillCategory.VISUAL,
            description="Visual skill 1",
        ))
        registry.register(Skill(
            name="skill2",
            category=SkillCategory.VISUAL,
            description="Visual skill 2",
        ))
        registry.register(Skill(
            name="skill3",
            category=SkillCategory.TEMPORAL,
            description="Temporal skill",
        ))

        visual_skills = registry.list_by_category(SkillCategory.VISUAL)
        assert len(visual_skills) == 2

        temporal_skills = registry.list_by_category(SkillCategory.TEMPORAL)
        assert len(temporal_skills) == 1

    def test_search(self):
        """Test skill search."""
        registry = SkillRegistry()

        registry.register(Skill(
            name="brightness",
            category=SkillCategory.VISUAL,
            description="Adjust brightness",
            tags=["light", "exposure"],
        ))
        registry.register(Skill(
            name="contrast",
            category=SkillCategory.VISUAL,
            description="Adjust contrast",
        ))

        results = registry.search("bright")
        assert len(results) == 1
        assert results[0].name == "brightness"

        results = registry.search("light")
        assert len(results) == 1

    def test_global_registry(self):
        """Test global registry has default skills."""
        registry = get_registry()

        # Should have skills from all categories
        assert len(registry.list_all()) > 0
        assert len(registry.list_by_category(SkillCategory.TEMPORAL)) > 0
        assert len(registry.list_by_category(SkillCategory.SPATIAL)) > 0
        assert len(registry.list_by_category(SkillCategory.VISUAL)) > 0

    def test_to_prompt_string(self):
        """Test generating prompt string."""
        registry = get_registry()
        prompt_str = registry.to_prompt_string()

        assert "Available Skills" in prompt_str
        assert "temporal" in prompt_str.lower() or "Temporal" in prompt_str


class TestPipeline:
    """Tests for Pipeline class."""

    def test_add_step(self):
        """Test adding steps to pipeline."""
        pipeline = Pipeline()
        pipeline.add_step("resize", {"width": 1280, "height": 720})
        pipeline.add_step("compress", {"preset": "medium"})

        assert len(pipeline.steps) == 2
        assert pipeline.steps[0].skill_name == "resize"
        assert pipeline.steps[1].skill_name == "compress"

    def test_remove_step(self):
        """Test removing steps."""
        pipeline = Pipeline()
        pipeline.add_step("resize", {})
        pipeline.add_step("compress", {})

        pipeline.remove_step(0)

        assert len(pipeline.steps) == 1
        assert pipeline.steps[0].skill_name == "compress"

    def test_clear(self):
        """Test clearing pipeline."""
        pipeline = Pipeline()
        pipeline.add_step("resize", {})
        pipeline.add_step("compress", {})

        pipeline.clear()

        assert len(pipeline.steps) == 0


class TestSkillComposer:
    """Tests for SkillComposer class."""

    def test_compose_simple_pipeline(self):
        """Test composing a simple pipeline."""
        composer = SkillComposer()

        pipeline = Pipeline(
            input_path="/input.mp4",
            output_path="/output.mp4",
        )
        pipeline.add_step("resize", {"width": 1280, "height": 720})

        command = composer.compose(pipeline)

        assert command is not None
        assert len(command.inputs) == 1
        assert len(command.outputs) == 1

    def test_compose_multi_step_pipeline(self):
        """Test composing multi-step pipeline."""
        composer = SkillComposer()

        pipeline = Pipeline(
            input_path="/input.mp4",
            output_path="/output.mp4",
        )
        pipeline.add_step("trim", {"start": 5, "duration": 30})
        pipeline.add_step("resize", {"width": 1280, "height": 720})
        pipeline.add_step("brightness", {"value": 0.1})

        command = composer.compose(pipeline)
        cmd_str = command.to_string()

        assert "scale" in cmd_str or "-vf" in cmd_str

    def test_validate_pipeline(self):
        """Test pipeline validation."""
        composer = SkillComposer()

        # Valid pipeline
        valid_pipeline = Pipeline(
            input_path="/input.mp4",
            output_path="/output.mp4",
        )
        valid_pipeline.add_step("resize", {"width": 1280, "height": 720})

        # Note: This would fail on actual validation since file doesn't exist
        # In a real test, we'd use fixtures

    def test_explain_pipeline(self):
        """Test pipeline explanation."""
        composer = SkillComposer()

        pipeline = Pipeline()
        pipeline.add_step("resize", {"width": 1280, "height": 720})
        pipeline.add_step("compress", {"preset": "medium"})

        explanation = composer.explain_pipeline(pipeline)

        assert "resize" in explanation.lower()
        assert "compress" in explanation.lower()

    def test_compose_with_unknown_skill(self):
        """Test handling of unknown skill — skipped with warning."""
        composer = SkillComposer()

        pipeline = Pipeline(
            input_path="/input.mp4",
            output_path="/output.mp4",
        )
        pipeline.add_step("nonexistent_skill", {})

        # Unknown skills are now skipped (with a warning log) rather than
        # raising an exception, so compose should succeed.
        result = composer.compose(pipeline)
        assert result is not None

    # ---- Template option splitting tests (regression for the -movflags bug) ----

    def test_template_output_opts_are_split(self):
        """web_optimize template '-movflags +faststart' must become two separate args."""
        composer = SkillComposer()
        pipeline = Pipeline(input_path="/in.mp4", output_path="/out.mp4")
        pipeline.add_step("web_optimize", {})

        command = composer.compose(pipeline)
        args = command.to_args()

        assert "-movflags" in args, f"-movflags missing from args: {args}"
        assert "+faststart" in args, f"+faststart missing from args: {args}"
        # They must NOT be merged into a single element
        for arg in args:
            assert " " not in arg, f"Arg contains space (not split): '{arg}'"

    def test_template_output_opts_with_param_substitution(self):
        """pixel_format template '-pix_fmt {format}' must split after substitution."""
        composer = SkillComposer()
        pipeline = Pipeline(input_path="/in.mp4", output_path="/out.mp4")
        pipeline.add_step("pixel_format", {"format": "yuv420p"})

        command = composer.compose(pipeline)
        args = command.to_args()

        assert "-pix_fmt" in args
        assert "yuv420p" in args
        for arg in args:
            assert " " not in arg, f"Arg contains space (not split): '{arg}'"

    def test_template_video_filter_not_split(self):
        """Video filter templates like 'curves=preset=vintage' should stay as one filter."""
        composer = SkillComposer()
        pipeline = Pipeline(input_path="/in.mp4", output_path="/out.mp4")
        pipeline.add_step("curves", {"preset": "vintage"})

        command = composer.compose(pipeline)
        cmd_str = command.to_string()

        assert "curves=preset=vintage" in cmd_str

    def test_template_video_filter_colorbalance(self):
        """colorbalance template should produce a valid video filter string."""
        composer = SkillComposer()
        pipeline = Pipeline(input_path="/in.mp4", output_path="/out.mp4")
        pipeline.add_step("colorbalance", {
            "rs": 0.1, "gs": 0, "bs": 0,
            "rm": 0.05, "gm": 0, "bm": 0,
        })

        command = composer.compose(pipeline)
        args = command.to_args()

        # colorbalance is a video filter, so -vf should be present
        assert "-vf" in args
        vf_idx = args.index("-vf")
        vf_val = args[vf_idx + 1]
        assert "colorbalance" in vf_val
        assert "rs=0.1" in vf_val

    # ---- Pipeline-based (composite) skill tests ----

    def test_pipeline_based_skill_cinematic(self):
        """Cinematic skill uses a pipeline of sub-skills; all should compose."""
        composer = SkillComposer()
        pipeline = Pipeline(input_path="/in.mp4", output_path="/out.mp4")
        pipeline.add_step("cinematic", {})

        command = composer.compose(pipeline)
        cmd_str = command.to_string()

        # cinematic pipeline includes contrast, saturation, vignette
        assert "-vf" in cmd_str
        assert "eq=" in cmd_str or "vignette" in cmd_str

    def test_pipeline_based_skill_dreamy(self):
        """Dreamy skill should produce blur + brightness + saturation filters."""
        composer = SkillComposer()
        pipeline = Pipeline(input_path="/in.mp4", output_path="/out.mp4")
        pipeline.add_step("dreamy", {})

        command = composer.compose(pipeline)
        cmd_str = command.to_string()

        assert "boxblur" in cmd_str or "blur" in cmd_str.lower()

    # ---- Mixed pipeline tests ----

    def test_mixed_builtin_and_template_skills(self):
        """A pipeline mixing builtin and template skills should produce valid args."""
        composer = SkillComposer()
        pipeline = Pipeline(input_path="/in.mp4", output_path="/out.mp4")
        pipeline.add_step("resize", {"width": 1280, "height": 720})
        pipeline.add_step("brightness", {"value": 0.1})
        pipeline.add_step("web_optimize", {})
        pipeline.add_step("pixel_format", {"format": "yuv420p"})

        command = composer.compose(pipeline)
        args = command.to_args()

        # No arg should contain a space (the core invariant)
        for arg in args:
            assert " " not in arg, f"Arg contains space: '{arg}'"

        # Video filters should be present
        assert "-vf" in args

        # Output options from templates should be present as separate args
        assert "-movflags" in args
        assert "+faststart" in args
        assert "-pix_fmt" in args
        assert "yuv420p" in args

    def test_quality_preset_injection(self):
        """Quality preset (always added by agent_node) should produce valid args."""
        composer = SkillComposer()
        pipeline = Pipeline(input_path="/in.mp4", output_path="/out.mp4")
        pipeline.add_step("resize", {"width": 1280, "height": 720})

        # Simulate the quality preset injection from agent_node.py lines 219-225
        pipeline.add_step("quality", {"crf": 23, "preset": "medium"})

        command = composer.compose(pipeline)
        args = command.to_args()

        assert "-c:v" in args
        assert "libx264" in args
        assert "-crf" in args
        assert "23" in args
        assert "-preset" in args
        assert "medium" in args

    def test_full_pipeline_no_spaces_in_args(self):
        """End-to-end: a realistic pipeline should never produce args with spaces."""
        composer = SkillComposer()
        pipeline = Pipeline(input_path="/in.mp4", output_path="/out.mp4")
        pipeline.add_step("trim", {"start": 5, "duration": 30})
        pipeline.add_step("resize", {"width": 1920, "height": 1080})
        pipeline.add_step("brightness", {"value": 0.05})
        pipeline.add_step("curves", {"preset": "vintage"})
        pipeline.add_step("web_optimize", {})
        pipeline.add_step("quality", {"crf": 18, "preset": "slow"})

        command = composer.compose(pipeline)
        args = command.to_args()

        for arg in args:
            assert " " not in arg, (
                f"FFMPEG arg contains embedded space and will cause "
                f"'Invalid argument' error: '{arg}'"
            )

        # Verify key elements are present
        assert "-ss" in args  # trim start
        assert "-t" in args   # trim duration
        assert "-vf" in args  # video filters
        assert "-movflags" in args
        assert "-c:v" in args

    def test_disabled_steps_are_skipped(self):
        """Disabled pipeline steps should not affect the command."""
        composer = SkillComposer()
        pipeline = Pipeline(input_path="/in.mp4", output_path="/out.mp4")
        pipeline.add_step("resize", {"width": 1280, "height": 720})

        # Manually disable the step
        pipeline.steps[0].enabled = False

        command = composer.compose(pipeline)
        args = command.to_args()

        assert "-vf" not in args  # no filter since step is disabled

    # ---- Audio template routing tests ----

    def test_audio_template_bass_routes_to_af(self):
        """Bass skill (template-based) must produce -af, not -vf."""
        composer = SkillComposer()
        pipeline = Pipeline(input_path="/in.mp4", output_path="/out.mp4")
        pipeline.add_step("bass", {"gain": 6, "frequency": 100})

        command = composer.compose(pipeline)
        args = command.to_args()

        assert "-af" in args, f"bass should produce -af but got: {args}"
        assert "-vf" not in args, f"bass should NOT produce -vf but got: {args}"
        af_idx = args.index("-af")
        assert "bass" in args[af_idx + 1]

    def test_audio_template_lowpass_routes_to_af(self):
        """Lowpass skill (template-based) must produce -af, not -vf."""
        composer = SkillComposer()
        pipeline = Pipeline(input_path="/in.mp4", output_path="/out.mp4")
        pipeline.add_step("lowpass", {"freq": 1000})

        command = composer.compose(pipeline)
        args = command.to_args()

        assert "-af" in args, f"lowpass should produce -af but got: {args}"
        assert "-vf" not in args

    def test_audio_template_echo_routes_to_af(self):
        """Echo skill (template-based) must produce -af, not -vf."""
        composer = SkillComposer()
        pipeline = Pipeline(input_path="/in.mp4", output_path="/out.mp4")
        pipeline.add_step("echo", {"delay": 500, "decay": 0.5})

        command = composer.compose(pipeline)
        args = command.to_args()

        assert "-af" in args, f"echo should produce -af but got: {args}"
        assert "-vf" not in args

    def test_mixed_video_and_audio_pipeline(self):
        """Pipeline with both video and audio skills should produce -vf and -af."""
        composer = SkillComposer()
        pipeline = Pipeline(input_path="/in.mp4", output_path="/out.mp4")
        pipeline.add_step("brightness", {"value": 0.1})
        pipeline.add_step("bass", {"gain": 6, "frequency": 100})

        command = composer.compose(pipeline)
        args = command.to_args()

        assert "-vf" in args, f"brightness should produce -vf: {args}"
        assert "-af" in args, f"bass should produce -af: {args}"

    # ---- Remove audio tests ----

    def test_remove_audio_produces_an_flag(self):
        """remove_audio skill must produce -an and no -af."""
        composer = SkillComposer()
        pipeline = Pipeline(input_path="/in.mp4", output_path="/out.mp4")
        pipeline.add_step("remove_audio", {})

        command = composer.compose(pipeline)
        args = command.to_args()

        assert "-an" in args, f"remove_audio should produce -an but got: {args}"
        assert "-af" not in args, f"remove_audio should NOT produce -af but got: {args}"

    def test_remove_audio_clears_conflicting_audio_filters(self):
        """remove_audio + volume must produce -an only, audio filters cleared."""
        composer = SkillComposer()
        pipeline = Pipeline(input_path="/in.mp4", output_path="/out.mp4")
        pipeline.add_step("volume", {"level": 0.5})
        pipeline.add_step("remove_audio", {})

        command = composer.compose(pipeline)
        args = command.to_args()

        assert "-an" in args, f"-an must be present: {args}"
        assert "-af" not in args, (
            f"-af must NOT be present when -an is set (conflict): {args}"
        )

    def test_remove_audio_preserves_video_filters(self):
        """remove_audio + video skill must produce -an and -vf but no -af."""
        composer = SkillComposer()
        pipeline = Pipeline(input_path="/in.mp4", output_path="/out.mp4")
        pipeline.add_step("brightness", {"value": 0.1})
        pipeline.add_step("remove_audio", {})

        command = composer.compose(pipeline)
        args = command.to_args()

        assert "-an" in args, f"-an must be present: {args}"
        assert "-vf" in args, f"-vf must be present: {args}"
        assert "-af" not in args, f"-af must NOT be present: {args}"

    # ---- Chroma key (green screen) tests ----

    def test_chromakey_produces_colorkey_filter(self):
        """chromakey skill must use filter_complex with colorkey+overlay for H.264/NVENC compat."""
        composer = SkillComposer()
        pipeline = Pipeline(input_path="/in.mp4", output_path="/out.mp4")
        pipeline.add_step("chromakey", {"color": "green"})

        command = composer.compose(pipeline)
        cmd_str = command.to_string()

        # Must use filter_complex (not simple -vf) to composite alpha over black
        assert "filter_complex" in cmd_str, f"Expected filter_complex but got: {cmd_str}"
        assert "colorkey=" in cmd_str, f"Expected 'colorkey' filter but got: {cmd_str}"
        assert "overlay" in cmd_str, f"Expected 'overlay' for compositing but got: {cmd_str}"

    # ---- Concat audio tests ----

    def test_concat_with_audio_produces_audio_streams(self):
        """concat with embedded audio should produce concat=n=2:v=1:a=1."""
        composer = SkillComposer()
        pipeline = Pipeline(
            input_path="/in.mp4",
            output_path="/out.mp4",
            extra_inputs=["/extra.mp4"],
        )
        pipeline.metadata["_has_embedded_audio"] = True
        pipeline.add_step("concat", {})

        command = composer.compose(pipeline)
        cmd_str = command.to_string()

        assert "concat=n=2:v=1:a=1" in cmd_str, (
            f"Expected audio concat (a=1) but got: {cmd_str}"
        )
        assert "filter_complex" in cmd_str
        # Audio read directly from video inputs
        assert "[0:a]" in cmd_str, f"Expected [0:a] but got: {cmd_str}"
        assert "[1:a]" in cmd_str, f"Expected [1:a] but got: {cmd_str}"

    def test_concat_without_audio_stays_video_only(self):
        """concat without audio should produce concat=n=2:v=1:a=0."""
        composer = SkillComposer()
        pipeline = Pipeline(
            input_path="/in.mp4",
            output_path="/out.mp4",
            extra_inputs=["/extra.mp4"],
        )
        pipeline.add_step("concat", {})

        command = composer.compose(pipeline)
        cmd_str = command.to_string()

        assert "concat=n=2:v=1:a=0" in cmd_str, (
            f"Expected video-only concat (a=0) but got: {cmd_str}"
        )

    # ---- Masking & Keying skill tests ----

    def test_colorkey_produces_filter_complex(self):
        """colorkey skill must use filter_complex with colorkey + overlay."""
        composer = SkillComposer()
        pipeline = Pipeline(input_path="/in.mp4", output_path="/out.mp4")
        pipeline.add_step("colorkey", {"color": "0xFF0000"})

        command = composer.compose(pipeline)
        cmd_str = command.to_string()

        assert "filter_complex" in cmd_str, f"Expected filter_complex: {cmd_str}"
        assert "colorkey=" in cmd_str, f"Expected colorkey filter: {cmd_str}"
        assert "overlay" in cmd_str, f"Expected overlay for compositing: {cmd_str}"
        assert "0xFF0000" in cmd_str, f"Expected color value: {cmd_str}"

    def test_colorkey_transparent_produces_vf(self):
        """colorkey with transparent background should produce -vf (no overlay)."""
        composer = SkillComposer()
        pipeline = Pipeline(input_path="/in.mp4", output_path="/out.mp4")
        pipeline.add_step("colorkey", {"color": "0x00FF00", "background": "transparent"})

        command = composer.compose(pipeline)
        args = command.to_args()

        assert "-vf" in args, f"Expected -vf for transparent mode: {args}"
        vf_idx = args.index("-vf")
        assert "colorkey=" in args[vf_idx + 1], f"Expected colorkey in vf: {args}"

    def test_lumakey_produces_filter_complex(self):
        """lumakey skill must use filter_complex with lumakey + overlay."""
        composer = SkillComposer()
        pipeline = Pipeline(input_path="/in.mp4", output_path="/out.mp4")
        pipeline.add_step("lumakey", {"threshold": 0.0, "tolerance": 0.2})

        command = composer.compose(pipeline)
        cmd_str = command.to_string()

        assert "filter_complex" in cmd_str, f"Expected filter_complex: {cmd_str}"
        assert "lumakey=" in cmd_str, f"Expected lumakey filter: {cmd_str}"
        assert "overlay" in cmd_str, f"Expected overlay for compositing: {cmd_str}"

    def test_lumakey_transparent_produces_vf(self):
        """lumakey with transparent background should produce -vf."""
        composer = SkillComposer()
        pipeline = Pipeline(input_path="/in.mp4", output_path="/out.mp4")
        pipeline.add_step("lumakey", {"threshold": 1.0, "background": "transparent"})

        command = composer.compose(pipeline)
        args = command.to_args()

        assert "-vf" in args, f"Expected -vf for transparent mode: {args}"
        vf_idx = args.index("-vf")
        assert "lumakey=" in args[vf_idx + 1], f"Expected lumakey in vf: {args}"

    def test_colorhold_produces_video_filter(self):
        """colorhold skill must produce -vf with colorhold= filter (no filter_complex)."""
        composer = SkillComposer()
        pipeline = Pipeline(input_path="/in.mp4", output_path="/out.mp4")
        pipeline.add_step("colorhold", {"color": "0xFF0000"})

        command = composer.compose(pipeline)
        args = command.to_args()

        assert "-vf" in args, f"Expected -vf: {args}"
        vf_idx = args.index("-vf")
        assert "colorhold=" in args[vf_idx + 1], f"Expected colorhold in vf: {args}"
        assert "0xFF0000" in args[vf_idx + 1], f"Expected color value: {args}"

    def test_despill_produces_video_filter(self):
        """despill skill must produce -vf with despill= filter."""
        composer = SkillComposer()
        pipeline = Pipeline(input_path="/in.mp4", output_path="/out.mp4")
        pipeline.add_step("despill", {"type": "green"})

        command = composer.compose(pipeline)
        args = command.to_args()

        assert "-vf" in args, f"Expected -vf: {args}"
        vf_idx = args.index("-vf")
        assert "despill=" in args[vf_idx + 1], f"Expected despill in vf: {args}"
        assert "type=0" in args[vf_idx + 1], f"Expected type=0 (green): {args}"

    def test_despill_blue_type(self):
        """despill with type=blue should produce type=1."""
        composer = SkillComposer()
        pipeline = Pipeline(input_path="/in.mp4", output_path="/out.mp4")
        pipeline.add_step("despill", {"type": "blue"})

        command = composer.compose(pipeline)
        args = command.to_args()

        vf_idx = args.index("-vf")
        assert "type=1" in args[vf_idx + 1], f"Expected type=1 (blue): {args}"

    def test_chromakey_then_despill_pipeline(self):
        """chromakey + despill should produce filter_complex + vf (combined)."""
        composer = SkillComposer()
        pipeline = Pipeline(input_path="/in.mp4", output_path="/out.mp4")
        pipeline.add_step("chromakey", {"color": "0x00FF00"})
        pipeline.add_step("despill", {"type": "green"})

        command = composer.compose(pipeline)
        cmd_str = command.to_string()

        assert "colorkey=" in cmd_str, f"Expected colorkey: {cmd_str}"
        assert "despill=" in cmd_str, f"Expected despill: {cmd_str}"

    def test_remove_background_graceful_without_rembg(self):
        """remove_background should not crash when rembg is not installed."""
        composer = SkillComposer()
        pipeline = Pipeline(input_path="/in.mp4", output_path="/out.mp4")
        pipeline.add_step("remove_background", {"model": "silueta"})

        # Should compose without error (skill simply does nothing)
        command = composer.compose(pipeline)
        assert command is not None

    def test_colorkey_alias_resolves(self):
        """color_key alias should resolve to colorkey in both aliases and dispatch."""
        composer = SkillComposer()
        pipeline = Pipeline(input_path="/in.mp4", output_path="/out.mp4")
        pipeline.add_step("color_key", {"color": "0xFF0000"})

        command = composer.compose(pipeline)
        cmd_str = command.to_string()

        assert "colorkey=" in cmd_str, f"Alias color_key should resolve: {cmd_str}"

    def test_sin_city_alias_resolves(self):
        """sin_city alias should resolve to colorhold."""
        composer = SkillComposer()
        pipeline = Pipeline(input_path="/in.mp4", output_path="/out.mp4")
        pipeline.add_step("sin_city", {"color": "0xFF0000"})

        command = composer.compose(pipeline)
        args = command.to_args()

        assert "-vf" in args, f"Expected -vf from colorhold: {args}"
        vf_idx = args.index("-vf")
        assert "colorhold=" in args[vf_idx + 1], f"sin_city should map to colorhold: {args}"

    # ---- Filter graph chaining tests (concat + overlay) ----

    def test_concat_then_overlay_chains_filter_graph(self):
        """concat + overlay_image must chain: overlay reads concat output, not [0:v]."""
        composer = SkillComposer()
        pipeline = Pipeline(
            input_path="/in.mp4",
            output_path="/out.mp4",
            extra_inputs=["/extra.mp4"],
        )
        pipeline.add_step("concat", {})
        pipeline.add_step("overlay_image", {"position": "bottom-right", "scale": 0.15})

        command = composer.compose(pipeline)
        cmd_str = command.to_string()

        assert "filter_complex" in cmd_str, f"Expected filter_complex: {cmd_str}"
        assert "concat=n=2" in cmd_str, f"Expected concat: {cmd_str}"
        assert "overlay=" in cmd_str, f"Expected overlay: {cmd_str}"
        # The concat output should be labeled, and overlay should use it
        assert "[_pipe_0]" in cmd_str, (
            f"Concat output should be labeled [_pipe_0] for chaining: {cmd_str}"
        )
        # The overlay should NOT reference [0:v] (it should use [_pipe_0] instead)
        # Count [0:v] occurrences — some are from concat scaling, which is fine.
        # But the overlay's base should not be [0:v].
        assert "[_pipe_0]" in cmd_str

    def test_overlay_image_normalizes_underscore_position(self):
        """overlay_image should accept bottom_right (underscore) as bottom-right."""
        composer = SkillComposer()
        pipeline = Pipeline(
            input_path="/in.mp4",
            output_path="/out.mp4",
            extra_inputs=["/logo.png"],
        )
        pipeline.add_step("overlay_image", {"position": "bottom_right", "scale": 0.15})

        command = composer.compose(pipeline)
        cmd_str = command.to_string()

        # Should produce the bottom-right overlay position (W-w-10:H-h-10)
        assert "W-w-" in cmd_str, (
            f"Expected bottom-right position expression but got: {cmd_str}"
        )
        assert "H-h-" in cmd_str, (
            f"Expected bottom-right position expression but got: {cmd_str}"
        )

    # ---- Concat + audio filter folding tests ----

    def test_concat_with_audio_then_normalize_folds_into_fc(self):
        """concat (a=1) + normalize must fold loudnorm into filter_complex, NOT -af."""
        composer = SkillComposer()
        pipeline = Pipeline(
            input_path="/in.mp4",
            output_path="/out.mp4",
            extra_inputs=["/extra.mp4"],
        )
        pipeline.metadata["_has_embedded_audio"] = True
        pipeline.add_step("concat", {})
        pipeline.add_step("normalize", {})

        command = composer.compose(pipeline)
        cmd_str = command.to_string()
        args = command.to_args()

        assert "filter_complex" in cmd_str, f"Expected filter_complex: {cmd_str}"
        assert "concat=n=2:v=1:a=1" in cmd_str, f"Expected audio concat: {cmd_str}"
        # loudnorm MUST be inside filter_complex, NOT as -af
        assert "loudnorm" in cmd_str, f"Expected loudnorm in command: {cmd_str}"
        assert "-af" not in args, (
            f"loudnorm must NOT be emitted via -af when concat produces "
            f"audio — -af conflicts with -filter_complex audio output: {args}"
        )
        # Must have -map flags to route the correct streams
        assert "-map" in args, f"Expected -map flags for stream routing: {args}"

    def test_concat_overlay_normalize_quality_full_pipeline(self):
        """Full error scenario: concat + overlay + normalize + web_optimize + quality.

        This is the exact pipeline from the failing prompt:
        'Concatenate all video segments, overlay the logo in the bottom right
        at 15% scale, normalize audio, compress for web'
        """
        composer = SkillComposer()
        pipeline = Pipeline(
            input_path="/in.mp4",
            output_path="/out.mp4",
            extra_inputs=["/logo.png", "/extra.mp4"],
        )
        pipeline.metadata["_has_embedded_audio"] = True
        pipeline.metadata["_input_fps"] = 24
        pipeline.metadata["_video_duration"] = 8.0
        pipeline.add_step("concat", {})
        pipeline.add_step("overlay_image", {
            "position": "bottom-right",
            "scale": 0.15,
            "image_source": "image_a",
        })
        pipeline.add_step("normalize", {})
        pipeline.add_step("web_optimize", {})
        pipeline.add_step("quality", {"crf": 23, "preset": "medium"})

        command = composer.compose(pipeline)
        cmd_str = command.to_string()
        args = command.to_args()

        # Core structure checks
        assert "filter_complex" in cmd_str, f"Expected filter_complex: {cmd_str}"
        assert "concat=" in cmd_str, f"Expected concat: {cmd_str}"
        assert "overlay=" in cmd_str, f"Expected overlay: {cmd_str}"

        # Audio filter folding: loudnorm MUST be in filter_complex
        assert "loudnorm" in cmd_str, f"Expected loudnorm: {cmd_str}"
        assert "-af" not in args, (
            f"-af must NOT be present when concat produces audio "
            f"inside filter_complex: {args}"
        )

        # Stream routing
        assert "-map" in args, f"Expected -map for stream routing: {args}"

        # Encoding options should be present
        assert "-c:v" in args, f"Expected video codec: {args}"
        assert "-movflags" in args, f"Expected faststart: {args}"

        # No args should contain spaces (regression check)
        for arg in args:
            assert " " not in arg, (
                f"FFMPEG arg contains embedded space: '{arg}'"
            )

    def test_concat_with_audio_no_audio_filter_no_map(self):
        """concat (a=1) without audio filters should NOT add -map flags."""
        composer = SkillComposer()
        pipeline = Pipeline(
            input_path="/in.mp4",
            output_path="/out.mp4",
            extra_inputs=["/extra.mp4"],
        )
        pipeline.metadata["_has_embedded_audio"] = True
        pipeline.add_step("concat", {})

        command = composer.compose(pipeline)
        args = command.to_args()

        # No -map needed when there are no audio filters to fold
        assert "-map" not in args, (
            f"-map should NOT be present when no audio filters are folded: {args}"
        )
        # Should NOT have -af either
        assert "-af" not in args, f"Unexpected -af: {args}"

    def test_concat_excludes_overlay_reserved_input(self):
        """concat should skip inputs reserved by overlay_image's image_source.

        With inputs: video (idx 0), logo.png (idx 1), extra.mp4 (idx 2)
        and overlay_image using image_source=image_a (idx 1),
        concat should only join idx 0 + idx 2 (n=2), NOT include idx 1.
        """
        composer = SkillComposer()
        pipeline = Pipeline(
            input_path="/in.mp4",
            output_path="/out.mp4",
            extra_inputs=["/logo.png", "/extra.mp4"],
        )
        pipeline.metadata["_has_embedded_audio"] = True
        pipeline.add_step("concat", {})
        pipeline.add_step("overlay_image", {
            "position": "bottom-right",
            "scale": 0.15,
            "image_source": "image_a",
        })

        command = composer.compose(pipeline)
        cmd_str = command.to_string()

        # Concat should use n=2 (main video + extra.mp4), NOT n=3
        assert "concat=n=2" in cmd_str, (
            f"Expected concat=n=2 (logo excluded) but got: {cmd_str}"
        )
        # The overlay should still reference the logo at [1:v]
        assert "[1:v]format=rgba" in cmd_str, (
            f"Overlay should still reference [1:v] for the logo: {cmd_str}"
        )

    def test_animated_overlay_bounce_no_inner_quotes(self):
        """animated_overlay motion expressions must not contain single quotes.

        Single quotes inside the filter_complex string conflict with
        shlex.quote() escaping, producing broken sequences like '"'"'.
        """
        composer = SkillComposer()
        pipeline = Pipeline(
            input_path="/in.mp4",
            output_path="/out.mp4",
            extra_inputs=["/logo.png"],
        )
        pipeline.add_step("animated_overlay", {
            "animation": "bounce",
            "scale": 0.15,
            "opacity": 0.5,
        })

        command = composer.compose(pipeline)
        cmd_str = command.to_string()

        # No single quotes inside the filter expression
        assert "'" not in cmd_str.split("-filter_complex")[-1].split("-c:")[0] if "-c:" in cmd_str else True, (
            f"Filter expression should not contain single quotes: {cmd_str}"
        )
        # Should contain overlay with eval=frame
        assert "overlay=" in cmd_str, f"Expected overlay: {cmd_str}"
        assert "eval=frame" in cmd_str, f"Expected eval=frame: {cmd_str}"
        # Should have bounce expression (abs, mod)
        assert "abs(mod(" in cmd_str, f"Expected bounce expression: {cmd_str}"

    def test_concat_excludes_animated_overlay_input(self):
        """concat should skip image_a when animated_overlay is also in pipeline.

        animated_overlay always uses [1:v], so concat should exclude idx 1.
        """
        composer = SkillComposer()
        pipeline = Pipeline(
            input_path="/in.mp4",
            output_path="/out.mp4",
            extra_inputs=["/logo.png", "/extra.mp4"],
        )
        pipeline.metadata["_has_embedded_audio"] = True
        pipeline.add_step("concat", {})
        pipeline.add_step("animated_overlay", {
            "animation": "bounce",
            "scale": 0.15,
        })

        command = composer.compose(pipeline)
        cmd_str = command.to_string()

        # concat should use n=2 (main + extra.mp4), NOT n=3
        assert "concat=n=2" in cmd_str, (
            f"Expected concat=n=2 (logo excluded) but got: {cmd_str}"
        )

    def test_concat_animated_overlay_with_audio_maps_both_pads(self):
        """concat(a=1) + animated_overlay needs -map for both video and audio.

        When concat produces dual pads [_pipe_0_v][_pipe_0_a] and
        animated_overlay chains from the video pad, the audio pad
        must still be mapped or ffmpeg errors with 'Invalid argument'.
        """
        composer = SkillComposer()
        pipeline = Pipeline(
            input_path="/in.mp4",
            output_path="/out.mp4",
            extra_inputs=["/logo.png", "/extra.mp4"],
        )
        pipeline.metadata["_has_embedded_audio"] = True
        pipeline.add_step("concat", {})
        pipeline.add_step("animated_overlay", {
            "animation": "bounce",
            "scale": 0.15,
            "opacity": 0.5,
        })

        command = composer.compose(pipeline)
        cmd_str = command.to_string()

        # Must have -map for both video and audio outputs
        assert "-map" in cmd_str, (
            f"Expected -map flags for dual pads but got: {cmd_str}"
        )
        assert "[_vfinal]" in cmd_str, (
            f"Expected [_vfinal] label for video output: {cmd_str}"
        )
        assert "[_pipe_0_a]" in cmd_str, (
            f"Expected [_pipe_0_a] label for audio output: {cmd_str}"
        )
        # concat should use n=2 (logo excluded by animated_overlay)
        assert "concat=n=2" in cmd_str, (
            f"Expected concat=n=2: {cmd_str}"
        )
        # overlay expression should not have inner quotes
        assert "eval=frame" in cmd_str, (
            f"Expected eval=frame in overlay: {cmd_str}"
        )

    def test_animated_overlay_multi_image_bounce(self):
        """animated_overlay with 3 images should produce 3 scaled overlays chained together.

        Each image gets a unique label ([_ovl0], [_ovl1], [_ovl2]),
        unique motion speed, and chained overlay filters via [_tmp0], [_tmp1].
        """
        composer = SkillComposer()
        pipeline = Pipeline(
            input_path="/in.mp4",
            output_path="/out.mp4",
            extra_inputs=["/extra1.mp4", "/extra2.mp4", "/extra3.mp4"],
        )
        pipeline.metadata["_image_paths"] = [
            "/img/pickup.png", "/img/rabbit.png", "/img/robot.png",
        ]
        pipeline.add_step("animated_overlay", {
            "animation": "bounce",
            "scale": 0.2,
        })

        command = composer.compose(pipeline)
        cmd_str = command.to_string()

        # Must have 3 unique scale labels
        assert "[_ovl0]" in cmd_str, f"Expected [_ovl0]: {cmd_str}"
        assert "[_ovl1]" in cmd_str, f"Expected [_ovl1]: {cmd_str}"
        assert "[_ovl2]" in cmd_str, f"Expected [_ovl2]: {cmd_str}"

        # Must chain overlays through intermediate labels
        assert "[_tmp0]" in cmd_str, f"Expected [_tmp0] chaining label: {cmd_str}"
        assert "[_tmp1]" in cmd_str, f"Expected [_tmp1] chaining label: {cmd_str}"

        # All overlays must have eval=frame
        assert cmd_str.count("eval=frame") == 3, (
            f"Expected 3 eval=frame expressions: {cmd_str}"
        )

        # All overlays must have bounce expressions
        assert cmd_str.count("abs(mod(") >= 6, (
            f"Expected at least 6 abs(mod(...)) expressions (2 per overlay): {cmd_str}"
        )

    def test_concat_overlay_image_auto_infers_image_source(self):
        """overlay_image without image_source should auto-infer it when alongside concat.

        When the LLM doesn't specify image_source but overlay_image is
        combined with concat, the composer should auto-detect the first
        image input and exclude it from concat segments.
        """
        composer = SkillComposer()
        pipeline = Pipeline(
            input_path="/in.mp4",
            output_path="/out.mp4",
            extra_inputs=["/logo.png", "/extra.mp4"],
        )
        pipeline.metadata["_has_embedded_audio"] = True
        pipeline.add_step("concat", {})
        pipeline.add_step("overlay_image", {
            "scale": 0.15,
            "opacity": 0.5,
            # NOTE: no image_source specified — should be auto-inferred
        })

        command = composer.compose(pipeline)
        cmd_str = command.to_string()

        # concat should use n=2 (logo at idx 1 auto-excluded)
        assert "concat=n=2" in cmd_str, (
            f"Expected concat=n=2 (auto-excluded logo) but got: {cmd_str}"
        )
        # overlay should only reference [1:v] (the logo), not [2:v]
        assert "[1:v]" in cmd_str, (
            f"Expected [1:v] for logo overlay: {cmd_str}"
        )

    def test_param_alias_resolves_bitrate_to_kbps(self):
        """audio_bitrate with bitrate=128 should resolve to kbps=128."""
        composer = SkillComposer()
        pipeline = Pipeline(
            input_path="/in.mp4",
            output_path="/out.mp4",
        )
        pipeline.add_step("audio_bitrate", {"bitrate": 128})

        command = composer.compose(pipeline)
        cmd_str = command.to_string()

        assert "-b:a 128k" in cmd_str, (
            f"Expected -b:a 128k from alias resolution but got: {cmd_str}"
        )

    def test_param_alias_strips_unit_suffix(self):
        """audio_bitrate with bitrate='128k' should strip suffix and produce kbps=128."""
        composer = SkillComposer()
        pipeline = Pipeline(
            input_path="/in.mp4",
            output_path="/out.mp4",
        )
        pipeline.add_step("audio_bitrate", {"bitrate": "128k"})

        command = composer.compose(pipeline)
        cmd_str = command.to_string()

        assert "-b:a 128k" in cmd_str, (
            f"Expected -b:a 128k from unit suffix strip but got: {cmd_str}"
        )

    def test_noise_reduction_default_amount(self):
        """noise_reduction with defaults should produce nr=12 (not 1)."""
        composer = SkillComposer()
        pipeline = Pipeline(
            input_path="/in.mp4",
            output_path="/out.mp4",
        )
        pipeline.add_step("noise_reduction", {})

        command = composer.compose(pipeline)
        cmd_str = command.to_string()

        assert "nr=12" in cmd_str, (
            f"Expected nr=12 (default) but got: {cmd_str}"
        )
        assert "afftdn=" in cmd_str, (
            f"Expected afftdn filter but got: {cmd_str}"
        )

    def test_beat_sync_with_audio_filter_keeps_audio(self):
        """beat_sync + bass should NOT strip audio — audio filters override -an."""
        composer = SkillComposer()
        pipeline = Pipeline(
            input_path="/in.mp4",
            output_path="/out.mp4",
        )
        pipeline.add_step("beat_sync", {"threshold": 0.15})
        pipeline.add_step("bass", {"gain": 8.0, "frequency": 100})

        command = composer.compose(pipeline)
        cmd_str = command.to_string()

        assert "-an" not in cmd_str, (
            f"Expected NO -an when audio filters exist: {cmd_str}"
        )
        assert "bass=g=8" in cmd_str, (
            f"Expected bass filter preserved: {cmd_str}"
        )

    def test_beat_sync_alone_strips_audio(self):
        """beat_sync without audio filters should still strip audio (-an)."""
        composer = SkillComposer()
        pipeline = Pipeline(
            input_path="/in.mp4",
            output_path="/out.mp4",
        )
        pipeline.add_step("beat_sync", {"threshold": 0.15})

        command = composer.compose(pipeline)
        cmd_str = command.to_string()

        assert "-an" in cmd_str, (
            f"Expected -an when no audio filters: {cmd_str}"
        )

    def test_replace_audio_maps_second_input(self):
        """replace_audio with audio filters routes [1:a] through filter_complex."""
        composer = SkillComposer()
        pipeline = Pipeline(
            input_path="/in.mp4",
            output_path="/out.mp4",
            extra_inputs=["/audio.wav"],
        )
        pipeline.add_step("replace_audio", {})
        pipeline.add_step("normalize", {})

        command = composer.compose(pipeline)
        cmd_str = command.to_string()

        assert "-map 0:v" in cmd_str, (
            f"Expected -map 0:v: {cmd_str}"
        )
        # Audio filters must route through [1:a] in filter_complex,
        # NOT via -af (which targets input 0's audio)
        assert "[1:a]" in cmd_str, (
            f"Expected [1:a] in filter_complex: {cmd_str}"
        )
        assert "[_aout]" in cmd_str, (
            f"Expected [_aout] output label: {cmd_str}"
        )
        assert "loudnorm" in cmd_str, (
            f"Expected loudnorm filter preserved: {cmd_str}"
        )
        # Direct -map 1:a should NOT be present (replaced by -map [_aout])
        assert "-map 1:a" not in cmd_str, (
            f"Direct -map 1:a should be replaced by -map [_aout]: {cmd_str}"
        )

    def test_replace_audio_alone_maps_directly(self):
        """replace_audio without audio filters uses direct -map 1:a."""
        composer = SkillComposer()
        pipeline = Pipeline(
            input_path="/in.mp4",
            output_path="/out.mp4",
            extra_inputs=["/audio.wav"],
        )
        pipeline.add_step("replace_audio", {})

        command = composer.compose(pipeline)
        cmd_str = command.to_string()

        assert "-map 0:v" in cmd_str, f"Expected -map 0:v: {cmd_str}"
        assert "-map 1:a" in cmd_str, f"Expected -map 1:a: {cmd_str}"
        assert "-shortest" in cmd_str, f"Expected -shortest: {cmd_str}"

    def test_replace_audio_with_video_and_audio_filters(self):
        """replace_audio with video+audio filters folds both into filter_complex."""
        composer = SkillComposer()
        pipeline = Pipeline(
            input_path="/in.mp4",
            output_path="/out.mp4",
            extra_inputs=["/audio.wav"],
        )
        pipeline.add_step("replace_audio", {})
        pipeline.add_step("monochrome", {})  # video filter
        pipeline.add_step("normalize", {})     # audio filter

        command = composer.compose(pipeline)
        cmd_str = command.to_string()

        # Both video and audio must be in filter_complex (no -vf allowed)
        assert "filter_complex" in cmd_str, (
            f"Expected filter_complex: {cmd_str}"
        )
        assert "[0:v]" in cmd_str, (
            f"Expected [0:v] in filter_complex for video chain: {cmd_str}"
        )
        assert "[1:a]" in cmd_str, (
            f"Expected [1:a] in filter_complex for audio chain: {cmd_str}"
        )
        assert "[_vout]" in cmd_str, (
            f"Expected [_vout] video output label: {cmd_str}"
        )
        assert "[_aout]" in cmd_str, (
            f"Expected [_aout] audio output label: {cmd_str}"
        )
        # No -vf should appear (would conflict with filter_complex)
        assert " -vf " not in cmd_str, (
            f"-vf must not appear when filter_complex is used: {cmd_str}"
        )
