# coding: utf-8
"""Tests for FaceCam node and synthesizer.

Covers:
- Camera parameter generation (pure math, no GPU)
- Camera preset resolution
- Proxy video camera matrix generation
- FaceCam node registration
- Model manager integration
"""

from __future__ import annotations

import numpy as np
import pytest


# ---------------------------------------------------------------------------
#  Camera parameter math (no GPU)
# ---------------------------------------------------------------------------

class TestGetProxyVideoCameras:
    """Test the camera trajectory generation math."""

    def test_basic_generation(self):
        """Should generate correct numbers of camera views."""
        from core.facecam_synthesizer import get_proxy_video_cameras

        w, h, num_views, fxfycxcy, c2ws = get_proxy_video_cameras(
            num_views=17, w=256, h=256,
        )
        assert w == 256
        assert h == 256
        assert num_views == 17
        assert fxfycxcy.shape == (17, 4)
        assert c2ws.shape == (17, 4, 4)

    def test_single_view(self):
        """Single view should produce one camera."""
        from core.facecam_synthesizer import get_proxy_video_cameras

        w, h, num_views, fxfycxcy, c2ws = get_proxy_video_cameras(
            num_views=1, w=128, h=128,
        )
        assert num_views == 1
        assert fxfycxcy.shape == (1, 4)
        assert c2ws.shape == (1, 4, 4)

    def test_c2w_is_valid_transform(self):
        """Camera-to-world matrices should be valid rigid transforms."""
        from core.facecam_synthesizer import get_proxy_video_cameras

        _, _, _, _, c2ws = get_proxy_video_cameras(num_views=5, w=64, h=64)

        for i in range(5):
            c2w = c2ws[i]
            # Last row should be [0, 0, 0, 1]
            np.testing.assert_allclose(c2w[3, :], [0, 0, 0, 1], atol=1e-6)
            # Rotation part should be orthonormal
            R = c2w[:3, :3]
            np.testing.assert_allclose(
                R @ R.T, np.eye(3), atol=1e-5,
                err_msg=f"Camera {i} rotation is not orthonormal",
            )

    def test_fov_affects_focal_length(self):
        """Wider FOV should result in shorter focal length."""
        from core.facecam_synthesizer import get_proxy_video_cameras

        _, _, _, fxfycxcy_narrow, _ = get_proxy_video_cameras(
            num_views=1, w=256, h=256, start_fov=15, end_fov=15,
        )
        _, _, _, fxfycxcy_wide, _ = get_proxy_video_cameras(
            num_views=1, w=256, h=256, start_fov=60, end_fov=60,
        )
        # Narrow FOV → longer focal length
        assert fxfycxcy_narrow[0, 0] > fxfycxcy_wide[0, 0]

    def test_azimuth_changes_camera_position(self):
        """Different azimuths should produce different camera positions."""
        from core.facecam_synthesizer import get_proxy_video_cameras

        _, _, _, _, c2ws_left = get_proxy_video_cameras(
            num_views=1, w=64, h=64, start_azimuth=-45, end_azimuth=-45,
        )
        _, _, _, _, c2ws_right = get_proxy_video_cameras(
            num_views=1, w=64, h=64, start_azimuth=45, end_azimuth=45,
        )
        # Camera positions should differ
        pos_left = c2ws_left[0, :3, 3]
        pos_right = c2ws_right[0, :3, 3]
        assert not np.allclose(pos_left, pos_right, atol=0.1)


# ---------------------------------------------------------------------------
#  Camera preset resolution
# ---------------------------------------------------------------------------

class TestResolveCameraParams:
    """Test the camera parameter preset resolver."""

    def test_preset_orbit_left(self):
        from core.facecam_synthesizer import resolve_camera_params

        params = resolve_camera_params(preset="orbit_left")
        assert "start_azimuth" in params
        assert "end_azimuth" in params
        assert params["start_azimuth"] == -45
        assert params["end_azimuth"] == 45

    def test_preset_zoom_in(self):
        from core.facecam_synthesizer import resolve_camera_params

        params = resolve_camera_params(preset="zoom_in")
        assert params["start_fov"] > params["end_fov"]

    def test_preset_random(self):
        from core.facecam_synthesizer import resolve_camera_params

        params = resolve_camera_params(preset="random")
        # Should produce valid values within limits
        assert -90 <= params["start_azimuth"] <= 90
        assert -90 <= params["end_azimuth"] <= 90
        assert -60 <= params["start_elevation"] <= 60
        assert -60 <= params["end_elevation"] <= 60
        assert 10 <= params["start_fov"] <= 60
        assert 10 <= params["end_fov"] <= 60

    def test_manual_values(self):
        from core.facecam_synthesizer import resolve_camera_params

        params = resolve_camera_params(
            start_azimuth=30, end_azimuth=-30,
            start_elevation=10, end_elevation=-10,
            start_fov=35, end_fov=15,
        )
        assert params["start_azimuth"] == 30
        assert params["end_azimuth"] == -30
        assert params["start_elevation"] == 10
        assert params["end_elevation"] == -10
        assert params["start_fov"] == 35
        assert params["end_fov"] == 15

    def test_manual_values_clamped(self):
        """Values exceeding limits should be clamped."""
        from core.facecam_synthesizer import resolve_camera_params

        params = resolve_camera_params(
            start_azimuth=200, end_azimuth=-200,
            start_elevation=100, end_elevation=-100,
            start_fov=0, end_fov=100,
        )
        assert params["start_azimuth"] == 90
        assert params["end_azimuth"] == -90
        assert params["start_elevation"] == 60
        assert params["end_elevation"] == -60
        assert params["start_fov"] == 10
        assert params["end_fov"] == 60

    def test_unknown_preset_falls_through(self):
        """Unknown preset name should fall through to manual defaults."""
        from core.facecam_synthesizer import resolve_camera_params

        params = resolve_camera_params(preset="nonexistent_preset")
        # Should get defaults (0,0,0,0,25,25) since no manual values given
        assert params["start_azimuth"] == 0
        assert params["end_azimuth"] == 0

    def test_all_presets_resolve(self):
        """Every defined preset should successfully resolve."""
        from core.facecam_synthesizer import CAMERA_PRESETS, resolve_camera_params

        for preset_name in CAMERA_PRESETS:
            params = resolve_camera_params(preset=preset_name)
            assert isinstance(params, dict)
            assert len(params) == 6, f"Preset {preset_name} missing keys"


