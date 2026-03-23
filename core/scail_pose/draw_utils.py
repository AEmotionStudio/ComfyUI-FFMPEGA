# coding: utf-8
# Vendored from kijai/ComfyUI-SCAIL-Pose/pose_draw/draw_utils.py
# Originally from https://github.com/IDEA-Research/DWPose
"""OpenCV-based drawing utilities for DWPose skeleton visualisation.

Functions to draw body limbs, hand skeletons, and facial landmarks
on canvas images using OpenCV primitives.
"""

import math
import random

import cv2
import numpy as np

eps = 0.01


def hsv_to_rgb(hsv):
    """Convert HSV to RGB (0-255)."""
    hsv = np.asarray(hsv, dtype=np.float32).reshape(-1, 3)
    h, s, v = hsv[:, 0], hsv[:, 1], hsv[:, 2]
    i = (h * 6.0).astype(int) % 6
    f = (h * 6.0) - i.astype(float)
    p = v * (1.0 - s)
    q = v * (1.0 - s * f)
    t = v * (1.0 - s * (1.0 - f))

    rgb = np.zeros_like(hsv)
    rgb[i == 0] = np.stack([v[i == 0], t[i == 0], p[i == 0]], axis=1)
    rgb[i == 1] = np.stack([q[i == 1], v[i == 1], p[i == 1]], axis=1)
    rgb[i == 2] = np.stack([p[i == 2], v[i == 2], t[i == 2]], axis=1)
    rgb[i == 3] = np.stack([p[i == 3], q[i == 3], v[i == 3]], axis=1)
    rgb[i == 4] = np.stack([t[i == 4], p[i == 4], v[i == 4]], axis=1)
    rgb[i == 5] = np.stack([v[i == 5], p[i == 5], q[i == 5]], axis=1)

    gray_mask = s == 0
    rgb[gray_mask] = np.stack([v[gray_mask]] * 3, axis=1)
    return (rgb.reshape(-1, 3) * 255)[0]


# ── Standard colour palette ───────────────────────────────────────

_BODY_COLORS = [
    [255, 0, 0], [255, 85, 0], [255, 170, 0], [255, 255, 0],
    [170, 255, 0], [85, 255, 0], [0, 255, 0], [0, 255, 85],
    [0, 255, 170], [0, 255, 255], [0, 170, 255], [0, 85, 255],
    [0, 0, 255], [85, 0, 255], [170, 0, 255], [255, 0, 255],
    [255, 0, 170], [255, 0, 85],
]

_LIMB_SEQ = [
    [2, 3], [2, 6], [3, 4], [4, 5], [6, 7], [7, 8],
    [2, 9], [9, 10], [10, 11], [2, 12], [12, 13], [13, 14],
    [2, 1], [1, 15], [15, 17], [1, 16], [16, 18], [3, 17], [6, 18],
]

_HAND_EDGES = [
    [0, 1], [1, 2], [2, 3], [3, 4],
    [0, 5], [5, 6], [6, 7], [7, 8],
    [0, 9], [9, 10], [10, 11], [11, 12],
    [0, 13], [13, 14], [14, 15], [15, 16],
    [0, 17], [17, 18], [18, 19], [19, 20],
]


# ── Body pose ─────────────────────────────────────────────────────


def draw_bodypose(canvas, candidate, subset):
    """Draw body limbs and keypoint dots on canvas."""
    H, W, C = canvas.shape
    candidate = np.array(candidate)
    subset = np.array(subset)
    stickwidth = 4

    for i in range(17):
        for n in range(len(subset)):
            index = subset[n][np.array(_LIMB_SEQ[i]) - 1]
            if -1 in index:
                continue
            Y = candidate[index.astype(int), 0] * float(W)
            X = candidate[index.astype(int), 1] * float(H)
            mX = np.mean(X)
            mY = np.mean(Y)
            length = ((X[0] - X[1]) ** 2 + (Y[0] - Y[1]) ** 2) ** 0.5
            angle = math.degrees(math.atan2(X[0] - X[1], Y[0] - Y[1]))
            polygon = cv2.ellipse2Poly(
                (int(mY), int(mX)), (int(length / 2), stickwidth), int(angle), 0, 360, 1
            )
            cv2.fillConvexPoly(canvas, polygon, _BODY_COLORS[i])

    canvas = (canvas * 0.6).astype(np.uint8)

    for i in range(18):
        for n in range(len(subset)):
            index = int(subset[n][i])
            if index == -1:
                continue
            x, y = candidate[index][0:2]
            x = int(x * W)
            y = int(y * H)
            cv2.circle(canvas, (int(x), int(y)), 4, _BODY_COLORS[i], thickness=-1)
    return canvas


