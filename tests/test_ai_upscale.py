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
            "seedvr2_3b_int8", "seedvr2_7b_int8",
            "seedvr2_3b_fp8", "seedvr2_3b_gguf",
            "seedvr2_7b_fp8", "seedvr2_7b_fp8_mixed", "seedvr2_7b_gguf",
            "flashvsr_full", "flashvsr_tiny", "flashvsr_tiny_long",
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
        assert spec[1]["min"] == -1  # -1 = auto budget (DiffSynth num_persistent_param_in_dit)
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


# ------------------------------------------------------------------ #
#  FlashVSR synthesizer
# ------------------------------------------------------------------ #

@pytest.mark.skipif(not _has_torch, reason="PyTorch not available")
class TestFlashVSRSynthesizer:
    """Verify the FlashVSR synthesizer module."""

    def test_flashvsr_synthesizer_importable(self):
        from core import flashvsr_synthesizer
        assert hasattr(flashvsr_synthesizer, "upscale_image")
        assert hasattr(flashvsr_synthesizer, "upscale_video")
        assert hasattr(flashvsr_synthesizer, "cleanup")
        assert hasattr(flashvsr_synthesizer, "FLASHVSR_CONFIGS")

    def test_flashvsr_configs_complete(self):
        from core.flashvsr_synthesizer import FLASHVSR_CONFIGS
        assert "flashvsr_full" in FLASHVSR_CONFIGS
        assert "flashvsr_tiny" in FLASHVSR_CONFIGS
        assert "flashvsr_tiny_long" in FLASHVSR_CONFIGS

    def test_flashvsr_configs_have_required_fields(self):
        from core.flashvsr_synthesizer import FLASHVSR_CONFIGS
        required = {"description", "mode", "sparse_ratio", "kv_ratio", "local_range", "size"}
        for name, cfg in FLASHVSR_CONFIGS.items():
            for field in required:
                assert field in cfg, f"{name} missing field: {field}"

    def test_flashvsr_in_vram_utils(self):
        from core._vram_utils import ALL_SYNTHESIZER_MODULES
        assert "flashvsr_synthesizer" in ALL_SYNTHESIZER_MODULES

    def test_flashvsr_handler_accepts_flashvsr_models(self):
        from skills.handlers.upscale import _VALID_MODELS, _FLASHVSR_MODELS
        assert "flashvsr_full" in _VALID_MODELS
        assert "flashvsr_tiny" in _VALID_MODELS
        assert "flashvsr_tiny_long" in _VALID_MODELS
        assert "flashvsr_full" in _FLASHVSR_MODELS

    def test_flashvsr_in_model_manager(self):
        from core.model_manager import _MODEL_INFO
        assert "flashvsr" in _MODEL_INFO
        info = _MODEL_INFO["flashvsr"]
        assert "name" in info
        assert "size" in info
        assert "url" in info

    def test_cleanup_when_no_pipeline(self):
        """cleanup() should not error when no pipeline is loaded."""
        import core.flashvsr_synthesizer as fvsr
        fvsr._pipeline = None
        fvsr.cleanup()  # Should not raise
        assert fvsr._pipeline is None


