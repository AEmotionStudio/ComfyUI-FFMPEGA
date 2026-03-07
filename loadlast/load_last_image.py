"""
Load Last Image node for ComfyUI.

Automatically loads the most recently created image(s) from the current
or previous workflow execution, with grid/side-by-side outputs, dedup,
pin/lock, diff overlay, captions, and metadata passthrough.
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime
from typing import Optional

import numpy as np
import torch
import torch.nn.functional as F

from .discovery.filesystem import FilesystemScanner, get_default_directories
from .discovery.execution_hook import ImageExecutionCache
from .processing.captions import format_caption, render_caption, render_captions_on_grid
from .processing.dedup import compute_pixel_hash, is_duplicate
from .processing.diff import compose_diff
from .processing.grid import compose_grid
from .processing.metadata import extract_png_metadata
from .processing.sidebyside import compose_side_by_side

logger = logging.getLogger(__name__)


class LoadLastImage:
    """
    Automatically load the most recently generated image(s).

    Uses a dual discovery strategy:
    1. Execution hook (intercepts IMAGE outputs from the pipeline)
    2. Filesystem fallback (scans output/temp directories by mtime)
    """

    CATEGORY = "image"
    FUNCTION = "load"
    OUTPUT_NODE = False

    RETURN_TYPES = (
        "IMAGE", "MASK", "IMAGE", "IMAGE", "IMAGE",
        "INT", "INT", "INT", "INT",
        "STRING", "STRING", "STRING",
        "BOOLEAN",
    )
    RETURN_NAMES = (
        "IMAGE", "MASK", "GRID_IMAGE", "SIDE_BY_SIDE", "DIFF_IMAGE",
        "width", "height", "batch_count", "iteration",
        "metadata_prompt", "metadata_seed", "metadata_workflow",
        "RING_BUFFER_FULL",
    )

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "refresh_mode": (["auto", "manual"], {
                    "default": "auto",
                    "tooltip": "auto: reload on every queue. manual: only reload when triggered.",
                }),
                "batch_size": ("INT", {
                    "default": 1,
                    "min": 1,
                    "max": 9999,
                    "step": 1,
                    "tooltip": "Number of recent images to load as a batch. 1 = most recent only.",
                }),
                "grid_columns": ("INT", {
                    "default": 2,
                    "min": 1,
                    "max": 8,
                    "step": 1,
                    "tooltip": "Number of columns in the grid output layout.",
                }),
                "grid_padding": ("INT", {
                    "default": 4,
                    "min": 0,
                    "max": 32,
                    "step": 1,
                    "tooltip": "Pixel gap between grid cells and side-by-side images.",
                }),
                "skip_duplicates": ("BOOLEAN", {
                    "default": True,
                    "tooltip": "Skip consecutive identical images to avoid wasting batch slots.",
                }),
                "pin_index": ("INT", {
                    "default": 0,
                    "min": 0,
                    "max": 9999,
                    "step": 1,
                    "tooltip": "Pin a specific iteration as the output. 0 = disabled (auto-load latest).",
                }),
                "diff_mode": (["heatmap", "overlay", "side_by_side_diff"], {
                    "default": "heatmap",
                    "tooltip": "Diff visualization mode between most recent and previous image.",
                }),
                "diff_sensitivity": ("FLOAT", {
                    "default": 1.0,
                    "min": 0.1,
                    "max": 5.0,
                    "step": 0.1,
                    "tooltip": "Multiplier on diff brightness. Higher = more visible subtle changes.",
                }),
                "show_captions": ("BOOLEAN", {
                    "default": False,
                    "tooltip": "Burn caption text onto grid and side-by-side outputs.",
                }),
                "caption_format": ("STRING", {
                    "default": "#{iteration} | {timestamp} | seed:{seed}",
                    "tooltip": "Caption template. Tokens: {iteration}, {timestamp}, {seed}, {index}, {filename}",
                }),
                "ring_buffer_size": ("INT", {
                    "default": 0,
                    "min": 0,
                    "max": 64,
                    "step": 1,
                    "tooltip": "Ring buffer mode: fixed-size circular batch for AnimateDiff. 0 = disabled.",
                }),
            },
            "optional": {
                "source_folder": ("STRING", {
                    "default": "",
                    "tooltip": "Optional custom folder path to scan. Leave empty for default output/temp.",
                }),
                "filename_filter": ("STRING", {
                    "default": "",
                    "tooltip": "Optional prefix filter (e.g., 'ComfyUI_' to only match default outputs).",
                }),
            },
            "hidden": {
                "prompt": "PROMPT",
                "extra_pnginfo": "EXTRA_PNGINFO",
            },
        }

    @classmethod
    def IS_CHANGED(cls, refresh_mode="auto", **kwargs):
        if refresh_mode == "auto":
            cache = ImageExecutionCache.get_instance()
            return f"{cache.iteration_counter}_{time.time()}"
        return ""

    def load(
        self,
        refresh_mode: str = "auto",
        batch_size: int = 1,
        grid_columns: int = 2,
        grid_padding: int = 4,
        skip_duplicates: bool = True,
        pin_index: int = 0,
        diff_mode: str = "heatmap",
        diff_sensitivity: float = 1.0,
        show_captions: bool = False,
        caption_format: str = "#{iteration} | {timestamp} | seed:{seed}",
        ring_buffer_size: int = 0,
        source_folder: str = "",
        filename_filter: str = "",
        prompt=None,
        extra_pnginfo=None,
    ):
        """Main execution function."""
        cache = ImageExecutionCache.get_instance()
        scanner = FilesystemScanner()

        # --- Determine which directories to scan ---
        scan_dirs = get_default_directories()
        if source_folder and source_folder.strip():
            custom = source_folder.strip()
            real_path = os.path.realpath(custom)
            # Validate path is within ComfyUI's allowed directories
            from .load_last_video import _is_path_sandboxed
            if not _is_path_sandboxed(real_path):
                logger.warning(
                    "[LoadLast] source_folder '%s' is outside allowed directories, ignoring",
                    custom,
                )
            elif os.path.isdir(real_path):
                scan_dirs = [real_path]
            else:
                logger.warning("[LoadLast] source_folder does not exist: %s", custom)

        # --- Handle pinned image ---
        if pin_index > 0:
            pinned = cache.get_pinned(pin_index)
            if pinned is not None:
                return self._build_output(
                    [pinned.tensor], cache.iteration_counter,
                    grid_columns, grid_padding,
                    diff_mode, diff_sensitivity,
                    show_captions, caption_format,
                    metadata={'prompt': '', 'seed': '', 'workflow': ''},
                    file_paths=[],
                    ring_buffer_full=False,
                )
            else:
                logger.warning(
                    "[LoadLast] Pinned iteration %d not in cache, falling back to latest",
                    pin_index
                )

        # --- Ring buffer mode overrides batch_size ---
        effective_batch = batch_size
        if ring_buffer_size > 0:
            effective_batch = ring_buffer_size

        # --- Discover images via filesystem ---
        paths = scanner.scan(
            scan_dirs,
            n=effective_batch * 2 if skip_duplicates else effective_batch,
            filename_filter=filename_filter,
        )

        if not paths:
            logger.warning("[LoadLast] No images found, returning black fallback")
            return self._empty_output(cache.iteration_counter)

        # --- Load images ---
        images: list[torch.Tensor] = []
        hashes: set[int] = set()
        first_metadata = {'prompt': '', 'seed': '', 'workflow': ''}
        first_path = None
        loaded_paths: list[str] = []

        for path in paths:
            if len(images) >= effective_batch:
                break

            try:
                tensor, meta = scanner.load_image(path)
            except Exception:
                logger.warning("[LoadLast] Skipping corrupted file: %s", path)
                continue

            # Skip duplicates
            if skip_duplicates:
                h = compute_pixel_hash(tensor)
                if h in hashes:
                    continue
                hashes.add(h)

            images.append(tensor)
            loaded_paths.append(path)

            # Capture metadata from the first (most recent) image
            if first_path is None:
                first_path = path
                first_metadata = extract_png_metadata(path)

        if not images:
            logger.warning("[LoadLast] All images were duplicates or corrupted")
            return self._empty_output(cache.iteration_counter)

        ring_buffer_full = (ring_buffer_size > 0 and len(images) >= ring_buffer_size)

        return self._build_output(
            images, cache.iteration_counter,
            grid_columns, grid_padding,
            diff_mode, diff_sensitivity,
            show_captions, caption_format,
            metadata=first_metadata,
            file_paths=loaded_paths,
            ring_buffer_full=ring_buffer_full,
        )

    def _build_output(
        self,
        images: list[torch.Tensor],
        iteration: int,
        grid_columns: int,
        grid_padding: int,
        diff_mode: str,
        diff_sensitivity: float,
        show_captions: bool,
        caption_format: str,
        metadata: dict,
        file_paths: list[str],
        ring_buffer_full: bool = False,
    ):
        """Construct all output tensors from a list of loaded images."""
        # Ensure all images match the first image's dimensions
        target_h, target_w = images[0].shape[0], images[0].shape[1]
        resized = []
        for img in images:
            if img.shape[0] != target_h or img.shape[1] != target_w:
                img_nchw = img.permute(2, 0, 1).unsqueeze(0)
                img_nchw = F.interpolate(
                    img_nchw, size=(target_h, target_w),
                    mode='bilinear', align_corners=False
                )
                img = img_nchw.squeeze(0).permute(1, 2, 0)
            resized.append(img)

        # Stack into batch tensor [B, H, W, 3]
        batch_tensor = torch.stack(resized, dim=0)
        batch_count = len(resized)

        # Create mask (solid white)
        mask = torch.ones(batch_count, target_h, target_w, dtype=torch.float32)

        # --- Build captions if enabled ---
        captions = []
        if show_captions:
            timestamp = datetime.now().strftime("%H:%M:%S")
            seed = metadata.get('seed', '')
            for idx in range(len(resized)):
                filename = os.path.basename(file_paths[idx]) if idx < len(file_paths) else ""
                caption = format_caption(
                    caption_format,
                    iteration=iteration,
                    timestamp=timestamp,
                    seed=seed,
                    index=idx,
                    filename=filename,
                )
                captions.append(caption)

        # Grid output
        grid_image = compose_grid(
            resized, columns=grid_columns, padding=grid_padding
        )

        # Apply captions to grid
        if show_captions and captions:
            grid_image = render_captions_on_grid(
                grid_image, captions,
                cell_width=target_w, cell_height=target_h,
                columns=grid_columns, padding=grid_padding,
            )

        # Side-by-side output
        img_a = resized[0]
        img_b = resized[1] if len(resized) > 1 else None
        side_by_side = compose_side_by_side(img_a, img_b, padding=grid_padding)

        # Apply captions to side-by-side
        if show_captions and len(captions) >= 1:
            sbs_squeezed = side_by_side.squeeze(0)
            sbs_squeezed = render_caption(sbs_squeezed, captions[0])
            side_by_side = sbs_squeezed.unsqueeze(0)

        # --- Diff output ---
        diff_image = compose_diff(
            img_a, img_b,
            mode=diff_mode,
            sensitivity=diff_sensitivity,
        )

        return (
            batch_tensor,           # IMAGE
            mask,                   # MASK
            grid_image,             # GRID_IMAGE
            side_by_side,           # SIDE_BY_SIDE
            diff_image,             # DIFF_IMAGE
            target_w,               # width
            target_h,               # height
            batch_count,            # batch_count
            iteration,              # iteration
            metadata.get('prompt', ''),     # metadata_prompt
            metadata.get('seed', ''),       # metadata_seed
            metadata.get('workflow', ''),   # metadata_workflow
            ring_buffer_full,       # RING_BUFFER_FULL
        )

    def _empty_output(self, iteration: int):
        """Return a black 512x512 fallback image with empty metadata."""
        black = torch.zeros(1, 512, 512, 3)
        mask = torch.ones(1, 512, 512)
        grid = torch.zeros(1, 512, 512, 3)
        sbs = torch.zeros(1, 512, 512 * 2 + 4, 3)
        diff = torch.zeros(1, 512, 512, 3)

        return (
            black,        # IMAGE
            mask,         # MASK
            grid,         # GRID_IMAGE
            sbs,          # SIDE_BY_SIDE
            diff,         # DIFF_IMAGE
            512,          # width
            512,          # height
            0,            # batch_count
            iteration,    # iteration
            '',           # metadata_prompt
            '',           # metadata_seed
            '',           # metadata_workflow
            False,        # RING_BUFFER_FULL
        )
