# coding: utf-8
# Vendored from kijai/ComfyUI-SCAIL-Pose/NLFPoseExtract/nlf_render.py
"""NLF pose → cylinder specs → rendered skeleton images.

Orchestrates the conversion of NLF 3D joint predictions into
cylinder specifications and renders them via the PyTorch renderer.
Optionally overlays 2D DWPose face/hand keypoints.
"""

import copy
import logging

import numpy as np
import torch

from .render_torch import render_whole as render_whole_torch
from .draw_pose_utils import draw_pose_to_canvas_np


def p3d_single_p2d(points, intrinsic_matrix):
    """Project a single 3D point to 2D using camera intrinsics."""
    X, Y, Z = points[0], points[1], points[2]
    u = (intrinsic_matrix[0, 0] * X / Z) + intrinsic_matrix[0, 2]
    v = (intrinsic_matrix[1, 1] * Y / Z) + intrinsic_matrix[1, 2]
    u_np = u.cpu().numpy() if isinstance(u, torch.Tensor) else float(u)
    v_np = v.cpu().numpy() if isinstance(v, torch.Tensor) else float(v)
    return np.array([u_np, v_np])


def process_data_to_COCO_format(joints):
    """Convert 24-joint NLF format to 18-joint COCO format.

    Args:
        joints: (24, 2) or (24, 3) array.

    Returns:
        (18, D) array in COCO keypoint order.
    """
    if joints.ndim != 2:
        raise ValueError(f"Expected shape (24,2) or (24,3), got {joints.shape}")

    dim = joints.shape[1]
    mapping = {
        15: 0,   # head
        12: 1,   # neck
        17: 2,   # left shoulder
        16: 5,   # right shoulder
        19: 3,   # left elbow
        18: 6,   # right elbow
        21: 4,   # left hand
        20: 7,   # right hand
        2: 8,    # left pelvis
        1: 11,   # right pelvis
        5: 9,    # left knee
        4: 12,   # right knee
        8: 10,   # left feet
        7: 13,   # right feet
    }

    new_joints = np.zeros((18, dim), dtype=joints.dtype)
    for src, dst in mapping.items():
        new_joints[dst] = joints[src]
    return new_joints


def intrinsic_matrix_from_field_of_view(imshape, fov_degrees=55):
    """Compute camera intrinsic matrix from field of view.

    Args:
        imshape: (H, W) image dimensions.
        fov_degrees: Field of view in degrees (default 55, NLF standard).

    Returns:
        (3, 3) intrinsic matrix.
    """
    imshape = np.array(imshape)
    fov_radians = fov_degrees * np.pi / 180
    larger_side = np.max(imshape)
    focal_length = larger_side / (np.tan(fov_radians / 2) * 2)
    return np.array([
        [focal_length, 0, imshape[1] / 2],
        [0, focal_length, imshape[0] / 2],
        [0, 0, 1],
    ])


def scale_around_center(points, center, dim, scale=1.0):
    return (points[:, dim] - center[dim]) * scale + center[dim]


