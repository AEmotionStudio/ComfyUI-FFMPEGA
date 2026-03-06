"""Tests for the animate_portrait skill (LivePortrait integration).

Covers skill registration, handler unit tests (with LivePortrait mocked),
dispatch table wiring, alias resolution, and model manager integration.
"""

import sys

import pytest
from unittest.mock import patch, MagicMock

from skills.registry import get_registry, SkillCategory


# ── Skill Registration ─────────────────────────────────────────────


class TestAnimatePortraitSkillRegistration:
    """Verify animate_portrait is registered correctly in the skill registry."""

    def test_skill_exists_in_registry(self):
        registry = get_registry()
        skill = registry.get("animate_portrait")
        assert skill is not None, "animate_portrait skill should be registered"

    def test_skill_category_is_ai_visual(self):
        registry = get_registry()
        skill = registry.get("animate_portrait")
        assert skill.category == SkillCategory.AI_VISUAL

    def test_skill_has_driving_video_param(self):
        registry = get_registry()
        skill = registry.get("animate_portrait")
        param = skill.get_param("driving_video")
        assert param is not None, "Should have driving_video parameter"
        assert param.required is True

    def test_skill_has_driving_multiplier_param(self):
        registry = get_registry()
        skill = registry.get("animate_portrait")
        param = skill.get_param("driving_multiplier")
        assert param is not None, "Should have driving_multiplier parameter"
        assert param.required is False
        assert param.default == 1.0

    def test_skill_has_relative_motion_param(self):
        registry = get_registry()
        skill = registry.get("animate_portrait")
        param = skill.get_param("relative_motion")
        assert param is not None, "Should have relative_motion parameter"
        assert param.required is False
        assert param.default is True

    def test_skill_has_tags(self):
        registry = get_registry()
        skill = registry.get("animate_portrait")
        assert len(skill.tags) > 0
        assert "liveportrait" in skill.tags
        assert "animate" in skill.tags

    def test_skill_searchable_by_keywords(self):
        registry = get_registry()
        for kw in ["animate", "portrait", "liveportrait", "face", "expression"]:
            results = registry.search(kw)
            names = [s.name for s in results]
            assert "animate_portrait" in names, (
                f"animate_portrait should be found by keyword '{kw}'"
            )


# ── Handler Unit Tests ─────────────────────────────────────────────


class TestAnimatePortraitHandler:
    """Test the _f_animate_portrait handler function with mocked LivePortrait."""

    def test_handler_returns_dict(self):
        from skills.handlers.animate_portrait import _f_animate_portrait
        # No input = should return error dict
        result = _f_animate_portrait({})
        assert isinstance(result, dict)

    def test_degrades_when_driving_video_missing(self):
        from skills.handlers.animate_portrait import _f_animate_portrait
        import tempfile, os
        # Create a dummy source file
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            f.write(b"\x00" * 100)
            src_path = f.name
        try:
            result = _f_animate_portrait({
                "_input_path": src_path,
                # driving_video missing
            })
            assert "error" in result
            assert "driving_video" in result["error"]
        finally:
            os.unlink(src_path)

    def test_degrades_when_source_missing(self):
        from skills.handlers.animate_portrait import _f_animate_portrait
        result = _f_animate_portrait({
            "_input_path": "/nonexistent/source.mp4",
            "driving_video": "/nonexistent/driving.mp4",
        })
        assert "error" in result

    def test_success_with_mocked_liveportrait(self):
        from skills.handlers.animate_portrait import _f_animate_portrait
        import tempfile, os

        # Create dummy files
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            f.write(b"\x00" * 100)
            src = f.name
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            f.write(b"\x00" * 100)
            drv = f.name
        output = tempfile.mktemp(suffix=".mp4")

        try:
            # Use sys.modules injection instead of patch() because
            # core.liveportrait_synthesizer requires torch/cv2 at import
            # time, which may not be available in CI.
            mock_animate = MagicMock(return_value=output)
            mock_module = MagicMock()
            mock_module.animate_portrait = mock_animate

            with patch.dict(
                sys.modules,
                {"core.liveportrait_synthesizer": mock_module},
            ):
                # Create a fake output file
                with open(output, "wb") as f:
                    f.write(b"\x00" * 100)

                result = _f_animate_portrait({
                    "_input_path": src,
                    "driving_video": drv,
                    "driving_multiplier": 1.5,
                    "relative_motion": True,
                })

                # Should not have error
                assert "error" not in result
                assert "movie" in result
                assert result["movie"] == output

                # Check the mock was called with right params
                mock_animate.assert_called_once()
                call_kwargs = mock_animate.call_args
                assert call_kwargs[1]["driving_multiplier"] == 1.5
                assert call_kwargs[1]["relative_motion"] is True
        finally:
            for p in [src, drv]:
                if os.path.exists(p):
                    os.unlink(p)
            if os.path.exists(output):
                os.unlink(output)


