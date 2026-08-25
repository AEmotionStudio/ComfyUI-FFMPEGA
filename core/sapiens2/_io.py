# coding: utf-8
"""Video frame I/O helpers for the Sapiens2 integration.

Lives apart from the inference code so it can be tested without loading
any ML deps.  Uses OpenCV for decode and the project's bundled ffmpeg
binary for encode (so output stays consistent with the rest of FFMPEGA).
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Iterator, Optional

import cv2
import numpy as np

log = logging.getLogger("ffmpega")


_IMAGE_EXTS = frozenset({".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".webp"})
_VIDEO_EXTS = frozenset({".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv",
                         ".wmv", ".ts", ".m4v"})


def is_image_path(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in _IMAGE_EXTS


def is_video_path(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in _VIDEO_EXTS


def open_video(path: str) -> tuple[cv2.VideoCapture, float, int, int, int]:
    """Open ``path`` and return ``(cap, fps, width, height, frame_count)``.

    Raises:
        FileNotFoundError: if ``path`` does not exist.
        RuntimeError: if OpenCV cannot decode the file.
    """
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Sapiens2 input file not found: {path}")

    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        raise RuntimeError(f"Sapiens2: cannot decode video {path!r}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    return cap, fps, width, height, frame_count


def iter_video_frames(path: str) -> Iterator[np.ndarray]:
    """Yield BGR frames (uint8 HxWx3) from ``path`` one at a time.

    Releases the capture even if the consumer breaks out of the loop.
    """
    cap, *_ = open_video(path)
    try:
        while True:
            ok, frame = cap.read()
            if not ok or frame is None:
                break
            yield frame
    finally:
        cap.release()


def encode_frames_to_video(
    frames_dir: str,
    output_path: str,
    fps: float,
    ffmpeg_bin: str,
    *,
    crf: int = 18,
    preset: str = "medium",
    pattern: str = "%06d.png",
) -> None:
    """Encode a directory of frames as an H.264 MP4.

    The caller owns ``frames_dir`` — this function does not delete it.

    Raises:
        RuntimeError: if ffmpeg exits non-zero or no frames matched
            ``pattern`` (caught from ffmpeg's stderr).
    """
    fps_str = (
        str(int(round(fps)))
        if abs(round(fps) - fps) < 0.01
        else f"{fps:.3f}"
    )
    cmd = [
        ffmpeg_bin, "-y",
        "-framerate", fps_str,
        "-i", os.path.join(frames_dir, pattern),
        "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2",
        "-c:v", "libx264",
        "-crf", str(crf),
        "-preset", preset,
        "-pix_fmt", "yuv420p",
        "-an",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="replace")[-2000:]
        raise RuntimeError(
            f"Sapiens2: ffmpeg encode failed (exit {result.returncode})\n"
            f"--- ffmpeg stderr (tail) ---\n{stderr}"
        )


class FrameSink:
    """Buffer for output frames written to a temp directory.

    Used by per-task pipelines so they don't all reimplement the
    "write frame N as PNG, then ffmpeg the directory" dance.

    Usage:
        with FrameSink(prefix="sapiens2_pose_") as sink:
            for i, frame_bgr in enumerate(frames):
                sink.add(frame_bgr)
            sink.encode(output_path, fps=24.0, ffmpeg_bin="ffmpeg")
    """

    def __init__(self, *, prefix: str = "sapiens2_") -> None:
        self._dir: Optional[str] = None
        self._prefix = prefix
        self._count = 0

    def __enter__(self) -> "FrameSink":
        self._dir = tempfile.mkdtemp(prefix=self._prefix)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.cleanup()

    @property
    def directory(self) -> str:
        if self._dir is None:
            raise RuntimeError("FrameSink used outside of a `with` block")
        return self._dir

    @property
    def count(self) -> int:
        return self._count

    def add(self, frame_bgr: np.ndarray) -> None:
        """Append one BGR frame.

        Frames are written as zero-padded PNGs (``%06d.png``).  We cap at
        999,999 frames per session (~11 hours at 24 fps); raise loudly
        rather than silently overflowing the pattern.
        """
        if self._count >= 999_999:
            raise RuntimeError(
                "Sapiens2: frame count exceeded 999,999 — increase pattern "
                "width or split the input."
            )
        path = os.path.join(self.directory, f"{self._count:06d}.png")
        ok = cv2.imwrite(path, frame_bgr)
        if not ok:
            raise RuntimeError(f"Sapiens2: cv2.imwrite failed for {path}")
        self._count += 1

    def encode(
        self,
        output_path: str,
        *,
        fps: float,
        ffmpeg_bin: str,
        crf: int = 18,
        preset: str = "medium",
    ) -> None:
        if self._count == 0:
            raise RuntimeError(
                "Sapiens2: no frames were written — refusing to encode an "
                "empty video."
            )
        encode_frames_to_video(
            self.directory, output_path,
            fps=fps, ffmpeg_bin=ffmpeg_bin, crf=crf, preset=preset,
        )

    def cleanup(self) -> None:
        if self._dir is not None and os.path.isdir(self._dir):
            shutil.rmtree(self._dir, ignore_errors=True)
        self._dir = None
