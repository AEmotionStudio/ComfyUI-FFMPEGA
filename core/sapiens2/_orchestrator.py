# coding: utf-8
"""Top-level orchestration for the Sapiens2 no-LLM mode.

Public entry points:

- :func:`run_sapiens2` — process an image or video and return the
  path to the rendered MP4 / PNG.
- :func:`cleanup` — release all VRAM held by Sapiens2 + DETR caches.
  Called by ``core._vram_utils.free_for_module`` when another
  synthesizer needs memory.

Per-task inference lives in helpers below.  Each helper accepts an
already-loaded model and returns a BGR uint8 visualization frame, so
the video loop in :func:`_process_video` stays uniform across tasks.
"""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
import torch
import torch.nn.functional as F

from . import _detector, _io, _models, _registry as reg, _render

log = logging.getLogger("ffmpega")


def _get_ffmpeg_bin() -> str:
    """Locate the ffmpeg binary bundled with FFMPEGA."""
    try:
        from ..bin_paths import get_ffmpeg_bin
    except ImportError:
        from core.bin_paths import get_ffmpeg_bin  # type: ignore
    return get_ffmpeg_bin()


# ---------------------------------------------------------------------------
# Per-task processors  (image BGR uint8 → visualization BGR uint8)
# ---------------------------------------------------------------------------

_FP8_DTYPES = (torch.float8_e4m3fn, torch.float8_e5m2)


def _model_compute_dtype(model) -> torch.dtype:
    """Return the dtype the model's *non-fp8* ops run in.

    For an fp8 model the backbone Linears are fp8 but everything else
    (norms, convs, head) is bf16, so inputs must be cast to bf16.  For the
    plain fp32 model this returns float32 (the cast becomes a no-op).
    """
    for p in model.parameters():
        if p.dtype not in _FP8_DTYPES:
            return p.dtype
    return torch.float32


def _prep_inputs(model, data: dict) -> torch.Tensor:
    """Pull ``inputs`` out of preprocessed *data* and cast to the model dtype."""
    return data["inputs"].to(_model_compute_dtype(model))


def _padding_size(
    image_bgr: np.ndarray, inputs: torch.Tensor, data_samples
) -> tuple[int, int, int, int]:
    """Return ``(left, right, top, bottom)`` aspect-ratio padding.

    Prefer the value packed into ``data_samples["meta"]`` (present for most
    sizes), but reconstruct it when absent — the 5B ``normal`` config omits
    ``padding_size`` from its ``NormalPackInputs.meta_keys`` even though the
    resize transform computes it.  The formula mirrors upstream
    ``NormalResizePadImage._resize_maintain_aspect_ratio``: resize to fit the
    1024×768 target keeping aspect ratio, then centre-pad the remainder.
    """
    try:
        ps = data_samples["meta"].get("padding_size")
    except (KeyError, TypeError, AttributeError):
        ps = None
    if ps is not None:
        return tuple(int(x) for x in ps)  # type: ignore[return-value]

    orig_h, orig_w = image_bgr.shape[:2]
    target_h, target_w = int(inputs.shape[2]), int(inputs.shape[3])
    scale = min(target_w / orig_w, target_h / orig_h)
    new_w, new_h = int(orig_w * scale), int(orig_h * scale)
    pad_w, pad_h = target_w - new_w, target_h - new_h
    left, top = pad_w // 2, pad_h // 2
    return left, pad_w - left, top, pad_h - top


def _process_dense_seg(model, image_bgr: np.ndarray, *, alpha: float) -> np.ndarray:
    data = model.pipeline(dict(img=image_bgr))
    data = model.data_preprocessor(data)
    inputs = _prep_inputs(model, data)
    with torch.no_grad():
        seg_logits = model(inputs)
    seg_logits = F.interpolate(
        seg_logits, size=image_bgr.shape[:2], mode="bilinear",
    )
    pred = seg_logits.argmax(dim=1).cpu().numpy().squeeze(0)
    return _render.visualize_seg(image_bgr, pred, alpha=alpha)


def _process_dense_normal(model, image_bgr: np.ndarray) -> np.ndarray:
    data = model.pipeline(dict(img=image_bgr))
    data = model.data_preprocessor(data)
    inputs = _prep_inputs(model, data)
    data_samples = data["data_samples"]

    with torch.no_grad():
        normal = model(inputs)
        normal = normal / torch.norm(normal, dim=1, keepdim=True).clamp(min=1e-8)

    pad_left, pad_right, pad_top, pad_bottom = _padding_size(
        image_bgr, inputs, data_samples
    )
    normal = normal[
        :, :,
        pad_top : inputs.shape[2] - pad_bottom,
        pad_left : inputs.shape[3] - pad_right,
    ]
    normal = F.interpolate(
        normal, size=(image_bgr.shape[0], image_bgr.shape[1]),
        mode="bilinear", align_corners=False,
    )
    normal_np = normal.squeeze(0).float().cpu().numpy().transpose(1, 2, 0)
    return _render.visualize_normals(normal_np)


