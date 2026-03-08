"""FFMPEGA server routes for ComfyUI.

Registers custom API endpoints on ComfyUI's aiohttp PromptServer
for features that need to serve content outside the standard
input/output/temp directories (e.g. live video preview of files
at arbitrary filesystem paths).
"""

import asyncio
import atexit
import json
import logging
import os
import threading
import time

import server
from .core.bin_paths import get_ffmpeg_bin, get_ffprobe_bin

log = logging.getLogger("ffmpega")
web = server.web


# --- Path sandboxing (delegates to shared utility) ---


def _is_path_sandboxed(filepath: str) -> bool:
    """Check that a resolved path is inside an allowed directory."""
    try:
        from .loadlast.discovery.path_utils import is_path_sandboxed
        return is_path_sandboxed(filepath)
    except ImportError:
        log.warning(
            "path_utils.is_path_sandboxed unavailable — denying path %r",
            filepath,
        )
        return False


def _resolve_video_path(raw_path: str) -> str | None:
    """Resolve a video path that may be absolute or ComfyUI-relative.

    Handles:
    - Absolute paths within ComfyUI's allowed directories
    - ComfyUI input dir: input/video.mp4
    - ComfyUI output dir: output/video.mp4
    - ComfyUI temp dir: temp/video.mp4

    Returns:
        Resolved absolute path if the file exists and is within an
        allowed directory, or None.
    """
    import folder_paths

    if not raw_path:
        return None

    # Try as absolute path first — but only if sandboxed
    abspath = os.path.abspath(raw_path)
    if os.path.isfile(abspath) and _is_path_sandboxed(abspath):
        return abspath

    # Try resolving relative to ComfyUI directories
    for prefix, getter in [
        ("input/", folder_paths.get_input_directory),
        ("output/", folder_paths.get_output_directory),
        ("temp/", folder_paths.get_temp_directory),
    ]:
        if raw_path.startswith(prefix):
            relative = raw_path[len(prefix):]
            candidate = os.path.join(getter(), relative)
            if os.path.isfile(candidate) and _is_path_sandboxed(candidate):
                return candidate

    # Try as-is in input directory (bare filename)
    candidate = os.path.join(folder_paths.get_input_directory(), raw_path)
    if os.path.isfile(candidate) and _is_path_sandboxed(candidate):
        return candidate

    return None


# ---------------------------------------------------------------------------
#  /ffmpega/preview — Seekable MP4 preview with proper range request support
# ---------------------------------------------------------------------------

# Cache of recently-transcoded preview files: key -> temp file path
# Key is (source_path, mtime, file_size, start_time, duration)
_preview_cache: dict[tuple[str, float, int, float, float], str] = {}
_PREVIEW_CACHE_MAX = 5
_preview_lock: asyncio.Lock | None = None
# Per-key locks to prevent duplicate concurrent transcodes for the same file
_transcode_locks: dict[tuple, asyncio.Lock] = {}


def _get_preview_lock() -> asyncio.Lock:
    """Lazily create the asyncio.Lock inside the running event loop.

    Safe without extra synchronisation because aiohttp route handlers
    run on a single event-loop thread — two coroutines cannot race
    through the ``if`` check simultaneously.
    """
    global _preview_lock
    if _preview_lock is None:
        _preview_lock = asyncio.Lock()
    return _preview_lock


def _evict_preview_cache():
    """Remove oldest entries when cache exceeds max size.

    Relies on Python 3.7+ dict insertion-order guarantee for FIFO eviction.
    Also prunes stale per-key lock entries to prevent unbounded growth.
    """
    while len(_preview_cache) > _PREVIEW_CACHE_MAX:
        oldest_key = next(iter(_preview_cache))
        old_path = _preview_cache.pop(oldest_key)
        _transcode_locks.pop(oldest_key, None)
        try:
            os.unlink(old_path)
        except OSError:
            pass


def _cleanup_preview_cache():
    """Remove all cached preview temp files (called at interpreter exit)."""
    for p in list(_preview_cache.values()):
        try:
            os.unlink(p)
        except OSError:
            pass
    _preview_cache.clear()


atexit.register(_cleanup_preview_cache)


# Timestamp recorded at import time so startup cleanup only removes
# files from *previous* processes, not ones we create later.
_PROCESS_START = time.time()


