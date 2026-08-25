"""Embed the ComfyUI workflow into the video container itself.

Follows ComfyUI's *native* convention (``prompt`` / ``workflow`` container
tags written with ``-movflags use_metadata_tags``) rather than
VideoHelperSuite's ``comment`` FFMETADATA pass, because the stock ComfyUI
frontend already knows how to read those tags back — dropping the saved mp4
onto the canvas restores the workflow with no client-side code of our own.

Matroska and WebM uppercase their tag keys (they came back as ``PROMPT`` /
``WORKFLOW`` when probed), so those containers additionally get a ``comment``
tag holding the workflow for readers that only look there.
"""

from __future__ import annotations

import json
import logging

logger = logging.getLogger("FFMPEGA")

#: Containers whose muxer needs ``use_metadata_tags`` to keep arbitrary keys.
_MOV_LIKE = (".mp4", ".mov", ".m4v")

#: Containers that uppercase tag names and are better served by `comment`.
_MATROSKA_LIKE = (".mkv", ".webm")


def _serialize(value) -> str | None:
    """JSON-encode a metadata value, returning None if it cannot be encoded."""
    if value is None:
        return None
    try:
        return json.dumps(value)
    except (TypeError, ValueError) as e:
        logger.warning("Metadata: could not serialize value: %s", e)
        return None


def metadata_args(
    prompt=None,
    extra_pnginfo: dict | None = None,
    ext: str = ".mp4",
    max_bytes: int = 4 * 1024 * 1024,
) -> list[str]:
    """ffmpeg args embedding ``prompt``/``workflow`` into the container.

    Args:
        prompt: The ComfyUI PROMPT dict (api-format graph).
        extra_pnginfo: The EXTRA_PNGINFO dict; its ``workflow`` key holds the
            drag-and-drop graph.
        ext: Target container extension, which decides the tag convention.
        max_bytes: Skip any single tag larger than this.  Very large graphs
            can push an mp4 ``udta`` atom past what some players tolerate,
            and the sidecar PNG still carries the full workflow.

    Returns:
        The ``-metadata`` args only, empty when there is nothing to embed.
        The mp4 muxer additionally needs the ``use_metadata_tags`` movflag —
        get it from :func:`required_movflags` and fold it into the single
        ``-movflags`` token, since a repeated flag would override faststart.
    """
    ext = (ext or ".mp4").lower()
    entries: dict[str, str] = {}

    encoded = _serialize(prompt)
    if encoded:
        entries["prompt"] = encoded

    workflow_json = None
    for key, value in (extra_pnginfo or {}).items():
        encoded = _serialize(value)
        if encoded:
            entries[key] = encoded
            if key == "workflow":
                workflow_json = encoded

    # Matroska/WebM uppercase keys, so mirror the workflow into `comment`
    # for readers that only inspect the standard field.
    if workflow_json and ext in _MATROSKA_LIKE and "comment" not in entries:
        entries["comment"] = workflow_json

    args: list[str] = []
    for key, value in entries.items():
        if len(value.encode("utf-8")) > max_bytes:
            logger.warning(
                "Metadata: skipping %r (%d bytes exceeds limit)",
                key, len(value.encode("utf-8")),
            )
            continue
        args += ["-metadata", f"{key}={value}"]

    return args


def required_movflags(ext: str, has_entries: bool) -> tuple[str, ...]:
    """movflag tokens the container needs to keep custom metadata keys.

    Returned as bare tokens so the caller can fold them into one
    ``-movflags`` value alongside ``faststart``.
    """
    if not has_entries:
        return ()
    if (ext or "").lower() in _MOV_LIKE:
        # Without this the mp4 muxer silently drops non-standard keys.
        return ("use_metadata_tags",)
    return ()


def has_metadata(prompt=None, extra_pnginfo: dict | None = None) -> bool:
    """Whether there is anything worth embedding."""
    return bool(prompt) or bool(extra_pnginfo)
