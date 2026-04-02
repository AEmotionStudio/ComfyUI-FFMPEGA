"""Save Image node for ComfyUI.

Image output node that takes a STRING image path OR an IMAGE tensor,
copies/saves the file to ComfyUI's output directory, and shows an
inline image preview.

Useful for saving and previewing mask overlays, extracted frames,
and other image outputs from the FFMPEGA pipeline.

Pipeline:  LoadVideoPath (mask_overlay_path) → Save Image (FFMPEGA)
           Any IMAGE output                  → Save Image (FFMPEGA)
"""

import glob
import json
import logging
import os
import shutil

import numpy as np
import torch

import folder_paths

logger = logging.getLogger("FFMPEGA")


class SaveImageNode:
    """Save / preview an image from its file path — zero memory cost."""

    def __init__(self):
        self.output_dir = folder_paths.get_output_directory()
        self.type = "output"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "filename_prefix": ("STRING", {
                    "default": "FFMPEGA",
                    "tooltip": (
                        "Prefix for the saved image filename. "
                        "Supports ComfyUI formatting like "
                        "%date:yyyy-MM-dd%."
                    ),
                }),
            },
            "optional": {
                "images": ("IMAGE", {
                    "tooltip": (
                        "Image tensor input. When connected, saves the "
                        "tensor directly as PNG. Takes priority over "
                        "image_path when both are provided."
                    ),
                }),
                "image_path": ("STRING", {
                    "forceInput": True,
                    "tooltip": (
                        "Path to an image file (e.g. mask_overlay_path "
                        "from Load Video Path, or any PNG/JPG path). "
                        "The file will be copied as-is to ComfyUI's "
                        "output directory."
                    ),
                }),
                "save_output": ("BOOLEAN", {
                    "default": True,
                    "label_on": "Save to Output",
                    "label_off": "Preview Only",
                    "tooltip": (
                        "When On, copies the image to ComfyUI's output "
                        "directory. When Off, shows the inline preview "
                        "without saving a permanent copy."
                    ),
                }),
                "overwrite": ("BOOLEAN", {
                    "default": False,
                    "tooltip": (
                        "If true, overwrite the output file if it "
                        "already exists. Otherwise, auto-increment "
                        "the filename counter."
                    ),
                }),
                "mask_points": ("STRING", {
                    "forceInput": True,
                    "tooltip": (
                        "Optional upstream mask_points pass-through. "
                        "Forwarded as-is to the mask_points output."
                    ),
                }),
                "mask": ("MASK", {
                    "tooltip": (
                        "Optional upstream MASK pass-through. "
                        "Forwarded as-is to the mask output."
                    ),
                }),
            },
            "hidden": {
                "prompt": "PROMPT",
                "extra_pnginfo": "EXTRA_PNGINFO",
            },
        }

    RETURN_TYPES = ("IMAGE", "STRING", "STRING", "MASK")
    RETURN_NAMES = ("image", "image_path", "mask_points", "mask")
    FUNCTION = "save_image"
    OUTPUT_NODE = True
    CATEGORY = "FFMPEGA"
    DESCRIPTION = (
        "Image output with inline preview. "
        "Accepts an IMAGE tensor or an image path (e.g. mask_overlay_path "
        "from Load Video Path). Saves to ComfyUI's output directory and "
        "shows a preview. Also outputs the IMAGE tensor and saved path "
        "for chaining with downstream nodes."
    )

    def save_image(
        self,
        image_path: str = "",
        filename_prefix: str = "FFMPEGA",
        save_output: bool = True,
        overwrite: bool = False,
        mask_points: str = "",
        mask=None,
        images=None,
        prompt=None,
        extra_pnginfo=None,
    ) -> dict:
        """Save image to output directory and return UI data for preview."""
        # Guard against empty / non-string prefix
        if (
            not filename_prefix
            or not isinstance(filename_prefix, str)
            or not filename_prefix.strip()
            or filename_prefix.strip().lower() in ("false", "true")
        ):
            filename_prefix = "FFMPEGA"

        empty_image = torch.zeros(1, 64, 64, 3, dtype=torch.float32)
        empty_mask = torch.zeros(1, 64, 64, dtype=torch.float32)

        has_tensor = (
            images is not None
            and hasattr(images, "shape")
            and images.shape[0] > 0
        )
        has_path = bool(image_path) and os.path.isfile(image_path)

        if not has_tensor and not has_path:
            return {
                "ui": {"images": [], "file_size": ["0 B"]},
                "result": (
                    empty_image,
                    "",
                    mask_points or "",
                    mask if mask is not None else empty_mask,
                ),
            }

        # --- If IMAGE tensor provided, save it directly as PNG ---
        if has_tensor:
            return self._save_from_tensor(
                images, filename_prefix, save_output, overwrite,
                mask_points, mask, prompt, extra_pnginfo,
            )

        # Determine output path
        ext = os.path.splitext(image_path)[1] or ".png"

        # Use ComfyUI's standard path resolution
        full_output_folder, filename, _counter, subfolder, _ = (
            folder_paths.get_save_image_path(
                filename_prefix, self.output_dir
            )
        )
        os.makedirs(full_output_folder, exist_ok=True)

        if overwrite:
            output_filename = f"{filename}{ext}"
        else:
            # Find next available counter
            pattern = os.path.join(full_output_folder, f"{filename}_*")
            existing = glob.glob(pattern)
            max_counter = 0
            for path in existing:
                basename = os.path.splitext(os.path.basename(path))[0]
                parts = basename.rsplit("_", 1)
                if len(parts) == 2 and parts[1].isdigit():
                    max_counter = max(max_counter, int(parts[1]))
            counter = max_counter + 1
            output_filename = f"{filename}_{counter:05}{ext}"

        output_path = os.path.join(full_output_folder, output_filename)

        # Copy the image file
        src = os.path.abspath(image_path)
        dst = os.path.abspath(output_path)

        if save_output:
            if src != dst:
                shutil.copy2(image_path, output_path)
                logger.info(
                    "SaveImage: copied %s → %s",
                    image_path, output_path,
                )
            else:
                logger.info(
                    "SaveImage: file already in output: %s", output_path,
                )

            # Embed workflow metadata into PNG
            self._embed_workflow_png(
                output_path, prompt, extra_pnginfo,
            )
        else:
            # Preview-only: copy to temp
            temp_dir = folder_paths.get_temp_directory()
            os.makedirs(temp_dir, exist_ok=True)
            preview_name = f"ffmpega_img_preview_{os.getpid()}{ext}"
            preview_path = os.path.join(temp_dir, preview_name)
            try:
                shutil.copy2(image_path, preview_path)
            except Exception as e:
                logger.warning("SaveImage: preview copy failed: %s", e)
            output_path = preview_path if os.path.isfile(preview_path) else image_path
            logger.info("SaveImage: preview-only mode")

        # File size display
        file_size = os.path.getsize(image_path)
        if file_size >= 1_048_576:
            size_str = f"{file_size / 1_048_576:.1f} MB"
        elif file_size >= 1024:
            size_str = f"{file_size / 1024:.1f} KB"
        else:
            size_str = f"{file_size} B"

        logger.info(
            "SaveImage: %s (%s)", os.path.basename(output_path), size_str,
        )

        # Load image as tensor
        image_tensor = self._load_image_tensor(output_path)

        # Build UI data — use ComfyUI's standard image preview format
        if save_output:
            image_ui = [{
                "filename": output_filename,
                "subfolder": subfolder,
                "type": self.type,
            }]
        else:
            image_ui = [{
                "filename": os.path.basename(output_path),
                "subfolder": "",
                "type": "temp",
            }]

        return {
            "ui": {
                "images": image_ui,
                "file_size": [size_str],
            },
            "result": (
                image_tensor,
                output_path,
                mask_points or "",
                mask if mask is not None else empty_mask,
            ),
        }

    def _save_from_tensor(
        self,
        images: torch.Tensor,
        filename_prefix: str,
        save_output: bool,
        overwrite: bool,
        mask_points: str,
        mask,
        prompt,
        extra_pnginfo,
    ) -> dict:
        """Save IMAGE tensor to output directory as PNG.

        Handles batched tensors (B, H, W, 3) — each frame in the batch
        is saved as a separate PNG with auto-incremented filenames.
        """
        from PIL import Image

        empty_mask = torch.zeros(1, 64, 64, dtype=torch.float32)

        # Resolve output folder
        full_output_folder, filename, _counter, subfolder, _ = (
            folder_paths.get_save_image_path(
                filename_prefix, self.output_dir
            )
        )
        os.makedirs(full_output_folder, exist_ok=True)

        ext = ".png"
        batch_size = images.shape[0]

        # Find the starting counter for auto-increment
        if overwrite:
            counter = 0
        else:
            pattern = os.path.join(full_output_folder, f"{filename}_*")
            existing = glob.glob(pattern)
            max_counter = 0
            for path in existing:
                basename = os.path.splitext(os.path.basename(path))[0]
                parts = basename.rsplit("_", 1)
                if len(parts) == 2 and parts[1].isdigit():
                    max_counter = max(max_counter, int(parts[1]))
            counter = max_counter + 1

        image_ui = []
        saved_paths = []
        total_size = 0

        for i in range(batch_size):
            if overwrite and batch_size == 1:
                output_filename = f"{filename}{ext}"
            else:
                output_filename = f"{filename}_{counter:05}{ext}"
                counter += 1

            output_path = os.path.join(full_output_folder, output_filename)

            # Convert tensor → PIL → save
            img_np = images[i].cpu().numpy()
            img_np = np.clip(img_np * 255.0, 0, 255).astype(np.uint8)
            img = Image.fromarray(img_np, mode="RGB")

            if save_output:
                img.save(output_path, compress_level=4)
                self._embed_workflow_png(output_path, prompt, extra_pnginfo)
                logger.info(
                    "SaveImage: saved tensor → %s (%dx%d)",
                    output_path, img.width, img.height,
                )
                image_ui.append({
                    "filename": output_filename,
                    "subfolder": subfolder,
                    "type": self.type,
                })
            else:
                temp_dir = folder_paths.get_temp_directory()
                os.makedirs(temp_dir, exist_ok=True)
                preview_name = f"ffmpega_img_preview_{os.getpid()}_{i}{ext}"
                preview_path = os.path.join(temp_dir, preview_name)
                img.save(preview_path, compress_level=4)
                output_path = preview_path
                logger.info("SaveImage: tensor preview-only mode (%d/%d)", i + 1, batch_size)
                image_ui.append({
                    "filename": os.path.basename(output_path),
                    "subfolder": "",
                    "type": "temp",
                })

            saved_paths.append(output_path)
            total_size += os.path.getsize(output_path)

        # File size display (total across all saved images)
        if total_size >= 1_048_576:
            size_str = f"{total_size / 1_048_576:.1f} MB"
        elif total_size >= 1024:
            size_str = f"{total_size / 1024:.1f} KB"
        else:
            size_str = f"{total_size} B"
        if batch_size > 1:
            size_str = f"{size_str} ({batch_size} images)"

        return {
            "ui": {
                "images": image_ui,
                "file_size": [size_str],
            },
            "result": (
                images,
                saved_paths[0] if saved_paths else "",
                mask_points or "",
                mask if mask is not None else empty_mask,
            ),
        }

    def _load_image_tensor(self, image_path: str) -> torch.Tensor:
        """Load image file as ComfyUI IMAGE tensor (B, H, W, 3)."""
        try:
            from PIL import Image

            img = Image.open(image_path)
            if img.mode == "RGBA":
                # Composite onto white background
                bg = Image.new("RGB", img.size, (255, 255, 255))
                bg.paste(img, mask=img.split()[3])
                img = bg
            elif img.mode == "L":
                # Grayscale → RGB
                img = img.convert("RGB")
            else:
                img = img.convert("RGB")

            arr = np.array(img, dtype=np.float32) / 255.0
            return torch.from_numpy(arr).unsqueeze(0)

        except Exception as e:
            logger.warning("SaveImage: image load failed: %s", e)
            return torch.zeros(1, 64, 64, 3, dtype=torch.float32)

    def _embed_workflow_png(
        self,
        image_path: str,
        prompt,
        extra_pnginfo,
    ) -> None:
        """Embed workflow metadata into a PNG file for drag-and-drop loading."""
        if prompt is None and extra_pnginfo is None:
            return
        if not image_path.lower().endswith(".png"):
            return

        try:
            from PIL import Image
            from PIL.PngImagePlugin import PngInfo

            img = Image.open(image_path)

            metadata = PngInfo()
            if prompt is not None:
                metadata.add_text("prompt", json.dumps(prompt))
            if extra_pnginfo is not None:
                for key in extra_pnginfo:
                    metadata.add_text(key, json.dumps(extra_pnginfo[key]))

            img.save(image_path, pnginfo=metadata, compress_level=4)
            logger.info(
                "SaveImage: workflow metadata embedded → %s",
                os.path.basename(image_path),
            )

        except Exception as e:
            logger.warning(
                "SaveImage: workflow embed failed: %s", e,
            )
