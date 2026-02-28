import pytest
from skills.composer import SkillComposer, Pipeline
from skills.registry import Skill, SkillCategory, ParameterType, SkillParameter

def test_template_resolves_defaults_when_param_missing():
    # Register a test skill that uses an ffmpeg_template
    composer = SkillComposer()
    test_skill = Skill(
        name="test_template_skill",
        description="A test skill",
        category=SkillCategory.VISUAL,
        parameters=[
            SkillParameter("ratio", ParameterType.FLOAT, "Ratio", default=1.5),
            SkillParameter("mode", ParameterType.STRING, "Mode", default="auto"),
        ],
        ffmpeg_template="testfilter=ratio={ratio}:mode={mode}"
    )
    composer.registry.register(test_skill)

    pipeline = Pipeline(
        input_path="/in.mp4",
        output_path="/out.mp4",
    )
    # Don't provide ratio or mode - they should fall back to defaults
    pipeline.add_step("test_template_skill", {})

    command = composer.compose(pipeline)
    cmd_str = command.to_string()

    # The issue was that un-provided parameters were left as {ratio} in the template.
    assert "testfilter=ratio=1.5:mode=auto" in cmd_str, f"Expected defaults to be resolved, got: {cmd_str}"


def test_pipeline_skill_resolves_defaults_when_param_missing():
    composer = SkillComposer()

    # We need a child skill that actually takes the parameter
    child_skill = Skill(
        name="child_skill",
        description="Child skill",
        category=SkillCategory.VISUAL,
        parameters=[
            SkillParameter("ratio", ParameterType.FLOAT, "Ratio", default=1.0),
        ],
        ffmpeg_template="childfilter=ratio={ratio}"
    )
    composer.registry.register(child_skill)

    # And a parent skill with a pipeline that uses {ratio}
    parent_skill = Skill(
        name="parent_pipeline_skill",
        description="Parent skill with pipeline",
        category=SkillCategory.VISUAL,
        parameters=[
            SkillParameter("ratio", ParameterType.FLOAT, "Ratio", default=2.5),
        ],
        pipeline=["child_skill:ratio={ratio}"]
    )
    composer.registry.register(parent_skill)

    pipeline = Pipeline(
        input_path="/in.mp4",
        output_path="/out.mp4",
    )
    # Don't provide ratio
    pipeline.add_step("parent_pipeline_skill", {})

    command = composer.compose(pipeline)
    cmd_str = command.to_string()

    # The issue was that un-provided parameters were left as {ratio} in the step string.
    assert "childfilter=ratio=2.5" in cmd_str, f"Expected parent defaults to be passed to child, got: {cmd_str}"
