# coding: utf-8
"""Visualization helpers for Sapiens2 outputs.

Vendored from the sapiens2 reference vis scripts so the integration does
not depend on the upstream ``tools/vis/`` directory, which is not
shipped as part of the installable ``sapiens`` package.

Sources:
- ``visualize_keypoints``  → ``sapiens/pose/tools/vis/pose_render_utils.py``
- normal/pointmap helpers  → ``sapiens/dense/tools/vis/vis_*.py``

No torch imports here — pure numpy + opencv.  Keeps post-processing
testable in isolation.
"""

from __future__ import annotations

import logging
from typing import Optional, Sequence

import cv2
import numpy as np

log = logging.getLogger("ffmpega")


# ---------------------------------------------------------------------------
# Pose: keypoint overlay
# ---------------------------------------------------------------------------

def visualize_keypoints(
    image_rgb: np.ndarray,        # uint8 HxWx3
    keypoints: Sequence[np.ndarray],            # list of (J,2)
    keypoints_visible: Sequence[np.ndarray],    # list of (J,) bool/{0,1}
    keypoint_scores: Sequence[np.ndarray],      # list of (J,)
    *,
    radius: int = 4,
    thickness: int = 1,
    kpt_thr: float = 0.3,
    skeleton: Optional[list] = None,            # list of (i,j)
    kpt_color=None,
    link_color=None,
) -> np.ndarray:
    """Draw keypoints (and optional skeleton links) onto an RGB image.

    Returns a new RGB uint8 image with the same shape as ``image_rgb``.
    Inputs are not modified.
    """
    if image_rgb.dtype != np.uint8:
        raise TypeError(
            f"visualize_keypoints: expected uint8 image, got {image_rgb.dtype}"
        )
    if image_rgb.ndim != 3 or image_rgb.shape[2] != 3:
        raise ValueError(
            f"visualize_keypoints: expected HxWx3 image, got shape "
            f"{image_rgb.shape}"
        )

    img = image_rgb.copy()
    H, W = img.shape[:2]

    if skeleton is None:
        skeleton = []
    if kpt_color is None:
        kpt_color = (255, 0, 0)
    if link_color is None:
        link_color = (0, 255, 0)

    def _as_color_list(c, n: int) -> list[tuple[int, int, int]]:
        if hasattr(c, "detach"):
            c = c.detach().cpu().numpy()
        if isinstance(c, np.ndarray):
            if c.ndim == 2 and c.shape[1] == 3:
                return [tuple(int(v) for v in row) for row in c.tolist()]
            if c.size == 3:
                return [tuple(int(v) for v in c.tolist())] * max(1, n)
        if isinstance(c, (list, tuple)):
            if n and len(c) == n and isinstance(c[0], (list, tuple, np.ndarray)):
                out = []
                for cc in c:
                    cc = np.asarray(cc).reshape(-1)
                    if cc.size != 3:
                        raise ValueError("Each keypoint color must be length-3")
                    out.append(tuple(int(v) for v in cc.tolist()))
                return out
            c_arr = np.asarray(c).reshape(-1)
            if c_arr.size == 3:
                return [tuple(int(v) for v in c_arr.tolist())] * max(1, n)
        return [(255, 0, 0)] * max(1, n)

    J = keypoints[0].shape[0] if keypoints else 0
    kpt_colors = _as_color_list(kpt_color, J)
    link_colors = _as_color_list(link_color, len(skeleton))

    def _in_bounds(x: int, y: int) -> bool:
        return 0 <= x < W and 0 <= y < H

    for kpts, vis, score in zip(keypoints, keypoints_visible, keypoint_scores):
        kpts = np.asarray(kpts, float)
        vis = np.asarray(vis).reshape(-1).astype(bool)
        score = np.asarray(score).reshape(-1)

        # skeleton
        for lk, (i, j) in enumerate(skeleton):
            if i >= len(kpts) or j >= len(kpts):
                continue
            if not (vis[i] and vis[j]):
                continue
            if score[i] < kpt_thr or score[j] < kpt_thr:
                continue
            x1, y1 = map(int, np.round(kpts[i]))
            x2, y2 = map(int, np.round(kpts[j]))
            if not (_in_bounds(x1, y1) and _in_bounds(x2, y2)):
                continue
            cv2.line(
                img, (x1, y1), (x2, y2),
                link_colors[lk % len(link_colors)],
                thickness=max(1, thickness),
                lineType=cv2.LINE_AA,
            )

        # points
        for j_idx, (xy, v, s) in enumerate(zip(kpts, vis, score)):
            if not v or s < kpt_thr:
                continue
            x, y = map(int, np.round(xy))
            if not _in_bounds(x, y):
                continue
            c = kpt_colors[min(j_idx, len(kpt_colors) - 1)]
            cv2.circle(img, (x, y), radius, c, thickness=-1, lineType=cv2.LINE_AA)

    return img


