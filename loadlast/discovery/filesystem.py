"""
Filesystem scanner for discovering recent image files.

Scans ComfyUI's output and temp directories for image files,
sorted by modification time. Used as fallback when the execution
hook doesn't have cached results.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

import numpy as np
import torch
from PIL import Image

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp', '.bmp', '.tiff', '.tif', '.gif'}
MAX_FILE_SIZE = 200 * 1024 * 1024  # 200 MB


class FilesystemScanner:
    """Scans directories for recent image files."""

    def scan(
        self,
        directories: list[str],
        n: int = 1,
        filename_filter: str = "",
        recursive: bool = True,
    ) -> list[str]:
        """
        Return paths to the N most recent image files, sorted by mtime descending.

        Args:
            directories: list of directory paths to scan
            n: number of files to return
            filename_filter: optional prefix filter for filenames
            recursive: whether to scan subdirectories

        Returns:
            List of absolute file paths, newest first
        """
        candidates: list[tuple[float, str]] = []

        for directory in directories:
            if not os.path.isdir(directory):
                logger.debug("[LoadLast] Directory does not exist: %s", directory)
                continue

            try:
                self._collect_files(directory, candidates, filename_filter, recursive)
            except PermissionError:
                logger.warning("[LoadLast] Permission denied scanning: %s", directory)
            except Exception:
                logger.warning("[LoadLast] Error scanning directory: %s", directory, exc_info=True)

        # Sort by mtime descending (newest first)
        candidates.sort(key=lambda x: x[0], reverse=True)

        return [path for _, path in candidates[:n]]

    def _collect_files(
        self,
        directory: str,
        candidates: list[tuple[float, str]],
        filename_filter: str,
        recursive: bool,
    ):
        """Collect image files from a directory into the candidates list."""
        try:
            entries = os.scandir(directory)
        except PermissionError:
            logger.warning("[LoadLast] Permission denied: %s", directory)
            return

        for entry in entries:
            try:
                if entry.is_file(follow_symlinks=False):
                    name = entry.name
                    ext = os.path.splitext(name)[1].lower()

                    if ext not in SUPPORTED_EXTENSIONS:
                        continue

                    if filename_filter and not name.startswith(filename_filter):
                        continue

                    # Resolve symlinks for security
                    real_path = os.path.realpath(entry.path)

                    stat = os.stat(real_path)
                    if stat.st_size > MAX_FILE_SIZE:
                        logger.debug("[LoadLast] Skipping large file: %s (%d bytes)",
                                     real_path, stat.st_size)
                        continue
                    if stat.st_size == 0:
                        continue

                    candidates.append((stat.st_mtime, real_path))

                elif entry.is_dir(follow_symlinks=False) and recursive:
                    self._collect_files(entry.path, candidates, filename_filter, recursive)

            except (PermissionError, OSError):
                continue

    def load_image(self, path: str) -> tuple[torch.Tensor, dict]:
        """
        Load an image file as a tensor + metadata dict.

        Args:
            path: absolute path to the image file

        Returns:
            Tuple of (tensor [H, W, C] float32 in [0,1], metadata dict)
        """
        metadata = {}

        try:
            img = Image.open(path)

            # Extract PNG metadata if available
            if hasattr(img, 'text'):
                metadata = dict(img.text)

            # Handle animated GIF — use first frame only
            if getattr(img, 'is_animated', False):
                img.seek(0)

            # Convert to RGB or RGBA
            if img.mode == 'RGBA':
                img_rgb = img.convert('RGB')
                # Keep alpha separately
                alpha = np.array(img.getchannel('A')).astype(np.float32) / 255.0
                metadata['_alpha'] = alpha
                img = img_rgb
            elif img.mode != 'RGB':
                img = img.convert('RGB')

            # Convert to tensor
            img_array = np.array(img).astype(np.float32) / 255.0
            tensor = torch.from_numpy(img_array)  # [H, W, 3]

            return tensor, metadata

        except Exception as e:
            logger.warning("[LoadLast] Failed to load image %s: %s", path, e)
            raise


def get_default_directories() -> list[str]:
    """
    Get ComfyUI's default output and temp directories.

    Returns:
        List of directory paths to scan
    """
    dirs = []
    try:
        import folder_paths
        output_dir = folder_paths.get_output_directory()
        if output_dir and os.path.isdir(output_dir):
            dirs.append(output_dir)

        temp_dir = folder_paths.get_temp_directory()
        if temp_dir and os.path.isdir(temp_dir):
            dirs.append(temp_dir)
    except ImportError:
        logger.debug("[LoadLast] folder_paths not available, using fallback paths")

    return dirs
