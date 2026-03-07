"""
Video filesystem scanner for discovering recent video files and image sequences.

Scans ComfyUI's output and temp directories for video files (.mp4, .webm, .gif)
and groups of numbered image files into image sequences.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

VIDEO_EXTENSIONS = {'.mp4', '.webm', '.gif'}
SEQUENCE_IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp', '.bmp', '.tiff'}
SEQUENCE_PATTERN = re.compile(r'^(.+?)[-_]?(\d{3,})\.(\w+)$')
MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024  # 2 GB


@dataclass
class VideoEntry:
    """A single discovered video (file or image sequence)."""
    path: str                       # File path (or first frame path for sequences)
    source_type: str                # "file" or "sequence"
    mtime: float                    # Most recent modification time
    frame_paths: list[str] = field(default_factory=list)  # For sequences: all frames in order
    extension: str = ""             # Container format or frame format


class VideoFilesystemScanner:
    """Scans directories for video files and image sequences."""

    def scan(
        self,
        directories: list[str],
        n: int = 1,
        filename_filter: str = "",
        recursive: bool = True,
    ) -> list[VideoEntry]:
        """
        Return the N most recent video entries, sorted by mtime descending.

        Args:
            directories: list of directory paths to scan
            n: number of entries to return
            filename_filter: optional prefix filter for filenames
            recursive: whether to scan subdirectories

        Returns:
            List of VideoEntry, newest first
        """
        all_entries: list[VideoEntry] = []

        for directory in directories:
            if not os.path.isdir(directory):
                logger.debug("[LoadLast] Video scan: directory does not exist: %s", directory)
                continue

            try:
                entries = self._scan_directory(directory, filename_filter, recursive)
                all_entries.extend(entries)
            except PermissionError:
                logger.warning("[LoadLast] Permission denied scanning: %s", directory)
            except Exception:
                logger.warning("[LoadLast] Error scanning directory: %s", directory, exc_info=True)

        # Sort by mtime descending (newest first)
        all_entries.sort(key=lambda e: e.mtime, reverse=True)
        return all_entries[:n]

    def _scan_directory(
        self, directory: str, filename_filter: str, recursive: bool
    ) -> list[VideoEntry]:
        """Scan a single directory for video files and image sequences."""
        entries: list[VideoEntry] = []

        # 1. Find video files
        entries.extend(self._scan_video_files(directory, filename_filter))

        # 2. Detect image sequences
        entries.extend(self._detect_sequences(directory, filename_filter))

        # 3. Recurse into subdirectories
        if recursive:
            try:
                for item in os.scandir(directory):
                    if item.is_dir(follow_symlinks=False):
                        entries.extend(self._scan_directory(item.path, filename_filter, recursive))
            except PermissionError:
                pass

        return entries

    def _scan_video_files(self, directory: str, filename_filter: str) -> list[VideoEntry]:
        """Find individual video files (.mp4, .webm, .gif)."""
        entries = []

        try:
            for item in os.scandir(directory):
                if not item.is_file(follow_symlinks=False):
                    continue

                ext = os.path.splitext(item.name)[1].lower()
                if ext not in VIDEO_EXTENSIONS:
                    continue

                if filename_filter and not item.name.startswith(filename_filter):
                    continue

                real_path = os.path.realpath(item.path)

                try:
                    stat = os.stat(real_path)
                except OSError:
                    continue

                if stat.st_size > MAX_FILE_SIZE:
                    logger.debug("[LoadLast] Skipping large video: %s (%d bytes)", real_path, stat.st_size)
                    continue

                if stat.st_size == 0:
                    continue

                entries.append(VideoEntry(
                    path=real_path,
                    source_type="file",
                    mtime=stat.st_mtime,
                    frame_paths=[],
                    extension=ext,
                ))

        except PermissionError:
            pass

        return entries

    def _detect_sequences(self, directory: str, filename_filter: str) -> list[VideoEntry]:
        """
        Group numbered image files into sequence entries.

        Algorithm:
        1. Match filenames against SEQUENCE_PATTERN
        2. Group by (prefix, extension)
        3. Validate: require minimum 2 frames
        4. Return as VideoEntry with source_type="sequence"
        """
        groups: dict[tuple[str, str], list[tuple[int, str, float]]] = {}

        try:
            for item in os.scandir(directory):
                if not item.is_file(follow_symlinks=False):
                    continue

                ext = os.path.splitext(item.name)[1].lower()
                if ext not in SEQUENCE_IMAGE_EXTENSIONS:
                    continue

                if filename_filter and not item.name.startswith(filename_filter):
                    continue

                match = SEQUENCE_PATTERN.match(item.name)
                if not match:
                    continue

                prefix = match.group(1)
                frame_num = int(match.group(2))
                real_path = os.path.realpath(item.path)

                try:
                    stat = os.stat(real_path)
                except OSError:
                    continue

                if stat.st_size == 0:
                    continue

                key = (prefix, ext)
                if key not in groups:
                    groups[key] = []
                groups[key].append((frame_num, real_path, stat.st_mtime))

        except PermissionError:
            pass

        entries = []
        for (prefix, ext), frames in groups.items():
            if len(frames) < 2:
                continue  # Not a sequence — need at least 2 frames

            # Sort by frame number
            frames.sort(key=lambda f: f[0])
            frame_paths = [f[1] for f in frames]
            max_mtime = max(f[2] for f in frames)

            entries.append(VideoEntry(
                path=frame_paths[0],  # First frame path
                source_type="sequence",
                mtime=max_mtime,
                frame_paths=frame_paths,
                extension=ext,
            ))

        return entries
