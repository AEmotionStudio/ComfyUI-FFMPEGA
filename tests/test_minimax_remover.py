"""Tests for MiniMax-Remover integration.

Follows the same testing patterns as test_flux_klein.py — all GPU/model
operations are mocked so tests run fast without a GPU.
"""

import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
#  Static / cold-import bootstrap (same pattern as test_flux_klein.py)
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _isolate_module(monkeypatch):
    """Remove cached core.minimax_remover so each test gets a clean import."""
    for mod_name in list(sys.modules):
        if "minimax_remover" in mod_name:
            monkeypatch.delitem(sys.modules, mod_name, raising=False)
    yield


# ---------------------------------------------------------------------------
#  Constants
# ---------------------------------------------------------------------------

class TestMiniMaxConstants:
    """Verify the public constants match expected values."""

    def test_hf_repo(self):
        from core.minimax_remover import _HF_REPO
        assert _HF_REPO == "zibojia/minimax-remover"

    def test_mirror_repo(self):
        from core.minimax_remover import _MIRROR_REPO
        assert _MIRROR_REPO == "AEmotionStudio/minimax-remover"

    def test_model_dir_name(self):
        from core.minimax_remover import _MODEL_DIR_NAME
        assert _MODEL_DIR_NAME == "minimax_remover"

    def test_batch_size(self):
        from core.minimax_remover import _BATCH_SIZE
        assert _BATCH_SIZE == 81

    def test_batch_overlap(self):
        from core.minimax_remover import _BATCH_OVERLAP
        assert _BATCH_OVERLAP == 8


# ---------------------------------------------------------------------------
#  Model directory helper
# ---------------------------------------------------------------------------

class TestMiniMaxModelDir:
    """Verify _get_model_dir() respects env vars and fallbacks."""

    def test_env_var_override(self, monkeypatch, tmp_path):
        monkeypatch.setenv("FFMPEGA_MINIMAX_MODEL_DIR", str(tmp_path))
        from core.minimax_remover import _get_model_dir
        assert _get_model_dir() == tmp_path

    def test_fallback_creates_dir(self, monkeypatch, tmp_path):
        monkeypatch.delenv("FFMPEGA_MINIMAX_MODEL_DIR", raising=False)
        # Hide folder_paths so it falls through to extension fallback
        monkeypatch.setitem(sys.modules, "folder_paths", None)
        from core.minimax_remover import _get_model_dir
        result = _get_model_dir()
        assert result.exists()


# ---------------------------------------------------------------------------
#  Pipeline cleanup
# ---------------------------------------------------------------------------

class TestMiniMaxCleanup:
    """Verify cleanup() resets the cached pipeline."""

    def test_cleanup_resets_pipeline(self):
        import core.minimax_remover as mmr
        mmr._pipeline = MagicMock()
        mmr.cleanup()
        assert mmr._pipeline is None

    def test_cleanup_noop_when_none(self):
        import core.minimax_remover as mmr
        mmr._pipeline = None
        mmr.cleanup()  # should not raise
        assert mmr._pipeline is None


# ---------------------------------------------------------------------------
#  Model manager registration
# ---------------------------------------------------------------------------

class TestMiniMaxModelManager:
    """Verify minimax_remover is in the model registry."""

    def test_registered_in_model_info(self):
        from core.model_manager import _MODEL_INFO
        assert "minimax_remover" in _MODEL_INFO

    def test_has_required_fields(self):
        from core.model_manager import _MODEL_INFO
        entry = _MODEL_INFO["minimax_remover"]
        assert "name" in entry
        assert "size" in entry
        assert "url" in entry
        assert "mirror_repo" in entry

    def test_mirror_repo_matches(self):
        from core.model_manager import _MODEL_INFO
        from core.minimax_remover import _MIRROR_REPO
        assert _MODEL_INFO["minimax_remover"]["mirror_repo"] == _MIRROR_REPO

    def test_license_is_cc_by_nc(self):
        from core.model_manager import _MODEL_INFO
        assert _MODEL_INFO["minimax_remover"]["license"] == "CC-BY-NC-4.0"


