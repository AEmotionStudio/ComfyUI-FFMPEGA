# coding: utf-8
"""Analytic face-mesh conditioning for FaceCam.

FaceCam encodes camera pose as a drawn MediaPipe face mesh. The original
pipeline produced that mesh by rendering a 3D Gaussian proxy head along the
camera path and running a face *detector* over the renders — throwing away the
camera pose we computed analytically, then paying a detector to guess it back.
MediaPipe loses the mesh past roughly 40-50° of yaw, which is exactly the pose a
camera orbit exists to produce, so conditioning went blank at the extremes.

This module removes the round-trip: pose MediaPipe's own canonical face model
with the same camera matrices and project it. Coverage is total by construction,
motion is smooth because it is an analytic function of the camera path, and
`orbit_left`/`orbit_right` are exact mirrors instead of differing by however well
the detector coped with each direction.

The canonical model is not shipped in the mediapipe wheel, but the
``face_landmarker`` task bundle already on disk is a zip containing
``geometry_pipeline_metadata_landmarks.binarypb``, whose ``Mesh3d`` holds the 468
canonical vertices. No vendored asset is required.
"""

from __future__ import annotations

import hashlib
import json
import logging
import struct
import zipfile
from functools import lru_cache
from pathlib import Path

import numpy as np

log = logging.getLogger("ffmpega")

_METADATA_ENTRY = "geometry_pipeline_metadata_landmarks.binarypb"

# MediaPipe's face mesh is 468 points; the 478-point variant appends 10 iris
# landmarks that the tesselation/contour topology does not reference.
NUM_CANONICAL_LANDMARKS = 468

# Calibration poses (azimuth, elevation) in degrees, relative to frontal. Kept
# modest on purpose — these only need to be poses the detector handles well, so
# the fit has clean observations to work from.
_CALIBRATION_POSES = (
    (0, 0), (-15, 0), (15, 0), (0, -15), (0, 15), (-25, 0), (25, 0),
)
_CALIBRATION_FOV = 40
_CALIBRATION_RESOLUTION = 480
_MIN_CALIBRATION_VIEWS = 3
# Prototype fit landed at 4.4 px RMS / 9.0 px held-out on a 480 px frame; well
# past this and the fit has not found the right basin.
_MAX_CALIBRATION_RMS_PX = 15.0
_FIT_RESTARTS = 8


# ---------------------------------------------------------------------------
#  Canonical mesh extraction (protobuf wire format)
# ---------------------------------------------------------------------------

def _read_varint(buf: bytes, i: int) -> tuple[int, int]:
    result = shift = 0
    while True:
        byte = buf[i]
        i += 1
        result |= (byte & 0x7F) << shift
        shift += 7
        if not byte & 0x80:
            return result, i


def _read_fields(buf: bytes) -> list[tuple[int, int, object]]:
    """Walk a serialized protobuf, returning (field_number, wire_type, value)."""
    i = 0
    out: list[tuple[int, int, object]] = []
    while i < len(buf):
        key, i = _read_varint(buf, i)
        field, wire = key >> 3, key & 7
        if wire == 0:
            value, i = _read_varint(buf, i)
        elif wire == 2:
            length, i = _read_varint(buf, i)
            value = buf[i:i + length]
            i += length
        elif wire == 5:
            value = buf[i:i + 4]
            i += 4
        elif wire == 1:
            value = buf[i:i + 8]
            i += 8
        else:
            raise ValueError(f"unsupported protobuf wire type {wire}")
        out.append((field, wire, value))
    return out


