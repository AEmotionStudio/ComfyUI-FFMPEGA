"""Shared helpers for the Save/Load Last Frame node pair.

Deliberately torch-free so the slot-naming contract and the tail-index
math can be imported (and unit-tested) without a full ComfyUI install.
The two nodes live in different packages — ``nodes/save_last_frame_node``
and ``loadlast/load_last_frame`` — and this module is the single place
where they agree on where files go and which frames get picked.

Layout written by the Save node::

    output/ffmpega_last_frame/<slot>/lastframe_00.png   # oldest of the batch
    output/ffmpega_last_frame/<slot>/lastframe_01.png
    output/ffmpega_last_frame/<slot>/lastframe_02.png   # the actual last frame

Indices are chronological within the saved batch and zero-padded, so the
Load node can sort by filename instead of racing on mtime.
"""

from __future__ import annotations

import glob
import json
import logging
import os
import re
import subprocess
import tempfile

try:
    from .bin_paths import get_ffmpeg_bin, get_ffprobe_bin
except ImportError:  # pragma: no cover - direct (non-package) import
    from bin_paths import get_ffmpeg_bin, get_ffprobe_bin  # type: ignore

try:
    import folder_paths
except ImportError:  # pragma: no cover - importable outside ComfyUI
    folder_paths = None  # type: ignore[assignment]

logger = logging.getLogger("FFMPEGA")

# Subfolder under ComfyUI's output directory that holds every slot.
LAST_FRAME_ROOT = "ffmpega_last_frame"

DEFAULT_SLOT = "default"
DEFAULT_PREFIX = "lastframe"

# Upper bound on frames pulled out of a video in one call.
MAX_TAIL_FRAMES = 64

_SLOT_SAFE = re.compile(r"[^A-Za-z0-9_-]+")


# ─── Slot naming ────────────────────────────────────────────────────────

def sanitize_slot(name) -> str:
    """Reduce a user-supplied slot name to ``[A-Za-z0-9_-]``.

    This is the path-traversal defense and must run *before* the name is
    joined into any path. ``folder_paths.get_save_image_path`` refuses to
    resolve outside the output directory as a second layer, but relying on
    an exception for routine input would be sloppy.
    """
    if not isinstance(name, str):
        return DEFAULT_SLOT
    cleaned = _SLOT_SAFE.sub("_", name).strip("_-")
    return cleaned or DEFAULT_SLOT


def slot_prefix(slot: str, prefix: str = DEFAULT_PREFIX) -> str:
    """Build the ``filename_prefix`` handed to ``get_save_image_path``.

    Returns a slash-joined prefix — ComfyUI splits it into subfolder +
    filename itself, so this is all that's needed to target the slot dir.
    """
    safe_slot = sanitize_slot(slot)
    safe_prefix = _SLOT_SAFE.sub("_", prefix or DEFAULT_PREFIX).strip("_-")
    return f"{LAST_FRAME_ROOT}/{safe_slot}/{safe_prefix or DEFAULT_PREFIX}"


def slot_dir(slot: str) -> str:
    """Absolute path of a slot's directory. Empty string without ComfyUI."""
    if folder_paths is None:
        return ""
    return os.path.join(
        folder_paths.get_output_directory(), LAST_FRAME_ROOT, sanitize_slot(slot),
    )


def frame_name(index: int, prefix: str = DEFAULT_PREFIX, ext: str = ".png") -> str:
    """Fixed name for position ``index`` within a saved batch."""
    return f"{prefix}_{index:02}{ext}"


# ─── Tail selection ─────────────────────────────────────────────────────

