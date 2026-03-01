"""Tests for model_manager mirror download and registry."""

import os
import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path

# Import from project
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.model_manager import (
    _MODEL_INFO,
    try_mirror_download,
)


class TestModelInfoRegistry(unittest.TestCase):
    """Verify _MODEL_INFO has correct mirror fields."""

    def test_all_models_have_mirror_repo(self):
        """Every model in _MODEL_INFO should have a mirror_repo field."""
        for key, info in _MODEL_INFO.items():
            self.assertIn(
                "mirror_repo", info,
                f"Model '{key}' missing 'mirror_repo' field",
            )
            self.assertTrue(
                info["mirror_repo"].startswith("AEmotionStudio/"),
                f"Mirror repo for '{key}' should be under AEmotionStudio org",
            )

    def test_lama_has_mirror_filename(self):
        """LaMa should specify its mirror filename."""
        self.assertEqual(
            _MODEL_INFO["lama"]["mirror_filename"],
            "big-lama.pt",
        )

    def test_urls_point_to_aemotionstudio(self):
        """Model URLs should point to AEmotionStudio HuggingFace repos."""
        for key in ("lama", "whisper"):
            self.assertIn(
                "AEmotionStudio",
                _MODEL_INFO[key]["url"],
                f"URL for '{key}' should reference AEmotionStudio",
            )


class TestTryMirrorDownload(unittest.TestCase):
    """Verify try_mirror_download fallback behaviour."""

    @patch("core.model_manager.log")
    def test_returns_none_for_unknown_model_key(self, mock_log):
        """Unknown model key should return None immediately."""
        result = try_mirror_download("nonexistent", "file.pt", "/tmp")
        self.assertIsNone(result)

    @patch("core.model_manager.log")
    def test_returns_none_when_hf_hub_not_installed(self, mock_log):
        """Should return None if huggingface_hub is not installed."""
        with patch.dict("sys.modules", {"huggingface_hub": None}):
            result = try_mirror_download("lama", "big-lama.pt", "/tmp")
            self.assertIsNone(result)

    @patch("core.model_manager.log")
    def test_returns_none_on_download_failure(self, mock_log):
        """Should return None when download raises an exception."""
        with patch("huggingface_hub.hf_hub_download", side_effect=Exception("network error")):
            result = try_mirror_download("lama", "big-lama.pt", "/tmp/test_mirror")
            self.assertIsNone(result)

    @patch("core.model_manager.log")
    def test_returns_path_on_success(self, mock_log):
        """Should return the path when download succeeds."""
        expected_path = "/tmp/test_mirror/big-lama.pt"
        with patch("huggingface_hub.hf_hub_download", return_value=expected_path):
            result = try_mirror_download("lama", "big-lama.pt", "/tmp/test_mirror")
            self.assertEqual(result, expected_path)

    @patch("core.model_manager.log")
    def test_whisper_mirror_repo_correct(self, mock_log):
        """Whisper mirror repo should be AEmotionStudio/whisper-models."""
        self.assertEqual(
            _MODEL_INFO["whisper"]["mirror_repo"],
            "AEmotionStudio/whisper-models",
        )


if __name__ == "__main__":
    unittest.main()
