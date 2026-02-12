"""Tests for YAML custom skill loader."""

import pytest
import tempfile
import os
from pathlib import Path

from skills.yaml_loader import (
    load_skill_from_yaml,
    load_custom_skills,
    _parse_parameter,
)
from skills.registry import (
    SkillRegistry,
    SkillCategory,
    ParameterType,
)


# ── Sample YAML content for testing ──────────────────────────────────

# Note: the YAML loader expects `parameters` as a dict mapping name → config,
# and uses `ffmpeg_template` (not `ffmpeg_filter`).

VALID_SKILL_YAML = """
name: test_glow
description: Apply a warm glow effect
category: visual
ffmpeg_template: "unsharp=5:5:1.5:5:5:0.5,eq=brightness=0.05:saturation=1.3"
parameters:
  intensity:
    type: float
    default: 1.0
    min: 0.0
    max: 5.0
    description: Glow intensity
  color:
    type: choice
    default: warm
    choices: [warm, cool, neutral]
    description: Color tone
examples:
  - "Add a warm glow"
  - "Make it look dreamy"
tags:
  - glow
  - warm
  - dreamy
"""

MINIMAL_SKILL_YAML = """
name: test_flip
description: Flip horizontally
category: spatial
ffmpeg_template: "hflip"
"""

MISSING_NAME_YAML = """
description: Missing name field
category: visual
ffmpeg_template: "null"
"""

NO_FILTER_YAML = """
name: test_nofilter
description: Has no template
category: visual
"""

INVALID_YAML = """
name: [this is
  bad yaml: {{}}
"""


# ── load_skill_from_yaml tests ────────────────────────────────────────

class TestLoadSkillFromYaml:
    """Tests for loading individual YAML skill files."""

    def _write_yaml(self, content: str) -> Path:
        """Write YAML content to a temporary file and return its path."""
        fd, path = tempfile.mkstemp(suffix=".yaml")
        with os.fdopen(fd, "w") as f:
            f.write(content)
        return Path(path)

    def test_load_valid_skill(self):
        """Valid YAML should load into a Skill object."""
        path = self._write_yaml(VALID_SKILL_YAML)
        try:
            skill = load_skill_from_yaml(path)
            assert skill is not None
            assert skill.name == "test_glow"
            assert skill.description == "Apply a warm glow effect"
            assert skill.category == SkillCategory.VISUAL
        finally:
            path.unlink()

    def test_load_minimal_skill(self):
        """Minimal YAML (name, description, category, template) should work."""
        path = self._write_yaml(MINIMAL_SKILL_YAML)
        try:
            skill = load_skill_from_yaml(path)
            assert skill is not None
            assert skill.name == "test_flip"
            assert skill.category == SkillCategory.SPATIAL
        finally:
            path.unlink()

    def test_parameters_parsed(self):
        """Parameters should be parsed with correct types."""
        path = self._write_yaml(VALID_SKILL_YAML)
        try:
            skill = load_skill_from_yaml(path)
            assert skill is not None
            assert len(skill.parameters) == 2

            intensity = skill.get_param("intensity")
            assert intensity is not None
            assert intensity.default == 1.0

            color = skill.get_param("color")
            assert color is not None
            assert "warm" in color.choices
        finally:
            path.unlink()

    def test_examples_loaded(self):
        """Example prompts should be loaded."""
        path = self._write_yaml(VALID_SKILL_YAML)
        try:
            skill = load_skill_from_yaml(path)
            assert skill is not None
            assert len(skill.examples) == 2
            assert "warm glow" in skill.examples[0]
        finally:
            path.unlink()

    def test_tags_loaded(self):
        """Tags should be loaded."""
        path = self._write_yaml(VALID_SKILL_YAML)
        try:
            skill = load_skill_from_yaml(path)
            assert skill is not None
            assert "glow" in skill.tags
            assert "dreamy" in skill.tags
        finally:
            path.unlink()

    def test_missing_name_returns_none(self):
        """YAML without 'name' should return None."""
        path = self._write_yaml(MISSING_NAME_YAML)
        try:
            skill = load_skill_from_yaml(path)
            assert skill is None
        finally:
            path.unlink()

    def test_no_filter_still_loads(self):
        """YAML without ffmpeg_template is valid (could use pipeline instead)."""
        path = self._write_yaml(NO_FILTER_YAML)
        try:
            skill = load_skill_from_yaml(path)
            # Skills without a template OR pipeline are still valid Skill objects
            # The composer handles missing templates at runtime
            assert skill is not None
            assert skill.name == "test_nofilter"
        finally:
            path.unlink()

    def test_invalid_yaml_returns_none(self):
        """Malformed YAML should return None without crashing."""
        path = self._write_yaml(INVALID_YAML)
        try:
            skill = load_skill_from_yaml(path)
            assert skill is None
        finally:
            path.unlink()

    def test_nonexistent_file_returns_none(self):
        """Missing file should return None."""
        skill = load_skill_from_yaml(Path("/tmp/nonexistent_skill_xyz.yaml"))
        assert skill is None


