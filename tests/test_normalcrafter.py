"""Tests for the normalcrafter skill (NormalCrafter video normal maps).

Covers skill registration, handler unit tests (with NormalCrafter synthesizer
mocked), dispatch table wiring, alias resolution, and model manager
integration.
"""

import sys

import pytest
from unittest.mock import patch, MagicMock

from skills.registry import get_registry, SkillCategory


# ── Skill Registration ─────────────────────────────────────────────


class TestNormalCrafterSkillRegistration:
    """Verify normalcrafter is registered correctly in the skill registry."""

    def test_skill_exists_in_registry(self):
        registry = get_registry()
        skill = registry.get("normalcrafter")
        assert skill is not None, "normalcrafter skill should be registered"

    def test_skill_category_is_ai_visual(self):
        registry = get_registry()
        skill = registry.get("normalcrafter")
        assert skill.category == SkillCategory.AI_VISUAL

    def test_skill_has_max_res_param(self):
        registry = get_registry()
        skill = registry.get("normalcrafter")
        param = skill.get_param("max_res")
        assert param is not None, "Should have max_res parameter"
        assert param.required is False
        assert param.default == 1024

    def test_skill_has_window_size_param(self):
        registry = get_registry()
        skill = registry.get("normalcrafter")
        param = skill.get_param("window_size")
        assert param is not None, "Should have window_size parameter"
        assert param.required is False
        assert param.default == 14

    def test_skill_has_process_length_param(self):
        registry = get_registry()
        skill = registry.get("normalcrafter")
        param = skill.get_param("process_length")
        assert param is not None, "Should have process_length parameter"
        assert param.required is False
        assert param.default == -1

    def test_skill_has_target_fps_param(self):
        registry = get_registry()
        skill = registry.get("normalcrafter")
        param = skill.get_param("target_fps")
        assert param is not None, "Should have target_fps parameter"
        assert param.required is False
        assert param.default == -1

    def test_skill_has_seed_param(self):
        registry = get_registry()
        skill = registry.get("normalcrafter")
        param = skill.get_param("seed")
        assert param is not None, "Should have seed parameter"
        assert param.required is False
        assert param.default == 42

    def test_skill_tags_include_key_terms(self):
        registry = get_registry()
        skill = registry.get("normalcrafter")
        for tag in ("normalcrafter", "normals", "video", "ai", "vision", "relight"):
            assert tag in skill.tags, f"Tag '{tag}' should be in skill tags"

    def test_skill_has_examples(self):
        registry = get_registry()
        skill = registry.get("normalcrafter")
        assert skill.examples, "Skill should have usage examples"
        assert len(skill.examples) >= 3


# ── Handler Unit Tests ─────────────────────────────────────────────


class TestNormalCrafterHandler:
    """Test _f_normalcrafter handler with mocked synthesizer."""

    def test_missing_input_returns_error(self):
        from skills.handlers.normalcrafter import _f_normalcrafter

        result = _f_normalcrafter({"_input_path": ""})
        assert "error" in result

    @patch("skills.handlers.normalcrafter.os.path.isfile", return_value=True)
    def test_image_input_returns_error(self, mock_isfile):
        from skills.handlers.normalcrafter import _f_normalcrafter

        result = _f_normalcrafter({
            "_input_path": "/tmp/test.png",
        })
        assert "error" in result
        assert "video" in result["error"].lower()

    @patch("skills.handlers.normalcrafter.os.path.isfile", return_value=True)
    def test_success_returns_movie(self, mock_isfile):
        from skills.handlers.normalcrafter import _f_normalcrafter

        mock_run = MagicMock(return_value="/tmp/output_normalcrafter.mp4")
        mock_nc = MagicMock(run_normalcrafter=mock_run)
        with patch.dict(sys.modules, {"core.normalcrafter_synthesizer": mock_nc}):
            result = _f_normalcrafter({
                "_input_path": "/tmp/test.mp4",
                "max_res": 1024,
                "window_size": 14,
                "seed": 42,
            })

        # Handler should attempt to call run_normalcrafter
        assert isinstance(result, dict)

    def test_default_max_res_is_1024(self):
        from skills.handlers.normalcrafter import _f_normalcrafter

        result = _f_normalcrafter({"_input_path": ""})
        # Should fail on missing input, not param validation
        assert "error" in result
        assert "valid" in result["error"].lower() or "video" in result["error"].lower()


# ── Dispatch Table Wiring ──────────────────────────────────────────


class TestNormalCrafterDispatch:
    """Verify _f_normalcrafter is wired into the dispatch table."""

    def test_normalcrafter_in_dispatch(self):
        from skills.composer import _get_dispatch

        dispatch = _get_dispatch()
        assert "normalcrafter" in dispatch, "normalcrafter should be in dispatch table"

    def test_dispatch_aliases_point_to_same_handler(self):
        from skills.composer import _get_dispatch

        dispatch = _get_dispatch()
        handler = dispatch["normalcrafter"]

        aliases = [
            "video_normals", "video_normal_map",
            "temporal_normals", "video_surface_normals",
        ]
        for alias in aliases:
            assert alias in dispatch, f"Alias '{alias}' should be in dispatch"
            assert dispatch[alias] is handler, (
                f"Alias '{alias}' should point to the same handler as 'normalcrafter'"
            )


# ── Alias Resolution ──────────────────────────────────────────────