def select_tail_indices(
    total: int, frame_count: int = 1, offset_from_end: int = 0,
) -> list[int]:
    """Pick the trailing ``frame_count`` indices, skipping ``offset_from_end``.

    Returns chronological (ascending) indices, so index 0 of the result is
    the *oldest* frame of the batch and the last entry is the newest.

    Clamps rather than raises: an ``offset_from_end`` past the start of a
    short clip yields ``[0]``, because failing hard at the end of a long
    generation chain is worse than quietly using the only frame available.
    An empty input yields ``[]`` — callers must treat that as "write
    nothing", never as "write a black frame".
    """
    if total <= 0:
        return []
    end = max(1, total - max(0, offset_from_end))
    start = max(0, end - max(1, frame_count))
    return list(range(start, end))


# ─── ffprobe / ffmpeg ───────────────────────────────────────────────────

def _parse_rational(value) -> float:
    """Parse ffprobe rationals like ``"24000/1001"``. 0.0 when unusable."""
    if not value or value in ("0/0", "N/A"):
        return 0.0
    try:
        if "/" in str(value):
            num, den = str(value).split("/", 1)
            den_f = float(den)
            return float(num) / den_f if den_f else 0.0
        return float(value)
    except (ValueError, ZeroDivisionError):
        return 0.0


def probe_video_stats(video_path: str) -> tuple[float, float, int]:
    """Return ``(fps, duration_seconds, frame_count)`` for a video.

    Any field that cannot be determined comes back as 0. ``get_ffprobe_bin``
    falls back to a bare ``"ffprobe"`` when the binary is missing, so the
    subprocess raises ``FileNotFoundError`` rather than returning nonzero —
    hence the broad except.
    """
    cmd = [
        get_ffprobe_bin(), "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=nb_frames,r_frame_rate,avg_frame_rate,duration",
        "-show_entries", "format=duration",
        "-of", "json", video_path,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=30)
        if result.returncode != 0:
            logger.debug("last_frame: ffprobe failed on %s", video_path)
            return 0.0, 0.0, 0
        data = json.loads(result.stdout.decode("utf-8", "replace") or "{}")
    except Exception as e:
        logger.warning("last_frame: ffprobe unavailable or failed: %s", e)
        return 0.0, 0.0, 0

    streams = data.get("streams") or [{}]
    stream = streams[0] if streams else {}

    fps = _parse_rational(stream.get("avg_frame_rate"))
    if fps <= 0:
        fps = _parse_rational(stream.get("r_frame_rate"))

    duration = _parse_rational(stream.get("duration"))
    if duration <= 0:
        duration = _parse_rational((data.get("format") or {}).get("duration"))

    try:
        nb_frames = int(stream.get("nb_frames") or 0)
    except (TypeError, ValueError):
        nb_frames = 0
    if nb_frames <= 0 and fps > 0 and duration > 0:
        nb_frames = int(round(duration * fps))

    return fps, duration, nb_frames


def _run_ffmpeg(cmd: list[str], timeout: int = 60) -> subprocess.CompletedProcess | None:
    try:
        return subprocess.run(cmd, capture_output=True, timeout=timeout)
    except Exception as e:
        logger.warning("last_frame: ffmpeg call failed: %s", e)
        return None


