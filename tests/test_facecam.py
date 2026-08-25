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
        # Anchored at frontal and sweeping one direction, per upstream
        # large_pose. The old -45→+45 was double the trained range and left
        # both ends in profile where the face mesh can't be detected.
        assert params["start_azimuth"] == 0
        assert params["end_azimuth"] == -45

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
#  Camera preset ranges
# ---------------------------------------------------------------------------

class TestCameraPresetRanges:
    """Presets must stay inside the range FaceCam was trained on.

    Upstream sweeps max_azimuth=45 in ONE direction from frontal. A symmetric
    -45→+45 preset is double that and puts both ends in profile, where
    MediaPipe cannot resolve a face mesh.
    """

    def test_presets_start_frontal(self):
        from core.facecam_synthesizer import CAMERA_PRESETS

        for name, v in CAMERA_PRESETS.items():
            if v is None:
                continue
            assert v[0] == 0, f"{name} starts at azimuth {v[0]}, not frontal"
            assert v[2] == 0, f"{name} starts at elevation {v[2]}, not frontal"

    def test_presets_within_upstream_limits(self):
        from core.facecam_synthesizer import CAMERA_PRESETS

        for name, v in CAMERA_PRESETS.items():
            if v is None:
                continue
            start_az, end_az, start_el, end_el, start_fov, end_fov = v
            assert abs(end_az) <= 45, f"{name} azimuth {end_az} exceeds 45"
            assert abs(end_el) <= 30, f"{name} elevation {end_el} exceeds 30"
            for fov in (start_fov, end_fov):
                assert 25 <= fov <= 55, f"{name} fov {fov} outside 40±15"

    def test_orbit_presets_are_opposite(self):
        from core.facecam_synthesizer import CAMERA_PRESETS

        left = CAMERA_PRESETS["orbit_left"]
        right = CAMERA_PRESETS["orbit_right"]
        assert left[1] == -right[1], "orbit_left/right must mirror each other"

    def test_random_preset_spans_one_direction(self):
        from core.facecam_synthesizer import resolve_camera_params

        for _ in range(50):
            p = resolve_camera_params(preset="random")
            assert p["start_azimuth"] == 0
            assert abs(p["end_azimuth"]) <= 45
            assert abs(p["end_elevation"]) <= 30
            assert 25 <= p["end_fov"] <= 55


# ---------------------------------------------------------------------------
#  Analytic face mesh
# ---------------------------------------------------------------------------

class TestCanonicalMesh:
    """The canonical model is extracted from the .task bundle already on disk."""

    def test_loads_468_vertices(self):
        from core.facecam_mesh import load_canonical_face, NUM_CANONICAL_LANDMARKS
        from core.facecam_synthesizer import _get_landmarker_path

        verts = load_canonical_face(str(_get_landmarker_path()))
        assert verts.shape == (NUM_CANONICAL_LANDMARKS, 3)

    def test_covers_the_drawing_topology(self):
        """Every index the tesselation references must exist in the mesh."""
        from mediapipe.tasks.python.vision import face_landmarker as mp_face
        from core.facecam_mesh import load_canonical_face
        from core.facecam_synthesizer import _get_landmarker_path

        verts = load_canonical_face(str(_get_landmarker_path()))
        tess = mp_face.FaceLandmarksConnections.FACE_LANDMARKS_TESSELATION
        assert max(max(c.start, c.end) for c in tess) < len(verts)

    def test_is_centred_and_normalised(self):
        from core.facecam_mesh import load_canonical_face
        from core.facecam_synthesizer import _get_landmarker_path

        verts = load_canonical_face(str(_get_landmarker_path()))
        assert np.allclose(verts.mean(axis=0), 0, atol=1e-6)
        assert np.abs(verts).max() == pytest.approx(1.0)

    def test_anatomy_is_right_way_round(self):
        """Guards against a transposed or mis-strided vertex buffer."""
        from core.facecam_mesh import load_canonical_face
        from core.facecam_synthesizer import _get_landmarker_path

        verts = load_canonical_face(str(_get_landmarker_path()))
        assert int(np.argmin(verts[:, 1])) == 152, "landmark 152 should be the chin"
        assert verts[1, 2] == pytest.approx(verts[:, 2].max(), rel=0.05), \
            "landmark 1 (nose tip) should be the most forward point"

    def test_rejects_a_bundle_without_geometry(self, tmp_path):
        import zipfile
        from core.facecam_mesh import load_canonical_face

        bogus = tmp_path / "empty.task"
        with zipfile.ZipFile(bogus, "w") as z:
            z.writestr("something_else.tflite", b"\x00")
        with pytest.raises(ValueError):
            load_canonical_face(str(bogus))