def shift_dwpose_according_to_nlf(
    smpl_poses, aligned_poses, ori_intrinstics, modified_intrinstics,
    height, width, swap_hands=True, scale_hands=True, scale_x=1.0, scale_y=1.0
):
    """Shift 2D DWPose keypoints to align with 3D NLF projections."""
    for i in range(len(smpl_poses)):
        persons_joints_list = smpl_poses[i]
        poses_list = aligned_poses[i]
        if len(persons_joints_list) != len(poses_list["bodies"]["candidate"]):
            logging.warning(
                "Frame %d: NLF has %d persons but DW has %d. Skipping shift.",
                i, len(persons_joints_list), len(poses_list["bodies"]["candidate"]),
            )
            continue

        for person_idx, person_joints in enumerate(persons_joints_list):
            face = poses_list["faces"][person_idx]
            right_hand = poses_list["hands"][2 * person_idx]
            left_hand = poses_list["hands"][2 * person_idx + 1]
            candidate = poses_list["bodies"]["candidate"][person_idx]

            face_shift = (
                p3d_single_p2d(person_joints[15], modified_intrinstics)
                - p3d_single_p2d(person_joints[15], ori_intrinstics)
            ) if person_joints[15, 2] > 0.01 else np.array([0.0, 0.0])

            rhand_shift = (
                p3d_single_p2d(person_joints[20], modified_intrinstics)
                - p3d_single_p2d(person_joints[20], ori_intrinstics)
            ) if person_joints[20, 2] > 0.01 else np.array([0.0, 0.0])

            lhand_shift = (
                p3d_single_p2d(person_joints[21], modified_intrinstics)
                - p3d_single_p2d(person_joints[21], ori_intrinstics)
            ) if person_joints[21, 2] > 0.01 else np.array([0.0, 0.0])

            if swap_hands:
                lhand_shift, rhand_shift = rhand_shift, lhand_shift

            face[:, 0] += face_shift[0] / width
            face[:, 1] += face_shift[1] / height
            right_hand[:, 0] += rhand_shift[0] / width
            right_hand[:, 1] += rhand_shift[1] / height
            left_hand[:, 0] += lhand_shift[0] / width
            left_hand[:, 1] += lhand_shift[1] / height
            candidate[:, 0] += face_shift[0] / width
            candidate[:, 1] += face_shift[1] / height

            scales = [scale_x, scale_y]
            if scale_hands:
                for dim in [0, 1]:
                    right_hand[:, dim] = scale_around_center(
                        right_hand, right_hand[0, :], dim=dim, scale=scales[dim],
                    )
                    left_hand[:, dim] = scale_around_center(
                        left_hand, left_hand[0, :], dim=dim, scale=scales[dim],
                    )


def get_single_pose_cylinder_specs(args, include_missing=False):
    """Generate cylinder specs for a single frame's poses."""
    idx, pose, focal, princpt, height, width, colors, limb_seq, draw_seq = args
    cylinder_specs = []

    for joints3d in pose:
        if joints3d is None:
            if include_missing:
                for line_idx in draw_seq:
                    cylinder_specs.append((np.zeros(3), np.zeros(3), colors[line_idx]))
            continue
        if isinstance(joints3d, torch.Tensor):
            if torch.sum(torch.abs(joints3d)) < 0.01:
                if include_missing:
                    for line_idx in draw_seq:
                        cylinder_specs.append((np.zeros(3), np.zeros(3), colors[line_idx]))
                continue
            joints3d = joints3d.cpu().numpy()
        elif isinstance(joints3d, np.ndarray):
            if np.sum(np.abs(joints3d)) < 0.01:
                if include_missing:
                    for line_idx in draw_seq:
                        cylinder_specs.append((np.zeros(3), np.zeros(3), colors[line_idx]))
                continue
        else:
            if include_missing:
                for line_idx in draw_seq:
                    cylinder_specs.append((np.zeros(3), np.zeros(3), colors[line_idx]))
            continue

        joints3d = process_data_to_COCO_format(joints3d)
        for line_idx in draw_seq:
            line = limb_seq[line_idx]
            start, end = line[0], line[1]
            if np.sum(joints3d[start]) == 0 or np.sum(joints3d[end]) == 0:
                if include_missing:
                    cylinder_specs.append((np.zeros(3), np.zeros(3), colors[line_idx]))
                continue
            else:
                cylinder_specs.append((joints3d[start], joints3d[end], colors[line_idx]))
    return cylinder_specs


# ── Color palettes ─────────────────────────────────────────────────

_BASE_COLORS = {
    "Red": [255, 0, 0], "Orange": [255, 85, 0], "Golden Orange": [255, 170, 0],
    "Yellow": [255, 240, 0], "Yellow-Green": [180, 255, 0],
    "Bright Green": [0, 255, 0], "Light Green-Blue": [0, 255, 85],
    "Aqua": [0, 255, 170], "Cyan": [0, 255, 255], "Sky Blue": [0, 170, 255],
    "Medium Blue": [0, 85, 255], "Pure Blue": [0, 0, 255],
    "Purple-Blue": [85, 0, 255], "Medium Purple": [170, 0, 255],
    "Grey": [150, 150, 150], "Pink-Magenta": [255, 0, 170],
    "Dark Pink": [255, 0, 85], "Violet": [100, 0, 255], "Dark Violet": [50, 0, 255],
}

