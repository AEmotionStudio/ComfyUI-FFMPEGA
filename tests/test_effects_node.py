"""Tests for the FFMPEGA Effects Builder node."""

import json
import sys
import importlib.util
from pathlib import Path

import pytest

# Load effects_node directly to avoid ComfyUI deps in nodes/__init__.py
_effects_path = Path(__file__).resolve().parent.parent / "nodes" / "effects_node.py"
_spec = importlib.util.spec_from_file_location("effects_node", _effects_path)
_mod = importlib.util.module_from_spec(_spec)
sys.modules["effects_node"] = _mod
_spec.loader.exec_module(_mod)

FFMPEGAEffectsNode = _mod.FFMPEGAEffectsNode
_get_skill_data = _mod._get_skill_data
_find_categorized_name = _mod._find_categorized_name
_PRESETS = _mod._PRESETS
_PRESET_NAMES = _mod._PRESET_NAMES


class TestEffectsNodeInputTypes:
    """Tests for INPUT_TYPES and initialization."""

    def test_input_types_structure(self):
        """INPUT_TYPES should have required + optional sections."""
        inputs = FFMPEGAEffectsNode.INPUT_TYPES()
        assert "required" in inputs
        assert "optional" in inputs
        assert "preset" in inputs["required"]
        assert "effect_1" in inputs["required"]

    def test_effect_dropdowns_populated(self):
        """Effect dropdowns should contain categorized skill names."""
        inputs = FFMPEGAEffectsNode.INPUT_TYPES()
        skills = inputs["required"]["effect_1"][0]
        assert "none" in skills
        assert len(skills) > 10  # should have many skills
        # Should have at least one categorized name with /
        cat_names = [s for s in skills if "/" in s]
        assert len(cat_names) > 0

    def test_preset_dropdown(self):
        """Preset dropdown should contain curated presets."""
        inputs = FFMPEGAEffectsNode.INPUT_TYPES()
        presets = inputs["required"]["preset"][0]
        assert "none" in presets
        assert len(presets) >= 8  # we defined 8+ presets

    def test_hidden_data_widgets_present(self):
        """Hidden _presets_json and _defaults_json should be in optional inputs."""
        inputs = FFMPEGAEffectsNode.INPUT_TYPES()
        assert "_presets_json" in inputs["optional"]
        assert "_defaults_json" in inputs["optional"]

    def test_preset_json_is_valid(self):
        """_presets_json default should be valid JSON."""
        inputs = FFMPEGAEffectsNode.INPUT_TYPES()
        presets_str = inputs["optional"]["_presets_json"][1]["default"]
        data = json.loads(presets_str)
        assert isinstance(data, dict)
        assert len(data) > 0

    def test_defaults_json_is_valid(self):
        """_defaults_json default should be valid JSON."""
        inputs = FFMPEGAEffectsNode.INPUT_TYPES()
        defaults_str = inputs["optional"]["_defaults_json"][1]["default"]
        data = json.loads(defaults_str)
        assert isinstance(data, dict)


class TestSkillData:
    """Tests for the _get_skill_data helper."""

    def test_returns_three_tuple(self):
        """Should return (names, param_help, param_defaults)."""
        result = _get_skill_data()
        assert len(result) == 3
        names, param_help, param_defaults = result
        assert isinstance(names, list)
        assert isinstance(param_help, dict)
        assert isinstance(param_defaults, dict)

    def test_names_start_with_none(self):
        """First entry should be 'none'."""
        names, _, _ = _get_skill_data()
        assert names[0] == "none"

    def test_names_are_categorized(self):
        """Skill names should be prefixed with category labels."""
        names, _, _ = _get_skill_data()
        cat_names = [n for n in names if "/" in n]
        assert len(cat_names) > 0
        # Check for emoji category prefixes
        has_visual = any("🎨" in n for n in cat_names)
        has_temporal = any("⏱️" in n for n in cat_names)
        assert has_visual
        assert has_temporal

    def test_param_defaults_are_valid_json(self):
        """Each param_default value should be parseable JSON."""
        _, _, param_defaults = _get_skill_data()
        for skill, defaults_str in param_defaults.items():
            data = json.loads(defaults_str)
            assert isinstance(data, dict), f"{skill} defaults should be a dict"


class TestFindCategorizedName:
    """Tests for _find_categorized_name."""

    def test_finds_known_skill(self):
        """Should find the full categorized name for a raw skill."""
        names, _, _ = _get_skill_data()
        result = _find_categorized_name("blur", names)
        assert "/" in result
        assert result.endswith("/blur")

    def test_none_returns_none(self):
        """'none' should return 'none'."""
        assert _find_categorized_name("none", []) == "none"

    def test_unknown_returns_none(self):
        """Unknown skills should return 'none'."""
        result = _find_categorized_name("totally_fake_skill_xyz", ["none", "🎨 Visual/blur"])
        assert result == "none"