@lru_cache(maxsize=4)
def load_canonical_face(landmarker_path: str) -> np.ndarray:
    """Return the canonical face model as (468, 3), centred and unit-normalised.

    Raises:
        FileNotFoundError / ValueError if the bundle does not carry the geometry
        metadata, so callers can fall back to the detection path.
    """
    path = Path(landmarker_path)
    if not path.is_file():
        raise FileNotFoundError(f"landmarker task not found: {path}")
    if not zipfile.is_zipfile(path):
        raise ValueError(f"landmarker task is not a zip bundle: {path}")

    with zipfile.ZipFile(path) as bundle:
        if _METADATA_ENTRY not in bundle.namelist():
            raise ValueError(
                f"{path.name} has no {_METADATA_ENTRY}; cannot build the "
                f"canonical face model"
            )
        blob = bundle.read(_METADATA_ENTRY)

    # GeometryPipelineMetadata.canonical_mesh is by far the largest submessage.
    submessages = [v for _, wire, v in _read_fields(blob) if wire == 2]
    if not submessages:
        raise ValueError("no submessage found in geometry pipeline metadata")
    mesh = _read_fields(max(submessages, key=len))

    # Mesh3d.vertex_buffer is field 3, repeated float, written unpacked.
    raw = [struct.unpack("<f", v)[0]
           for field, wire, v in mesh if field == 3 and wire == 5]
    if not raw or len(raw) % 5:
        raise ValueError(
            f"unexpected vertex buffer length {len(raw)} (want a multiple of 5)"
        )

    verts = np.asarray(raw, dtype=np.float64).reshape(-1, 5)[:, :3]
    if len(verts) < NUM_CANONICAL_LANDMARKS:
        raise ValueError(
            f"canonical mesh has {len(verts)} vertices, need at least "
            f"{NUM_CANONICAL_LANDMARKS}"
        )
    verts = verts[:NUM_CANONICAL_LANDMARKS]

    verts = verts - verts.mean(axis=0)
    scale = float(np.abs(verts).max())
    if scale <= 0:
        raise ValueError("degenerate canonical mesh")
    return verts / scale


# ---------------------------------------------------------------------------
#  Calibration: place the canonical head in the proxy's world space
# ---------------------------------------------------------------------------

def _camera_for(azimuth: float, elevation: float, resolution: int):
    """Intrinsics + camera-to-world for one proxy pose.

    Uses the same generator that drives the proxy render, so the analytic mesh
    follows the identical trajectory by construction.
    """
    try:
        from .facecam_synthesizer import get_proxy_video_cameras
    except ImportError:
        from core.facecam_synthesizer import get_proxy_video_cameras  # type: ignore

    _, _, _, intrinsics, c2ws = get_proxy_video_cameras(
        num_views=1, w=resolution, h=resolution,
        start_azimuth=azimuth, end_azimuth=azimuth,
        start_elevation=elevation, end_elevation=elevation,
        start_fov=_CALIBRATION_FOV, end_fov=_CALIBRATION_FOV,
    )
    return (np.asarray(intrinsics[0], dtype=np.float64),
            np.asarray(c2ws[0], dtype=np.float64))


def _project(canonical, params, intrinsics, w2c) -> np.ndarray:
    """Project canonical vertices through one camera. Returns (N, 2) pixels."""
    import cv2

    rotation, _ = cv2.Rodrigues(params[:3])
    scale = np.exp(params[3])
    translation = params[4:7]

    world = scale * (canonical @ rotation.T) + translation
    homogeneous = np.hstack([world, np.ones((len(world), 1))])
    cam = (w2c @ homogeneous.T).T[:, :3]

    fx, fy, cx, cy = intrinsics
    depth = np.clip(cam[:, 2], 1e-6, None)
    return np.stack([fx * cam[:, 0] / depth + cx,
                     fy * cam[:, 1] / depth + cy], axis=1)


def _detect_calibration_views(landmarker_path: str, ply_path) -> dict:
    """Render + detect the calibration poses. Returns {(az, el): (N, 2) pixels}."""
    import mediapipe as mp
    from mediapipe.tasks import python as mp_python
    from mediapipe.tasks.python import vision

    try:
        from .facecam_synthesizer import render_proxy_video
    except ImportError:
        from core.facecam_synthesizer import render_proxy_video  # type: ignore

    detector = vision.FaceLandmarker.create_from_options(
        vision.FaceLandmarkerOptions(
            base_options=mp_python.BaseOptions(
                model_asset_path=str(landmarker_path)
            ),
            num_faces=1,
        )
    )

    res = _CALIBRATION_RESOLUTION
    observations: dict[tuple[float, float], np.ndarray] = {}
    for azimuth, elevation in _CALIBRATION_POSES:
        frame = render_proxy_video(
            camera_params={
                "start_azimuth": azimuth, "end_azimuth": azimuth,
                "start_elevation": elevation, "end_elevation": elevation,
                "start_fov": _CALIBRATION_FOV, "end_fov": _CALIBRATION_FOV,
            },
            num_frames=1,
            render_resolution=res,
            ply_path=ply_path,
        )[0]
        result = detector.detect(
            mp.Image(image_format=mp.ImageFormat.SRGB,
                     data=np.ascontiguousarray(frame))
        )
        if not result.face_landmarks:
            continue
        landmarks = result.face_landmarks[0][:NUM_CANONICAL_LANDMARKS]
        if len(landmarks) < NUM_CANONICAL_LANDMARKS:
            continue
        observations[(azimuth, elevation)] = np.array(
            [[p.x * res, p.y * res] for p in landmarks], dtype=np.float64
        )
    return observations


