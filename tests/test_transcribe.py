"""Tests for Whisper transcription integration.

Tests for:
- core/whisper_transcriber.py (SRT/ASS generation, model path)
- skills/handlers/transcribe.py (handler functions)
- Skill registry and dispatch table entries
"""

import json
import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

# Ensure project root is on sys.path
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)


# ── SRT generation tests ─────────────────────────────────────────────────


class TestSegmentsToSrt(unittest.TestCase):
    """Test segments_to_srt conversion."""

    def test_basic_segments(self):
        from core.whisper_transcriber import segments_to_srt

        segments = [
            {"start": 0.0, "end": 2.5, "text": "Hello world"},
            {"start": 3.0, "end": 5.0, "text": "How are you"},
        ]
        srt = segments_to_srt(segments)
        assert "1\n00:00:00,000 --> 00:00:02,500\nHello world" in srt
        assert "2\n00:00:03,000 --> 00:00:05,000\nHow are you" in srt

    def test_empty_segments(self):
        from core.whisper_transcriber import segments_to_srt

        assert segments_to_srt([]) == ""

    def test_long_timestamp(self):
        """Verify timestamps over 1 hour format correctly."""
        from core.whisper_transcriber import segments_to_srt

        segments = [{"start": 3661.5, "end": 3665.0, "text": "Late"}]
        srt = segments_to_srt(segments)
        assert "01:01:01,500" in srt

    def test_srt_index_starts_at_one(self):
        from core.whisper_transcriber import segments_to_srt

        segments = [{"start": 0, "end": 1, "text": "First"}]
        srt = segments_to_srt(segments)
        assert srt.startswith("1\n")


# ── ASS karaoke generation tests ─────────────────────────────────────────


class TestWordsToKaraokeAss(unittest.TestCase):
    """Test ASS karaoke subtitle generation."""

    def test_basic_karaoke(self):
        from core.whisper_transcriber import words_to_karaoke_ass

        words = [
            {"start": 0.0, "end": 0.5, "word": "Hello"},
            {"start": 0.6, "end": 1.0, "word": "world"},
        ]
        ass = words_to_karaoke_ass(words)
        assert "[Script Info]" in ass
        assert "[V4+ Styles]" in ass
        assert "[Events]" in ass
        assert "\\kf" in ass
        assert "Hello" in ass
        assert "world" in ass

    def test_empty_words(self):
        from core.whisper_transcriber import words_to_karaoke_ass

        assert words_to_karaoke_ass([]) == ""

    def test_custom_colors(self):
        from core.whisper_transcriber import words_to_karaoke_ass

        words = [{"start": 0, "end": 1, "word": "Test"}]
        ass = words_to_karaoke_ass(words, fill_color="cyan", base_color="gray")
        assert "&H00FFFF00" in ass  # cyan in BGR
        assert "&H00808080" in ass  # gray in BGR

    def test_hex_color_support(self):
        from core.whisper_transcriber import words_to_karaoke_ass

        words = [{"start": 0, "end": 1, "word": "Test"}]
        ass = words_to_karaoke_ass(words, fill_color="#FF0000")
        # #FF0000 (red) → &H000000FF in ASS BGR
        assert "&H000000FF" in ass

    def test_karaoke_timing_centiseconds(self):
        """\\kf duration should be in centiseconds."""
        from core.whisper_transcriber import words_to_karaoke_ass

        words = [{"start": 0.0, "end": 1.5, "word": "Long"}]
        ass = words_to_karaoke_ass(words)
        # 1.5 seconds = 150 centiseconds
        assert "\\kf150" in ass

    def test_word_grouping_by_gap(self):
        """Words separated by >1s gap should be on separate lines."""
        from core.whisper_transcriber import _group_words_into_lines

        words = [
            {"start": 0.0, "end": 0.5, "word": "Hello"},
            {"start": 2.0, "end": 2.5, "word": "world"},  # 1.5s gap
        ]
        lines = _group_words_into_lines(words)
        assert len(lines) == 2

    def test_word_grouping_by_count(self):
        """Lines should break at max_words_per_line."""
        from core.whisper_transcriber import _group_words_into_lines

        words = [
            {"start": i * 0.3, "end": (i + 1) * 0.3, "word": f"w{i}"}
            for i in range(12)
        ]
        lines = _group_words_into_lines(words, max_words_per_line=5)
        assert len(lines) >= 2
        assert all(len(line) <= 5 for line in lines)


# ── Handler tests (mocked Whisper) ───────────────────────────────────────