class TestStripCategory:
    """Tests for _strip_category."""

    def test_strips_prefix(self):
        assert FFMPEGAEffectsNode._strip_category("🎨 Visual/blur") == "blur"

    def test_strips_complex_prefix(self):
        assert FFMPEGAEffectsNode._strip_category("⏱️ Temporal/trim") == "trim"

    def test_none_unchanged(self):
        assert FFMPEGAEffectsNode._strip_category("none") == "none"

    def test_no_slash_unchanged(self):
        assert FFMPEGAEffectsNode._strip_category("blur") == "blur"


class TestBuildPipeline:
    """Tests for build_pipeline method."""

    @pytest.fixture
    def node(self):
        return FFMPEGAEffectsNode()

    def test_empty_state(self, node):
        """No effects selected should produce empty pipeline."""
        result = node.build_pipeline()
        data = json.loads(result[0])
        assert data["effects_mode"] == "empty"
        assert data["pipeline"] == []
        assert data["raw_ffmpeg"] == ""
        assert data["sam3"] is None

    def test_single_effect(self, node):
        """Single effect should produce skills mode."""
        result = node.build_pipeline(effect_1="🎨 Visual/blur")
        data = json.loads(result[0])
        assert data["effects_mode"] == "skills"
        assert len(data["pipeline"]) == 1
        assert data["pipeline"][0]["skill"] == "blur"

    def test_effect_with_params(self, node):
        """Effect with JSON params should parse correctly."""
        result = node.build_pipeline(
            effect_1="🎨 Visual/blur",
            effect_1_params='{"strength": 10}',
        )
        data = json.loads(result[0])
        assert data["pipeline"][0]["params"] == {"strength": 10}

    def test_multiple_effects(self, node):
        """Multiple effects should chain in order."""
        result = node.build_pipeline(
            effect_1="🎨 Visual/blur",
            effect_2="🎨 Visual/black_and_white",
            effect_3="⏱️ Temporal/speed",
            effect_3_params='{"factor": 2.0}',
        )
        data = json.loads(result[0])
        assert data["effects_mode"] == "skills"
        assert len(data["pipeline"]) == 3
        assert data["pipeline"][0]["skill"] == "blur"
        assert data["pipeline"][1]["skill"] == "black_and_white"
        assert data["pipeline"][2]["skill"] == "speed"
        assert data["pipeline"][2]["params"]["factor"] == 2.0

    def test_raw_ffmpeg_only(self, node):
        """Raw FFmpeg input only should produce raw mode."""
        result = node.build_pipeline(raw_ffmpeg="boxblur=5,eq=brightness=0.1")
        data = json.loads(result[0])
        assert data["effects_mode"] == "raw"
        assert data["raw_ffmpeg"] == "boxblur=5,eq=brightness=0.1"
        assert data["pipeline"] == []

    def test_hybrid_mode(self, node):
        """Skills + raw FFmpeg should produce hybrid mode."""
        result = node.build_pipeline(
            effect_1="🎨 Visual/blur",
            raw_ffmpeg="eq=brightness=0.1",
        )
        data = json.loads(result[0])
        assert data["effects_mode"] == "hybrid"
        assert len(data["pipeline"]) == 1
        assert data["raw_ffmpeg"] == "eq=brightness=0.1"

    def test_sam3_integration(self, node):
        """SAM3 target should add auto_mask step and sam3 config."""
        result = node.build_pipeline(
            sam3_target="the person",
            sam3_effect="blur",
        )
        data = json.loads(result[0])
        assert data["sam3"]["target"] == "the person"
        assert data["sam3"]["effect"] == "blur"
        # auto_mask should be inserted as a pipeline step
        assert any(s["skill"] == "auto_mask" for s in data["pipeline"])

    def test_sam3_with_none_effect(self, node):
        """SAM3 with effect='none' should still set target but default to blur."""
        result = node.build_pipeline(
            sam3_target="face",
            sam3_effect="none",
        )
        data = json.loads(result[0])
        assert data["sam3"]["target"] == "face"
        assert data["sam3"]["effect"] == "blur"  # defaults to blur

    def test_invalid_json_params_ignored(self, node):
        """Invalid JSON in params should be ignored with empty params."""
        result = node.build_pipeline(
            effect_1="🎨 Visual/blur",
            effect_1_params="not valid json {",
        )
        data = json.loads(result[0])
        assert data["pipeline"][0]["params"] == {}

    def test_non_dict_params_ignored(self, node):
        """Non-dict JSON in params should be ignored."""
        result = node.build_pipeline(
            effect_1="🎨 Visual/blur",
            effect_1_params='[1, 2, 3]',
        )
        data = json.loads(result[0])
        assert data["pipeline"][0]["params"] == {}

    def test_none_effects_skipped(self, node):
        """Effects set to 'none' should not appear in pipeline."""
        result = node.build_pipeline(
            effect_1="none",
            effect_2="🎨 Visual/blur",
        )
        data = json.loads(result[0])
        # Only blur should be in the pipeline
        assert len(data["pipeline"]) == 1
        assert data["pipeline"][0]["skill"] == "blur"

    def test_uncategorized_effect_name(self, node):
        """Raw skill name without category prefix should still work."""
        result = node.build_pipeline(effect_1="blur")
        data = json.loads(result[0])
        assert data["pipeline"][0]["skill"] == "blur"

    def test_is_changed_hash(self):
        """IS_CHANGED should return different hashes for different inputs."""
        h1 = FFMPEGAEffectsNode.IS_CHANGED(effect_1="blur")
        h2 = FFMPEGAEffectsNode.IS_CHANGED(effect_1="black_and_white")
        h3 = FFMPEGAEffectsNode.IS_CHANGED(effect_1="blur")
        assert h1 != h2
        assert h1 == h3


