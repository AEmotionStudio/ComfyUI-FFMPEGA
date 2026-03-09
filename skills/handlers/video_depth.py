# coding: utf-8
"""Handler for the video_depth skill (Video Depth Anything).

Produces temporally-consistent depth estimation videos using
the Video Depth Anything model with native temporal attention.
"""

import logging
import os

log = logging.getLogger("ffmpega")

_VALID_ENCODERS = {"vits", "vitb", "vitl"}


def _f_video_depth(params: dict) -> dict:
    """Execute video depth estimation via Video Depth Anything.

    Expected params:
        _input_path (str): path to source video
        encoder (str): model variant — 'vits' (default), 'vitb', 'vitl'
        input_size (int): model input resolution (default 518)
        max_res (int): max video resolution (default 1280)

    Returns:
        dict with 'movie' key on success, or 'error' key on failure.
    """
    input_path = params.get("_input_path", "")

    if not input_path or not os.path.isfile(input_path):
        return {"error": "video_depth requires a valid source video input"}

    encoder = str(params.get("encoder", "vits")).lower()
    if encoder not in _VALID_ENCODERS:
        return {
            "error": f"Invalid encoder '{encoder}'. "
                     f"Must be one of: {sorted(_VALID_ENCODERS)}"
        }

    input_size = int(params.get("input_size", 518))
    max_res = int(params.get("max_res", 1280))

    # Import synthesizer
    try:
        try:
            from core.vda_synthesizer import run_video_depth
        except ImportError:
            from ...core.vda_synthesizer import run_video_depth
    except ImportError:
        return {
            "error": "Video Depth Anything is not available. "
                     "Ensure core/vda_synthesizer.py and "
                     "core/video_depth_anything/ exist."
        }

    # Run inference
    try:
        output_path = run_video_depth(
            input_path=input_path,
            encoder=encoder,
            input_size=input_size,
            max_res=max_res,
        )
    except Exception as exc:
        log.error("video_depth handler failed: %s", exc)
        return {"error": f"Video depth estimation failed: {exc}"}

    if not output_path or not os.path.isfile(output_path):
        return {"error": "Video depth estimation produced no output"}

    return {"movie": output_path}
