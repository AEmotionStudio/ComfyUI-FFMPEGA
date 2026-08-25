# coding: utf-8
"""DETR person detector for the Sapiens2 pose pipeline.

Wraps ``transformers.DetrForObjectDetection`` for the
``facebook/detr-resnet-101-dc5`` checkpoint that the upstream pose vis
tool uses.  Kept in its own module so the dense / pretrain code paths
don't pay the import cost.

The detector cache is a separate single-slot from the main model cache:
people typically run multiple pose jobs back-to-back, and the detector
weights are independent of the Sapiens2 backbone size.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import numpy as np
import torch

from . import _registry as reg

log = logging.getLogger("ffmpega")

# Upstream HF repo for the DETR detector.  Apache 2.0 — no need to mirror.
_DETR_REPO = "facebook/detr-resnet-101-dc5"


@dataclass
class LoadedDetector:
    processor: object
    model: object
    device: torch.device


_detector: Optional[LoadedDetector] = None


def evict() -> None:
    """Release the cached detector + run gc/empty_cache."""
    global _detector
    if _detector is None:
        return
    log.info("[Sapiens2] Unloading DETR person detector")
    try:
        _detector.model.to("cpu")
    except Exception:
        pass
    _detector = None
    import gc
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


def _require_downloads_allowed() -> None:
    try:
        from ..model_manager import require_downloads_allowed
    except ImportError:
        from core.model_manager import require_downloads_allowed  # type: ignore
    # Re-use the pose key — DETR is only used for pose.
    require_downloads_allowed(reg.MODEL_MANAGER_KEY["pose"])


def load_detector(device: torch.device) -> LoadedDetector:
    """Load (or reuse) the DETR detector on ``device``."""
    global _detector
    if _detector is not None and _detector.device == device:
        return _detector

    try:
        from transformers import DetrForObjectDetection, DetrImageProcessor
    except ImportError as exc:
        raise ImportError(
            "Sapiens2 pose requires the 'transformers' package.  It "
            "should already be present in the ComfyUI venv."
        ) from exc

    # Pre-cache to the same directory the rest of FFMPEGA uses, so users
    # who copy the model folder around get the detector too.
    cache_dir = reg.detector_cache_dir()

    log.info(
        "[Sapiens2] Loading DETR person detector (%s) on %s",
        _DETR_REPO, device,
    )
    _require_downloads_allowed()
    try:
        processor = DetrImageProcessor.from_pretrained(
            _DETR_REPO, cache_dir=str(cache_dir),
        )
        model = DetrForObjectDetection.from_pretrained(
            _DETR_REPO, cache_dir=str(cache_dir),
        ).eval().to(device)
    except Exception as exc:
        raise RuntimeError(
            f"Sapiens2 pose: could not load DETR detector ({_DETR_REPO}) "
            f"— {exc}"
        ) from exc

    _detector = LoadedDetector(processor=processor, model=model, device=device)
    return _detector


def _nms(bboxes: np.ndarray, iou_thr: float) -> np.ndarray:
    """Vanilla NMS on (N, 5) [x1, y1, x2, y2, score] boxes.

    Returns the indices kept after suppression, sorted by score desc.
    Vendored so we don't depend on ``sapiens.pose.evaluators`` (which
    pulls in the full pose runtime).
    """
    if bboxes.size == 0:
        return np.empty((0,), dtype=np.int64)

    x1, y1, x2, y2, scores = (bboxes[:, i] for i in range(5))
    areas = (x2 - x1).clip(min=0) * (y2 - y1).clip(min=0)
    order = scores.argsort()[::-1]

    keep: list[int] = []
    while order.size > 0:
        i = order[0]
        keep.append(int(i))
        if order.size == 1:
            break
        xx1 = np.maximum(x1[i], x1[order[1:]])
        yy1 = np.maximum(y1[i], y1[order[1:]])
        xx2 = np.minimum(x2[i], x2[order[1:]])
        yy2 = np.minimum(y2[i], y2[order[1:]])
        inter = (xx2 - xx1).clip(min=0) * (yy2 - yy1).clip(min=0)
        union = areas[i] + areas[order[1:]] - inter
        iou = inter / np.maximum(union, 1e-6)
        order = order[1:][iou <= iou_thr]

    return np.asarray(keep, dtype=np.int64)


def detect_persons(
    image_bgr: np.ndarray,
    *,
    device: torch.device,
    bbox_thr: float = 0.3,
    nms_thr: float = 0.3,
) -> np.ndarray:
    """Return person bounding boxes ``(N, 4)`` as ``[x1, y1, x2, y2]``.

    If no person is detected, returns a single full-image box so the
    pose stage still produces an output (matches upstream behavior).
    """
    if image_bgr.ndim != 3 or image_bgr.shape[2] != 3:
        raise ValueError(
            f"detect_persons: expected HxWx3 BGR, got shape {image_bgr.shape}"
        )

    det = load_detector(device)
    # transformers' DETR processor expects RGB.
    image_rgb = image_bgr[:, :, ::-1].copy()

    import cv2  # noqa: F401  # type: ignore[import-not-found]
    from PIL import Image
    pil = Image.fromarray(image_rgb)

    inputs = det.processor(images=pil, return_tensors="pt").to(device)
    with torch.no_grad():
        outputs = det.model(**inputs)
    target_sizes = torch.tensor([image_rgb.shape[:2]], device=device)
    results = det.processor.post_process_object_detection(
        outputs, target_sizes=target_sizes, threshold=bbox_thr,
    )[0]

    # COCO person class id = 1.
    person_mask = results["labels"] == 1
    boxes = results["boxes"][person_mask].cpu().numpy()
    scores = results["scores"][person_mask].cpu().numpy().reshape(-1, 1)
    if boxes.size == 0:
        H, W = image_rgb.shape[:2]
        return np.array([[0, 0, W - 1, H - 1]], dtype=np.float32)

    bboxes = np.concatenate([boxes, scores], axis=1)  # (N, 5)
    keep = _nms(bboxes, nms_thr)
    return bboxes[keep, :4].astype(np.float32)
