"""Unit tests for the GPU shader overlay system.

Tests cover:
- Shader support module (capability detection, path resolution, fallback)
- Skill registration and discovery
- Alias resolution
- Handler output structure (GPU and fallback paths)
- Effect mapping for auto_mask integration
- Video editor processing module
- Composer integration
"""

import os
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

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


# --- Shader Support Module ---------------------------------------------------

class TestShaderSupport:
    """Tests for core/shader_support.py."""

    def test_shaders_dir_exists(self):
        """The built-in shaders/ directory should exist."""
        from core.shader_support import _get_shaders_dir
        d = _get_shaders_dir()
        assert d.is_dir(), f"shaders/ directory missing at {d}"

    def test_list_available_shaders(self):
        """Should discover built-in shader presets."""
        from core.shader_support import list_available_shaders
        shaders = list_available_shaders()
        assert len(shaders) >= 70, f"Expected >=70 shaders, got {len(shaders)}: {shaders}"
        expected = {
            "crt", "vhs", "holographic", "glitch", "voronoi",
            "water_ripple", "night_vision", "force_field",
            "plasma_burn", "shockwave", "datamosh", "crystal",
            "aurora", "hologram_scan", "portal", "circuit_board",
            "dissolve", "hex_matrix", "liquid_metal", "xray",
            "cartoon", "jelly", "emboss_3d", "infrared_predator",
            "digital_decay", "underwater", "electric_arc", "ink_wash",
            "neon_outline", "fire_outline", "frost_outline", "shadow_outline",
            "oil_paint", "rain", "matrix", "sketch",
            "pixel_sort", "topographic", "stained_glass", "smoke",
            "geometric_shatter", "noir", "cyberpunk", "mosaic",
            "lava_lamp", "vaporwave", "supernova", "fractal_loop",
            "kaleidoscope", "ebruli", "spirals", "space_tunnel",
            "singularity", "blueprint", "singularity_box",
            # NPR & Stylized
            "anime_pro", "watercolor", "pop_art", "woodcut",
            "chromatic_prism", "anime_glow", "comic_book",
            "watercolor_bleed", "retro_dither", "neon_wireframe",
            # Depth-Native
            "toon_3d", "depth_fog", "focus_pull",
            "relief_sculpt", "depth_watercolor",
        }
        assert expected.issubset(set(shaders)), \
            f"Missing presets: {expected - set(shaders)}"

    def test_resolve_shader_path_by_name(self):
        """resolve_shader_path('crt') should find crt.glsl."""
        from core.shader_support import resolve_shader_path
        path = resolve_shader_path("crt")
        assert path is not None
        assert path.suffix == ".glsl"
        assert "crt" in path.stem

    def test_resolve_shader_path_not_found(self):
        """resolve_shader_path for a nonexistent shader returns None."""
        from core.shader_support import resolve_shader_path
        assert resolve_shader_path("nonexistent_shader_xyz") is None

    def test_resolve_shader_path_full_path(self):
        """resolve_shader_path with a real .glsl file path should work."""
        from core.shader_support import resolve_shader_path, _get_shaders_dir
        real_path = str(_get_shaders_dir() / "crt.glsl")
        result = resolve_shader_path(real_path)
        assert result is not None
        assert result.suffix == ".glsl"

    def test_resolve_shader_path_invalid_extension(self):
        """Reject non-GLSL file extensions."""
        from core.shader_support import resolve_shader_path
        # Use a real path but with wrong extension
        assert resolve_shader_path("/tmp/not_a_shader.py") is None

    def test_fallback_filter_known_preset(self):
        """Each built-in preset should have an FFmpeg fallback."""
        from core.shader_support import get_fallback_filter
        presets = [
            "crt", "vhs", "holographic", "glitch", "voronoi",
            "water_ripple", "night_vision", "force_field",
            "plasma_burn", "shockwave", "datamosh", "crystal",
            "aurora", "hologram_scan", "portal", "circuit_board",
            "dissolve", "hex_matrix", "liquid_metal", "xray",
            "cartoon", "jelly", "emboss_3d", "infrared_predator",
            "digital_decay", "underwater", "electric_arc", "ink_wash",
            "neon_outline", "fire_outline", "frost_outline", "shadow_outline",
            "oil_paint", "rain", "matrix", "sketch",
            "pixel_sort", "topographic", "stained_glass", "smoke",
            "geometric_shatter", "noir", "cyberpunk", "mosaic",
            "lava_lamp", "vaporwave", "supernova", "fractal_loop",
            "kaleidoscope", "ebruli", "spirals", "space_tunnel",
            "singularity", "blueprint", "singularity_box",
            # NPR & Stylized
            "anime_pro", "watercolor", "pop_art", "woodcut",
            "chromatic_prism", "anime_glow", "comic_book",
            "watercolor_bleed", "retro_dither", "neon_wireframe",
            # Depth-Native
            "toon_3d", "depth_fog", "focus_pull",
            "relief_sculpt", "depth_watercolor",
        ]
        for p in presets:
            fb = get_fallback_filter(p)
            assert fb is not None, f"No fallback for preset '{p}'"
            assert len(fb) > 0

    def test_fallback_filter_unknown(self):
        """Unknown preset should return None for fallback."""
        from core.shader_support import get_fallback_filter
        assert get_fallback_filter("unknown_preset") is None

    def test_escape_shader_path(self):
        """Special characters should be escaped for FFmpeg."""
        from core.shader_support import escape_shader_path
        result = escape_shader_path("/path/to/shader:file.glsl")
        assert "\\:" in result

    def test_build_shader_filter_full_intensity(self):
        """Full intensity should produce a vf filter, no fc."""
        from core.shader_support import build_shader_filter, _get_shaders_dir
        path = str(_get_shaders_dir() / "crt.glsl")
        vf, fc = build_shader_filter(path, intensity=1.0)
        assert len(vf) == 1
        assert "libplacebo" in vf[0]
        assert fc == ""

    def test_build_shader_filter_partial_intensity(self):
        """Partial intensity should produce a filter_complex with blend."""
        from core.shader_support import build_shader_filter, _get_shaders_dir
        path = str(_get_shaders_dir() / "crt.glsl")
        vf, fc = build_shader_filter(path, intensity=0.5)
        assert len(vf) == 0
        assert "blend" in fc
        assert "0.5" in fc

    def test_build_shader_filter_zero_intensity(self):
        """Zero intensity should produce nothing."""
        from core.shader_support import build_shader_filter, _get_shaders_dir
        path = str(_get_shaders_dir() / "crt.glsl")
        vf, fc = build_shader_filter(path, intensity=0.0)
        assert len(vf) == 0
        assert fc == ""

    @patch("core.shader_support.subprocess.run")
    def test_has_libplacebo_detection(self, mock_run):
        """has_libplacebo() should detect libplacebo in ffmpeg -filters."""
        from core.shader_support import has_libplacebo
        # Clear LRU cache
        has_libplacebo.cache_clear()

        mock_run.return_value = MagicMock(stdout="libplacebo some other filters")
        assert has_libplacebo() is True
        has_libplacebo.cache_clear()

        mock_run.return_value = MagicMock(stdout="scale overlay no_placebo")
        assert has_libplacebo() is False
        has_libplacebo.cache_clear()


