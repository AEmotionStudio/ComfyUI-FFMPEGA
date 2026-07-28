# coding: utf-8
"""FaceCam — portrait video camera control via scale-aware conditioning.

CVPR 2026 | https://github.com/weijielyu/FaceCam

Generates portrait videos with camera control (orbit, zoom, tilt) from a
single input video/image using Wan2.2 14B I2V fine-tuned DiT models.

Pipeline:
1. Face-centered crop of input video
2. 3D Gaussian proxy rendering for camera trajectory conditioning
3. MediaPipe face landmark extraction from proxy → camera_cond
4. VAE-encode video_cond + camera_cond
5. Wan 2.2 DiT inference with FaceCam conditioning format:
   - Temporal concat: [noise_latents | video_cond_latents] along dim=2
   - Channel concat: [camera_cond_latents | i2v_y] into model y
   - Model switch at 90% boundary (dit → dit2)
   - Scheduler step only on first F frames

Architecture follows upstream FaceCam (wan_video_facecam.py) conditioning,
adapted for ComfyUI model_patcher + GGUF base workflow.
"""

from __future__ import annotations

import gc
import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

import numpy as np

try:
    from .sanitize import validate_video_path, validate_output_file_path
except ImportError:
    from core.sanitize import validate_video_path, validate_output_file_path  # type: ignore

try:
    from .bin_paths import get_ffmpeg_bin as _get_ffmpeg_bin
except ImportError:
    from core.bin_paths import get_ffmpeg_bin as _get_ffmpeg_bin  # type: ignore

try:
    from .bin_paths import get_ffprobe_bin as _get_ffprobe_bin
except ImportError:
    from core.bin_paths import get_ffprobe_bin as _get_ffprobe_bin  # type: ignore

log = logging.getLogger("ffmpega")


# ---------------------------------------------------------------------------
#  Constants
# ---------------------------------------------------------------------------

DEFAULT_NUM_FRAMES = 81
DEFAULT_RENDER_RESOLUTION = 480
# Upstream inference.py defaults: --height 704 --width 480. FaceCam is a
# *portrait* camera-control model; landscape is off-distribution.
DEFAULT_HEIGHT = 704
DEFAULT_WIDTH = 480
DEFAULT_FPS = 24
DEFAULT_CFG_SCALE = 5.0
DEFAULT_NUM_STEPS = 50
DEFAULT_SIGMA_SHIFT = 5.0
SWITCH_DIT_BOUNDARY = 0.9  # upstream default: switch from dit to dit2 at 90%

MAX_AZIMUTH = 90
MAX_ELEVATION = 60
MIN_FOV = 10
MAX_FOV = 60

_PROXY_BASE_AZIMUTH = 270
_PROXY_BASE_ELEVATION = 0
_PROXY_RADIUS = 2.7

# Upstream random_camera_params: base_azimuth=0, base_elevation=0, base_fov=40,
# max_azimuth=45, max_elevation=30, max_fov=15. With large_pose=True it spans
# max_azimuth in ONE direction from frontal.
#
# Presets follow that: every trajectory starts at the input pose (0) and moves
# outward. A symmetric -45→+45 sweep is double the trained range and puts both
# ends in profile, where MediaPipe cannot resolve a face mesh — which leaves the
# camera conditioning blank for ~30% of frames.
_MAX_AZIMUTH_UPSTREAM = 45
_MAX_ELEVATION_UPSTREAM = 30
_BASE_FOV_UPSTREAM = 40
_MAX_FOV_UPSTREAM = 15

CAMERA_PRESETS = {
    # (start_az, end_az, start_elev, end_elev, start_fov, end_fov)
    "orbit_left": (0, -45, 0, 0, 40, 40),
    "orbit_right": (0, 45, 0, 0, 40, 40),
    "zoom_in": (0, 0, 0, 0, 50, 25),
    "zoom_out": (0, 0, 0, 0, 25, 50),
    "look_up": (0, 0, 0, -30, 40, 40),
    "look_down": (0, 0, 0, 30, 40, 40),
    "dramatic_pan": (0, 45, 0, -25, 45, 30),
    "subtle_drift": (0, 15, 0, -8, 40, 40),
    "dolly_zoom": (0, 25, 0, 0, 55, 25),
    "random": None,
}

# Cached state
_gaussian_model = None


# ---------------------------------------------------------------------------
#  Model directory helpers
# ---------------------------------------------------------------------------

