"""Face detection and bbox extraction for MuseTalk lip sync pipeline.

Uses MediaPipe FaceLandmarker (tasks API) for precise face detection.
Raises an error if no face is detected to fail fast rather than
producing unusable output.
"""

import logging
import os
import threading
import warnings
from pathlib import Path
from typing import List, Optional, Tuple

import cv2
import numpy as np

log = logging.getLogger("ffmpega")

# Type alias for bounding box: (x1, y1, x2, y2)
BBox = Tuple[int, int, int, int]

# Sentinel for frames where no face is detected
COORD_PLACEHOLDER = (-1, -1, -1, -1)

# FaceLandmarker model bundle URL (~4MB)
_FACE_LANDMARKER_URL = (
    "https://storage.googleapis.com/mediapipe-models/"
    "face_landmarker/face_landmarker/float16/latest/face_landmarker.task"
)

# Cached detector (guarded by _landmarker_lock for thread safety)
_landmarker = None
_landmarker_lock = threading.Lock()


# ---------------------------------------------------------------------------
#  FaceLandmarker setup
# ---------------------------------------------------------------------------


def _get_model_path() -> str:
    """Get or download the FaceLandmarker model bundle.

    Stored in ComfyUI/models/musetalk/ alongside other MuseTalk models.
    """
    env_dir = os.environ.get("FFMPEGA_MUSETALK_MODEL_DIR")
    if env_dir and os.path.isdir(env_dir):
        model_dir = Path(env_dir)
    else:
        ext_dir = Path(__file__).resolve().parent.parent.parent
        comfy_root = ext_dir.parent.parent
        comfy_models = comfy_root / "models" / "musetalk"
        if comfy_models.exists() or not ext_dir.name.startswith("ComfyUI"):
            model_dir = comfy_models
        else:
            model_dir = ext_dir / "models" / "musetalk"

    model_dir.mkdir(parents=True, exist_ok=True)
    model_path = model_dir / "face_landmarker.task"

    if model_path.is_file():
        return str(model_path)

    # Gate download behind the same allow_model_downloads check
    # used by all other model download paths in the project.
    try:
        try:
            from ..model_manager import require_downloads_allowed
        except ImportError:
            from core.model_manager import require_downloads_allowed  # type: ignore
        require_downloads_allowed("musetalk")
    except ImportError:
        pass  # model_manager not available (e.g. standalone test) — allow

    log.info("[MuseTalk] Downloading FaceLandmarker model (~4MB)...")
    try:
        import urllib.request
        urllib.request.urlretrieve(_FACE_LANDMARKER_URL, str(model_path))
        log.info("[MuseTalk] FaceLandmarker model saved to %s", model_path)
    except Exception as e:
        raise RuntimeError(
            f"Failed to download FaceLandmarker model: {e}\n"
            f"You can manually download it to: {model_path}"
        ) from e

    return str(model_path)


def _get_landmarker():
    """Get or create FaceLandmarker singleton (thread-safe)."""
    global _landmarker
    if _landmarker is not None:
        return _landmarker

    with _landmarker_lock:
        # Double-check after acquiring lock
        if _landmarker is not None:
            return _landmarker

        import mediapipe as mp

        if not (hasattr(mp, "tasks") and hasattr(mp.tasks, "vision")):
            raise RuntimeError(
                "MediaPipe tasks API not available. "
                "Please install mediapipe >= 0.10.x"
            )

        model_path = _get_model_path()
        base_options = mp.tasks.BaseOptions(model_asset_path=model_path)
        options = mp.tasks.vision.FaceLandmarkerOptions(
            base_options=base_options,
            running_mode=mp.tasks.vision.RunningMode.IMAGE,
            num_faces=10,
            min_face_detection_confidence=0.5,
            min_face_presence_confidence=0.5,
            output_face_blendshapes=False,
            output_facial_transformation_matrixes=False,
        )
        _landmarker = mp.tasks.vision.FaceLandmarker.create_from_options(options)
        return _landmarker


# ---------------------------------------------------------------------------
#  Public API
# ---------------------------------------------------------------------------