def extract_tail_frames(
    video_path: str,
    frame_count: int = 1,
    offset_from_end: int = 0,
    out_dir: str | None = None,
) -> list[str]:
    """Decode the tail of a video and return the chosen frames as PNG paths.

    Result is chronological. Returns ``[]`` when nothing could be decoded.
    Caller owns ``out_dir`` and is responsible for cleaning it up; when it
    is None a temp dir is created and its path is implied by the returns.

    Note this path is **not** lossless — it re-decodes h264/yuv420p. Prefer
    feeding the Save node an IMAGE tensor when one is available.
    """
    if not video_path or not os.path.isfile(video_path):
        return []

    frame_count = max(1, min(int(frame_count), MAX_TAIL_FRAMES))
    offset_from_end = max(0, int(offset_from_end))

    if out_dir is None:
        out_dir = tempfile.mkdtemp(prefix="ffmpega_tail_")
    os.makedirs(out_dir, exist_ok=True)

    fps, duration, _nb = probe_video_stats(video_path)

    # How far back from EOF to start decoding. Pad generously — a keyframe
    # seek lands at or before the request, and over-decoding a couple of
    # extra frames is far cheaper than coming up short.
    need = frame_count + offset_from_end
    if fps > 0:
        tail_seconds = (need + 2) / fps + 0.5
    else:
        tail_seconds = max(1.0, need * 0.25)
    if duration > 0:
        tail_seconds = min(tail_seconds, duration)

    pattern = os.path.join(out_dir, "tail_%05d.png")
    base_cmd = [
        get_ffmpeg_bin(), "-y", "-v", "error", "-noautorotate",
        # -sseof is an *input* option and must precede -i. Placed after -i
        # it is parsed as an output option and silently does nothing.
        "-sseof", f"-{tail_seconds:.3f}",
        "-i", video_path,
    ]
    result = _run_ffmpeg(
        base_cmd + ["-fps_mode", "passthrough", "-q:v", "1", "-start_number", "0", pattern]
    )

    # -fps_mode replaced -vsync in ffmpeg 5.0; retry for older installs.
    if result is not None and result.returncode != 0:
        stderr = result.stderr.decode("utf-8", "replace")
        if "Unrecognized option" in stderr or "Option not found" in stderr:
            result = _run_ffmpeg(
                base_cmd + ["-vsync", "0", "-q:v", "1", "-start_number", "0", pattern]
            )

    files = sorted(glob.glob(os.path.join(out_dir, "tail_*.png")))

    if files:
        # Index from the *back*. The keyframe seek means the first emitted
        # frame may be well before the requested point, and a failed seek
        # can dump the whole file — indexing from the front would silently
        # return frames from the middle of the video. This is also why
        # -frames:v can't bound the decode: it truncates the wrong end.
        end = max(1, len(files) - offset_from_end)
        chosen = files[max(0, end - frame_count):end]
        if len(files) > need + 64:
            logger.debug(
                "last_frame: -sseof seek looks imprecise on %s (%d frames decoded)",
                os.path.basename(video_path), len(files),
            )
        return chosen

    # Nothing decoded — fall back to the single-frame form already proven
    # in the SVI continuation path (nodes/nollm_modes.py).
    if frame_count == 1 and offset_from_end == 0:
        single = os.path.join(out_dir, "tail_last.png")
        fallback = _run_ffmpeg(
            [
                get_ffmpeg_bin(), "-y", "-v", "error",
                "-sseof", "-0.1", "-i", video_path,
                "-frames:v", "1", "-update", "1", single,
            ],
            timeout=30,
        )
        if (
            fallback is not None
            and os.path.isfile(single)
            and os.path.getsize(single) > 0
        ):
            return [single]

    logger.warning(
        "last_frame: could not extract tail frames from %s", video_path,
    )
    return []


# ─── PNG workflow metadata ──────────────────────────────────────────────

def embed_workflow_png(image_path: str, prompt, extra_pnginfo) -> None:
    """Embed workflow metadata into a PNG so it can be dragged back in.

    No-op when there is nothing to embed or the file isn't a PNG.
    """
    if prompt is None and extra_pnginfo is None:
        return
    if not image_path.lower().endswith(".png"):
        return

    try:
        from PIL import Image
        from PIL.PngImagePlugin import PngInfo

        img = Image.open(image_path)

        metadata = PngInfo()
        if prompt is not None:
            metadata.add_text("prompt", json.dumps(prompt))
        if extra_pnginfo is not None:
            for key in extra_pnginfo:
                metadata.add_text(key, json.dumps(extra_pnginfo[key]))

        img.save(image_path, pnginfo=metadata, compress_level=4)

    except Exception as e:
        logger.warning(
            "last_frame: workflow embed failed for %s: %s",
            os.path.basename(image_path), e,
        )
