# Copyright 2024-2025 The Alibaba Wan Team Authors. All rights reserved.
# Adapted for ComfyUI-FFMPEGA from Wan2.2 preprocess pipeline.
# Original: https://github.com/Wan-Video/Wan2.2 (Apache 2.0)
"""
Wan-Animate preprocessing pipeline.

Extracts pose skeletons, face crops, background images, and masks
from a driving video using YOLO + ViTPose ONNX models.
"""
from __future__ import annotations

import logging
import math
import os
import warnings
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

logger = logging.getLogger("ComfyUI-FFMPEGA.wan_animate")

# ---------------------------------------------------------------------------
#  Model paths (resolved at runtime via folder_paths → ComfyUI/models/)
# ---------------------------------------------------------------------------
def _resolve_models_root() -> str:
    """Resolve wan_animate models dir: ComfyUI/models/wan_animate/ first, then extension-local."""
    try:
        import folder_paths  # type: ignore[import-not-found]
        comfy_dir = os.path.join(folder_paths.models_dir, "wan_animate")
        if os.path.isdir(comfy_dir):
            return comfy_dir
    except ImportError:
        pass
    # Fallback: extension-local models/ (unlikely to exist since models/ is gitignored)
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "models", "wan_animate",
    )

_MODELS_ROOT = _resolve_models_root()
_DET_PATH = os.path.join(_MODELS_ROOT, "det", "yolov10m.onnx")
_POSE_PATH = os.path.join(_MODELS_ROOT, "pose2d", "vitpose_h_wholebody_model.onnx")


# ═══════════════════════════════════════════════════════════════════════════
#  Utility functions (vendored from Wan2.2 preprocess/utils.py)
# ═══════════════════════════════════════════════════════════════════════════

