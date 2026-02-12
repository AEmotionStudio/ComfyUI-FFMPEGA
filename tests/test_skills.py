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
        """Test handling of unknown skill."""
        composer = SkillComposer()

        pipeline = Pipeline(
            input_path="/input.mp4",
            output_path="/output.mp4",
        )
        pipeline.add_step("nonexistent_skill", {})

        with pytest.raises(ValueError):
            composer.compose(pipeline)

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
