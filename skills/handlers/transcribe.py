"""FFMPEGA Transcription skill handlers.

Handles auto-transcription and karaoke subtitle generation using Whisper.
Supports single video and multi-video (concat) workflows.
"""

import atexit
import os
import tempfile

try:
    from ..handler_contract import make_result
except ImportError:
    from skills.handler_contract import make_result

try:
    from ...core.sanitize import sanitize_text_param, ffmpeg_escape_path
except ImportError:
    from core.sanitize import sanitize_text_param, ffmpeg_escape_path


def _collect_video_paths(p):
    """Collect all video paths from handler params (primary + extras).

    Returns ordered list: [primary_video, extra_video_1, extra_video_2, ...]
    Only includes paths that look like video files.
    """
    _VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".flv", ".wmv", ".m4v", ".ts"}

    paths = []
    primary = p.get("_input_path", "")
    if primary and os.path.isfile(primary):
        paths.append(primary)

    for ep in p.get("_extra_input_paths", []):
        if ep and os.path.isfile(ep):
            ext = os.path.splitext(ep)[1].lower()
            if ext in _VIDEO_EXTS:
                paths.append(ep)

    return paths


def _f_auto_transcribe(p):
    """Auto-transcribe video audio with Whisper and burn subtitles.

    Extracts audio from all connected videos, runs Whisper speech-to-text,
    generates SRT subtitles with correct timing across concatenated clips,
    and burns them into the video.
    """
    try:
        from ...core.whisper_transcriber import (
            transcribe_audio,
            transcribe_multi_video,
            segments_to_srt,
        )
    except ImportError:
        from core.whisper_transcriber import (
            transcribe_audio,
            transcribe_multi_video,
            segments_to_srt,
        )

    video_paths = _collect_video_paths(p)
    if not video_paths:
        raise ValueError(
            "auto_transcribe requires a video input with audio. "
            "No input video path available."
        )

    fontsize = int(p.get("fontsize", 24))
    fontcolor = sanitize_text_param(str(p.get("fontcolor", "white")))

    # Read whisper preferences from node settings
    whisper_device = p.get("_whisper_device", "gpu")
    whisper_model = p.get("_whisper_model", "large-v3")

    # Prefer connected audio input (audio_a) when available.
    # When audio_a is connected, it replaces the video's embedded audio,
    # so we transcribe it directly — its timeline IS the output timeline.
    audio_input_path = p.get("_audio_input_path", "")
    if audio_input_path and os.path.isfile(audio_input_path):
        import logging
        _log = logging.getLogger("ffmpega")
        _log.info("Transcribing connected audio input: %s", audio_input_path)
        if len(video_paths) > 1:
            _log.info(
                "Note: using connected audio_a for subtitle timing "
                "(ignoring individual video durations)"
            )
        result = transcribe_audio(audio_input_path, model_size=whisper_model, device=whisper_device)
    elif len(video_paths) > 1:
        result = transcribe_multi_video(video_paths, model_size=whisper_model, device=whisper_device)
    else:
        result = transcribe_audio(video_paths[0], model_size=whisper_model, device=whisper_device)

    if not result.segments:
        import logging
        logging.getLogger("ffmpega").warning(
            "Whisper found no speech in audio — skipping subtitle burn"
        )
        return make_result()

    # Generate SRT
    srt_content = segments_to_srt(result.segments)

    # Write to temp file
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".srt", delete=False, encoding="utf-8"
    )
    tmp.write(srt_content)
    tmp.close()
    atexit.register(os.unlink, tmp.name)

    # Build subtitle filter (same approach as _f_burn_subtitles)
    _COLOR_MAP = {
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
    if fontcolor_lower in _COLOR_MAP:
        ass_color = _COLOR_MAP[fontcolor_lower]
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

    escaped_path = ffmpeg_escape_path(tmp.name)
    style = f"FontSize={fontsize},PrimaryColour={ass_color}"
    escaped_style = ffmpeg_escape_path(style)
    vf = f"subtitles={escaped_path}:force_style={escaped_style}"

    return make_result(vf=[vf])


def _f_karaoke_subtitles(p):
    """Auto-transcribe and burn karaoke-style word-by-word subtitles.

    Uses Whisper's word-level timestamps to generate ASS subtitles
    with \\kf karaoke timing tags for progressive fill effect.
    Supports multi-video (concat) workflows.
    """
    try:
        from ...core.whisper_transcriber import (
            transcribe_audio,
            transcribe_multi_video,
            words_to_karaoke_ass,
        )
    except ImportError:
        from core.whisper_transcriber import (
            transcribe_audio,
            transcribe_multi_video,
            words_to_karaoke_ass,
        )

    video_paths = _collect_video_paths(p)
    if not video_paths:
        raise ValueError(
            "karaoke_subtitles requires a video input with audio. "
            "No input video path available."
        )

    fontsize = int(p.get("fontsize", 48))
    base_color = sanitize_text_param(str(p.get("base_color", "white")))
    fill_color = sanitize_text_param(str(p.get("fill_color", "yellow")))

    # Read whisper preferences from node settings
    whisper_device = p.get("_whisper_device", "gpu")
    whisper_model = p.get("_whisper_model", "large-v3")

    # Prefer connected audio input (audio_a) when available.
    # When audio_a is connected, it replaces the video's embedded audio,
    # so we transcribe it directly — its timeline IS the output timeline.
    audio_input_path = p.get("_audio_input_path", "")
    if audio_input_path and os.path.isfile(audio_input_path):
        import logging
        _log = logging.getLogger("ffmpega")
        _log.info("Transcribing connected audio input for karaoke: %s", audio_input_path)
        if len(video_paths) > 1:
            _log.info(
                "Note: using connected audio_a for karaoke timing "
                "(ignoring individual video durations)"
            )
        result = transcribe_audio(audio_input_path, model_size=whisper_model, device=whisper_device)
    elif len(video_paths) > 1:
        result = transcribe_multi_video(video_paths, model_size=whisper_model, device=whisper_device)
    else:
        result = transcribe_audio(video_paths[0], model_size=whisper_model, device=whisper_device)

    if not result.words:
        import logging
        logging.getLogger("ffmpega").warning(
            "Whisper found no words in audio — skipping karaoke burn"
        )
        return make_result()

    # Generate ASS with karaoke tags
    ass_content = words_to_karaoke_ass(
        result.words,
        fontsize=fontsize,
        base_color=base_color,
        fill_color=fill_color,
    )

    # Write to temp file
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".ass", delete=False, encoding="utf-8"
    )
    tmp.write(ass_content)
    tmp.close()
    atexit.register(os.unlink, tmp.name)

    # Use ass= filter for ASS subtitles
    escaped_path = ffmpeg_escape_path(tmp.name)
    vf = f"ass={escaped_path}"

    return make_result(vf=[vf])

