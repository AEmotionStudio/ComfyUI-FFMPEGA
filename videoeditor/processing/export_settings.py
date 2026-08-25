"""Export settings parser for the Video Editor.

Parses the export settings JSON and returns FFmpeg arguments for
codec, CRF, resolution, audio codec, and format.
"""

from __future__ import annotations

import json
import logging

log = logging.getLogger("ffmpega.videoeditor")

# Codec → FFmpeg encoder mappings
_VIDEO_CODECS = {
    "h264": "libx264",
    "h265": "libx265",
    "vp9": "libvpx-vp9",
    "av1": "libaom-av1",
}

_AUDIO_CODECS = {
    "aac": "aac",
    "mp3": "libmp3lame",
    "opus": "libopus",
    "flac": "flac",
    "copy": "copy",
}

_FORMAT_EXTENSIONS = {
    "mp4": ".mp4",
    "mkv": ".mkv",
    "webm": ".webm",
    "mov": ".mov",
}

# Defaults matching ExportSettingsPanel
_DEFAULTS = {
    "resolution": "source",
    "video_codec": "h264",
    "crf": 18,
    "preset": "fast",
    "format": "mp4",
    "audio_codec": "aac",
    "audio_bitrate": "192k",
}


def parse_export_settings(settings_json: str) -> dict:
    """Parse export settings JSON into structured settings dict.

    Returns a dict with keys: video_codec, crf, preset, audio_codec,
    audio_bitrate, resolution, format, extension.
    """
    result = {**_DEFAULTS, "extension": ".mp4"}

    if not settings_json or not settings_json.strip() or settings_json == "{}":
        return result

    try:
        data = json.loads(settings_json)
    except (json.JSONDecodeError, TypeError):
        return result

    if not isinstance(data, dict):
        return result

    result["resolution"] = str(data.get("resolution", "source"))
    result["video_codec"] = str(data.get("video_codec", "h264"))
    result["crf"] = max(0, min(51, int(data.get("crf", 18))))
    result["preset"] = str(data.get("preset", "fast"))
    result["format"] = str(data.get("format", "mp4"))
    result["audio_codec"] = str(data.get("audio_codec", "aac"))
    result["audio_bitrate"] = str(data.get("audio_bitrate", "192k"))
    result["extension"] = _FORMAT_EXTENSIONS.get(result["format"], ".mp4")

    return result


def build_video_codec_args(settings: dict) -> list[str]:
    """Build FFmpeg video codec arguments from parsed settings.

    Returns list like ["-c:v", "libx264", "-crf", "18", "-preset", "fast"].
    """
    codec = _VIDEO_CODECS.get(settings.get("video_codec", "h264"), "libx264")
    crf = str(settings.get("crf", 18))
    preset = settings.get("preset", "fast")

    args = ["-c:v", codec, "-crf", crf]

    # VP9 and AV1 use different preset mechanisms
    if codec in ("libvpx-vp9",):
        args.extend(["-b:v", "0", "-deadline", preset])
    elif codec == "libaom-av1":
        # AV1 uses -cpu-used instead of -preset
        speed_map = {"ultrafast": "8", "fast": "6", "medium": "4", "slow": "2", "veryslow": "0"}
        args.extend(["-cpu-used", speed_map.get(preset, "4")])
    else:
        args.extend(["-preset", preset])

    args.extend(["-pix_fmt", "yuv420p"])
    return args


def build_audio_codec_args(settings: dict) -> list[str]:
    """Build FFmpeg audio codec arguments from parsed settings.

    Returns list like ["-c:a", "aac", "-b:a", "192k"].
    """
    codec = _AUDIO_CODECS.get(settings.get("audio_codec", "aac"), "aac")

    if codec == "copy":
        return ["-c:a", "copy"]
    elif codec == "flac":
        return ["-c:a", "flac"]
    else:
        bitrate = settings.get("audio_bitrate", "192k")
        return ["-c:a", codec, "-b:a", bitrate]


def build_resolution_filter(settings: dict) -> str | None:
    """Build FFmpeg scale filter for resolution.

    Returns None if resolution is "source" (no scaling needed).
    """
    resolution = settings.get("resolution", "source")

    if resolution == "source":
        return None

    scale_map = {
        "4k": "3840:-2",
        "1080p": "1920:-2",
        "720p": "1280:-2",
        "480p": "854:-2",
    }

    scale = scale_map.get(resolution)
    if scale:
        return f"scale={scale}"

    # Custom resolution: "WxH" format
    if "x" in resolution:
        try:
            w, h = resolution.split("x")
            return f"scale={int(w)}:{int(h)}"
        except (ValueError, IndexError):
            pass

    return None


def has_export_settings(settings_json: str) -> bool:
    """Check if non-default export settings are configured."""
    if not settings_json or not settings_json.strip() or settings_json == "{}":
        return False
    try:
        data = json.loads(settings_json)
        if not isinstance(data, dict):
            return False
        # Check if any non-default values
        for key, default in _DEFAULTS.items():
            if str(data.get(key, default)) != str(default):
                return True
        return False
    except (json.JSONDecodeError, TypeError):
        return False
