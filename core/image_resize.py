"""Self-contained image-resize helper for the FFMPEGA loader nodes.

Replicates the core resize semantics of the KJNodes "Resize Image v2"
(``ImageResizeKJv2``) node for the common modes, without taking a runtime
dependency on KJNodes. Operates on ComfyUI BHWC IMAGE tensors (float32 in
[0, 1]) and optional BHW MASK tensors, keeping the mask aligned with the image.

Supported ``keep_proportion`` modes:
  - ``stretch`` : scale exactly to (width, height), ignoring aspect ratio.
  - ``resize``  : scale to fit inside (width, height), preserving aspect ratio.
  - ``pad``     : like ``resize``, then pad with ``pad_color`` to exactly
                  (width, height); placement controlled by ``crop_position``.
  - ``crop``    : crop to the target aspect ratio (placement via
                  ``crop_position``) then scale to (width, height).

A zero on either ``width`` or ``height`` derives that dimension from the
source aspect ratio.
"""

from __future__ import annotations

import logging

import torch

logger = logging.getLogger(__name__)

UPSCALE_METHODS = ["nearest-exact", "bilinear", "area", "bicubic", "lanczos"]
KEEP_PROPORTION = ["stretch", "resize", "pad", "crop"]
CROP_POSITIONS = ["center", "top", "bottom", "left", "right"]
RESIZE_DEVICES = ["cpu", "gpu"]


def resize_input_types() -> dict:
    """Return the optional ``INPUT_TYPES`` widgets for the resize toggle.

    Shared by the FFMPEGA image loader nodes so their resize controls stay
    identical. Spread into a node's ``optional`` dict.
    """
    return {
        "enable_resize": ("BOOLEAN", {
            "default": False,
            "label_on": "Resize: on",
            "label_off": "Resize: off",
            "tooltip": "Resize the output image (and mask) before returning.",
        }),
        "resize_width": ("INT", {
            "default": 512, "min": 0, "max": 8192, "step": 1,
            "tooltip": "Target width. 0 = derive from aspect ratio.",
        }),
        "resize_height": ("INT", {
            "default": 512, "min": 0, "max": 8192, "step": 1,
            "tooltip": "Target height. 0 = derive from aspect ratio.",
        }),
        "upscale_method": (UPSCALE_METHODS, {
            "default": "nearest-exact",
            "tooltip": "Interpolation method used when scaling.",
        }),
        "keep_proportion": (KEEP_PROPORTION, {
            "default": "resize",
            "tooltip": (
                "stretch: ignore aspect ratio. resize: fit inside w/h. "
                "pad: fit then pad to w/h. crop: crop to aspect then scale."
            ),
        }),
        "pad_color": ("STRING", {
            "default": "0, 0, 0",
            "tooltip": "Padding color as 'R, G, B' (0-255). Used by pad mode.",
        }),
        "crop_position": (CROP_POSITIONS, {
            "default": "center",
            "tooltip": "Anchor for crop/pad placement.",
        }),
        "divisible_by": ("INT", {
            "default": 2, "min": 0, "max": 512, "step": 1,
            "tooltip": "Round final dimensions down to a multiple of this (0/1 = off).",
        }),
        "resize_device": (RESIZE_DEVICES, {
            "default": "cpu",
            "tooltip": "Compute device for resizing. GPU does not support lanczos.",
        }),
    }


def _common_upscale(samples, width, height, upscale_method, crop):
    """Thin wrapper around ``comfy.utils.common_upscale``.

    ``samples`` is a BCHW tensor. Returns a BCHW tensor scaled to
    (height, width) using ``upscale_method`` (``nearest-exact``, ``bilinear``,
    ``area``, ``bicubic``, ``lanczos``, ``bislerp``).
    """
    import comfy.utils

    return comfy.utils.common_upscale(samples, width, height, upscale_method, crop)


def _parse_pad_color(pad_color: str) -> tuple[float, float, float]:
    """Parse a ``"R, G, B"`` string (0-255) into normalized 0..1 channels.

    Falls back to black on any parse error.
    """
    try:
        parts = [p.strip() for p in str(pad_color).split(",")]
        vals = [float(p) for p in parts if p != ""]
        if len(vals) == 1:
            vals = vals * 3
        if len(vals) < 3:
            vals = (vals + [0.0, 0.0, 0.0])[:3]
        return tuple(max(0.0, min(255.0, v)) / 255.0 for v in vals[:3])  # type: ignore[return-value]
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("image_resize: bad pad_color %r (%s); using black", pad_color, exc)
        return (0.0, 0.0, 0.0)