def resize_by_area(image: np.ndarray, target_area: int, divisor: int = 16) -> np.ndarray:
    """Resize image so total pixel area ≈ target_area, preserving aspect."""
    h, w = image.shape[:2]
    aspect = w / h
    new_h = int(math.sqrt(target_area / aspect))
    new_w = int(target_area / new_h)
    new_w = (new_w // divisor) * divisor
    new_h = (new_h // divisor) * divisor
    if new_w <= 0 or new_h <= 0:
        return image
    interp = cv2.INTER_AREA if (new_w * new_h < w * h) else cv2.INTER_LINEAR
    return padding_resize(image, height=new_h, width=new_w, interpolation=interp)


def padding_resize(
    img: np.ndarray,
    height: int = 512,
    width: int = 512,
    padding_color: Tuple[int, ...] = (0, 0, 0),
    interpolation: int = cv2.INTER_LINEAR,
) -> np.ndarray:
    """Resize with aspect-preserving padding."""
    ori_h, ori_w = img.shape[:2]
    ch = img.shape[2] if img.ndim == 3 else 1
    pad = np.zeros((height, width, ch), dtype=np.uint8)
    for c in range(min(ch, 3)):
        pad[:, :, c] = padding_color[c] if c < len(padding_color) else 0

    if (ori_h / ori_w) > (height / width):
        new_w = int(height / ori_h * ori_w)
        resized = cv2.resize(img, (new_w, height), interpolation=interpolation)
        offset = (width - new_w) // 2
        if resized.ndim == 2:
            resized = resized[:, :, np.newaxis]
        pad[:, offset:offset + new_w, :] = resized
    else:
        new_h = int(width / ori_w * ori_h)
        resized = cv2.resize(img, (width, new_h), interpolation=interpolation)
        offset = (height - new_h) // 2
        if resized.ndim == 2:
            resized = resized[:, :, np.newaxis]
        pad[offset:offset + new_h, :, :] = resized
    return pad.astype(np.uint8)


def get_face_bboxes(
    kp2ds: np.ndarray,
    scale: float = 1.3,
    image_shape: Tuple[int, int] = (480, 832),
) -> List[int]:
    """Get expanded face bounding box from face keypoints."""
    h, w = image_shape
    kp_face = kp2ds.copy()[1:] * (w, h)
    min_x, min_y = np.min(kp_face, axis=0)
    max_x, max_y = np.max(kp_face, axis=0)

    init_w = max(max_x - min_x, 1)
    init_h = max(max_y - min_y, 1)
    init_area = init_w * init_h
    exp_area = init_area * scale

    new_w = np.sqrt(exp_area * (init_w / init_h))
    new_h = np.sqrt(exp_area * (init_h / init_w))
    dw = (new_w - init_w) / 2
    dh = (new_h - init_h) / 4

    x1 = max(int(min_x - dw), 0)
    x2 = min(int(max_x + dw), w)
    y1 = max(int(min_y - 3 * dh), 0)
    y2 = min(int(max_y + dh), h)
    return [x1, x2, y1, y2]


def get_aug_mask(body_mask: np.ndarray, w_len: int = 1, h_len: int = 1) -> np.ndarray:
    """Augment mask by filling grid cells that overlap the body."""
    y_coords, x_coords = np.nonzero(body_mask)
    if len(y_coords) == 0:
        return body_mask
    bbox = [x_coords.min(), y_coords.min(), x_coords.max(), y_coords.max()]
    bbox_wh = [bbox[2] - bbox[0], bbox[3] - bbox[1]]
    w_slice = max(int(bbox_wh[0] / w_len), 1)
    h_slice = max(int(bbox_wh[1] / h_len), 1)
    for ew in range(bbox[0], bbox[2], w_slice):
        ws = min(ew, bbox[2])
        we = min(ew + w_slice, bbox[2])
        for eh in range(bbox[1], bbox[3], h_slice):
            hs = min(eh, bbox[3])
            he = min(eh + h_slice, bbox[3])
            if body_mask[hs:he, ws:we].sum() > 0:
                body_mask[hs:he, ws:we] = 1
    return body_mask


def get_mask_body_img(
    img: np.ndarray, mask: np.ndarray, k: int = 7, iterations: int = 1
) -> Tuple[np.ndarray, np.ndarray]:
    """Dilate mask and return masked image + dilated mask."""
    kernel = np.ones((k, k), np.uint8)
    dilated = cv2.dilate(mask.astype(np.uint8), kernel, iterations=iterations)
    masked = img * (1 - dilated[:, :, None])
    return masked, dilated


def get_frame_indices(
    frame_num: int, video_fps: float, clip_length: int, target_fps: float
) -> List[int]:
    """Compute frame indices for resampling video to target FPS."""
    times = np.arange(0, clip_length) / target_fps
    indices = np.round(times * video_fps).astype(int)
    indices = np.clip(indices, 0, frame_num - 1)
    return indices.tolist()


# ═══════════════════════════════════════════════════════════════════════════
#  AAPoseMeta — pose metadata container
# ═══════════════════════════════════════════════════════════════════════════

class AAPoseMeta:
    """Pose metadata from 133-keypoint ViTPose output."""

    def __init__(self):
        self.width: int = 0
        self.height: int = 0
        self.kps_body: Optional[np.ndarray] = None
        self.kps_lhand: Optional[np.ndarray] = None
        self.kps_rhand: Optional[np.ndarray] = None
        self.kps_face: Optional[np.ndarray] = None
        self.kps_body_p: Optional[np.ndarray] = None
        self.kps_lhand_p: Optional[np.ndarray] = None
        self.kps_rhand_p: Optional[np.ndarray] = None
        self.kps_face_p: Optional[np.ndarray] = None

    @staticmethod
    def from_kp2ds(kp2ds: np.ndarray, width: int, height: int) -> "AAPoseMeta":
        """Create from 133×3 keypoints (x, y, confidence)."""
        meta = AAPoseMeta()
        meta.width = width
        meta.height = height
        body = (
            kp2ds[[0, 6, 6, 8, 10, 5, 7, 9, 12, 14, 16, 11, 13, 15, 2, 1, 4, 3, 17, 20]]
            + kp2ds[[0, 5, 6, 8, 10, 5, 7, 9, 12, 14, 16, 11, 13, 15, 2, 1, 4, 3, 18, 21]]
        ) / 2
        lhand = kp2ds[91:112]
        rhand = kp2ds[112:133]
        face = np.concatenate([kp2ds[23:91], kp2ds[1:3]], axis=0)
        meta.kps_body = body[:, :2]
        meta.kps_body_p = body[:, 2]
        meta.kps_lhand = lhand[:, :2]
        meta.kps_lhand_p = lhand[:, 2]
        meta.kps_rhand = rhand[:, :2]
        meta.kps_rhand_p = rhand[:, 2]
        meta.kps_face = face[:, :2]
        meta.kps_face_p = face[:, 2]
        return meta

    @staticmethod
    def from_humanapi_meta(meta_dict: dict) -> "AAPoseMeta":
        """Create from pipeline metadata dict (normalized coords)."""
        meta = AAPoseMeta()
        w, h = meta_dict["width"], meta_dict["height"]
        meta.width = w
        meta.height = h
        meta.kps_body = meta_dict["keypoints_body"][:, :2] * (w, h)
        meta.kps_body_p = meta_dict["keypoints_body"][:, 2]
        meta.kps_lhand = meta_dict["keypoints_left_hand"][:, :2] * (w, h)
        meta.kps_lhand_p = meta_dict["keypoints_left_hand"][:, 2]
        meta.kps_rhand = meta_dict["keypoints_right_hand"][:, :2] * (w, h)
        meta.kps_rhand_p = meta_dict["keypoints_right_hand"][:, 2]
        if "keypoints_face" in meta_dict:
            meta.kps_face = meta_dict["keypoints_face"][:, :2] * (w, h)
            meta.kps_face_p = meta_dict["keypoints_face"][:, 2]
        return meta

    def padding_resize(self, height: int, width: int) -> "AAPoseMeta":
        """Rescale keypoints for padding_resize transformation."""
        all_kps = [self.kps_body, self.kps_lhand, self.kps_rhand, self.kps_face]
        ori_h, ori_w = self.height, self.width
        if (ori_h / ori_w) > (height / width):
            scale = height / ori_h
            padding = (width - int(ori_w * scale)) // 2
            for kps in all_kps:
                if kps is not None:
                    kps[:, 0] = kps[:, 0] * scale + padding
                    kps[:, 1] = kps[:, 1] * scale
        else:
            scale = width / ori_w
            padding = (height - int(ori_h * scale)) // 2
            for kps in all_kps:
                if kps is not None:
                    kps[:, 1] = kps[:, 1] * scale + padding
                    kps[:, 0] = kps[:, 0] * scale
        self.width = width
        self.height = height
        return self


# ═══════════════════════════════════════════════════════════════════════════
#  Keypoint post-processing (vendored from pose2d_utils.py)
# ═══════════════════════════════════════════════════════════════════════════

def _transform(pt, center, scale, res, invert=0):
    """Affine transform for bounding box → crop mapping."""
    t = np.zeros((3, 3))
    t[0, 0] = float(res[1]) / scale
    t[1, 1] = float(res[0]) / scale
    t[0, 2] = res[1] * (-float(center[0]) / scale + 0.5)
    t[1, 2] = res[0] * (-float(center[1]) / scale + 0.5)
    t[2, 2] = 1
    if invert:
        t = np.linalg.inv(t)
    new_pt = np.array([pt[0] - 1, pt[1] - 1, 1.0]).T
    new_pt = np.dot(t, new_pt)
    return new_pt[:2].astype(int) + 1


def _transform_preds(coords, center, scale, output_size, use_udp=False):
    """Transform keypoint predictions back to image coordinates."""
    if use_udp:
        sx = scale[0] / (output_size[0] - 1.0)
        sy = scale[1] / (output_size[1] - 1.0)
    else:
        sx = scale[0] / output_size[0]
        sy = scale[1] / output_size[1]
    target = np.ones_like(coords)
    target[:, 0] = coords[:, 0] * sx + center[0] - scale[0] * 0.5
    target[:, 1] = coords[:, 1] * sy + center[1] - scale[1] * 0.5
    return target


def _get_max_preds(heatmaps):
    """Get keypoint predictions from heatmaps."""
    N, K, _, W = heatmaps.shape
    reshaped = heatmaps.reshape((N, K, -1))
    idx = np.argmax(reshaped, 2).reshape((N, K, 1))
    maxvals = np.amax(reshaped, 2).reshape((N, K, 1))
    preds = np.tile(idx, (1, 1, 2)).astype(np.float32)
    preds[:, :, 0] = preds[:, :, 0] % W
    preds[:, :, 1] = preds[:, :, 1] // W
    preds = np.where(np.tile(maxvals, (1, 1, 2)) > 0.0, preds, -1)
    return preds, maxvals


def _gaussian_blur(heatmaps, kernel=11):
    """Modulate heatmap distribution with Gaussian."""
    border = (kernel - 1) // 2
    B, K, H, W = heatmaps.shape
    for i in range(B):
        for j in range(K):
            origin_max = np.max(heatmaps[i, j])
            dr = np.zeros((H + 2 * border, W + 2 * border), dtype=np.float32)
            dr[border:-border, border:-border] = heatmaps[i, j].copy()
            dr = cv2.GaussianBlur(dr, (kernel, kernel), 0)
            heatmaps[i, j] = dr[border:-border, border:-border].copy()
            if np.max(heatmaps[i, j]) > 0:
                heatmaps[i, j] *= origin_max / np.max(heatmaps[i, j])
    return heatmaps


def _taylor(heatmap, coord):
    """Distribution-aware coordinate refinement."""
    H, W = heatmap.shape[:2]
    px, py = int(coord[0]), int(coord[1])
    if 1 < px < W - 2 and 1 < py < H - 2:
        dx = 0.5 * (heatmap[py][px + 1] - heatmap[py][px - 1])
        dy = 0.5 * (heatmap[py + 1][px] - heatmap[py - 1][px])
        dxx = 0.25 * (heatmap[py][px + 2] - 2 * heatmap[py][px] + heatmap[py][px - 2])
        dxy = 0.25 * (
            heatmap[py + 1][px + 1] - heatmap[py - 1][px + 1]
            - heatmap[py + 1][px - 1] + heatmap[py - 1][px - 1]
        )
        dyy = 0.25 * (heatmap[py + 2][px] - 2 * heatmap[py][px] + heatmap[py - 2][px])
        derivative = np.array([[dx], [dy]])
        hessian = np.array([[dxx, dxy], [dxy, dyy]])
        if dxx * dyy - dxy ** 2 != 0:
            hessianinv = np.linalg.inv(hessian)
            offset = -hessianinv @ derivative
            coord += np.squeeze(offset.T)
    return coord


def keypoints_from_heatmaps(
    heatmaps, center, scale, unbiased=True, kernel=11, use_udp=False
):
    """Extract keypoints from heatmaps and transform to image coords."""
    heatmaps = heatmaps.copy()
    N, K, H, W = heatmaps.shape
    preds, maxvals = _get_max_preds(heatmaps)
    if unbiased:
        heatmaps = np.log(np.maximum(_gaussian_blur(heatmaps, kernel), 1e-10))
        for n in range(N):
            for k in range(K):
                preds[n][k] = _taylor(heatmaps[n][k], preds[n][k])
    for i in range(N):
        preds[i] = _transform_preds(preds[i], center[i], scale[i], [W, H], use_udp=use_udp)
    return preds, maxvals


def bbox_from_detector(bbox, input_resolution=(256, 192), rescale=1.25):
    """Get center and scale from bounding box for ViTPose crop."""
    crop_h, crop_w = input_resolution
    aspect = crop_h / float(crop_w)
    cx = (bbox[0] + bbox[2]) / 2.0
    cy = (bbox[1] + bbox[3]) / 2.0
    center = np.array([cx, cy])
    bw = bbox[2] - bbox[0]
    bh = bbox[3] - bbox[1]
    bbox_size = max(bw * aspect, bh)
    scale = np.array([bbox_size / aspect, bbox_size]) / 200.0
    scale *= rescale
    return center, scale


def crop_for_pose(img, center, scale, res):
    """Crop image region for pose estimation."""
    ul = np.array(_transform([1, 1], center, max(scale), res, invert=1)) - 1
    br = np.array(_transform([res[1] + 1, res[0] + 1], center, max(scale), res, invert=1)) - 1
    new_shape = [br[1] - ul[1], br[0] - ul[0]]
    if len(img.shape) > 2:
        new_shape += [img.shape[2]]
    new_img = np.zeros(new_shape, dtype=np.float32)
    new_x = max(0, -ul[0]), min(br[0], img.shape[1]) - ul[0]
    new_y = max(0, -ul[1]), min(br[1], img.shape[0]) - ul[1]
    old_x = max(0, ul[0]), min(img.shape[1], br[0])
    old_y = max(0, ul[1]), min(img.shape[0], br[1])
    try:
        new_img[new_y[0]:new_y[1], new_x[0]:new_x[1]] = img[old_y[0]:old_y[1], old_x[0]:old_x[1]]
    except Exception:
        pass
    new_img = cv2.resize(new_img, (res[1], res[0]))
    return new_img


def box_convert_xywh2xyxy(box):
    """Convert [x, y, w, h] to [x1, y1, x2, y2]."""
    return [box[0], box[1], box[2] + box[0], box[3] + box[1]]


def load_pose_metas_from_kp2ds(kp2ds_seq, width, height):
    """Convert sequence of 133-keypoint arrays → list of metadata dicts."""

    def _split(kps):
        body = (
            kps[[0, 6, 6, 8, 10, 5, 7, 9, 12, 14, 16, 11, 13, 15, 2, 1, 4, 3, 17, 20]]
            + kps[[0, 5, 6, 8, 10, 5, 7, 9, 12, 14, 16, 11, 13, 15, 2, 1, 4, 3, 18, 21]]
        ) / 2
        lhand = kps[91:112]
        rhand = kps[112:133]
        face = np.concatenate([kps[23:91], kps[1:3]], axis=0)
        return body.copy(), lhand.copy(), rhand.copy(), face.copy()

    metas = []
    last_body = None
    for kps in kp2ds_seq:
        kps = kps.copy()
        kps[:, 0] /= width
        kps[:, 1] /= height
        body, lhand, rhand, face = _split(kps)
        if body[:, :2].min(axis=1).max() < 0 and last_body is not None:
            body = last_body
        last_body = body
        metas.append({
            "width": width,
            "height": height,
            "keypoints_body": body,
            "keypoints_left_hand": lhand,
            "keypoints_right_hand": rhand,
            "keypoints_face": face,
        })
    return metas


# ═══════════════════════════════════════════════════════════════════════════
#  Pose drawing (vendored from human_visualization.py)
# ═══════════════════════════════════════════════════════════════════════════

def _draw_handpose(canvas, keypoints, hand_score_th=0.6):
    """Draw hand skeleton on canvas."""
    import matplotlib.colors
    eps = 0.01
    H, W, _ = canvas.shape
    sw = max(max(int(min(H, W) / 200) - 1, 1) // 2, 1)
    edges = [
        [0, 1], [1, 2], [2, 3], [3, 4],
        [0, 5], [5, 6], [6, 7], [7, 8],
        [0, 9], [9, 10], [10, 11], [11, 12],
        [0, 13], [13, 14], [14, 15], [15, 16],
        [0, 17], [17, 18], [18, 19], [19, 20],
    ]
    for ie, (e1, e2) in enumerate(edges):
        k1, k2 = keypoints[e1], keypoints[e2]
        if k1 is None or k2 is None:
            continue
        if k1[2] < hand_score_th or k2[2] < hand_score_th:
            continue
        x1, y1 = int(k1[0]), int(k1[1])
        x2, y2 = int(k2[0]), int(k2[1])
        if x1 > eps and y1 > eps and x2 > eps and y2 > eps:
            color = np.array(matplotlib.colors.hsv_to_rgb(
                [ie / float(len(edges)), 1.0, 1.0]
            )) * 255
            cv2.line(canvas, (x1, y1), (x2, y2), color.tolist(), thickness=sw)
    for kp in keypoints:
        if kp is None or kp[2] < hand_score_th:
            continue
        x, y = int(kp[0]), int(kp[1])
        if x > eps and y > eps:
            cv2.circle(canvas, (x, y), sw, (0, 0, 255), thickness=-1)
    return canvas


def draw_aapose(
    img: np.ndarray,
    meta: AAPoseMeta,
    threshold: float = 0.5,
    draw_hand: bool = True,
    draw_head: bool = True,
) -> np.ndarray:
    """Draw AA-pose skeleton on image (v2 style — thinner lines)."""
    kp2ds = np.concatenate([meta.kps_body, meta.kps_body_p[:, None]], axis=1).copy()
    kp_lhand = np.concatenate([meta.kps_lhand, meta.kps_lhand_p[:, None]], axis=1)
    kp_rhand = np.concatenate([meta.kps_rhand, meta.kps_rhand_p[:, None]], axis=1)

    if not draw_head:
        kp2ds[[0, 14, 15, 16, 17], 2] = 0.0

    limbs = [
        (2, 3), (2, 6), (3, 4), (4, 5), (6, 7), (7, 8),
        (2, 9), (9, 10), (10, 11), (2, 12), (12, 13), (13, 14),
        (2, 1), (1, 15), (15, 17), (1, 16), (16, 18), (14, 19), (11, 20),
    ]
    colors = [
        [255, 0, 0], [255, 85, 0], [255, 170, 0], [255, 255, 0],
        [170, 255, 0], [85, 255, 0], [0, 255, 0], [0, 255, 85],
        [0, 255, 170], [0, 255, 255], [0, 170, 255], [0, 85, 255],
        [0, 0, 255], [85, 0, 255], [170, 0, 255], [255, 0, 255],
        [255, 0, 170], [255, 0, 85], [200, 200, 0], [100, 100, 0],
    ]

    H, W, _ = img.shape
    sw = max(max(int(min(H, W) / 200) - 1, 1) // 2, 1)

    for (k1i, k2i), color in zip(limbs, colors):
        kp1 = kp2ds[k1i - 1]
        kp2 = kp2ds[k2i - 1]
        if kp1[2] < threshold or kp2[2] < threshold:
            continue
        Y = np.array([kp1[0], kp2[0]])
        X = np.array([kp1[1], kp2[1]])
        mX, mY = np.mean(X), np.mean(Y)
        length = np.sqrt((X[0] - X[1]) ** 2 + (Y[0] - Y[1]) ** 2)
        angle = math.degrees(math.atan2(X[0] - X[1], Y[0] - Y[1]))
        polygon = cv2.ellipse2Poly(
            (int(mY), int(mX)), (int(length / 2), sw), int(angle), 0, 360, 1
        )
        cv2.fillConvexPoly(img, polygon, [int(float(c) * 0.6) for c in color])

    for i, (kp, color) in enumerate(zip(kp2ds, colors)):
        if kp[2] < threshold:
            continue
        cv2.circle(img, (int(kp[0]), int(kp[1])), sw, color, thickness=-1)

    if draw_hand:
        _draw_handpose(img, kp_lhand, hand_score_th=threshold)
        _draw_handpose(img, kp_rhand, hand_score_th=threshold)

    return img


# ═══════════════════════════════════════════════════════════════════════════
#  ONNX inference wrappers
# ═══════════════════════════════════════════════════════════════════════════

class _YoloDetector:
    """YOLOv10 person detector via ONNX Runtime."""

    def __init__(self, checkpoint: str, device: str = "cuda"):
        import onnxruntime
        providers = (
            [("CUDAExecutionProvider", {"device_id": "0"}), "CPUExecutionProvider"]
            if "cuda" in device
            else ["CPUExecutionProvider"]
        )
        self.session = onnxruntime.InferenceSession(checkpoint, providers=providers)
        self.input_name = self.session.get_inputs()[0].name
        self.conf_threshold = 0.05
        self.iou_threshold = 0.5

    def detect(self, image: np.ndarray) -> np.ndarray:
        """Detect persons in a single RGB image. Returns [x1,y1,x2,y2,score]."""
        h, w = image.shape[:2]
        resized = cv2.resize(image, (640, 640))
        blob = (resized.astype(np.float32) / 255.0).transpose(2, 0, 1)[None]
        outputs = self.session.run(None, {self.input_name: blob})[0]
        outputs = np.squeeze(outputs)
        if outputs.ndim == 1:
            outputs = outputs[None]

        x_factor = w / 640.0
        y_factor = h / 640.0

        # YOLOv10 format: [x1, y1, x2, y2, score, class_id]
        if outputs.shape[-1] == 6:
            mask = outputs[:, 4] >= self.conf_threshold
            dets = outputs[mask]
            if len(dets) == 0:
                return np.array([[0.0, 0.0, float(w), float(h), -1.0]])
            # Person class = 0
            person_mask = dets[:, 5].astype(int) == 0
            dets = dets[person_mask]
            if len(dets) == 0:
                return np.array([[0.0, 0.0, float(w), float(h), -1.0]])
            dets[:, 0] *= x_factor
            dets[:, 1] *= y_factor
            dets[:, 2] *= x_factor
            dets[:, 3] *= y_factor
            # Select largest person
            areas = (dets[:, 2] - dets[:, 0]) * (dets[:, 3] - dets[:, 1])
            best = np.argmax(areas)
            return dets[best:best + 1, :5]
        return np.array([[0.0, 0.0, float(w), float(h), -1.0]])


class _ViTPoseEstimator:
    """ViTPose-H wholebody keypoint estimator via ONNX Runtime."""

    IMG_NORM_MEAN = np.array([0.485, 0.456, 0.406])
    IMG_NORM_STD = np.array([0.229, 0.224, 0.225])

    def __init__(self, checkpoint: str, device: str = "cuda"):
        import onnxruntime
        providers = (
            [("CUDAExecutionProvider", {"device_id": "0"}), "CPUExecutionProvider"]
            if "cuda" in device
            else ["CPUExecutionProvider"]
        )
        self.session = onnxruntime.InferenceSession(checkpoint, providers=providers)
        self.input_name = self.session.get_inputs()[0].name
        input_shape = self.session.get_inputs()[0].shape
        self.input_resolution = (input_shape[2], input_shape[3])  # (H, W)

    def estimate(self, image: np.ndarray, bbox: np.ndarray) -> np.ndarray:
        """Estimate 133 keypoints for a single person. Returns (133, 3)."""
        center, scale = bbox_from_detector(bbox[:4], self.input_resolution, rescale=1.25)
        cropped = crop_for_pose(image, center, scale, self.input_resolution)
        normed = ((cropped / 255.0 - self.IMG_NORM_MEAN) / self.IMG_NORM_STD).transpose(2, 0, 1).astype(np.float32)
        heatmaps = self.session.run([], {self.input_name: normed[None]})[0]
        points, prob = keypoints_from_heatmaps(
            heatmaps=heatmaps,
            center=center[None],
            scale=(scale * 200)[None],
            unbiased=True,
        )
        return np.concatenate([points[0], prob[0]], axis=1)  # (133, 3)


class Pose2dExtractor:
    """YOLO + ViTPose pipeline for whole-body 2D pose estimation."""

    def __init__(
        self,
        det_path: str = _DET_PATH,
        pose_path: str = _POSE_PATH,
        device: str = "cuda",
    ):
        if not os.path.exists(det_path):
            raise FileNotFoundError(
                f"YOLO model not found: {det_path}\n"
                "Download yolov10m.onnx to models/wan_animate/det/"
            )
        if not os.path.exists(pose_path):
            raise FileNotFoundError(
                f"ViTPose model not found: {pose_path}\n"
                "Download vitpose_h_wholebody.onnx to models/wan_animate/pose2d/"
            )
        self.detector = _YoloDetector(det_path, device)
        self.estimator = _ViTPoseEstimator(pose_path, device)

    def __call__(self, frames: List[np.ndarray]) -> List[dict]:
        """Extract pose metadata for each frame (RGB numpy arrays)."""
        H, W = frames[0].shape[:2]
        kp2ds_all = []
        for frame in frames:
            bbox = self.detector.detect(frame)[0]
            kp2d = self.estimator.estimate(frame, bbox)
            kp2ds_all.append(kp2d)
        kp2ds_seq = np.array(kp2ds_all)  # (N, 133, 3)
        metas = load_pose_metas_from_kp2ds(kp2ds_seq, width=W, height=H)
        return metas


# ═══════════════════════════════════════════════════════════════════════════
#  Debug overlay — draw skeleton + face bbox on driving frames
# ═══════════════════════════════════════════════════════════════════════════

def draw_debug_overlay(
    frames: List[np.ndarray],
    metas: List[dict],
    face_bboxes: List[List[int]],
) -> List[np.ndarray]:
    """Overlay skeleton + face bounding boxes on original frames for debug."""
    debug_frames = []
    for frame, meta, face_bb in zip(frames, metas, face_bboxes):
        canvas = frame.copy()
        pose_meta = AAPoseMeta.from_humanapi_meta(meta)
        draw_aapose(canvas, pose_meta, threshold=0.3, draw_hand=True, draw_head=True)
        # Draw face bounding box
        x1, x2, y1, y2 = face_bb
        cv2.rectangle(canvas, (x1, y1), (x2, y2), (0, 255, 0), 2)
        cv2.putText(canvas, "face", (x1, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
        debug_frames.append(canvas)
    return debug_frames


# ═══════════════════════════════════════════════════════════════════════════
#  Main preprocessing pipeline
# ═══════════════════════════════════════════════════════════════════════════

class WanAnimatePreprocessor:
    """Complete Wan-Animate preprocessing pipeline.

    Takes a driving video and reference image, produces:
    - pose conditioning images (skeleton on black canvas)
    - face crops (512×512 per frame)
    - background images (for replacement mode)
    - masks (for replacement mode)
    - debug overlay video frames
    """

    def __init__(self, device: str = "cuda"):
        self.device = device
        self._pose2d: Optional[Pose2dExtractor] = None

    def _ensure_models(self):
        """Lazy-load ONNX models."""
        if self._pose2d is None:
            self._pose2d = Pose2dExtractor(
                det_path=_DET_PATH,
                pose_path=_POSE_PATH,
                device=self.device,
            )

    def preprocess(
        self,
        frames: List[np.ndarray],
        refer_image: np.ndarray,
        mode: str = "animate",
        resolution_area: int = 1280 * 720,
        iterations: int = 3,
        k: int = 7,
        w_len: int = 1,
        h_len: int = 1,
    ) -> Dict[str, object]:
        """Run the full preprocessing pipeline.

        Args:
            frames: List of driving video frames (RGB numpy arrays).
            refer_image: Reference character image (RGB numpy array).
            mode: "animate" or "replace".
            resolution_area: Target pixel area for processing.
            iterations: Mask dilation iterations (replace mode).
            k: Mask dilation kernel size (replace mode).
            w_len: Mask grid w subdivisions (replace mode).
            h_len: Mask grid h subdivisions (replace mode).

        Returns:
            dict with keys:
              - pose_frames: List[np.ndarray] — skeleton conditioning images
              - face_frames: List[np.ndarray] — 512×512 face crops
              - ref_image: np.ndarray — processed reference image
              - debug_frames: List[np.ndarray] — skeleton+face overlay on originals
              - bg_frames: List[np.ndarray] | None — background (replace mode)
              - mask_frames: List[np.ndarray] | None — masks (replace mode)
        """
        self._ensure_models()

        # Resize frames
        frames = [resize_by_area(f, resolution_area, divisor=16) for f in frames]
        H, W = frames[0].shape[:2]

        logger.info("WanAnimate: Processing %d frames at %dx%d", len(frames), W, H)

        # Extract pose metadata
        logger.info("WanAnimate: Extracting pose keypoints...")
        pose_metas = self._pose2d(frames)

        # Extract face images
        face_frames = []
        face_bboxes = []
        for idx, meta in enumerate(pose_metas):
            fb = get_face_bboxes(
                meta["keypoints_face"][:, :2],
                scale=1.3,
                image_shape=(H, W),
            )
            face_bboxes.append(fb)
            x1, x2, y1, y2 = fb
            face_crop = frames[idx][max(y1, 0):max(y2, 1), max(x1, 0):max(x2, 1)]
            if face_crop.size == 0:
                face_crop = np.zeros((512, 512, 3), dtype=np.uint8)
            else:
                face_crop = cv2.resize(face_crop, (512, 512))
            face_frames.append(face_crop)

        # Process reference image
        ref_processed = padding_resize(refer_image, H, W)

        # Draw conditioning (skeleton) images
        aa_metas = [AAPoseMeta.from_humanapi_meta(m) for m in pose_metas]
        cond_images = []
        for meta in aa_metas:
            canvas = np.zeros((H, W, 3), dtype=np.uint8)
            draw_aapose(canvas, meta, threshold=0.5, draw_hand=True, draw_head=True)
            if mode == "animate":
                # For animation mode, resize to match reference
                canvas = padding_resize(canvas, ref_processed.shape[0], ref_processed.shape[1])
            cond_images.append(canvas)

        # Debug overlay
        debug_frames = draw_debug_overlay(frames, pose_metas, face_bboxes)

        result = {
            "pose_frames": cond_images,
            "face_frames": face_frames,
            "ref_image": ref_processed,
            "debug_frames": debug_frames,
            "bg_frames": None,
            "mask_frames": None,
        }

        # Replacement mode: extract backgrounds and masks
        if mode == "replace":
            bg_frames = []
            mask_frames = []
            for frame, meta in zip(frames, pose_metas):
                # Simple body mask from body keypoints
                body_kps = meta["keypoints_body"][:, :2] * (W, H)
                body_kps = body_kps[meta["keypoints_body"][:, 2] > 0.3]
                mask = np.zeros((H, W), dtype=np.uint8)
                if len(body_kps) > 2:
                    hull = cv2.convexHull(body_kps.astype(np.int32))
                    cv2.fillConvexPoly(mask, hull, 1)
                if iterations > 0:
                    _, mask = get_mask_body_img(frame, mask, k=k, iterations=iterations)
                    mask = get_aug_mask(mask, w_len=w_len, h_len=h_len)
                bg = frame * (1 - mask[:, :, None])
                bg_frames.append(bg.astype(np.uint8))
                mask_frames.append(mask)
            result["bg_frames"] = bg_frames
            result["mask_frames"] = mask_frames

        logger.info("WanAnimate: Preprocessing complete. %d pose, %d face frames.",
                     len(cond_images), len(face_frames))
        return result

    def cleanup(self):
        """Release ONNX sessions."""
        self._pose2d = None


def cleanup():
    """Module-level cleanup for VRAM coordination."""
    pass  # ONNX sessions are GC'd when Pose2dExtractor is released