# ---------------------------------------------------------------------------
# Dense: surface normals
# ---------------------------------------------------------------------------

def visualize_normals(
    normal: np.ndarray,  # HxWx3 float, unit-norm (model output domain)
    *,
    mask: Optional[np.ndarray] = None,
    background_bgr: Optional[np.ndarray] = None,
) -> np.ndarray:
    """Render unit normals as BGR uint8 (matches sapiens vis_normal.py).

    Normals are mapped from ``[-1, 1]`` to ``[0, 255]`` and the channels
    are flipped to BGR for cv2 consumers.

    If ``mask`` is provided, background pixels are either black (when
    ``background_bgr`` is None) or copied from ``background_bgr``.
    """
    if normal.ndim != 3 or normal.shape[2] != 3:
        raise ValueError(f"visualize_normals: expected HxWx3, got {normal.shape}")
    out = normal.copy()
    if mask is not None:
        out[mask == 0] = -1
    rgb = ((out + 1.0) / 2.0 * 255.0).clip(0, 255).astype(np.uint8)
    bgr = rgb[:, :, ::-1].copy()
    if mask is not None and background_bgr is not None:
        if background_bgr.shape != bgr.shape:
            raise ValueError(
                "visualize_normals: background_bgr shape "
                f"{background_bgr.shape} != normal vis shape {bgr.shape}"
            )
        bgr[mask == 0] = background_bgr[mask == 0]
    return bgr


# ---------------------------------------------------------------------------
# Dense: pointmap (depth from z-channel of the predicted point cloud)
# ---------------------------------------------------------------------------

_TURBO_LUT_CACHE: Optional[np.ndarray] = None


def _turbo_lut() -> np.ndarray:
    """Return a (256, 3) BGR uint8 turbo LUT, computed lazily.

    We use OpenCV's COLORMAP_TURBO directly so we don't pull in matplotlib
    at inference time.
    """
    global _TURBO_LUT_CACHE
    if _TURBO_LUT_CACHE is None:
        gray = np.arange(256, dtype=np.uint8).reshape(256, 1)
        bgr = cv2.applyColorMap(gray, cv2.COLORMAP_TURBO)  # (256, 1, 3)
        _TURBO_LUT_CACHE = bgr.reshape(256, 3)
    return _TURBO_LUT_CACHE