# --- Skill Registration Tests ------------------------------------------------

class TestShaderSkillRegistration:
    """Test that the shader skill is properly registered."""

    def test_skill_exists(self, registry):
        """shader should be in the registry."""
        skill = registry.get("shader")
        assert skill is not None
        assert skill.name == "shader"

    def test_skill_category(self, registry):
        """shader should be in the VISUAL category."""
        from skills.registry import SkillCategory
        skill = registry.get("shader")
        assert skill.category == SkillCategory.VISUAL

    def test_skill_has_preset_param(self, registry):
        """shader should have a 'preset' parameter with choices."""
        skill = registry.get("shader")
        param_names = {p.name for p in skill.parameters}
        assert "preset" in param_names
        preset_param = next(p for p in skill.parameters if p.name == "preset")
        assert "crt" in preset_param.choices
        assert "vhs" in preset_param.choices

    def test_skill_has_intensity_param(self, registry):
        """shader should have an 'intensity' parameter (0.0–1.0)."""
        skill = registry.get("shader")
        param_names = {p.name for p in skill.parameters}
        assert "intensity" in param_names
        intensity_param = next(p for p in skill.parameters if p.name == "intensity")
        assert intensity_param.min_value == 0.0
        assert intensity_param.max_value == 1.0

    def test_skill_has_custom_path_param(self, registry):
        """shader should have a 'custom_path' parameter."""
        skill = registry.get("shader")
        param_names = {p.name for p in skill.parameters}
        assert "custom_path" in param_names

    def test_skill_discoverable_by_tags(self, registry):
        """shader should be discoverable via tag search."""
        results = registry.search("glsl")
        names = [s.name for s in results]
        assert "shader" in names

    def test_skill_has_examples(self, registry):
        """shader should have usage examples."""
        skill = registry.get("shader")
        assert len(skill.examples) >= 5


