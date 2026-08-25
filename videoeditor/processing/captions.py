"""Convert transcription segments to TextOverlay arrays.

Provides utilities for converting Whisper/transcription output
into the TextOverlay format used by the video editor.

This module operates purely on data structures — no FFmpeg or
Whisper dependencies. Actual transcription is triggered via the
server endpoint, and the results are converted here.
"""

from __future__ import annotations

import json
import logging

log = logging.getLogger("ffmpega.videoeditor")

# Default caption styling (bottom-center subtitle look)
_CAPTION_DEFAULTS = {
    "font": "sans-serif",
    "font_size": 32,
    "color": "#ffffff",
    "alignment": "center",
    "x": "center",
    "y": "bottom",
    "bold": False,
    "italic": False,
    "backgroundColor": "#000000",
    "backgroundOpacity": 0.6,
    "outlineColor": None,
    "outlineWidth": 0,
}


def segments_to_overlays(
    segments: list[dict],
    *,
    style: dict | None = None,
    max_chars: int = 60,
    merge_gap: float = 0.3,
) -> list[dict]:
    """Convert transcription segments to TextOverlay dicts.

    Parameters
    ----------
    segments:
        List of ``{"text": str, "start": float, "end": float}`` dicts
        from Whisper or similar transcription.
    style:
        Optional style overrides (font, font_size, color, etc.)
    max_chars:
        Maximum characters per overlay line. Longer segments are
        kept as-is (no word-wrap splitting in this version).
    merge_gap:
        Maximum gap (seconds) between segments to merge into one overlay.

    Returns
    -------
    list[dict]
        List of TextOverlay-compatible dicts with ``text``, ``start_time``,
        ``end_time``, and styling fields.
    """
    if not segments:
        return []

    base = {**_CAPTION_DEFAULTS}
    if style:
        base.update(style)

    # Merge nearby segments with small gaps
    merged = _merge_segments(segments, merge_gap, max_chars)

    overlays: list[dict] = []
    for seg in merged:
        text = str(seg.get("text", "")).strip()
        if not text:
            continue

        start = float(seg.get("start", 0))
        end = float(seg.get("end", start + 1))

        overlay = {
            **base,
            "text": text,
            "start_time": round(start, 2),
            "end_time": round(end, 2),
        }
        overlays.append(overlay)

    return overlays


def _merge_segments(
    segments: list[dict],
    max_gap: float,
    max_chars: int,
) -> list[dict]:
    """Merge consecutive segments with small gaps into single overlays."""
    if not segments:
        return []

    merged: list[dict] = []
    current = {**segments[0]}

    for seg in segments[1:]:
        gap = float(seg.get("start", 0)) - float(current.get("end", 0))
        combined_text = f"{current.get('text', '')} {seg.get('text', '')}".strip()

        if gap <= max_gap and len(combined_text) <= max_chars:
            # Merge
            current["text"] = combined_text
            current["end"] = seg.get("end", current.get("end", 0))
        else:
            merged.append(current)
            current = {**seg}

    merged.append(current)
    return merged


def parse_srt_to_segments(srt_text: str) -> list[dict]:
    """Parse SRT subtitle text into segment dicts.

    Handles the standard SRT format:
    ```
    1
    00:00:01,000 --> 00:00:03,500
    Hello world
    ```

    Returns list of ``{"text": str, "start": float, "end": float}``.
    """
    if not srt_text or not srt_text.strip():
        return []

    segments: list[dict] = []
    blocks = srt_text.strip().split("\n\n")

    for block in blocks:
        lines = block.strip().split("\n")
        if len(lines) < 3:
            continue

        # Line 2 is the timestamp
        timestamp = lines[1]
        if "-->" not in timestamp:
            continue

        parts = timestamp.split("-->")
        if len(parts) != 2:
            continue

        start = _srt_time_to_seconds(parts[0].strip())
        end = _srt_time_to_seconds(parts[1].strip())
        text = "\n".join(lines[2:]).strip()

        if start is not None and end is not None and text:
            segments.append({"text": text, "start": start, "end": end})

    return segments


def _srt_time_to_seconds(time_str: str) -> float | None:
    """Convert SRT timestamp (HH:MM:SS,mmm) to seconds."""
    try:
        time_str = time_str.replace(",", ".")
        parts = time_str.split(":")
        if len(parts) == 3:
            h, m, s = parts
            return int(h) * 3600 + int(m) * 60 + float(s)
        elif len(parts) == 2:
            m, s = parts
            return int(m) * 60 + float(s)
    except (ValueError, IndexError):
        pass
    return None