class TestSeedVR2Int8ConvRot:
    """INT8 ConvRot variants (ComfyUI's int8_tensorwise layout + block-Hadamard rotation)."""

    INT8_MODELS = ("seedvr2_3b_int8", "seedvr2_7b_int8")

    def test_int8_variants_in_seedvr_configs(self):
        from core.seedvr_synthesizer import SEEDVR_CONFIGS
        for name in self.INT8_MODELS:
            assert name in SEEDVR_CONFIGS
            assert SEEDVR_CONFIGS[name]["dit_model"].endswith("_int8_convrot.safetensors")

    def test_int8_variants_in_every_enum(self):
        """All four model lists must agree, or a variant is selectable but rejected."""
        pytest.importorskip("torch")
        from nodes.agent_node import FFMPEGAgentNode
        from nodes.nollm_modes import process_ai_upscale_only  # noqa: F401
        from skills.handlers.upscale import _VALID_MODELS, _SEEDVR_MODELS
        from skills.registry import get_registry

        node_models = FFMPEGAgentNode.INPUT_TYPES()["optional"]["upscale_model"][0]
        skill_choices = {
            p.name: p for p in get_registry().get("ai_upscale").parameters
        }["model"].choices

        for name in self.INT8_MODELS:
            assert name in node_models, f"{name} missing from agent_node dropdown"
            assert name in skill_choices, f"{name} missing from ai_upscale skill choices"
            assert name in _SEEDVR_MODELS, f"{name} missing from handler _SEEDVR_MODELS"
            assert name in _VALID_MODELS, f"{name} missing from handler _VALID_MODELS"

    def test_fp8_mixed_parity_across_enums(self):
        """seedvr2_7b_fp8_mixed was previously missing from the skill layer."""
        from skills.handlers.upscale import _VALID_MODELS, _SEEDVR_MODELS
        from skills.registry import get_registry

        skill_choices = {
            p.name: p for p in get_registry().get("ai_upscale").parameters
        }["model"].choices
        assert "seedvr2_7b_fp8_mixed" in _SEEDVR_MODELS
        assert "seedvr2_7b_fp8_mixed" in _VALID_MODELS
        assert "seedvr2_7b_fp8_mixed" in skill_choices

    def test_int8_models_registered_local_only(self):
        from core.seedvr.utils.model_registry import MODEL_REGISTRY
        from core.seedvr_synthesizer import SEEDVR_CONFIGS

        for name in self.INT8_MODELS:
            filename = SEEDVR_CONFIGS[name]["dit_model"]
            assert filename in MODEL_REGISTRY
            info = MODEL_REGISTRY[filename]
            assert info.local_only is True
            assert info.precision == "int8_convrot"

    def test_diffusion_models_folder_is_searched(self):
        """int8 checkpoints live in diffusion_models/, not SEEDVR2/."""
        pytest.importorskip("folder_paths")
        from core.seedvr.utils.constants import get_all_model_paths
        paths = [os.path.normpath(p).lower() for p in get_all_model_paths()]
        assert any(p.endswith("seedvr2") for p in paths)
        assert any(p.endswith("diffusion_models") for p in paths)

    def test_shared_folder_discovery_filters_by_name(self, tmp_path, monkeypatch):
        """diffusion_models also holds unrelated checkpoints; they must not be offered."""
        from core.seedvr.utils import constants

        seedvr_dir = tmp_path / "SEEDVR2"
        shared_dir = tmp_path / "diffusion_models"
        seedvr_dir.mkdir()
        shared_dir.mkdir()

        (seedvr_dir / "ema_vae_fp16.safetensors").touch()
        (shared_dir / "seedvr2_3b_int8_convrot.safetensors").touch()
        (shared_dir / "Wan2_2-T2V-A14B-LOW_fp8.safetensors").touch()
        (shared_dir / "krea2_turbo_fp8.safetensors").touch()
        (shared_dir / "seedvr2_notes.txt").touch()

        monkeypatch.setattr(constants, "get_seedvr2_model_paths", lambda: [str(seedvr_dir)])
        monkeypatch.setattr(constants, "get_shared_dit_paths", lambda: [str(shared_dir)])

        found = constants.get_all_model_files()
        assert set(found) == {
            "ema_vae_fp16.safetensors",
            "seedvr2_3b_int8_convrot.safetensors",
        }

    def test_seedvr2_folder_wins_on_duplicate_filename(self, tmp_path, monkeypatch):
        """The dedicated folder is searched first, so it takes priority."""
        from core.seedvr.utils import constants

        seedvr_dir = tmp_path / "SEEDVR2"
        shared_dir = tmp_path / "diffusion_models"
        seedvr_dir.mkdir()
        shared_dir.mkdir()
        (seedvr_dir / "seedvr2_3b_int8_convrot.safetensors").touch()
        (shared_dir / "seedvr2_3b_int8_convrot.safetensors").touch()

        monkeypatch.setattr(constants, "get_seedvr2_model_paths", lambda: [str(seedvr_dir)])
        monkeypatch.setattr(constants, "get_shared_dit_paths", lambda: [str(shared_dir)])

        resolved = constants.get_all_model_files()["seedvr2_3b_int8_convrot.safetensors"]
        assert resolved == str(seedvr_dir / "seedvr2_3b_int8_convrot.safetensors")

    def test_parse_comfy_quant_decodes_tag(self):
        torch = pytest.importorskip("torch")
        import json
        from core.seedvr.optimization.int8_ops import parse_comfy_quant

        payload = json.dumps(
            {"format": "int8_tensorwise", "convrot": True, "convrot_groupsize": 256}
        ).encode()
        state = {
            "blocks.0.mlp.vid.proj_in.comfy_quant": torch.tensor(
                list(payload), dtype=torch.uint8
            ),
            "blocks.0.mlp.vid.proj_in.weight": torch.zeros(4, 4, dtype=torch.int8),
        }
        quant_map = parse_comfy_quant(state)
        assert list(quant_map) == ["blocks.0.mlp.vid.proj_in"]
        assert quant_map["blocks.0.mlp.vid.proj_in"]["convrot_groupsize"] == 256

    def test_parse_comfy_quant_rejects_unknown_format(self):
        torch = pytest.importorskip("torch")
        import json
        from core.seedvr.optimization.int8_ops import parse_comfy_quant

        payload = json.dumps({"format": "nvfp4"}).encode()
        state = {"x.comfy_quant": torch.tensor(list(payload), dtype=torch.uint8)}
        with pytest.raises(ValueError, match="nvfp4"):
            parse_comfy_quant(state)

    def test_strip_quant_metadata_removes_only_tags(self):
        torch = pytest.importorskip("torch")
        from core.seedvr.optimization.int8_ops import strip_quant_metadata

        state = {
            "a.comfy_quant": torch.zeros(4, dtype=torch.uint8),
            "a.weight": torch.zeros(2, 2, dtype=torch.int8),
            "a.weight_scale": torch.zeros(2, 1),
        }
        assert strip_quant_metadata(state) == 1
        assert set(state) == {"a.weight", "a.weight_scale"}

    def test_convert_state_preserves_int8_and_scales(self):
        torch = pytest.importorskip("torch")
        from core.seedvr.optimization.int8_ops import convert_state_to_compute_dtype

        state = {
            "a.weight": torch.zeros(2, 2, dtype=torch.int8),
            "a.weight_scale": torch.zeros(2, 1, dtype=torch.float32),
            "a.bias": torch.zeros(2, dtype=torch.float16),
        }
        converted = convert_state_to_compute_dtype(state, torch.bfloat16)
        assert converted == 1
        assert state["a.weight"].dtype == torch.int8
        assert state["a.weight_scale"].dtype == torch.float32
        assert state["a.bias"].dtype == torch.bfloat16

    def test_replace_linear_and_load_state_dict(self):
        """The BlockSwap contract: buffers load by name and survive .to() moves."""
        torch = pytest.importorskip("torch")
        import json
        import torch.nn as nn
        from core.seedvr.optimization.int8_ops import (
            Int8ConvRotLinear,
            parse_comfy_quant,
            replace_linear_with_int8,
            strip_quant_metadata,
        )

        class Toy(nn.Module):
            def __init__(self):
                super().__init__()
                self.with_bias = nn.Linear(512, 256, bias=True)
                self.no_bias = nn.Linear(512, 256, bias=False)

        with torch.device("meta"):
            model = Toy()

        payload = json.dumps(
            {"format": "int8_tensorwise", "convrot": True, "convrot_groupsize": 256}
        ).encode()
        tag = torch.tensor(list(payload), dtype=torch.uint8)
        state = {
            "with_bias.weight": torch.zeros(256, 512, dtype=torch.int8),
            "with_bias.weight_scale": torch.ones(256, 1, dtype=torch.float32),
            "with_bias.bias": torch.zeros(256, dtype=torch.bfloat16),
            "with_bias.comfy_quant": tag.clone(),
            "no_bias.weight": torch.zeros(256, 512, dtype=torch.int8),
            "no_bias.weight_scale": torch.ones(256, 1, dtype=torch.float32),
            "no_bias.comfy_quant": tag.clone(),
        }

        replacements, groups = replace_linear_with_int8(model, parse_comfy_quant(state))
        strip_quant_metadata(state)
        assert replacements == 2
        assert groups == {"convrot256": 2}
        assert isinstance(model.with_bias, Int8ConvRotLinear)

        result = model.load_state_dict(state, strict=False, assign=True)
        assert result.missing_keys == []
        assert result.unexpected_keys == []
        assert model.with_bias.weight.dtype == torch.int8
        assert model.with_bias.weight_scale.dtype == torch.float32
        assert model.no_bias.bias is None

        # BlockSwap moves whole blocks with .to(); int8 must survive the round-trip.
        model.to("cpu")
        assert model.with_bias.weight.dtype == torch.int8
        assert model.with_bias.weight.device.type == "cpu"

    def test_replace_rejects_missing_module(self):
        torch = pytest.importorskip("torch")
        import torch.nn as nn
        from core.seedvr.optimization.int8_ops import replace_linear_with_int8

        with torch.device("meta"):
            model = nn.Module()
        with pytest.raises(ValueError, match="does not exist"):
            replace_linear_with_int8(model, {"nope": {"convrot": True}})


