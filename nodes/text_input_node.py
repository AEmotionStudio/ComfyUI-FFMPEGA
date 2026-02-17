"""FFMPEGA Text Input node for ComfyUI.

Provides a flexible text input that connects to the FFMPEGA Agent node's
dynamic text_a, text_b, ... inputs.  Supports subtitle content, overlay
text, watermarks, and raw text with auto-mode detection.
"""

import json
import logging
import re

logger = logging.getLogger("FFMPEGA")



def _detect_mode(text: str) -> str:
    """Auto-detect the best mode for the given text.

    Returns one of: ``subtitle``, ``watermark``, ``overlay``.
    """
    if "-->" in text:
        return "subtitle"
    lines = [ln for ln in text.strip().splitlines() if ln.strip()]
    if len(lines) == 1 and len(lines[0]) < 50:
        return "watermark"
    if len(lines) > 2:
        return "subtitle"
    return "overlay"


_AUTO_POSITION = {
    "subtitle": "bottom_center",
    "watermark": "bottom_right",
    "overlay": "center",
    "title_card": "center",
    "raw": "center",
}

_AUTO_FONTSIZE = {
    "subtitle": 24,
    "watermark": 20,
    "overlay": 48,
    "title_card": 64,
    "raw": 24,
}


class TextInputNode:
    """FFMPEGA Text — flexible text input with auto-mode detection.

    Outputs a JSON-encoded string so the agent node can parse both
    the text content and its metadata (mode, position, font settings).
    Plain STRING primitives also work — the agent treats non-JSON
    strings as raw text.
    """

    MODES = ["auto", "subtitle", "overlay", "watermark", "title_card", "raw"]
    POSITIONS = [
        "auto", "center", "top", "bottom",
        "top_left", "top_right", "bottom_left", "bottom_right",
        "bottom_center",
    ]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "text": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "placeholder": (
                        "Enter text, paste SRT subtitles, or type a watermark..."
                    ),
                    "tooltip": (
                        "The text content to use. Can be plain text, multi-line "
                        "subtitles, or full SRT format with timestamps."
                    ),
                }),
            },
            "optional": {
                "auto_mode": ("BOOLEAN", {
                    "default": True,
                    "label_on": "Auto",
                    "label_off": "Manual",
                    "tooltip": (
                        "When Auto, the system detects whether your text is "
                        "subtitles, a watermark, or overlay text and sets "
                        "defaults accordingly. Turn off for full manual control."
                    ),
                }),
                "mode": (cls.MODES, {
                    "default": "auto",
                    "tooltip": (
                        "Text usage mode. 'auto' detects from content. "
                        "'subtitle' burns timed text. 'overlay' draws text on "
                        "video. 'watermark' adds small persistent text. "
                        "'title_card' shows large centered text. 'raw' passes "
                        "text through unchanged."
                    ),
                }),
                "position": (cls.POSITIONS, {
                    "default": "auto",
                    "tooltip": (
                        "Where to place the text. 'auto' chooses based on mode "
                        "(subtitle → bottom, watermark → bottom-right, etc.)."
                    ),
                }),
                "font_size": ("INT", {
                    "default": 0,
                    "min": 0,
                    "max": 200,
                    "step": 2,
                    "tooltip": (
                        "Font size in pixels. 0 = auto (24 for subtitles, "
                        "48 for overlay, 20 for watermark)."
                    ),
                }),
                "font_color": ("STRING", {
                    "default": "#FFFFFF",
                    "tooltip": "Text color — click to pick a color or type a hex value (#RRGGBB).",
                }),
                "start_time": ("FLOAT", {
                    "default": 0.0,
                    "min": 0.0,
                    "max": 3600.0,
                    "step": 0.5,
                    "tooltip": "Start time in seconds. 0 = beginning of video.",
                }),
                "end_time": ("FLOAT", {
                    "default": -1.0,
                    "min": -1.0,
                    "max": 3600.0,
                    "step": 0.5,
                    "tooltip": (
                        "End time in seconds. -1 = full video duration."
                    ),
                }),
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("text_output",)
    OUTPUT_TOOLTIPS = (
        "JSON-encoded text with metadata. Connect to text_a, text_b, etc. "
        "on the FFMPEGA Agent node.",
    )
    FUNCTION = "process"
    CATEGORY = "FFMPEGA"
    DESCRIPTION = (
        "Flexible text input for subtitles, overlays, watermarks, and more. "
        "Connect to the FFMPEGA Agent node's text_a/text_b/... inputs."
    )

    def process(
        self,
        text: str,
        auto_mode: bool = True,
        mode: str = "auto",
        position: str = "auto",
        font_size: int = 0,
        font_color: str = "white",
        start_time: float = 0.0,
        end_time: float = -1.0,
    ) -> tuple[str]:
        """Build JSON payload with text content and metadata."""
        if not text.strip():
            return ("",)

        # Resolve mode
        effective_mode = mode
        if auto_mode or mode == "auto":
            effective_mode = _detect_mode(text)

        # Resolve position
        effective_position = position
        if auto_mode or position == "auto":
            effective_position = _AUTO_POSITION.get(effective_mode, "center")
        elif position != "auto":
            effective_position = position

        # Resolve font_size (0 = auto)
        effective_font_size = font_size
        if font_size == 0:
            effective_font_size = _AUTO_FONTSIZE.get(effective_mode, 24)

        payload = {
            "text": text.strip(),
            "mode": effective_mode,
            "position": effective_position,
            "font_size": effective_font_size,
            "font_color": font_color.strip(),
            "start_time": start_time,
            "end_time": end_time,
            "auto_mode": auto_mode,
        }

        return (json.dumps(payload),)

    @classmethod
    def IS_CHANGED(cls, text="", **kwargs):
        """Re-run when text or settings change."""
        import hashlib
        key = f"{text}:{kwargs}"
        return hashlib.md5(key.encode()).hexdigest()
