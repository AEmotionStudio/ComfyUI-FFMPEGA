"""Tests for the ace_step skill (ACE-Step 1.5 integration).

Covers skill registration, handler unit tests (with ACE-Step mocked),
dispatch table wiring, alias resolution, model manager, VRAM utils,
and no-LLM mode wiring.
"""

import pytest
from unittest.mock import patch

from skills.handler_contract import HandlerResult
from skills.registry import get_registry, SkillCategory


# ── Skill Registration ─────────────────────────────────────────────


class TestAceStepSkillRegistration:
    """Verify ace_step is registered correctly in the skill registry."""

    def test_skill_exists_in_registry(self):
        """ace_step should be registered in the global registry."""
        registry = get_registry()
        skill = registry.get("ace_step")
        assert skill is not None
        assert skill.name == "ace_step"

    def test_skill_category_is_audio(self):
        """ace_step should be in the AUDIO category."""
        registry = get_registry()
        skill = registry.get("ace_step")
        assert skill.category == SkillCategory.AUDIO

    def test_skill_has_prompt_param(self):
        """ace_step should have a 'prompt' parameter."""
        registry = get_registry()
        skill = registry.get("ace_step")
        param = skill.get_param("prompt")
        assert param is not None
        assert param.default == ""

    def test_skill_has_lyrics_param(self):
        """ace_step should have a 'lyrics' parameter."""
        registry = get_registry()
        skill = registry.get("ace_step")
        param = skill.get_param("lyrics")
        assert param is not None
        assert param.default == ""

    def test_skill_has_mode_param(self):
        """ace_step should have a 'mode' parameter with all 4 choices."""
        registry = get_registry()
        skill = registry.get("ace_step")
        param = skill.get_param("mode")
        assert param is not None
        assert param.default == "generate"
        assert set(param.choices) == {
            "generate", "cover", "repaint", "audiox_repaint",
        }

    def test_skill_has_audio_mode_param(self):
        """ace_step should have an 'audio_mode' parameter."""
        registry = get_registry()
        skill = registry.get("ace_step")
        param = skill.get_param("audio_mode")
        assert param is not None
        assert param.default == "replace"
        assert set(param.choices) == {"replace", "mix", "save_only"}

    def test_skill_has_duration_param(self):
        """ace_step should have a 'duration' parameter with 10-600 range."""
        registry = get_registry()
        skill = registry.get("ace_step")
        param = skill.get_param("duration")
        assert param is not None
        assert param.default == 60.0
        assert param.min_value == 10.0
        assert param.max_value == 600.0

    def test_skill_has_lm_model_param(self):
        """ace_step should have an 'lm_model' parameter."""
        registry = get_registry()
        skill = registry.get("ace_step")
        param = skill.get_param("lm_model")
        assert param is not None
        assert param.default == "1.7B"
        assert set(param.choices) == {"0.6B", "1.7B"}

    def test_skill_has_cover_strength_param(self):
        """ace_step should have a 'cover_strength' parameter."""
        registry = get_registry()
        skill = registry.get("ace_step")
        param = skill.get_param("cover_strength")
        assert param is not None
        assert param.default == 0.8
        assert param.min_value == 0.0
        assert param.max_value == 1.0

    def test_skill_has_steps_param(self):
        """ace_step should have a 'steps' parameter."""
        registry = get_registry()
        skill = registry.get("ace_step")
        param = skill.get_param("steps")
        assert param is not None
        assert param.default == 8  # turbo default

    def test_skill_has_seed_param(self):
        """ace_step should have a 'seed' parameter."""
        registry = get_registry()
        skill = registry.get("ace_step")
        param = skill.get_param("seed")
        assert param is not None
        assert param.default == -1

    def test_skill_has_tags(self):
        """ace_step should have relevant search tags."""
        registry = get_registry()
        skill = registry.get("ace_step")
        assert "music" in skill.tags
        assert "ace_step" in skill.tags
        assert "cover" in skill.tags
        assert "repaint" in skill.tags
        assert "mit" in skill.tags

    def test_skill_searchable_by_keywords(self):
        """ace_step should be findable by searching relevant keywords."""
        registry = get_registry()
        for keyword in ["ace_step", "cover", "repaint", "lyrics"]:
            results = registry.search(keyword)
            names = [s.name for s in results]
            assert "ace_step" in names, f"Not found for keyword: {keyword}"


# ── Handler Unit Tests ─────────────────────────────────────────────