def _startup_cleanup_previews() -> None:
    """Remove orphaned preview temp files left by prior crashes/SIGKILL.

    Only deletes files whose mtime is older than the current process start
    to avoid nuking in-use cache entries if the module is re-imported during
    a hot-reload.
    """
    import glob
    import tempfile
    pattern = os.path.join(tempfile.gettempdir(), "ffmpega_preview_*.mp4")
    for path in glob.glob(pattern):
        try:
            if os.path.getmtime(path) < _PROCESS_START:
                os.unlink(path)
        except OSError:
            pass


# Run cleanup in a daemon thread to avoid blocking import / startup.
threading.Thread(
    target=_startup_cleanup_previews,
    name="ffmpega-preview-cleanup",
    daemon=True,
).start()


async def _transcode_preview(filepath: str, start_time: float,
                              duration: float, ffmpeg_bin: str) -> str | None:
    """Transcode source video to a seekable MP4 temp file.

    Returns the path to the temp file, or None on error.
    Uses -movflags +faststart so the moov atom is at the beginning,
    enabling the browser to seek immediately.
    """
    import tempfile
    tmp = tempfile.NamedTemporaryFile(
        suffix=".mp4", prefix="ffmpega_preview_", delete=False,
    )
    tmp_path = tmp.name
    tmp.close()

    args = [ffmpeg_bin, "-v", "error", "-y"]

    # Seek (pre-input for fast seek on large files)
    if start_time > 0:
        if start_time > 4:
            # Fast seek to 4s before target, then precise post-input seek
            args += ["-ss", str(start_time - 4)]
            post_seek = ["-ss", "4"]
        else:
            # Short offset — pre-input fast seek is still faster than demuxer
            args += ["-ss", str(start_time)]
            post_seek = []
    else:
        post_seek = []

    args += ["-i", filepath] + post_seek

    # Duration limit
    if duration > 0:
        args += ["-t", str(duration)]
    else:
        args += ["-t", "30"]  # Cap preview at 30s

    # Output: MP4 with faststart for seeking
    args += [
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-crf", "28",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "128k",
        "-movflags", "+faststart",
        tmp_path,
    ]

    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
            stdin=asyncio.subprocess.DEVNULL,
        )
        try:
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            log.warning("Preview transcode timed out (120s)")
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            return None

        if proc.returncode != 0:
            log.warning("Preview transcode failed: %s",
                        stderr.decode("utf-8", errors="replace"))
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            return None

        return tmp_path

    except Exception as e:
        log.warning("Preview transcode error: %s", e)
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        return None


@server.PromptServer.instance.routes.get("/ffmpega/preview")
async def preview_video(request):
    """Serve a seekable MP4 preview with HTTP Range support.

    Query params:
        path        — absolute or ComfyUI-relative path to the video (required)
        start_time  — start offset in seconds (default: 0)
        duration    — clip duration in seconds (default: 30, 0 = full up to 30s)

    The video is transcoded to MP4 (h264 + faststart) on first request
    and cached. Subsequent requests for the same file serve from cache.
    Full HTTP Range request support enables precise browser seeking.
    """
    query = request.rel_url.query

    # --- Validate path ---
    raw_path = query.get("path", "").strip()
    filepath = _resolve_video_path(raw_path)
    if not filepath:
        return web.Response(status=404, text="File not found")

    ffmpeg_bin = get_ffmpeg_bin()
    if not ffmpeg_bin:
        return web.Response(status=500, text="ffmpeg not found in PATH")

    # --- Parse numeric params with validation ---
    try:
        start_time = float(query.get("start_time", 0))
    except (ValueError, TypeError):
        return web.Response(status=400, text="Invalid start_time")

    duration_raw = query.get("duration")
    try:
        duration = float(duration_raw) if duration_raw else 0
    except (ValueError, TypeError):
        return web.Response(status=400, text="Invalid duration")

    mtime = os.path.getmtime(filepath)
    fsize = os.path.getsize(filepath)
    cache_key = (filepath, mtime, fsize, start_time, duration)

    # --- Check cache ---
    async with _get_preview_lock():
        cached_path = _preview_cache.get(cache_key)
        if cached_path and os.path.isfile(cached_path):
            return _serve_file_with_ranges(cached_path)

    # --- Per-key lock prevents duplicate transcodes for the same file ---
    async with _get_preview_lock():
        if cache_key not in _transcode_locks:
            _transcode_locks[cache_key] = asyncio.Lock()
        key_lock = _transcode_locks[cache_key]

    async with key_lock:
        # Re-check cache — another request may have finished while we waited
        async with _get_preview_lock():
            cached_path = _preview_cache.get(cache_key)
            if cached_path and os.path.isfile(cached_path):
                return _serve_file_with_ranges(cached_path)

        # Transcode (only one request per cache key proceeds here)
        tmp_path = await _transcode_preview(
            filepath, start_time, duration, ffmpeg_bin,
        )
        if not tmp_path:
            return web.Response(status=500, text="Transcode failed")

        async with _get_preview_lock():
            _preview_cache[cache_key] = tmp_path
            _evict_preview_cache()

    return _serve_file_with_ranges(tmp_path)


