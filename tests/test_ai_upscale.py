# coding: utf-8
"""Tests for AI Upscale (super-resolution) integration."""

import sys
import os
from unittest.mock import patch, MagicMock

import pytest

# Ensure project root is on sys.path
_proj = os.path.dirname(os.path.dirname(__file__))
if _proj not in sys.path:
    sys.path.insert(0, _proj)

from skills.registry import get_registry, SkillCategory

# PyTorch guard
try:
    import torch  # noqa: F401
    _has_torch = True
except (ImportError, RuntimeError):
    _has_torch = False



# ------------------------------------------------------------------ #
#  Skill registration
# ------------------------------------------------------------------ #

class TestAIUpscaleSkillRegistration:
    """Verify the ai_upscale skill is in the global registry."""

    def test_skill_exists_in_registry(self):
        registry = get_registry()
        skill = registry.get("ai_upscale")
        assert skill is not None

    def test_skill_category_is_ai_visual(self):
        registry = get_registry()
        skill = registry.get("ai_upscale")
        assert skill.category == SkillCategory.AI_VISUAL

    def test_skill_has_model_param(self):
        registry = get_registry()
        skill = registry.get("ai_upscale")
        params = {p.name: p for p in skill.parameters}
        assert "model" in params
        assert params["model"].default == "realesrgan_x4plus"

    def test_skill_model_choices(self):
        registry = get_registry()
        skill = registry.get("ai_upscale")
        params = {p.name: p for p in skill.parameters}
        choices = params["model"].choices
        expected = {
            "realesrgan_x4plus", "realesrgan_x4_anime",
            "hat_x4", "dat_x4", "swinir_x4",
            "seedvr2_3b_fp8", "seedvr2_7b_gguf",
        }
        assert set(choices) == expected

    def test_skill_has_scale_factor_param(self):
        registry = get_registry()
        skill = registry.get("ai_upscale")
        params = {p.name: p for p in skill.parameters}
        assert "scale_factor" in params
        assert params["scale_factor"].default == 4

    def test_skill_has_tile_size_param(self):
        registry = get_registry()
        skill = registry.get("ai_upscale")
        params = {p.name: p for p in skill.parameters}
        assert "tile_size" in params
        assert params["tile_size"].default == 512

    def test_skill_tags_include_key_terms(self):
        registry = get_registry()
        skill = registry.get("ai_upscale")
        for tag in ("upscale", "super_resolution", "esrgan", "hat", "ai", "seedvr2"):
            assert tag in skill.tags

    def test_skill_has_examples(self):
        registry = get_registry()
        skill = registry.get("ai_upscale")
        assert len(skill.examples) > 0


# ------------------------------------------------------------------ #
#  Handler
# ------------------------------------------------------------------ #

class TestAIUpscaleHandler:
    """Unit tests for the _f_ai_upscale handler."""

    def test_missing_input_returns_error(self):
        from skills.handlers.upscale import _f_ai_upscale
        result = _f_ai_upscale({"_input_path": "", "model": "realesrgan_x4plus"})
        assert "error" in result

    @patch("skills.handlers.upscale.os.path.isfile", return_value=True)
    def test_invalid_model_returns_error(self, mock_isfile):
        from skills.handlers.upscale import _f_ai_upscale
        result = _f_ai_upscale({
            "_input_path": "/tmp/test.mp4",
            "model": "invalid_model",
        })
        assert "error" in result
        assert "model" in result["error"].lower() or "invalid" in result["error"].lower()

    @patch("skills.handlers.upscale.os.path.isfile", return_value=True)
    def test_success_returns_movie_for_video(self, mock_isfile):
        from skills.handlers.upscale import _f_ai_upscale
        mock_upscaler = MagicMock()
        mock_upscaler.upscale_video = MagicMock(return_value="/tmp/out.mp4")
        mock_upscaler.upscale_image = MagicMock(return_value="/tmp/out.png")
        with patch.dict(sys.modules, {"core.upscaler": mock_upscaler}):
            result = _f_ai_upscale({
                "_input_path": "/tmp/test.mp4",
                "model": "realesrgan_x4plus",
            })
        assert "movie" in result
        assert result["movie"] == "/tmp/out.mp4"

    @patch("skills.handlers.upscale.os.path.isfile", return_value=True)
    def test_success_returns_image_for_png(self, mock_isfile):
        from skills.handlers.upscale import _f_ai_upscale
        mock_upscaler = MagicMock()
        mock_upscaler.upscale_image = MagicMock(return_value="/tmp/out.png")
        with patch.dict(sys.modules, {"core.upscaler": mock_upscaler}):
            result = _f_ai_upscale({
                "_input_path": "/tmp/test.png",
                "model": "realesrgan_x4plus",
            })
        assert "image" in result
        assert result["image"] == "/tmp/out.png"

    @patch("skills.handlers.upscale.os.path.isfile", return_value=True)
    def test_default_model_is_realesrgan(self, mock_isfile):
        from skills.handlers.upscale import _f_ai_upscale
        mock_upscaler = MagicMock()
        mock_upscaler.upscale_video = MagicMock(return_value="/tmp/out.mp4")
        with patch.dict(sys.modules, {"core.upscaler": mock_upscaler}):
            _f_ai_upscale({"_input_path": "/tmp/test.mp4"})
            mock_upscaler.upscale_video.assert_called_once()
            assert mock_upscaler.upscale_video.call_args[1]["model_name"] == "realesrgan_x4plus"


