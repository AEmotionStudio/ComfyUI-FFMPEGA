# coding: utf-8
"""Handler for the ai_upscale skill (AI Super-Resolution).

Upscales images and videos using Real-ESRGAN, HAT, DAT, SwinIR
via the spandrel universal model loader, or SeedVR2 diffusion-based
upscaler for higher quality with temporal consistency.
"""

import logging
import os

log = logging.getLogger("ffmpega")

_GAN_MODELS = {
    "realesrgan_x4plus", "realesrgan_x4_anime",
    "hat_x4", "dat_x4", "swinir_x4",
}
_SEEDVR_MODELS = {"seedvr2_3b_fp8", "seedvr2_3b_gguf", "seedvr2_7b_fp8", "seedvr2_7b_gguf"}
_VALID_MODELS = _GAN_MODELS | _SEEDVR_MODELS
_VALID_SCALES = {2, 4}
_VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".flv", ".wmv"}


def _f_ai_upscale(params: dict) -> dict:
    """Execute AI upscaling.

    Expected params:
        _input_path (str): path to source image or video
        model (str): upscaler model name (default: realesrgan_x4plus)
        scale_factor (int): 2 or 4 (default: 4)
        tile_size (int): tile size 256-1024 (default: 512)

    Returns:
        dict with 'movie' or 'image' key on success, or 'error' on failure.
    """
    input_path = params.get("_input_path", "")

    if not input_path or not os.path.isfile(input_path):
        return {"error": "ai_upscale requires a valid source image or video input"}

    model = str(params.get("model", "realesrgan_x4plus")).lower()
    if model not in _VALID_MODELS:
        return {
            "error": f"Invalid model '{model}'. "
                     f"Must be one of: {sorted(_VALID_MODELS)}"
        }

    # Determine if input is video or image
    ext = os.path.splitext(input_path)[1].lower()
    is_video = ext in _VIDEO_EXTS

    # ── SeedVR2 diffusion upscaler ────────────────────────────────────
    if model in _SEEDVR_MODELS:
        try:
            try:
                from core.seedvr_synthesizer import upscale_image, upscale_video
            except ImportError:
                from ...core.seedvr_synthesizer import upscale_image, upscale_video
        except ImportError:
            return {
                "error": "SeedVR2 upscaler is not available. "
                         "Ensure core/seedvr_synthesizer.py exists and "
                         "diffusers is installed."
            }

        try:
            if is_video:
                output_path = upscale_video(
                    input_path=input_path,
                    model_name=model,
                )
                return {"movie": output_path}
            else:
                output_path = upscale_image(
                    input_path=input_path,
                    model_name=model,
                )
                return {"image": output_path}
        except Exception as exc:
            log.error("ai_upscale (SeedVR2) handler failed: %s", exc)
            return {"error": f"SeedVR2 upscaling failed: {exc}"}

    # ── GAN upscaler (spandrel) ───────────────────────────────────────
    scale_factor = int(params.get("scale_factor", 4))
    if scale_factor not in _VALID_SCALES:
        return {
            "error": f"Invalid scale_factor '{scale_factor}'. "
                     f"Must be one of: {sorted(_VALID_SCALES)}"
        }

    tile_size = int(params.get("tile_size", 512))
    tile_size = max(256, min(1024, tile_size))

    try:
        try:
            from core.upscaler import upscale_image, upscale_video
        except ImportError:
            from ...core.upscaler import upscale_image, upscale_video
    except ImportError:
        return {
            "error": "AI Upscaler is not available. "
                     "Ensure core/upscaler.py exists and spandrel is installed."
        }

    try:
        if is_video:
            output_path = upscale_video(
                input_path=input_path,
                model_name=model,
                scale_factor=scale_factor,
                tile_size=tile_size,
            )
            return {"movie": output_path}
        else:
            output_path = upscale_image(
                input_path=input_path,
                model_name=model,
                scale_factor=scale_factor,
                tile_size=tile_size,
            )
            return {"image": output_path}
    except Exception as exc:
        log.error("ai_upscale handler failed: %s", exc)
        return {"error": f"AI upscaling failed: {exc}"}