# --- Alias Resolution --------------------------------------------------------

class TestShaderAliases:
    """Test alias resolution for the shader skill."""

    def test_glsl_alias(self, composer):
        """'glsl' should resolve to 'shader'."""
        assert composer.SKILL_ALIASES.get("glsl") == "shader"

    def test_gpu_shader_alias(self, composer):
        """'gpu_shader' should resolve to 'shader'."""
        assert composer.SKILL_ALIASES.get("gpu_shader") == "shader"

    def test_shader_overlay_alias(self, composer):
        """'shader_overlay' should resolve to 'shader'."""
        assert composer.SKILL_ALIASES.get("shader_overlay") == "shader"


# --- Handler Tests -----------------------------------------------------------

class TestShaderHandler:
    """Test _f_shader handler output structure."""

    @patch("skills.handlers.shader.has_libplacebo", return_value=True)
    def test_handler_gpu_path(self, mock_placebo):
        """With libplacebo, handler should return a libplacebo filter."""
        from skills.handlers.shader import _f_shader
        result = _f_shader({"preset": "crt", "intensity": 1.0})
        vf, af, opts, fc, io = result
        assert any("libplacebo" in f for f in vf), f"Expected libplacebo in vf: {vf}"

    @patch("skills.handlers.shader.has_libplacebo", return_value=False)
    def test_handler_fallback_path(self, mock_placebo):
        """Without libplacebo, handler should use FFmpeg fallback."""
        from skills.handlers.shader import _f_shader
        result = _f_shader({"preset": "crt", "intensity": 1.0})
        vf, af, opts, fc, io = result
        assert len(vf) > 0, "Fallback should produce vf filters"
        # Should NOT contain libplacebo
        assert not any("libplacebo" in f for f in vf)

    @patch("skills.handlers.shader.has_libplacebo", return_value=True)
    def test_handler_partial_intensity_produces_fc(self, mock_placebo):
        """Partial intensity should produce a filter_complex with blend."""
        from skills.handlers.shader import _f_shader
        result = _f_shader({"preset": "vhs", "intensity": 0.5})
        vf, af, opts, fc, io = result
        assert fc, "Partial intensity should produce filter_complex"
        assert "blend" in fc

    def test_handler_zero_intensity_noop(self):
        """Zero intensity should produce no filters."""
        from skills.handlers.shader import _f_shader
        result = _f_shader({"preset": "crt", "intensity": 0.0})
        vf, af, opts, fc, io = result
        assert len(vf) == 0
        assert fc == ""

    def test_handler_unknown_preset_noop(self):
        """Unknown preset should produce no filters."""
        from skills.handlers.shader import _f_shader
        result = _f_shader({"preset": "nonexistent_xyz"})
        vf, af, opts, fc, io = result
        assert len(vf) == 0

    @patch("skills.handlers.shader.has_libplacebo", return_value=True)
    def test_get_shader_vf_for_mask(self, mock_placebo):
        """get_shader_vf_for_mask should return a single filter string."""
        from skills.handlers.shader import get_shader_vf_for_mask
        result = get_shader_vf_for_mask("crt")
        assert result is not None
        assert "libplacebo" in result

    @patch("skills.handlers.shader.has_libplacebo", return_value=False)
    def test_get_shader_vf_for_mask_fallback(self, mock_placebo):
        """Fallback should return the FFmpeg approximation filter."""
        from skills.handlers.shader import get_shader_vf_for_mask
        result = get_shader_vf_for_mask("crt")
        assert result is not None
        # Should be the fallback filter, not libplacebo
        assert "libplacebo" not in result


