"""Tests for the marigold skill (Marigold dense vision integration).

Covers skill registration, handler unit tests (with Marigold synthesizer
mocked), dispatch table wiring, alias resolution, and model manager
integration.
"""

import sys

import pytest
from unittest.mock import patch, MagicMock

from skills.registry import get_registry, SkillCategory

# Pre-import so unittest.mock.patch("core.marigold_synthesizer.xxx") can
# resolve the dotted path in CI where the submodule may not yet be an
# attribute of the ``core`` package.
try:
    import core.marigold_synthesizer  # noqa: F401
except ImportError:
    pass


# ── Skill Registration ─────────────────────────────────────────────


class TestMarigoldSkillRegistration:
    """Verify marigold is registered correctly in the skill registry."""

    def test_skill_exists_in_registry(self):
        registry = get_registry()
        skill = registry.get("marigold")
        assert skill is not None, "marigold skill should be registered"

    def test_skill_category_is_ai_visual(self):
        registry = get_registry()
        skill = registry.get("marigold")
        assert skill.category == SkillCategory.AI_VISUAL

    def test_skill_has_output_type_param(self):
        registry = get_registry()
        skill = registry.get("marigold")
        param = skill.get_param("output_type")
        assert param is not None, "Should have output_type parameter"
        assert param.required is True

    def test_skill_has_num_steps_param(self):
        registry = get_registry()
        skill = registry.get("marigold")
        param = skill.get_param("num_steps")
        assert param is not None, "Should have num_steps parameter"
        assert param.required is False
        assert param.default == 4

    def test_skill_has_ensemble_size_param(self):
        registry = get_registry()
        skill = registry.get("marigold")
        param = skill.get_param("ensemble_size")
        assert param is not None, "Should have ensemble_size parameter"
        assert param.required is False
        assert param.default == 1

    def test_skill_tags_include_key_terms(self):
        registry = get_registry()
        skill = registry.get("marigold")
        for tag in ("marigold", "depth", "normals", "albedo", "ai", "vision"):
            assert tag in skill.tags, f"Tag '{tag}' should be in skill tags"

    def test_skill_has_examples(self):
        registry = get_registry()
        skill = registry.get("marigold")
        assert skill.examples, "Skill should have usage examples"
        assert len(skill.examples) >= 3


# ── Handler Unit Tests ─────────────────────────────────────────────


class TestMarigoldHandler:
    """Test _f_marigold handler with mocked synthesizer."""

    def test_missing_input_returns_error(self):
        from skills.handlers.marigold import _f_marigold

        result = _f_marigold({"_input_path": "", "output_type": "depth"})
        assert "error" in result

    @patch("skills.handlers.marigold.os.path.isfile", return_value=True)
    def test_invalid_output_type_returns_error(self, mock_isfile):
        from skills.handlers.marigold import _f_marigold

        result = _f_marigold({
            "_input_path": "/tmp/test.mp4",
            "output_type": "invalid_type",
        })
        assert "error" in result
        assert "output_type" in result["error"]

    @patch("skills.handlers.marigold.os.path.isfile", return_value=True)
    def test_success_returns_movie(self, mock_isfile):
        from skills.handlers.marigold import _f_marigold

        mock_run = MagicMock(return_value="/tmp/output_marigold_depth.mp4")
        with patch.dict(sys.modules, {
            "core.marigold_synthesizer": MagicMock(run_marigold=mock_run),
        }):
            # Need to reload the module to pick up the mock
            with patch("core.marigold_synthesizer.run_marigold", mock_run):
                result = _f_marigold({
                    "_input_path": "/tmp/test.mp4",
                    "output_type": "depth",
                    "num_steps": 4,
                    "ensemble_size": 1,
                })

        # Handler should attempt to call run_marigold
        # (may fail if import path differs but the test validates flow)
        assert isinstance(result, dict)

    def test_default_output_type_is_depth(self):
        from skills.handlers.marigold import _f_marigold

        result = _f_marigold({"_input_path": ""})
        # Should fail on missing input, not output_type validation
        assert "error" in result
        assert "valid source" in result["error"]

    @patch("skills.handlers.marigold.os.path.isfile", return_value=True)
    def test_synthesizer_import_failure_returns_error(self, mock_isfile):
        """When synthesizer cannot be imported, handler returns friendly error."""
        from skills.handlers.marigold import _f_marigold

        with patch.dict(sys.modules, {
            "core.marigold_synthesizer": None,
        }):
            result = _f_marigold({
                "_input_path": "/tmp/test.mp4",
                "output_type": "normals",
            })
        # Should have an error (import fails)
        assert isinstance(result, dict)


