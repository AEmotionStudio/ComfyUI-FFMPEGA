"""Tests for the generate_music skill (AudioX integration).

Covers skill registration, handler unit tests (with AudioX mocked),
dispatch table wiring, and alias resolution.
"""

import pytest
from unittest.mock import patch

from skills.handler_contract import HandlerResult
from skills.registry import get_registry, SkillCategory


# ── Skill Registration ─────────────────────────────────────────────


class TestGenerateMusicSkillRegistration:
    """Verify generate_music is registered correctly in the skill registry."""

    def test_skill_exists_in_registry(self):
        """generate_music should be registered in the global registry."""
        registry = get_registry()
        skill = registry.get("generate_music")
        assert skill is not None
        assert skill.name == "generate_music"

    def test_skill_category_is_audio(self):
        """generate_music should be in the AUDIO category."""
        registry = get_registry()
        skill = registry.get("generate_music")
        assert skill.category == SkillCategory.AUDIO

    def test_skill_has_prompt_param(self):
        """generate_music should have a 'prompt' parameter."""
        registry = get_registry()
        skill = registry.get("generate_music")
        param = skill.get_param("prompt")
        assert param is not None
        assert param.default == ""

    def test_skill_has_mode_param(self):
        """generate_music should have a 'mode' parameter with replace/mix choices."""
        registry = get_registry()
        skill = registry.get("generate_music")
        param = skill.get_param("mode")
        assert param is not None
        assert param.default == "replace"
        assert set(param.choices) == {"replace", "mix"}

    def test_skill_has_negative_prompt_param(self):
        """generate_music should have a 'negative_prompt' parameter."""
        registry = get_registry()
        skill = registry.get("generate_music")
        param = skill.get_param("negative_prompt")
        assert param is not None
        assert param.default == ""

    def test_skill_has_seed_param(self):
        """generate_music should have a 'seed' parameter."""
        registry = get_registry()
        skill = registry.get("generate_music")
        param = skill.get_param("seed")
        assert param is not None
        assert param.default == -1
        assert param.min_value == -1

    def test_skill_has_cfg_scale_param(self):
        """generate_music should have a 'cfg_scale' parameter."""
        registry = get_registry()
        skill = registry.get("generate_music")
        param = skill.get_param("cfg_scale")
        assert param is not None
        assert param.default == 7.0

    def test_skill_has_duration_param(self):
        """generate_music should have a 'duration' parameter."""
        registry = get_registry()
        skill = registry.get("generate_music")
        param = skill.get_param("duration")
        assert param is not None
        assert param.max_value == 10.0

    def test_skill_has_steps_param(self):
        """generate_music should have a 'steps' parameter."""
        registry = get_registry()
        skill = registry.get("generate_music")
        param = skill.get_param("steps")
        assert param is not None
        assert param.default == 250

    def test_skill_has_tags(self):
        """generate_music should have relevant search tags."""
        registry = get_registry()
        skill = registry.get("generate_music")
        assert "music" in skill.tags
        assert "audiox" in skill.tags
        assert "soundtrack" in skill.tags

    def test_skill_searchable_by_keywords(self):
        """generate_music should be findable by searching relevant keywords."""
        registry = get_registry()
        for keyword in ["music", "soundtrack", "audiox", "compose", "bgm"]:
            results = registry.search(keyword)
            names = [s.name for s in results]
            assert "generate_music" in names, f"Not found for keyword: {keyword}"


# ── Handler Unit Tests ─────────────────────────────────────────────


class TestGenerateMusicHandler:
    """Test the _f_generate_music handler function with mocked AudioX."""

    def test_handler_returns_handler_result(self):
        """Handler should return a HandlerResult even when AudioX is unavailable."""
        from skills.handlers.generate_music import _f_generate_music
        result = _f_generate_music({})
        assert isinstance(result, HandlerResult)

    def test_fallback_when_no_audiox(self):
        """When AudioX is not installed, handler should return empty result gracefully."""
        from skills.handlers.generate_music import _f_generate_music
        metadata = {}
        result = _f_generate_music({
            "prompt": "test",
            "_input_path": "/fake/video.mp4",
            "_metadata_ref": metadata,
        })
        assert isinstance(result, HandlerResult)
        # Should mark as degraded when AudioX not available
        assert metadata.get("_skill_degraded") is True

    def test_no_video_no_prompt_returns_empty(self):
        """With no video and no prompt, handler returns empty result."""
        from skills.handlers.generate_music import _f_generate_music

        with patch("skills.handlers.generate_music.log"):
            result = _f_generate_music({
                "_input_path": "",
                "prompt": "",
            })
            assert isinstance(result, HandlerResult)

    @patch("core.audiox_synthesizer.generate_music")
    def test_replace_mode(self, mock_synth):
        """mode=replace should produce filter_complex with amovie source."""
        mock_synth.return_value = "/tmp/test_music.wav"

        with patch("os.path.isfile", return_value=True):
            from skills.handlers.generate_music import _f_generate_music
            result = _f_generate_music({
                "prompt": "epic orchestral",
                "mode": "replace",
                "_input_path": "/fake/video.mp4",
                "_metadata_ref": {},
            })
        assert isinstance(result, HandlerResult)
        if result.filter_complex:
            assert "amovie" in result.filter_complex

    @patch("core.audiox_synthesizer.generate_music")
    def test_mix_mode_with_audio(self, mock_synth):
        """mode=mix with embedded audio should use amix in filter_complex."""
        mock_synth.return_value = "/tmp/test_music.wav"

        with patch("os.path.isfile", return_value=True):
            from skills.handlers.generate_music import _f_generate_music
            result = _f_generate_music({
                "prompt": "calm piano",
                "mode": "mix",
                "_input_path": "/fake/video.mp4",
                "_has_embedded_audio": True,
                "_metadata_ref": {},
            })
        assert isinstance(result, HandlerResult)
        if result.filter_complex:
            assert "amix" in result.filter_complex