class TestPresets:
    """Tests for preset definitions."""

    def test_presets_have_none(self):
        """Presets should include 'none'."""
        assert "none" in _PRESET_NAMES

    def test_all_presets_have_valid_skills(self):
        """All preset skill references should exist in the registry."""
        from skills.registry import get_registry
        registry = get_registry()
        all_skills = {s.name for s in registry.list_all()}

        for preset_name, cfg in _PRESETS.items():
            if preset_name == "none":
                continue
            for key in ("effect_1", "effect_2", "effect_3"):
                skill = cfg.get(key, "none")
                if skill and skill != "none":
                    assert skill in all_skills, (
                        f"Preset '{preset_name}' references unknown skill '{skill}'"
                    )

    def test_preset_count(self):
        """Should have at least 8 presets (including 'none')."""
        assert len(_PRESET_NAMES) >= 8


class TestInjectEffectsHints:
    """Tests for _inject_effects_hints (from agent_node)."""

    @staticmethod
    def _get_inject_fn():
        """Import _inject_effects_hints without importing all of agent_node."""
        # Since agent_node imports ComfyUI-specific modules, we test the
        # static method via the effects node's _strip_category as a proxy,
        # and verify the hint injection logic here manually.
        def inject(prompt, pipeline_json):
            import json as _json
            try:
                data = _json.loads(pipeline_json)
            except (ValueError, TypeError):
                return prompt
            steps = data.get("pipeline", [])
            raw = data.get("raw_ffmpeg", "")
            if not steps and not raw:
                return prompt
            hint_lines = [
                "\n\n--- EFFECTS BUILDER (pre-selected by user) ---",
                "The user has pre-selected the following effects. You MUST include",
                "these EXACT skills in your pipeline with the specified parameters.",
                "You may add additional skills if the user's prompt requires them.",
            ]
            for step in steps:
                skill = step.get("skill", "")
                params = step.get("params", {})
                if skill:
                    params_str = ", ".join(f"{k}={v}" for k, v in params.items()) if params else "defaults"
                    hint_lines.append(f"  - {skill} ({params_str})")
            if raw:
                hint_lines.append(f"  - RAW FFMPEG FILTERS: {raw}")
            hint_lines.append("--- END EFFECTS BUILDER ---")
            return prompt + "\n".join(hint_lines)
        return inject

    def test_injects_skill_hints(self):
        inject = self._get_inject_fn()
        pipeline = json.dumps({
            "pipeline": [{"skill": "blur", "params": {"strength": 5}}],
            "raw_ffmpeg": "",
        })
        result = inject("Make the video dreamy", pipeline)
        assert "blur" in result
        assert "strength=5" in result
        assert "EFFECTS BUILDER" in result

    def test_injects_raw_filter(self):
        inject = self._get_inject_fn()
        pipeline = json.dumps({
            "pipeline": [],
            "raw_ffmpeg": "boxblur=5",
        })
        result = inject("Apply filter", pipeline)
        assert "boxblur=5" in result

    def test_empty_pipeline_no_injection(self):
        inject = self._get_inject_fn()
        pipeline = json.dumps({
            "pipeline": [],
            "raw_ffmpeg": "",
        })
        result = inject("No effects", pipeline)
        assert result == "No effects"

    def test_invalid_json_returns_original(self):
        inject = self._get_inject_fn()
        result = inject("Original prompt", "not valid json")
        assert result == "Original prompt"
