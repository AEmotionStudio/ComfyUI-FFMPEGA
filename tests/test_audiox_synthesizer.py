"""Tests for the AudioX synthesizer module.

Covers module API surface, model directory resolution,
and video frame extraction.
"""

import pytest
from unittest.mock import patch, MagicMock
import os


# ── Module API Surface ────────────────────────────────────────────


class TestAudioXAPI:
    """Verify the AudioX synthesizer exports the expected API."""

    def test_generate_music_importable(self):
        """generate_music should be importable from the synthesizer."""
        from core.audiox_synthesizer import generate_music
        assert callable(generate_music)

    def test_generate_audio_audiox_importable(self):
        """generate_audio_audiox should be importable."""
        from core.audiox_synthesizer import generate_audio_audiox
        assert callable(generate_audio_audiox)

    def test_inpaint_audio_importable(self):
        """inpaint_audio should be importable."""
        from core.audiox_synthesizer import inpaint_audio
        assert callable(inpaint_audio)

    def test_load_models_importable(self):
        """load_models should be importable."""
        from core.audiox_synthesizer import load_models
        assert callable(load_models)

    def test_cleanup_importable(self):
        """cleanup should be importable."""
        from core.audiox_synthesizer import cleanup
        assert callable(cleanup)


# ── Model Directory & Files ────────────────────────────────────────


class TestAudioXModelFiles:
    """Verify model file constants and directory resolution."""

    def test_model_files_dict(self):
        """_MODEL_FILES should contain expected keys."""
        from core.audiox_synthesizer import _MODEL_FILES
        assert "model" in _MODEL_FILES
        assert "config" in _MODEL_FILES
        assert "synchformer" in _MODEL_FILES
        # Note: AudioX-MAF bundles VAE inside the main model checkpoint
        assert "vae" not in _MODEL_FILES

    def test_hf_repo_constant(self):
        """HF repo should point to AudioX-MAF."""
        from core.audiox_synthesizer import _HF_REPO
        assert "AudioX-MAF" in _HF_REPO

    def test_mirror_repo_constant(self):
        """Mirror repo should point to AEmotionStudio."""
        from core.audiox_synthesizer import _MIRROR_REPO
        assert "AEmotionStudio" in _MIRROR_REPO

    def test_max_duration(self):
        """Max duration should be 10 seconds."""
        from core.audiox_synthesizer import _MAX_DURATION
        assert _MAX_DURATION == 10.0


# ── Video Frame Extraction ─────────────────────────────────────────


class TestVideoFrameExtraction:
    """Test the FFmpeg-based video frame extraction function."""

    def test_extract_function_exists(self):
        """_extract_video_frames should be importable."""
        from core.audiox_synthesizer import _extract_video_frames
        assert callable(_extract_video_frames)


# ── VRAM & Offloading ──────────────────────────────────────────────


class TestAudioXVRAM:
    """Test VRAM management functions."""

    def test_cleanup_when_no_models_loaded(self):
        """cleanup should be safe to call when no models are loaded."""
        from core.audiox_synthesizer import cleanup
        # Should not raise
        cleanup()

    def test_cleanup_resets_global_state(self):
        """cleanup should reset the global _models to None."""
        import core.audiox_synthesizer as synth
        synth._models = None  # Ensure clean state
        synth.cleanup()  # Should be idempotent
        assert synth._models is None


# ── License Notice ──────────────────────────────────────────────────


class TestLicenseNotice:
    """Verify the license notice logging."""

    def test_license_logged_once(self):
        """License notice should only be logged once per session."""
        import core.audiox_synthesizer as synth
        # Reset the flag
        synth._license_logged = False
        synth._log_license_notice()
        assert synth._license_logged is True
        # Second call should be a no-op (no error)
        synth._log_license_notice()
        assert synth._license_logged is True
