"""Model download guard for FFMPEGA.

When the user sets allow_model_downloads=False on the FFMPEG Agent node,
calling require_downloads_allowed() raises a RuntimeError before any model
auto-download can occur. Call this at the top of any model loading function
that may trigger a download.
"""

from __future__ import annotations

import logging

log = logging.getLogger("ffmpega")

# ---------------------------------------------------------------------------
#  Global flag (set by agent_node.py before each skill run)
# ---------------------------------------------------------------------------

_downloads_allowed: bool = True


def set_downloads_allowed(allowed: bool) -> None:
    """Set the global model-download permission flag.

    Called by agent_node.py at the start of each run, before skill
    handlers are invoked.
    """
    global _downloads_allowed
    _downloads_allowed = allowed


def downloads_allowed() -> bool:
    """Return the current model-download permission flag."""
    return _downloads_allowed


# ---------------------------------------------------------------------------
#  Model registry — info shown in the error message when blocked
# ---------------------------------------------------------------------------

_MODEL_INFO: dict[str, dict] = {
    "sam3": {
        "name": "SAM3 (Segment Anything Model 3)",
        "size": "~300 MB",
        "url": "https://huggingface.co/AEmotionStudio/sam3",
        "manual": "Download sam3.safetensors and place it in ComfyUI/models/SAM3/",
    },
    "lama": {
        "name": "LaMa (Large Mask Inpainting)",
        "size": "~200 MB",
        "url": "https://github.com/enesmsahin/simple-lama-inpainting",
        "manual": "Model auto-downloads via simple-lama-inpainting on first use "
                  "when allow_model_downloads is enabled.",
    },
    "whisper": {
        "name": "OpenAI Whisper",
        "size": "75 MB (tiny) – 3 GB (large-v3)",
        "url": "https://github.com/openai/whisper",
        "manual": "Download from https://openaipublic.blob.core.windows.net/gpt-2/encodings "
                  "or enable allow_model_downloads and let Whisper fetch it automatically.",
    },
}


def require_downloads_allowed(model_key: str) -> None:
    """Raise RuntimeError if model downloads are disabled.

    Call this at the start of any model loading function that may trigger
    an automatic download. When blocked, logs a clear console message with
    the model's download URL so the user knows where to get it manually.

    Args:
        model_key: One of "sam3", "lama", "whisper".

    Raises:
        RuntimeError: If allow_model_downloads is False on the node.
    """
    if _downloads_allowed:
        return

    info = _MODEL_INFO.get(model_key, {
        "name": model_key,
        "size": "unknown",
        "url": "https://github.com/AEmotionStudio/ComfyUI-FFMPEGA",
        "manual": "See project README for manual installation.",
    })

    msg = (
        f"\n"
        f"[FFMPEGA] ⛔ Model download blocked: {info['name']} ({info['size']})\n"
        f"[FFMPEGA]    The 'allow_model_downloads' toggle is OFF on the FFMPEG Agent node.\n"
        f"[FFMPEGA]    To download automatically: enable 'allow_model_downloads' and re-run.\n"
        f"[FFMPEGA]    To install manually:       {info['manual']}\n"
        f"[FFMPEGA]    Model page:                {info['url']}\n"
    )

    # Always print to console so it's visible even if logging is suppressed
    print(msg)
    log.error(
        "Model download blocked (%s). Enable allow_model_downloads or install manually. "
        "See: %s",
        info["name"], info["url"],
    )

    raise RuntimeError(
        f"{info['name']} requires a download (~{info['size']}) but "
        f"'allow_model_downloads' is disabled on the FFMPEG Agent node. "
        f"Enable it to auto-download, or download manually from: {info['url']}"
    )