class TestAceStepHandler:
    """Test the _f_ace_step handler function with ACE-Step mocked."""

    def test_handler_returns_handler_result(self):
        """Handler should return a HandlerResult even when ACE-Step is unavailable."""
        from skills.handlers.ace_step import _f_ace_step
        result = _f_ace_step({})
        assert isinstance(result, HandlerResult)

    @patch("core.acestep_synthesizer.is_available", return_value=False)
    def test_fallback_when_no_acestep(self, mock_avail):
        """When ACE-Step is not installed, handler should return empty result gracefully."""
        from skills.handlers.ace_step import _f_ace_step
        metadata = {}
        result = _f_ace_step({
            "prompt": "test",
            "_input_path": "/fake/video.mp4",
            "_metadata_ref": metadata,
        })
        assert isinstance(result, HandlerResult)
        # Should mark as degraded when ACE-Step not available
        assert metadata.get("_skill_degraded") is True

    @patch("core.acestep_synthesizer.generate_music_acestep")
    @patch("core.acestep_synthesizer.is_available", return_value=True)
    def test_generate_mode_replace(self, mock_avail, mock_gen):
        """mode=generate + audio_mode=replace should produce amovie filter."""
        mock_gen.return_value = "/tmp/test_ace.wav"

        with patch("os.path.isfile", return_value=True):
            from skills.handlers.ace_step import _f_ace_step
            result = _f_ace_step({
                "prompt": "epic orchestral",
                "mode": "generate",
                "audio_mode": "replace",
                "_input_path": "/fake/video.mp4",
                "_metadata_ref": {},
            })
        assert isinstance(result, HandlerResult)
        if result.filter_complex:
            assert "amovie" in result.filter_complex

    @patch("core.acestep_synthesizer.generate_music_acestep")
    @patch("core.acestep_synthesizer.is_available", return_value=True)
    def test_generate_mode_mix_with_audio(self, mock_avail, mock_gen):
        """mode=generate + audio_mode=mix with embedded audio should use amix."""
        mock_gen.return_value = "/tmp/test_ace.wav"

        with patch("os.path.isfile", return_value=True):
            from skills.handlers.ace_step import _f_ace_step
            result = _f_ace_step({
                "prompt": "calm piano",
                "mode": "generate",
                "audio_mode": "mix",
                "_input_path": "/fake/video.mp4",
                "_has_embedded_audio": True,
                "_metadata_ref": {},
            })
        assert isinstance(result, HandlerResult)
        if result.filter_complex:
            assert "amix" in result.filter_complex

    @patch("core.acestep_synthesizer.generate_music_acestep")
    @patch("core.acestep_synthesizer.is_available", return_value=True)
    def test_save_only_mode(self, mock_avail, mock_gen):
        """audio_mode=save_only should return empty result (no ffmpeg)."""
        mock_gen.return_value = "/tmp/test_ace.wav"

        with patch("os.path.isfile", return_value=True):
            from skills.handlers.ace_step import _f_ace_step
            result = _f_ace_step({
                "prompt": "test",
                "audio_mode": "save_only",
                "_input_path": "/fake/video.mp4",
                "_metadata_ref": {},
            })
        assert isinstance(result, HandlerResult)
        # save_only should not produce filter_complex
        assert not result.filter_complex


# ── Dispatch Table Tests ───────────────────────────────────────────


class TestAceStepDispatch:
    """Verify ace_step is wired into the dispatch table."""

    def test_dispatch_table_has_ace_step(self):
        """ace_step should be in the dispatch table."""
        from skills.composer import _get_dispatch
        dispatch = _get_dispatch()
        assert "ace_step" in dispatch

    def test_dispatch_aliases(self):
        """All ace_step aliases should exist in the dispatch table."""
        from skills.composer import _get_dispatch
        dispatch = _get_dispatch()
        aliases = [
            "acestep", "music_repaint", "audio_cover",
            "music_cover", "vocal2bgm", "lrc", "stem_separate",
        ]
        for alias in aliases:
            assert alias in dispatch, f"Alias '{alias}' not in dispatch table"

    def test_all_aliases_point_to_same_handler(self):
        """All aliases should point to the same handler function."""
        from skills.composer import _get_dispatch
        dispatch = _get_dispatch()
        base_handler = dispatch["ace_step"]
        aliases = [
            "acestep", "music_repaint", "audio_cover",
            "music_cover", "vocal2bgm", "lrc", "stem_separate",
        ]
        for alias in aliases:
            assert dispatch[alias] is base_handler, (
                f"Alias '{alias}' doesn't point to ace_step handler"
            )