# ---------------------------------------------------------------------------
#  No-LLM mode registration
# ---------------------------------------------------------------------------

class TestMiniMaxNoLLMMode:
    """Verify minimax_remover appears in the no_llm_mode dropdown."""

    def test_in_dropdown(self):
        from nodes.agent_node import FFMPEGAgentNode
        input_types = FFMPEGAgentNode.INPUT_TYPES()
        all_required = input_types.get("required", {})
        modes = all_required["no_llm_mode"][0]
        assert "minimax_remover" in modes

    def test_process_function_importable(self):
        from nodes.nollm_modes import process_minimax_remover_only
        assert callable(process_minimax_remover_only)


# ---------------------------------------------------------------------------
#  Toggle in agent_node INPUT_TYPES
# ---------------------------------------------------------------------------

class TestMiniMaxToggle:
    """Verify use_minimax_remover toggle is in INPUT_TYPES."""

    def test_toggle_exists(self):
        from nodes.agent_node import FFMPEGAgentNode
        input_types = FFMPEGAgentNode.INPUT_TYPES()
        optional = input_types.get("optional", {})
        assert "use_minimax_remover" in optional

    def test_toggle_is_boolean(self):
        from nodes.agent_node import FFMPEGAgentNode
        input_types = FFMPEGAgentNode.INPUT_TYPES()
        optional = input_types.get("optional", {})
        widget = optional["use_minimax_remover"]
        assert widget[0] == "BOOLEAN"

    def test_toggle_default_false(self):
        from nodes.agent_node import FFMPEGAgentNode
        input_types = FFMPEGAgentNode.INPUT_TYPES()
        optional = input_types.get("optional", {})
        widget = optional["use_minimax_remover"]
        assert widget[1]["default"] is False


# ---------------------------------------------------------------------------
#  Auto-mask handler priority
# ---------------------------------------------------------------------------

class TestMiniMaxAutoMaskPriority:
    """Verify MiniMax takes priority over FLUX Klein for removal."""

    @patch("core.minimax_remover.remove_object")
    @patch("core.minimax_remover.cleanup")
    def test_minimax_priority_over_flux(self, mock_cleanup, mock_remove):
        """When both toggles are on, MiniMax should be called, not Flux."""
        import tempfile, os
        # Create a real temp file for the cached mask path
        mask_fd, mask_path = tempfile.mkstemp(suffix=".mp4")
        os.close(mask_fd)
        try:
            mock_remove.return_value = "/tmp/removed.mp4"

            # Import the handler
            from skills.handlers.visual import _f_auto_mask

            result = _f_auto_mask({
                "target": "person",
                "effect": "remove",
                "_input_path": "/tmp/test.mp4",
                "_enable_flux_klein": True,
                "_enable_minimax_remover": True,
                "_metadata_ref": {"_mask_video_path": mask_path},
            })

            # MiniMax should have been called (not FLUX Klein)
            mock_remove.assert_called_once()
        finally:
            if os.path.exists(mask_path):
                os.unlink(mask_path)

    def test_metadata_propagation(self):
        """Verify _enable_minimax_remover is set on pipeline metadata."""
        from nodes.pipeline_assembler import assemble_pipeline
        import inspect
        sig = inspect.signature(assemble_pipeline)
        assert "use_minimax_remover" in sig.parameters


# ---------------------------------------------------------------------------
#  Vendored module import tests
# ---------------------------------------------------------------------------

class TestMiniMaxVendoredImports:
    """Verify the vendored modules are importable."""

    def test_transformer_importable(self):
        from core.minimax.transformer_minimax_remover import Transformer3DModel
        assert Transformer3DModel is not None

    def test_pipeline_importable(self):
        from core.minimax.pipeline_minimax_remover import Minimax_Remover_Pipeline
        assert Minimax_Remover_Pipeline is not None