_ORDERED_COLORS = [
    _BASE_COLORS["Red"], _BASE_COLORS["Cyan"],
    _BASE_COLORS["Orange"], _BASE_COLORS["Golden Orange"],
    _BASE_COLORS["Sky Blue"], _BASE_COLORS["Medium Blue"],
    _BASE_COLORS["Yellow-Green"], _BASE_COLORS["Bright Green"],
    _BASE_COLORS["Light Green-Blue"], _BASE_COLORS["Pure Blue"],
    _BASE_COLORS["Purple-Blue"], _BASE_COLORS["Medium Purple"],
    _BASE_COLORS["Grey"], _BASE_COLORS["Pink-Magenta"],
    _BASE_COLORS["Dark Violet"], _BASE_COLORS["Pink-Magenta"],
    _BASE_COLORS["Dark Violet"],
]

_LIMB_SEQ = [
    [1, 2], [1, 5], [2, 3], [3, 4], [5, 6], [6, 7],
    [1, 8], [8, 9], [9, 10], [1, 11], [11, 12], [12, 13],
    [1, 0], [0, 14], [14, 16], [0, 15], [15, 17],
]

_DRAW_SEQ = [0, 2, 3, 1, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16]


# ── Rendering functions ───────────────────────────────────────────


def render_nlf_as_images(
    smpl_poses, dw_poses, height, width, video_length,
    intrinsic_matrix=None, draw_2d=True, draw_face=True, draw_hands=True,
    render_backend="torch",
):
    """Render NLF 3D poses as skeleton images.

    Args:
        smpl_poses: List of per-frame pose lists (each pose is [24, 3] tensor/array).
        dw_poses: Optional DWPose dict for 2D face/hand overlay.
        height, width: Output image dimensions.
        video_length: Number of frames.
        intrinsic_matrix: Camera intrinsics (computed from FoV if None).
        draw_2d: Whether to overlay 2D DWPose.
        draw_face, draw_hands: Toggle face/hand drawing.
        render_backend: Always "torch" (taichi not supported).

    Returns:
        List of (H, W, 4) uint8 RGBA numpy arrays.
    """
    colors = [[c / 300 + 0.15 for c in rgb] + [0.8] for rgb in _ORDERED_COLORS]

    if dw_poses is not None:
        aligned_poses = copy.deepcopy(dw_poses)

    if intrinsic_matrix is None:
        intrinsic_matrix = intrinsic_matrix_from_field_of_view((height, width))
    focal_x = intrinsic_matrix[0, 0]
    focal_y = intrinsic_matrix[1, 1]
    princpt = (intrinsic_matrix[0, 2], intrinsic_matrix[1, 2])

    cylinder_specs_list = []
    for i in range(video_length):
        specs = get_single_pose_cylinder_specs(
            (i, smpl_poses[i], None, None, None, None, colors, _LIMB_SEQ, _DRAW_SEQ),
        )
        cylinder_specs_list.append(specs)

    frames_np_rgba = render_whole_torch(
        cylinder_specs_list, H=height, W=width,
        fx=focal_x, fy=focal_y, cx=princpt[0], cy=princpt[1],
    )

    if dw_poses is not None and draw_2d:
        canvas_2d = draw_pose_to_canvas_np(
            aligned_poses, pool=None, H=height, W=width, reshape_scale=0,
            show_feet_flag=False, show_body_flag=False, show_cheek_flag=True,
            dw_hand=True, show_face_flag=draw_face, show_hand_flag=draw_hands,
        )
        for i in range(len(frames_np_rgba)):
            frame_img = frames_np_rgba[i]
            canvas_img = canvas_2d[i]
            mask = canvas_img != 0
            frame_img[:, :, :3][mask] = canvas_img[mask]
            frames_np_rgba[i] = frame_img

    return frames_np_rgba