def draw_bodypose_with_feet(canvas, candidate, subset):
    """Draw body limbs including foot connections."""
    H, W, C = canvas.shape
    candidate = np.array(candidate)
    subset = np.array(subset)
    stickwidth = 4

    foot_limb_seq = [
        [14, 19], [14, 20], [14, 21], [11, 22], [11, 23], [11, 24],
    ]
    colors_feet = [
        [100, 0, 215], [80, 0, 235], [60, 0, 255],
        [0, 235, 150], [0, 215, 170], [0, 195, 190],
    ]

    for i in range(17):
        for n in range(len(subset)):
            index = subset[n][np.array(_LIMB_SEQ[i]) - 1]
            if -1 in index:
                continue
            Y = candidate[index.astype(int), 0] * float(W)
            X = candidate[index.astype(int), 1] * float(H)
            mX = np.mean(X)
            mY = np.mean(Y)
            length = ((X[0] - X[1]) ** 2 + (Y[0] - Y[1]) ** 2) ** 0.5
            angle = math.degrees(math.atan2(X[0] - X[1], Y[0] - Y[1]))
            polygon = cv2.ellipse2Poly(
                (int(mY), int(mX)), (int(length / 2), stickwidth), int(angle), 0, 360, 1
            )
            cv2.fillConvexPoly(canvas, polygon, _BODY_COLORS[i])

    for i in range(6):
        for n in range(len(subset)):
            index = subset[n][np.array(foot_limb_seq[i]) - 1]
            if -1 in index:
                continue
            Y = candidate[index.astype(int), 0] * float(W)
            X = candidate[index.astype(int), 1] * float(H)
            mX = np.mean(X)
            mY = np.mean(Y)
            length = ((X[0] - X[1]) ** 2 + (Y[0] - Y[1]) ** 2) ** 0.5
            angle = math.degrees(math.atan2(X[0] - X[1], Y[0] - Y[1]))
            polygon = cv2.ellipse2Poly(
                (int(mY), int(mX)), (int(length / 2), stickwidth), int(angle), 0, 360, 1
            )
            cv2.fillConvexPoly(canvas, polygon, colors_feet[i])

    canvas = (canvas * 0.6).astype(np.uint8)

    for i in range(24):
        for n in range(len(subset)):
            index = int(subset[n][i])
            if index == -1:
                continue
            x, y = candidate[index][0:2]
            x = int(x * W)
            y = int(y * H)
            cv2.circle(canvas, (int(x), int(y)), 4, _BODY_COLORS[min(i, 17)], thickness=-1)
    return canvas


def draw_bodypose_augmentation(
    canvas, candidate, subset,
    drop_aug=True, shift_aug=False, all_cheek_aug=False,
):
    """Draw body pose with optional augmentation (drop/shift/cheek-only)."""
    H, W, C = canvas.shape
    candidate = np.array(candidate)
    subset = np.array(subset)
    stickwidth = 4

    if drop_aug:
        k_drop = random.choices([0, 1, 2], weights=[0.5, 0.3, 0.2])[0]
        drop_indices = random.sample(list(range(17)), k_drop)
    else:
        drop_indices = []
    if all_cheek_aug:
        drop_indices = list(range(13))

    for i in range(17):
        if i in drop_indices:
            continue
        for n in range(len(subset)):
            index = subset[n][np.array(_LIMB_SEQ[i]) - 1]
            if -1 in index:
                continue
            Y = candidate[index.astype(int), 0] * float(W)
            X = candidate[index.astype(int), 1] * float(H)
            mX = np.mean(X)
            mY = np.mean(Y)
            length = ((X[0] - X[1]) ** 2 + (Y[0] - Y[1]) ** 2) ** 0.5
            angle = math.degrees(math.atan2(X[0] - X[1], Y[0] - Y[1]))
            polygon = cv2.ellipse2Poly(
                (int(mY), int(mX)), (int(length / 2), stickwidth), int(angle), 0, 360, 1
            )
            cv2.fillConvexPoly(canvas, polygon, _BODY_COLORS[i])

    canvas = (canvas * 0.6).astype(np.uint8)

    for i in range(18):
        if all_cheek_aug and i not in [0, 14, 15, 16, 17]:
            continue
        for n in range(len(subset)):
            index = int(subset[n][i])
            if index == -1:
                continue
            x, y = candidate[index][0:2]
            x = int(x * W)
            y = int(y * H)
            cv2.circle(canvas, (int(x), int(y)), 4, _BODY_COLORS[i], thickness=-1)
    return canvas


