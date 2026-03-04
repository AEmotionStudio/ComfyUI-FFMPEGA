"""Unit tests for the SAM3 auto_mask skill integration.

Tests cover:
- Skill registration and discovery
- Alias resolution
- Graceful degradation when SAM3 is not installed
- Handler output structure (fallback path)
- Effect mapping
- Composer integration
- SAM3 masker module
"""

import pytest

# PyTorch import can fail on Python 3.14 — guard torch-dependent tests
try:
    import torch  # noqa: F401
    _has_torch = True
except (ImportError, RuntimeError):
    _has_torch = False

# --- Fixtures ----------------------------------------------------------------

@pytest.fixture
def registry():
    """Get a populated skill registry."""
    from skills.registry import get_registry
    return get_registry()


@pytest.fixture
def composer():
    """Get a SkillComposer with the default registry."""
    from skills.composer import SkillComposer
    return SkillComposer()


# --- Skill Registration Tests ------------------------------------------------

class TestAutoMaskRegistration:
    """Test that auto_mask skill is properly registered."""

    def test_skill_exists(self, registry):
        """auto_mask should be registered in the skill registry."""
        skill = registry.get("auto_mask")
        assert skill is not None
        assert skill.name == "auto_mask"

    def test_skill_category(self, registry):
        """auto_mask should be in the VISUAL category."""
        from skills.registry import SkillCategory
        skill = registry.get("auto_mask")
        assert skill.category == SkillCategory.VISUAL

    def test_skill_has_parameters(self, registry):
        """auto_mask should have the simplified SAM3 parameters."""
        skill = registry.get("auto_mask")
        param_names = {p.name for p in skill.parameters}
        expected = {"target", "effect", "strength", "invert", "edit_prompt", "smoothing"}
        assert expected == param_names

    def test_no_box_params(self, registry):
        """SAM3 version should NOT have bounding box parameters."""
        skill = registry.get("auto_mask")
        param_names = {p.name for p in skill.parameters}
        assert "box_x" not in param_names
        assert "box_y" not in param_names
        assert "box_w" not in param_names
        assert "box_h" not in param_names
        assert "model_size" not in param_names

    def test_target_is_required(self, registry):
        """target should be a required parameter."""
        skill = registry.get("auto_mask")
        target_param = next(p for p in skill.parameters if p.name == "target")
        assert target_param.required is True

    def test_effect_choices(self, registry):
        """Effect parameter should have the right choices."""
        skill = registry.get("auto_mask")
        effect_param = next(p for p in skill.parameters if p.name == "effect")
        assert set(effect_param.choices) == {
            "blur", "pixelate", "remove", "edit", "grayscale", "highlight",
            "greenscreen", "transparent", "thermal",
        }

    def test_skill_has_tags(self, registry):
        """auto_mask should have SAM3 tags for LLM discoverability."""
        skill = registry.get("auto_mask")
        assert "mask" in skill.tags
        assert "sam3" in skill.tags
        assert "prompt" in skill.tags

    def test_skill_has_examples(self, registry):
        """auto_mask should have text-prompt example strings."""
        skill = registry.get("auto_mask")
        assert len(skill.examples) >= 3
        # Examples should reference target=, not box params
        assert any("target=" in ex for ex in skill.examples)


# --- Alias Resolution Tests --------------------------------------------------

class TestAutoMaskAliases:
    """Test that common aliases resolve to auto_mask."""

    @pytest.mark.parametrize("alias", [
        "auto_segment", "segment", "smart_mask",
        "sam2", "sam_mask", "ai_mask", "object_mask",
    ])
    def test_alias_in_skill_aliases(self, alias, composer):
        """Common mask aliases should resolve to auto_mask."""
        resolved = composer.SKILL_ALIASES.get(alias)
        assert resolved == "auto_mask", \
            f"Alias '{alias}' should resolve to 'auto_mask', got '{resolved}'"

    @pytest.mark.parametrize("alias", [
        "auto_mask", "auto_segment", "segment", "smart_mask",
        "sam2", "sam_mask", "ai_mask", "object_mask",
    ])
    def test_alias_in_dispatch(self, alias):
        """All aliases should appear in the dispatch table."""
        from skills.composer import _get_dispatch
        dispatch = _get_dispatch()
        assert alias in dispatch, \
            f"Alias '{alias}' should be in dispatch table"


# --- Graceful Degradation Tests -----------------------------------------------

