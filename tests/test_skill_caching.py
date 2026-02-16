
import pytest
from skills.registry import Skill, SkillParameter, SkillCategory, ParameterType

def test_skill_caching_initialization():
    """Test that Skill object initializes cached maps."""
    skill = Skill(
        name="test_skill",
        category=SkillCategory.TEMPORAL,
        description="A test skill",
        parameters=[
            SkillParameter(name="param1", type=ParameterType.INT, description="p1"),
            SkillParameter(name="param2", type=ParameterType.INT, description="p2", aliases=["p2_alias"]),
        ]
    )

    # Check if _param_map is populated
    assert hasattr(skill, "_param_map")
    assert "param1" in skill._param_map
    assert "param2" in skill._param_map
    assert skill._param_map["param1"].name == "param1"

    # Check if _alias_map is populated
    assert hasattr(skill, "_alias_map")
    assert "p2_alias" in skill._alias_map
    assert skill._alias_map["p2_alias"] == "param2"

def test_skill_caching_no_params():
    """Test caching with no parameters."""
    skill = Skill(
        name="test_skill_empty",
        category=SkillCategory.TEMPORAL,
        description="Empty skill"
    )

    assert hasattr(skill, "_param_map")
    assert len(skill._param_map) == 0
    assert hasattr(skill, "_alias_map")
    assert len(skill._alias_map) == 0