def visualize_pointmap_z(
    pointmap: np.ndarray,  # HxWx3 float (x, y, z) in camera space
    *,
    mask: Optional[np.ndarray] = None,
    percentile: tuple[float, float] = (2.0, 98.0),
) -> np.ndarray:
    """Render the z-channel of a pointmap as a turbo-colormap BGR image.

    Uses robust min/max via ``percentile`` to avoid outliers from a few
    extreme depth values dominating the colormap.  Background pixels
    (where ``mask == 0``) are filled with a neutral grey.
    """
    if pointmap.ndim != 3 or pointmap.shape[2] != 3:
        raise ValueError(
            f"visualize_pointmap_z: expected HxWx3, got {pointmap.shape}"
        )
    H, W = pointmap.shape[:2]
    z = pointmap[..., 2].astype(np.float32)

    if mask is None:
        active = np.ones((H, W), dtype=bool)
    else:
        active = mask > 0

    if not active.any():
        return np.full((H, W, 3), 100, dtype=np.uint8)

    z_active = z[active]
    lo, hi = np.percentile(z_active, percentile)
    if hi - lo < 1e-6:
        hi = lo + 1e-6
    norm = np.clip((z - lo) / (hi - lo), 0.0, 1.0)
    idx = (norm * 255.0).astype(np.uint8)

    lut = _turbo_lut()
    out_flat = lut[idx.reshape(-1)]
    out = out_flat.reshape(H, W, 3).copy()
    out[~active] = 100
    return out


# ---------------------------------------------------------------------------
# Dense: human matting (composite alpha onto green for preview)
# ---------------------------------------------------------------------------

# Default chroma green (BGR), matches sapiens/dense/tools/vis/vis_matting.py.
_DEFAULT_GREEN_BGR = (0, 177, 64)


def composite_matting(
    image_bgr: np.ndarray,  # HxWx3 uint8 — original frame
    fgr_rgb: np.ndarray,    # HxWx3 float in [0, 1] — pre-multiplied foreground
    alpha: np.ndarray,      # HxW float in [0, 1] — alpha matte
    *,
    background_bgr: tuple[int, int, int] = _DEFAULT_GREEN_BGR,
) -> tuple[np.ndarray, np.ndarray]:
    """Return ``(composite_bgr, alpha_bgr3)``.

    ``composite_bgr`` is the predicted foreground over ``background_bgr``,
    matching what sapiens' demo renders.  ``alpha_bgr3`` is a 3-channel
    visualization of the alpha matte (so it can be muxed into the same
    H.264 stream).  Both outputs are uint8 HxWx3 BGR.
    """
    if fgr_rgb.shape[:2] != alpha.shape[:2]:
        raise ValueError(
            "composite_matting: fgr_rgb and alpha shapes disagree "
            f"({fgr_rgb.shape[:2]} vs {alpha.shape[:2]})"
        )
    if image_bgr.shape[:2] != alpha.shape[:2]:
        raise ValueError(
            "composite_matting: image_bgr and alpha shapes disagree "
            f"({image_bgr.shape[:2]} vs {alpha.shape[:2]})"
        )

    # Foreground arrives as RGB pre-multiplied by alpha.  Composite over
    # the chosen background: out = fgr + (1 - alpha) * bg.
    fgr_bgr = fgr_rgb[..., ::-1]  # RGB -> BGR
    bg = np.full_like(image_bgr, background_bgr, dtype=np.float32) / 255.0
    a = alpha[..., None].astype(np.float32)
    composite = fgr_bgr + (1.0 - a) * bg
    composite_u8 = (composite.clip(0.0, 1.0) * 255.0).astype(np.uint8)

    alpha_u8 = (alpha.clip(0.0, 1.0) * 255.0).astype(np.uint8)
    alpha_bgr3 = np.stack([alpha_u8, alpha_u8, alpha_u8], axis=-1)

    return composite_u8, alpha_bgr3


# ---------------------------------------------------------------------------
# Pretrain: PCA-based feature visualization
# ---------------------------------------------------------------------------

