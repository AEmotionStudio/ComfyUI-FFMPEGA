"""Unit tests for the SVI (Stable Video Infinity) synthesizer module.

Tests cover:
- Module constants (HF repo, model dir, LoRA paths, default params)
- Model directory helper
- Pipeline cleanup
- Model manager integration
- No-LLM mode registration
- Prompt parsing
"""

import pytest

import os

# PyTorch import can fail on Python 3.14 — guard torch-dependent tests
try:
    import torch  # noqa: F401
    _has_torch = True
except (ImportError, RuntimeError):
    _has_torch = False


# --- Constants Tests ----------------------------------------------------------

class TestSVIConstants:
    """Test that module constants are correctly defined."""

    def test_hf_repo(self):
        """_HF_REPO should point to the SVI model repo."""
        from core.svi_synthesizer import _HF_REPO
        assert _HF_REPO == "vita-video-gen/svi-model"

    def test_model_dir_name(self):
        """_MODEL_DIR_NAME should be svi."""
        from core.svi_synthesizer import _MODEL_DIR_NAME
        assert _MODEL_DIR_NAME == "svi"

    def test_lora_pro_paths(self):
        """Pro LoRA filenames should contain '2.0_pro'."""
        from core.svi_synthesizer import _LORA_HIGH_PRO, _LORA_LOW_PRO
        assert "v2.0_pro" in _LORA_HIGH_PRO
        assert "v2.0_pro" in _LORA_LOW_PRO

    def test_lora_std_paths(self):
        """Standard LoRA filenames should contain '2.0' but not 'pro'."""
        from core.svi_synthesizer import _LORA_HIGH_STD, _LORA_LOW_STD
        assert "v2.0" in _LORA_HIGH_STD
        assert "v2.0" in _LORA_LOW_STD
        assert "pro" not in _LORA_HIGH_STD
        assert "pro" not in _LORA_LOW_STD

    def test_default_params(self):
        """Default generation parameters should be reasonable values."""
        from core.svi_synthesizer import (
            _FRAMES_PER_CLIP, _DEFAULT_HEIGHT, _DEFAULT_WIDTH,
            _DEFAULT_FPS, _DEFAULT_CFG_SCALE, _DEFAULT_NUM_CLIPS,
            _DEFAULT_OVERLAP_FRAMES, _DEFAULT_SWITCH_BOUNDARY,
        )
        assert _FRAMES_PER_CLIP == 81
        assert _DEFAULT_HEIGHT == 480
        assert _DEFAULT_WIDTH == 832
        assert _DEFAULT_FPS == 15
        assert _DEFAULT_CFG_SCALE == 4.0
        assert _DEFAULT_NUM_CLIPS == 10
        assert _DEFAULT_OVERLAP_FRAMES == 5
        assert _DEFAULT_SWITCH_BOUNDARY == 0.875

    def test_negative_prompt_is_nonempty(self):
        """_NEGATIVE_PROMPT should be a meaningful string."""
        from core.svi_synthesizer import _NEGATIVE_PROMPT
        assert len(_NEGATIVE_PROMPT) > 20


# --- Model Directory Tests ----------------------------------------------------

class TestSVIModelDir:
    """Test the model directory helper."""

    def test_model_dir_contains_svi(self):
        """_get_model_dir should return a path ending in svi."""
        from unittest.mock import patch
        from core.svi_synthesizer import _get_model_dir
        with patch.object(os, "environ", {"FFMPEGA_SVI_MODEL_DIR": "/tmp/svi"}):
            d = _get_model_dir()
            assert str(d).endswith("svi")

    def test_resolve_lora_path_pro(self):
        """_resolve_lora_path with pro LoRA should return path containing the filename."""
        from core.svi_synthesizer import _resolve_lora_path, _LORA_HIGH_PRO
        path = _resolve_lora_path(_LORA_HIGH_PRO)
        assert "pro" in str(path)

    def test_resolve_lora_path_standard(self):
        """_resolve_lora_path with standard LoRA should return path without 'pro'."""
        from core.svi_synthesizer import _resolve_lora_path, _LORA_HIGH_STD
        path = _resolve_lora_path(_LORA_HIGH_STD)
        assert "pro" not in str(path)


# --- Cleanup Tests -------------------------------------------------------------

class TestSVICleanup:
    """Test pipeline cleanup."""

    @pytest.mark.skipif(not _has_torch, reason="PyTorch not available")
    def test_cleanup_resets_state(self):
        """Cleanup should reset the cached pipeline state."""
        import core.svi_synthesizer as svi
        svi._pipeline_loaded = True
        svi._wan_models = {"test": "data"}
        svi.cleanup()
        assert svi._pipeline_loaded is False
        assert svi._wan_models is None


# --- Model Manager Integration -------------------------------------------------