def _process_dense_pointmap(model, image_bgr: np.ndarray) -> np.ndarray:
    data = model.pipeline(dict(img=image_bgr))
    data = model.data_preprocessor(data)
    inputs = _prep_inputs(model, data)
    data_samples = data["data_samples"]

    with torch.no_grad():
        out = model(inputs)
    # Pointmap heads return (B, 3, H, W) — x, y, z in camera space.
    if isinstance(out, (list, tuple)):
        # Some configs additionally return a scale; we only need the map.
        out = out[0]

    pad_left, pad_right, pad_top, pad_bottom = _padding_size(
        image_bgr, inputs, data_samples
    )
    out = out[
        :, :,
        pad_top : inputs.shape[2] - pad_bottom,
        pad_left : inputs.shape[3] - pad_right,
    ]
    out = F.interpolate(
        out, size=(image_bgr.shape[0], image_bgr.shape[1]),
        mode="bilinear", align_corners=False,
    )
    pmap = out.squeeze(0).float().cpu().numpy().transpose(1, 2, 0)
    return _render.visualize_pointmap_z(pmap)


def _process_dense_matting(model, image_bgr: np.ndarray) -> np.ndarray:
    data = model.pipeline(dict(img=image_bgr))
    data = model.data_preprocessor(data)
    inputs = _prep_inputs(model, data)

    with torch.no_grad():
        outputs = model(inputs)
    outputs = F.interpolate(
        outputs, size=(image_bgr.shape[0], image_bgr.shape[1]),
        mode="bilinear", align_corners=False,
    )
    outputs = outputs.squeeze(0).float().cpu().numpy()
    fgr_rgb = outputs[0:3].clip(0, 1).transpose(1, 2, 0)
    alpha = outputs[3].clip(0, 1)
    composite, _alpha_vis = _render.composite_matting(image_bgr, fgr_rgb, alpha)
    return composite


def _process_pose(
    model,
    image_bgr: np.ndarray,
    *,
    device: torch.device,
    bbox_thr: float,
    nms_thr: float,
    kpt_thr: float,
    radius: int,
    thickness: int,
) -> np.ndarray:
    bboxes = _detector.detect_persons(
        image_bgr, device=device, bbox_thr=bbox_thr, nms_thr=nms_thr,
    )
    if bboxes.size == 0:
        return image_bgr.copy()

    inputs_list = []
    samples_list = []
    for bbox in bboxes:
        info = dict(img=image_bgr)
        info["bbox"] = bbox[None]
        info["bbox_score"] = np.ones(1, dtype=np.float32)
        data = model.pipeline(info)
        data = model.data_preprocessor(data)
        inputs_list.append(data["inputs"])
        samples_list.append(data["data_samples"])
    inputs = torch.cat(inputs_list, dim=0)

    with torch.no_grad():
        pred = model(inputs)
        flip_test = bool(getattr(model.cfg.val_cfg, "get", lambda *_: False)("flip_test", False)) \
            if getattr(model.cfg, "val_cfg", None) is not None else False
        if flip_test:
            pred_f = model(inputs.flip(-1)).flip(-1)
            flip_indices = model.pose_metainfo["flip_indices"]
            if len(flip_indices) == pred_f.shape[1]:
                pred = (pred + pred_f[:, flip_indices]) / 2.0

    pred_np = pred.cpu().numpy()

    keypoints, scores = [], []
    for i, samples in enumerate(samples_list):
        kpts_i, scores_i = model.codec.decode(pred_np[i])
        input_size = samples["meta"]["input_size"]
        bbox_center = samples["meta"]["bbox_center"]
        bbox_scale = samples["meta"]["bbox_scale"]
        kpts_i = kpts_i / input_size * bbox_scale + bbox_center - 0.5 * bbox_scale
        keypoints.append(kpts_i[0])
        scores.append(scores_i[0])

    image_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
    vis_rgb = _render.visualize_keypoints(
        image_rgb,
        keypoints=keypoints,
        keypoints_visible=[np.ones_like(s) > 0 for s in scores],
        keypoint_scores=scores,
        radius=radius,
        thickness=thickness,
        kpt_thr=kpt_thr,
        skeleton=model.pose_metainfo.get("skeleton_links"),
        kpt_color=model.pose_metainfo.get("keypoint_colors"),
        link_color=model.pose_metainfo.get("skeleton_link_colors"),
    )
    return cv2.cvtColor(vis_rgb, cv2.COLOR_RGB2BGR)


