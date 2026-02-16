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
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("image_path",)
    OUTPUT_TOOLTIPS = (
        "Absolute file path to the selected image. Connect to "
        "FFMPEGA Agent's image_path_a / image_path_b / … inputs.",
    )
    FUNCTION = "load_image_path"
    CATEGORY = "FFMPEGA"
    DESCRIPTION = (
        "Zero-memory image loader — outputs a file path STRING "
        "instead of an IMAGE tensor. Connect to FFMPEGA Agent's "
        "image_path slots. Uses ~0 MB for any number of images vs "
        "~6 MB per image with standard Load Image."
    )

    def load_image_path(self, image: str = "") -> dict:
        """Resolve the image path and return it plus UI preview data."""
        if not image:
            raise FileNotFoundError("No image selected")

        # Handle subfolder/filename format from ComfyUI
        if "/" in image or "\\" in image:
            parts = image.rsplit("/", 1) if "/" in image else image.rsplit("\\", 1)
            subfolder = parts[0]
            filename = parts[1]
        else:
            subfolder = ""
            filename = image

        input_dir = folder_paths.get_input_directory()
        full_path = os.path.join(input_dir, subfolder, filename) if subfolder else os.path.join(input_dir, filename)
        full_path = os.path.abspath(full_path)

        if not os.path.isfile(full_path):
            raise FileNotFoundError(f"Image not found: {full_path}")

        logger.info("LoadImagePath: %s", full_path)

        return {
            "ui": {
                "images": [{
                    "filename": filename,
                    "subfolder": subfolder,
                    "type": "input",
                }],
            },
            "result": (full_path,),
        }

    @classmethod
    def IS_CHANGED(cls, image: str = ""):
        if not image:
            return 0.0
        input_dir = folder_paths.get_input_directory()
        full_path = os.path.join(input_dir, image)
        if os.path.isfile(full_path):
            m = hashlib.sha256()
            m.update(full_path.encode())
            m.update(str(os.path.getmtime(full_path)).encode())
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
