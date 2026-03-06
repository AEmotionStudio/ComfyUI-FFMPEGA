"""Face blending utilities for compositing lip-synced faces.

Adapted from MuseTalk (MIT License).

The reference MuseTalk uses BiSeNet face parsing for precise face masks.
We approximate this with an elliptical mask that closely follows face
contours, with heavy Gaussian feathering for smooth edges.

The blending operates in an expanded crop region (like the reference),
pasting the generated face into a larger context before compositing
back onto the original frame. This prevents hard edges at bbox boundaries.
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
    expand: float = 1.2,
) -> np.ndarray:
    """Blend a generated face region into the original frame.

    Follows the reference MuseTalk pattern:
    1. Expand the bbox to get a larger context region
    2. Create elliptical mask covering the lower face (mouth area)
    3. Gaussian blur the mask for smooth edges
    4. Paste the generated face into the expanded region
    5. Composite back using the blurred mask

    This avoids the hard bbox edges by working in a larger region
    and using PIL's mask-based paste (same as the reference).

    Args:
        original_frame: Original BGR frame (will not be modified).
        generated_face: Generated face crop (BGR, same dims as face_box).
        face_box: ``(x1, y1, x2, y2)`` face bounding box.
        upper_boundary_ratio: How much of upper face to preserve.
        expand: Expansion factor for the compositing region.

    Returns:
        Composited BGR frame.
    """
    x1, y1, x2, y2 = face_box
    face_w, face_h = x2 - x1, y2 - y1
    if face_w <= 0 or face_h <= 0:
        return original_frame.copy()

    # Resize generated face to match face bbox
    try:
        gen_resized = cv2.resize(
            generated_face.astype(np.uint8),
            (face_w, face_h),
            interpolation=cv2.INTER_LANCZOS4,
        )
    except Exception:
        return original_frame.copy()

    # Convert to PIL (BGR → RGB for PIL)
    body = Image.fromarray(original_frame[:, :, ::-1])
    face_pil = Image.fromarray(gen_resized[:, :, ::-1])

    # Compute expanded crop box (larger context region)
    crop_box, s = get_crop_box(face_box, expand)
    x_s, y_s, x_e, y_e = crop_box

    # Crop the expanded region from the original
    # PIL.crop handles out-of-bounds gracefully
    body_w, body_h = body.size
    # Clamp crop_box to image bounds for the crop
    cx_s = max(0, x_s)
    cy_s = max(0, y_s)
    cx_e = min(body_w, x_e)
    cy_e = min(body_h, y_e)
    face_large = body.crop((cx_s, cy_s, cx_e, cy_e))

    ori_w, ori_h = face_large.size
    if ori_w <= 0 or ori_h <= 0:
        return original_frame.copy()

    # Create the mask in the expanded region's coordinate space
    # The mask should only cover the lower portion (mouth area)
    mask_image = Image.new("L", (ori_w, ori_h), 0)

    # Face position within the expanded crop
    fx1 = x1 - cx_s
    fy1 = y1 - cy_s
    fx2 = x2 - cx_s
    fy2 = y2 - cy_s

    # Create elliptical mask just for the face region
    face_mask = np.zeros((face_h, face_w), dtype=np.uint8)

    # Only blend lower portion (mouth area)
    top_boundary = int(face_h * upper_boundary_ratio)

    # Ellipse covering the mouth/chin region
    center_x = face_w // 2
    center_y = (top_boundary + face_h) // 2
    radius_x = int(face_w * 0.45)
    radius_y = int((face_h - top_boundary) * 0.50)

    cv2.ellipse(
        face_mask,
        (center_x, center_y),
        (radius_x, radius_y),
        0, 0, 360,
        color=255,
        thickness=-1,
    )

    # Place the face mask into the expanded mask
    mask_arr = np.array(mask_image)
    # Ensure we don't go out of bounds
    paste_y1 = max(0, fy1)
    paste_x1 = max(0, fx1)
    paste_y2 = min(ori_h, fy2)
    paste_x2 = min(ori_w, fx2)

    src_y1 = paste_y1 - fy1
    src_x1 = paste_x1 - fx1
    src_y2 = src_y1 + (paste_y2 - paste_y1)
    src_x2 = src_x1 + (paste_x2 - paste_x1)

    if src_y2 > src_y1 and src_x2 > src_x1:
        mask_arr[paste_y1:paste_y2, paste_x1:paste_x2] = \
            face_mask[src_y1:src_y2, src_x1:src_x2]

    # Gaussian blur the mask for smooth feathering
    # Reference uses 0.05 * width, but we use wider for better blending
    blur_kernel_size = int(0.1 * ori_w // 2 * 2) + 1
    blur_kernel_size = max(3, blur_kernel_size)
    mask_arr = cv2.GaussianBlur(
        mask_arr, (blur_kernel_size, blur_kernel_size), 0
    )

    mask_image = Image.fromarray(mask_arr)

    # Paste the generated face into the expanded region
    face_large.paste(
        face_pil,
        (fx1, fy1, fx1 + face_w, fy1 + face_h),
    )

    # Composite the expanded region back onto the body using the mask
    body.paste(face_large, (cx_s, cy_s), mask_image)

    # Convert back to BGR numpy
    result = np.array(body)[:, :, ::-1]
    return result