def _process_pretrain(
    model,
    image_bgr: np.ndarray,
    *,
    input_resolution: tuple[int, int],
    device: torch.device,
) -> np.ndarray:
    """Run the standalone backbone and PCA-visualize the features."""
    H_in, W_in = input_resolution
    img_resized = cv2.resize(image_bgr, (W_in, H_in), interpolation=cv2.INTER_AREA)
    rgb = cv2.cvtColor(img_resized, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0

    # ImageNet normalization (matches sapiens recommendation).
    mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
    std = np.array([0.229, 0.224, 0.225], dtype=np.float32)
    rgb = (rgb - mean) / std

    tensor = torch.from_numpy(rgb.transpose(2, 0, 1))[None].to(device)
    if next(model.parameters()).dtype == torch.float16:
        tensor = tensor.half()

    with torch.no_grad():
        out = model(tensor)

    # Backbone is built with out_type="featmap" so it returns a tuple of
    # (B, C, h, w) tensors (one per out_indices entry — default is the
    # final layer only).  Fall back to manual reshape only if some
    # downstream change reverts to the raw token output.
    if isinstance(out, (list, tuple)):
        out = out[0]
    if out.dim() == 4:
        feat = out
    elif out.dim() == 3:
        # (B, N, C) — strip leading non-spatial tokens (CLS + registers).
        B, N, C = out.shape
        h = H_in // 16
        w = W_in // 16
        expected_spatial = h * w
        extra = N - expected_spatial
        if extra < 0 or extra > 32:
            raise RuntimeError(
                f"Sapiens2 pretrain: unexpected token count {N} "
                f"(spatial={expected_spatial}, extras={extra}) for "
                f"H={H_in} W={W_in} patch=16"
            )
        spatial = out[:, extra:, :]
        feat = spatial.transpose(1, 2).reshape(B, C, h, w)
    else:
        raise RuntimeError(
            f"Sapiens2 pretrain: unexpected backbone output shape {out.shape}"
        )

    feat_np = feat.squeeze(0).float().cpu().numpy()  # (C, h, w)
    vis_small = _render.visualize_features_pca(feat_np)
    return cv2.resize(
        vis_small, (image_bgr.shape[1], image_bgr.shape[0]),
        interpolation=cv2.INTER_NEAREST,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def cleanup() -> None:
    """Release all Sapiens2-held VRAM.  Called from ``_vram_utils``."""
    _models.evict()
    _detector.evict()


def _load_for_task(
    task: str, size: str, precision: str = "auto"
) -> _models.LoadedModel:
    if task == "pose":
        return _models.load_pose_model(task, size)
    if task in reg.DENSE_TASKS:
        return _models.load_dense_model(task, size, precision=precision)
    if task == "pretrain":
        return _models.load_pretrain_backbone(size)
    raise ValueError(f"Sapiens2: unknown task {task!r}")


def _run_one_frame(
    task: str,
    loaded: _models.LoadedModel,
    image_bgr: np.ndarray,
    *,
    device: torch.device,
    seg_alpha: float,
    pose_bbox_thr: float,
    pose_nms_thr: float,
    pose_kpt_thr: float,
    pose_radius: int,
    pose_thickness: int,
) -> np.ndarray:
    if task == "seg":
        return _process_dense_seg(loaded.model, image_bgr, alpha=seg_alpha)
    if task == "normal":
        return _process_dense_normal(loaded.model, image_bgr)
    if task == "pointmap":
        return _process_dense_pointmap(loaded.model, image_bgr)
    if task == "matting":
        return _process_dense_matting(loaded.model, image_bgr)
    if task == "pose":
        return _process_pose(
            loaded.model, image_bgr,
            device=device,
            bbox_thr=pose_bbox_thr,
            nms_thr=pose_nms_thr,
            kpt_thr=pose_kpt_thr,
            radius=pose_radius,
            thickness=pose_thickness,
        )
    if task == "pretrain":
        if loaded.input_resolution is None:
            raise RuntimeError(
                "Sapiens2 pretrain: cached model missing input_resolution"
            )
        return _process_pretrain(
            loaded.model, image_bgr,
            input_resolution=loaded.input_resolution,
            device=device,
        )
    raise ValueError(f"Sapiens2: unknown task {task!r}")


def run_sapiens2(
    input_path: str,
    *,
    task: str = "pose",
    size: str = "1b",
    precision: str = "auto",
    seg_alpha: float = 0.5,
    pose_bbox_thr: float = 0.3,
    pose_nms_thr: float = 0.3,
    pose_kpt_thr: float = 0.3,
    pose_radius: int = 6,
    pose_thickness: int = 4,
    crf: int = 18,
    preset: str = "medium",
) -> str:
    """Run Sapiens2 on ``input_path`` (image or video).

    Returns the path to a rendered PNG (image input) or MP4 (video
    input).  The caller is responsible for moving/copying the file to
    its final destination — output is written to a temp location.

    Raises:
        FileNotFoundError: if ``input_path`` does not exist or the
            checkpoint cannot be obtained.
        ValueError:        if ``task`` or ``size`` is unknown or
            ``(task, size)`` has no released checkpoint.
        ImportError:       if the ``sapiens`` package is not installed.
        RuntimeError:      for ffmpeg/encode errors or model-runtime
            failures.
    """
    # ---- validate inputs ----
    if not isinstance(input_path, str) or not input_path:
        raise ValueError("Sapiens2: input_path must be a non-empty string")
    if not os.path.isfile(input_path):
        raise FileNotFoundError(f"Sapiens2: input file not found: {input_path}")

    if task not in reg.TASKS:
        raise ValueError(
            f"Sapiens2: unknown task {task!r}.  Valid tasks: {list(reg.TASKS)}"
        )
    reg.validate_task_size(task, size)
    if not 0.0 <= seg_alpha <= 1.0:
        raise ValueError(f"Sapiens2: seg_alpha must be in [0, 1], got {seg_alpha}")
    if pose_radius < 1 or pose_thickness < 1:
        raise ValueError(
            "Sapiens2: pose_radius/pose_thickness must be >= 1"
        )

    # ---- load model + figure out device ----
    loaded = _load_for_task(task, size, precision)
    device = next(loaded.model.parameters()).device

    ffmpeg_bin = _get_ffmpeg_bin()
    is_video = _io.is_video_path(input_path)
    is_image = _io.is_image_path(input_path)
    if not is_video and not is_image:
        # Try video first; fall back to image.
        is_video = True

    # ---- image path ----
    if is_image:
        image_bgr = cv2.imread(input_path)
        if image_bgr is None:
            raise RuntimeError(f"Sapiens2: cv2.imread failed for {input_path}")
        vis = _run_one_frame(
            task, loaded, image_bgr,
            device=device,
            seg_alpha=seg_alpha,
            pose_bbox_thr=pose_bbox_thr,
            pose_nms_thr=pose_nms_thr,
            pose_kpt_thr=pose_kpt_thr,
            pose_radius=pose_radius,
            pose_thickness=pose_thickness,
        )
        suffix = f"_sapiens2_{task}.png"
        fd, out_path = tempfile.mkstemp(suffix=suffix)
        os.close(fd)
        if not cv2.imwrite(out_path, vis):
            raise RuntimeError(
                f"Sapiens2: cv2.imwrite failed for {out_path}"
            )
        return out_path

    # ---- video path ----
    cap, fps, _w, _h, frame_count = _io.open_video(input_path)
    cap.release()  # we iterate via iter_video_frames

    fd, out_path = tempfile.mkstemp(suffix=f"_sapiens2_{task}.mp4")
    os.close(fd)

    with _io.FrameSink(prefix=f"sapiens2_{task}_") as sink:
        for i, frame_bgr in enumerate(_io.iter_video_frames(input_path)):
            if (i + 1) % 50 == 0 or i == 0:
                log.info(
                    "[Sapiens2] %s/%s frame %d/%s",
                    task, size, i + 1,
                    frame_count if frame_count > 0 else "?",
                )
            try:
                vis = _run_one_frame(
                    task, loaded, frame_bgr,
                    device=device,
                    seg_alpha=seg_alpha,
                    pose_bbox_thr=pose_bbox_thr,
                    pose_nms_thr=pose_nms_thr,
                    pose_kpt_thr=pose_kpt_thr,
                    pose_radius=pose_radius,
                    pose_thickness=pose_thickness,
                )
            except torch.cuda.OutOfMemoryError as exc:
                # Free everything and re-raise with a helpful hint.
                cleanup()
                raise RuntimeError(
                    f"Sapiens2: out of VRAM at frame {i} running task='{task}' "
                    f"size='{size}'.  Try a smaller size (e.g. 0.4b) or close "
                    f"other GPU-bound apps.  Original error: {exc}"
                ) from exc
            sink.add(vis)
        sink.encode(out_path, fps=fps, ffmpeg_bin=ffmpeg_bin, crf=crf, preset=preset)

    return out_path
