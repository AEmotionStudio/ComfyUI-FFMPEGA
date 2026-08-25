"""Unit tests for the SCAIL-2 synthesizer module.

Tests cover:
- Block swap registration via the shared core.vram_utils helper
- scail2_blockswap_blocks / scail2_tiled_vae widget plumbing on the Agent node
"""

import pytest


# --- Block Swap / VRAM Option Tests ---------------------------------------------

class TestScail2BlockSwap:
    """Test the scail2_blockswap_blocks VRAM option.

    Mirrors TestSVIBlockSwap in test_svi.py — both delegate to the same
    core.vram_utils.register_blockswap helper, so the contract is identical
    apart from the wrapper key and label.
    """

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
                return num_blocks * TestScail2BlockSwap._MODULE_SIZE

        return FakePatcher()

    def test_zero_blocks_registers_nothing(self):
        """blocks_to_swap=0 must be a no-op (no wrapper, no comfy import needed)."""
        from core.scail2_synthesizer import _register_blockswap
        patcher = self._fake_patcher()
        _register_blockswap(patcher, 0)
        assert patcher.wrappers == {}

    def test_wrapper_registered_under_prepare_sampling(self, monkeypatch):
        """A wrapper should be registered under WrappersMP.PREPARE_SAMPLING."""
        self._install_fake_comfy(monkeypatch)
        from core.scail2_synthesizer import _register_blockswap
        patcher = self._fake_patcher()
        _register_blockswap(patcher, 4)
        assert ("prepare_sampling", "scail2_blockswap") in patcher.wrappers

    def test_key_does_not_collide_with_svi(self, monkeypatch):
        """SCAIL-2 must use its own key so it can coexist with other models."""
        self._install_fake_comfy(monkeypatch)
        from core.scail2_synthesizer import _register_blockswap
        patcher = self._fake_patcher()
        _register_blockswap(patcher, 4)
        assert ("prepare_sampling", "svi_blockswap") not in patcher.wrappers

    def test_wrapper_bumps_and_restores_reserve(self, monkeypatch):
        """The wrapper must raise EXTRA_RESERVED_VRAM by blocks*block_size
        during the executor call and restore it afterwards."""
        mm = self._install_fake_comfy(monkeypatch)
        from core.scail2_synthesizer import _register_blockswap
        patcher = self._fake_patcher()
        _register_blockswap(patcher, 4)
        wrapper = patcher.wrappers[("prepare_sampling", "scail2_blockswap")]

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
        from core.scail2_synthesizer import _register_blockswap
        patcher = self._fake_patcher()
        _register_blockswap(patcher, 8)
        wrapper = patcher.wrappers[("prepare_sampling", "scail2_blockswap")]

        baseline = mm.EXTRA_RESERVED_VRAM

        def executor(*args, **kwargs):
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError):
            wrapper(executor)
        assert mm.EXTRA_RESERVED_VRAM == baseline

    def test_blocks_capped_at_model_block_count(self, monkeypatch):
        """Requesting more blocks than the model has must cap at len(blocks)."""
        mm = self._install_fake_comfy(monkeypatch)
        from core.scail2_synthesizer import _register_blockswap
        patcher = self._fake_patcher(num_blocks=40)
        _register_blockswap(patcher, 99)
        wrapper = patcher.wrappers[("prepare_sampling", "scail2_blockswap")]

        baseline = mm.EXTRA_RESERVED_VRAM
        seen = {}

        def executor(*args, **kwargs):
            seen["reserve"] = mm.EXTRA_RESERVED_VRAM
            return None

        wrapper(executor)
        assert seen["reserve"] == baseline + 40 * self._MODULE_SIZE


# --- Widget Plumbing Tests ------------------------------------------------------

class TestScail2VramWidgets:
    """Test that the VRAM widgets are exposed on the Agent node."""

    def test_blockswap_blocks_widget_exists(self):
        """scail2_blockswap_blocks should be an INT widget spanning 0..40."""
        pytest.importorskip("torch")
        from nodes.agent_node import FFMPEGAgentNode
        optional = FFMPEGAgentNode.INPUT_TYPES().get("optional", {})
        assert "scail2_blockswap_blocks" in optional
        spec = optional["scail2_blockswap_blocks"]
        assert spec[0] == "INT"
        assert spec[1]["default"] == 0
        assert spec[1]["min"] == 0
        assert spec[1]["max"] == 40

    def test_tiled_vae_widget_exists(self):
        """scail2_tiled_vae should be a BOOLEAN widget defaulting to off."""
        pytest.importorskip("torch")
        from nodes.agent_node import FFMPEGAgentNode
        optional = FFMPEGAgentNode.INPUT_TYPES().get("optional", {})
        assert "scail2_tiled_vae" in optional
        spec = optional["scail2_tiled_vae"]
        assert spec[0] == "BOOLEAN"
        assert spec[1]["default"] is False

    def test_generate_video_accepts_vram_params(self):
        """generate_video must accept blockswap_blocks / tiled_vae as kwargs."""
        import inspect
        from core.scail2_synthesizer import generate_video
        params = inspect.signature(generate_video).parameters
        assert params["blockswap_blocks"].default == 0
        assert params["tiled_vae"].default is False