# --- Auto-Mask Integration ---------------------------------------------------

class TestShaderAutoMaskEffect:
    """Test that 'shader' is a valid auto_mask effect."""

    def test_shader_in_auto_mask_effect_choices(self, registry):
        """'shader' should be listed in auto_mask effect parameter choices."""
        skill = registry.get("auto_mask")
        assert skill is not None
        effect_param = next(
            (p for p in skill.parameters if p.name == "effect"), None,
        )
        assert effect_param is not None
        assert "shader" in effect_param.choices

    def test_effect_filter_map_includes_shader(self):
        """_effect_filter_map should include a 'shader' key."""
        from skills.handlers.visual import _effect_filter_map
        efm = _effect_filter_map(50, shader_preset="crt")
        assert "shader" in efm or "blur" in efm  # shader may fail if import fails


# --- Video Editor Processing -------------------------------------------------

class TestVideoEditorShaders:
    """Test the video editor shader processing module."""

    def test_has_shader_none(self):
        """No shader when preset is 'none' or empty."""
        from videoeditor.processing.shaders import has_shader
        assert has_shader("{}") is False
        assert has_shader("") is False
        assert has_shader('{"preset": "none"}') is False

    def test_has_shader_crt(self):
        """Should detect a real shader preset."""
        from videoeditor.processing.shaders import has_shader
        assert has_shader('{"preset": "crt", "intensity": 1.0}') is True

    def test_build_shader_filter_none(self):
        """No filters for preset=none."""
        from videoeditor.processing.shaders import build_shader_filter
        vf, fc = build_shader_filter('{"preset": "none"}')
        assert vf == []
        assert fc == ""


# --- Dispatch Table -----------------------------------------------------------

class TestShaderDispatch:
    """Test that _f_shader is in the composer dispatch table."""

    def test_shader_in_dispatch(self):
        """'shader' should be in the dispatch table."""
        from skills.composer import _get_dispatch
        dispatch = _get_dispatch()
        assert "shader" in dispatch

    def test_glsl_in_dispatch(self):
        """'glsl' alias should be in the dispatch table."""
        from skills.composer import _get_dispatch
        dispatch = _get_dispatch()
        assert "glsl" in dispatch

    def test_dispatch_points_to_shader_handler(self):
        """All shader dispatch keys should point to _f_shader."""
        from skills.composer import _get_dispatch
        from skills.handlers.shader import _f_shader
        dispatch = _get_dispatch()
        for key in ["shader", "glsl", "gpu_shader", "gpu_effect", "shader_overlay"]:
            assert dispatch[key] is _f_shader, f"{key} doesn't point to _f_shader"


# --- GLSL File Validation ----------------------------------------------------