class TestAutoTranscribeHandler(unittest.TestCase):
    """Test _f_auto_transcribe handler with mocked Whisper."""

    @patch("os.path.isfile", return_value=True)
    @patch("core.whisper_transcriber.transcribe_audio")
    def test_produces_subtitle_filter(self, mock_transcribe, _mock_isfile):
        from core.whisper_transcriber import TranscriptionResult
        from skills.handlers.transcribe import _f_auto_transcribe

        mock_transcribe.return_value = TranscriptionResult(
            segments=[{"start": 0.0, "end": 2.0, "text": "Hello"}],
            words=[],
            language="en",
            full_text="Hello",
        )

        result = _f_auto_transcribe({"_input_path": "/tmp/test.mp4"})
        vf, af, opts = result[:3]
        assert len(vf) == 1
        assert "subtitles=" in vf[0]

    @patch("os.path.isfile", return_value=True)
    @patch("core.whisper_transcriber.transcribe_audio")
    def test_no_speech_returns_empty(self, mock_transcribe, _mock_isfile):
        from core.whisper_transcriber import TranscriptionResult
        from skills.handlers.transcribe import _f_auto_transcribe

        mock_transcribe.return_value = TranscriptionResult()

        result = _f_auto_transcribe({"_input_path": "/tmp/test.mp4"})
        vf, af, opts = result[:3]
        assert len(vf) == 0

    def test_missing_input_path_raises(self):
        from skills.handlers.transcribe import _f_auto_transcribe

        with self.assertRaises(ValueError):
            _f_auto_transcribe({})

    @patch("os.path.isfile", return_value=True)
    @patch("core.whisper_transcriber.transcribe_multi_video")
    def test_multi_video_calls_transcribe_multi(self, mock_multi, _mock_isfile):
        """When extra inputs are present, should use transcribe_multi_video."""
        from core.whisper_transcriber import TranscriptionResult
        from skills.handlers.transcribe import _f_auto_transcribe

        mock_multi.return_value = TranscriptionResult(
            segments=[
                {"start": 0.0, "end": 2.0, "text": "First clip"},
                {"start": 8.0, "end": 10.0, "text": "Second clip"},
            ],
            words=[], language="en", full_text="First clip Second clip",
        )

        result = _f_auto_transcribe({
            "_input_path": "/tmp/video_a.mp4",
            "_extra_input_paths": ["/tmp/video_b.mp4"],
        })
        vf, af, opts = result[:3]
        assert len(vf) == 1
        assert "subtitles=" in vf[0]
        # Verify it called multi-video, not single
        mock_multi.assert_called_once()
        paths_arg = mock_multi.call_args[0][0]
        assert len(paths_arg) == 2


class TestKaraokeSubtitlesHandler(unittest.TestCase):
    """Test _f_karaoke_subtitles handler with mocked Whisper."""

    @patch("os.path.isfile", return_value=True)
    @patch("core.whisper_transcriber.transcribe_audio")
    def test_produces_ass_filter(self, mock_transcribe, _mock_isfile):
        from core.whisper_transcriber import TranscriptionResult
        from skills.handlers.transcribe import _f_karaoke_subtitles

        mock_transcribe.return_value = TranscriptionResult(
            segments=[{"start": 0.0, "end": 2.0, "text": "Hello world"}],
            words=[
                {"start": 0.0, "end": 0.5, "word": "Hello"},
                {"start": 0.6, "end": 1.0, "word": "world"},
            ],
            language="en",
            full_text="Hello world",
        )

        result = _f_karaoke_subtitles({"_input_path": "/tmp/test.mp4"})
        vf, af, opts = result[:3]
        assert len(vf) == 1
        assert "ass=" in vf[0]

    @patch("os.path.isfile", return_value=True)
    @patch("core.whisper_transcriber.transcribe_audio")
    def test_no_words_returns_empty(self, mock_transcribe, _mock_isfile):
        from core.whisper_transcriber import TranscriptionResult
        from skills.handlers.transcribe import _f_karaoke_subtitles

        mock_transcribe.return_value = TranscriptionResult()

        result = _f_karaoke_subtitles({"_input_path": "/tmp/test.mp4"})
        vf, af, opts = result[:3]
        assert len(vf) == 0


# ── Registry & dispatch tests ────────────────────────────────────────────


class TestTranscribeSkillRegistry(unittest.TestCase):
    """Verify skills are registered and dispatch entries exist."""

    def test_auto_transcribe_registered(self):
        from skills.registry import get_registry

        registry = get_registry()
        skill = registry.get("auto_transcribe")
        assert skill is not None
        assert skill.name == "auto_transcribe"

    def test_karaoke_subtitles_registered(self):
        from skills.registry import get_registry

        registry = get_registry()
        skill = registry.get("karaoke_subtitles")
        assert skill is not None
        assert skill.name == "karaoke_subtitles"

    def test_auto_transcribe_tags(self):
        from skills.registry import get_registry

        registry = get_registry()
        skill = registry.get("auto_transcribe")
        assert "whisper" in skill.tags
        assert "transcribe" in skill.tags

    def test_dispatch_entries(self):
        from skills.composer import _get_dispatch

        dispatch = _get_dispatch()
        assert "auto_transcribe" in dispatch
        assert "transcribe" in dispatch
        assert "speech_to_text" in dispatch
        assert "karaoke_subtitles" in dispatch

    def test_skill_aliases(self):
        from skills.composer import SkillComposer

        aliases = SkillComposer.SKILL_ALIASES
        assert aliases.get("auto_subtitle") == "auto_transcribe"
        assert aliases.get("auto_caption") == "auto_transcribe"
        assert aliases.get("whisper") == "auto_transcribe"
        assert aliases.get("speech_to_text") == "auto_transcribe"


# ── Model path tests ────────────────────────────────────────────────────


class TestWhisperModelDir(unittest.TestCase):
    """Test model download directory resolution."""

    @patch("os.makedirs")
    @patch.dict("sys.modules", {"folder_paths": MagicMock(models_dir="/mock/models")})
    def test_uses_comfyui_models_dir(self, mock_makedirs):
        # Need to reimport after patching
        import importlib
        import core.whisper_transcriber as wt
        importlib.reload(wt)

        model_dir = wt._get_whisper_model_dir()
        assert model_dir == "/mock/models/whisper"
        mock_makedirs.assert_called_once_with("/mock/models/whisper", exist_ok=True)

        # Restore
        importlib.reload(wt)

    def test_fallback_without_folder_paths(self):
        """Without folder_paths, should fall back to extension models dir."""
        import importlib
        import core.whisper_transcriber as wt

        # Temporarily hide folder_paths to trigger the fallback
        with patch.dict("sys.modules", {"folder_paths": None}):
            importlib.reload(wt)
            model_dir = wt._get_whisper_model_dir()
            assert "whisper" in model_dir
            assert os.path.isdir(model_dir)

        # Restore
        importlib.reload(wt)


if __name__ == "__main__":
    unittest.main()