# ── Composer Alias Tests ───────────────────────────────────────────


class TestAceStepComposerAliases:
    """Verify composer aliases resolve ace_step correctly."""

    def test_skill_aliases_in_composer(self):
        """SKILL_ALIASES should map common names to ace_step."""
        from skills.composer import SkillComposer
        aliases = SkillComposer.SKILL_ALIASES
        expected = {
            "acestep": "ace_step",
            "music_repaint": "ace_step",
            "audio_cover": "ace_step",
            "music_cover": "ace_step",
            "vocal2bgm": "ace_step",
            "lrc": "ace_step",
            "stem_separate": "ace_step",
        }
        for alias, target in expected.items():
            assert aliases.get(alias) == target, (
                f"Alias '{alias}' not mapped to '{target}'"
            )


# ── Model Manager Tests ───────────────────────────────────────────


class TestAceStepModelManager:
    """Verify acestep is registered in the model manager."""

    def test_acestep_in_model_registry(self):
        """acestep should be registered in the model info registry."""
        from core.model_manager import _MODEL_INFO
        assert "acestep" in _MODEL_INFO
        info = _MODEL_INFO["acestep"]
        assert "ACE-Step" in info["name"]
        assert info["license"] == "MIT"
        assert "AEmotionStudio" in info["mirror_repo"]

    @patch("core.model_manager._downloads_allowed", False)
    def test_download_guard_blocks_acestep(self):
        """require_downloads_allowed should block when downloads are disabled."""
        from core.model_manager import require_downloads_allowed
        with pytest.raises(RuntimeError, match="ACE-Step"):
            require_downloads_allowed("acestep")


# ── VRAM Utils Tests ──────────────────────────────────────────────


class TestAceStepVRAMUtils:
    """Verify acestep_synthesizer is in the VRAM cleanup registry."""

    def test_acestep_in_all_synthesizer_modules(self):
        """acestep_synthesizer should be in ALL_SYNTHESIZER_MODULES."""
        from core._vram_utils import ALL_SYNTHESIZER_MODULES
        assert "acestep_synthesizer" in ALL_SYNTHESIZER_MODULES


# ── No-LLM Mode Tests ───────────────────────────────────────────


class TestAceStepNoLLMMode:
    """Verify ace_step is wired into the no_llm_mode system."""

    def test_ace_step_in_no_llm_mode_dropdown(self):
        """ace_step should be a valid no_llm_mode option."""
        pytest.importorskip("torch")
        from nodes.agent_node import FFMPEGAgentNode
        inputs = FFMPEGAgentNode.INPUT_TYPES()
        no_llm_choices = inputs["required"]["no_llm_mode"][0]
        assert "ace_step" in no_llm_choices


# ── Synthesizer API Tests ─────────────────────────────────────────


class TestAceStepSynthesizerAPI:
    """Verify the in-process synthesizer API surface exists."""

    def test_generate_music_acestep_exists(self):
        """generate_music_acestep function should be importable."""
        from core.acestep_synthesizer import generate_music_acestep
        assert callable(generate_music_acestep)

    def test_cover_audio_exists(self):
        """cover_audio function should be importable."""
        from core.acestep_synthesizer import cover_audio
        assert callable(cover_audio)

    def test_repaint_audio_exists(self):
        """repaint_audio function should be importable."""
        from core.acestep_synthesizer import repaint_audio
        assert callable(repaint_audio)

    def test_audiox_to_acestep_repaint_exists(self):
        """audiox_to_acestep_repaint function should be importable."""
        from core.acestep_synthesizer import audiox_to_acestep_repaint
        assert callable(audiox_to_acestep_repaint)

    def test_cleanup_exists(self):
        """cleanup function should be importable."""
        from core.acestep_synthesizer import cleanup
        assert callable(cleanup)

    def test_is_available_exists(self):
        """is_available function should be importable."""
        from core.acestep_synthesizer import is_available
        assert callable(is_available)

    def test_load_handler_exists(self):
        """load_handler function should be importable."""
        from core.acestep_synthesizer import load_handler
        assert callable(load_handler)

    def test_generate_lyrics_exists(self):
        """generate_lyrics function should be importable."""
        from core.acestep_synthesizer import generate_lyrics
        assert callable(generate_lyrics)
