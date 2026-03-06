"""Unit tests for the FLUX Klein editor module.

Tests cover:
- Module constants (HF repo, mirror repo, model dir name)
- Model directory helper
- Pipeline cleanup
- Model manager integration
- Removal prompt constant
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

class TestFluxKleinConstants:
    """Test that module constants are correctly defined."""

    def test_hf_repo(self):
        """_HF_REPO should point to BFL's official repo."""
        from core.flux_klein_editor import _HF_REPO
        assert _HF_REPO == "black-forest-labs/FLUX.2-klein-4B"

    def test_mirror_repo(self):
        """_MIRROR_REPO should point to AEmotionStudio mirror."""
        from core.flux_klein_editor import _MIRROR_REPO
        assert _MIRROR_REPO == "AEmotionStudio/flux-klein"

    def test_model_dir_name(self):
        """_MODEL_DIR_NAME should be flux_klein."""
        from core.flux_klein_editor import _MODEL_DIR_NAME
        assert _MODEL_DIR_NAME == "flux_klein"

    def test_removal_prompt_is_descriptive(self):
        """_REMOVAL_PROMPT should be a meaningful prompt, not empty."""
        from core.flux_klein_editor import _REMOVAL_PROMPT
        assert len(_REMOVAL_PROMPT) > 20
        assert "fill" in _REMOVAL_PROMPT.lower() or "background" in _REMOVAL_PROMPT.lower()

    def test_pipeline_defaults(self):
        """Pipeline defaults should be reasonable values."""
        from core.flux_klein_editor import _NUM_STEPS, _GUIDANCE_SCALE, _OUTPUT_SIZE
        assert _NUM_STEPS == 4
        assert _GUIDANCE_SCALE == 1.0
        assert _OUTPUT_SIZE == 1024


# --- Model Directory Tests ----------------------------------------------------

class TestFluxKleinModelDir:
    """Test the model directory helper."""

    def test_model_dir_contains_flux_klein(self):
        """_get_model_dir should return a path ending in flux_klein."""
        from unittest.mock import patch
        from core.flux_klein_editor import _get_model_dir
        with patch.object(os, "environ", {"FFMPEGA_FLUX_KLEIN_MODEL_DIR": "/tmp/flux_klein"}):
            d = _get_model_dir()
            assert str(d).endswith("flux_klein")


# --- Cleanup Tests -------------------------------------------------------------

class TestFluxKleinCleanup:
    """Test pipeline cleanup."""

    @pytest.mark.skipif(not _has_torch, reason="PyTorch not available")
    def test_cleanup_resets_pipeline(self):
        """Cleanup should reset the cached pipeline to None."""
        import core.flux_klein_editor as fk
        fk._pipeline = "fake"
        fk.cleanup()
        assert fk._pipeline is None


# --- Model Manager Integration -------------------------------------------------

class TestFluxKleinModelManager:
    """Test that FLUX Klein is registered in model_manager."""

    def test_flux_klein_in_model_info(self):
        """flux_klein should be in _MODEL_INFO."""
        from core.model_manager import _MODEL_INFO
        assert "flux_klein" in _MODEL_INFO

    def test_model_info_has_required_fields(self):
        """flux_klein entry should have all required fields."""
        from core.model_manager import _MODEL_INFO
        info = _MODEL_INFO["flux_klein"]
        assert "name" in info
        assert "size" in info
        assert "url" in info
        assert "mirror_repo" in info
        assert "manual" in info

    def test_mirror_repo_matches(self):
        """Mirror repo in model_manager should match flux_klein_editor."""
        from core.model_manager import _MODEL_INFO
        from core.flux_klein_editor import _MIRROR_REPO
        assert _MODEL_INFO["flux_klein"]["mirror_repo"] == _MIRROR_REPO

    def test_license_is_apache(self):
        """FLUX Klein should be Apache 2.0 licensed."""
        from core.model_manager import _MODEL_INFO
        assert "Apache" in _MODEL_INFO["flux_klein"].get("license", "")


# --- Skill Registration Tests --------------------------------------------------