# ------------------------------------------------------------------ #
#  Dispatch table
# ------------------------------------------------------------------ #

class TestAIUpscaleDispatch:
    """Verify ai_upscale is in the dispatch table."""

    def test_ai_upscale_in_dispatch(self):
        from skills.composer import _get_dispatch
        dispatch = _get_dispatch()
        assert "ai_upscale" in dispatch

    def test_dispatch_aliases_point_to_same_handler(self):
        from skills.composer import _get_dispatch
        dispatch = _get_dispatch()
        handler = dispatch["ai_upscale"]
        for alias in (
            "super_resolution", "esrgan", "swinir",
            "hat_upscale", "ai_enhance", "upscale_ai", "sr",
        ):
            assert dispatch[alias] is handler


# ------------------------------------------------------------------ #
#  Aliases
# ------------------------------------------------------------------ #

class TestAIUpscaleAliases:
    """Verify SKILL_ALIASES resolve correctly."""

    def test_aliases_resolve_to_ai_upscale(self):
        from skills.composer import SkillComposer
        aliases = SkillComposer.SKILL_ALIASES
        for alias in (
            "super_resolution", "esrgan", "swinir",
            "hat_upscale", "ai_enhance", "upscale_ai", "sr",
        ):
            assert aliases[alias] == "ai_upscale"


# ------------------------------------------------------------------ #
#  Model manager
# ------------------------------------------------------------------ #

class TestAIUpscaleModelManager:
    """Verify model info for ai_upscale."""

    def test_model_info_exists(self):
        from core.model_manager import _MODEL_INFO
        assert "ai_upscale" in _MODEL_INFO

    def test_model_info_has_required_fields(self):
        from core.model_manager import _MODEL_INFO
        info = _MODEL_INFO["ai_upscale"]
        for field in ("name", "size", "url", "license", "manual"):
            assert field in info, f"Missing field: {field}"

    def test_model_info_name(self):
        from core.model_manager import _MODEL_INFO
        assert "Upscaler" in _MODEL_INFO["ai_upscale"]["name"]

    def test_mirror_repo_is_aemotionstudio(self):
        from core.model_manager import _MODEL_INFO
        assert "AEmotionStudio" in _MODEL_INFO["ai_upscale"]["mirror_repo"]

    def test_seedvr2_model_info_exists(self):
        from core.model_manager import _MODEL_INFO
        assert "seedvr2" in _MODEL_INFO

    def test_seedvr2_model_info_has_required_fields(self):
        from core.model_manager import _MODEL_INFO
        info = _MODEL_INFO["seedvr2"]
        for field in ("name", "size", "url", "license", "manual"):
            assert field in info, f"Missing field: {field}"


# ------------------------------------------------------------------ #
#  Module imports
# ------------------------------------------------------------------ #

@pytest.mark.skipif(not _has_torch, reason="PyTorch not available")
class TestAIUpscaleModuleImport:
    """Verify core modules can be imported."""

    def test_synthesizer_module_importable(self):
        from core import upscaler
        assert hasattr(upscaler, "upscale_image")
        assert hasattr(upscaler, "upscale_video")
        assert hasattr(upscaler, "cleanup")
        assert hasattr(upscaler, "MODEL_CONFIGS")

    def test_model_configs_complete(self):
        from core.upscaler import MODEL_CONFIGS
        expected_models = {
            "realesrgan_x4plus", "realesrgan_x4_anime",
            "hat_x4", "dat_x4", "swinir_x4",
        }
        assert set(MODEL_CONFIGS.keys()) == expected_models

    def test_model_configs_have_mirror_repos(self):
        from core.upscaler import MODEL_CONFIGS
        for model_name, cfg in MODEL_CONFIGS.items():
            assert "AEmotionStudio" in cfg["mirror_repo"], \
                f"{model_name} missing AEmotionStudio mirror"

    def test_model_configs_have_required_fields(self):
        from core.upscaler import MODEL_CONFIGS
        required = {"mirror_repo", "filename", "scale", "size"}
        for model_name, cfg in MODEL_CONFIGS.items():
            for field in required:
                assert field in cfg, f"{model_name} missing field: {field}"

    def test_handler_importable(self):
        from skills.handlers.upscale import _f_ai_upscale
        assert callable(_f_ai_upscale)


# ------------------------------------------------------------------ #
#  No-LLM mode
# ------------------------------------------------------------------ #