class TestAutoMaskFallback:
    """Test that auto_mask degrades gracefully when SAM3 is not installed."""

    @pytest.mark.skipif(not _has_torch, reason="PyTorch not available")
    def test_fallback_returns_result(self):
        """Fallback should return a valid HandlerResult."""
        from skills.handlers.visual import _auto_mask_fallback
        result = _auto_mask_fallback("blur", 50)
        assert hasattr(result, 'video_filters')
        assert hasattr(result, 'audio_filters')
        assert hasattr(result, 'filter_complex')

    @pytest.mark.parametrize("effect", [
        "blur", "pixelate", "remove", "grayscale", "highlight",
    ])
    def test_fallback_each_effect(self, effect):
        """Each effect should produce a non-empty filter in fallback mode."""
        from skills.handlers.visual import _auto_mask_fallback
        result = _auto_mask_fallback(effect, 50)
        vf = result.video_filters if hasattr(result, 'video_filters') else result[0]
        assert len(vf) > 0, f"Effect '{effect}' produced empty video filters"

    def test_fallback_unknown_effect(self):
        """Unknown effect should fall back to blur."""
        from skills.handlers.visual import _auto_mask_fallback
        result = _auto_mask_fallback("unknown_effect", 50)
        vf = result.video_filters if hasattr(result, 'video_filters') else result[0]
        assert "boxblur" in vf[0]


# --- Handler Output Tests ----------------------------------------------------

class TestAutoMaskHandler:
    """Test _f_auto_mask handler output structure."""

    @pytest.mark.skipif(not _has_torch, reason="PyTorch not available")
    def test_handler_with_text_prompt(self):
        """Handler should accept text prompt and return valid result."""
        from skills.handlers.visual import _f_auto_mask
        result = _f_auto_mask({
            "target": "the person",
            "effect": "blur",
            "strength": 50,
            "_input_path": "/test/video.mp4",
        })
        # Should return a HandlerResult (fallback since no real video)
        assert hasattr(result, 'video_filters') or hasattr(result, 'filter_complex')

    @pytest.mark.skipif(not _has_torch, reason="PyTorch not available")
    def test_handler_default_target(self):
        """Handler should use 'the subject' as default target."""
        from skills.handlers.visual import _f_auto_mask
        result = _f_auto_mask({
            "_input_path": "/test/video.mp4",
        })
        assert result is not None


# --- Composer Integration Tests -----------------------------------------------

class TestAutoMaskComposer:
    """Test that auto_mask integrates with the SkillComposer pipeline."""

    def test_compose_auto_mask(self, composer):
        """Composing a pipeline with auto_mask should not raise."""
        from skills.composer import Pipeline
        pipeline = Pipeline(
            input_path="/tmp/test.mp4",
            output_path="/tmp/out.mp4",
        )
        pipeline.add_step("auto_mask", {
            "target": "the face",
            "effect": "blur",
            "strength": 50,
        })
        cmd = composer.compose(pipeline)
        assert cmd is not None

    def test_compose_with_alias(self, composer):
        """Composing with an alias should also work."""
        from skills.composer import Pipeline
        pipeline = Pipeline(
            input_path="/tmp/test.mp4",
            output_path="/tmp/out.mp4",
        )
        pipeline.add_step("smart_mask", {
            "target": "license plate",
            "effect": "pixelate",
            "strength": 80,
        })
        cmd = composer.compose(pipeline)
        assert cmd is not None


# --- SAM3 Masker Module Tests -------------------------------------------------

class TestSAM3MaskerUnit:
    """Test the SAM3 masker module without requiring SAM3 installed."""

    def test_hf_repo_constant(self):
        """_HF_REPO should point to AEmotionStudio."""
        from core.sam3_masker import _HF_REPO
        assert _HF_REPO == "AEmotionStudio/sam3"

    def test_checkpoint_names(self):
        """Checkpoint names should be correct."""
        from core.sam3_masker import _SAFETENSORS_NAME, _PT_NAME
        assert _SAFETENSORS_NAME == "sam3.safetensors"
        assert _PT_NAME == "sam3.pt"

    def test_model_dir_contains_sam3(self):
        """_get_model_dir should return a path ending in SAM3."""
        from core.sam3_masker import _get_model_dir
        d = _get_model_dir()
        assert str(d).endswith("SAM3")

    @pytest.mark.skipif(not _has_torch, reason="PyTorch not available")
    def test_cleanup(self):
        """Cleanup should reset all cached models."""
        import core.sam3_masker as sm
        sm._image_model = "fake"
        sm._image_processor = "fake"
        sm._video_model = "fake"
        sm.cleanup()
        assert sm._image_model is None
        assert sm._image_processor is None
        assert sm._video_model is None
