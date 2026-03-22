"""Tests for the Foundation-1 synthesizer module.

Covers module API surface, model directory resolution,
prompt presets, and VRAM management.
"""

import pytest
from unittest.mock import patch, MagicMock
import os


# ── Module API Surface ────────────────────────────────────────────


class TestFoundation1API:
    """Verify the Foundation-1 synthesizer exports the expected API."""

    def test_generate_sample_importable(self):
        """generate_sample should be importable from the synthesizer."""
        from core.foundation1_synthesizer import generate_sample
        assert callable(generate_sample)

    def test_load_models_importable(self):
        """load_models should be importable."""
        from core.foundation1_synthesizer import load_models
        assert callable(load_models)

    def test_cleanup_importable(self):
        """cleanup should be importable."""
        from core.foundation1_synthesizer import cleanup
        assert callable(cleanup)

    def test_resolve_prompt_importable(self):
        """_resolve_prompt should be importable."""
        from core.foundation1_synthesizer import _resolve_prompt
        assert callable(_resolve_prompt)


# ── Model Directory & Files ────────────────────────────────────────


class TestFoundation1ModelFiles:
    """Verify model file constants and directory resolution."""

    def test_model_files_dict(self):
        """_MODEL_FILES should contain expected keys."""
        from core.foundation1_synthesizer import _MODEL_FILES
        assert "model" in _MODEL_FILES
        assert "config" in _MODEL_FILES
        # Foundation-1 is simpler than AudioX — no synchformer
        assert "synchformer" not in _MODEL_FILES

    def test_model_filename(self):
        """Model filename should match Foundation-1 convention."""
        from core.foundation1_synthesizer import _MODEL_FILES
        assert _MODEL_FILES["model"] == "Foundation_1.safetensors"
        assert _MODEL_FILES["config"] == "model_config.json"

    def test_hf_repo_constant(self):
        """HF repo should point to RoyalCities/Foundation-1."""
        from core.foundation1_synthesizer import _HF_REPO
        assert "RoyalCities" in _HF_REPO
        assert "Foundation-1" in _HF_REPO

    def test_mirror_repo_constant(self):
        """Mirror repo should point to AEmotionStudio."""
        from core.foundation1_synthesizer import _MIRROR_REPO
        assert "AEmotionStudio" in _MIRROR_REPO


# ── Prompt Presets ─────────────────────────────────────────────────


class TestPromptPresets:
    """Verify the built-in prompt presets."""

    def test_presets_dict_exists(self):
        """PRESETS should be a non-empty dict."""
        from core.foundation1_synthesizer import PRESETS
        assert isinstance(PRESETS, dict)
        assert len(PRESETS) > 0

    def test_presets_all_strings(self):
        """Every preset key and value should be a string."""
        from core.foundation1_synthesizer import PRESETS
        for key, value in PRESETS.items():
            assert isinstance(key, str), f"Preset key {key!r} is not a string"
            assert isinstance(value, str), f"Preset value for {key!r} is not a string"

    def test_known_presets_exist(self):
        """Expected presets should be present."""
        from core.foundation1_synthesizer import PRESETS
        expected = {
            "warm_pad", "synth_lead", "bass_loop",
            "string_ensemble", "electric_piano", "plucked_arp",
        }
        for name in expected:
            assert name in PRESETS, f"Missing preset: {name}"

    def test_presets_non_empty_values(self):
        """Every preset value should be non-empty."""
        from core.foundation1_synthesizer import PRESETS
        for key, value in PRESETS.items():
            assert value.strip(), f"Preset {key!r} has empty value"


# ── Prompt Resolution ──────────────────────────────────────────────


class TestPromptResolution:
    """Test the _resolve_prompt function."""

    def test_prompt_only(self):
        """User prompt should be returned directly."""
        from core.foundation1_synthesizer import _resolve_prompt
        result = _resolve_prompt("Bright synth lead")
        assert "Bright synth lead" in result

    def test_preset_only(self):
        """Preset tags should be used when no prompt given."""
        from core.foundation1_synthesizer import _resolve_prompt, PRESETS
        result = _resolve_prompt("", preset="warm_pad")
        assert PRESETS["warm_pad"] in result

    def test_prompt_and_preset_combined(self):
        """Preset and prompt should both appear."""
        from core.foundation1_synthesizer import _resolve_prompt, PRESETS
        result = _resolve_prompt("Extra bright", preset="warm_pad")
        assert "Extra bright" in result
        assert PRESETS["warm_pad"] in result

    def test_bpm_appended(self):
        """BPM should be appended when provided."""
        from core.foundation1_synthesizer import _resolve_prompt
        result = _resolve_prompt("A loop", bpm=120)
        assert "120 BPM" in result

    def test_bars_appended(self):
        """Bars should be appended when provided."""
        from core.foundation1_synthesizer import _resolve_prompt
        result = _resolve_prompt("A loop", bars=8)
        assert "8 Bars" in result

    def test_key_appended(self):
        """Key should be appended when provided."""
        from core.foundation1_synthesizer import _resolve_prompt
        result = _resolve_prompt("A loop", key="C major")
        assert "C major" in result

    def test_all_params(self):
        """All params should be combined in the output."""
        from core.foundation1_synthesizer import _resolve_prompt
        result = _resolve_prompt(
            "Synth pad", preset="warm_pad",
            bpm=100, bars=4, key="A minor",
        )
        assert "Synth pad" in result
        assert "100 BPM" in result
        assert "4 Bars" in result
        assert "A minor" in result

    def test_empty_returns_default(self):
        """Empty prompt with no preset should return a default."""
        from core.foundation1_synthesizer import _resolve_prompt
        result = _resolve_prompt("")
        assert len(result) > 0

    def test_unknown_preset_ignored(self):
        """Unknown preset name should be silently ignored."""
        from core.foundation1_synthesizer import _resolve_prompt
        result = _resolve_prompt("A loop", preset="nonexistent_preset")
        assert "A loop" in result

    def test_bpm_zero_not_appended(self):
        """BPM of 0 should not be appended."""
        from core.foundation1_synthesizer import _resolve_prompt
        result = _resolve_prompt("A loop", bpm=0)
        assert "BPM" not in result


# ── VRAM & Offloading ──────────────────────────────────────────────


class TestFoundation1VRAM:
    """Test VRAM management functions."""

    def test_cleanup_when_no_models_loaded(self):
        """cleanup should be safe to call when no models are loaded."""
        from core.foundation1_synthesizer import cleanup
        # Should not raise
        cleanup()

    def test_cleanup_resets_global_state(self):
        """cleanup should reset the global _models to None."""
        import core.foundation1_synthesizer as synth
        synth._models = None  # Ensure clean state
        synth.cleanup()  # Should be idempotent
        assert synth._models is None


# ── License Notice ──────────────────────────────────────────────────


class TestLicenseNotice:
    """Verify the license notice logging."""

    def test_license_logged_once(self):
        """License notice should only be logged once per session."""
        import core.foundation1_synthesizer as synth
        # Reset the flag
        synth._license_logged = False
        synth._log_license_notice()
        assert synth._license_logged is True
        # Second call should be a no-op (no error)
        synth._log_license_notice()
        assert synth._license_logged is True


# ── Skill Handler ──────────────────────────────────────────────────


class TestGenerateSampleHandler:
    """Verify the skill handler is importable."""

    def test_handler_importable(self):
        """_f_generate_sample should be importable."""
        from skills.handlers.generate_sample import _f_generate_sample
        assert callable(_f_generate_sample)