# ── Dispatch Table Tests ───────────────────────────────────────────


class TestAnimatePortraitDispatch:
    """Verify animate_portrait is wired into the dispatch table."""

    def test_dispatch_table_has_animate_portrait(self):
        from skills.composer import _get_dispatch
        dispatch = _get_dispatch()
        assert "animate_portrait" in dispatch

    def test_dispatch_aliases(self):
        from skills.composer import _get_dispatch
        dispatch = _get_dispatch()
        aliases = [
            "portrait_animation", "face_animation", "face_reenactment",
            "liveportrait", "face_puppet", "puppet", "face_swap_motion",
        ]
        for alias in aliases:
            assert alias in dispatch, f"Dispatch should contain alias '{alias}'"

    def test_all_aliases_point_to_same_handler(self):
        from skills.composer import _get_dispatch
        from skills.handlers.animate_portrait import _f_animate_portrait
        dispatch = _get_dispatch()
        aliases = [
            "animate_portrait", "portrait_animation", "face_animation",
            "face_reenactment", "liveportrait", "face_puppet", "puppet",
            "face_swap_motion",
        ]
        for alias in aliases:
            assert dispatch[alias] is _f_animate_portrait, (
                f"'{alias}' should point to _f_animate_portrait"
            )


# ── Alias Resolution Tests ────────────────────────────────────────


class TestAnimatePortraitAliasResolution:
    """Verify skill alias resolution for animate_portrait."""

    def test_aliases_resolve_to_animate_portrait(self):
        from skills.composer import SkillComposer
        aliases = [
            "portrait_animation", "face_animation", "face_reenactment",
            "liveportrait", "face_puppet", "puppet", "face_swap_motion",
        ]
        for alias in aliases:
            resolved = SkillComposer.SKILL_ALIASES.get(alias)
            assert resolved == "animate_portrait", (
                f"Alias '{alias}' should resolve to 'animate_portrait', "
                f"got '{resolved}'"
            )


# ── Model Manager Tests ──────────────────────────────────────────


class TestAnimatePortraitModelManager:
    """Verify LivePortrait is registered in the model manager."""

    def test_model_info_entry_exists(self):
        from core.model_manager import _MODEL_INFO
        assert "liveportrait" in _MODEL_INFO

    def test_model_info_has_required_fields(self):
        from core.model_manager import _MODEL_INFO
        info = _MODEL_INFO["liveportrait"]
        assert "name" in info
        assert "size" in info
        assert "url" in info
        assert "mirror_repo" in info
        assert "manual" in info

    def test_mirror_repo_matches(self):
        from core.model_manager import _MODEL_INFO
        info = _MODEL_INFO["liveportrait"]
        assert "liveportrait" in info["mirror_repo"].lower()


# ── VRAM Coordination Tests ──────────────────────────────────────


class TestLivePortraitVRAMCoordination:
    """Verify LivePortrait cleanup is called by other synthesizers."""

    def test_liveportrait_has_cleanup(self):
        torch = pytest.importorskip("torch")
        cv2 = pytest.importorskip("cv2")
        from core import liveportrait_synthesizer
        assert hasattr(liveportrait_synthesizer, "cleanup")
        assert callable(liveportrait_synthesizer.cleanup)

    def test_liveportrait_cleanup_is_safe_when_not_loaded(self):
        """cleanup() should succeed even if models never loaded."""
        torch = pytest.importorskip("torch")
        cv2 = pytest.importorskip("cv2")
        from core import liveportrait_synthesizer
        liveportrait_synthesizer.cleanup()  # Should not raise


# ── Module Import Tests ──────────────────────────────────────────


class TestLivePortraitModuleImports:
    """Verify all vendored LivePortrait modules can be imported.

    Requires torch and cv2 — skipped in lightweight CI environments.
    """

    def test_import_init(self):
        pytest.importorskip("torch")
        from core import liveportrait

    def test_import_util(self):
        pytest.importorskip("torch")
        from core.liveportrait import util

    def test_import_convnextv2(self):
        pytest.importorskip("torch")
        from core.liveportrait import convnextv2

    def test_import_dense_motion(self):
        pytest.importorskip("torch")
        from core.liveportrait import dense_motion

    def test_import_appearance_feature_extractor(self):
        pytest.importorskip("torch")
        from core.liveportrait import appearance_feature_extractor

    def test_import_motion_extractor(self):
        pytest.importorskip("torch")
        from core.liveportrait import motion_extractor

    def test_import_warping_network(self):
        pytest.importorskip("torch")
        from core.liveportrait import warping_network

    def test_import_spade_generator(self):
        pytest.importorskip("torch")
        from core.liveportrait import spade_generator

    def test_import_stitching_retargeting_network(self):
        pytest.importorskip("torch")
        from core.liveportrait import stitching_retargeting_network

    def test_import_synthesizer(self):
        pytest.importorskip("torch")
        pytest.importorskip("cv2")
        from core import liveportrait_synthesizer