def _get_facecam_dir() -> Path:
    """Get or create FaceCam assets directory (gaussians.ply etc.)."""
    env_dir = os.environ.get("FFMPEGA_FACECAM_MODEL_DIR")
    if env_dir:
        p = Path(env_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p

    for candidate in [
        Path(__file__).resolve().parents[3] / "models" / "facecam",
        Path.home() / "ComfyUI" / "models" / "facecam",
    ]:
        if candidate.parent.is_dir():
            candidate.mkdir(parents=True, exist_ok=True)
            return candidate

    fallback = Path.home() / ".cache" / "facecam"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


def _get_ply_path() -> Path:
    return _get_facecam_dir() / "gaussians.ply"


def _get_landmarker_path() -> Path:
    return _get_facecam_dir() / "face_landmarker_v2_with_blendshapes.task"


# ---------------------------------------------------------------------------
#  3D Gaussian proxy rendering
# ---------------------------------------------------------------------------

def _check_gaussian_rasterizer() -> bool:
    """Check if fast_gauss or diff_gaussian_rasterization is available."""
    try:
        from fast_gauss import GaussianRasterizationSettings, GaussianRasterizer  # noqa
        return True
    except ImportError:
        pass
    try:
        from diff_gaussian_rasterization import GaussianRasterizationSettings, GaussianRasterizer  # noqa
        return True
    except ImportError:
        pass
    return False

def _get_rasterizer():
    """Get the available rasterizer classes."""
    try:
        from fast_gauss import GaussianRasterizationSettings, GaussianRasterizer
        return GaussianRasterizationSettings, GaussianRasterizer, 'fast_gauss'
    except ImportError:
        pass
    try:
        from diff_gaussian_rasterization import GaussianRasterizationSettings, GaussianRasterizer
        return GaussianRasterizationSettings, GaussianRasterizer, 'diff_gaussian_rasterization'
    except ImportError:
        pass
    return None, None, None


def get_proxy_video_cameras(
    num_views: int = 81,
    w: int = 480,
    h: int = 480,
    radius: float = _PROXY_RADIUS,
    base_azimuth: float = _PROXY_BASE_AZIMUTH,
    base_elevation: float = _PROXY_BASE_ELEVATION,
    up_vector: np.ndarray | None = None,
    start_azimuth: float = -40,
    end_azimuth: float = 40,
    start_elevation: float = -20,
    end_elevation: float = 20,
    start_fov: float = 25,
    end_fov: float = 45,
) -> tuple:
    """Generate camera parameters for proxy video rendering."""
    if up_vector is None:
        up_vector = np.array([0, 0, 1])

    azimuths = np.linspace(
        base_azimuth + start_azimuth, base_azimuth + end_azimuth, num_views
    )
    elevations = np.linspace(
        base_elevation + start_elevation, base_elevation + end_elevation, num_views
    )
    hfovs = np.linspace(start_fov, end_fov, num_views)

    fxs = w / (2 * np.tan(np.deg2rad(hfovs) / 2.0))
    fxfycxcy = np.stack(
        [fxs, fxs, np.full(num_views, w / 2.0), np.full(num_views, h / 2.0)],
        axis=1,
    )

    c2ws = []
    for elev, azim in zip(elevations, azimuths):
        elev_r, azim_r = np.deg2rad(elev), np.deg2rad(azim)
        z = radius * np.sin(elev_r)
        base = radius * np.cos(elev_r)
        cam_pos = np.array([base * np.cos(azim_r), base * np.sin(azim_r), z])
        forward = -cam_pos / np.linalg.norm(cam_pos)
        right = np.cross(forward, up_vector)
        right = right / np.linalg.norm(right)
        up = np.cross(right, forward)
        up = up / np.linalg.norm(up)
        c2w = np.eye(4)
        c2w[:3, :4] = np.concatenate(
            (np.stack((right, -up, forward), axis=1), cam_pos[:, None]), axis=1
        )
        c2ws.append(c2w)

    return w, h, num_views, fxfycxcy, np.stack(c2ws, axis=0)


def render_proxy_video(
    camera_params: dict,
    num_frames: int = DEFAULT_NUM_FRAMES,
    render_resolution: int = DEFAULT_RENDER_RESOLUTION,
    ply_path: str | Path | None = None,
) -> list[np.ndarray]:
    """Render proxy video from 3D Gaussian head model (pure PyTorch)."""
    import torch

    if ply_path is None:
        ply_path = _get_ply_path()

    global _gaussian_model
    if _gaussian_model is None:
        _gaussian_model = _load_gaussian_model(ply_path)

    pc = _gaussian_model
    device = pc["xyz"].device

    _, _, _, fxfycxcy, c2ws = get_proxy_video_cameras(
        num_views=num_frames,
        w=render_resolution,
        h=render_resolution,
        start_azimuth=camera_params.get("start_azimuth", -40),
        end_azimuth=camera_params.get("end_azimuth", 40),
        start_elevation=camera_params.get("start_elevation", 0),
        end_elevation=camera_params.get("end_elevation", 0),
        start_fov=camera_params.get("start_fov", 25),
        end_fov=camera_params.get("end_fov", 25),
    )

    fxfycxcy_t = torch.from_numpy(fxfycxcy).float().to(device)
    c2ws_t = torch.from_numpy(c2ws).float().to(device)

    # Try compiled Gaussian rasterizer first (fast_gauss / diff_gaussian_rasterization)
    # for highest quality renders. Fall back to pure PyTorch splatting.
    # Force PyTorch renderer — fast_gauss has precision issues on this system.
    # TODO: Re-enable when proper compiled rasterizer (gsplat) is available.
    RasterSettings, Rasterizer, rast_name = None, None, None

    if RasterSettings is not None:
        log.info("[FaceCam] Gaussian rasterizer: %s", rast_name)
        renderings = torch.zeros(
            num_frames, 3, render_resolution, render_resolution,
            dtype=torch.float32, device=device,
        )
        for j in range(num_frames):
            rendered = _render_gaussian_frame(
                pc, render_resolution, render_resolution,
                c2ws_t[j], fxfycxcy_t[j],
                RasterSettings, Rasterizer,
            )
            # Fix: fast_gauss may return values outside [0,1] or uint8-scaled.
            # Ensure float32 in [0,1] range.
            rendered = rendered.float()
            if rendered.max() > 1.5:  # likely uint8-scaled (0-255)
                rendered = rendered / 255.0
            renderings[j] = rendered.clamp(0.0, 1.0)
    else:
        log.info("[FaceCam] Gaussian rasterizer: PyTorch (splatting fallback)")
        renderings = torch.zeros(
            num_frames, 3, render_resolution, render_resolution,
            dtype=torch.float32, device=device,
        )
        for j in range(num_frames):
            renderings[j] = _render_gaussian_frame_pytorch(
                pc, render_resolution, render_resolution,
                c2ws_t[j], fxfycxcy_t[j],
            )

    renderings = renderings.detach().cpu().numpy()
    renderings = (renderings * 255).clip(0, 255).astype(np.uint8)
    return [renderings[i].transpose(1, 2, 0) for i in range(num_frames)]



def _load_gaussian_model(ply_path: str | Path) -> dict:
    """Load a Gaussian model from a PLY file."""
    import torch

    try:
        from plyfile import PlyData
    except ImportError:
        raise ImportError(
            "FaceCam requires plyfile. Install with: pip install plyfile"
        )

    plydata = PlyData.read(str(ply_path))
    el = plydata.elements[0]

    xyz = np.stack((
        np.asarray(el["x"]),
        np.asarray(el["y"]),
        np.asarray(el["z"]),
    ), axis=1)

    features_dc = np.zeros((xyz.shape[0], 3, 1))
    features_dc[:, 0, 0] = np.asarray(el["f_dc_0"])
    features_dc[:, 1, 0] = np.asarray(el["f_dc_1"])
    features_dc[:, 2, 0] = np.asarray(el["f_dc_2"])

    scale_names = sorted(
        [p.name for p in el.properties if p.name.startswith("scale_")],
        key=lambda x: int(x.split("_")[-1]),
    )
    scales = np.zeros((xyz.shape[0], len(scale_names)))
    for idx, attr_name in enumerate(scale_names):
        scales[:, idx] = np.asarray(el[attr_name])

    rot_names = sorted(
        [p.name for p in el.properties if p.name.startswith("rot")],
        key=lambda x: int(x.split("_")[-1]),
    )
    rots = np.zeros((xyz.shape[0], len(rot_names)))
    for idx, attr_name in enumerate(rot_names):
        rots[:, idx] = np.asarray(el[attr_name])

    opacities = np.asarray(el["opacity"])[..., np.newaxis]

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    return {
        "xyz": torch.from_numpy(xyz.astype(np.float32)).to(device),
        "features_dc": torch.from_numpy(
            features_dc.astype(np.float32)
        ).transpose(1, 2).contiguous().to(device),
        "scaling": torch.from_numpy(scales.astype(np.float32)).contiguous().to(device),
        "rotation": torch.from_numpy(rots.astype(np.float32)).contiguous().to(device),
        "opacity": torch.from_numpy(
            opacities.copy().astype(np.float32)
        ).contiguous().to(device),
    }


def _render_gaussian_frame(pc, height, width, C2W, fxfycxcy,
                           RasterSettings, Rasterizer, bg_color=(1.0, 1.0, 1.0)):
    """Render a single frame using diff_gaussian_rasterization or fast_gauss API."""
    import torch

    device = pc["xyz"].device
    W2C = C2W.inverse()
    znear, zfar = 0.01, 100.0

    fx, fy, cx, cy = fxfycxcy[0], fxfycxcy[1], fxfycxcy[2], fxfycxcy[3]
    tanfovX = width / (2 * fx)
    tanfovY = height / (2 * fy)

    P = torch.zeros(4, 4, device=device)
    P[0, 0] = 2 * fx / width
    P[1, 1] = 2 * fy / height
    P[0, 2] = 2 * (cx / width) - 1
    P[1, 2] = 2 * (cy / height) - 1
    P[2, 2] = -(zfar + znear) / (zfar - znear)
    P[3, 2] = 1.0
    P[2, 3] = -(2 * zfar * znear) / (zfar - znear)

    world_view_transform = W2C.transpose(0, 1)
    projection_matrix = P.transpose(0, 1)
    full_proj = (
        world_view_transform.unsqueeze(0)
        .bmm(projection_matrix.unsqueeze(0))
        .squeeze(0)
    )
    camera_center = C2W[:3, 3]

    xyz = pc["xyz"]
    screenspace_points = torch.empty_like(
        xyz, dtype=xyz.dtype, requires_grad=True, device=device
    )
    bg = torch.tensor(list(bg_color), dtype=torch.float32, device=device)

    raster_kwargs = dict(
        image_height=int(height),
        image_width=int(width),
        tanfovx=float(tanfovX),
        tanfovy=float(tanfovY),
        bg=bg,
        scale_modifier=1.0,
        viewmatrix=world_view_transform,
        projmatrix=full_proj,
        sh_degree=0,
        campos=camera_center,
        prefiltered=False,
        debug=False,
    )

    # diff_gaussian_rasterization has projmatrix_raw, fast_gauss doesn't
    import inspect
    sig = inspect.signature(RasterSettings)
    if "projmatrix_raw" in sig.parameters:
        raster_kwargs["projmatrix_raw"] = projection_matrix

    raster_settings = RasterSettings(**raster_kwargs)

    rasterizer = Rasterizer(raster_settings=raster_settings)
    shs = pc["features_dc"]
    opacity = torch.sigmoid(pc["opacity"])
    scaling = torch.exp(pc["scaling"])
    rotation = torch.nn.functional.normalize(pc["rotation"])

    rendered_image, *_ = rasterizer(
        means3D=xyz,
        means2D=screenspace_points,
        shs=shs,
        colors_precomp=None,
        opacities=opacity,
        scales=scaling,
        rotations=rotation,
        cov3D_precomp=None,
    )
    return rendered_image


def _render_gaussian_frame_pytorch(pc, height, width, C2W, fxfycxcy,
                                    bg_color=(1.0, 1.0, 1.0),
                                    splat_radius: int = 2):
    """Render a single frame using pure PyTorch — no CUDA extensions needed.

    Projects 3D Gaussian centres to 2D, then splatts each as a small disk
    with its SH-DC colour, alpha-blending front-to-back by depth order.

    NOTE: sizing splats from each Gaussian's own ``scaling`` was measured and
    rejected — these Gaussians are near-degenerate (median max/min axis ratio
    ~7000), so an isotropic radius from the major axis smears interior points
    over the face and drops MediaPipe detection sharply (3/8 vs 6/8 poses),
    while the minor axis renders almost nothing (0/8). Varying the fixed radius
    2→8 showed no reliable effect either. The speckle does not appear to bother
    the landmarker; leave this alone without new measurements.
    """
    import torch

    device = pc["xyz"].device
    W2C = C2W.inverse()

    fx, fy, cx, cy = fxfycxcy[0], fxfycxcy[1], fxfycxcy[2], fxfycxcy[3]

    xyz = pc["xyz"]                                    # [N, 3]
    opacity = torch.sigmoid(pc["opacity"]).squeeze(-1)  # [N]
    # SH DC → RGB:  color = C0 * sh_dc + 0.5
    C0 = 0.28209479177387814  # 1 / (2*sqrt(pi))
    colors = (C0 * pc["features_dc"].squeeze(1) + 0.5).clamp(0, 1)  # [N, 3]

    # Transform to camera space
    xyz_h = torch.cat([xyz, torch.ones(xyz.shape[0], 1, device=device)], dim=1)  # [N, 4]
    xyz_cam = (W2C @ xyz_h.T).T[:, :3]  # [N, 3]

    # Keep only points in front of camera (z > 0)
    mask = xyz_cam[:, 2] > 0.01
    xyz_cam = xyz_cam[mask]
    colors_vis = colors[mask]
    opacity_vis = opacity[mask]

    if xyz_cam.shape[0] == 0:
        bg = torch.tensor(bg_color, device=device)
        return bg.view(3, 1, 1).expand(3, height, width)

    # Project to pixel coords
    px = (fx * xyz_cam[:, 0] / xyz_cam[:, 2] + cx).long()  # [M]
    py = (fy * xyz_cam[:, 1] / xyz_cam[:, 2] + cy).long()  # [M]
    depth = xyz_cam[:, 2]  # [M]

    # Sort by depth (front to back)
    sort_idx = torch.argsort(depth)
    px = px[sort_idx]
    py = py[sort_idx]
    colors_vis = colors_vis[sort_idx]
    opacity_vis = opacity_vis[sort_idx]

    # Rasterize via scatter — paint splats front-to-back
    bg = torch.tensor(bg_color, dtype=torch.float32, device=device)
    canvas = bg.view(3, 1, 1).expand(3, height, width).clone()

    # Use a small splat radius for each Gaussian centre
    for dy in range(-splat_radius, splat_radius + 1):
        for dx in range(-splat_radius, splat_radius + 1):
            # Circular mask
            if dx * dx + dy * dy > splat_radius * splat_radius:
                continue

            sx = px + dx
            sy = py + dy

            valid = (sx >= 0) & (sx < width) & (sy >= 0) & (sy < height)
            sx = sx[valid]
            sy = sy[valid]
            c = colors_vis[valid]   # [K, 3]
            a = opacity_vis[valid]  # [K]

            if sx.shape[0] == 0:
                continue

            # Alpha-blend front-to-back (simple painter's algorithm per-splat)
            for ch in range(3):
                canvas[ch, sy, sx] = (
                    canvas[ch, sy, sx] * (1 - a) + c[:, ch] * a
                )

    return canvas.clamp(0, 1)

# ---------------------------------------------------------------------------
#  MediaPipe face conditioning
# ---------------------------------------------------------------------------

def _fit_frame_to_target(
    frame: np.ndarray, target_h: int, target_w: int,
) -> np.ndarray:
    """Fit a frame inside the target and centre it on a white background.

    ``crop_portrait_video`` centres the subject on both axes, so the proxy has
    to be centred too or the two conditioning streams disagree about where the
    face is. The old code padded only bottom/right, which pushed the head into
    the left ~40% of a landscape frame (measured face centre x=0.34 vs 0.55
    once centred).

    Contain rather than cover: scaling a square head render to *fill* a
    landscape frame crops the crown and chin, and measurably costs detections
    (5/9 vs 7/9 poses).
    """
    import cv2

    h, w = frame.shape[:2]
    if (h, w) == (target_h, target_w):
        return frame

    scale = min(target_h / h, target_w / w)
    new_h, new_w = max(1, int(round(h * scale))), max(1, int(round(w * scale)))
    resized = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_AREA)

    out = np.full((target_h, target_w, frame.shape[2]), 255, dtype=frame.dtype)
    top, left = (target_h - new_h) // 2, (target_w - new_w) // 2
    out[top:top + new_h, left:left + new_w] = resized
    return out


