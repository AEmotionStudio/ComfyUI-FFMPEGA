"""Face detection and bbox extraction using MediaPipe.

Replaces MuseTalk's mmpose/face-alignment dependency with MediaPipe
(already installed in ComfyUI).  Provides face bounding boxes for
the lip sync pipeline.
"""

import logging
from typing import List, Optional, Tuple

import cv2
import numpy as np

log = logging.getLogger("ffmpega")

# Type alias for bounding box: (x1, y1, x2, y2)
BBox = Tuple[int, int, int, int]

# Sentinel for frames where no face is detected
COORD_PLACEHOLDER = (-1, -1, -1, -1)


def _load_face_detector():
    """Load MediaPipe FaceMesh for landmark-based face detection."""
    import mediapipe as mp

    return mp.solutions.face_mesh.FaceMesh(
        static_image_mode=True,
        max_num_faces=10,
        refine_landmarks=True,
        min_detection_confidence=0.5,
    )


def get_face_bbox(
    image: np.ndarray,
    face_mesh,
    bbox_shift: int = 0,
    extra_margin: int = 10,
    face_index: int = -1,
) -> List[BBox]:
    """Detect faces and return bounding boxes.

    Args:
        image: BGR numpy image.
        face_mesh: MediaPipe FaceMesh instance.
        bbox_shift: Vertical shift for bbox (positive = down).
        extra_margin: Extra pixels below chin.
        face_index: -1 for all faces, 0+ for specific face.

    Returns:
        List of ``(x1, y1, x2, y2)`` bounding boxes.
    """
    h, w = image.shape[:2]
    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    results = face_mesh.process(rgb)

    if not results.multi_face_landmarks:
        return []

    bboxes = []
    for face_landmarks in results.multi_face_landmarks:
        # Get all landmark coordinates
        xs = [int(lm.x * w) for lm in face_landmarks.landmark]
        ys = [int(lm.y * h) for lm in face_landmarks.landmark]

        x1 = max(0, min(xs))
        y1 = max(0, min(ys))
        x2 = min(w, max(xs))
        y2 = min(h, max(ys))

        # Add some padding around the face
        pad_w = int((x2 - x1) * 0.1)
        pad_h = int((y2 - y1) * 0.1)
        x1 = max(0, x1 - pad_w)
        y1 = max(0, y1 - pad_h)
        x2 = min(w, x2 + pad_w)
        y2 = min(h, y2 + pad_h + extra_margin + bbox_shift)

        bboxes.append((x1, y1, x2, y2))

    if face_index >= 0 and face_index < len(bboxes):
        return [bboxes[face_index]]

    return bboxes


def get_landmarks_and_bboxes(
    frames: List[np.ndarray],
    bbox_shift: int = 0,
    extra_margin: int = 10,
    face_index: int = -1,
) -> Tuple[List[List[BBox]], List[np.ndarray]]:
    """Extract face bounding boxes from a list of video frames.

    Args:
        frames: List of BGR numpy images.
        bbox_shift: Vertical shift.
        extra_margin: Extra margin below chin.
        face_index: -1 for all faces, 0+ for specific face.

    Returns:
        Tuple of (list-of-bbox-lists per frame, frames).
        Each inner list has one bbox per detected face.
    """
    face_mesh = _load_face_detector()
    all_bboxes = []

    for frame in frames:
        bboxes = get_face_bbox(
            frame,
            face_mesh,
            bbox_shift=bbox_shift,
            extra_margin=extra_margin,
            face_index=face_index,
        )
        if not bboxes:
            all_bboxes.append([COORD_PLACEHOLDER])
        else:
            all_bboxes.append(bboxes)

    face_mesh.close()
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
        num_frames: How many frames to create (duration determined by audio).

    Returns:
        Tuple of (list of BGR frames, default fps of 25).
    """
    img = cv2.imread(image_path)
    if img is None:
        raise ValueError(f"Could not read image: {image_path}")
    return [img] * num_frames, 25.0