def get_face_bbox(
    image: np.ndarray,
    bbox_shift: int = 0,
    extra_margin: int = 10,
    **kwargs,
) -> List[BBox]:
    """Detect faces using FaceLandmarker and return bounding boxes.

    .. versionchanged:: 0.9
        The ``face_mesh`` and ``face_index`` parameters were removed
        when migrating from FaceMesh to FaceLandmarker (Tasks API).
        The detector is now managed internally as a singleton.
        Multi-face filtering is handled by the caller (e.g.,
        ``get_landmarks_and_bboxes``).

    Args:
        image: BGR numpy image.
        bbox_shift: Vertical shift for bbox (positive = down).
        extra_margin: Extra pixels below chin.

    Returns:
        List of ``(x1, y1, x2, y2)`` bounding boxes.
    """
    # Catch removed parameters and emit clear migration message
    _removed = {"face_mesh", "face_index"}
    for key in _removed & set(kwargs):
        warnings.warn(
            f"get_face_bbox() parameter '{key}' was removed in v0.9 — "
            "FaceLandmarker is now managed internally. "
            "Remove the parameter from your call.",
            DeprecationWarning,
            stacklevel=2,
        )
    _unknown = set(kwargs) - _removed
    if _unknown:
        raise TypeError(
            f"get_face_bbox() got unexpected keyword argument(s): {_unknown}"
        )
    import mediapipe as mp

    h, w = image.shape[:2]
    landmarker = _get_landmarker()

    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)

    result = landmarker.detect(mp_image)

    if not result.face_landmarks:
        return []

    bboxes = []
    for face_landmarks in result.face_landmarks:
        xs = [int(lm.x * w) for lm in face_landmarks]
        ys = [int(lm.y * h) for lm in face_landmarks]

        x1 = max(0, min(xs))
        y1 = max(0, min(ys))
        x2 = min(w, max(xs))
        y2 = min(h, max(ys))

        # Add padding
        pad_w = int((x2 - x1) * 0.1)
        pad_h = int((y2 - y1) * 0.1)
        x1 = max(0, x1 - pad_w)
        y1 = max(0, y1 - pad_h)
        x2 = min(w, x2 + pad_w)
        y2 = min(h, y2 + pad_h + extra_margin + bbox_shift)

        bboxes.append((x1, y1, x2, y2))

    return bboxes


def get_landmarks_and_bboxes(
    frames: List[np.ndarray],
    bbox_shift: int = 0,
    extra_margin: int = 10,
    face_index: int = -1,
) -> Tuple[List[List[BBox]], List[np.ndarray]]:
    """Extract face bounding boxes from a list of video frames.

    Uses FaceLandmarker for detection. Raises RuntimeError if no face
    is detected in any frame (fails fast instead of producing output
    without lip sync).

    Args:
        frames: List of BGR numpy images.
        bbox_shift: Vertical shift.
        extra_margin: Extra margin below chin.
        face_index: -1 for all faces, 0+ for specific face.

    Returns:
        Tuple of (list-of-bbox-lists per frame, frames).

    Raises:
        RuntimeError: If no face is detected in any frame.
    """
    all_bboxes = []
    last_good_bboxes = None
    any_detected = False

    for frame in frames:
        bboxes = get_face_bbox(
            frame,
            bbox_shift=bbox_shift,
            extra_margin=extra_margin,
        )

        # Filter to requested face index
        if bboxes and face_index >= 0 and face_index < len(bboxes):
            bboxes = [bboxes[face_index]]

        if bboxes:
            all_bboxes.append(bboxes)
            last_good_bboxes = bboxes
            any_detected = True
        elif last_good_bboxes is not None:
            # Carry forward last good detection for temporal stability
            all_bboxes.append(last_good_bboxes)
        else:
            all_bboxes.append([COORD_PLACEHOLDER])

    if not any_detected:
        raise RuntimeError(
            "[MuseTalk] No face detected in any frame. "
            "Ensure the face is clearly visible and large enough "
            "in the video (FaceLandmarker needs faces to be at least "
            "~100px wide). You can try cropping or zooming in on the face."
        )

    return all_bboxes, frames


def read_frames_from_video(video_path: str) -> Tuple[List[np.ndarray], float]:
    """Read all frames from a video file.

    Args:
        video_path: Path to video file.

    Returns:
        Tuple of (list of BGR frames, fps).
    """
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    frames = []

    while True:
        ret, frame = cap.read()
        if not ret:
            break
        frames.append(frame)

    cap.release()
    return frames, fps


def read_image_as_frames(
    image_path: str,
    num_frames: int = 1,
) -> Tuple[List[np.ndarray], float]:
    """Read a single image and replicate it as frames.

    Args:
        image_path: Path to image file.
        num_frames: How many frames to create.

    Returns:
        Tuple of (list of BGR frames, default fps of 25).
    """
    img = cv2.imread(image_path)
    if img is None:
        raise ValueError(f"Could not read image: {image_path}")
    return [img] * num_frames, 25.0