def _interpolate_landmark_gaps(
    raw: list[list | None],
) -> list[list | None]:
    """Fill frames where face detection failed by interpolating landmarks.

    MediaPipe loses the face mesh at steep yaw angles, so a camera sweep drops
    landmarks near its extremes. Linearly interpolating each point between the
    nearest detected frames keeps the mesh *moving* through the gap; holding the
    last good frame instead would freeze then jump. Leading and trailing gaps
    are filled with the nearest detection (nothing to interpolate toward).

    Returns a list the same length as ``raw``. Entries stay None only when no
    frame anywhere had a detection.
    """
    from mediapipe.tasks.python.components.containers.landmark import (
        NormalizedLandmark,
    )

    detected = [i for i, lm in enumerate(raw) if lm is not None]
    if not detected:
        return list(raw)

    out: list[list | None] = list(raw)

    def _as_array(landmarks) -> np.ndarray:
        return np.array(
            [[p.x, p.y, p.z] for p in landmarks], dtype=np.float32
        )

    def _as_landmarks(arr: np.ndarray) -> list:
        return [
            NormalizedLandmark(x=float(x), y=float(y), z=float(z))
            for x, y, z in arr
        ]

    first, last = detected[0], detected[-1]

    # Leading / trailing gaps: nearest detection.
    for i in range(first):
        out[i] = _as_landmarks(_as_array(raw[first]))
    for i in range(last + 1, len(raw)):
        out[i] = _as_landmarks(_as_array(raw[last]))

    # Interior gaps: linear interpolation between bracketing detections.
    for a, b in zip(detected, detected[1:]):
        if b - a <= 1:
            continue
        arr_a, arr_b = _as_array(raw[a]), _as_array(raw[b])
        if arr_a.shape != arr_b.shape:
            # Different landmark counts — fall back to holding the earlier one.
            for i in range(a + 1, b):
                out[i] = _as_landmarks(arr_a)
            continue
        for i in range(a + 1, b):
            t = (i - a) / (b - a)
            out[i] = _as_landmarks(arr_a * (1.0 - t) + arr_b * t)

    return out


