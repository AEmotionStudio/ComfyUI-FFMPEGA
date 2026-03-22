"""Tests for the depth-aware shader system.

Tests the depth_shader_bridge module and shader overlay node
depth integration.
"""

import os
import sys
import pytest

# Ensure the extension root is on sys.path
_EXT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _EXT_ROOT not in sys.path:
    sys.path.insert(0, _EXT_ROOT)


class TestDepthShaderBridge:
    """Tests for core/depth_shader_bridge.py — module structure and constants."""

    def test_importable(self):
        """Should be importable."""
        from core.depth_shader_bridge import (
            generate_depth_map,
            generate_normal_map,
            generate_combined_mask,
            composite_with_depth_mask,
            DEPTH_MODES,
            DEPTH_ENCODERS,
        )
        assert callable(generate_depth_map)
        assert callable(generate_normal_map)
        assert callable(generate_combined_mask)
        assert callable(composite_with_depth_mask)

    def test_depth_modes_list(self):
        """DEPTH_MODES should contain all expected modes."""
        from core.depth_shader_bridge import DEPTH_MODES
        expected = {
            "none", "foreground_focus", "background_focus",
            "depth_outline", "atmospheric", "full_depth",
        }
        assert expected == set(DEPTH_MODES)

    def test_depth_encoders_list(self):
        """DEPTH_ENCODERS should contain all VDA model variants."""
        from core.depth_shader_bridge import DEPTH_ENCODERS
        assert set(DEPTH_ENCODERS) == {"vits", "vitb", "vitl"}

    def test_process_depth_for_mode_is_callable(self):
        """_process_depth_for_mode should be callable."""
        from core.depth_shader_bridge import _process_depth_for_mode
        assert callable(_process_depth_for_mode)

    def test_depth_native_shaders_set(self):
        """DEPTH_NATIVE_SHADERS should contain expected names."""
        from core.depth_shader_bridge import DEPTH_NATIVE_SHADERS
        expected = {"toon_3d", "depth_fog", "focus_pull",
                    "relief_sculpt", "depth_watercolor"}
        assert expected == DEPTH_NATIVE_SHADERS

    def test_is_depth_native(self):
        """is_depth_native should correctly identify depth-native shaders."""
        from core.depth_shader_bridge import is_depth_native
        assert is_depth_native("toon_3d") is True
        assert is_depth_native("focus_pull") is True
        assert is_depth_native("crt") is False
        assert is_depth_native("anime_pro") is False

    def test_pack_sbs_is_callable(self):
        """pack_sbs should be callable."""
        from core.depth_shader_bridge import pack_sbs
        assert callable(pack_sbs)

    def test_unpack_sbs_is_callable(self):
        """unpack_sbs should be callable."""
        from core.depth_shader_bridge import unpack_sbs
        assert callable(unpack_sbs)

    def test_generate_normal_map_is_callable(self):
        """generate_normal_map should be callable."""
        from core.depth_shader_bridge import generate_normal_map
        assert callable(generate_normal_map)

    def test_pack_sbs_accepts_normals(self):
        """pack_sbs should accept optional normals_path parameter."""
        import inspect
        from core.depth_shader_bridge import pack_sbs
        sig = inspect.signature(pack_sbs)
        assert "normals_path" in sig.parameters
        assert "depth_path" in sig.parameters

    def test_unpack_sbs_accepts_panel_count(self):
        """unpack_sbs should accept optional panel_count parameter."""
        import inspect
        from core.depth_shader_bridge import unpack_sbs
        sig = inspect.signature(unpack_sbs)
        assert "panel_count" in sig.parameters


class TestShaderOverlayDepthInputs:
    """Tests that ShaderOverlayNode has the new AI toggle inputs."""

    def test_input_types_has_enable_vda(self):
        """Node should have an enable_vda boolean input."""
        from nodes.shader_overlay_node import ShaderOverlayNode
        inputs = ShaderOverlayNode.INPUT_TYPES()
        optional = inputs.get("optional", {})
        assert "enable_vda" in optional
        assert optional["enable_vda"][0] == "BOOLEAN"

    def test_input_types_has_enable_normals(self):
        """Node should have an enable_normals boolean input."""
        from nodes.shader_overlay_node import ShaderOverlayNode
        inputs = ShaderOverlayNode.INPUT_TYPES()
        optional = inputs.get("optional", {})
        assert "enable_normals" in optional
        assert optional["enable_normals"][0] == "BOOLEAN"

    def test_input_types_has_normals_input(self):
        """Node should have a normals_input for external normal maps."""
        from nodes.shader_overlay_node import ShaderOverlayNode
        inputs = ShaderOverlayNode.INPUT_TYPES()
        optional = inputs.get("optional", {})
        assert "normals_input" in optional

    def test_input_types_has_depth_encoder(self):
        """Node should have a depth_encoder input."""
        from nodes.shader_overlay_node import ShaderOverlayNode
        inputs = ShaderOverlayNode.INPUT_TYPES()
        optional = inputs.get("optional", {})
        assert "depth_encoder" in optional
        choices = optional["depth_encoder"][0]
        assert "vits" in choices
        assert "vitl" in choices

    def test_input_types_has_depth_input(self):
        """Node should have a depth_input for external depth maps."""
        from nodes.shader_overlay_node import ShaderOverlayNode
        inputs = ShaderOverlayNode.INPUT_TYPES()
        optional = inputs.get("optional", {})
        assert "depth_input" in optional

    def test_input_types_has_depth_strength(self):
        """Node should have a depth_strength slider."""
        from nodes.shader_overlay_node import ShaderOverlayNode
        inputs = ShaderOverlayNode.INPUT_TYPES()
        optional = inputs.get("optional", {})
        assert "depth_strength" in optional
        config = optional["depth_strength"][1]
        assert config["min"] == 0.0
        assert config["max"] == 1.0

    def test_apply_depth_masked_exists(self):
        """Node should have the _apply_depth_masked static method."""
        from nodes.shader_overlay_node import ShaderOverlayNode
        assert hasattr(ShaderOverlayNode, '_apply_depth_masked')
        assert callable(ShaderOverlayNode._apply_depth_masked)


class TestVideoEditorShaderDepth:
    """Tests for the video editor shader pipeline depth config."""

    def test_get_depth_config_default(self):
        """get_depth_config should return defaults for empty JSON."""
        from videoeditor.processing.shaders import get_depth_config
        config = get_depth_config("{}")
        assert config["enable_vda"] is False
        assert config["enable_normals"] is False
        assert config["depth_encoder"] == "vits"
        assert config["depth_strength"] == 1.0

    def test_get_depth_config_custom(self):
        """get_depth_config should parse custom values."""
        import json
        from videoeditor.processing.shaders import get_depth_config
        data = json.dumps({
            "enable_vda": True,
            "enable_normals": True,
            "depth_encoder": "vitl",
            "depth_strength": 0.7,
        })
        config = get_depth_config(data)
        assert config["enable_vda"] is True
        assert config["enable_normals"] is True
        assert config["depth_encoder"] == "vitl"
        assert config["depth_strength"] == 0.7

    def test_get_depth_config_invalid_json(self):
        """get_depth_config should handle invalid JSON gracefully."""
        from videoeditor.processing.shaders import get_depth_config
        config = get_depth_config("not json")
        assert config["enable_vda"] is False
        assert config["enable_normals"] is False
