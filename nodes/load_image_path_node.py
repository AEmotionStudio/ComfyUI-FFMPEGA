"""Load Image Path node for ComfyUI.

Zero-memory alternative to the standard Load Image node.  Instead of
decoding the image into a ~6 MB float32 IMAGE tensor, this node simply
outputs the file path as a STRING.  Connect the output to FFMPEGA Agent's
image_path_a / image_path_b / … slots so ffmpeg reads the file directly.

When processing 60 images, the tensor approach uses ~360 MB + conversion
overhead.  This node uses ~0 MB for any number of images.

Memory cost: ~0 MB regardless of image count or resolution.
"""

import hashlib
import logging
import os

import torch

import folder_paths

try:
    from ..core.image_resize import resize_image_tensor, resize_input_types as _resize_input_types
except ImportError:  # pragma: no cover - fallback for non-package import
    from core.image_resize import resize_image_tensor, resize_input_types as _resize_input_types  # type: ignore

logger = logging.getLogger("FFMPEGA")


def _postprocess_mask(mask_np, expand=0, feather=0, invert=False):
    """Apply grow/shrink, feather, and invert to a uint8 mask (0/255).

    Replicates the same logic used by LoadVideoPathNode so masks are
    consistent across image and video nodes.
    """
    import cv2
    import numpy as np

    if invert:
        mask_np = (255 - mask_np).astype(np.uint8)

    if expand > 0:
        kernel = cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE, (expand * 2 + 1, expand * 2 + 1),
        )
        mask_np = cv2.dilate(mask_np, kernel, iterations=1)
    elif expand < 0:
        kernel = cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE, (abs(expand) * 2 + 1, abs(expand) * 2 + 1),
        )
        mask_np = cv2.erode(mask_np, kernel, iterations=1)

    if feather > 0:
        k = feather * 2 + 1  # kernel must be odd
        mask_np = cv2.GaussianBlur(mask_np, (k, k), 0)

    return mask_np