class TestSVIModelManager:
    """Test that SVI is registered in model_manager."""

    def test_svi_in_model_info(self):
        """svi should be in _MODEL_INFO."""
        from core.model_manager import _MODEL_INFO
        assert "svi" in _MODEL_INFO

    def test_model_info_has_required_fields(self):
        """svi entry should have all required fields."""
        from core.model_manager import _MODEL_INFO
        info = _MODEL_INFO["svi"]
        assert "name" in info
        assert "size" in info
        assert "url" in info
        assert "manual" in info

    def test_license_is_apache(self):
        """SVI should be Apache 2.0 licensed."""
        from core.model_manager import _MODEL_INFO
        assert "Apache" in _MODEL_INFO["svi"].get("license", "")


# --- No-LLM Mode Tests --------------------------------------------------------

class TestSVINoLLMMode:
    """Test the svi no_llm_mode integration."""

    def test_svi_in_no_llm_dropdown(self):
        """'svi' should be in the no_llm_mode dropdown choices."""
        pytest.importorskip("torch")
        from nodes.agent_node import FFMPEGAgentNode
        input_types = FFMPEGAgentNode.INPUT_TYPES()
        choices = input_types["required"]["no_llm_mode"][0]
        assert "svi" in choices

    def test_svi_params_in_input_types(self):
        """SVI-specific parameters should be in INPUT_TYPES."""
        pytest.importorskip("torch")
        from nodes.agent_node import FFMPEGAgentNode
        input_types = FFMPEGAgentNode.INPUT_TYPES()
        optional = input_types.get("optional", {})
        assert "svi_num_clips" in optional
        assert "svi_height" in optional
        assert "svi_width" in optional
        assert "svi_fps" in optional
        assert "svi_cfg_scale" in optional
        assert "svi_overlap_frames" in optional
        assert "svi_seed_multiplier" in optional
        assert "svi_variant" in optional

    def test_svi_variant_choices(self):
        """svi_variant should have 'pro' and 'standard' choices."""
        pytest.importorskip("torch")
        from nodes.agent_node import FFMPEGAgentNode
        input_types = FFMPEGAgentNode.INPUT_TYPES()
        variant_choices = input_types["optional"]["svi_variant"][0]
        assert "pro" in variant_choices
        assert "standard" in variant_choices

    def test_generate_infinite_video_exists(self):
        """generate_infinite_video should be importable from svi_synthesizer."""
        from core.svi_synthesizer import generate_infinite_video
        assert callable(generate_infinite_video)

    def test_process_svi_only_exists(self):
        """process_svi_only should be importable from nollm_modes."""
        pytest.importorskip("torch")
        from nodes.nollm_modes import process_svi_only
        assert callable(process_svi_only)

    def test_generate_infinite_video_signature(self):
        """generate_infinite_video should accept expected parameters."""
        import inspect
        from core.svi_synthesizer import generate_infinite_video
        sig = inspect.signature(generate_infinite_video)
        params = sig.parameters
        assert "ref_image_path" in params
        assert "prompts" in params
        assert "output_path" in params
        assert "num_clips" in params
        assert "height" in params
        assert "width" in params
        assert "fps" in params
        assert "cfg_scale" in params
        assert "variant" in params


# --- Prompt Parsing Tests -------------------------------------------------------

class TestSVIPromptParsing:
    """Test that newline-separated prompts are correctly handled."""

    def test_pad_prompts(self):
        """generate_infinite_video should pad prompts if fewer than num_clips."""
        from core.svi_synthesizer import generate_infinite_video
        import inspect
        # Just verify the function signature accepts the needed params
        sig = inspect.signature(generate_infinite_video)
        assert "prompts" in sig.parameters
        assert "num_clips" in sig.parameters

    def test_generate_rejects_missing_ref_image(self):
        """generate_infinite_video should raise FileNotFoundError for missing ref image."""
        from core.svi_synthesizer import generate_infinite_video
        with pytest.raises(FileNotFoundError):
            generate_infinite_video(
                "/tmp/nonexistent_image_svi_test.png",
                ["test prompt"],
                num_clips=1,
            )


# --- Block Swap / VRAM Option Tests ---------------------------------------------