def _save_facecam_diagnostics(output_path, proxy_frames, cond_frames) -> None:
    """Dump first/mid proxy and conditioning frames next to the output video.

    These are the frames that made the blank-conditioning bug visible, so they
    are worth keeping. The analytic path renders no proxy, so that half is
    simply skipped.
    """
    try:
        import cv2

        diag_dir = Path(output_path).parent
        groups = [("proxy", proxy_frames), ("cond", cond_frames)]
        for name, frames in groups:
            if not frames:
                continue
            for label, frame in (
                ("first", frames[0]), ("mid", frames[len(frames) // 2]),
            ):
                cv2.imwrite(
                    str(diag_dir / f"facecam_diag_{name}_{label}.png"),
                    cv2.cvtColor(frame, cv2.COLOR_RGB2BGR),
                )
        saved = ", ".join(n for n, f in groups if f)
        if saved:
            log.info("[FaceCam] Saved diagnostic frames (%s) → %s", saved, diag_dir)
    except Exception as e:  # noqa: BLE001 - diagnostics must never be fatal
        log.warning("[FaceCam] Could not save diagnostics: %s", e)


def draw_face_mesh(landmarks, shape) -> np.ndarray:
    """Draw one face mesh on a white canvas of ``shape``.

    Shared by the detected and analytic conditioning paths so both produce
    identically styled frames — the model should not be able to tell which
    path generated a given frame.

    ``landmarks`` of None yields a blank frame (no camera signal at all), which
    only happens when every fallback has been exhausted.
    """
    from mediapipe.tasks.python.vision import drawing_utils as mp_drawing
    from mediapipe.tasks.python.vision import face_landmarker as mp_face

    annotated = np.ones(shape, dtype=np.uint8) * 255
    if landmarks is None:
        return annotated

    mp_drawing.draw_landmarks(
        image=annotated,
        landmark_list=landmarks,
        connections=mp_face.FaceLandmarksConnections.FACE_LANDMARKS_TESSELATION,
        landmark_drawing_spec=None,
        connection_drawing_spec=mp_drawing.DrawingSpec(
            color=(224, 224, 224), thickness=1,
        ),
        is_drawing_landmarks=False,
    )
    mp_drawing.draw_landmarks(
        image=annotated,
        landmark_list=landmarks,
        connections=mp_face.FaceLandmarksConnections.FACE_LANDMARKS_CONTOURS,
        landmark_drawing_spec=None,
        connection_drawing_spec=mp_drawing.DrawingSpec(
            color=(0, 0, 0), thickness=1,
        ),
        is_drawing_landmarks=False,
    )
    return annotated


def detect_subject_anchor(
    frames: list[np.ndarray],
    landmarker_path: str | Path | None = None,
    max_samples: int = 32,
) -> dict | None:
    """Find where the subject's face sits in the input video.

    The projected mesh is frame-filling; the real subject may be a small figure
    high in the frame. Sampling several frames (the subject may only face camera
    part of the time), returns the median face box as normalised
    ``{cx, cy, height}`` in [0, 1], or None if no frame yields a face.
    """
    import mediapipe as mp
    from mediapipe.tasks import python
    from mediapipe.tasks.python import vision

    if not frames:
        return None
    if landmarker_path is None:
        landmarker_path = _get_landmarker_path()

    detector = vision.FaceLandmarker.create_from_options(
        vision.FaceLandmarkerOptions(
            base_options=python.BaseOptions(model_asset_path=str(landmarker_path)),
            num_faces=1,
        )
    )

    idx = np.unique(np.linspace(0, len(frames) - 1, max_samples).astype(int))
    boxes = []
    for i in idx:
        frame = np.ascontiguousarray(frames[i])
        h, w = frame.shape[:2]
        result = detector.detect(
            mp.Image(image_format=mp.ImageFormat.SRGB, data=frame)
        )
        if not result.face_landmarks:
            continue
        xs = np.array([p.x for p in result.face_landmarks[0]])
        ys = np.array([p.y for p in result.face_landmarks[0]])
        boxes.append((
            (xs.min() + xs.max()) / 2,
            (ys.min() + ys.max()) / 2,
            ys.max() - ys.min(),
        ))

    if not boxes:
        return None
    boxes = np.array(boxes)
    anchor = {
        "cx": float(np.median(boxes[:, 0])),
        "cy": float(np.median(boxes[:, 1])),
        "height": float(np.median(boxes[:, 2])),
    }
    log.info(
        "[FaceCam] Subject face anchor: centre (%.2f, %.2f), height %.2f of "
        "frame (from %d/%d sampled frames)",
        anchor["cx"], anchor["cy"], anchor["height"], len(boxes), len(idx),
    )
    return anchor


def get_analytic_conditioning(
    camera_params: dict,
    num_frames: int,
    height: int,
    width: int,
    landmarker_path: str | Path | None = None,
    subject_anchor: dict | None = None,
) -> list[np.ndarray]:
    """Build camera conditioning by projecting the canonical face mesh.

    No detector and no proxy render in the loop: the mesh is posed with the same
    camera matrices the proxy would have used, so coverage is total and motion is
    an analytic function of the camera path.

    When ``subject_anchor`` is given, the whole trajectory is scaled and
    translated so it lands on the subject's real face (position and size) rather
    than filling the frame centred — otherwise the DiT renders a large centred
    face and discards the rest of the composition.

    Raises whatever the calibration raises, so the caller can fall back.
    """
    try:
        from . import facecam_mesh
    except ImportError:
        from core import facecam_mesh  # type: ignore

    if landmarker_path is None:
        landmarker_path = _get_landmarker_path()

    square = min(height, width)
    calibration = facecam_mesh.get_calibration(str(landmarker_path))
    per_frame = facecam_mesh.project_landmarks(
        calibration, camera_params, num_frames, square, str(landmarker_path),
    )

    # Place the square projection into the H×W frame, centred.
    offset = np.array([(width - square) / 2.0, (height - square) / 2.0])
    per_frame = [pixels + offset for pixels in per_frame]

    if subject_anchor is not None:
        target = (
            subject_anchor["cx"] * width,
            subject_anchor["cy"] * height,
            subject_anchor["height"] * height,
        )
        per_frame = facecam_mesh.anchor_to_subject(per_frame, target)

    shape = (height, width, 3)
    frames = [
        draw_face_mesh(
            facecam_mesh.to_normalized_landmarks(pixels, width, height), shape
        )
        for pixels in per_frame
    ]
    log.info(
        "[FaceCam] Analytic face mesh: %d/%d frames projected "
        "(calibration %.1f px RMS over %d views, anchor=%s) — no detection gaps",
        len(frames), num_frames, calibration["rms_px"], calibration["views"],
        "subject" if subject_anchor else "centred",
    )
    return frames


def get_mediapipe_conditioning(
    frames: list[np.ndarray],
    landmarker_path: str | Path | None = None,
) -> list[np.ndarray]:
    """Extract MediaPipe face mesh conditioning from video frames."""
    import mediapipe as mp
    from mediapipe.tasks import python
    from mediapipe.tasks.python import vision

    if landmarker_path is None:
        landmarker_path = _get_landmarker_path()

    base_options = python.BaseOptions(model_asset_path=str(landmarker_path))
    options = vision.FaceLandmarkerOptions(
        base_options=base_options,
        output_face_blendshapes=True,
        output_facial_transformation_matrixes=True,
        num_faces=1,
    )
    detector = vision.FaceLandmarker.create_from_options(options)

    # Pass 1: detect. A miss stores None rather than emitting a blank frame —
    # blank conditioning means the model gets no camera signal at all for that
    # frame and free-runs, which reads as jitter and loss of direction.
    raw_landmarks: list[list | None] = []
    for frame in frames:
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame)
        result = detector.detect(mp_image)
        raw_landmarks.append(
            result.face_landmarks[0] if result.face_landmarks else None
        )

    detect_count = sum(lm is not None for lm in raw_landmarks)

    # Pass 2: fill gaps so the trajectory stays continuous.
    filled_landmarks = _interpolate_landmark_gaps(raw_landmarks)

    conditioning_frames = [
        draw_face_mesh(landmarks, frame.shape)
        for frame, landmarks in zip(frames, filled_landmarks)
    ]

    total = len(frames)
    filled_count = sum(lm is not None for lm in filled_landmarks)
    log.info(
        "[FaceCam] MediaPipe face detection: %d/%d detected, %d interpolated, "
        "%d blank (frame shape=%s)",
        detect_count, total, filled_count - detect_count, total - filled_count,
        list(frames[0].shape) if frames else "N/A",
    )
    if total and detect_count == 0:
        log.error(
            "[FaceCam] No face detected in ANY proxy frame — camera "
            "conditioning is entirely blank and the camera preset will have no "
            "effect. Check that gaussians.ply rendered correctly."
        )
    elif total and detect_count < total * 0.5:
        log.warning(
            "[FaceCam] Only %d/%d proxy frames yielded a face mesh; the rest "
            "are interpolated. The camera trajectory is likely too extreme for "
            "landmark detection — try a smaller azimuth/elevation range.",
            detect_count, total,
        )

    return conditioning_frames


# ---------------------------------------------------------------------------
#  Face-centered video cropping
# ---------------------------------------------------------------------------

def crop_portrait_video(
    frames: list[np.ndarray],
    target_height: int = 480,
    target_width: int = 832,
) -> list[np.ndarray]:
    """Crop video frames centered on detected face."""
    import cv2
    import mediapipe as mp
    from mediapipe.tasks import python
    from mediapipe.tasks.python import vision

    if not frames:
        raise ValueError("Empty frames list")

    first = frames[0]
    h, w = first.shape[:2]

    scale_h = target_height / h
    scale_w = target_width / w
    scale = max(scale_h, scale_w)
    new_h, new_w = int(h * scale), int(w * scale)

    left, top = 0, 0
    right, bottom = new_w, new_h

    if new_w > target_width:
        left = (new_w - target_width) // 2
        right = left + target_width
    if new_h > target_height:
        top = (new_h - target_height) // 2
        bottom = top + target_height

    try:
        landmarker_path = _get_landmarker_path()
        if landmarker_path.is_file():
            base_options = python.BaseOptions(
                model_asset_path=str(landmarker_path)
            )
            options = vision.FaceLandmarkerOptions(
                base_options=base_options,
                num_faces=1,
            )
            detector = vision.FaceLandmarker.create_from_options(options)
            resized_first = cv2.resize(first, (new_w, new_h))
            mp_image = mp.Image(
                image_format=mp.ImageFormat.SRGB, data=resized_first
            )
            result = detector.detect(mp_image)

            if result.face_landmarks:
                nose_tip = result.face_landmarks[0][4]
                center_x = int(nose_tip.x * new_w)
                center_y = int(nose_tip.y * new_h)

                if new_w > target_width:
                    left = max(0, center_x - target_width // 2)
                    right = left + target_width
                    if right > new_w:
                        right = new_w
                        left = right - target_width

                if new_h > target_height:
                    top = max(0, center_y - target_height // 2)
                    bottom = top + target_height
                    if bottom > new_h:
                        bottom = new_h
                        top = bottom - target_height
    except Exception as e:
        log.warning("Face detection for crop failed, using center crop: %s", e)

    cropped = []
    for frame in frames:
        resized = cv2.resize(frame, (new_w, new_h))
        cropped.append(resized[top:bottom, left:right])

    return cropped


# ---------------------------------------------------------------------------
#  Video I/O helpers
# ---------------------------------------------------------------------------

def _get_video_fps(video_path: str) -> float:
    try:
        result = subprocess.run(
            [
                _get_ffprobe_bin(), "-v", "quiet",
                "-select_streams", "v:0",
                "-show_entries", "stream=r_frame_rate",
                "-of", "csv=p=0",
                video_path,
            ],
            capture_output=True, text=True, check=True,
        )
        rate = result.stdout.strip()
        if "/" in rate:
            num, den = rate.split("/")
            return float(num) / float(den)
        return float(rate)
    except Exception:
        return 24.0


def load_video_frames(
    video_path: str,
    max_frames: int = DEFAULT_NUM_FRAMES,
    target_height: int | None = None,
    target_width: int | None = None,
) -> tuple[list[np.ndarray], float]:
    """Load video frames as numpy arrays."""
    from PIL import Image

    fps = _get_video_fps(video_path)

    tmpdir = tempfile.mkdtemp(prefix="facecam_frames_")
    try:
        cmd = [
            _get_ffmpeg_bin(), "-i", video_path,
            "-q:v", "2",
            "-frames:v", str(max_frames),
            os.path.join(tmpdir, "%06d.png"),
        ]
        subprocess.run(cmd, capture_output=True, check=True)

        frame_files = sorted(Path(tmpdir).glob("*.png"))
        frames = []
        for f in frame_files[:max_frames]:
            img = Image.open(f).convert("RGB")
            arr = np.array(img)
            if target_height and target_width:
                import cv2
                arr = cv2.resize(arr, (target_width, target_height))
            frames.append(arr)

        if not frames:
            raise RuntimeError(f"No frames extracted from {video_path}")

        return frames, fps
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def save_video_from_frames(
    frames: list[np.ndarray],
    output_path: str,
    fps: float = DEFAULT_FPS,
) -> str:
    """Save numpy frames to a video file via FFmpeg."""
    from PIL import Image

    tmpdir = tempfile.mkdtemp(prefix="facecam_out_")
    try:
        for i, frame in enumerate(frames):
            img = Image.fromarray(frame)
            img.save(os.path.join(tmpdir, f"{i:06d}.png"))

        cmd = [
            _get_ffmpeg_bin(),
            "-y",
            "-framerate", str(fps),
            "-i", os.path.join(tmpdir, "%06d.png"),
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-crf", "18",
            output_path,
        ]
        subprocess.run(cmd, capture_output=True, check=True)
        return output_path
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ---------------------------------------------------------------------------
#  VRAM management
# ---------------------------------------------------------------------------

def _free_vram() -> None:
    try:
        from ._vram_utils import free_for_module
    except ImportError:
        from core._vram_utils import free_for_module  # type: ignore
    free_for_module(exclude="facecam_synthesizer")


def _flush_vram() -> None:
    gc.collect()
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except ImportError:
        pass


# ---------------------------------------------------------------------------
#  Model patching: apply FaceCam weights on top of GGUF base
# ---------------------------------------------------------------------------

def _load_facecam_state_dict(safetensors_path: str) -> dict:
    """Load FaceCam partial checkpoint from a safetensors file.

    FaceCam checkpoints are PARTIAL fine-tunes containing only
    self_attn + patch_embedding layers (402 keys). They are NOT
    full Wan2.2 models and cannot be loaded via ComfyUI's
    load_diffusion_model. We load them as raw safetensors.
    """
    from safetensors.torch import load_file

    log.info("[FaceCam] Loading partial checkpoint: %s", safetensors_path)
    sd = load_file(safetensors_path, device="cpu")
    log.info("[FaceCam] Loaded %d keys from %s", len(sd), Path(safetensors_path).name)
    return sd


def _resolve_inference_dtype(model):
    """Return the dtype the base model's activations arrive in.

    ``get_dtype_inference()`` reports ``manual_cast_dtype`` when set, which is
    what a quantized checkpoint (fp8 mixed-precision, GGUF) actually computes
    in — the stored weight dtype can differ. Falls back for older ComfyUI
    builds that predate the accessor.
    """
    import torch

    dtype = None
    for attr in ("get_dtype_inference", "get_dtype"):
        getter = getattr(model, attr, None)
        if getter is None:
            continue
        try:
            dtype = getter()
        except Exception:  # noqa: BLE001 - diagnostic-only, fall through
            continue
        if dtype is not None:
            break

    # fp8 is a storage dtype; nn.Parameters we inject must be a compute dtype.
    if dtype is None or dtype in (torch.float8_e4m3fn, torch.float8_e5m2):
        return torch.bfloat16
    return dtype


def _apply_facecam_patches(base_patcher, facecam_path: str):
    """Clone the base model and apply FaceCam weights.

    FaceCam checkpoints are partial fine-tunes of Wan2.2-I2V-A14B.
    They contain self-attention + patch_embedding weights (402 keys)
    that replace the corresponding layers in the base model.

    Strategy for GGUF compatibility:
    1. set_attr_param: Directly replace GGMLTensor with nn.Parameter(bf16).
       This ensures the weight is correct AND makes is_quantized() return
       False, so ComfyUI's regular (non-GGUF) backup/restore path handles it.
    2. add_patches("diff"): Register a diff patch (FaceCam - original_dequantized)
       so ComfyUI's model switching can properly restore weights when switching
       between HIGH and LOW models.

    Args:
        base_patcher: ComfyUI ModelPatcher for the base Wan2.2 model.
        facecam_path: Path to FaceCam safetensors file.
    """
    import torch
    import comfy.utils

    cloned = base_patcher.clone()

    # Load FaceCam partial state dict from safetensors
    facecam_sd = _load_facecam_state_dict(facecam_path)
    if not facecam_sd:
        log.warning("[FaceCam] No FaceCam weights loaded — using base model as-is")
        return cloned

    # Match the dtype the base model actually computes in. A quantized base
    # (e.g. fp8 mixed-precision) reports its manual-cast dtype here, which is
    # what activations arrive as — injecting bf16 into an fp16 model makes
    # every replaced linear fail with "self and mat2 must have the same dtype".
    target_dtype = _resolve_inference_dtype(cloned.model)

    prefix = "diffusion_model."
    replaced = 0
    replaced_keys: set[str] = set()

    for key, facecam_tensor in facecam_sd.items():
        full_key = key if key.startswith(prefix) else prefix + key

        try:
            current_weight = comfy.utils.get_attr(cloned.model, full_key)
        except (AttributeError, KeyError):
            log.debug("[FaceCam] Key '%s' not found in model — skipping", full_key)
            continue

        # Replace GGMLTensor with a regular nn.Parameter in the base model's
        # compute dtype. This makes is_quantized() return False for this weight,
        # so ComfyUI uses the regular backup/restore path on model switch.
        new_param = torch.nn.Parameter(
            facecam_tensor.to(device=current_weight.device, dtype=target_dtype),
            requires_grad=False,
        )
        comfy.utils.set_attr_param(cloned.model, full_key, new_param)
        replaced += 1
        replaced_keys.add(full_key)

    log.info(
        "[FaceCam] Applied %d direct weight replacements as %s "
        "(%d total keys, patcher: %s)",
        replaced, target_dtype, len(facecam_sd), type(cloned).__name__,
    )
    if replaced < len(facecam_sd):
        log.warning("[FaceCam] %d keys did NOT match model structure!", len(facecam_sd) - replaced)

    # A speed/distillation LoRA loaded ahead of this node registers patches that
    # ComfyUI applies at cast time — on top of the weights just written here.
    # Those deltas were fitted to base Wan attention, not FaceCam's camera-tuned
    # attention, so they dilute exactly the layers that carry camera control.
    try:
        patch_keys = set(getattr(cloned, "patches", {}) or {})
        overlap = patch_keys & replaced_keys
        if overlap:
            log.warning(
                "[FaceCam] ⚠️ %d LoRA/patch entries target FaceCam-replaced "
                "layers (of %d patches, %d FaceCam keys). Those deltas were "
                "trained for the base model and will be summed onto FaceCam's "
                "camera attention, weakening camera control. Bypass speed "
                "LoRAs for best results.",
                len(overlap), len(patch_keys), len(replaced_keys),
            )
    except Exception as e:  # noqa: BLE001 - diagnostic only, never fatal
        log.debug("[FaceCam] Could not inspect patches for overlap: %s", e)

    # Force new patches_uuid so ComfyUI knows weights changed
    import uuid
    cloned.patches_uuid = uuid.uuid4()

    # Store metadata for verification
    pe_key_local = "patch_embedding.weight"
    if pe_key_local in facecam_sd:
        cloned._facecam_pe_sum = facecam_sd[pe_key_local].float().sum().item()
        log.info("[FaceCam] Expected patch_embedding checksum: %.4f", cloned._facecam_pe_sum)
    cloned._facecam_path = facecam_path

    return cloned


# ---------------------------------------------------------------------------
#  Main pipeline
# ---------------------------------------------------------------------------

def generate_facecam_video(
    input_frames: list,
    wan_high_patcher,
    facecam_high_path: str,
    wan_low_patcher=None,
    facecam_low_path: str | None = None,
    vae=None,
    clip=None,
    camera_params: dict = None,
    output_path: str | None = None,
    *,
    num_frames: int = DEFAULT_NUM_FRAMES,
    height: int = DEFAULT_HEIGHT,
    width: int = DEFAULT_WIDTH,
    cfg_scale: float = DEFAULT_CFG_SCALE,
    num_steps: int = DEFAULT_NUM_STEPS,
    sigma_shift: float = DEFAULT_SIGMA_SHIFT,
    sampler_name: str = "euler",
    scheduler: str = "simple",
    seed: int | None = None,
    fps: float = DEFAULT_FPS,
    prompt: str = "A portrait video with camera motion.",
    negative_prompt: str = "",
    high_model_ratio: float = 0.2,
    blockswap_blocks: int = 0,
    mesh_source: str = "auto",
    progress_callback=None,
) -> tuple[str, dict | None]:
    """Run the full FaceCam pipeline.

    1. Crop input frames (face-centered)
    2. Render 3D Gaussian proxy video from camera trajectory
    3. Extract MediaPipe face mesh conditioning from proxy
    4. Run Wan 2.2 DiT with FaceCam conditioning (two-phase: HIGH → LOW)
    5. Save output video

    Args:
        input_frames: List of numpy frames (H, W, 3) uint8.
        wan_high_patcher: Base Wan2.2 high-noise ModelPatcher.
        facecam_high_path: Path to FaceCam high-noise safetensors.
        wan_low_patcher: Optional base Wan2.2 low-noise ModelPatcher.
        facecam_low_path: Optional path to FaceCam low-noise safetensors.
        vae: ComfyUI VAE.
        clip: ComfyUI CLIP (T5-XXL).
        camera_params: Camera trajectory dict.
        output_path: Output video path.
        high_model_ratio: Fraction of steps using HIGH model (0.0-1.0).
        blockswap_blocks: DiT blocks (of 40) to keep off-GPU during sampling.
            0 disables. Raise on cards that can't hold the 14B model plus
            FaceCam's doubled temporal dimension.
        mesh_source: How to build camera conditioning. "auto" projects the
            canonical face mesh analytically and falls back to detection if
            calibration fails; "analytic" and "detected" force either path.
    """
    import torch

    if output_path is None:
        output_path = str(Path.home() / "facecam_output.mp4")
    validate_output_file_path(output_path)

    # FaceCam is a portrait camera-control model: upstream inference.py
    # defaults to --height 704 --width 480. Landscape is off-distribution.
    if width > height:
        log.warning(
            "[FaceCam] ⚠️ Landscape resolution %dx%d — FaceCam is trained on "
            "portrait video (upstream default %dx%d, w×h). Camera control is "
            "weaker off-distribution; consider swapping width/height.",
            width, height, DEFAULT_WIDTH, DEFAULT_HEIGHT,
        )

    # CFG is what applies the camera conditioning: at scale 1.0 the negative
    # branch is skipped entirely and the trajectory is followed only as far as
    # the unguided model happens to.
    if cfg_scale <= 1.0:
        log.warning(
            "[FaceCam] ⚠️ cfg_scale=%.1f disables classifier-free guidance, "
            "which is the mechanism that applies camera conditioning. Camera "
            "motion will be weak. Upstream uses %.1f.",
            cfg_scale, DEFAULT_CFG_SCALE,
        )
    if num_steps < 10:
        log.warning(
            "[FaceCam] ⚠️ steps=%d is low for FaceCam (upstream uses %d); the "
            "camera trajectory may not resolve. If using a distillation LoRA "
            "for speed, see the LoRA overlap warning below.",
            num_steps, DEFAULT_NUM_STEPS,
        )

    log.info(
        "[FaceCam] Starting generation → %s (frames=%d, %dx%d)",
        output_path, num_frames, width, height,
    )

    # Step 1: Face-centered crop
    if progress_callback:
        progress_callback(0, 5)
    log.info("[FaceCam] Step 1/5: Cropping input frames...")
    cropped_frames = crop_portrait_video(
        input_frames, target_height=height, target_width=width,
    )

    # ── Steps 2-3: camera conditioning ────────────────────────────────
    # The analytic path poses the canonical face mesh with the same camera
    # matrices the proxy render would have used, so it needs no per-frame render
    # and has no detection gaps. Step 2 collapses to a one-off cached
    # calibration when it is in use.
    if progress_callback:
        progress_callback(1, 5)

    square = min(height, width)
    camera_cond_frames = None

    if mesh_source in ("auto", "analytic"):
        log.info("[FaceCam] Step 2/5: Projecting analytic face mesh...")
        try:
            # Anchor the mesh to the subject's real face so the orbit happens
            # around them at their size, instead of a frame-filling centred head
            # that makes the DiT zoom to a portrait and drop the composition.
            subject_anchor = detect_subject_anchor(cropped_frames)
            if subject_anchor is None:
                log.warning(
                    "[FaceCam] No face found in the input to anchor to — the "
                    "mesh will be frame-centred and the result may zoom to a "
                    "portrait. Ensure the subject's face is visible."
                )
            camera_cond_frames = get_analytic_conditioning(
                camera_params, num_frames, height, width,
                subject_anchor=subject_anchor,
            )
        except Exception as e:  # noqa: BLE001 - fall back to detection
            if mesh_source == "analytic":
                raise
            log.warning(
                "[FaceCam] Analytic face mesh unavailable (%s) — falling back "
                "to proxy render + detection.", e,
            )

    proxy_frames = None
    if camera_cond_frames is None:
        # Detection path: render the proxy along the trajectory, then read the
        # pose back out of the pixels with MediaPipe.
        log.info("[FaceCam] Step 2/5: Rendering 3D proxy video...")

        if _check_gaussian_rasterizer() and _get_ply_path().is_file():
            proxy_frames = render_proxy_video(
                camera_params=camera_params,
                num_frames=num_frames,
                render_resolution=square,
            )
        else:
            log.warning(
                "[FaceCam] No Gaussian rasterizer or gaussians.ply not found. "
                "Using input frames for conditioning (results may degrade). "
                "Install: pip install plyfile && pip install gsplat"
            )

        # Free Gaussian model from GPU — no longer needed after proxy rendering
        global _gaussian_model
        if _gaussian_model is not None:
            _gaussian_model = None
            _flush_vram()
            log.info("[FaceCam] Freed Gaussian model from GPU")

        log.info("[FaceCam] Step 3/5: Extracting face mesh conditioning...")

        if proxy_frames is not None:
            # Centre the square proxy render in the target frame.
            # crop_portrait_video centres the subject, so the proxy must match.
            proxy_frames = [
                _fit_frame_to_target(frame, height, width)
                for frame in proxy_frames
            ]
            camera_cond_frames = get_mediapipe_conditioning(proxy_frames)
        else:
            camera_cond_frames = get_mediapipe_conditioning(cropped_frames)

    if progress_callback:
        progress_callback(2, 5)
    _save_facecam_diagnostics(output_path, proxy_frames, camera_cond_frames)

    # Step 4: Run DiT with FaceCam conditioning
    if progress_callback:
        progress_callback(3, 5)
    log.info("[FaceCam] Step 4/5: Running Wan 2.2 DiT inference...")

    _free_vram()
    _flush_vram()

    output_frames, latent_output = _run_facecam_dit(
        input_frames=cropped_frames,
        proxy_frames=proxy_frames,
        wan_high_patcher=wan_high_patcher,
        facecam_high_path=facecam_high_path,
        wan_low_patcher=wan_low_patcher,
        facecam_low_path=facecam_low_path,
        vae=vae,
        clip=clip,
        camera_cond_frames=camera_cond_frames,
        num_frames=num_frames,
        height=height,
        width=width,
        cfg_scale=cfg_scale,
        num_steps=num_steps,
        sigma_shift=sigma_shift,
        sampler_name=sampler_name,
        scheduler=scheduler,
        seed=seed,
        prompt=prompt,
        negative_prompt=negative_prompt,
        high_model_ratio=high_model_ratio,
        blockswap_blocks=blockswap_blocks,
        progress_callback=progress_callback,
    )

    # Step 5: Save output video
    if progress_callback:
        progress_callback(4, 5)
    log.info("[FaceCam] Step 5/5: Saving output video...")
    save_video_from_frames(output_frames, output_path, fps=fps)

    if progress_callback:
        progress_callback(5, 5)
    log.info("[FaceCam] Generation complete: %s", output_path)
    return output_path, latent_output


# ---------------------------------------------------------------------------
#  DiT Inference — upstream FaceCam conditioning format
# ---------------------------------------------------------------------------

def _run_facecam_dit(
    input_frames: list[np.ndarray],
    wan_high_patcher,
    facecam_high_path: str,
    proxy_frames: list | None = None,
    wan_low_patcher=None,
    facecam_low_path: str | None = None,
    vae=None,
    clip=None,
    camera_cond_frames: list[np.ndarray] = None,
    num_frames: int = 81,
    height: int = 480,
    width: int = 832,
    cfg_scale: float = DEFAULT_CFG_SCALE,
    num_steps: int = DEFAULT_NUM_STEPS,
    sigma_shift: float = DEFAULT_SIGMA_SHIFT,
    sampler_name: str = "euler",
    scheduler: str = "simple",
    seed: int | None = None,
    prompt: str = "A portrait video with camera motion.",
    negative_prompt: str = "",
    high_model_ratio: float = 0.2,
    blockswap_blocks: int = 0,
    progress_callback=None,
) -> tuple[list[np.ndarray], dict | None]:
    """Run FaceCam DiT inference with two-phase model switching.

    Upstream pipeline (wan_video_facecam.py) conditioning:
    1. video_cond (input video) → VAE encode → video_cond_latents
    2. camera_cond (mediapipe mesh) → VAE encode → camera_cond_latents
    3. During denoising each step:
       a. Temporal concat: latents = [noise_latents | video_cond_latents] (dim=2)
       b. Channel concat via y: y = [camera_cond_latents | i2v_y] (dim=1), doubled
       c. Model sees: x = [latents, y] channel-concatenated (in model_fn)
       d. Scheduler step on first F frames only
    4. Model switch from HIGH→LOW at high_model_ratio boundary

    We implement this via:
    - A shared model_function_wrapper for conditioning
    - Two sequential comfy.sample.sample() calls (HIGH then LOW)
    """
    import torch
    import comfy.model_management as mm
    import comfy.sample
    import comfy.samplers
    import comfy.sd
    import comfy.utils

    device = mm.get_torch_device()
    dtype = mm.unet_dtype()

    if seed is None:
        seed = torch.randint(0, 2**32, (1,)).item()

    # ── Merge FaceCam weights onto base ───────────────────────────────
    log.info("[FaceCam] Applying FaceCam patches to base model (high)...")
    merged_high = _apply_facecam_patches(wan_high_patcher, facecam_high_path)

    if wan_low_patcher is not None and facecam_low_path is not None:
        log.info("[FaceCam] Applying FaceCam patches to base model (low)...")
        merged_low = _apply_facecam_patches(wan_low_patcher, facecam_low_path)
    else:
        merged_low = merged_high

    # ── Build text conditioning ───────────────────────────────────────
    if clip is not None:
        try:
            tokens_pos = clip.tokenize(prompt)
            positive_cond = clip.encode_from_tokens_scheduled(tokens_pos)
            tokens_neg = clip.tokenize(negative_prompt)
            negative_cond = clip.encode_from_tokens_scheduled(tokens_neg)
            log.info("[FaceCam] Text conditioning from CLIP encoder")
        except Exception as e:
            log.warning("[FaceCam] CLIP encoding failed: %s — using zeros", e)
            positive_cond, negative_cond = _zero_text_cond(device, dtype)
    else:
        log.info("[FaceCam] No CLIP — using zero text conditioning")
        positive_cond, negative_cond = _zero_text_cond(device, dtype)

    # ── VAE-encode input video → video_cond_latents ───────────────────
    # Use ORIGINAL input video for temporal conditioning (upstream design).
    # Camera trajectory comes through y-channel conditioning (camera_cond).
    log.info("[FaceCam] VAE-encoding input video for temporal conditioning...")
    video_cond_frames = [
        torch.from_numpy(f).float() / 255.0 for f in input_frames
    ]
    video_cond_bhwc = torch.stack(video_cond_frames, dim=0)[:, :height, :width, :]
    video_cond_latent = vae.encode(video_cond_bhwc)
    if video_cond_latent.ndim == 4:
        video_cond_latent = video_cond_latent.permute(1, 0, 2, 3).unsqueeze(0)
    # Normalize with process_latent_in — required for ComfyUI's WAN pipeline.
    video_cond_latent = merged_high.model.process_latent_in(video_cond_latent)
    video_cond_latent = video_cond_latent.to(dtype=dtype, device="cpu")
    log.info("[FaceCam] video_cond_latent (normalized): %s min=%.4f max=%.4f mean=%.4f",
             list(video_cond_latent.shape), video_cond_latent.min().item(),
             video_cond_latent.max().item(), video_cond_latent.mean().item())
    _flush_vram()

    # ── VAE-encode camera conditioning → camera_cond_latents ──────────
    # Use MediaPipe face mesh conditioning from proxy renders (upstream design).
    # The face mesh captures camera trajectory as seen through face geometry.
    log.info("[FaceCam] VAE-encoding face mesh conditioning...")
    cam_frames = [
        torch.from_numpy(f).float() / 255.0 for f in camera_cond_frames
    ]
    cam_bhwc = torch.stack(cam_frames, dim=0)[:, :height, :width, :]
    camera_cond_latent = vae.encode(cam_bhwc)
    if camera_cond_latent.ndim == 4:
        camera_cond_latent = camera_cond_latent.permute(1, 0, 2, 3).unsqueeze(0)
    # Normalize with process_latent_in to match ComfyUI's expected input scale
    camera_cond_latent = merged_high.model.process_latent_in(camera_cond_latent)
    camera_cond_latent = camera_cond_latent.to(dtype=dtype, device="cpu")  # keep on CPU
    log.info("[FaceCam] camera_cond_latent (normalized): %s min=%.4f max=%.4f mean=%.4f",
             list(camera_cond_latent.shape), camera_cond_latent.min().item(),
             camera_cond_latent.max().item(), camera_cond_latent.mean().item())
    _flush_vram()

    # ── Compute latent dimensions ─────────────────────────────────────
    latent_f = (num_frames - 1) // 4 + 1
    latent_h = height // 8
    latent_w = width // 8

    # Match video_cond_latent dimensions
    vcl = video_cond_latent
    if vcl.shape[2] != latent_f:
        indices = torch.linspace(0, vcl.shape[2] - 1, latent_f, dtype=torch.long)
        vcl = vcl[:, :, indices]
    if vcl.shape[3] != latent_h or vcl.shape[4] != latent_w:
        from torch.nn import functional as TF
        b, ch, f, h, w = vcl.shape
        flat = vcl.reshape(b * ch * f, 1, h, w)
        flat = TF.interpolate(flat, size=(latent_h, latent_w), mode="bilinear", align_corners=False)
        vcl = flat.reshape(b, ch, f, latent_h, latent_w)
    video_cond_latent = vcl.to(dtype=dtype)

    # Match camera_cond_latent dimensions
    ccl = camera_cond_latent
    if ccl.shape[2] != latent_f:
        indices = torch.linspace(0, ccl.shape[2] - 1, latent_f, dtype=torch.long)
        ccl = ccl[:, :, indices]
    if ccl.shape[3] != latent_h or ccl.shape[4] != latent_w:
        from torch.nn import functional as TF
        b, ch, f, h, w = ccl.shape
        flat = ccl.reshape(b * ch * f, 1, h, w)
        flat = TF.interpolate(flat, size=(latent_h, latent_w), mode="bilinear", align_corners=False)
        ccl = flat.reshape(b, ch, f, latent_h, latent_w)
    camera_cond_latent = ccl.to(dtype=dtype)

    # ── Build I2V y and combine with camera_cond ──────────────────────
    # Get the model's in_dim to compute y_dim
    dit_model = merged_high.model
    if hasattr(dit_model, "diffusion_model"):
        dit = dit_model.diffusion_model
    else:
        dit = dit_model

    # Mask: zeros (no masking for FaceCam — full generation)
    mask = torch.zeros(1, 4, latent_f, latent_h, latent_w, dtype=dtype, device="cpu")

    # FaceCam y-channel layout (verified by experiment):
    #   y[0:16]  = camera conditioning latent (face mesh VAE output)
    #   y[16:20] = mask (zeros — no masking for FaceCam)
    in_dim = getattr(dit, "in_dim", None)
    if in_dim is not None:
        y_dim_total = in_dim - 16
        log.info(
            "[FaceCam] in_dim=%d, y_total=%d, camera_cond=%d, mask=%d",
            in_dim, y_dim_total, camera_cond_latent.shape[1], mask.shape[1],
        )
    else:
        log.warning("[FaceCam] Could not determine dit.in_dim — using default y structure")

    # Build y: [camera_cond(16ch), mask(4ch)] = 20 channels
    y = torch.cat([camera_cond_latent, mask], dim=1)  # all on CPU
    del camera_cond_latent, mask
    y_doubled = y.repeat(1, 1, 2, 1, 1)
    log.info("[FaceCam] y: %s → doubled: %s", list(y.shape), list(y_doubled.shape))
    del y

    # ── Aggressive VRAM cleanup before DiT sampling ───────────────────
    # Free all ComfyUI-managed models (VAE, CLIP) so DiT gets max VRAM
    try:
        mm.free_memory(mm.get_free_memory(device), device)
    except Exception:
        pass
    mm.soft_empty_cache()
    _flush_vram()
    free_gb = torch.cuda.mem_get_info()[0] / (1024**3) if torch.cuda.is_available() else 0
    log.info("[VRAM] GPU free after cleanup: %.2f GiB", free_gb)

    # ── Wrapper: temporal extension + y injection ─────────────────────
    _call_count = [0]

    def facecam_wrapper(model_function, kwargs):
        """Wrapper that implements FaceCam's upstream conditioning format."""
        import torch
        input_x = kwargs["input"]     # [B, 16, F', H', W']
        timestep = kwargs["timestep"]
        c = kwargs.get("c", {})
        B = input_x.shape[0]

        # Remove any native c_concat — we handle conditioning ourselves
        c.pop("c_concat", None)

        # 1. Temporal concat: [noise_latents | video_cond_latents] along dim=2
        vcl_dev = video_cond_latent.to(device=input_x.device, dtype=input_x.dtype)
        if vcl_dev.shape[0] != B:
            vcl_dev = vcl_dev.expand(B, -1, -1, -1, -1)
        x_extended = torch.cat([input_x, vcl_dev], dim=2)  # [B, 16, 2*F', H', W']

        # 2. Inject y as c_concat
        # We set y via c_concat to match ComfyUI's WAN21.concat_cond behavior
        y_dev = y_doubled.to(device=input_x.device, dtype=input_x.dtype)
        if y_dev.shape[0] != B:
            y_dev = y_dev.expand(B, -1, -1, -1, -1)
        # Match temporal length
        if y_dev.shape[2] != x_extended.shape[2]:
            y_dev = y_dev[:, :, :x_extended.shape[2]]
        c["c_concat"] = y_dev

        _call_count[0] += 1
        if _call_count[0] == 1:
            log.info(
                "[FaceCam] wrapper: x=%s → x_ext=%s, y=%s",
                list(input_x.shape), list(x_extended.shape), list(y_dev.shape),
            )

        # 3. Run model with temporally extended input
        orig_f = input_x.shape[2]
        del input_x  # free ref — sampler still holds its copy
        output = model_function(x_extended, timestep, **c)
        del x_extended, vcl_dev  # free GPU intermediates

        # 4. Truncate output to first F' frames (scheduler only steps these)
        output = output[:, :, :orig_f]

        return output

    merged_high.set_model_unet_function_wrapper(facecam_wrapper)
    if merged_low is not merged_high:
        merged_low.set_model_unet_function_wrapper(facecam_wrapper)

    # ── Diagnostic: verify FaceCam weights were injected ─────────────────
    try:
        pe_w = merged_high.model.diffusion_model.patch_embedding.weight
        log.info("[FaceCam] patch_embedding.weight: shape=%s dtype=%s sum=%.4f",
                 list(pe_w.shape), pe_w.dtype, pe_w.float().sum().item())
    except Exception as e:
        log.info("[FaceCam] Could not read patch_embedding weight: %s", e)

    # ── Create noise latent ───────────────────────────────────────────
    noise = torch.randn(
        1, 16, latent_f, latent_h, latent_w,
        device="cpu", dtype=torch.float32,
    )
    latent_image = torch.zeros_like(noise)

    # ── Override memory estimation for FaceCam's extra tensors ─────────
    # FaceCam's wrapper creates extra GPU tensors each denoising step:
    #   x_extended  = [B, 16, 2F, H, W]  (temporal concat)
    #   vcl_dev     = [B, 16, F, H, W]   (video_cond on GPU)
    #   y_dev       = [B, 20, 2F, H, W]  (conditioning)
    # The transformer also sees 2× the temporal dimension internally, and that
    # dominates: with 2×F frames the patchified sequence is
    # (2F)·(H/2)·(W/2) tokens, each a WAN_DIM-wide hidden state, and a block
    # keeps several such tensors live at once. At 832×480/81f that is ~640 MiB
    # per activation — a fixed reserve can't track it, so scale with the job.
    _orig_mem_required = merged_high.model.memory_required

    _WAN22_HIDDEN_DIM = 5120
    _LIVE_ACTIVATIONS = 6  # concurrent hidden-state tensors per block
    _tokens = (2 * latent_f) * (latent_h // 2) * (latent_w // 2)
    # Size against the compute dtype, not the weight storage dtype — an fp8
    # checkpoint still carries 16-bit activations.
    _act_dtype = _resolve_inference_dtype(merged_high.model)
    _act_bytes = _tokens * _WAN22_HIDDEN_DIM * torch.finfo(_act_dtype).bits // 8
    # Never budget below the previous fixed reserve.
    _FACECAM_EXTRA_VRAM = max(
        int(1.5 * 1024 * 1024 * 1024),
        int(_act_bytes * _LIVE_ACTIVATIONS),
    )
    log.info(
        "[FaceCam] VRAM reserve: %.2f GiB (%d tokens × %d dim × %d live)",
        _FACECAM_EXTRA_VRAM / 1024**3, _tokens, _WAN22_HIDDEN_DIM,
        _LIVE_ACTIVATIONS,
    )

    def _facecam_memory_required(input_shape, cond_shapes={}):
        """Add extra VRAM budget for FaceCam's temporal doubling."""
        base = _orig_mem_required(input_shape, cond_shapes=cond_shapes)
        return base + _FACECAM_EXTRA_VRAM

    merged_high.model.memory_required = _facecam_memory_required
    if merged_low is not merged_high:
        merged_low.model.memory_required = _facecam_memory_required

    # Optional block swap — the reserve above only tells ComfyUI to keep VRAM
    # free; on a card too small for a 14B DiT plus the doubled temporal dim,
    # weights have to actually leave the GPU as well.
    if blockswap_blocks > 0:
        try:
            from .vram_utils import register_blockswap
        except ImportError:
            from core.vram_utils import register_blockswap  # type: ignore
        register_blockswap(
            merged_high, blockswap_blocks,
            key="facecam_blockswap_high", label="FaceCam HIGH",
        )
        if merged_low is not merged_high:
            register_blockswap(
                merged_low, blockswap_blocks,
                key="facecam_blockswap_low", label="FaceCam LOW",
            )

    # ── Two-phase denoising (HIGH → LOW) ───────────────────────────────
    # Upstream FaceCam uses two DiT models:
    #   - HIGH (high-noise): handles camera trajectory structure
    #   - LOW (low-noise): handles detail refinement
    # high_model_ratio controls how many steps use HIGH before switching to LOW.

    # Apply sigma_shift to model sampling (Wan2.2 uses DiscreteFlow)
    try:
        merged_high.model.model_sampling.set_parameters(shift=sigma_shift)
        if merged_low is not merged_high:
            merged_low.model.model_sampling.set_parameters(shift=sigma_shift)
        log.info("[FaceCam] Applied sigma_shift=%.1f to model_sampling", sigma_shift)
    except Exception as e:
        log.warning("[FaceCam] Could not set sigma_shift: %s", e)

    # Compute switch step from ratio
    switch_step = max(1, round(num_steps * high_model_ratio))
    if merged_low is merged_high or high_model_ratio >= 1.0:
        # No LOW model or ratio=1.0 → single-pass with HIGH
        switch_step = num_steps

    log.info(
        "[FaceCam] Sampling: %d total steps, HIGH 0→%d, LOW %d→%d, "
        "ratio=%.2f, sampler=%s scheduler=%s sigma_shift=%.1f",
        num_steps, switch_step,
        switch_step, num_steps if switch_step < num_steps else switch_step,
        high_model_ratio, sampler_name, scheduler, sigma_shift,
    )

    # ── Phase 1: HIGH model (steps 0 → switch_step) ──────────────────
    is_single_pass = (switch_step >= num_steps)
    phase = "HIGH"
    try:
        latent = comfy.sample.sample(
            model=merged_high,
            noise=noise,
            steps=num_steps,
            cfg=cfg_scale,
            sampler_name=sampler_name,
            scheduler=scheduler,
            positive=positive_cond,
            negative=negative_cond,
            latent_image=latent_image,
            denoise=1.0,
            disable_noise=True,
            start_step=0,
            last_step=switch_step,
            force_full_denoise=is_single_pass,  # fully denoise only if no LOW pass
            noise_mask=None,
            callback=lambda step, x0, x, total: (
                progress_callback(3 + step / num_steps, 5)
                if progress_callback else None
            ),
            disable_pbar=True,
            seed=seed,
        )
        log.info("[FaceCam] Phase 1 (HIGH) complete: steps 0→%d", switch_step)

        # ── Phase 2: LOW model (switch_step → num_steps) ─────────────────
        if switch_step < num_steps and merged_low is not merged_high:
            phase = "LOW"
            # Set the same wrapper on LOW model
            merged_low.set_model_unet_function_wrapper(facecam_wrapper)
            _call_count[0] = 0

            latent = comfy.sample.sample(
                model=merged_low,
                noise=torch.zeros_like(noise),  # zero noise — Phase 1 output is already at the right noise level
                steps=num_steps,
                cfg=cfg_scale,
                sampler_name=sampler_name,
                scheduler=scheduler,
                positive=positive_cond,
                negative=negative_cond,
                latent_image=latent,  # continue from HIGH output
                denoise=1.0,
                disable_noise=True,
                start_step=switch_step,
                last_step=num_steps,
                force_full_denoise=True,
                noise_mask=None,
                callback=lambda step, x0, x, total: (
                    progress_callback(3 + step / num_steps, 5)
                    if progress_callback else None
                ),
                disable_pbar=True,
                seed=seed,
            )
            log.info("[FaceCam] Phase 2 (LOW) complete: steps %d→%d", switch_step, num_steps)
    except Exception as e:
        # Re-raise: swallowing this returned the untouched input frames, and
        # the caller then saved them and logged "Generation complete" — a
        # failed run was indistinguishable from a successful one.
        log.error("[FaceCam] %s sampling failed: %s", phase, e, exc_info=True)
        _flush_vram()
        raise
    finally:
        # Restore original memory estimation
        merged_high.model.memory_required = _orig_mem_required
        if merged_low is not merged_high:
            merged_low.model.memory_required = _orig_mem_required

    mm.soft_empty_cache()

    # Build LATENT output dict
    latent_output = {"samples": latent}

    # ── Decode latents ────────────────────────────────────────────────
    log.info("[FaceCam] Decoding latents to video frames...")
    output_frames = _decode_latent_to_frames(latent, num_frames, height, width, vae=vae)

    _flush_vram()
    return output_frames, latent_output


# ---------------------------------------------------------------------------
#  Helpers
# ---------------------------------------------------------------------------

def _zero_text_cond(device, dtype):
    """Return zero text conditioning in ComfyUI format."""
    import torch
    cond = torch.zeros(1, 512, 4096, device=device, dtype=dtype)
    positive = [[cond, {}]]
    negative = [[cond.clone(), {}]]
    return positive, negative


def _decode_latent_to_frames(
    latent, num_frames, height, width, vae=None,
) -> list[np.ndarray]:
    """Decode latent tensor to video frames."""
    import torch

    if vae is not None:
        try:
            log.info("[FaceCam] Decoding with VAE...")
            pixel_samples = vae.decode(latent)

            if pixel_samples.ndim == 5:
                pixel_samples = pixel_samples[0]
            elif pixel_samples.ndim == 4:
                pass

            frames = []
            for f_idx in range(pixel_samples.shape[0]):
                frame = pixel_samples[f_idx]
                frame = frame.clamp(0, 1) * 255
                frame = frame.byte().cpu().numpy()
                frames.append(frame)

            while len(frames) < num_frames:
                frames.append(frames[-1])
            frames = frames[:num_frames]

            log.info("[FaceCam] VAE decode complete: %d frames", len(frames))
            return frames

        except Exception as e:
            log.warning("[FaceCam] VAE decode failed: %s — using fallback", e)

    # Fallback: naive latent → RGB
    log.info("[FaceCam] Using latent→RGB approximation (no VAE)")
    lat = latent[0]

    frames = []
    for f_idx in range(lat.shape[1]):
        frame_lat = lat[:, f_idx]
        rgb = frame_lat[:3]
        rgb = (rgb - rgb.min()) / (rgb.max() - rgb.min() + 1e-8)
        rgb = rgb.unsqueeze(0)
        rgb = torch.nn.functional.interpolate(
            rgb, size=(height, width), mode="bilinear", align_corners=False,
        )
        rgb = rgb.squeeze(0)
        frame = (rgb.clamp(0, 1) * 255).byte().cpu().numpy()
        frame = frame.transpose(1, 2, 0)
        frames.append(frame)

    while len(frames) < num_frames:
        frames.append(frames[-1])
    frames = frames[:num_frames]

    return frames


# ---------------------------------------------------------------------------
#  Cleanup
# ---------------------------------------------------------------------------

def cleanup() -> None:
    """Free GPU memory and clear cached state."""
    global _gaussian_model

    if _gaussian_model is not None:
        _gaussian_model = None

    gc.collect()
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except ImportError:
        pass
    try:
        import comfy.model_management as mm
        mm.soft_empty_cache()
    except (ImportError, AttributeError):
        pass
    log.info("FaceCam synthesizer unloaded")


def offload_to_cpu() -> None:
    """Offload cached Gaussian model to CPU without destroying it."""
    global _gaussian_model
    if _gaussian_model is not None:
        import torch
        for key in _gaussian_model:
            if isinstance(_gaussian_model[key], torch.Tensor):
                _gaussian_model[key] = _gaussian_model[key].cpu()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        log.info("FaceCam Gaussian model offloaded to CPU")


# ---------------------------------------------------------------------------
#  Camera preset resolution
# ---------------------------------------------------------------------------

def resolve_camera_params(
    preset: str | None = None,
    start_azimuth: float = 0,
    end_azimuth: float = 0,
    start_elevation: float = 0,
    end_elevation: float = 0,
    start_fov: float = 25,
    end_fov: float = 25,
) -> dict:
    """Build camera params dict from a preset name or manual values."""
    if preset and preset in CAMERA_PRESETS:
        values = CAMERA_PRESETS[preset]
        if values is None:
            import random
            # Upstream large_pose=True: pick a direction, then span up to
            # max_azimuth from frontal — not two independent endpoints, which
            # would sweep up to 2× the trained range through profile views.
            direction = random.choice((-1, 1))
            values = (
                0,
                direction * random.uniform(0, _MAX_AZIMUTH_UPSTREAM),
                0,
                random.uniform(-_MAX_ELEVATION_UPSTREAM, _MAX_ELEVATION_UPSTREAM),
                _BASE_FOV_UPSTREAM,
                _BASE_FOV_UPSTREAM + random.uniform(
                    -_MAX_FOV_UPSTREAM, _MAX_FOV_UPSTREAM
                ),
            )
        return {
            "start_azimuth": values[0],
            "end_azimuth": values[1],
            "start_elevation": values[2],
            "end_elevation": values[3],
            "start_fov": values[4],
            "end_fov": values[5],
        }

    params = {
        "start_azimuth": max(-MAX_AZIMUTH, min(MAX_AZIMUTH, start_azimuth)),
        "end_azimuth": max(-MAX_AZIMUTH, min(MAX_AZIMUTH, end_azimuth)),
        "start_elevation": max(-MAX_ELEVATION, min(MAX_ELEVATION, start_elevation)),
        "end_elevation": max(-MAX_ELEVATION, min(MAX_ELEVATION, end_elevation)),
        "start_fov": max(MIN_FOV, min(MAX_FOV, start_fov)),
        "end_fov": max(MIN_FOV, min(MAX_FOV, end_fov)),
    }

    # Analytic conditioning stays valid at any angle, so the tracker no longer
    # caps how far the camera can travel — but the DiT was only trained to
    # max_azimuth=45 / max_elevation=30, and it is now the binding constraint.
    az = max(abs(params["start_azimuth"]), abs(params["end_azimuth"]))
    el = max(abs(params["start_elevation"]), abs(params["end_elevation"]))
    if az > _MAX_AZIMUTH_UPSTREAM or el > _MAX_ELEVATION_UPSTREAM:
        log.warning(
            "[FaceCam] ⚠️ Camera range (azimuth %.0f°, elevation %.0f°) exceeds "
            "what FaceCam was trained on (%d°/%d°). Conditioning is still valid, "
            "but the model is extrapolating and the face may distort.",
            az, el, _MAX_AZIMUTH_UPSTREAM, _MAX_ELEVATION_UPSTREAM,
        )

    return params
