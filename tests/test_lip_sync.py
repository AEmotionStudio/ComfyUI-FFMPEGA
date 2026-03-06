"""Tests for the lip_sync skill (MuseTalk integration).

Covers skill registration, handler unit tests (with MuseTalk mocked),
dispatch table wiring, and alias resolution.
"""

import pytest
from unittest.mock import patch, MagicMock

from skills.handler_contract import HandlerResult
from skills.registry import get_registry, SkillCategory


# ── Skill Registration ─────────────────────────────────────────────


class TestLipSyncSkillRegistration:
    """Verify lip_sync is registered correctly in the skill registry."""

    # lip_sync should be registered in the global registry.
    def test_skill_exists_in_registry(self):
        registry = get_registry()
        skill = registry.get("lip_sync")
        assert skill is not None
        assert skill.name == "lip_sync"

    # lip_sync should be in the AUDIO category.
    def test_skill_category_is_audio(self):
        registry = get_registry()
        skill = registry.get("lip_sync")
        assert skill.category == SkillCategory.AUDIO

    # lip_sync should have a required 'audio_path' parameter.
    def test_skill_has_audio_path_param(self):
        registry = get_registry()
        skill = registry.get("lip_sync")
        param = skill.get_param("audio_path")
        assert param is not None
        assert param.required is True

    # lip_sync should have an optional 'face_index' parameter.
    def test_skill_has_face_index_param(self):
        registry = get_registry()
        skill = registry.get("lip_sync")
        param = skill.get_param("face_index")
        assert param is not None
        assert param.required is False
        assert param.default == -1

    # lip_sync should have an optional 'batch_size' parameter.
    def test_skill_has_batch_size_param(self):
        registry = get_registry()
        skill = registry.get("lip_sync")
        param = skill.get_param("batch_size")
        assert param is not None
        assert param.required is False
        assert param.default == 8

    # lip_sync should have relevant search tags.
    def test_skill_has_tags(self):
        registry = get_registry()
        skill = registry.get("lip_sync")
        assert "musetalk" in skill.tags
        assert "ai" in skill.tags
        assert "lip" in skill.tags

    # lip_sync should be findable by searching relevant keywords.
    def test_skill_searchable_by_keywords(self):
        registry = get_registry()
        for keyword in ["lip", "sync", "dub", "musetalk"]:
            results = registry.search(keyword)
            names = [s.name for s in results]
            assert "lip_sync" in names, f"lip_sync should be found for '{keyword}'"


# ── Handler Unit Tests ─────────────────────────────────────────────


class TestLipSyncHandler:
    """Test the _f_lip_sync handler function with mocked MuseTalk."""

    # Handler should return a HandlerResult even when MuseTalk is unavailable.
    def test_handler_returns_handler_result(self):
        from skills.handlers.lip_sync import _f_lip_sync
        result = _f_lip_sync({"_input_path": "", "audio_path": ""})
        assert isinstance(result, HandlerResult)

    # When audio_path is missing, handler should degrade gracefully.
    def test_degrades_when_audio_path_missing(self):
        from skills.handlers.lip_sync import _f_lip_sync
        metadata = {}
        result = _f_lip_sync({
            "_input_path": "/tmp/test.mp4",
            "audio_path": "",
            "_metadata_ref": metadata,
        })
        assert isinstance(result, HandlerResult)
        assert metadata.get("_skill_degraded") is True

    # When _input_path is missing, handler should degrade gracefully.
    def test_degrades_when_video_path_missing(self):
        from skills.handlers.lip_sync import _f_lip_sync
        metadata = {}
        result = _f_lip_sync({
            "_input_path": "",
            "audio_path": "/tmp/test.wav",
            "_metadata_ref": metadata,
        })
        assert isinstance(result, HandlerResult)
        assert metadata.get("_skill_degraded") is True

    # With valid inputs and mocked MuseTalk, handler should return filter_complex.
    @patch("skills.handlers.lip_sync.validate_video_path", side_effect=lambda x: x)
    def test_success_with_mocked_musetalk(self, mock_validate):
        from skills.handlers.lip_sync import _f_lip_sync

        mock_lip_sync = MagicMock(return_value="/tmp/output_lipsync.mp4")

        with patch(
            "core.musetalk_synthesizer.lip_sync",
            mock_lip_sync,
            create=True,
        ):
            metadata = {}
            result = _f_lip_sync({
                "_input_path": "/tmp/test.mp4",
                "audio_path": "/tmp/speech.wav",
                "_metadata_ref": metadata,
            })
            assert isinstance(result, HandlerResult)

    # Handler should import lip_sync, not lip_sync_subprocess.
    def test_handler_uses_in_process_not_subprocess(self):
        import inspect
        from skills.handlers import lip_sync as lip_sync_module
        source = inspect.getsource(lip_sync_module)
        assert "lip_sync_subprocess" not in source, (
            "Handler should use lip_sync() in-process, not lip_sync_subprocess()"
        )