class TestAnalyticProjection:
    """Projection must be deterministic and track the camera path."""

    @staticmethod
    def _calib():
        return {"params": [1.641, -0.009, -0.011, float(np.log(0.396)),
                           -0.015, -0.529, -0.186],
                "rms_px": 4.4, "views": 5}

    def _project(self, preset_params, frames=9, res=480):
        from core.facecam_mesh import project_landmarks
        from core.facecam_synthesizer import _get_landmarker_path

        return project_landmarks(self._calib(), preset_params, frames, res,
                                 str(_get_landmarker_path()))

    def test_deterministic(self):
        p = {"start_azimuth": 0, "end_azimuth": -45, "start_elevation": 0,
             "end_elevation": 0, "start_fov": 40, "end_fov": 40}
        a, b = self._project(p), self._project(p)
        assert all(np.array_equal(x, y) for x, y in zip(a, b))

    def test_one_full_landmark_set_per_frame(self):
        from core.facecam_mesh import NUM_CANONICAL_LANDMARKS

        p = {"start_azimuth": 0, "end_azimuth": -45, "start_elevation": 0,
             "end_elevation": 0, "start_fov": 40, "end_fov": 40}
        out = self._project(p, frames=12)
        assert len(out) == 12
        assert all(f.shape == (NUM_CANONICAL_LANDMARKS, 2) for f in out)

    def test_motion_is_smooth(self):
        """No frame-to-frame jump should dwarf the median — that is the
        signature of detector jitter and interpolation seams."""
        p = {"start_azimuth": 0, "end_azimuth": -45, "start_elevation": 0,
             "end_elevation": 0, "start_fov": 40, "end_fov": 40}
        centres = np.array([f.mean(axis=0) for f in self._project(p, frames=41)])
        steps = np.linalg.norm(np.diff(centres, axis=0), axis=1)
        assert steps.max() < 3.0 * np.median(steps)

    def test_orbits_mirror_each_other(self):
        """The detected path was asymmetric (35/41 vs 19/41); this must not be."""
        base = {"start_elevation": 0, "end_elevation": 0,
                "start_fov": 40, "end_fov": 40}
        left = np.array([f.mean(axis=0)[0] for f in self._project(
            {**base, "start_azimuth": 0, "end_azimuth": -45})])
        right = np.array([f.mean(axis=0)[0] for f in self._project(
            {**base, "start_azimuth": 0, "end_azimuth": 45})])
        centre = 240.0
        assert np.abs((left - centre) + (right - centre)).max() < 0.05 * centre

    def test_static_camera_does_not_drift(self):
        p = {"start_azimuth": 10, "end_azimuth": 10, "start_elevation": 0,
             "end_elevation": 0, "start_fov": 40, "end_fov": 40}
        out = self._project(p, frames=6)
        assert all(np.allclose(out[0], f) for f in out[1:])


class TestSubjectAnchor:
    """The mesh must land on the subject's real face, not fill the frame.

    A frame-filling centred mesh makes the DiT render a large centred face and
    drop the rest of the composition — the reported 'lost subject' bug.
    """

    def test_ref_frame_maps_onto_target(self):
        from core.facecam_mesh import anchor_to_subject, _bbox

        # a fake mesh: unit square of points, plus a moved copy
        base = np.array([[0, 0], [10, 0], [0, 10], [10, 10]], dtype=np.float64)
        per_frame = [base, base + [5, 0]]
        target = (100.0, 60.0, 40.0)  # cx, cy, height
        out = anchor_to_subject(per_frame, target)

        cx, cy, h = _bbox(out[0])
        assert cx == pytest.approx(100.0)
        assert cy == pytest.approx(60.0)
        assert h == pytest.approx(40.0)

    def test_motion_scales_with_face(self):
        """A smaller anchored face must sweep proportionally fewer pixels."""
        from core.facecam_mesh import anchor_to_subject

        base = np.array([[0, 0], [10, 0], [0, 10], [10, 10]], dtype=np.float64)
        per_frame = [base, base + [5, 0]]           # 5 px of motion at size 10
        target = (100.0, 60.0, 5.0)                 # shrink to half size
        out = anchor_to_subject(per_frame, target)
        motion = np.linalg.norm(out[1].mean(0) - out[0].mean(0))
        assert motion == pytest.approx(2.5)          # motion halves with size

    def test_does_not_mutate_input(self):
        from core.facecam_mesh import anchor_to_subject

        base = np.array([[0, 0], [10, 10]], dtype=np.float64)
        per_frame = [base.copy()]
        _ = anchor_to_subject(per_frame, (5.0, 5.0, 2.0))
        assert np.array_equal(per_frame[0], base)

    def test_anchored_conditioning_lands_on_anchor(self):
        """End-to-end: the drawn mesh's frame-0 box matches the subject box."""
        from core.facecam_synthesizer import (
            get_analytic_conditioning, resolve_camera_params,
        )

        H, W = 704, 480
        anchor = {"cx": 0.5, "cy": 0.25, "height": 0.12}
        frames = get_analytic_conditioning(
            resolve_camera_params(preset="orbit_left"), 5, H, W,
            subject_anchor=anchor,
        )
        ys, xs = np.where(frames[0][:, :, 0] < 250)
        cy = (ys.min() + ys.max()) / 2 / H
        fh = (ys.max() - ys.min()) / H
        assert cy == pytest.approx(0.25, abs=0.03)
        assert fh == pytest.approx(0.12, abs=0.03)

    def test_centred_mesh_is_much_larger_than_a_typical_subject(self):
        """Guards the premise: without anchoring the mesh really does dominate."""
        from core.facecam_synthesizer import (
            get_analytic_conditioning, resolve_camera_params,
        )

        frames = get_analytic_conditioning(
            resolve_camera_params(preset="orbit_left"), 3, 704, 480,
            subject_anchor=None,
        )
        ys, _ = np.where(frames[0][:, :, 0] < 250)
        assert (ys.max() - ys.min()) / 704 > 0.25  # vs a real face ~0.12


