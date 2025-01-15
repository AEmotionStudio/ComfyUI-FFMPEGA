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

logger = logging.getLogger("FFMPEGA")


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
            },
            "hidden": {
                "mask_points_data": "STRING",
            },
        }

    RETURN_TYPES = ("STRING", "STRING", "IMAGE")
    RETURN_NAMES = ("image_path", "mask_points", "images")
    OUTPUT_TOOLTIPS = (
        "Absolute file path to the selected image. Connect to "
        "FFMPEGA Agent's image_path_a / image_path_b / … inputs.",
        "JSON-encoded point selection data from the Point Selector. "
        "Connect to FFMPEGA Agent's mask_points input for guided masking.",
        "Upstream IMAGE pass-through (or empty tensor if not connected).",
    )
    FUNCTION = "load_image_path"
    CATEGORY = "FFMPEGA"
    DESCRIPTION = (
        "Zero-memory image loader — outputs a file path STRING "
        "instead of an IMAGE tensor. Connect to FFMPEGA Agent's "
        "image_path slots. Uses ~0 MB for any number of images vs "
        "~6 MB per image with standard Load Image. Accepts optional "
        "upstream IMAGE and image_path inputs for chaining."
    )

    def load_image_path(
        self,
        image: str = "",
        mask_points_data: str = "",
        images=None,
        image_path=None,
        mask_points=None,
    ) -> dict:
        """Resolve the image path and return it plus UI preview data.

        If ``image_path`` is provided (upstream connection), it overrides
        the file-picker combo.  ``images`` is passed through to the new
        output slot.
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

        # --- Pass-through upstream IMAGE ---
        images_out = images if images is not None else torch.zeros(
            1, 64, 64, 3, dtype=torch.float32,
        )

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

        return {
            "ui": {
                "images": ui_images,
            },
            "result": (full_path, mask_points_data or "", images_out),
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
