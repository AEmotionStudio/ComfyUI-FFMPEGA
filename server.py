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
    """Check that a resolved path is inside an allowed directory.

    Accepts ComfyUI's managed directories (output, temp, input) as well
    as the system tempdir, where upstream FFMPEGA nodes create preview-mode
    renders via ``tempfile.mkdtemp``.
    """
    try:
        from .loadlast.discovery.path_utils import is_path_sandboxed
        if is_path_sandboxed(filepath):
            return True
    except ImportError:
        log.warning(
            "path_utils.is_path_sandboxed unavailable — checking tempdir only for %r",
            filepath,
        )

    # Also accept the system temp directory — upstream FFMPEGA nodes
    # write preview renders to /tmp/ffmpega_*/
    import tempfile
    real = os.path.realpath(filepath)
    sys_tmp = os.path.realpath(tempfile.gettempdir())
    return real == sys_tmp or real.startswith(sys_tmp + os.sep)


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
        headers={
            "Content-Type": "video/mp4",
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
    audio_segments_json = json.dumps(body.get("audio_segments", []))
    color_grading_json = json.dumps(body.get("color_grading", {}))
    filter_preset_json = json.dumps(body.get("filter_preset", {}))
    shader_preset_json = json.dumps(body.get("shader_preset", {}))
    keyframes_json = json.dumps(body.get("keyframes", {}))
    relight_json = json.dumps(body.get("relight_params", {}))
    export_settings_json = json.dumps(body.get("export_settings", {}))
    compose_json = json.dumps(body.get("compose_layers", {}))
    ai_compose_json = json.dumps(body.get("ai_compose", {}))
    transform_json = json.dumps(body.get("transform", {}))
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
            audio_segments_json=audio_segments_json,
            color_grading_json=color_grading_json,
            filter_preset_json=filter_preset_json,
            shader_preset_json=shader_preset_json,
            keyframes_json=keyframes_json,
            relight_json=relight_json,
            export_settings_json=export_settings_json,
            compose_json=compose_json,
            ai_compose_json=ai_compose_json,
            transform_json=transform_json,
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


# ── Waveform extraction ─────────────────────────────────────────────


@server.PromptServer.instance.routes.get("/ffmpega/waveform")
async def waveform_peaks(request):
    """Extract audio waveform peaks from a video file.

    Query params:
        path — absolute or ComfyUI-relative path to the video (required)

    Returns JSON:
        { "peaks": [float, ...], "duration": float, "sampleRate": int }

    Peaks are 2000 bins normalised to 0–1. On failure, returns flat
    peaks (all 0.1) with duration/sampleRate = 0.
    """
    from .videoeditor.processing.waveform import FLAT_WAVEFORM, extract_waveform_peaks

    query = request.rel_url.query
    raw_path = query.get("path", "").strip()
    filepath = _resolve_video_path(raw_path)
    if not filepath:
        return web.json_response(dict(FLAT_WAVEFORM), status=404)

    try:
        result = await asyncio.wait_for(
            extract_waveform_peaks(filepath),
            timeout=60,
        )
    except asyncio.TimeoutError:
        log.warning("[Waveform] Extraction timed out for %s", filepath)
        return web.json_response(dict(FLAT_WAVEFORM), status=504)
    except Exception as e:
        log.warning("[Waveform] Extraction error: %s", e)
        return web.json_response(dict(FLAT_WAVEFORM), status=500)

    return web.json_response(result)


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


# ── Shader Overlay Presets ───────────────────────────────────────────

_SHADER_PRESETS_FILE = os.path.join(os.path.dirname(__file__), "shader_presets.json")


@server.PromptServer.instance.routes.get("/ffmpega/shader_presets")
async def _get_shader_presets(request):
    """Return saved custom shader overlay presets."""
    try:
        if os.path.isfile(_SHADER_PRESETS_FILE):
            with open(_SHADER_PRESETS_FILE, "r", encoding="utf-8") as f:
                presets = json.load(f)
        else:
            presets = []
        return web.json_response(presets)
    except Exception as e:
        log.warning("shader_presets GET error: %s", e)
        return web.json_response([], status=500)


@server.PromptServer.instance.routes.post("/ffmpega/shader_presets")
async def _save_shader_presets(request):
    """Save custom shader overlay presets (replaces entire list)."""
    try:
        data = await request.json()
        if not isinstance(data, list):
            return web.json_response({"error": "expected array"}, status=400)
        with open(_SHADER_PRESETS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return web.json_response({"ok": True})
    except Exception as e:
        log.warning("shader_presets POST error: %s", e)
        return web.json_response({"error": str(e)}, status=500)


# ── SAM3 Point Mask (live preview for click-to-mask) ─────────────────

# Cache of first-frame extractions: video_path → (mtime, temp_png_path)
_first_frame_cache: dict[str, tuple[float, str]] = {}
_FIRST_FRAME_CACHE_MAX = 10


def _evict_first_frame_cache():
    """Remove oldest entries when cache exceeds max."""
    while len(_first_frame_cache) > _FIRST_FRAME_CACHE_MAX:
        oldest_key = next(iter(_first_frame_cache))
        _, old_path = _first_frame_cache.pop(oldest_key)
        try:
            os.unlink(old_path)
        except OSError:
            pass


def _cleanup_first_frame_cache():
    """Remove all cached first-frame temp files at exit."""
    for _, path in list(_first_frame_cache.values()):
        try:
            os.unlink(path)
        except OSError:
            pass
    _first_frame_cache.clear()


atexit.register(_cleanup_first_frame_cache)


@server.PromptServer.instance.routes.post("/ffmpega/first_frame")
async def extract_first_frame(request):
    """Extract the first frame from a video and return its path.

    Body JSON:
        video_path — absolute or ComfyUI-relative path to the video

    Returns JSON:
        { "frame_path": "/tmp/ffmpega_frame_xxx.png", "width": N, "height": N }
    """
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON"}, status=400)

    raw_path = body.get("video_path", "").strip()
    skip_frames = int(body.get("skip_frames", 0))
    filepath = _resolve_video_path(raw_path)
    if not filepath:
        return web.json_response({"error": "File not found"}, status=404)

    # Check cache (invalidate if file was modified)
    mtime = os.path.getmtime(filepath)
    cache_key = f"{filepath}:{skip_frames}"
    cached = _first_frame_cache.get(cache_key)
    if cached and cached[0] == mtime and os.path.isfile(cached[1]):
        # Return cached result with dimensions and base64
        from PIL import Image as _PILImage
        import base64 as _b64
        try:
            with _PILImage.open(cached[1]) as img:
                w, h = img.size
            with open(cached[1], "rb") as f:
                frame_b64 = _b64.b64encode(f.read()).decode("ascii")
        except Exception:
            w, h = 0, 0
            frame_b64 = ""
        return web.json_response({
            "frame_path": cached[1], "width": w, "height": h,
            "frame_b64": frame_b64,
        })

    # Extract first frame using ffmpeg
    import tempfile
    tmp = tempfile.NamedTemporaryFile(
        suffix=".png", prefix="ffmpega_frame_", delete=False,
    )
    tmp_path = tmp.name
    tmp.close()

    ffmpeg_bin = get_ffmpeg_bin()
    if not ffmpeg_bin:
        return web.json_response({"error": "ffmpeg not found"}, status=500)

    try:
        # Build ffmpeg command with optional frame seek
        cmd = [ffmpeg_bin, "-v", "error", "-y"]
        if skip_frames > 0:
            # Estimate seek time: probe fps first, fallback to 30fps
            try:
                ffprobe_bin = get_ffprobe_bin()
                if ffprobe_bin:
                    probe = await asyncio.create_subprocess_exec(
                        ffprobe_bin, "-v", "error",
                        "-select_streams", "v:0",
                        "-show_entries", "stream=r_frame_rate",
                        "-of", "csv=p=0", filepath,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.DEVNULL,
                    )
                    stdout, _ = await asyncio.wait_for(probe.communicate(), timeout=5)
                    fps_str = stdout.decode().strip()
                    if "/" in fps_str:
                        num, den = fps_str.split("/")
                        fps = float(num) / float(den) if float(den) != 0 else 30.0
                    else:
                        fps = float(fps_str) if fps_str else 30.0
                else:
                    fps = 30.0
            except Exception:
                fps = 30.0
            seek_time = skip_frames / fps
            cmd += ["-ss", str(seek_time)]
        cmd += ["-i", filepath, "-vframes", "1", "-q:v", "1", tmp_path]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
        if proc.returncode != 0:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            return web.json_response(
                {"error": f"ffmpeg failed: {stderr.decode()[:200]}"}, status=500,
            )
    except asyncio.TimeoutError:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        return web.json_response({"error": "Frame extraction timed out"}, status=504)

    # Cache the result
    _first_frame_cache[cache_key] = (mtime, tmp_path)
    _evict_first_frame_cache()

    # Get dimensions and encode frame as base64 for browser use
    from PIL import Image as _PILImage
    import base64 as _b64
    try:
        with _PILImage.open(tmp_path) as img:
            w, h = img.size
        with open(tmp_path, "rb") as f:
            frame_b64 = _b64.b64encode(f.read()).decode("ascii")
    except Exception:
        w, h = 0, 0
        frame_b64 = ""

    return web.json_response({
        "frame_path": tmp_path, "width": w, "height": h,
        "frame_b64": frame_b64,
    })


# ─────────────────────────────────────────────────────────────────────
#  /ffmpega/edge_map — Compute Canny edge map for a frame
# ─────────────────────────────────────────────────────────────────────

_edge_map_cache: dict = {}  # {frame_path: (mtime, edge_b64)}


@server.PromptServer.instance.routes.post("/ffmpega/edge_map")
async def edge_map(request):
    """Compute a Canny edge map from a frame image.

    Body JSON:
        frame_path — path to the image (from /ffmpega/first_frame)

    Returns JSON:
        { "edge_b64": "<base64 PNG of edge map>" }
    """
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON"}, status=400)

    frame_path = body.get("frame_path", "").strip()
    if not frame_path or not os.path.isfile(frame_path):
        return web.json_response({"error": "File not found"}, status=404)

    if not _is_path_sandboxed(frame_path):
        return web.json_response({"error": "Path not allowed"}, status=403)

    # Check cache
    mtime = os.path.getmtime(frame_path)
    cached = _edge_map_cache.get(frame_path)
    if cached and cached[0] == mtime:
        return web.json_response({"edge_b64": cached[1]})

    try:
        import cv2
        import numpy as np
        import base64 as _b64

        img = cv2.imread(frame_path)
        if img is None:
            return web.json_response({"error": "Cannot read image"}, status=400)

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        # Gaussian blur to reduce noise
        blurred = cv2.GaussianBlur(gray, (5, 5), 1.0)
        # Canny edge detection
        edges = cv2.Canny(blurred, 50, 150)

        # Encode as PNG
        _, buf = cv2.imencode(".png", edges)
        edge_b64 = _b64.b64encode(buf.tobytes()).decode("ascii")

        # Cache result
        _edge_map_cache[frame_path] = (mtime, edge_b64)

        return web.json_response({"edge_b64": edge_b64})
    except ImportError:
        return web.json_response(
            {"error": "OpenCV not available"}, status=500,
        )
    except Exception as e:
        log.warning("edge_map error: %s", e)
        return web.json_response({"error": str(e)}, status=500)


@server.PromptServer.instance.routes.post("/ffmpega/resolve_image_path")
async def resolve_image_path(request):
    """Resolve a ComfyUI input-dir filename to an absolute path.

    Body JSON:
        filename  — image filename from the file picker
        subfolder — optional subdirectory within input dir

    Returns JSON:
        { "image_path": "/abs/path/to/image.png" }
    """
    import folder_paths as _fp

    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON"}, status=400)

    filename = body.get("filename", "").strip()
    subfolder = body.get("subfolder", "").strip()

    if not filename:
        return web.json_response({"error": "No filename"}, status=400)

    input_dir = _fp.get_input_directory()
    if subfolder:
        full_path = os.path.join(input_dir, subfolder, filename)
    else:
        full_path = os.path.join(input_dir, filename)
    full_path = os.path.abspath(full_path)

    if not os.path.isfile(full_path):
        return web.json_response({"error": "File not found"}, status=404)

    if not _is_path_sandboxed(full_path):
        return web.json_response({"error": "Path not allowed"}, status=403)

    return web.json_response({"image_path": full_path})


@server.PromptServer.instance.routes.post("/ffmpega/sam3_point_mask")
async def sam3_point_mask(request):
    """Generate a SAM3 mask from point prompts and return as base64 PNG.

    Body JSON:
        frame_path   — path to the image (from /ffmpega/first_frame)
        points       — [[x, y], ...] pixel coordinates
        labels       — [1, 0, ...] (1=foreground, 0=background)
        image_width  — width of the image the points were drawn on
        image_height — height of the image the points were drawn on

    Returns JSON:
        {
            "mask_b64": "...",      # base64 PNG of the mask overlay
            "raw_mask_b64": "...",  # base64 PNG of the raw B&W mask
            "width": N,
            "height": N
        }
    """
    import base64
    import io

    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON"}, status=400)

    frame_path = body.get("frame_path", "").strip()
    points = body.get("points", [])
    labels = body.get("labels", [])
    image_width = int(body.get("image_width", 0))
    image_height = int(body.get("image_height", 0))
    multi_object = bool(body.get("multi_object", False))
    box = body.get("box", None)  # [x1, y1, x2, y2] or None
    edge_refine = bool(body.get("edge_refine", False))

    if not frame_path or not os.path.isfile(frame_path):
        return web.json_response({"error": "Frame not found"}, status=404)

    if not _is_path_sandboxed(frame_path):
        return web.json_response({"error": "Path not allowed"}, status=403)

    # Need at least points or a box
    if (not points or not labels) and not box:
        return web.json_response({"error": "No points or box provided"}, status=400)

    # Run SAM3 in thread pool to avoid blocking the event loop
    loop = asyncio.get_running_loop()

    def _generate_mask():
        # Offload other models to make room for SAM3
        try:
            import comfy.model_management as _mm
            _dev = _mm.get_torch_device()
            _mm.free_memory(6 * 1024 * 1024 * 1024, _dev)  # request 6 GiB
            _mm.soft_empty_cache()
        except Exception:
            pass
        from .core.sam3_masker import mask_image_with_points
        return mask_image_with_points(
            image_path=frame_path,
            points=points,
            labels=labels,
            image_width=image_width,
            image_height=image_height,
            device="gpu",
            multi_object=multi_object,
            box=box,
        )

    try:
        result = await asyncio.wait_for(
            loop.run_in_executor(None, _generate_mask),
            timeout=60,
        )
    except asyncio.TimeoutError:
        return web.json_response({"error": "SAM3 timed out"}, status=504)
    except Exception as e:
        log.error("sam3_point_mask error: %s", e, exc_info=True)
        return web.json_response({"error": str(e)[:200]}, status=500)

    from PIL import Image as _PILImage
    import numpy as _np

    # mask_image_with_points returns tuple (mask, per_object_masks) in
    # multi-object mode, or just a plain ndarray in single-object mode.
    per_obj_masks = None
    if isinstance(result, tuple):
        mask_np, per_obj_masks = result
    else:
        mask_np = result

    # Apply GrabCut edge refinement if requested
    if edge_refine:
        from .core.sam3_masker import refine_mask_grabcut
        mask_np = refine_mask_grabcut(frame_path, mask_np)
        if per_obj_masks:
            per_obj_masks = [
                refine_mask_grabcut(frame_path, m) for m in per_obj_masks
            ]

    h, w = mask_np.shape[:2]

    # 1. Raw B&W mask (combined)
    raw_mask_img = _PILImage.fromarray(mask_np, mode="L")
    raw_buf = io.BytesIO()
    raw_mask_img.save(raw_buf, format="PNG", optimize=True)
    raw_mask_b64 = base64.b64encode(raw_buf.getvalue()).decode("ascii")

    # Per-object color palette (RGBA at 40% opacity)
    _OBJECT_COLORS = [
        (0, 212, 170, 102),    # Teal
        (220, 60, 180, 102),   # Magenta
        (255, 160, 40, 102),   # Orange
        (40, 180, 255, 102),   # Cyan
        (120, 220, 40, 102),   # Lime
        (160, 80, 255, 102),   # Violet
        (255, 100, 100, 102),  # Coral
        (50, 255, 200, 102),   # Mint
        (255, 200, 50, 102),   # Amber
        (255, 150, 200, 102),  # Pink
        (80, 100, 255, 102),   # Indigo
        (180, 255, 50, 102),   # Chartreuse
    ]
    _CONTOUR_COLORS = [
        (0, 255, 200, 255),    # Teal
        (255, 80, 220, 255),   # Magenta
        (255, 190, 60, 255),   # Orange
        (60, 200, 255, 255),   # Cyan
        (140, 255, 60, 255),   # Lime
        (180, 100, 255, 255),  # Violet
        (255, 130, 130, 255),  # Coral
        (70, 255, 220, 255),   # Mint
        (255, 220, 70, 255),   # Amber
        (255, 170, 220, 255),  # Pink
        (100, 120, 255, 255),  # Indigo
        (200, 255, 70, 255),   # Chartreuse
    ]

    # 2. Colored overlay
    try:
        orig_img = _PILImage.open(frame_path).convert("RGBA")
        overlay = _PILImage.new("RGBA", (w, h), (0, 0, 0, 0))
        overlay_np = _np.array(overlay)

        # Check for per-object masks (multi-object mode)
        if per_obj_masks and len(per_obj_masks) > 1:
            # Multi-object: each object gets a distinct color
            for idx, obj_mask in enumerate(per_obj_masks):
                color = _OBJECT_COLORS[idx % len(_OBJECT_COLORS)]
                obj_bool = obj_mask > 127
                overlay_np[obj_bool] = color
            # Darken unmasked
            combined_bool = mask_np > 127
            overlay_np[~combined_bool] = [30, 60, 90, 128]
        else:
            # Single object: standard teal
            mask_bool = mask_np > 127
            overlay_np[mask_bool] = [0, 212, 170, 102]
            overlay_np[~mask_bool] = [30, 60, 90, 128]

        overlay = _PILImage.fromarray(overlay_np, mode="RGBA")
        result = _PILImage.alpha_composite(orig_img, overlay)

        # Draw contour outlines
        try:
            import cv2
            if per_obj_masks and len(per_obj_masks) > 1:
                result_np = _np.array(result)
                for idx, obj_mask in enumerate(per_obj_masks):
                    contour_color = _CONTOUR_COLORS[idx % len(_CONTOUR_COLORS)]
                    contours, _ = cv2.findContours(
                        obj_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE,
                    )
                    if contours:
                        cv2.drawContours(result_np, contours, -1, contour_color, 2)
                result = _PILImage.fromarray(result_np, mode="RGBA")
            else:
                contours, _ = cv2.findContours(
                    mask_np, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE,
                )
                if contours:
                    result_np = _np.array(result)
                    cv2.drawContours(result_np, contours, -1, (255, 215, 0, 255), 2)
                    result = _PILImage.fromarray(result_np, mode="RGBA")
        except ImportError:
            pass  # cv2 not available — skip contour

        result_rgb = result.convert("RGB")
        overlay_buf = io.BytesIO()
        result_rgb.save(overlay_buf, format="PNG", optimize=True)
        mask_overlay_b64 = base64.b64encode(overlay_buf.getvalue()).decode("ascii")
    except Exception as e:
        log.warning("sam3_point_mask overlay generation failed: %s", e)
        mask_overlay_b64 = raw_mask_b64  # fallback to raw mask

    return web.json_response({
        "mask_b64": mask_overlay_b64,
        "raw_mask_b64": raw_mask_b64,
        "width": w,
        "height": h,
    })