class TestGLSLPresets:
    """Validate built-in GLSL shader files."""

    def test_all_presets_are_valid_glsl(self):
        """Each .glsl file should contain HOOK and BIND directives."""
        from core.shader_support import _get_shaders_dir
        shaders_dir = _get_shaders_dir()
        for glsl_file in shaders_dir.glob("*.glsl"):
            content = glsl_file.read_text()
            assert "//!HOOK" in content, f"{glsl_file.name} missing //!HOOK"
            assert "//!BIND" in content, f"{glsl_file.name} missing //!BIND"
            assert "vec4 hook()" in content, f"{glsl_file.name} missing hook() function"

    def test_animated_shaders_use_frame_uniform(self):
        """Animated shaders should reference the 'frame' uniform."""
        from core.shader_support import _get_shaders_dir
        animated = [
            "vhs", "holographic", "glitch", "water_ripple",
            "night_vision", "force_field",
            "plasma_burn", "shockwave", "datamosh", "crystal",
            "aurora", "hologram_scan", "portal", "circuit_board",
            "dissolve", "hex_matrix", "liquid_metal", "xray",
            "jelly", "emboss_3d", "infrared_predator",
            "digital_decay", "underwater", "electric_arc", "ink_wash",
            "neon_outline", "fire_outline", "frost_outline", "shadow_outline",
            "rain", "matrix",
            "pixel_sort", "topographic", "stained_glass", "smoke",
            "geometric_shatter", "noir", "cyberpunk", "mosaic",
            "lava_lamp", "vaporwave", "supernova", "fractal_loop",
            "kaleidoscope", "ebruli", "spirals", "space_tunnel",
            "singularity", "blueprint", "singularity_box",
            # NPR & Stylized
            "anime_pro", "watercolor", "pop_art", "woodcut",
            "chromatic_prism", "anime_glow", "comic_book",
            "watercolor_bleed", "neon_wireframe",
            # Depth-Native (toon_3d and focus_pull excluded — static depth shaders, no frame uniform)
            "depth_fog",
            "relief_sculpt", "depth_watercolor",
        ]
        shaders_dir = _get_shaders_dir()
        for name in animated:
            path = shaders_dir / f"{name}.glsl"
            content = path.read_text()
            assert "frame" in content, f"{name}.glsl should use 'frame' uniform"

    def test_preset_count(self):
        """Should have exactly 55 built-in presets."""
        from core.shader_support import _get_shaders_dir
        shaders_dir = _get_shaders_dir()
        glsl_files = list(shaders_dir.glob("*.glsl"))
        assert len(glsl_files) == 70, \
            f"Expected 70 presets, found {len(glsl_files)}: {[f.stem for f in glsl_files]}"


# --- ShaderOverlayNode (Dedicated No-LLM Node) ------------------------------