def solve_calibration(landmarker_path: str, ply_path=None) -> dict:
    """Fit a 7-DOF similarity placing the canonical face in proxy world space.

    Returns a dict with ``params`` (rotvec 3, log-scale 1, translation 3),
    ``rms_px`` and ``views``.

    Raises:
        RuntimeError if too few views detect or the fit does not converge to a
        usable residual — the caller should fall back to detection.
    """
    from scipy.optimize import least_squares

    canonical = load_canonical_face(str(landmarker_path))
    observations = _detect_calibration_views(str(landmarker_path), ply_path)

    if len(observations) < _MIN_CALIBRATION_VIEWS:
        raise RuntimeError(
            f"only {len(observations)} of {len(_CALIBRATION_POSES)} calibration "
            f"views produced a face mesh (need {_MIN_CALIBRATION_VIEWS})"
        )

    # Precompute the cameras once; the residual is evaluated thousands of times.
    cameras = {}
    for pose in observations:
        intrinsics, c2w = _camera_for(pose[0], pose[1], _CALIBRATION_RESOLUTION)
        cameras[pose] = (intrinsics, np.linalg.inv(c2w))

    poses = list(observations)

    def residual(params):
        return np.concatenate([
            (_project(canonical, params, *cameras[p]) - observations[p]).ravel()
            for p in poses
        ])

    # Orientation is multi-modal, so restart from several seeds. Seeds are fixed
    # so calibration is reproducible run to run.
    best = None
    for seed in range(_FIT_RESTARTS):
        rng = np.random.default_rng(seed)
        x0 = np.concatenate([rng.normal(0, 1.5, 3), [np.log(0.5)], [0.0, 0.0, 0.0]])
        try:
            fit = least_squares(residual, x0, method="lm", max_nfev=5000)
        except Exception as e:  # noqa: BLE001 - a bad seed must not kill the run
            log.debug("[FaceCam] calibration seed %d failed: %s", seed, e)
            continue
        if best is None or fit.cost < best.cost:
            best = fit

    if best is None:
        raise RuntimeError("no calibration restart converged")

    residuals = residual(best.x)
    rms = float(np.sqrt(2.0 * best.cost / len(residuals)))
    if not np.isfinite(rms) or rms > _MAX_CALIBRATION_RMS_PX:
        raise RuntimeError(
            f"calibration residual {rms:.1f}px exceeds {_MAX_CALIBRATION_RMS_PX}px"
        )

    return {
        "params": [float(v) for v in best.x],
        "rms_px": rms,
        "views": len(observations),
    }


# ---------------------------------------------------------------------------
#  Calibration cache
# ---------------------------------------------------------------------------

def _cache_path() -> Path:
    try:
        from .facecam_synthesizer import _get_facecam_dir
    except ImportError:
        from core.facecam_synthesizer import _get_facecam_dir  # type: ignore
    return _get_facecam_dir() / "mesh_calibration.json"


def _cache_key(ply_path) -> str:
    """Identify the proxy geometry this calibration belongs to.

    The solved parameters are world-space, so output resolution does not enter
    the key — only the head model and the orbit geometry it was fitted against.
    """
    try:
        from . import facecam_synthesizer as fs
    except ImportError:
        import core.facecam_synthesizer as fs  # type: ignore

    digest = hashlib.sha256()
    path = Path(ply_path) if ply_path else fs._get_ply_path()
    if path.is_file():
        stat = path.stat()
        digest.update(f"{path.name}:{stat.st_size}:{int(stat.st_mtime)}".encode())
    else:
        digest.update(b"missing-ply")
    digest.update(
        f"|{fs._PROXY_RADIUS}|{fs._PROXY_BASE_AZIMUTH}|{fs._PROXY_BASE_ELEVATION}"
        f"|{_CALIBRATION_FOV}|{_CALIBRATION_RESOLUTION}".encode()
    )
    return digest.hexdigest()[:16]