class TestDownloadGateChecksDiskFirst:
    """allow_model_downloads gates downloading, not using what is already there.

    The SeedVR2 loader called require_downloads_allowed() unconditionally at the
    top, so users with every weight on disk but the toggle off were refused a
    download they did not need.
    """

    def test_present_files_need_no_permission(self, tmp_path):
        from core import model_manager as mm

        weight = tmp_path / "present.safetensors"
        weight.write_bytes(b"x")
        original = mm._downloads_allowed
        try:
            mm._downloads_allowed = False
            assert mm.require_downloads_allowed_for_missing(
                "seedvr2", [str(weight)]
            ) == []
        finally:
            mm._downloads_allowed = original

    def test_absent_file_still_blocks(self, tmp_path):
        from core import model_manager as mm

        original = mm._downloads_allowed
        try:
            mm._downloads_allowed = False
            with pytest.raises(RuntimeError, match="allow_model_downloads"):
                mm.require_downloads_allowed_for_missing(
                    "seedvr2", [str(tmp_path / "absent.safetensors")]
                )
        finally:
            mm._downloads_allowed = original

    def test_absent_file_is_reported_when_downloads_allowed(self, tmp_path):
        from core import model_manager as mm

        present = tmp_path / "present.safetensors"
        present.write_bytes(b"x")
        absent = tmp_path / "absent.safetensors"
        original = mm._downloads_allowed
        try:
            mm._downloads_allowed = True
            missing = mm.require_downloads_allowed_for_missing(
                "seedvr2", [str(present), str(absent)]
            )
            assert missing == [str(absent)]
        finally:
            mm._downloads_allowed = original

    def test_unresolved_path_counts_as_missing(self):
        from core import model_manager as mm

        original = mm._downloads_allowed
        try:
            mm._downloads_allowed = False
            with pytest.raises(RuntimeError):
                mm.require_downloads_allowed_for_missing("seedvr2", [""])
        finally:
            mm._downloads_allowed = original

    def test_seedvr_loader_no_longer_gates_unconditionally(self):
        """Guard: the gate must sit behind a disk check, not above it."""
        import inspect
        from core import seedvr_synthesizer

        src = inspect.getsource(seedvr_synthesizer._load_model)
        assert "require_downloads_allowed_for_missing" in src
        assert "require_downloads_allowed(" not in src
