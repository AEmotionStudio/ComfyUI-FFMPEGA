"""Tests for the Fish Speech synthesizer module.

Covers module API surface, model directory resolution,
voice library, emotion tags, and VRAM management.
"""

import pytest
from unittest.mock import patch, MagicMock
import os


# ── Module API Surface ────────────────────────────────────────────


class TestFishSpeechAPI:
    """Verify the Fish Speech synthesizer exports the expected API."""

    def test_generate_speech_importable(self):
        """generate_speech should be importable from the synthesizer."""
        from core.fish_speech_synthesizer import generate_speech
        assert callable(generate_speech)

    def test_clone_voice_importable(self):
        """clone_voice should be importable."""
        from core.fish_speech_synthesizer import clone_voice
        assert callable(clone_voice)

    def test_list_voices_importable(self):
        """list_voices should be importable."""
        from core.fish_speech_synthesizer import list_voices
        assert callable(list_voices)

    def test_load_models_importable(self):
        """load_models should be importable."""
        from core.fish_speech_synthesizer import load_models
        assert callable(load_models)

    def test_cleanup_importable(self):
        """cleanup should be importable."""
        from core.fish_speech_synthesizer import cleanup
        assert callable(cleanup)

    def test_unload_models_importable(self):
        """unload_models should be importable."""
        from core.fish_speech_synthesizer import unload_models
        assert callable(unload_models)


# ── Model Repos & Constants ───────────────────────────────────────


class TestFishSpeechModelConstants:
    """Verify model file constants and repo pointers."""

    def test_hf_repo_fp8(self):
        """FP8 HF repo should point to AEmotionStudio mirror."""
        from core.fish_speech_synthesizer import _HF_REPO_FP8
        assert "AEmotionStudio" in _HF_REPO_FP8
        assert "fp8" in _HF_REPO_FP8

    def test_hf_repo_bf16(self):
        """BF16 HF repo should point to AEmotionStudio mirror."""
        from core.fish_speech_synthesizer import _HF_REPO_BF16
        assert "AEmotionStudio" in _HF_REPO_BF16

    def test_upstream_repo(self):
        """Upstream repo should point to fishaudio/s2-pro."""
        from core.fish_speech_synthesizer import _HF_UPSTREAM
        assert "fishaudio" in _HF_UPSTREAM
        assert "s2-pro" in _HF_UPSTREAM

    def test_model_files_dict(self):
        """_MODEL_FILES should contain expected keys."""
        from core.fish_speech_synthesizer import _MODEL_FILES
        expected = {"model", "codec", "config", "tokenizer", "tokenizer_config"}
        assert expected == set(_MODEL_FILES.keys())

    def test_model_filename(self):
        """Model filename should be model.safetensors."""
        from core.fish_speech_synthesizer import _MODEL_FILES
        assert _MODEL_FILES["model"] == "model.safetensors"

    def test_codec_filename(self):
        """Codec filename should be codec.pth."""
        from core.fish_speech_synthesizer import _MODEL_FILES
        assert _MODEL_FILES["codec"] == "codec.pth"

    def test_model_variants(self):
        """Both fp8 and bf16 variants should be defined."""
        from core.fish_speech_synthesizer import _MODEL_VARIANTS
        assert "fp8" in _MODEL_VARIANTS
        assert "bf16" in _MODEL_VARIANTS

    def test_default_variant(self):
        """Default variant should be bf16."""
        from core.fish_speech_synthesizer import _DEFAULT_VARIANT
        assert _DEFAULT_VARIANT == "bf16"


# ── Emotion Tags ──────────────────────────────────────────────────


class TestEmotionTags:
    """Verify the curated emotion tag list."""

    def test_tags_list_exists(self):
        """EMOTION_TAGS should be a non-empty list."""
        from core.fish_speech_synthesizer import EMOTION_TAGS
        assert isinstance(EMOTION_TAGS, list)
        assert len(EMOTION_TAGS) > 0

    def test_first_tag_is_empty(self):
        """First tag should be empty string (no emotion)."""
        from core.fish_speech_synthesizer import EMOTION_TAGS
        assert EMOTION_TAGS[0] == ""

    def test_known_tags_present(self):
        """Essential emotion tags should be present."""
        from core.fish_speech_synthesizer import EMOTION_TAGS
        expected = {
            "[happy]", "[sad]", "[angry]", "[excited]",
            "[whisper]", "[singing]", "[laughing]", "[pause]",
        }
        for tag in expected:
            assert tag in EMOTION_TAGS, f"Missing emotion tag: {tag}"

    def test_tags_format(self):
        """Non-empty tags should be enclosed in brackets."""
        from core.fish_speech_synthesizer import EMOTION_TAGS
        for tag in EMOTION_TAGS:
            if tag:  # skip empty
                assert tag.startswith("["), f"Tag should start with [: {tag}"
                assert tag.endswith("]"), f"Tag should end with ]: {tag}"


# ── Voice Library ─────────────────────────────────────────────────