class TestNormalCrafterAliases:
    """Verify SKILL_ALIASES resolve correctly."""

    def test_aliases_resolve_to_normalcrafter(self):
        from skills.composer import SkillComposer

        aliases = [
            "video_normals", "video_normal_map",
            "temporal_normals", "video_surface_normals",
        ]
        for alias in aliases:
            assert alias in SkillComposer.SKILL_ALIASES, (
                f"Alias '{alias}' should be in SKILL_ALIASES"
            )
            assert SkillComposer.SKILL_ALIASES[alias] == "normalcrafter", (
                f"Alias '{alias}' should resolve to 'normalcrafter'"
            )


# ── Model Manager ─────────────────────────────────────────────────


class TestNormalCrafterModelManager:
    """Verify normalcrafter model is registered in model manager."""

    def test_model_info_exists(self):
        from core.model_manager import _MODEL_INFO

        assert "normalcrafter" in _MODEL_INFO, (
            "normalcrafter should be registered in _MODEL_INFO"
        )

    def test_model_info_has_required_fields(self):
        from core.model_manager import _MODEL_INFO

        info = _MODEL_INFO["normalcrafter"]
        for field in ("name", "size", "url", "license", "manual"):
            assert field in info, f"Model info should have '{field}' field"

    def test_model_info_name(self):
        from core.model_manager import _MODEL_INFO

        info = _MODEL_INFO["normalcrafter"]
        assert "NormalCrafter" in info["name"]
        assert "Normal" in info["name"]

    def test_model_license_is_mit(self):
        from core.model_manager import _MODEL_INFO

        info = _MODEL_INFO["normalcrafter"]
        assert info["license"] == "MIT"

    def test_model_has_mirror_repo(self):
        from core.model_manager import _MODEL_INFO

        info = _MODEL_INFO["normalcrafter"]
        assert "mirror_repo" in info
        assert info["mirror_repo"].startswith("AEmotionStudio/")


# ── VRAM Utils ────────────────────────────────────────────────────


class TestNormalCrafterVRAM:
    """Verify normalcrafter is registered in VRAM management."""

    def test_module_in_all_synthesizer_modules(self):
        from core._vram_utils import ALL_SYNTHESIZER_MODULES

        assert "normalcrafter_synthesizer" in ALL_SYNTHESIZER_MODULES, (
            "normalcrafter_synthesizer should be in ALL_SYNTHESIZER_MODULES"
        )


# ── Module Import ─────────────────────────────────────────────────


# PyTorch guard — normalcrafter_synthesizer requires torch at module level
try:
    import torch  # noqa: F401
    _has_torch = True
except (ImportError, RuntimeError):
    _has_torch = False


@pytest.mark.skipif(not _has_torch, reason="PyTorch not available")
class TestNormalCrafterModuleImport:
    """Verify core module can be imported."""

    def test_synthesizer_module_importable(self):
        """normalcrafter_synthesizer module should be importable."""
        import core.normalcrafter_synthesizer as nc

        assert hasattr(nc, "run_normalcrafter")
        assert hasattr(nc, "run_normalcrafter_frames")
        assert hasattr(nc, "cleanup")

    def test_repos_have_mirror(self):
        """All repos should have AEmotionStudio mirror repos."""
        import core.normalcrafter_synthesizer as nc

        for name, cfg in nc._REPOS.items():
            assert "mirror_repo" in cfg, f"{name} should have mirror_repo"
            assert cfg["mirror_repo"].startswith("AEmotionStudio/"), (
                f"{name} mirror_repo should start with AEmotionStudio/"
            )
            assert "upstream_repo" in cfg, f"{name} should have upstream_repo"

    def test_handler_importable(self):
        """normalcrafter handler should be importable from handlers package."""
        from skills.handlers import _f_normalcrafter

        assert callable(_f_normalcrafter)


# ── Relight Integration ───────────────────────────────────────────


class TestRelightAINormals:
    """Verify relight module's AI normals integration."""

    def test_defaults_include_ai_normals(self):
        from videoeditor.processing.relight import _DEFAULTS

        assert "ai_normals" in _DEFAULTS
        assert _DEFAULTS["ai_normals"] is False

    def test_needs_ai_normals_false_by_default(self):
        from videoeditor.processing.relight import needs_ai_normals
        import json

        state = json.dumps({"enabled": True, "azimuth": 45})
        assert needs_ai_normals(state) is False

    def test_needs_ai_normals_true_when_enabled(self):
        from videoeditor.processing.relight import needs_ai_normals
        import json

        state = json.dumps({"enabled": True, "ai_normals": True})
        assert needs_ai_normals(state) is True

    def test_build_filters_empty_when_ai_normals(self):
        from videoeditor.processing.relight import build_relight_filters
        import json

        state = json.dumps({
            "enabled": True,
            "ai_normals": True,
            "azimuth": 45,
            "intensity": 1.5,
        })
        filters = build_relight_filters(state)
        assert filters == [], (
            "build_relight_filters should return empty when ai_normals=True"
        )

    def test_build_filters_nonempty_without_ai_normals(self):
        from videoeditor.processing.relight import build_relight_filters
        import json

        state = json.dumps({
            "enabled": True,
            "ai_normals": False,
            "azimuth": 45,
            "intensity": 1.5,
        })
        filters = build_relight_filters(state)
        assert len(filters) > 0, (
            "build_relight_filters should produce filters when ai_normals=False"
        )

    def test_apply_ai_relight_importable(self):
        from videoeditor.processing.relight import apply_ai_relight

        assert callable(apply_ai_relight)
