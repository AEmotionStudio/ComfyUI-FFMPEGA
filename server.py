"""FFMPEGA server routes for ComfyUI.

Registers custom API endpoints on ComfyUI's aiohttp PromptServer
for features that need to serve content outside the standard
input/output/temp directories (e.g. live video preview of files
at arbitrary filesystem paths).
"""

import asyncio
import logging
import os

import server
from .core.bin_paths import get_ffmpeg_bin, get_ffprobe_bin

log = logging.getLogger("ffmpega")
web = server.web


def _resolve_video_path(raw_path: str) -> str | None:
    """Resolve a video path that may be absolute or ComfyUI-relative.

    Handles:
    - Absolute paths: /home/user/video.mp4
    - ComfyUI input dir: input/video.mp4
    - ComfyUI output dir: output/video.mp4
    - ComfyUI temp dir: temp/video.mp4

    Returns:
        Resolved absolute path if the file exists, or None.
    """
    import folder_paths

    if not raw_path:
        return None

    # Try as absolute path first
    abspath = os.path.abspath(raw_path)
    if os.path.isfile(abspath):
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
            if os.path.isfile(candidate):
                return candidate

    # Try as-is in input directory (bare filename)
    candidate = os.path.join(folder_paths.get_input_directory(), raw_path)
    if os.path.isfile(candidate):
        return candidate

    return None


# ---------------------------------------------------------------------------
#  /ffmpega/preview — Stream a video segment as webm for inline preview
# ---------------------------------------------------------------------------

@server.PromptServer.instance.routes.get("/ffmpega/preview")
async def preview_video(request):
    """Stream a video file (or segment) as webm for the browser.

    Query params:
        path        — absolute or ComfyUI-relative path to the video (required)
        start_time  — start offset in seconds (default: 0)
        duration    — clip duration in seconds (default: full video)

    The video is re-encoded on-the-fly using ffmpeg → libvpx-vp9 webm
    and streamed directly to the response (no temp files).
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

    # --- Build ffmpeg command ---
    args = [ffmpeg_bin, "-v", "error"]

    # Seek (pre-input for fast seek on large files)
    start_time = float(query.get("start_time", 0))
    if start_time > 0:
        if start_time > 4:
            # Fast seek to 4s before, then precise seek the rest
            args += ["-ss", str(start_time - 4)]
            post_seek = ["-ss", "4"]
        else:
            post_seek = ["-ss", str(start_time)]
    else:
        post_seek = []

    args += ["-i", filepath] + post_seek

    # Duration limit (0 or absent = full video; cap preview at 30s)
    duration = query.get("duration")
    if duration:
        dur_val = float(duration)
        if dur_val > 0:
            args += ["-t", str(dur_val)]
        else:
            # 0 = full video, but cap preview at 30s to avoid huge encodes
            args += ["-t", "30"]
    else:
        args += ["-t", "30"]

    # Frame cap (prevent huge encodes)
    frame_cap = query.get("frame_cap")
    if frame_cap:
        args += ["-frames:v", str(int(float(frame_cap)))]

    # Output: webm stream to stdout
    args += [
        "-c:v", "libvpx-vp9",
        "-deadline", "realtime",
        "-cpu-used", "8",
        "-b:v", "0",
        "-crf", "35",
        "-c:a", "libopus",  # Include audio for preview
        "-f", "webm",
        "-",
    ]

    # --- Stream ffmpeg output to response ---
    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            stdin=asyncio.subprocess.DEVNULL,
        )

        resp = web.StreamResponse()
        resp.content_type = "video/webm"
        filename = os.path.basename(filepath)
        resp.headers["Content-Disposition"] = f'inline; filename="{filename}"'
        await resp.prepare(request)

        try:
            while True:
                chunk = await proc.stdout.read(1024 * 1024)  # 1MB chunks
                if not chunk:
                    break
                await resp.write(chunk)
            await proc.wait()
        except (ConnectionResetError, ConnectionError):
            proc.kill()
            await proc.wait()

        return resp

    except BrokenPipeError:
        return web.Response(status=500, text="Stream interrupted")
    except Exception as e:
        log.warning("Preview stream error: %s", e)
        return web.Response(status=500, text=str(e))


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
        import json
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


# ── Text Presets ─────────────────────────────────────────────────────
import json

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