class TestVoiceLibrary:
    """Test voice reference library functions."""

    def test_list_voices_returns_list(self):
        """list_voices should return a list."""
        from core.fish_speech_synthesizer import list_voices
        result = list_voices()
        assert isinstance(result, list)

    def test_voice_audio_path_returns_none_for_unknown(self):
        """_get_voice_audio_path should return None for unknown voices."""
        from core.fish_speech_synthesizer import _get_voice_audio_path
        result = _get_voice_audio_path("__nonexistent_voice__")
        assert result is None

    def test_voice_transcript_returns_none_for_unknown(self):
        """_get_voice_transcript should return None for unknown voices."""
        from core.fish_speech_synthesizer import _get_voice_transcript
        result = _get_voice_transcript("__nonexistent_voice__")
        assert result is None


# ── FP8 Dequantization ────────────────────────────────────────────


class TestFP8Dequantization:
    """Test FP8 dequantization logic."""

    def test_passthrough_when_no_scales(self):
        """State dict without .scale keys should pass through unchanged."""
        torch = pytest.importorskip("torch")
        from core.fish_speech_synthesizer import _dequantize_fp8_state_dict

        state_dict = {
            "layer.weight": torch.randn(4, 4, dtype=torch.bfloat16),
            "layer.bias": torch.randn(4, dtype=torch.bfloat16),
        }
        result = _dequantize_fp8_state_dict(state_dict)
        assert "layer.weight" in result
        assert "layer.bias" in result

    def test_dequantize_with_scales(self):
        """FP8 weights should be dequantized when .scale keys present."""
        torch = pytest.importorskip("torch")
        from core.fish_speech_synthesizer import _dequantize_fp8_state_dict

        # Simulate FP8 quantized weight + scale
        w_bf16 = torch.randn(4, 8, dtype=torch.bfloat16)
        scale = w_bf16.abs().amax(dim=1, keepdim=True) / 448.0
        w_fp8 = (w_bf16 / scale).to(torch.float8_e4m3fn)

        state_dict = {
            "layer.weight": w_fp8,
            "layer.weight.scale": scale.float(),
            "norm.weight": torch.randn(4, dtype=torch.bfloat16),
        }

        result = _dequantize_fp8_state_dict(state_dict)

        # Scale key should be removed
        assert "layer.weight.scale" not in result
        # Weight should be dequantized — dtype may be float32 due to
        # bf16 * float32 promotion (load_state_dict handles final dtype)
        assert result["layer.weight"].dtype in (torch.bfloat16, torch.float32)
        # Non-scaled weights preserved
        assert "norm.weight" in result

    def test_extract_scale_weights(self):
        """Scale keys should be extracted and reformatted for convert_fp8_linear."""
        torch = pytest.importorskip("torch")
        from core.fish_speech_synthesizer import _extract_scale_weights

        state_dict = {
            "layers.0.attn.wq.weight": torch.randn(4, 4, dtype=torch.bfloat16).to(torch.float8_e4m3fn),
            "layers.0.attn.wq.weight.scale": torch.tensor([1.5]),
            "layers.0.attn.wk.weight": torch.randn(4, 4, dtype=torch.bfloat16).to(torch.float8_e4m3fn),
            "layers.0.attn.wk.weight.scale": torch.tensor([2.0]),
            "norm.weight": torch.randn(4, dtype=torch.bfloat16),
        }

        scale_weights = _extract_scale_weights(state_dict)

        # Scale keys should be extracted and removed from state_dict
        assert "layers.0.attn.wq.weight.scale" not in state_dict
        assert "layers.0.attn.wk.weight.scale" not in state_dict
        # Reformatted keys should be in scale_weights
        assert "layers.0.attn.wq.scale_weight" in scale_weights
        assert "layers.0.attn.wk.scale_weight" in scale_weights
        # Original weights and non-scaled tensors should remain
        assert "layers.0.attn.wq.weight" in state_dict
        assert "norm.weight" in state_dict

    def test_supports_fp8_matmul(self):
        """_supports_fp8_matmul should return a boolean."""
        from core.fish_speech_synthesizer import _supports_fp8_matmul
        result = _supports_fp8_matmul()
        assert isinstance(result, bool)


# ── VRAM & Offloading ──────────────────────────────────────────────


class TestFishSpeechVRAM:
    """Test VRAM management functions."""

    def test_cleanup_when_no_models_loaded(self):
        """cleanup should be safe to call when no models are loaded."""
        from core.fish_speech_synthesizer import cleanup
        cleanup()

    def test_cleanup_resets_global_state(self):
        """cleanup should reset the global _models."""
        import core.fish_speech_synthesizer as synth
        synth._models = {}
        synth._active_variant = ""
        synth.cleanup()
        assert synth._models == {} or not synth._models


# ── License Notice ──────────────────────────────────────────────────


class TestLicenseNotice:
    """Verify the license notice logging."""

    def test_license_logged_once(self):
        """License notice should only be logged once per session."""
        import core.fish_speech_synthesizer as synth
        synth._license_logged = False
        synth._log_license_notice()
        assert synth._license_logged is True
        # Second call should be a no-op
        synth._log_license_notice()
        assert synth._license_logged is True


