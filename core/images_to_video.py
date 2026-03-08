"""Shared utility: stream IMAGE tensor frames to an FFmpeg video file.

Used by both LoadLastVideo and VideoEditorNode to convert IMAGE tensor
batches into temp video files for preview/editing.
"""

from __future__ import annotations

import subprocess
import time

import numpy as np
import torch

from .bin_paths import get_ffmpeg_bin


def images_to_video(
    images: torch.Tensor, output_path: str, fps: int = 24,
) -> None:
    """Convert an IMAGE tensor batch [N, H, W, C] to a video file.

    Streams frames to FFmpeg via stdin to avoid materializing the
    entire raw buffer in memory at once.

    Parameters
    ----------
    images:
        Tensor of shape ``(N, H, W, C)`` with float values in [0, 1].
    output_path:
        Destination file path (usually ``.mp4``).
    fps:
        Output framerate.
    """
    ffmpeg = get_ffmpeg_bin()

    n, h, w, c = images.shape
    # Ensure exactly 3 channels (drop alpha if RGBA)
    if c != 3:
        images = images[..., :3]

    cmd = [
        ffmpeg, "-y",
        "-f", "rawvideo", "-pix_fmt", "rgb24",
        "-s", f"{w}x{h}", "-r", str(fps),
        "-i", "pipe:0",
        "-c:v", "libx264", "-preset", "ultrafast",
        "-pix_fmt", "yuv420p",
        "-v", "quiet",
        output_path,
    ]
    proc = subprocess.Popen(
        cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        # Deadline for entire write loop + drain to prevent indefinite hangs.
        # Scale with frame count so large batches don't get killed prematurely.
        deadline = time.monotonic() + max(60, n * 0.1)
        for i in range(n):
            if proc.poll() is not None:
                raise RuntimeError("ffmpeg exited unexpectedly during encoding")
            if time.monotonic() > deadline:
                raise RuntimeError("ffmpeg encode timed out during frame writes")
            frame_bytes = (images[i].cpu().numpy() * 255).astype(np.uint8).tobytes()
            proc.stdin.write(frame_bytes)
        proc.stdin.close()
        remaining = max(1, deadline - time.monotonic())
        _, stderr = proc.communicate(timeout=remaining)
        if proc.returncode != 0:
            raise RuntimeError(f"ffmpeg encode failed: {stderr.decode()[:200]}")
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)
        raise RuntimeError("ffmpeg encode timed out")
    except Exception:
        proc.kill()
        proc.wait(timeout=5)
        raise