# ── Dispatch Table Tests ───────────────────────────────────────────


class TestLipSyncDispatch:
    """Verify lip_sync is wired into the dispatch table."""

    # lip_sync should be in the dispatch table.
    def test_dispatch_table_has_lip_sync(self):
        from skills.composer import _get_dispatch
        dispatch = _get_dispatch()
        assert "lip_sync" in dispatch

    # All lip_sync aliases should exist in the dispatch table.
    def test_dispatch_aliases(self):
        from skills.composer import _get_dispatch
        dispatch = _get_dispatch()

        aliases = [
            "lip_sync", "lipsync", "dub", "dubbing",
            "sync_lips", "talking_head", "lip_dub", "voice_sync",
        ]
        for alias in aliases:
            assert alias in dispatch, f"'{alias}' should be in dispatch table"

    # All aliases should point to the same handler function.
    def test_all_aliases_point_to_same_handler(self):
        from skills.composer import _get_dispatch
        dispatch = _get_dispatch()

        canonical_handler = dispatch["lip_sync"]
        aliases = ["lipsync", "dub", "dubbing", "sync_lips", "talking_head", "lip_dub", "voice_sync"]
        for alias in aliases:
            assert dispatch[alias] is canonical_handler, (
                f"'{alias}' should point to same handler as 'lip_sync'"
            )


# ── Alias Resolution Tests ────────────────────────────────────────


class TestLipSyncAliasResolution:
    """Verify skill alias resolution for lip_sync."""

    def test_aliases_resolve_to_lip_sync(self):
        from skills.composer import SkillComposer
        aliases = [
            "lipsync", "dub", "dubbing", "sync_lips",
            "talking_head", "lip_dub", "voice_sync",
        ]
        for alias in aliases:
            canonical = SkillComposer.SKILL_ALIASES.get(alias)
            assert canonical == "lip_sync", (
                f"Alias '{alias}' should resolve to 'lip_sync', got '{canonical}'"
            )


# ── No-LLM Mode Tests ─────────────────────────────────────────────


class TestLipSyncNoLLMMode:
    """Verify lip_sync is wired into the no_llm_mode system."""

    def test_lip_sync_in_no_llm_mode_dropdown(self):
        """lip_sync should be a valid no_llm_mode option."""
        pytest.importorskip("torch")
        from nodes.agent_node import FFMPEGAgentNode
        inputs = FFMPEGAgentNode.INPUT_TYPES()
        no_llm_choices = inputs["required"]["no_llm_mode"][0]
        assert "lip_sync" in no_llm_choices

    def test_audio_a_tooltip_mentions_lip_sync(self):
        """audio_a tooltip should mention lip sync."""
        pytest.importorskip("torch")
        from nodes.agent_node import FFMPEGAgentNode
        inputs = FFMPEGAgentNode.INPUT_TYPES()
        tooltip = inputs["optional"]["audio_a"][1]["tooltip"]
        assert "lip sync" in tooltip.lower()


# ── Model Caching API Tests ───────────────────────────────────────────


class TestMuseTalkModelCaching:
    """Verify the in-process model caching API exists."""

    def test_load_models_exists(self):
        """load_models function should be importable."""
        from core.musetalk_synthesizer import load_models
        assert callable(load_models)

    def test_cleanup_exists(self):
        """cleanup function should be importable."""
        from core.musetalk_synthesizer import cleanup
        assert callable(cleanup)

    def test_lip_sync_subprocess_still_exists(self):
        """lip_sync_subprocess should still exist as legacy fallback."""
        from core.musetalk_synthesizer import lip_sync_subprocess
        assert callable(lip_sync_subprocess)
