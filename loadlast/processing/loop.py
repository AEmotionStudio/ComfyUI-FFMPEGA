"""
Loop / Ping-pong frame manipulation.

Applies loop or ping-pong mode to a frame tensor for seamless
looping in AnimateDiff and similar pipelines.
"""

from __future__ import annotations

import torch


def apply_loop_mode(
    frames: torch.Tensor,
    mode: str = "none",
) -> torch.Tensor:
    """
    Apply loop/ping-pong to frame tensor.

    Args:
        frames: [N, H, W, 3] frame tensor
        mode: "none", "loop", or "ping_pong"

    Returns:
        Modified frame tensor:
        - none: [N, H, W, 3] (unchanged)
        - loop: [N+1, H, W, 3] (first frame appended at end)
        - ping_pong: [2N-2, H, W, 3] (frames + reversed middle frames)
    """
    if mode == "none" or frames.shape[0] <= 1:
        return frames

    if mode == "loop":
        # Append the first frame at the end for seamless looping
        return torch.cat([frames, frames[0:1]], dim=0)

    if mode == "ping_pong":
        n = frames.shape[0]
        if n <= 2:
            # With 2 frames: [0, 1, 0]
            return torch.cat([frames, frames[0:1]], dim=0)

        # Reverse middle frames (exclude first and last to avoid stuttering)
        reversed_middle = frames[1:-1].flip(dims=[0])
        return torch.cat([frames, reversed_middle], dim=0)

    # Unknown mode, return as-is
    return frames
