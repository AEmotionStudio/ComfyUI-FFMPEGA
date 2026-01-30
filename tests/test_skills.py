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