# ── Dispatch Table Tests ───────────────────────────────────────────


class TestGenerateMusicDispatch:
    """Verify generate_music is wired into the dispatch table."""

    def test_dispatch_table_has_generate_music(self):
        """generate_music should be in the dispatch table."""
        from skills.composer import _get_dispatch
        dispatch = _get_dispatch()
        assert "generate_music" in dispatch

    def test_dispatch_aliases(self):
        """All generate_music aliases should exist in the dispatch table."""
        from skills.composer import _get_dispatch
        dispatch = _get_dispatch()
        aliases = [
            "music", "score", "soundtrack", "bgm",
            "video_to_music", "v2m", "compose_music",
            "text_to_music", "t2m", "audiox",
        ]
        for alias in aliases:
            assert alias in dispatch, f"Alias '{alias}' not in dispatch table"

    def test_all_aliases_point_to_same_handler(self):
        """All aliases should point to the same handler function."""
        from skills.composer import _get_dispatch
        dispatch = _get_dispatch()
        base_handler = dispatch["generate_music"]
        aliases = [
            "music", "score", "soundtrack", "bgm",
            "video_to_music", "v2m", "audiox",
        ]
        for alias in aliases:
            assert dispatch[alias] is base_handler, (
                f"Alias '{alias}' doesn't point to generate_music handler"
            )


# ── Composer Alias Tests ───────────────────────────────────────────


class TestGenerateMusicComposerAliases:
    """Verify composer aliases resolve generate_music correctly."""

    def test_skill_aliases_in_composer(self):
        """SKILL_ALIASES should map common names to generate_music."""
        from skills.composer import SkillComposer
        aliases = SkillComposer.SKILL_ALIASES
        expected = {
            "music": "generate_music",
            "score": "generate_music",
            "soundtrack": "generate_music",
            "bgm": "generate_music",
            "video_to_music": "generate_music",
            "v2m": "generate_music",
            "compose_music": "generate_music",
            "text_to_music": "generate_music",
            "t2m": "generate_music",
            "audiox": "generate_music",
        }
        for alias, target in expected.items():
            assert aliases.get(alias) == target, (
                f"Alias '{alias}' not mapped to '{target}'"
            )


# ── Model Manager Tests ───────────────────────────────────────────


class TestAudioXModelManager:
    """Verify audiox is registered in the model manager."""

    def test_audiox_in_model_registry(self):
        """audiox should be registered in the model info registry."""
        from core.model_manager import _MODEL_INFO
        assert "audiox" in _MODEL_INFO
        info = _MODEL_INFO["audiox"]
        assert "AudioX" in info["name"]
        assert info["mirror_repo"] == "AEmotionStudio/audiox-models"

    @patch("core.model_manager._downloads_allowed", False)
    def test_download_guard_blocks_audiox(self):
        """require_downloads_allowed should block when downloads are disabled."""
        from core.model_manager import require_downloads_allowed
        with pytest.raises(RuntimeError, match="AudioX"):
            require_downloads_allowed("audiox")


# ── No-LLM Mode Tests ───────────────────────────────────────────


class TestGenerateMusicNoLLMMode:
    """Verify generate_music is wired into the no_llm_mode system."""

    def test_generate_music_in_no_llm_mode_dropdown(self):
        """generate_music should be a valid no_llm_mode option."""
        pytest.importorskip("torch")
        from nodes.agent_node import FFMPEGAgentNode
        inputs = FFMPEGAgentNode.INPUT_TYPES()
        no_llm_choices = inputs["required"]["no_llm_mode"][0]
        assert "generate_music (AudioX)" in no_llm_choices


# ── In-Process Model API Tests ─────────────────────────────────────


class TestAudioXModelCaching:
    """Verify the in-process model caching API exists."""

    def test_load_models_exists(self):
        """load_models function should be importable."""
        from core.audiox_synthesizer import load_models
        assert callable(load_models)

    def test_cleanup_exists(self):
        """cleanup function should be importable."""
        from core.audiox_synthesizer import cleanup
        assert callable(cleanup)

    def test_generate_music_exists(self):
        """generate_music function should be importable."""
        from core.audiox_synthesizer import generate_music
        assert callable(generate_music)

    def test_inpaint_audio_exists(self):
        """inpaint_audio function should be importable."""
        from core.audiox_synthesizer import inpaint_audio
        assert callable(inpaint_audio)

    def test_generate_audio_audiox_exists(self):
        """generate_audio_audiox function should be importable."""
        from core.audiox_synthesizer import generate_audio_audiox
        assert callable(generate_audio_audiox)
