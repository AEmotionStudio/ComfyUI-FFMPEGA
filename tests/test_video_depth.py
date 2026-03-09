# coding: utf-8
"""Tests for Video Depth Anything integration."""

import sys
import os
from unittest.mock import patch, MagicMock

import pytest

# Ensure project root is on sys.path
_proj = os.path.dirname(os.path.dirname(__file__))
if _proj not in sys.path:
    sys.path.insert(0, _proj)

from skills.registry import get_registry, SkillCategory


# ------------------------------------------------------------------ #
#  Skill registration
# ------------------------------------------------------------------ #

class TestVideoDepthSkillRegistration:
    """Verify the video_depth skill is in the global registry."""

    def test_skill_exists_in_registry(self):
        registry = get_registry()
        skill = registry.get("video_depth")
        assert skill is not None

    def test_skill_category_is_ai_visual(self):
        registry = get_registry()
        skill = registry.get("video_depth")
        assert skill.category == SkillCategory.AI_VISUAL

    def test_skill_has_encoder_param(self):
        registry = get_registry()
        skill = registry.get("video_depth")
        params = {p.name: p for p in skill.parameters}
        assert "encoder" in params
        assert params["encoder"].default == "vits"

    def test_skill_has_input_size_param(self):
        registry = get_registry()
        skill = registry.get("video_depth")
        params = {p.name: p for p in skill.parameters}
        assert "input_size" in params
        assert params["input_size"].default == 518

    def test_skill_has_max_res_param(self):
        registry = get_registry()
        skill = registry.get("video_depth")
        params = {p.name: p for p in skill.parameters}
        assert "max_res" in params
        assert params["max_res"].default == 1280

    def test_skill_tags_include_key_terms(self):
        registry = get_registry()
        skill = registry.get("video_depth")
        for tag in ("video_depth", "temporal", "consistent", "depth"):
            assert tag in skill.tags

    def test_skill_has_examples(self):
        registry = get_registry()
        skill = registry.get("video_depth")
        assert len(skill.examples) > 0


# ------------------------------------------------------------------ #
#  Handler
# ------------------------------------------------------------------ #

class TestVideoDepthHandler:
    """Unit tests for the _f_video_depth handler."""

    def test_missing_input_returns_error(self):
        from skills.handlers.video_depth import _f_video_depth
        result = _f_video_depth({"_input_path": "", "encoder": "vits"})
        assert "error" in result

    @patch("skills.handlers.video_depth.os.path.isfile", return_value=True)
    def test_invalid_encoder_returns_error(self, mock_isfile):
        from skills.handlers.video_depth import _f_video_depth
        result = _f_video_depth({
            "_input_path": "/tmp/test.mp4",
            "encoder": "invalid_encoder",
        })
        assert "error" in result
        assert "encoder" in result["error"].lower()

    @patch("skills.handlers.video_depth.os.path.isfile", return_value=True)
    def test_success_returns_movie(self, mock_isfile):
        from skills.handlers.video_depth import _f_video_depth
        with patch("core.vda_synthesizer.run_video_depth", return_value="/tmp/out.mp4"):
            result = _f_video_depth({
                "_input_path": "/tmp/test.mp4",
                "encoder": "vits",
            })
        assert "movie" in result
        assert result["movie"] == "/tmp/out.mp4"

    @patch("skills.handlers.video_depth.os.path.isfile", return_value=True)
    def test_default_encoder_is_vits(self, mock_isfile):
        from skills.handlers.video_depth import _f_video_depth
        with patch("core.vda_synthesizer.run_video_depth", return_value="/tmp/out.mp4") as mock_run:
            _f_video_depth({"_input_path": "/tmp/test.mp4"})
            mock_run.assert_called_once()
            assert mock_run.call_args[1]["encoder"] == "vits"


# ------------------------------------------------------------------ #
#  Dispatch table
# ------------------------------------------------------------------ #

class TestVideoDepthDispatch:
    """Verify video_depth is in the dispatch table."""

    def test_video_depth_in_dispatch(self):
        from skills.composer import _get_dispatch
        dispatch = _get_dispatch()
        assert "video_depth" in dispatch

    def test_dispatch_aliases_point_to_same_handler(self):
        from skills.composer import _get_dispatch
        dispatch = _get_dispatch()
        handler = dispatch["video_depth"]
        for alias in ("video_depth_map", "temporal_depth", "consistent_depth",
                       "vda", "vda_depth"):
            assert dispatch[alias] is handler


# ------------------------------------------------------------------ #
#  Aliases
# ------------------------------------------------------------------ #

class TestVideoDepthAliases:
    """Verify SKILL_ALIASES resolve correctly."""

    def test_aliases_resolve_to_video_depth(self):
        from skills.composer import SkillComposer
        aliases = SkillComposer.SKILL_ALIASES
        for alias in ("video_depth_map", "temporal_depth", "consistent_depth",
                       "vda", "vda_depth"):
            assert aliases[alias] == "video_depth"


# ------------------------------------------------------------------ #
#  Model manager
# ------------------------------------------------------------------ #

class TestVideoDepthModelManager:
    """Verify model info for video_depth."""

    def test_model_info_exists(self):
        from core.model_manager import _MODEL_INFO
        assert "video_depth" in _MODEL_INFO

    def test_model_info_has_required_fields(self):
        from core.model_manager import _MODEL_INFO
        info = _MODEL_INFO["video_depth"]
        for field in ("name", "size", "url", "license", "manual"):
            assert field in info, f"Missing field: {field}"

    def test_model_info_name(self):
        from core.model_manager import _MODEL_INFO
        assert "Video Depth" in _MODEL_INFO["video_depth"]["name"]


# ------------------------------------------------------------------ #
#  Module imports
# ------------------------------------------------------------------ #

class TestVideoDepthModuleImport:
    """Verify core modules can be imported."""

    def test_synthesizer_module_importable(self):
        from core import vda_synthesizer
        assert hasattr(vda_synthesizer, "run_video_depth")
        assert hasattr(vda_synthesizer, "cleanup")
        assert hasattr(vda_synthesizer, "MODEL_CONFIGS")

    def test_model_configs_complete(self):
        from core.vda_synthesizer import MODEL_CONFIGS
        for encoder in ("vits", "vitb", "vitl"):
            assert encoder in MODEL_CONFIGS
            cfg = MODEL_CONFIGS[encoder]
            assert "hf_repo" in cfg
            assert "mirror_repo" in cfg
            assert "filename" in cfg

    def test_model_configs_have_mirror_repos(self):
        from core.vda_synthesizer import MODEL_CONFIGS
        for encoder, cfg in MODEL_CONFIGS.items():
            assert "AEmotionStudio" in cfg["mirror_repo"]

    def test_handler_importable(self):
        from skills.handlers.video_depth import _f_video_depth
        assert callable(_f_video_depth)

    def test_vendored_model_importable(self):
        from core.video_depth_anything.video_depth import VideoDepthAnything
        assert callable(VideoDepthAnything)