# ── _parse_parameter tests ────────────────────────────────────────────

class TestParseParameter:
    """Tests for _parse_parameter helper."""

    def test_float_parameter(self):
        """Float parameter should parse correctly."""
        param = _parse_parameter("intensity", {
            "type": "float",
            "default": 1.5,
            "min": 0.0,
            "max": 10.0,
            "description": "Effect intensity",
        })
        assert param.name == "intensity"
        assert param.default == 1.5
        assert param.description == "Effect intensity"

    def test_int_parameter(self):
        """Integer parameter should parse correctly."""
        param = _parse_parameter("radius", {
            "type": "int",
            "default": 5,
            "min": 1,
            "max": 50,
        })
        assert param.name == "radius"
        assert param.default == 5

    def test_choice_parameter(self):
        """Choice parameter should include choices list."""
        param = _parse_parameter("mode", {
            "type": "choice",
            "default": "fast",
            "choices": ["fast", "slow", "medium"],
        })
        assert param.choices == ["fast", "slow", "medium"]

    def test_string_parameter(self):
        """String parameter should work with 'str' type alias."""
        param = _parse_parameter("text", {
            "type": "str",
            "default": "hello",
        })
        assert param.default == "hello"

    def test_bool_parameter(self):
        """Boolean type aliases should work."""
        param = _parse_parameter("enabled", {
            "type": "boolean",
            "default": True,
        })
        assert param.default is True

    def test_default_type_is_string(self):
        """Missing type should default to string."""
        param = _parse_parameter("text", {
            "default": "hello",
        })
        assert param.default == "hello"


# ── load_custom_skills directory scan ─────────────────────────────────

class TestLoadCustomSkillsDirectory:
    """Tests for scanning custom_skills directory."""

    def test_load_from_temp_directory(self):
        """Should load skills from a directory of YAML files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Write a test skill
            skill_path = Path(tmpdir) / "test_effect.yaml"
            skill_path.write_text(VALID_SKILL_YAML)

            registry = SkillRegistry()
            handlers = {}

            # load_custom_skills uses a fixed path, so we test load_skill_from_yaml
            # and manual registration instead
            skill = load_skill_from_yaml(skill_path)
            assert skill is not None
            registry.register(skill)

            found = registry.get("test_glow")
            assert found is not None
            assert found.name == "test_glow"

    def test_example_skills_load(self):
        """Built-in example skills should load without errors."""
        examples_dir = Path(__file__).parent.parent / "custom_skills" / "examples"
        if not examples_dir.exists():
            pytest.skip("custom_skills/examples not found")

        yaml_files = list(examples_dir.glob("*.yaml"))
        if not yaml_files:
            pytest.skip("No example yaml files found")

        for yaml_file in yaml_files:
            skill = load_skill_from_yaml(yaml_file)
            assert skill is not None, f"Failed to load {yaml_file.name}"
            assert skill.name, f"{yaml_file.name} has empty name"
            assert skill.description, f"{yaml_file.name} has empty description"