def visualize_features_pca(
    features: np.ndarray,  # channels-first (C, H, W) float
) -> np.ndarray:
    """Project per-pixel features to RGB via PCA → BGR uint8.

    Used for the ``pretrain`` task so users get *something* visible
    instead of a 1500-channel feature map.  The first 3 principal
    components map to (B, G, R); pixels are independently normalized to
    [0, 1] using global per-component min/max.

    Input is expected channels-first ``(C, H, W)`` (matching PyTorch
    convention).  Shape is not auto-detected because a feature map with
    fewer channels than spatial extent (e.g. a 64-channel 256×256 map)
    would otherwise be misinterpreted.
    """
    if features.ndim != 3:
        raise ValueError(
            f"visualize_features_pca: expected 3-D (C, H, W) feature map, "
            f"got shape {features.shape}"
        )
    C, H, W = features.shape
    if C < 3:
        raise ValueError(
            f"visualize_features_pca: need at least 3 channels, got {C}"
        )
    feat = np.transpose(features, (1, 2, 0))  # (H, W, C)

    flat = feat.reshape(-1, C).astype(np.float32)
    flat -= flat.mean(axis=0, keepdims=True)

    # SVD-based PCA — only need the top-3 right singular vectors.
    # For very large feature maps, use a randomized projection as a
    # cheaper alternative.
    if flat.shape[0] > 200_000:
        rng = np.random.default_rng(seed=0)
        proj = rng.standard_normal((C, 3), dtype=np.float32)
        proj /= np.linalg.norm(proj, axis=0, keepdims=True) + 1e-8
        pcs = flat @ proj  # (N, 3)
    else:
        _u, _s, vt = np.linalg.svd(flat, full_matrices=False)
        pcs = flat @ vt[:3].T  # (N, 3)

    lo = pcs.min(axis=0, keepdims=True)
    hi = pcs.max(axis=0, keepdims=True)
    span = np.maximum(hi - lo, 1e-6)
    norm = (pcs - lo) / span
    rgb = (norm.clip(0.0, 1.0) * 255.0).astype(np.uint8).reshape(H, W, 3)
    bgr = rgb[:, :, ::-1].copy()
    return bgr


# ---------------------------------------------------------------------------
# Seg: 29-class palette
# ---------------------------------------------------------------------------

# Default Sapiens2 "dome29" palette (background + 28 body parts).  Generated
# deterministically with HSV evenly spaced around the hue circle so
# adjacent classes contrast well.  This avoids depending on
# ``sapiens.dense.visualizers.SegVisualizer`` at runtime (which pulls in
# matplotlib and a chain of optional helpers).
def _build_seg_palette(num_classes: int = 29) -> np.ndarray:
    palette = np.zeros((num_classes, 3), dtype=np.uint8)
    # 0 is background -> black
    for i in range(1, num_classes):
        h = int(180 * (i - 1) / max(1, num_classes - 1))
        hsv = np.uint8([[[h, 220, 230]]])
        bgr = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)[0, 0]
        palette[i] = bgr
    return palette


_SEG_PALETTE: Optional[np.ndarray] = None


def visualize_seg(
    image_bgr: np.ndarray,           # HxWx3 uint8 — original frame (for blend)
    pred_labels: np.ndarray,         # HxW int — argmax class indices
    *,
    alpha: float = 0.5,
    num_classes: int = 29,
) -> np.ndarray:
    """Blend a class-color overlay over the original image (BGR uint8).

    The overlay is generated from a deterministic HSV palette so users
    don't depend on the upstream visualizer module.
    """
    global _SEG_PALETTE
    if _SEG_PALETTE is None or _SEG_PALETTE.shape[0] != num_classes:
        _SEG_PALETTE = _build_seg_palette(num_classes)
    palette = _SEG_PALETTE

    if pred_labels.shape != image_bgr.shape[:2]:
        raise ValueError(
            "visualize_seg: pred_labels shape "
            f"{pred_labels.shape} != image shape {image_bgr.shape[:2]}"
        )
    if not 0.0 <= alpha <= 1.0:
        raise ValueError(f"visualize_seg: alpha must be in [0, 1], got {alpha}")

    labels_clipped = np.clip(pred_labels, 0, num_classes - 1).astype(np.int64)
    color = palette[labels_clipped]
    blended = (image_bgr.astype(np.float32) * (1.0 - alpha) +
               color.astype(np.float32) * alpha)
    return blended.clip(0, 255).astype(np.uint8)