# ── Hand pose ─────────────────────────────────────────────────────


def draw_handpose_lr(canvas, all_hand_peaks):
    """Draw left/right hand skeletons with L/R colour coding."""
    H, W, C = canvas.shape
    all_num_hands = len(all_hand_peaks)

    for peaks_idx, peaks in enumerate(all_hand_peaks):
        left_or_right = not (peaks_idx >= all_num_hands / 2)
        base_hue = 0 if left_or_right == 0 else 0.3
        peaks = np.array(peaks)

        for ie, e in enumerate(_HAND_EDGES):
            x1, y1 = peaks[e[0]]
            x2, y2 = peaks[e[1]]
            x1, y1, x2, y2 = int(x1 * W), int(y1 * H), int(x2 * W), int(y2 * H)
            if x1 > eps and y1 > eps and x2 > eps and y2 > eps:
                hsv_color = [base_hue + ie / float(len(_HAND_EDGES)) * 0.8,
                             0.9 if left_or_right == 0 else 0.8,
                             0.9 if left_or_right == 0 else 1]
                cv2.line(canvas, (x1, y1), (x2, y2), hsv_to_rgb(hsv_color), thickness=2)

        for keypoint in peaks:
            x, y = keypoint
            x, y = int(x * W), int(y * H)
            if x > eps and y > eps:
                color = (245, 100, 100) if left_or_right == 0 else (100, 100, 255)
                cv2.circle(canvas, (x, y), 4, color, thickness=-1)
    return canvas


def draw_handpose(canvas, all_hand_peaks):
    """Draw hand skeletons with rainbow HSV colouring."""
    H, W, C = canvas.shape
    stickwidth_thin = min(max(int(min(H, W) / 300), 1), 2)

    for peaks in all_hand_peaks:
        peaks = np.array(peaks)
        for ie, e in enumerate(_HAND_EDGES):
            x1, y1 = peaks[e[0]]
            x2, y2 = peaks[e[1]]
            x1, y1, x2, y2 = int(x1 * W), int(y1 * H), int(x2 * W), int(y2 * H)
            if x1 > eps and y1 > eps and x2 > eps and y2 > eps:
                rgb_color = tuple(int(c) for c in hsv_to_rgb([ie / float(len(_HAND_EDGES)), 1.0, 1.0]))
                cv2.line(canvas, (x1, y1), (x2, y2), rgb_color, thickness=stickwidth_thin)

        for keypoint in peaks:
            x, y = keypoint
            x, y = int(x * W), int(y * H)
            if x > eps and y > eps:
                cv2.circle(canvas, (x, y), stickwidth_thin, (0, 0, 255), thickness=-1)
    return canvas


# ── Face pose ─────────────────────────────────────────────────────


def draw_facepose(canvas, all_lmks, optimized_face=True):
    """Draw facial landmarks on canvas."""
    H, W, C = canvas.shape
    stickwidth = min(max(int(min(H, W) / 200), 1), 3)
    stickwidth_thin = min(max(int(min(H, W) / 300), 1), 2)

    for lmks in all_lmks:
        lmks = np.array(lmks)
        for lmk_idx, lmk in enumerate(lmks):
            x, y = lmk
            x, y = int(x * W), int(y * H)
            if x > eps and y > eps:
                if optimized_face:
                    if lmk_idx in list(range(17, 27)) + list(range(36, 70)):
                        cv2.circle(canvas, (x, y), stickwidth_thin, (255, 255, 255), thickness=-1)
                else:
                    cv2.circle(canvas, (x, y), stickwidth, (255, 255, 255), thickness=-1)
    return canvas