# ---------------------------------------------------------------------------
#  Model manager integration
# ---------------------------------------------------------------------------

class TestModelManagerIntegration:
    """Test FaceCam model registry entry."""

    def test_facecam_in_model_info(self):
        """FaceCam should be registered in model_manager._MODEL_INFO."""
        from core.model_manager import _MODEL_INFO

        assert "facecam" in _MODEL_INFO
        info = _MODEL_INFO["facecam"]
        assert "name" in info
        assert "size" in info
        assert "url" in info
        assert info["url"] == "https://huggingface.co/wlyu/FaceCam"


# ---------------------------------------------------------------------------
#  VRAM utils integration
# ---------------------------------------------------------------------------

class TestVRAMUtilsIntegration:
    """Test FaceCam is in VRAM cleanup registry."""

    def test_facecam_in_synthesizer_modules(self):
        """facecam_synthesizer should be in ALL_SYNTHESIZER_MODULES."""
        from core._vram_utils import ALL_SYNTHESIZER_MODULES

        assert "facecam_synthesizer" in ALL_SYNTHESIZER_MODULES


# ---------------------------------------------------------------------------
#  Node registration
# ---------------------------------------------------------------------------

class TestNodeRegistration:
    """Test FaceCam node is registered in ComfyUI."""

    def test_facecam_node_class_exists(self):
        """FaceCamNode class should be importable."""
        from nodes.facecam_node import FaceCamNode
        assert FaceCamNode is not None

    def test_facecam_node_has_required_attrs(self):
        """FaceCamNode should have ComfyUI required attributes."""
        from nodes.facecam_node import FaceCamNode

        assert hasattr(FaceCamNode, "INPUT_TYPES")
        assert hasattr(FaceCamNode, "FUNCTION")
        assert hasattr(FaceCamNode, "RETURN_TYPES")
        assert hasattr(FaceCamNode, "CATEGORY")

        inputs = FaceCamNode.INPUT_TYPES()
        assert "required" in inputs
        assert "model_high" in inputs["required"]
        assert "prompt" in inputs["required"]
        assert "high_model_ratio" in inputs["required"]
        assert "camera_preset" in inputs["required"]
        assert "num_frames" in inputs["required"]
        assert "width" in inputs["required"]
        assert "height" in inputs["required"]

    def test_facecam_node_optional_inputs(self):
        """FaceCamNode should accept optional model_low + facecam_low inputs."""
        from nodes.facecam_node import FaceCamNode

        inputs = FaceCamNode.INPUT_TYPES()
        assert "optional" in inputs
        opt = inputs["optional"]
        assert "model_low" in opt
        assert "images" in opt
        assert "video_path" in opt

    def test_facecam_node_camera_controls(self):
        """FaceCamNode should have manual camera control widgets."""
        from nodes.facecam_node import FaceCamNode

        inputs = FaceCamNode.INPUT_TYPES()
        optional = inputs.get("optional", {})
        for param in ("start_azimuth", "end_azimuth",
                       "start_elevation", "end_elevation",
                       "start_fov", "end_fov"):
            assert param in optional, f"Missing camera control: {param}"


# ---------------------------------------------------------------------------
#  Gaussian model loading (mock test, no GPU)
# ---------------------------------------------------------------------------

class TestGaussianModelLoading:
    """Test Gaussian model loading utilities (without actual PLY file)."""

    def test_check_rasterizer_returns_bool(self):
        """_check_gaussian_rasterizer should return bool."""
        from core.facecam_synthesizer import _check_gaussian_rasterizer

        result = _check_gaussian_rasterizer()
        assert isinstance(result, bool)

    def test_facecam_dir_helper(self):
        """_get_facecam_dir should return a Path."""
        from core.facecam_synthesizer import _get_facecam_dir

        result = _get_facecam_dir()
        assert hasattr(result, "exists")  # Path-like

    def test_ply_path_helper(self):
        """_get_ply_path should return a Path."""
        from core.facecam_synthesizer import _get_ply_path

        result = _get_ply_path()
        assert str(result).endswith("gaussians.ply")


# ---------------------------------------------------------------------------
#  Cleanup / offload
# ---------------------------------------------------------------------------

class TestCleanup:
    """Test cleanup and offload functions."""

    def test_cleanup_no_crash(self):
        """cleanup() should not crash when nothing is loaded."""
        from core.facecam_synthesizer import cleanup
        cleanup()  # should be no-op

    def test_offload_no_crash(self):
        """offload_to_cpu() should not crash when nothing is loaded."""
        from core.facecam_synthesizer import offload_to_cpu
        offload_to_cpu()  # should be no-op