def resize_image_tensor(
    image: torch.Tensor,
    width: int,
    height: int,
    keep_proportion: str,
    upscale_method: str,
    divisible_by: int,
    pad_color: str,
    crop_position: str,
    device: str = "cpu",
    mask: torch.Tensor | None = None,
):
    """Resize a BHWC IMAGE tensor (and optional BHW MASK) in place of KJ v2.

    Returns ``(image, mask, out_width, out_height)``. Outputs are moved back to
    CPU. ``mask`` is returned unchanged (``None`` stays ``None``) but is scaled
    /cropped/padded to track the image when provided.
    """
    B, H, W, C = image.shape

    # Resolve device.
    if device == "gpu":
        if upscale_method == "lanczos":
            raise ValueError("Lanczos is not supported on the GPU")
        import comfy.model_management as mm

        torch_device = mm.get_torch_device()
    else:
        torch_device = torch.device("cpu")

    image = image.to(torch_device)
    if mask is not None:
        # Align an upstream mask to the source image size first.
        if mask.shape[-2:] != (H, W):
            mask = _common_upscale(
                mask.unsqueeze(1), W, H, "bilinear", crop="disabled"
            ).squeeze(1)
        mask = mask.to(torch_device)

    # --- Determine target dimensions ---
    pad_left = pad_right = pad_top = pad_bottom = 0

    if keep_proportion in ("resize", "pad"):
        if width == 0 and height == 0:
            new_width, new_height = W, H
        elif width == 0:
            ratio = height / H
            new_width = round(W * ratio)
            new_height = height
        elif height == 0:
            ratio = width / W
            new_width = width
            new_height = round(H * ratio)
        else:
            ratio = min(width / W, height / H)
            new_width = round(W * ratio)
            new_height = round(H * ratio)

        if keep_proportion == "pad":
            # Pad to the requested (width, height); position via crop_position.
            if crop_position == "top":
                pad_left = (width - new_width) // 2
                pad_right = width - new_width - pad_left
                pad_top = 0
                pad_bottom = height - new_height
            elif crop_position == "bottom":
                pad_left = (width - new_width) // 2
                pad_right = width - new_width - pad_left
                pad_top = height - new_height
                pad_bottom = 0
            elif crop_position == "left":
                pad_left = 0
                pad_right = width - new_width
                pad_top = (height - new_height) // 2
                pad_bottom = height - new_height - pad_top
            elif crop_position == "right":
                pad_left = width - new_width
                pad_right = 0
                pad_top = (height - new_height) // 2
                pad_bottom = height - new_height - pad_top
            else:  # center
                pad_left = (width - new_width) // 2
                pad_right = width - new_width - pad_left
                pad_top = (height - new_height) // 2
                pad_bottom = height - new_height - pad_top
            # Guard against negative pads if the source is larger.
            pad_left, pad_right = max(0, pad_left), max(0, pad_right)
            pad_top, pad_bottom = max(0, pad_top), max(0, pad_bottom)

        width = new_width
        height = new_height
    else:  # stretch / crop
        if width == 0:
            width = W
        if height == 0:
            height = H

    if divisible_by and divisible_by > 1:
        width = width - (width % divisible_by)
        height = height - (height % divisible_by)
        width = max(width, divisible_by)
        height = max(height, divisible_by)

    # --- Crop to target aspect ratio (crop mode) ---
    if keep_proportion == "crop":
        old_height = image.shape[-3]
        old_width = image.shape[-2]
        old_aspect = old_width / old_height
        new_aspect = width / height
        if old_aspect > new_aspect:
            crop_w = round(old_height * new_aspect)
            crop_h = old_height
        else:
            crop_w = old_width
            crop_h = round(old_width / new_aspect)

        if crop_position == "top":
            x = (old_width - crop_w) // 2
            y = 0
        elif crop_position == "bottom":
            x = (old_width - crop_w) // 2
            y = old_height - crop_h
        elif crop_position == "left":
            x = 0
            y = (old_height - crop_h) // 2
        elif crop_position == "right":
            x = old_width - crop_w
            y = (old_height - crop_h) // 2
        else:  # center
            x = (old_width - crop_w) // 2
            y = (old_height - crop_h) // 2

        image = image.narrow(-2, x, crop_w).narrow(-3, y, crop_h)
        if mask is not None:
            mask = mask.narrow(-1, x, crop_w).narrow(-2, y, crop_h)

    # --- Scale ---
    image = _common_upscale(
        image.movedim(-1, 1), width, height, upscale_method, crop="disabled"
    ).movedim(1, -1)
    if mask is not None:
        if upscale_method == "lanczos":
            mask = _common_upscale(
                mask.unsqueeze(1).repeat(1, 3, 1, 1),
                width, height, upscale_method, crop="disabled",
            ).movedim(1, -1)[:, :, :, 0]
        else:
            mask = _common_upscale(
                mask.unsqueeze(1), width, height, upscale_method, crop="disabled"
            ).squeeze(1)

    # --- Pad (pad mode) ---
    if keep_proportion == "pad" and (pad_left or pad_right or pad_top or pad_bottom):
        padded_width = width + pad_left + pad_right
        padded_height = height + pad_top + pad_bottom
        if divisible_by and divisible_by > 1:
            if padded_width % divisible_by:
                pad_right += divisible_by - (padded_width % divisible_by)
            if padded_height % divisible_by:
                pad_bottom += divisible_by - (padded_height % divisible_by)

        r, g, b = _parse_pad_color(pad_color)
        # F.pad on BHWC: pad the last two spatial dims per channel via channels.
        out = image.new_empty(
            (image.shape[0],
             height + pad_top + pad_bottom,
             width + pad_left + pad_right,
             image.shape[3]),
        )
        fill = image.new_tensor([r, g, b] + [0.0] * max(0, image.shape[3] - 3))
        out[:] = fill
        out[:, pad_top:pad_top + height, pad_left:pad_left + width, :] = image
        image = out
        if mask is not None:
            mout = mask.new_zeros(
                (mask.shape[0],
                 height + pad_top + pad_bottom,
                 width + pad_left + pad_right),
            )
            mout[:, pad_top:pad_top + height, pad_left:pad_left + width] = mask
            mask = mout

    out_h, out_w = image.shape[1], image.shape[2]
    image = image.cpu()
    if mask is not None:
        mask = mask.cpu()
    return image, mask, out_w, out_h