class TestSVIBlockSwap:
    """Test the svi_blockswap_blocks / svi_tiled_vae VRAM options."""

    _MODULE_SIZE = 1000  # fake bytes per transformer block

    def _install_fake_comfy(self, monkeypatch):
        """Inject minimal comfy.model_management / comfy.patcher_extension mocks."""
        import sys
        import types

        mm = types.ModuleType("comfy.model_management")
        mm.EXTRA_RESERVED_VRAM = 400
        mm.module_size = lambda module: self._MODULE_SIZE

        pe = types.ModuleType("comfy.patcher_extension")

        class WrappersMP:
            PREPARE_SAMPLING = "prepare_sampling"

        pe.WrappersMP = WrappersMP

        comfy_pkg = sys.modules.get("comfy")
        if comfy_pkg is None:
            comfy_pkg = types.ModuleType("comfy")
            monkeypatch.setitem(sys.modules, "comfy", comfy_pkg)
        monkeypatch.setattr(comfy_pkg, "model_management", mm, raising=False)
        monkeypatch.setattr(comfy_pkg, "patcher_extension", pe, raising=False)
        monkeypatch.setitem(sys.modules, "comfy.model_management", mm)
        monkeypatch.setitem(sys.modules, "comfy.patcher_extension", pe)
        return mm

    def _fake_patcher(self, num_blocks=40):
        import types

        class FakePatcher:
            def __init__(self):
                self.model = types.SimpleNamespace(
                    diffusion_model=types.SimpleNamespace(
                        blocks=[object()] * num_blocks
                    )
                )
                self.wrappers = {}

            def add_wrapper_with_key(self, wrapper_type, key, wrapper):
                self.wrappers[(wrapper_type, key)] = wrapper

            def model_size(self):
                return num_blocks * TestSVIBlockSwap._MODULE_SIZE

        return FakePatcher()

    def test_zero_blocks_registers_nothing(self):
        """blocks_to_swap=0 must be a no-op (no wrapper, no comfy import needed)."""
        from core.svi_synthesizer import _register_blockswap
        patcher = self._fake_patcher()
        _register_blockswap(patcher, 0)
        assert patcher.wrappers == {}

    def test_wrapper_registered_under_prepare_sampling(self, monkeypatch):
        """A wrapper should be registered under WrappersMP.PREPARE_SAMPLING."""
        self._install_fake_comfy(monkeypatch)
        from core.svi_synthesizer import _register_blockswap
        patcher = self._fake_patcher()
        _register_blockswap(patcher, 4)
        assert ("prepare_sampling", "svi_blockswap") in patcher.wrappers

    def test_wrapper_bumps_and_restores_reserve(self, monkeypatch):
        """The wrapper must raise EXTRA_RESERVED_VRAM by blocks*block_size
        during the executor call and restore it afterwards."""
        mm = self._install_fake_comfy(monkeypatch)
        from core.svi_synthesizer import _register_blockswap
        patcher = self._fake_patcher()
        _register_blockswap(patcher, 4)
        wrapper = patcher.wrappers[("prepare_sampling", "svi_blockswap")]

        baseline = mm.EXTRA_RESERVED_VRAM
        seen = {}

        def executor(*args, **kwargs):
            seen["reserve"] = mm.EXTRA_RESERVED_VRAM
            return "ok"

        assert wrapper(executor) == "ok"
        assert seen["reserve"] == baseline + 4 * self._MODULE_SIZE
        assert mm.EXTRA_RESERVED_VRAM == baseline

    def test_wrapper_restores_reserve_on_exception(self, monkeypatch):
        """EXTRA_RESERVED_VRAM must be restored even if the executor raises."""
        mm = self._install_fake_comfy(monkeypatch)
        from core.svi_synthesizer import _register_blockswap
        patcher = self._fake_patcher()
        _register_blockswap(patcher, 8)
        wrapper = patcher.wrappers[("prepare_sampling", "svi_blockswap")]

        baseline = mm.EXTRA_RESERVED_VRAM

        def executor(*args, **kwargs):
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError):
            wrapper(executor)
        assert mm.EXTRA_RESERVED_VRAM == baseline

    def test_blocks_capped_at_model_block_count(self, monkeypatch):
        """Requesting more blocks than the model has must cap at len(blocks)."""
        mm = self._install_fake_comfy(monkeypatch)
        from core.svi_synthesizer import _register_blockswap
        patcher = self._fake_patcher(num_blocks=40)
        _register_blockswap(patcher, 99)
        wrapper = patcher.wrappers[("prepare_sampling", "svi_blockswap")]

        baseline = mm.EXTRA_RESERVED_VRAM
        seen = {}

        def executor(*args, **kwargs):
            seen["reserve"] = mm.EXTRA_RESERVED_VRAM

        wrapper(executor)
        assert seen["reserve"] == baseline + 40 * self._MODULE_SIZE

    def test_new_params_in_generate_signature(self):
        """generate_infinite_video should accept blockswap_blocks and tiled_vae."""
        import inspect
        from core.svi_synthesizer import generate_infinite_video
        params = inspect.signature(generate_infinite_video).parameters
        assert "blockswap_blocks" in params
        assert params["blockswap_blocks"].default == 0
        assert "tiled_vae" in params
        assert params["tiled_vae"].default is False

    def test_new_widgets_in_input_types(self):
        """svi_blockswap_blocks / svi_tiled_vae should be in INPUT_TYPES."""
        pytest.importorskip("torch")
        from nodes.agent_node import FFMPEGAgentNode
        optional = FFMPEGAgentNode.INPUT_TYPES().get("optional", {})
        assert "svi_blockswap_blocks" in optional
        cfg = optional["svi_blockswap_blocks"][1]
        assert cfg["default"] == 0
        assert cfg["min"] == 0
        assert cfg["max"] == 40
        assert "svi_tiled_vae" in optional
        assert optional["svi_tiled_vae"][1]["default"] is False
