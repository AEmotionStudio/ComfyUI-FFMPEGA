# coding: utf-8
# Vendored from kijai/ComfyUI-SCAIL-Pose/pose_draw/draw_pose_utils.py
"""High-level DWPose drawing — composes body/hand/face into final canvas."""

import cv2
import numpy as np

from .draw_utils import (
    draw_bodypose,
    draw_bodypose_with_feet,
    draw_bodypose_augmentation,
    draw_handpose,
    draw_handpose_lr,
    draw_facepose,
)


def draw_pose(
    pose, H, W, show_feet=False, show_body=True, show_hand=True,
    show_face=True, show_cheek=False, dw_bgr=False, dw_hand=False,
    aug_body_draw=False, optimized_face=False,
):
    """Draw a complete pose (body + hands + face) on canvas.

    Args:
        pose: Dict with 'bodies', 'hands', 'faces' keys.
        H, W: Canvas dimensions.
        show_feet, show_body, show_hand, show_face: Toggle components.
        show_cheek: Augmented cheek-only mode.
        dw_bgr: Convert body canvas to RGB from BGR.
        dw_hand: Use DWPose-style hand drawing vs L/R coding.
        aug_body_draw: Use augmented body drawing.
        optimized_face: Optimised facial landmark subset.

    Returns:
        (H, W, 3) uint8 canvas.
    """
    final_canvas = np.zeros(shape=(H, W, 3), dtype=np.uint8)
    for i in range(len(pose["bodies"]["candidate"])):
        canvas = np.zeros(shape=(H, W, 3), dtype=np.uint8)
        bodies = pose["bodies"]
        faces = pose["faces"][i:i + 1]
        hands = pose["hands"][2 * i:2 * i + 2]
        candidate = bodies["candidate"][i]
        subset = bodies["subset"][i:i + 1]

        if show_body:
            if len(subset[0]) <= 18 or not show_feet:
                canvas = draw_bodypose(canvas, candidate, subset)
            else:
                canvas = draw_bodypose_with_feet(canvas, candidate, subset)
            if dw_bgr:
                canvas = cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB)

        if show_cheek:
            assert not show_body, "show_cheek and show_body cannot both be True"
            canvas = draw_bodypose_augmentation(
                canvas, candidate, subset,
                drop_aug=True, shift_aug=False, all_cheek_aug=True,
            )

        if show_hand:
            if not dw_hand:
                canvas = draw_handpose_lr(canvas, hands)
            else:
                canvas = draw_handpose(canvas, hands)

        if show_face:
            canvas = draw_facepose(canvas, faces, optimized_face=optimized_face)

        final_canvas = final_canvas + canvas
    return final_canvas


def draw_pose_to_canvas_np(
    poses, pool, H, W, reshape_scale,
    show_feet_flag=False, show_body_flag=True, show_hand_flag=True,
    show_face_flag=True, show_cheek_flag=False, dw_bgr=False,
    dw_hand=False, aug_body_draw=False,
):
    """Draw a list of poses to numpy canvases.

    Args:
        poses: List of pose dicts.
        pool: Reshape pool (unused in our pipeline, pass None).
        H, W: Output dimensions.
        reshape_scale: If > 0, apply random reshapes.

    Returns:
        List of (H, W, 3) uint8 numpy arrays.
    """
    canvas_np_lst = []
    for pose in poses:
        if reshape_scale > 0 and pool is not None:
            pool.apply_random_reshapes(pose)
        canvas = draw_pose(
            pose, H, W,
            show_feet_flag, show_body_flag, show_hand_flag,
            show_face_flag, show_cheek_flag, dw_bgr, dw_hand,
            aug_body_draw, optimized_face=True,
        )
        canvas_np_lst.append(canvas)
    return canvas_np_lst
