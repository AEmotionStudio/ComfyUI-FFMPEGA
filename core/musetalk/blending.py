"""Face blending utilities for compositing lip-synced faces.

Adapted from MuseTalk (MIT License).
Simplified version that uses Gaussian blur blending instead of BiSeNet
face parsing (avoids the extra model dependency).
"""

import cv2
import numpy as np
from PIL import Image


def get_crop_box(box, expand: float = 1.5):
    """Expand a face bounding box around its center.

    Args:
        box: ``(x1, y1, x2, y2)`` face bbox.
        expand: Expansion factor.

    Returns:
        Tuple of (expanded bbox, half-size).
    """
    x, y, x1, y1 = box
    x_c = (x + x1) // 2
    y_c = (y + y1) // 2
    w, h = x1 - x, y1 - y
    s = int(max(w, h) // 2 * expand)
    crop_box = [x_c - s, y_c - s, x_c + s, y_c + s]
    return crop_box, s


def blend_face(
    original_frame: np.ndarray,
    generated_face: np.ndarray,
    face_box,
    upper_boundary_ratio: float = 0.5,
    expand: float = 1.5,
) -> np.ndarray:
    """Blend a generated face region back into the original frame.

    Uses Gaussian-blurred masking for smooth edges, keeping the upper
    half of the face from the original and blending the lower half
    (mouth area) from the generated face.

    Args:
        original_frame: Original BGR frame (will not be modified).
        generated_face: Generated face crop (BGR, same size as bbox).
        face_box: ``(x1, y1, x2, y2)`` face bounding box.
        upper_boundary_ratio: How much of the upper face to preserve.
        expand: Expansion factor for blending region.

    Returns:
        Composited BGR frame.
    """
    frame = original_frame.copy()
    x1, y1, x2, y2 = face_box

    # Resize generated face to match bbox dimensions
    face_h, face_w = y2 - y1, x2 - x1
    if face_h <= 0 or face_w <= 0:
        return frame

    try:
        gen_resized = cv2.resize(
            generated_face.astype(np.uint8),
            (face_w, face_h),
            interpolation=cv2.INTER_LANCZOS4,
        )
    except Exception:
        return frame

    # Create blending mask — only blend lower portion (mouth area)
    mask = np.zeros((face_h, face_w), dtype=np.float32)
    top_boundary = int(face_h * upper_boundary_ratio)
    mask[top_boundary:, :] = 1.0

    # Gaussian blur the mask edges for smooth blending
    blur_size = max(3, int(0.05 * face_w // 2 * 2) + 1)
    mask = cv2.GaussianBlur(mask, (blur_size, blur_size), 0)

    # Expand mask to 3 channels
    mask_3ch = np.stack([mask] * 3, axis=-1)

    # Get the region from the original frame
    orig_region = frame[y1:y2, x1:x2]

    # Ensure dimensions match
    if orig_region.shape != gen_resized.shape:
        return frame

    # Blend: original * (1 - mask) + generated * mask
    blended = (
        orig_region.astype(np.float32) * (1.0 - mask_3ch)
        + gen_resized.astype(np.float32) * mask_3ch
    )
    frame[y1:y2, x1:x2] = blended.astype(np.uint8)

    return frame
