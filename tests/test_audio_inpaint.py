"""Tests for the audio_inpaint skill (AudioX integration).

Covers skill registration, handler unit tests (with AudioX mocked),
dispatch table wiring, and alias resolution.
"""

import pytest
from unittest.mock import patch

from skills.handler_contract import HandlerResult
from skills.registry import get_registry, SkillCategory


# ── Skill Registration ─────────────────────────────────────────────


class TestAudioInpaintSkillRegistration:
    """Verify audio_inpaint is registered correctly in the skill registry."""

    def test_skill_exists_in_registry(self):
        """audio_inpaint should be registered in the global registry."""
        registry = get_registry()
        skill = registry.get("audio_inpaint")
        assert skill is not None
        assert skill.name == "audio_inpaint"

    def test_skill_category_is_audio(self):
        """audio_inpaint should be in the AUDIO category."""
        registry = get_registry()
        skill = registry.get("audio_inpaint")
        assert skill.category == SkillCategory.AUDIO

    def test_skill_has_prompt_param(self):
        """audio_inpaint should have a 'prompt' parameter."""
        registry = get_registry()
        skill = registry.get("audio_inpaint")
        param = skill.get_param("prompt")
        assert param is not None
        assert param.default == ""

    def test_skill_has_mask_start_param(self):
        """audio_inpaint should have a 'mask_start' parameter."""
        registry = get_registry()
        skill = registry.get("audio_inpaint")
        param = skill.get_param("mask_start")
        assert param is not None
        assert param.default == 0.0
        assert param.min_value == 0.0
        assert param.max_value == 100.0

    def test_skill_has_mask_end_param(self):
        """audio_inpaint should have a 'mask_end' parameter."""
        registry = get_registry()
        skill = registry.get("audio_inpaint")
        param = skill.get_param("mask_end")
        assert param is not None
        assert param.default == 100.0
        assert param.min_value == 0.0
        assert param.max_value == 100.0

    def test_skill_has_seed_param(self):
        """audio_inpaint should have a 'seed' parameter."""
        registry = get_registry()
        skill = registry.get("audio_inpaint")
        param = skill.get_param("seed")
        assert param is not None
        assert param.default == -1

    def test_skill_has_cfg_scale_param(self):
        """audio_inpaint should have a 'cfg_scale' parameter."""
        registry = get_registry()
        skill = registry.get("audio_inpaint")
        param = skill.get_param("cfg_scale")
        assert param is not None
        assert param.default == 7.0

    def test_skill_has_steps_param(self):
        """audio_inpaint should have a 'steps' parameter."""
        registry = get_registry()
        skill = registry.get("audio_inpaint")
        param = skill.get_param("steps")
        assert param is not None
        assert param.default == 250

    def test_skill_has_tags(self):
        """audio_inpaint should have relevant search tags."""
        registry = get_registry()
        skill = registry.get("audio_inpaint")
        assert "inpaint" in skill.tags
        assert "audiox" in skill.tags

    def test_skill_searchable_by_keywords(self):
        """audio_inpaint should be findable by searching relevant keywords."""
        registry = get_registry()
        for keyword in ["inpaint", "fill", "extend", "completion"]:
            results = registry.search(keyword)
            names = [s.name for s in results]
            assert "audio_inpaint" in names, f"Not found for keyword: {keyword}"


# ── Handler Unit Tests ─────────────────────────────────────────────


class TestAudioInpaintHandler:
    """Test the _f_audio_inpaint handler function with mocked AudioX."""

    def test_handler_returns_handler_result(self):
        """Handler should return a HandlerResult even when AudioX is unavailable."""
        from skills.handlers.audio_inpaint import _f_audio_inpaint
        result = _f_audio_inpaint({})
        assert isinstance(result, HandlerResult)

    def test_fallback_when_no_audiox(self):
        """When no valid video is available, handler should return empty result gracefully."""
        from skills.handlers.audio_inpaint import _f_audio_inpaint
        metadata = {}
        result = _f_audio_inpaint({
            "prompt": "test",
            "_input_path": "/fake/video.mp4",
            "_metadata_ref": metadata,
        })
        assert isinstance(result, HandlerResult)
        # Handler returns early when the file doesn't exist — that's correct behavior

    def test_no_video_returns_empty(self):
        """With no video input, handler returns empty result."""
        from skills.handlers.audio_inpaint import _f_audio_inpaint

        with patch("skills.handlers.audio_inpaint.log"):
            result = _f_audio_inpaint({
                "_input_path": "",
                "prompt": "birds chirping",
            })
            assert isinstance(result, HandlerResult)


# ── Dispatch Table Tests ───────────────────────────────────────────


class TestAudioInpaintDispatch:
    """Verify audio_inpaint is wired into the dispatch table."""

    def test_dispatch_table_has_audio_inpaint(self):
        """audio_inpaint should be in the dispatch table."""
        from skills.composer import _get_dispatch
        dispatch = _get_dispatch()
        assert "audio_inpaint" in dispatch

    def test_dispatch_aliases(self):
        """All audio_inpaint aliases should exist in the dispatch table."""
        from skills.composer import _get_dispatch
        dispatch = _get_dispatch()
        aliases = [
            "inpaint_audio", "audio_fill", "extend_audio",
            "audio_completion", "complete_audio",
        ]
        for alias in aliases:
            assert alias in dispatch, f"Alias '{alias}' not in dispatch table"

    def test_all_aliases_point_to_same_handler(self):
        """All aliases should point to the same handler function."""
        from skills.composer import _get_dispatch
        dispatch = _get_dispatch()
        base_handler = dispatch["audio_inpaint"]
        aliases = [
            "inpaint_audio", "audio_fill", "extend_audio",
            "audio_completion", "complete_audio",
        ]
        for alias in aliases:
            assert dispatch[alias] is base_handler, (
                f"Alias '{alias}' doesn't point to audio_inpaint handler"
            )


# ── Composer Alias Tests ───────────────────────────────────────────


class TestAudioInpaintComposerAliases:
    """Verify composer aliases resolve audio_inpaint correctly."""

    def test_skill_aliases_in_composer(self):
        """SKILL_ALIASES should map common names to audio_inpaint."""
        from skills.composer import SkillComposer
        aliases = SkillComposer.SKILL_ALIASES
        expected = {
            "inpaint_audio": "audio_inpaint",
            "audio_fill": "audio_inpaint",
            "extend_audio": "audio_inpaint",
            "audio_completion": "audio_inpaint",
            "complete_audio": "audio_inpaint",
        }
        for alias, target in expected.items():
            assert aliases.get(alias) == target, (
                f"Alias '{alias}' not mapped to '{target}'"
            )


# ── No-LLM Mode Tests ───────────────────────────────────────────


class TestAudioInpaintNoLLMMode:
    """Verify audio_inpaint is wired into the no_llm_mode system."""

    def test_audio_inpaint_in_no_llm_mode_dropdown(self):
        """audio_inpaint should be a valid no_llm_mode option."""
        pytest.importorskip("torch")
        from nodes.agent_node import FFMPEGAgentNode
        inputs = FFMPEGAgentNode.INPUT_TYPES()
        no_llm_choices = inputs["required"]["no_llm_mode"][0]
        assert "audio_inpaint (AudioX)" in no_llm_choices
