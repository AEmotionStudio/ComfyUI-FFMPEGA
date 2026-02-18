"""FFMPEGA Subtitle skill handlers.

Handles subtitle burning and SRT generation from text.
"""

try:
    from ...core.sanitize import (
        sanitize_text_param,
        validate_path,
        ALLOWED_SUBTITLE_EXTENSIONS,
    )
except ImportError:
    from core.sanitize import (
        sanitize_text_param,
        validate_path,
        ALLOWED_SUBTITLE_EXTENSIONS,
    )

try:
    from ..handler_contract import make_result
except ImportError:
    from skills.handler_contract import make_result


def _f_burn_subtitles(p):
    """Burn/hardcode subtitles from .srt/.ass file or text input into video."""
    import json as _json
    import tempfile as _tmpmod

    # --- Try to resolve text from connected text inputs ---
    text_inputs = p.get("_text_inputs", [])
    text_input_ref = p.get("text_input", "")  # LLM may specify "text_a"
    text_content = None
    srt_file_path = None

    # --- Resolve subtitle file path ---
    path = p.get("path", "")
    _trusted_path = False  # auto-generated paths don't need text sanitization

    # Handle LLM passing text input slot reference as path (e.g. path='text_a')
    import re as _re
    if _re.match(r'^text_[a-z]$', str(path)) and text_inputs:
        slot_idx = ord(str(path)[-1]) - ord('a')
        if 0 <= slot_idx < len(text_inputs):
            raw = text_inputs[slot_idx]
            try:
                meta = _json.loads(raw)
                if isinstance(meta, dict) and meta.get("text"):
                    text_content = meta["text"]
                    if "font_size" in meta and meta["font_size"]:
                        p["fontsize"] = meta["font_size"]
                    if "font_color" in meta and meta["font_color"]:
                        p["fontcolor"] = meta["font_color"]
            except (_json.JSONDecodeError, TypeError):
                text_content = raw
        path = ""  # Clear the slot reference

    # If no explicit slot was resolved, scan all text inputs
    if not text_content and not srt_file_path:
        for raw_text in text_inputs:
            try:
                meta = _json.loads(raw_text)
                if isinstance(meta, dict) and meta.get("mode") in ("subtitle", "auto"):
                    if meta.get("path"):
                        srt_file_path = meta["path"]
                    elif meta.get("text"):
                        text_content = meta["text"]
                        if "font_size" in meta and meta["font_size"]:
                            p["fontsize"] = meta["font_size"]
                        if "font_color" in meta and meta["font_color"]:
                            p["fontcolor"] = meta["font_color"]
                    break
            except (_json.JSONDecodeError, TypeError):
                text_content = raw_text
                break

    if srt_file_path:
        path = srt_file_path
        _trusted_path = True
    elif text_content:
        duration = float(p.get("_video_duration", 8.0))
        srt_content = _auto_srt_from_text(text_content, duration)
        tmp = _tmpmod.NamedTemporaryFile(
            mode="w", suffix=".srt", delete=False, encoding="utf-8"
        )
        tmp.write(srt_content)
        tmp.close()
        path = tmp.name
        _trusted_path = True
        import atexit as _atexit
        import os as _os
        _atexit.register(_os.unlink, path)
    elif not path:
        path = "subtitles.srt"

    if not _trusted_path:
        path = sanitize_text_param(str(path))
    validate_path(path, ALLOWED_SUBTITLE_EXTENSIONS, must_exist=True)
    fontsize = int(p.get("fontsize", 24))
    fontcolor = sanitize_text_param(str(p.get("fontcolor", "white")))

    color_map = {
        "white": "&H00FFFFFF",
        "black": "&H00000000",
        "red": "&H000000FF",
        "green": "&H0000FF00",
        "blue": "&H00FF0000",
        "yellow": "&H0000FFFF",
        "cyan": "&H00FFFF00",
        "magenta": "&H00FF00FF",
    }
    fontcolor_lower = fontcolor.lower().strip()
    if fontcolor_lower in color_map:
        ass_color = color_map[fontcolor_lower]
    elif fontcolor_lower.startswith("#") and len(fontcolor_lower) in (7, 9):
        hex_val = fontcolor_lower.lstrip("#")
        if len(hex_val) == 6:
            r, g, b = hex_val[0:2], hex_val[2:4], hex_val[4:6]
            ass_color = f"&H00{b}{g}{r}".upper()
        else:
            a, r, g, b = hex_val[0:2], hex_val[2:4], hex_val[4:6], hex_val[6:8]
            ass_color = f"&H{a}{b}{g}{r}".upper()
    elif fontcolor_lower.startswith("&h"):
        ass_color = fontcolor
    else:
        ass_color = "&H00FFFFFF"

    def _ffmpeg_escape(s: str) -> str:
        """Escape special chars for ffmpeg filter option values."""
        s = s.replace("\\", "\\\\")
        s = s.replace("'", "\\'")
        s = s.replace(":", "\\:")
        s = s.replace(",", "\\,")
        s = s.replace("[", "\\[")
        s = s.replace("]", "\\]")
        s = s.replace(" ", "\\ ")
        return s

    escaped_path = _ffmpeg_escape(str(path))
    style = f"FontSize={fontsize},PrimaryColour={ass_color}"
    escaped_style = _ffmpeg_escape(style)
    vf = f"subtitles={escaped_path}:force_style={escaped_style}"
    return make_result(vf=[vf])


def _auto_srt_from_text(text: str, duration: float = 8.0) -> str:
    """Convert plain text into SRT subtitle format."""
    if "-->" in text:
        return text

    lines = [ln.strip() for ln in text.strip().splitlines() if ln.strip()]
    if not lines:
        return ""

    srt_blocks = []
    interval = duration / len(lines)
    for i, line in enumerate(lines):
        start = i * interval
        end = min((i + 1) * interval, duration)
        h_s, m_s, s_s = int(start // 3600), int((start % 3600) // 60), start % 60
        h_e, m_e, s_e = int(end // 3600), int((end % 3600) // 60), end % 60
        srt_blocks.append(
            f"{i + 1}\n"
            f"{h_s:02d}:{m_s:02d}:{int(s_s):02d},{int((s_s % 1) * 1000):03d} --> "
            f"{h_e:02d}:{m_e:02d}:{int(s_e):02d},{int((s_e % 1) * 1000):03d}\n"
            f"{line}\n"
        )
    return "\n".join(srt_blocks)