def align_persons_across_frames(smpl_poses, max_persons=2):
    """Align person indices across frames using pelvis proximity."""
    video_length = len(smpl_poses)
    aligned = [[None for _ in range(max_persons)] for _ in range(video_length)]

    for i in range(min(max_persons, len(smpl_poses[0]))):
        aligned[0][i] = smpl_poses[0][i]

    for t in range(1, video_length):
        prev_persons = [p for p in aligned[t - 1] if p is not None]
        curr_persons = smpl_poses[t]
        assigned = set()
        for i, prev_pose in enumerate(prev_persons):
            if prev_pose is None:
                continue
            prev_pelvis = prev_pose[0]
            min_dist = float("inf")
            min_j = -1
            for j, curr_pose in enumerate(curr_persons):
                if j in assigned:
                    continue
                curr_pelvis = curr_pose[0]
                dist = np.linalg.norm(
                    prev_pelvis.cpu().numpy() - curr_pelvis.cpu().numpy()
                )
                if dist < min_dist:
                    min_dist = dist
                    min_j = j
            if min_j >= 0:
                aligned[t][i] = curr_persons[min_j]
                assigned.add(min_j)
        for i in range(max_persons):
            if aligned[t][i] is None:
                aligned[t][i] = torch.zeros((24, 3), dtype=torch.float32)
    return aligned


def render_multi_nlf_as_images(
    smpl_poses, dw_poses, height, width, video_length,
    intrinsic_matrix=None, draw_2d=True, draw_face=True, draw_hands=True,
    render_backend="torch",
):
    """Render multi-person NLF poses with person-specific colors."""
    # Build per-person color palettes
    max_persons = max(len(frame) for frame in smpl_poses)
    aligned = align_persons_across_frames(smpl_poses, max_persons=max_persons)

    # Simplified: use main palette for all persons
    colors = [[c / 300 + 0.15 for c in rgb] + [0.8] for rgb in _ORDERED_COLORS[:13]]

    limb_seq = _LIMB_SEQ[:13]
    draw_seq = [0, 2, 3, 1, 4, 5, 6, 7, 8, 9, 10, 11, 12]

    video_length = len(smpl_poses)
    cylinder_specs_list = []
    for i in range(video_length):
        cylinder_specs = []
        for person_idx in range(max_persons):
            person_specs = get_single_pose_cylinder_specs(
                (i, [aligned[i][person_idx]], None, None, None, None,
                 colors, limb_seq, draw_seq),
            )
            cylinder_specs.extend(person_specs)
        cylinder_specs_list.append(cylinder_specs)

    if intrinsic_matrix is None:
        intrinsic_matrix = intrinsic_matrix_from_field_of_view((height, width))
    focal_x = intrinsic_matrix[0, 0]
    focal_y = intrinsic_matrix[1, 1]
    princpt = (intrinsic_matrix[0, 2], intrinsic_matrix[1, 2])

    frames_np_rgba = render_whole_torch(
        cylinder_specs_list, H=height, W=width,
        fx=focal_x, fy=focal_y, cx=princpt[0], cy=princpt[1],
    )

    if dw_poses is not None and draw_2d:
        aligned_dw = copy.deepcopy(dw_poses)
        canvas_2d = draw_pose_to_canvas_np(
            aligned_dw, pool=None, H=height, W=width, reshape_scale=0,
            show_feet_flag=False, show_body_flag=False, show_cheek_flag=True,
            dw_hand=True, show_face_flag=draw_face, show_hand_flag=draw_hands,
        )
        for i in range(len(frames_np_rgba)):
            frame_img = frames_np_rgba[i]
            canvas_img = canvas_2d[i]
            mask = canvas_img != 0
            frame_img[:, :, :3][mask] = canvas_img[mask]
            frames_np_rgba[i] = frame_img

    return frames_np_rgba
