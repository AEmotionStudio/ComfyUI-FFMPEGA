"""Shared utility: stream IMAGE tensor frames to an FFmpeg video file.

Used by both LoadLastVideo and VideoEditorNode to convert IMAGE tensor
batches into temp video files for preview/editing.
"""

from __future__ import annotations

import subprocess
import time

import torch

from .bin_paths import get_ffmpeg_bin
from .video import encode_opts as eo


def images_to_video(
    images: torch.Tensor, output_path: str, fps: int = 24,
    color: str = eo.DEFAULT_COLOR_POLICY,
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
    color:
        Colour policy key from :mod:`core.video.encode_opts`.  Defaults to
        the same sRGB handling every other FFMPEGA encoder uses; previously
        this path wrote untagged BT.601, disagreeing with the rest.
    """
    ffmpeg = get_ffmpeg_bin()

    n, h, w, c = images.shape
    # Ensure exactly 3 channels (drop alpha if RGBA)
    if c != 3:
        images = images[..., :3]

    spec = eo.EncodeSpec(
        format="h264-mp4", crf=18, preset="ultrafast",
        color=color, faststart=False,
    )
    cmd = [ffmpeg, "-y", "-v", "quiet"]
    cmd += eo.raw_input_args(w, h, fps, spec.bit_depth)
    vf = eo.video_filter(spec)
    if vf:
        cmd += ["-vf", vf]
    cmd += eo.video_output_args(spec)
    cmd.append(output_path)

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
            # frames_to_bytes clamps; the old `* 255` cast here wrapped
            # out-of-gamut values around to black.
            frame_bytes = eo.frames_to_bytes(images[i:i + 1], spec.bit_depth).tobytes()
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
