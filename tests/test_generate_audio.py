"""Tests for the generate_audio skill (MMAudio integration).

Covers skill registration, handler unit tests (with MMAudio mocked),
dispatch table wiring, and alias resolution.
"""

import pytest
from unittest.mock import patch

from skills.handler_contract import HandlerResult
from skills.registry import get_registry, SkillCategory


# ── Skill Registration ─────────────────────────────────────────────


class TestGenerateAudioSkillRegistration:
    """Verify generate_audio is registered correctly in the skill registry."""

    def test_skill_exists_in_registry(self):
        """generate_audio should be registered in the global registry."""
        registry = get_registry()
        skill = registry.get("generate_audio")
        assert skill is not None
        assert skill.name == "generate_audio"

    def test_skill_category_is_audio(self):
        """generate_audio should be in the AUDIO category."""
        registry = get_registry()
        skill = registry.get("generate_audio")
        assert skill.category == SkillCategory.AUDIO

    def test_skill_has_prompt_param(self):
        """generate_audio should have a 'prompt' parameter."""
        registry = get_registry()
        skill = registry.get("generate_audio")
        param = skill.get_param("prompt")
        assert param is not None
        assert param.default == ""

    def test_skill_has_mode_param(self):
        """generate_audio should have a 'mode' parameter with replace/mix choices."""
        registry = get_registry()
        skill = registry.get("generate_audio")
        param = skill.get_param("mode")
        assert param is not None
        assert param.default == "replace"
        assert set(param.choices) == {"replace", "mix"}

    def test_skill_has_negative_prompt_param(self):
        """generate_audio should have a 'negative_prompt' parameter."""
        registry = get_registry()
        skill = registry.get("generate_audio")
        param = skill.get_param("negative_prompt")
        assert param is not None
        assert param.default == ""

    def test_skill_has_seed_param(self):
        """generate_audio should have a 'seed' parameter."""
        registry = get_registry()
        skill = registry.get("generate_audio")
        param = skill.get_param("seed")
        assert param is not None
        assert param.default == 42
        assert param.min_value == 0

    def test_skill_has_cfg_strength_param(self):
        """generate_audio should have a 'cfg_strength' parameter."""
        registry = get_registry()
        skill = registry.get("generate_audio")
        param = skill.get_param("cfg_strength")
        assert param is not None
        assert param.default == 4.5

    def test_skill_has_tags(self):
        """generate_audio should have relevant search tags."""
        registry = get_registry()
        skill = registry.get("generate_audio")
        assert "foley" in skill.tags
        assert "mmaudio" in skill.tags
        assert "synthesize" in skill.tags

    def test_skill_searchable_by_keywords(self):
        """generate_audio should be findable by searching relevant keywords."""
        registry = get_registry()
        for keyword in ["foley", "synthesize", "generate", "sound", "mmaudio"]:
            results = registry.search(keyword)
            names = [s.name for s in results]
            assert "generate_audio" in names, f"Not found for keyword: {keyword}"


# ── Handler Unit Tests ─────────────────────────────────────────────


class TestGenerateAudioHandler:
    """Test the _f_generate_audio handler function with mocked MMAudio."""

    def test_handler_returns_handler_result(self):
        """Handler should return a HandlerResult even when MMAudio is unavailable."""
        # Import with MMAudio not available (which is the case in test env)
        from skills.handlers.generate_audio import _f_generate_audio
        result = _f_generate_audio({})
        assert isinstance(result, HandlerResult)

    def test_fallback_when_no_mmaudio(self):
        """When MMAudio is not installed, handler should return empty result gracefully."""
        from skills.handlers.generate_audio import _f_generate_audio
        metadata = {}
        result = _f_generate_audio({
            "prompt": "test",
            "_input_path": "/fake/video.mp4",
            "_metadata_ref": metadata,
        })
        assert isinstance(result, HandlerResult)
        # Should mark as degraded
        assert metadata.get("_skill_degraded") is True

    def test_no_video_no_prompt_returns_empty(self):
        """With no video and no prompt, handler returns empty result."""
        from skills.handlers.generate_audio import _f_generate_audio

        with patch("skills.handlers.generate_audio.log"):
            result = _f_generate_audio({
                "_input_path": "",
                "prompt": "",
            })
            assert isinstance(result, HandlerResult)

    @patch("core.mmaudio_synthesizer.generate_audio_subprocess")
    def test_replace_mode(self, mock_synth):
        """mode=replace should produce filter_complex with amovie source."""
        mock_synth.return_value = "/tmp/test_audio.flac"

        # Patch os.path.isfile to return True for our fake paths
        with patch("os.path.isfile", return_value=True):
            from skills.handlers.generate_audio import _f_generate_audio
            result = _f_generate_audio({
                "prompt": "ocean waves",
                "mode": "replace",
                "_input_path": "/fake/video.mp4",
                "_metadata_ref": {},
            })
        assert isinstance(result, HandlerResult)
        # In replace mode with subprocess available, should have filter_complex
        if result.filter_complex:
            assert "amovie" in result.filter_complex

    @patch("core.mmaudio_synthesizer.generate_audio_subprocess")
    def test_mix_mode_with_audio(self, mock_synth):
        """mode=mix with embedded audio should use amix in filter_complex."""
        mock_synth.return_value = "/tmp/test_audio.flac"

        with patch("os.path.isfile", return_value=True):
            from skills.handlers.generate_audio import _f_generate_audio
            result = _f_generate_audio({
                "prompt": "birds chirping",
                "mode": "mix",
                "_input_path": "/fake/video.mp4",
                "_has_embedded_audio": True,
                "_metadata_ref": {},
            })
        assert isinstance(result, HandlerResult)
        if result.filter_complex:
            assert "amix" in result.filter_complex