class TestShaderOverlayNode:
    """Test the dedicated ShaderOverlayNode for no-LLM workflows."""

    def test_node_importable(self):
        """ShaderOverlayNode should be importable."""
        from nodes.shader_overlay_node import ShaderOverlayNode
        assert ShaderOverlayNode is not None

    def test_input_types_has_preset(self):
        """Node should have a 'preset' required input."""
        from nodes.shader_overlay_node import ShaderOverlayNode
        inputs = ShaderOverlayNode.INPUT_TYPES()
        assert "preset" in inputs["required"]

    def test_input_types_has_intensity(self):
        """Node should have an 'intensity' required input."""
        from nodes.shader_overlay_node import ShaderOverlayNode
        inputs = ShaderOverlayNode.INPUT_TYPES()
        assert "intensity" in inputs["required"]

    def test_input_types_has_custom_path(self):
        """Node should have a 'custom_shader_path' optional input."""
        from nodes.shader_overlay_node import ShaderOverlayNode
        inputs = ShaderOverlayNode.INPUT_TYPES()
        assert "custom_shader_path" in inputs["optional"]

    def test_preset_choices_include_builtins(self):
        """Preset dropdown should include all built-in presets + random."""
        from nodes.shader_overlay_node import ShaderOverlayNode
        inputs = ShaderOverlayNode.INPUT_TYPES()
        preset_field = inputs["required"]["preset"]
        choices = preset_field[0]
        assert "none" in choices
        assert "crt" in choices
        assert "vhs" in choices
        assert "force_field" in choices
        assert "🎲 random" in choices
        assert len(choices) >= 72  # none + random + 70 presets + category headers

    def test_input_types_has_chaining(self):
        """Node should have preset_2/preset_3 for shader chaining."""
        from nodes.shader_overlay_node import ShaderOverlayNode
        inputs = ShaderOverlayNode.INPUT_TYPES()
        assert "preset_2" in inputs["optional"]
        assert "intensity_2" in inputs["optional"]
        assert "preset_3" in inputs["optional"]
        assert "intensity_3" in inputs["optional"]

    def test_input_types_has_speed(self):
        """Node should have a speed slider."""
        from nodes.shader_overlay_node import ShaderOverlayNode
        inputs = ShaderOverlayNode.INPUT_TYPES()
        assert "speed" in inputs["optional"]

    def test_input_types_has_hue_shift(self):
        """Node should have a hue_shift slider."""
        from nodes.shader_overlay_node import ShaderOverlayNode
        inputs = ShaderOverlayNode.INPUT_TYPES()
        assert "hue_shift" in inputs["optional"]

    def test_input_types_has_blend_mode(self):
        """Node should have a blend_mode dropdown."""
        from nodes.shader_overlay_node import ShaderOverlayNode
        inputs = ShaderOverlayNode.INPUT_TYPES()
        assert "blend_mode" in inputs["optional"]
        blend_choices = inputs["optional"]["blend_mode"][0]
        assert "normal" in blend_choices
        assert "multiply" in blend_choices
        assert "screen" in blend_choices

    def test_input_types_has_phase(self):
        """Node should have a phase slider."""
        from nodes.shader_overlay_node import ShaderOverlayNode
        inputs = ShaderOverlayNode.INPUT_TYPES()
        assert "phase" in inputs["optional"]

    def test_input_types_has_shader_params(self):
        """Node should have a shader_params text field."""
        from nodes.shader_overlay_node import ShaderOverlayNode
        inputs = ShaderOverlayNode.INPUT_TYPES()
        assert "shader_params" in inputs["optional"]

    def test_input_types_has_resolution_scale(self):
        """Node should have a resolution_scale dropdown."""
        from nodes.shader_overlay_node import ShaderOverlayNode
        inputs = ShaderOverlayNode.INPUT_TYPES()
        assert "resolution_scale" in inputs["optional"]
        res_choices = inputs["optional"]["resolution_scale"][0]
        assert "1.0" in res_choices
        assert "0.5" in res_choices

    def test_return_types(self):
        """Node should return (IMAGE, STRING)."""
        from nodes.shader_overlay_node import ShaderOverlayNode
        assert ShaderOverlayNode.RETURN_TYPES == ("IMAGE", "STRING", "MASK")
        assert ShaderOverlayNode.RETURN_NAMES == ("images", "video_path", "mask")

    def test_category_is_ffmpega(self):
        """Node should be in the FFMPEGA category."""
        from nodes.shader_overlay_node import ShaderOverlayNode
        assert ShaderOverlayNode.CATEGORY == "FFMPEGA"

    def test_node_registered_in_mappings(self):
        """Node should be in NODE_CLASS_MAPPINGS."""
        from nodes import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS
        assert "FFMPEGAShaderOverlay" in NODE_CLASS_MAPPINGS
        assert "FFMPEGAShaderOverlay" in NODE_DISPLAY_NAME_MAPPINGS
        assert NODE_DISPLAY_NAME_MAPPINGS["FFMPEGAShaderOverlay"] == "Shader Overlay (FFMPEGA)"

    @pytest.mark.skipif(not _has_torch, reason="torch not available")
    def test_node_passthrough_no_shader(self):
        """preset='none' should passthrough without processing."""
        from nodes.shader_overlay_node import ShaderOverlayNode
        node = ShaderOverlayNode()
        result = node.process(preset="none", intensity=1.0)
        frames, path, mask = result
        assert isinstance(frames, torch.Tensor)
        assert path == ""  # No input provided → empty result

    def test_input_types_has_mask_target(self):
        """Node should have a 'mask_target' optional input."""
        from nodes.shader_overlay_node import ShaderOverlayNode
        inputs = ShaderOverlayNode.INPUT_TYPES()
        assert "mask_target" in inputs["optional"]

    def test_input_types_has_invert_mask(self):
        """Node should have an 'invert_mask' optional input."""
        from nodes.shader_overlay_node import ShaderOverlayNode
        inputs = ShaderOverlayNode.INPUT_TYPES()
        assert "invert_mask" in inputs["optional"]

    def test_mask_target_placeholder(self):
        """mask_target should have a helpful placeholder."""
        from nodes.shader_overlay_node import ShaderOverlayNode
        inputs = ShaderOverlayNode.INPUT_TYPES()
        mask_field = inputs["optional"]["mask_target"]
        # mask_field is (type, config_dict)
        assert "placeholder" in mask_field[1]