class TestMeshSourceFallback:
    """'auto' must degrade to detection rather than fail the run."""

    def test_calibration_rejects_too_few_views(self, monkeypatch):
        """Too few detections must raise so 'auto' can fall back, not ship a
        garbage fit that would silently mis-place the mesh for every frame."""
        import core.facecam_mesh as fm
        from core.facecam_synthesizer import _get_landmarker_path

        monkeypatch.setattr(
            fm, "_detect_calibration_views",
            lambda *a, **k: {(0, 0): np.zeros((468, 2))},
        )
        with pytest.raises(RuntimeError, match="calibration views"):
            fm.solve_calibration(str(_get_landmarker_path()))

    def test_calibration_rejects_a_bad_fit(self, monkeypatch):
        """A converged but wildly wrong fit must also be refused."""
        import core.facecam_mesh as fm
        from core.facecam_synthesizer import _get_landmarker_path

        rng = np.random.default_rng(0)
        monkeypatch.setattr(
            fm, "_detect_calibration_views",
            lambda *a, **k: {
                (0, 0): rng.uniform(0, 480, (468, 2)),
                (-15, 0): rng.uniform(0, 480, (468, 2)),
                (15, 0): rng.uniform(0, 480, (468, 2)),
            },
        )
        with pytest.raises(RuntimeError, match="residual"):
            fm.solve_calibration(str(_get_landmarker_path()))

    def test_draw_face_mesh_blank_without_landmarks(self):
        from core.facecam_synthesizer import draw_face_mesh

        frame = draw_face_mesh(None, (64, 64, 3))
        assert frame.shape == (64, 64, 3)
        assert len(np.unique(frame)) == 1 and frame[0, 0, 0] == 255

    def test_draw_face_mesh_renders_landmarks(self):
        from core.facecam_synthesizer import draw_face_mesh
        from core.facecam_mesh import (
            load_canonical_face, to_normalized_landmarks,
        )
        from core.facecam_synthesizer import _get_landmarker_path

        verts = load_canonical_face(str(_get_landmarker_path()))
        pixels = (verts[:, :2] * 0.4 + 0.5) * 256
        frame = draw_face_mesh(to_normalized_landmarks(pixels, 256), (256, 256, 3))
        assert len(np.unique(frame)) > 1, "mesh drew nothing"


# ---------------------------------------------------------------------------
#  Landmark gap interpolation
# ---------------------------------------------------------------------------

class TestLandmarkInterpolation:
    """Blank conditioning frames leave the model with no camera signal."""

    @staticmethod
    def _lm(v):
        from mediapipe.tasks.python.components.containers.landmark import (
            NormalizedLandmark,
        )
        return [NormalizedLandmark(x=v, y=v * 2, z=0.0)]

    def test_interior_gap_is_interpolated(self):
        from core.facecam_synthesizer import _interpolate_landmark_gaps

        out = _interpolate_landmark_gaps(
            [self._lm(0.2), None, None, None, self._lm(0.6)]
        )
        xs = [o[0].x for o in out]
        assert all(o is not None for o in out)
        assert xs[0] == pytest.approx(0.2, abs=1e-5)
        assert xs[-1] == pytest.approx(0.6, abs=1e-5)
        # evenly spaced across the gap, not a frozen hold
        assert xs[2] == pytest.approx(0.4, abs=1e-5)
        assert all(b > a for a, b in zip(xs, xs[1:]))

    def test_leading_and_trailing_gaps_filled(self):
        from core.facecam_synthesizer import _interpolate_landmark_gaps

        out = _interpolate_landmark_gaps([None, None, self._lm(0.5), None])
        assert all(o is not None for o in out)
        assert [o[0].x for o in out] == pytest.approx([0.5] * 4, abs=1e-5)

    def test_all_missing_stays_missing(self):
        from core.facecam_synthesizer import _interpolate_landmark_gaps

        assert _interpolate_landmark_gaps([None, None]) == [None, None]

    def test_no_gaps_is_a_passthrough(self):
        from core.facecam_synthesizer import _interpolate_landmark_gaps

        raw = [self._lm(0.1), self._lm(0.3)]
        assert [o[0].x for o in _interpolate_landmark_gaps(raw)] == [0.1, 0.3]