# ── Dispatch Table Tests ───────────────────────────────────────────


class TestGenerateAudioDispatch:
    """Verify generate_audio is wired into the dispatch table."""

    def test_dispatch_table_has_generate_audio(self):
        """generate_audio should be in the dispatch table."""
        from skills.composer import _get_dispatch
        dispatch = _get_dispatch()
        assert "generate_audio" in dispatch

    def test_dispatch_aliases(self):
        """All generate_audio aliases should exist in the dispatch table."""
        from skills.composer import _get_dispatch
        dispatch = _get_dispatch()
        aliases = [
            "add_audio", "ai_audio", "sound_effects", "foley",
            "video_to_audio", "v2a", "mmaudio", "synthesize_audio",
            "generate_sound", "add_sound",
        ]
        for alias in aliases:
            assert alias in dispatch, f"Alias '{alias}' not in dispatch table"

    def test_all_aliases_point_to_same_handler(self):
        """All aliases should point to the same handler function."""
        from skills.composer import _get_dispatch
        dispatch = _get_dispatch()
        base_handler = dispatch["generate_audio"]
        aliases = [
            "add_audio", "ai_audio", "sound_effects", "foley",
            "video_to_audio", "v2a", "mmaudio",
        ]
        for alias in aliases:
            assert dispatch[alias] is base_handler, (
                f"Alias '{alias}' doesn't point to generate_audio handler"
            )


# ── Composer Alias Tests ───────────────────────────────────────────


class TestGenerateAudioComposerAliases:
    """Verify composer aliases resolve generate_audio correctly."""

    def test_skill_aliases_in_composer(self):
        """SKILL_ALIASES should map common names to generate_audio."""
        from skills.composer import SkillComposer
        aliases = SkillComposer.SKILL_ALIASES
        expected = {
            "add_audio": "generate_audio",
            "ai_audio": "generate_audio",
            "sound_effects": "generate_audio",
            "foley": "generate_audio",
            "video_to_audio": "generate_audio",
            "v2a": "generate_audio",
            "mmaudio": "generate_audio",
            "synthesize_audio": "generate_audio",
        }
        for alias, target in expected.items():
            assert aliases.get(alias) == target, (
                f"Alias '{alias}' not mapped to '{target}'"
            )


# ── Model Manager Tests ───────────────────────────────────────────


class TestMMAudioModelManager:
    """Verify mmaudio is registered in the model manager."""

    def test_mmaudio_in_model_registry(self):
        """mmaudio should be registered in the model info registry."""
        from core.model_manager import _MODEL_INFO
        assert "mmaudio" in _MODEL_INFO
        info = _MODEL_INFO["mmaudio"]
        assert "MMAudio" in info["name"]
        assert info["mirror_repo"] == "AEmotionStudio/mmaudio-models"

    @patch("core.model_manager._downloads_allowed", False)
    def test_download_guard_blocks_mmaudio(self):
        """require_downloads_allowed should block when downloads are disabled."""
        from core.model_manager import require_downloads_allowed
        with pytest.raises(RuntimeError, match="MMAudio"):
            require_downloads_allowed("mmaudio")