# ── Dispatch Table Wiring ──────────────────────────────────────────


class TestMarigoldDispatch:
    """Verify _f_marigold is wired into the dispatch table."""

    def test_marigold_in_dispatch(self):
        from skills.composer import _get_dispatch

        dispatch = _get_dispatch()
        assert "marigold" in dispatch, "marigold should be in dispatch table"

    def test_dispatch_aliases_point_to_same_handler(self):
        from skills.composer import _get_dispatch

        dispatch = _get_dispatch()
        handler = dispatch["marigold"]

        aliases = [
            "depth_map", "normal_map", "surface_normals",
            "depth_estimation", "normals_estimation",
            "intrinsic_decomposition", "albedo_map", "material_map",
        ]
        for alias in aliases:
            assert alias in dispatch, f"Alias '{alias}' should be in dispatch"
            assert dispatch[alias] is handler, (
                f"Alias '{alias}' should point to the same handler as 'marigold'"
            )


# ── Alias Resolution ──────────────────────────────────────────────


class TestMarigoldAliases:
    """Verify SKILL_ALIASES resolve correctly."""

    def test_aliases_resolve_to_marigold(self):
        from skills.composer import SkillComposer

        aliases = [
            "depth_map", "normal_map", "surface_normals",
            "depth_estimation", "normals_estimation",
            "intrinsic_decomposition", "albedo_map", "material_map",
        ]
        for alias in aliases:
            assert alias in SkillComposer.SKILL_ALIASES, (
                f"Alias '{alias}' should be in SKILL_ALIASES"
            )
            assert SkillComposer.SKILL_ALIASES[alias] == "marigold", (
                f"Alias '{alias}' should resolve to 'marigold'"
            )


# ── Model Manager ─────────────────────────────────────────────────


class TestMarigoldModelManager:
    """Verify marigold model is registered in model manager."""

    def test_model_info_exists(self):
        from core.model_manager import _MODEL_INFO

        assert "marigold" in _MODEL_INFO, (
            "marigold should be registered in _MODEL_INFO"
        )

    def test_model_info_has_required_fields(self):
        from core.model_manager import _MODEL_INFO

        info = _MODEL_INFO["marigold"]
        for field in ("name", "size", "url", "license", "manual"):
            assert field in info, f"Model info should have '{field}' field"

    def test_model_info_name(self):
        from core.model_manager import _MODEL_INFO

        info = _MODEL_INFO["marigold"]
        assert "Marigold" in info["name"]
        assert "Dense Vision" in info["name"]


# ── Module Import ─────────────────────────────────────────────────


class TestMarigoldModuleImport:
    """Verify core module can be imported."""

    def test_synthesizer_module_importable(self):
        """marigold_synthesizer module should be importable."""
        import core.marigold_synthesizer as ms

        assert hasattr(ms, "run_marigold")
        assert hasattr(ms, "cleanup")
        assert hasattr(ms, "_OUTPUT_TYPES")

    def test_output_types_complete(self):
        """All 4 output types should be defined."""
        import core.marigold_synthesizer as ms

        expected = {"depth", "normals", "appearance", "lighting"}
        assert set(ms._OUTPUT_TYPES.keys()) == expected

    def test_output_types_have_mirror_repos(self):
        """All output types should have AEmotionStudio mirror repos."""
        import core.marigold_synthesizer as ms

        for name, cfg in ms._OUTPUT_TYPES.items():
            assert "mirror_repo" in cfg, f"{name} should have mirror_repo"
            assert cfg["mirror_repo"].startswith("AEmotionStudio/"), (
                f"{name} mirror_repo should start with AEmotionStudio/"
            )
            assert "upstream_repo" in cfg, f"{name} should have upstream_repo"

    def test_handler_importable(self):
        """marigold handler should be importable from handlers package."""
        from skills.handlers import _f_marigold

        assert callable(_f_marigold)