# ---------------------------------------------------------------------------
#  Proxy framing
# ---------------------------------------------------------------------------

class TestProxyFraming:
    """The proxy must be centred to match the centre-cropped input video."""

    @staticmethod
    def _marked_square(size=480):
        f = np.full((size, size, 3), 255, np.uint8)
        c = size // 2
        f[c - 20:c + 20, c - 20:c + 20] = 0
        return f

    def test_content_is_centred_in_landscape(self):
        from core.facecam_synthesizer import _fit_frame_to_target

        out = _fit_frame_to_target(self._marked_square(), 480, 832)
        assert out.shape == (480, 832, 3)
        ys, xs = np.where(out[:, :, 0] == 0)
        assert xs.mean() == pytest.approx(416, abs=3), "not horizontally centred"
        assert ys.mean() == pytest.approx(240, abs=3), "not vertically centred"

    def test_content_is_centred_in_portrait(self):
        from core.facecam_synthesizer import _fit_frame_to_target

        out = _fit_frame_to_target(self._marked_square(), 704, 480)
        assert out.shape == (704, 480, 3)
        ys, xs = np.where(out[:, :, 0] == 0)
        assert xs.mean() == pytest.approx(240, abs=3)
        assert ys.mean() == pytest.approx(352, abs=3)

    def test_contains_rather_than_crops(self):
        """The whole head must survive — cover-cropping loses crown and chin."""
        from core.facecam_synthesizer import _fit_frame_to_target

        src = np.full((480, 480, 3), 255, np.uint8)
        src[0:5, :] = 0      # top edge marker
        src[-5:, :] = 0      # bottom edge marker
        out = _fit_frame_to_target(src, 480, 832)
        assert (out == 0).any(), "source content was cropped away entirely"
        ys = np.where((out[:, :, 0] == 0).any(axis=1))[0]
        assert ys.min() < 10 and ys.max() > 470, "top/bottom markers were cropped"

    def test_identity_when_already_matching(self):
        from core.facecam_synthesizer import _fit_frame_to_target

        f = self._marked_square()
        assert _fit_frame_to_target(f, 480, 480) is f


# ---------------------------------------------------------------------------
#  Weight injection dtype
# ---------------------------------------------------------------------------

class TestInferenceDtype:
    """FaceCam weights must be injected in the base model's compute dtype.

    Injecting bf16 into an fp8/fp16 base makes every replaced linear fail with
    "self and mat2 must have the same dtype, but got Half and BFloat16".
    """

    @staticmethod
    def _model(inference=None, weight=None, has_inference=True):
        class _Model:
            def get_dtype(self):
                return weight

            if has_inference:
                def get_dtype_inference(self):
                    return inference

        return _Model()

    def test_prefers_manual_cast_dtype(self):
        """An fp8 base that computes in fp16 should yield fp16, not bf16."""
        import torch
        from core.facecam_synthesizer import _resolve_inference_dtype

        model = self._model(inference=torch.float16, weight=torch.float16)
        assert _resolve_inference_dtype(model) is torch.float16

    def test_plain_bf16_model_unchanged(self):
        """A stock bf16 Wan base keeps the previous behaviour."""
        import torch
        from core.facecam_synthesizer import _resolve_inference_dtype

        model = self._model(inference=torch.bfloat16, weight=torch.bfloat16)
        assert _resolve_inference_dtype(model) is torch.bfloat16

    def test_fp8_never_returned(self):
        """fp8 is a storage dtype — injected params need a compute dtype."""
        import torch
        from core.facecam_synthesizer import _resolve_inference_dtype

        model = self._model(inference=torch.float8_e4m3fn, weight=torch.float8_e4m3fn)
        assert _resolve_inference_dtype(model) is torch.bfloat16

    def test_falls_back_without_inference_accessor(self):
        """Older ComfyUI builds lack get_dtype_inference()."""
        import torch
        from core.facecam_synthesizer import _resolve_inference_dtype

        model = self._model(weight=torch.float16, has_inference=False)
        assert _resolve_inference_dtype(model) is torch.float16

    def test_falls_back_with_no_accessors(self):
        """An unrecognised patcher must not crash the run."""
        import torch
        from core.facecam_synthesizer import _resolve_inference_dtype

        assert _resolve_inference_dtype(object()) is torch.bfloat16


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