class LoadImagePathNode:
    """Load an image by path — zero memory, no tensor decoding."""

    @classmethod
    def INPUT_TYPES(cls):
        input_dir = folder_paths.get_input_directory()
        files = sorted(
            f for f in os.listdir(input_dir)
            if f.lower().endswith((
                ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp",
                ".tiff", ".tif", ".svg",
            ))
        ) if os.path.isdir(input_dir) else []

        return {
            "required": {
                "image": (files, {
                    "image_upload": True,
                    "tooltip": (
                        "Select an image from ComfyUI's input directory "
                        "or upload a new one."
                    ),
                }),
            },
            "optional": {
                "images": ("IMAGE", {
                    "tooltip": (
                        "Optional upstream IMAGE input "
                        "(e.g. from another node). Passed through "
                        "as output."
                    ),
                }),
                "image_path": ("STRING", {
                    "forceInput": True,
                    "tooltip": (
                        "Optional upstream image path. Overrides "
                        "the file picker when connected."
                    ),
                }),
                "mask_points": ("STRING", {
                    "forceInput": True,
                    "tooltip": (
                        "Optional upstream mask_points pass-through. "
                        "When connected, overrides the locally drawn "
                        "mask points."
                    ),
                }),
                "mask": ("MASK", {
                    "tooltip": (
                        "Optional upstream MASK pass-through. "
                        "Forwarded as-is to the mask output."
                    ),
                }),
                **_resize_input_types(),
            },
            "hidden": {
                "mask_points_data": "STRING",
            },
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING", "IMAGE", "MASK")
    RETURN_NAMES = ("image_path", "mask_points", "mask_overlay_path", "images", "mask")
    OUTPUT_TOOLTIPS = (
        "Absolute file path to the selected image. Connect to "
        "FFMPEGA Agent's image_path_a / image_path_b / … inputs.",
        "JSON-encoded point selection data from the Point Selector. "
        "Connect to FFMPEGA Agent's mask_points input for guided masking.",
        "Path to a mask overlay preview image. "
        "Empty string when no mask is generated.",
        "Upstream IMAGE pass-through (or empty tensor if not connected).",
        "SAM3 segmentation mask from Point Selector clicks. "
        "Connect to any node accepting MASK input for compositing. "
        "Empty mask when no points are set.",
    )
    FUNCTION = "load_image_path"
    CATEGORY = "FFMPEGA"
    DESCRIPTION = (
        "Zero-memory image loader — outputs a file path STRING "
        "instead of an IMAGE tensor. Connect to FFMPEGA Agent's "
        "image_path slots. Uses ~0 MB for any number of images vs "
        "~6 MB per image with standard Load Image. Accepts optional "
        "upstream IMAGE and image_path inputs for chaining. "
        "Supports SAM3 point/draw/box masking via the Point Selector."
    )

    def load_image_path(
        self,
        image: str = "",
        mask_points_data: str = "",
        images=None,
        image_path=None,
        mask_points=None,
        mask=None,
        enable_resize: bool = False,
        resize_width: int = 512,
        resize_height: int = 512,
        upscale_method: str = "nearest-exact",
        keep_proportion: str = "resize",
        pad_color: str = "0, 0, 0",
        crop_position: str = "center",
        divisible_by: int = 2,
        resize_device: str = "cpu",
    ) -> dict:
        """Resolve the image path and return it plus UI preview data.

        If ``image_path`` is provided (upstream connection), it overrides
        the file-picker combo.  ``images`` is passed through to the new
        output slot.

        If ``mask_points_data`` contains valid JSON from the Point
        Selector, runs SAM3 mask generation and outputs the result
        as a MASK tensor.
        """
        # --- Determine the actual image path ---
        upstream = False

        # Upstream mask_points overrides locally drawn points
        if mask_points and isinstance(mask_points, str) and mask_points.strip():
            mask_points_data = mask_points.strip()
            logger.info("LoadImagePath: using upstream mask_points")

        if (
            image_path
            and isinstance(image_path, str)
            and image_path.strip()
        ):
            # Upstream connection overrides the file-picker
            full_path = image_path.strip()
            upstream = True
            logger.info(
                "LoadImagePath: using upstream image_path: %s", full_path,
            )

            if not os.path.isfile(full_path):
                raise FileNotFoundError(
                    f"Upstream image not found: {full_path}"
                )

            filename = os.path.basename(full_path)
            subfolder = ""
        else:
            if not image:
                raise FileNotFoundError("No image selected")

            # Handle subfolder/filename format from ComfyUI
            if "/" in image or "\\" in image:
                parts = (
                    image.rsplit("/", 1)
                    if "/" in image
                    else image.rsplit("\\", 1)
                )
                subfolder = parts[0]
                filename = parts[1]
            else:
                subfolder = ""
                filename = image

            input_dir = folder_paths.get_input_directory()
            full_path = (
                os.path.join(input_dir, subfolder, filename)
                if subfolder
                else os.path.join(input_dir, filename)
            )
            full_path = os.path.abspath(full_path)

            if not os.path.isfile(full_path):
                raise FileNotFoundError(f"Image not found: {full_path}")

        logger.info("LoadImagePath: %s", full_path)

        # --- Decode image into IMAGE tensor ---
        if images is not None:
            images_out = images
        else:
            try:
                from PIL import Image as _PILImg
                import numpy as _np
                _pil = _PILImg.open(full_path).convert("RGB")
                _arr = _np.array(_pil).astype(_np.float32) / 255.0
                images_out = torch.from_numpy(_arr).unsqueeze(0)  # (1,H,W,3)
            except Exception as _e:
                logger.warning("LoadImagePath: image decode failed: %s", _e)
                images_out = torch.zeros(1, 64, 64, 3, dtype=torch.float32)

        # --- Generate MASK output ---
        # Priority: upstream mask > SAM3 from points/draw > empty
        mask_overlay_path = ""

        if mask is not None:
            mask_out = mask
            logger.info("LoadImagePath: using upstream MASK (%s)", list(mask.shape))
        else:
            # Default empty mask — sized to image if we can read dimensions
            try:
                from PIL import Image as _PILImage
                with _PILImage.open(full_path) as _img:
                    _iw, _ih = _img.size
                mask_out = torch.zeros(1, _ih, _iw, dtype=torch.float32)
            except Exception:
                mask_out = torch.zeros(1, 64, 64, dtype=torch.float32)

            if mask_points_data and mask_points_data.strip():
                try:
                    import json as _json
                    import numpy as np

                    pt_data = _json.loads(mask_points_data)
                    if isinstance(pt_data, dict):
                        pt_mode = pt_data.get("mode", "points")

                        # Extract mask post-processing settings
                        mask_expand = int(pt_data.get("mask_expand", 0))
                        mask_feather = int(pt_data.get("mask_feather", 0))
                        mask_invert = bool(pt_data.get("mask_invert", False))
                        mask_threshold = float(pt_data.get("mask_threshold", 0.5))
                        mask_multi_object = bool(pt_data.get("mask_multi_object", False))
                        mask_edge_refine = bool(pt_data.get("mask_edge_refine", False))
                        mask_box = pt_data.get("box", None)

                        # ── Draw mode: user painted a mask directly ──
                        if pt_mode == "draw" and pt_data.get("mask_data"):
                            import base64
                            from io import BytesIO
                            from PIL import Image as PILImage

                            mask_b64 = pt_data["mask_data"]
                            mask_bytes = base64.b64decode(mask_b64)
                            mask_pil = PILImage.open(BytesIO(mask_bytes)).convert("L")

                            # Get image dimensions for resize
                            with PILImage.open(full_path) as ref_img:
                                img_w, img_h = ref_img.size

                            if mask_pil.size != (img_w, img_h):
                                mask_pil = mask_pil.resize(
                                    (img_w, img_h), PILImage.NEAREST,
                                )

                            mask_np = np.array(mask_pil)
                            logger.info(
                                "LoadImagePath: using DRAWN mask (%dx%d, coverage=%.1f%%)",
                                img_w, img_h,
                                (mask_np > 128).sum() / mask_np.size * 100,
                            )

                            # Post-process
                            mask_np = _postprocess_mask(
                                mask_np, mask_expand, mask_feather, mask_invert,
                            )

                            mask_float = mask_np.astype(np.float32) / 255.0
                            mask_out = torch.from_numpy(mask_float).unsqueeze(0)

                            # B&W mask overlay
                            import cv2
                            temp_dir = folder_paths.get_temp_directory()
                            os.makedirs(temp_dir, exist_ok=True)
                            bw_tmp = os.path.join(
                                temp_dir,
                                f"ffmpega_img_mask_bw_{os.getpid()}.png",
                            )
                            cv2.imwrite(bw_tmp, mask_np)
                            mask_overlay_path = bw_tmp
                            logger.info("LoadImagePath: drawn B&W mask: %s", bw_tmp)

                        # ── Point/box mode: SAM3-based masking ──
                        elif pt_mode in ("points", "box"):
                            pt_coords = pt_data.get("points", [])
                            pt_labels = pt_data.get("labels", [])
                            pt_w = int(pt_data.get("image_width", 0))
                            pt_h = int(pt_data.get("image_height", 0))

                            has_points = bool(pt_coords and pt_labels)
                            has_box = bool(mask_box)

                            if has_points or has_box:
                                try:
                                    try:
                                        from ..core.sam3_masker import mask_image_with_points
                                    except ImportError:
                                        from core.sam3_masker import mask_image_with_points  # type: ignore

                                    mask_result = mask_image_with_points(
                                        full_path, pt_coords, pt_labels,
                                        pt_w, pt_h, device="gpu",
                                        min_score=mask_threshold,
                                        multi_object=mask_multi_object,
                                        box=mask_box,
                                    )

                                    # Handle tuple return for multi-object
                                    per_obj_masks = None
                                    if isinstance(mask_result, tuple):
                                        mask_np, per_obj_masks = mask_result
                                    else:
                                        mask_np = mask_result

                                    # Apply GrabCut edge refinement if enabled
                                    if mask_edge_refine:
                                        try:
                                            try:
                                                from ..core.sam3_masker import refine_mask_grabcut
                                            except ImportError:
                                                from core.sam3_masker import refine_mask_grabcut  # type: ignore
                                            mask_np = refine_mask_grabcut(full_path, mask_np)
                                            if per_obj_masks:
                                                per_obj_masks = [
                                                    refine_mask_grabcut(full_path, m)
                                                    for m in per_obj_masks
                                                ]
                                        except Exception as re:
                                            logger.warning(
                                                "LoadImagePath: GrabCut refine failed: %s", re,
                                            )

                                    # Post-process
                                    mask_np = _postprocess_mask(
                                        mask_np, mask_expand, mask_feather, mask_invert,
                                    )

                                    mask_out = torch.from_numpy(
                                        mask_np.astype(np.float32) / 255.0
                                    ).unsqueeze(0)
                                    logger.info(
                                        "LoadImagePath: generated MASK from %d points "
                                        "(coverage=%.1f%%)",
                                        len(pt_coords),
                                        (mask_np > 128).sum() / mask_np.size * 100,
                                    )

                                    # Generate colored overlay preview
                                    try:
                                        import cv2
                                        from PIL import Image as PILImage

                                        orig_img = PILImage.open(full_path).convert("RGB")
                                        orig_np = np.array(orig_img)
                                        # BGR for cv2
                                        frame_bgr = cv2.cvtColor(orig_np, cv2.COLOR_RGB2BGR)

                                        try:
                                            try:
                                                from ..core.sam3_masker import _draw_masks_to_frame
                                            except ImportError:
                                                from core.sam3_masker import _draw_masks_to_frame  # type: ignore

                                            if per_obj_masks and len(per_obj_masks) > 1:
                                                masks_arr = np.array([
                                                    (m > 127).astype(np.uint8)
                                                    for m in per_obj_masks
                                                ])
                                                obj_ids = list(range(len(per_obj_masks)))
                                            else:
                                                masks_arr = np.array([
                                                    (mask_np > 127).astype(np.uint8)
                                                ])
                                                obj_ids = [0]

                                            overlay = _draw_masks_to_frame(
                                                frame_bgr, masks_arr, obj_ids,
                                            )
                                        except Exception:
                                            # Fallback: simple teal overlay
                                            overlay = frame_bgr.copy()
                                            mask_bool = mask_np > 127
                                            overlay[mask_bool] = (
                                                overlay[mask_bool] * 0.5 +
                                                np.array([170, 212, 0]) * 0.5
                                            ).astype(np.uint8)

                                        temp_dir = folder_paths.get_temp_directory()
                                        os.makedirs(temp_dir, exist_ok=True)
                                        overlay_tmp = os.path.join(
                                            temp_dir,
                                            f"ffmpega_img_mask_overlay_{os.getpid()}.png",
                                        )
                                        cv2.imwrite(overlay_tmp, overlay)
                                        mask_overlay_path = overlay_tmp
                                        logger.info(
                                            "LoadImagePath: colored overlay: %s",
                                            overlay_tmp,
                                        )
                                    except Exception as oe:
                                        logger.warning(
                                            "LoadImagePath: mask overlay failed: %s", oe,
                                        )

                                except Exception as e:
                                    logger.warning("LoadImagePath: SAM3 mask failed: %s", e)

                except Exception as e:
                    logger.warning("LoadImagePath: mask_points parse error: %s", e)

        # --- Build UI data ---
        if upstream:
            # For upstream paths, copy to temp so /view can serve it
            import shutil as _shutil

            temp_dir = folder_paths.get_temp_directory()
            os.makedirs(temp_dir, exist_ok=True)
            preview_name = f"ffmpega_lip_upstream_{os.getpid()}{os.path.splitext(full_path)[1]}"
            preview_path = os.path.join(temp_dir, preview_name)
            try:
                _shutil.copy2(full_path, preview_path)
            except Exception as e:
                logger.warning(
                    "LoadImagePath: upstream preview copy failed: %s", e,
                )
            ui_images = [{
                "filename": preview_name,
                "subfolder": "",
                "type": "temp",
            }]
        else:
            ui_images = [{
                "filename": filename,
                "subfolder": subfolder,
                "type": "input",
            }]

        # --- Optional resize of the IMAGE tensor (and aligned MASK) ---
        # image_path / mask_overlay_path outputs are left unchanged: the path
        # keeps pointing at the original file on disk.
        if enable_resize:
            try:
                images_out, mask_out, _rw, _rh = resize_image_tensor(
                    images_out,
                    width=resize_width,
                    height=resize_height,
                    keep_proportion=keep_proportion,
                    upscale_method=upscale_method,
                    divisible_by=divisible_by,
                    pad_color=pad_color,
                    crop_position=crop_position,
                    device=resize_device,
                    mask=mask_out,
                )
                logger.info("LoadImagePath: resized image to %dx%d", _rw, _rh)
            except Exception as _re:
                logger.warning("LoadImagePath: resize failed: %s", _re)

        return {
            "ui": {
                "images": ui_images,
            },
            "result": (full_path, mask_points_data or "", mask_overlay_path,
                       images_out, mask_out),
        }

    @classmethod
    def IS_CHANGED(
        cls, image: str = "", mask_points_data: str = "", **kwargs,
    ):
        # If upstream image_path is provided, hash it instead
        upstream_path = kwargs.get("image_path", "")
        if upstream_path and isinstance(upstream_path, str) and upstream_path.strip():
            path = upstream_path.strip()
            if os.path.isfile(path):
                m = hashlib.sha256()
                m.update(path.encode())
                m.update(str(os.path.getmtime(path)).encode())
                m.update((mask_points_data or "").encode())
                return m.hexdigest()
            return 0.0

        if not image:
            return 0.0
        input_dir = folder_paths.get_input_directory()
        full_path = os.path.join(input_dir, image)
        if os.path.isfile(full_path):
            m = hashlib.sha256()
            m.update(full_path.encode())
            m.update(str(os.path.getmtime(full_path)).encode())
            m.update((mask_points_data or "").encode())
            return m.hexdigest()
        return 0.0

    @classmethod
    def VALIDATE_INPUTS(cls, image: str = ""):
        if not image:
            return True
        input_dir = folder_paths.get_input_directory()
        full_path = os.path.join(input_dir, image)
        if not os.path.isfile(full_path):
            return f"Image not found: {full_path}"
        return True