def get_calibration(landmarker_path: str, ply_path=None, *, refresh: bool = False) -> dict:
    """Return a cached calibration, solving and storing one if needed."""
    key = _cache_key(ply_path)
    cache_file = _cache_path()

    if not refresh and cache_file.is_file():
        try:
            cached = json.loads(cache_file.read_text())
            if cached.get("key") == key:
                log.info(
                    "[FaceCam] Using cached mesh calibration (%.1f px RMS, %d views)",
                    cached.get("rms_px", float("nan")), cached.get("views", 0),
                )
                return cached
        except Exception as e:  # noqa: BLE001 - a bad cache must not be fatal
            log.debug("[FaceCam] Ignoring unreadable calibration cache: %s", e)

    log.info("[FaceCam] Calibrating analytic face mesh (one-off)...")
    calibration = solve_calibration(landmarker_path, ply_path)
    calibration["key"] = key

    try:
        cache_file.write_text(json.dumps(calibration, indent=2))
        log.info(
            "[FaceCam] Mesh calibration solved: %.1f px RMS over %d views → %s",
            calibration["rms_px"], calibration["views"], cache_file,
        )
    except Exception as e:  # noqa: BLE001 - caching is an optimisation
        log.warning("[FaceCam] Could not cache calibration: %s", e)

    return calibration


# ---------------------------------------------------------------------------
#  Projection
# ---------------------------------------------------------------------------

def project_landmarks(
    calibration: dict,
    camera_params: dict,
    num_frames: int,
    resolution: int,
    landmarker_path: str,
) -> list[np.ndarray]:
    """Project the calibrated face mesh along a camera trajectory.

    Returns one (468, 2) array of pixel coordinates per frame.
    """
    try:
        from .facecam_synthesizer import get_proxy_video_cameras
    except ImportError:
        from core.facecam_synthesizer import get_proxy_video_cameras  # type: ignore

    canonical = load_canonical_face(str(landmarker_path))
    params = np.asarray(calibration["params"], dtype=np.float64)

    _, _, _, intrinsics, c2ws = get_proxy_video_cameras(
        num_views=num_frames, w=resolution, h=resolution,
        start_azimuth=camera_params.get("start_azimuth", 0),
        end_azimuth=camera_params.get("end_azimuth", 0),
        start_elevation=camera_params.get("start_elevation", 0),
        end_elevation=camera_params.get("end_elevation", 0),
        start_fov=camera_params.get("start_fov", _CALIBRATION_FOV),
        end_fov=camera_params.get("end_fov", _CALIBRATION_FOV),
    )

    return [
        _project(
            canonical, params,
            np.asarray(intrinsics[i], dtype=np.float64),
            np.linalg.inv(np.asarray(c2ws[i], dtype=np.float64)),
        )
        for i in range(num_frames)
    ]


def to_normalized_landmarks(pixels: np.ndarray, width: int, height: int | None = None) -> list:
    """Convert (N, 2) pixel coordinates to MediaPipe NormalizedLandmark objects.

    ``height`` defaults to ``width`` for square frames.
    """
    from mediapipe.tasks.python.components.containers.landmark import (
        NormalizedLandmark,
    )
    if height is None:
        height = width
    return [
        NormalizedLandmark(x=float(x / width), y=float(y / height), z=0.0)
        for x, y in pixels
    ]


def _bbox(points: np.ndarray) -> tuple:
    """Axis-aligned bbox of (N, 2) points → (cx, cy, height)."""
    lo, hi = points.min(axis=0), points.max(axis=0)
    return (lo[0] + hi[0]) / 2.0, (lo[1] + hi[1]) / 2.0, float(hi[1] - lo[1])


def anchor_to_subject(
    per_frame: list[np.ndarray],
    target: tuple[float, float, float],
    ref_frame: int = 0,
) -> list[np.ndarray]:
    """Similarity-transform a landmark trajectory onto the subject's face.

    The projected mesh is frame-filling and centred; the actual subject's face
    may be small and high in the frame. Map the reference frame's face box onto
    the subject's box (uniform scale + translation) and apply that same
    transform to every frame — so the mesh lands on the subject at the right
    size while the orbit motion is preserved (it scales with the face, which is
    physically correct: a smaller face sweeps fewer pixels).

    Args:
        per_frame: list of (N, 2) landmark pixel arrays in the draw frame.
        target: subject face box as (cx, cy, height) in the same pixel space.
        ref_frame: which frame to anchor exactly (0 = first).

    Returns a new list; input is not modified.
    """
    ref_cx, ref_cy, ref_h = _bbox(per_frame[ref_frame])
    tgt_cx, tgt_cy, tgt_h = target
    scale = tgt_h / max(ref_h, 1e-6)
    ref_c = np.array([ref_cx, ref_cy], dtype=np.float64)
    tgt_c = np.array([tgt_cx, tgt_cy], dtype=np.float64)
    return [scale * (frame - ref_c) + tgt_c for frame in per_frame]