# ── Long-Form Text Splitting ──────────────────────────────────────


class TestTextSplitting:
    """Test sentence-aware text splitting for long-form TTS."""

    def test_count_words_empty(self):
        """Empty text should return 0 words."""
        from core.fish_speech_synthesizer import _count_words
        assert _count_words("") == 0
        assert _count_words("   ") == 0

    def test_count_words_english(self):
        """English words should be counted correctly."""
        from core.fish_speech_synthesizer import _count_words
        assert _count_words("Hello world") == 2
        assert _count_words("The quick brown fox jumps") == 5

    def test_count_words_cjk(self):
        """CJK characters should each count as one word."""
        from core.fish_speech_synthesizer import _count_words
        assert _count_words("你好世界") == 4
        # Mixed: 2 CJK + 1 Western
        assert _count_words("Hello 你好") == 3

    def test_split_empty(self):
        """Empty text should return empty list."""
        from core.fish_speech_synthesizer import _split_text_into_chunks
        assert _split_text_into_chunks("") == []
        assert _split_text_into_chunks("  ") == []

    def test_split_short_text(self):
        """Text under the limit should return as a single chunk."""
        from core.fish_speech_synthesizer import _split_text_into_chunks
        result = _split_text_into_chunks("Hello world.", max_words_per_chunk=200)
        assert len(result) == 1

    def test_split_respects_sentences(self):
        """Chunks should break at sentence boundaries."""
        from core.fish_speech_synthesizer import _split_text_into_chunks
        text = "First sentence. Second sentence. Third sentence."
        result = _split_text_into_chunks(text, max_words_per_chunk=3)
        assert len(result) >= 2
        # Each chunk should end with a sentence
        for chunk in result:
            assert chunk.strip()

    def test_split_long_sentence_standalone(self):
        """A single sentence exceeding the limit gets its own chunk."""
        from core.fish_speech_synthesizer import _split_text_into_chunks
        long_sent = " ".join(["word"] * 50)
        text = f"Short. {long_sent}. Another short."
        result = _split_text_into_chunks(text, max_words_per_chunk=10)
        # The long sentence should be in its own chunk
        assert any(len(chunk.split()) >= 50 for chunk in result)


# ── Audio Crossfade ──────────────────────────────────────────────


class TestCrossfadeConcat:
    """Test audio segment crossfade stitching."""

    def test_empty_segments(self):
        """Empty list should return empty array."""
        import numpy as np
        from core.fish_speech_synthesizer import _crossfade_concat
        result = _crossfade_concat([], sample_rate=44100)
        assert len(result) == 0

    def test_single_segment(self):
        """Single segment should be returned as-is."""
        import numpy as np
        from core.fish_speech_synthesizer import _crossfade_concat
        seg = np.ones(1000, dtype=np.float32)
        result = _crossfade_concat([seg], sample_rate=44100)
        np.testing.assert_array_equal(result, seg)

    def test_two_segments_crossfade(self):
        """Two segments should be joined with crossfade."""
        import numpy as np
        from core.fish_speech_synthesizer import _crossfade_concat
        seg1 = np.ones(5000, dtype=np.float32)
        seg2 = np.ones(5000, dtype=np.float32) * 0.5
        result = _crossfade_concat([seg1, seg2], sample_rate=44100, crossfade_ms=100)
        # Result should be shorter than sum due to overlap
        xfade_samples = int(44100 * 100 / 1000)
        assert len(result) == len(seg1) + len(seg2) - xfade_samples

    def test_no_crossfade(self):
        """With crossfade_ms=0, segments should be simply concatenated."""
        import numpy as np
        from core.fish_speech_synthesizer import _crossfade_concat
        seg1 = np.ones(100, dtype=np.float32)
        seg2 = np.ones(100, dtype=np.float32) * 2
        result = _crossfade_concat([seg1, seg2], sample_rate=44100, crossfade_ms=0)
        assert len(result) == 200


# ── Expanded Tags ──────────────────────────────────────────────────


class TestExpandedTags:
    """Test the expanded emotion tag list from upstream."""

    def test_tag_count(self):
        """Should have 46+ tags (including empty)."""
        from core.fish_speech_synthesizer import EMOTION_TAGS
        assert len(EMOTION_TAGS) >= 46

    def test_new_upstream_tags_present(self):
        """Tags from the upstream README should be present."""
        from core.fish_speech_synthesizer import EMOTION_TAGS
        new_tags = {
            "[laughing tone]", "[chuckling]", "[chuckle]",
            "[short pause]", "[inhale]", "[exhale]", "[tsk]",
            "[shocked]", "[delight]", "[interrupting]",
            "[low voice]", "[volume up]", "[volume down]",
            "[echo]", "[panting]", "[clearing throat]",
            "[audience laughter]", "[with strong accent]",
        }
        for tag in new_tags:
            assert tag in EMOTION_TAGS, f"Missing upstream tag: {tag}"