class TestFluxKleinSkillRegistration:
    """Test that the edit effect is registered in auto_mask."""

    @pytest.fixture
    def registry(self):
        from skills.registry import get_registry
        return get_registry()

    def test_edit_effect_in_choices(self, registry):
        """auto_mask should include 'edit' in effect choices."""
        skill = registry.get("auto_mask")
        effect_param = next(p for p in skill.parameters if p.name == "effect")
        assert "edit" in effect_param.choices

    def test_edit_prompt_parameter_exists(self, registry):
        """auto_mask should have an edit_prompt parameter."""
        skill = registry.get("auto_mask")
        param_names = {p.name for p in skill.parameters}
        assert "edit_prompt" in param_names

    def test_edit_prompt_not_required(self, registry):
        """edit_prompt should not be required (only needed for effect=edit)."""
        skill = registry.get("auto_mask")
        ep = next(p for p in skill.parameters if p.name == "edit_prompt")
        assert ep.required is False

    def test_edit_examples_exist(self, registry):
        """auto_mask should have examples showing the edit effect."""
        skill = registry.get("auto_mask")
        assert any("effect=edit" in ex for ex in skill.examples)

    def test_flux_tag_exists(self, registry):
        """auto_mask should have 'flux' in its tags."""
        skill = registry.get("auto_mask")
        assert "flux" in skill.tags


# --- Path Validation Tests -----------------------------------------------------

class TestFluxKleinPathValidation:
    """Test that path inputs are validated against traversal attacks."""

    def test_edit_video_rejects_traversal(self):
        """edit_video should reject path traversal in video_path."""
        from core.flux_klein_editor import edit_video
        from core.errors import ValidationError
        with pytest.raises(ValidationError):
            edit_video("../../../../etc/passwd", "/tmp/mask.mp4", "test")


# --- OOM Cleanup Tests ---------------------------------------------------------

class TestFluxKleinOOMCleanup:
    """Test that cleanup() is always called, even on OOM errors."""

    @pytest.mark.skipif(not _has_torch, reason="PyTorch not available")
    def test_cleanup_called_on_oom(self):
        """cleanup() should run even when a frame raises OOM."""
        from unittest.mock import patch, MagicMock
        import core.flux_klein_editor as fk

        # Set up a fake pipeline so load_pipeline returns it
        fk._pipeline = MagicMock()

        with (
            patch.object(fk, "_load_video_frames") as mock_load,
            patch.object(fk, "_load_mask_frames") as mock_masks,
            patch.object(fk, "_edit_frame", side_effect=RuntimeError("fake OOM")),
            patch.object(fk, "cleanup") as mock_cleanup,
            patch.object(fk, "validate_video_path", side_effect=lambda x: x),
        ):
            # Provide minimal frame/mask data
            from PIL import Image
            import numpy as np
            dummy_frame = Image.fromarray(np.zeros((64, 64, 3), dtype=np.uint8))
            dummy_mask = Image.fromarray(np.full((64, 64), 255, dtype=np.uint8))
            mock_load.return_value = ([dummy_frame], 8.0, "/tmp/fake_frames")
            mock_masks.return_value = ([dummy_mask], "/tmp/fake_masks")

            with pytest.raises(RuntimeError, match="fake OOM"):
                fk.edit_video("/tmp/v.mp4", "/tmp/m.mp4", "test")

            # cleanup() must have been called even though we raised
            mock_cleanup.assert_called_once()

    @pytest.mark.skipif(not _has_torch, reason="PyTorch not available")
    def test_auto_mask_edit_cleanup_on_flux_error(self):
        """_f_auto_mask should call flux cleanup when edit_video fails."""
        from unittest.mock import patch, MagicMock
        from skills.handlers.visual import _f_auto_mask

        params = {
            "_input_path": "/tmp/fake.mp4",
            "target": "hair",
            "effect": "edit",
            "edit_prompt": "blonde hair",
            "_enable_flux_klein": True,
            "_metadata_ref": {"_mask_video_path": "/tmp/mask.mp4"},
        }

        with (
            patch("os.path.isfile", return_value=True),
            patch("core.flux_klein_editor.edit_video", side_effect=RuntimeError("OOM")),
            patch("core.flux_klein_editor.cleanup") as mock_cleanup,
        ):
            with pytest.raises(RuntimeError, match="OOM"):
                _f_auto_mask(params)
            mock_cleanup.assert_called_once()