def _serve_file_with_ranges(file_path: str):
    """Serve a file with proper HTTP Range request support for seeking.

    Uses aiohttp's FileResponse for efficient streaming with built-in
    Range support, ETag, and Last-Modified headers.
    """
    return web.FileResponse(
        file_path,
        content_type="video/mp4",
        headers={
            "Cache-Control": "public, max-age=60",
            "Content-Disposition": 'inline; filename="preview.mp4"',
        },
    )


# ---------------------------------------------------------------------------
#  /ffmpega/video_info — Get video metadata (resolution, duration, fps)
# ---------------------------------------------------------------------------

@server.PromptServer.instance.routes.get("/ffmpega/video_info")
async def video_info(request):
    """Return basic video metadata as JSON.

    Query params:
        path — absolute path to the video file (required)

    Returns JSON:
        { "width": N, "height": N, "duration": N, "fps": N, "frames": N }
    """
    query = request.rel_url.query
    raw_path = query.get("path", "").strip()
    filepath = _resolve_video_path(raw_path)

    if not filepath:
        return web.json_response({}, status=404)

    ffprobe_bin = get_ffprobe_bin()
    if not ffprobe_bin:
        return web.json_response({}, status=500)

    try:
        result = await asyncio.create_subprocess_exec(
            ffprobe_bin,
            "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height,r_frame_rate,nb_frames",
            "-show_entries", "format=duration",
            "-of", "json",
            filepath,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await result.communicate()
        data = json.loads(stdout.decode("utf-8", errors="replace"))

        stream = data.get("streams", [{}])[0]
        fmt = data.get("format", {})

        width = stream.get("width", 0)
        height = stream.get("height", 0)
        duration = float(fmt.get("duration", 0))

        # Parse fps from fraction string like "30/1"
        fps_str = stream.get("r_frame_rate", "30/1")
        if "/" in fps_str:
            num, den = fps_str.split("/")
            fps = float(num) / float(den) if float(den) != 0 else 30.0
        else:
            fps = float(fps_str) if fps_str else 30.0

        nb_frames = stream.get("nb_frames", "N/A")
        try:
            frames = int(nb_frames)
        except (ValueError, TypeError):
            frames = round(duration * fps)

        return web.json_response({
            "width": width,
            "height": height,
            "duration": round(duration, 2),
            "fps": round(fps, 2),
            "frames": frames,
        })

    except Exception as e:
        log.warning("video_info error: %s", e)
        return web.json_response({}, status=500)


# ── Video Editor Export ──────────────────────────────────────────────


@server.PromptServer.instance.routes.post("/ffmpega/video_export")
async def video_export(request):
    """Render video edits and save to disk.

    Body JSON:
        source_path  — path to source video (required)
        segments     — [[start, end], ...]
        crop         — {x, y, w, h} or null
        speed_map    — {segment_index: speed} or {}
        volume       — float 0.0–2.0
        text_overlays — [{text, x, y, ...}, ...]
        transitions  — [{after_segment, type, duration}, ...]
        output_name  — optional output filename

    Returns JSON:
        { success, output_path, duration, file_size, error }
    """
    import folder_paths

    try:
        body = await request.json()
    except Exception:
        return web.json_response(
            {"success": False, "error": "Invalid JSON body"}, status=400,
        )

    source_path = _resolve_video_path(body.get("source_path", ""))
    if not source_path:
        return web.json_response(
            {"success": False, "error": "Source file not found"}, status=404,
        )

    # Build output path — sanitize to prevent path traversal
    output_name = os.path.basename(body.get("output_name", ""))
    if not output_name:
        output_name = f"videoeditor_export_{int(time.time())}.mp4"
    if not output_name.endswith(".mp4"):
        output_name += ".mp4"

    output_dir = folder_paths.get_output_directory()
    output_path = os.path.join(output_dir, output_name)

    # Run export in a thread to avoid blocking the event loop
    from .videoeditor.processing.export import render_edits

    # Serialize once — render_edits expects JSON strings
    segments_json = json.dumps(body.get("segments", []))
    crop_val = body.get("crop")
    crop_json = json.dumps(crop_val) if crop_val else ""
    speed_map_json = json.dumps(body.get("speed_map", {}))
    text_overlays_json = json.dumps(body.get("text_overlays", []))
    transitions_json = json.dumps(body.get("transitions", []))
    try:
        volume = float(body.get("volume", 1.0))
    except (ValueError, TypeError):
        return web.json_response(
            {"success": False, "error": "Invalid volume value"}, status=400,
        )
    volume = max(0.0, min(2.0, volume))

    # NOTE: cancel_event is only triggered by the 15-min timeout below.
    # There is currently no client-facing cancel endpoint — this is a
    # known limitation.  render_edits() checks the event between pipeline
    # stages, so a slow single-stage render will not be interrupted until
    # the current FFmpeg subprocess finishes.
    cancel_event = threading.Event()

    def _do_export():
        return render_edits(
            source_path,
            output_path,
            segments_json=segments_json,
            crop_json=crop_json,
            speed_map_json=speed_map_json,
            volume=volume,
            text_overlays_json=text_overlays_json,
            transitions_json=transitions_json,
            cancel_event=cancel_event,
        )

    loop = asyncio.get_running_loop()
    try:
        result = await asyncio.wait_for(
            loop.run_in_executor(None, _do_export),
            timeout=900,  # 15 min hard cap
        )
    except asyncio.TimeoutError:
        cancel_event.set()  # signal render_edits to stop between steps
        log.warning("Export timed out (15 min); cancellation signalled.")
        # Clean up partial output
        try:
            if os.path.isfile(output_path):
                os.unlink(output_path)
        except OSError:
            pass
        return web.json_response(
            {"success": False, "error": "Export timed out (15 min limit)"},
            status=504,
        )

    # Sanitize output_path — don't leak absolute server paths to the client
    if "output_path" in result:
        result["output_path"] = os.path.basename(result["output_path"])

    status = 200 if result.get("success") else 500
    return web.json_response(result, status=status)


# ── Text Presets ─────────────────────────────────────────────────────

_PRESETS_FILE = os.path.join(os.path.dirname(__file__), "text_presets.json")


@server.PromptServer.instance.routes.get("/ffmpega/text_presets")
async def _get_text_presets(request):
    """Return saved custom text presets."""
    try:
        if os.path.isfile(_PRESETS_FILE):
            with open(_PRESETS_FILE, "r", encoding="utf-8") as f:
                presets = json.load(f)
        else:
            presets = []
        return web.json_response(presets)
    except Exception as e:
        log.warning("text_presets GET error: %s", e)
        return web.json_response([], status=500)


@server.PromptServer.instance.routes.post("/ffmpega/text_presets")
async def _save_text_presets(request):
    """Save custom text presets (replaces entire list)."""
    try:
        data = await request.json()
        if not isinstance(data, list):
            return web.json_response({"error": "expected array"}, status=400)
        with open(_PRESETS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return web.json_response({"ok": True})
    except Exception as e:
        log.warning("text_presets POST error: %s", e)
        return web.json_response({"error": str(e)}, status=500)


# ── Effects Builder Presets ──────────────────────────────────────────

_EFFECTS_PRESETS_FILE = os.path.join(os.path.dirname(__file__), "effects_presets.json")


@server.PromptServer.instance.routes.get("/ffmpega/effects_presets")
async def _get_effects_presets(request):
    """Return saved custom effects builder presets."""
    try:
        if os.path.isfile(_EFFECTS_PRESETS_FILE):
            with open(_EFFECTS_PRESETS_FILE, "r", encoding="utf-8") as f:
                presets = json.load(f)
        else:
            presets = []
        return web.json_response(presets)
    except Exception as e:
        log.warning("effects_presets GET error: %s", e)
        return web.json_response([], status=500)


@server.PromptServer.instance.routes.post("/ffmpega/effects_presets")
async def _save_effects_presets(request):
    """Save custom effects builder presets (replaces entire list)."""
    try:
        data = await request.json()
        if not isinstance(data, list):
            return web.json_response({"error": "expected array"}, status=400)
        with open(_EFFECTS_PRESETS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return web.json_response({"ok": True})
    except Exception as e:
        log.warning("effects_presets POST error: %s", e)
        return web.json_response({"error": str(e)}, status=500)