class TestAIUpscaleNoLLMMode:
    """Test the ai_upscale no_llm_mode integration."""

    def test_ai_upscale_in_no_llm_dropdown(self):
        """'ai_upscale' should be in the no_llm_mode dropdown choices."""
        pytest.importorskip("torch")
        from nodes.agent_node import FFMPEGAgentNode
        input_types = FFMPEGAgentNode.INPUT_TYPES()
        choices = input_types["required"]["no_llm_mode"][0]
        assert "ai_upscale" in choices

    def test_upscale_model_dropdown_exists(self):
        """upscale_model should be in optional INPUT_TYPES."""
        pytest.importorskip("torch")
        from nodes.agent_node import FFMPEGAgentNode
        input_types = FFMPEGAgentNode.INPUT_TYPES()
        optional = input_types.get("optional", {})
        assert "upscale_model" in optional
        models = optional["upscale_model"][0]
        assert "realesrgan_x4plus" in models
        assert "hat_x4" in models
        assert "seedvr2_3b_fp8" in models
        assert "seedvr2_7b_gguf" in models

    def test_upscale_scale_dropdown_exists(self):
        """upscale_scale should be in optional INPUT_TYPES."""
        pytest.importorskip("torch")
        from nodes.agent_node import FFMPEGAgentNode
        input_types = FFMPEGAgentNode.INPUT_TYPES()
        optional = input_types.get("optional", {})
        assert "upscale_scale" in optional

    def test_blockswap_blocks_widget_exists(self):
        """blockswap_blocks INT widget should be in optional INPUT_TYPES."""
        pytest.importorskip("torch")
        from nodes.agent_node import FFMPEGAgentNode
        input_types = FFMPEGAgentNode.INPUT_TYPES()
        optional = input_types.get("optional", {})
        assert "blockswap_blocks" in optional
        spec = optional["blockswap_blocks"]
        assert spec[0] == "INT"
        assert spec[1]["default"] == 0
        assert spec[1]["min"] == 0
        assert spec[1]["max"] == 32

    def test_process_ai_upscale_only_exists(self):
        """process_ai_upscale_only should be importable from nollm_modes."""
        pytest.importorskip("torch")
        from nodes.nollm_modes import process_ai_upscale_only
        assert callable(process_ai_upscale_only)

    @pytest.mark.skipif(not _has_torch, reason="PyTorch not available")
    def test_cleanup_exists(self):
        """cleanup() should be importable from upscaler."""
        from core.upscaler import cleanup
        assert callable(cleanup)

    @pytest.mark.skipif(not _has_torch, reason="PyTorch not available")
    def test_cleanup_when_no_model(self):
        """cleanup() should not error when no model is loaded."""
        import core.upscaler as up
        up._model = None
        up.cleanup()  # Should not raise
        assert up._model is None


# ------------------------------------------------------------------ #
#  SeedVR2 synthesizer
# ------------------------------------------------------------------ #

@pytest.mark.skipif(not _has_torch, reason="PyTorch not available")
class TestSeedVR2Synthesizer:
    """Verify the SeedVR2 synthesizer module."""

    def test_seedvr_synthesizer_importable(self):
        from core import seedvr_synthesizer
        assert hasattr(seedvr_synthesizer, "upscale_image")
        assert hasattr(seedvr_synthesizer, "upscale_video")
        assert hasattr(seedvr_synthesizer, "cleanup")
        assert hasattr(seedvr_synthesizer, "SEEDVR_CONFIGS")

    def test_seedvr_configs_complete(self):
        from core.seedvr_synthesizer import SEEDVR_CONFIGS
        assert "seedvr2_3b_fp8" in SEEDVR_CONFIGS
        assert "seedvr2_7b_gguf" in SEEDVR_CONFIGS

    def test_seedvr_configs_have_required_fields(self):
        from core.seedvr_synthesizer import SEEDVR_CONFIGS
        required = {"description", "dit_model", "vae_model", "size"}
        for name, cfg in SEEDVR_CONFIGS.items():
            for field in required:
                assert field in cfg, f"{name} missing field: {field}"

    def test_seedvr_in_vram_utils(self):
        from core._vram_utils import ALL_SYNTHESIZER_MODULES
        assert "seedvr_synthesizer" in ALL_SYNTHESIZER_MODULES

    def test_seedvr_handler_accepts_seedvr2_models(self):
        from skills.handlers.upscale import _VALID_MODELS, _SEEDVR_MODELS
        assert "seedvr2_3b_fp8" in _VALID_MODELS
        assert "seedvr2_7b_gguf" in _VALID_MODELS
        assert "seedvr2_3b_fp8" in _SEEDVR_MODELS
        assert "seedvr2_7b_gguf" in _SEEDVR_MODELS

    def test_cleanup_when_no_model(self):
        """cleanup() should not error when no model is loaded."""
        import core.seedvr_synthesizer as svr
        svr._runner = None
        svr.cleanup()  # Should not raise
        assert svr._runner is None
