"""
Load Last Video node for ComfyUI — enhanced with FFMPEGA-inspired patterns.

Auto-discovers the most recently saved video in ComfyUI's output/temp
directories, decodes frames (capped) to an IMAGE batch, extracts audio,
and outputs rich metadata — all with an inline preview that loads
*immediately* before any queue run.

Architecture:
  - Python registers /loadlast/latest_video and /loadlast/video_list API routes
  - JS polls those routes to always show the last video on the node
  - On execution, frames are decoded (with capping) via VideoDecoder
  - Audio extracted via AudioExtractor
  - Metadata output via ffprobe
"""

from __future__ import annotations

import atexit
import hashlib
import json
import logging
import os
import shutil
import subprocess
import tempfile
import time

import numpy as np
import torch
import torch.nn.functional as F

try:
    import folder_paths
except ImportError:
    folder_paths = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

# Maximum file size (bytes) to copy into temp for preview (500 MB)
_MAX_COPY_SIZE = 500 * 1024 * 1024

# Auto-select mode options
FRAME_SELECT_MODES = [
    "manual", "uniform_5", "uniform_10", "first_last",
    "every_2nd", "every_5th", "timestamps",
]

# Supported video extensions (lowercase, no dot)
VIDEO_EXTENSIONS = {"mp4", "webm", "gif", "mkv", "mov"}

# Default max frames to decode (prevents OOM on long videos)
from .constants import DEFAULT_MAX_FRAMES

# Maximum values for integer parameters
BIGMAX = 2**31 - 1

# Cap on auto-generated timestamps to prevent spawning too many subprocesses
_MAX_AUTO_TIMESTAMPS = 256

# Fallback FPS guess when neither duration nor fps is available
_FALLBACK_FPS_GUESS = 30

# Time-to-live (seconds) for selected-frame PNGs before cleanup
_STALE_FRAME_TTL = 60

# Track temp paths for cleanup at exit — a single atexit handler
# iterates this set rather than accumulating one handler per path.
_registered_atexit_paths: set[str] = set()
_atexit_registered = False


def _cleanup_registered_temps() -> None:
    """Remove all registered temp files at interpreter exit."""
    for p in list(_registered_atexit_paths):
        try:
            if os.path.isfile(p):
                os.remove(p)
        except OSError:
            pass
    _registered_atexit_paths.clear()

# Module-level timestamps for rate-limiting stale-frame cleanup.
# Each cleanup site tracks its own timestamp so they run independently.
_last_preview_cleanup_time: float = 0.0
_last_selected_cleanup_time: float = 0.0

# ─── User Video Selections (server-side state) ──────────────────────────
# Stores the user's explicit video selection from the browser strip,
# keyed by node ID.  Set via POST /loadlast/select_video, consumed
# (one-shot) by load().  Capped to prevent unbounded growth.
# Each value is {"data": <entry dict>, "ts": <time.time()>}.
_user_video_selections: dict[str, dict] = {}

# ─── User Edit States (server-side state) ────────────────────────────
# Stores the user's inline edit state (segments, crop, speed) from the
# Apply Edits button, keyed by node ID.  Consumed one-shot by load().
# Each value is {"data": <edits dict>, "ts": <time.time()>}.
_user_edit_states: dict[str, dict] = {}

# Max entries for server-side state dicts (prevents unbounded growth)
_MAX_SERVER_STATE_ENTRIES = 100

# TTL (seconds) for server-side state entries.  Entries older than this
# are evicted in IS_CHANGED to prevent stale state from persisting
# when load() is never called (e.g. node disconnected from graph).
_SERVER_STATE_TTL = 300  # 5 minutes

# Rate-limit TTL eviction scans in IS_CHANGED (seconds).
# IS_CHANGED is called on every scheduler poll; scanning all entries
# each time is needlessly heavy.  This mirrors the _last_preview_cleanup_time
# pattern used for file cleanup.
_EVICTION_SCAN_INTERVAL = 30
_last_eviction_scan_time: float = 0.0


def _capped_insert(d: dict, key: str, value: dict) -> None:
    """Insert *value* under *key* into *d*, evicting the oldest entry if at cap.

    FIFO eviction relies on dict insertion-order preservation (guaranteed
    since Python 3.7+, CPython 3.6+).  Do not replace *d* with a mapping
    type that does not preserve insertion order.
    """
    if len(d) >= _MAX_SERVER_STATE_ENTRIES and key not in d:
        oldest = next(iter(d))
        d.pop(oldest, None)
    d[key] = value

# Allowed keys for video selection entries
_ALLOWED_ENTRY_KEYS = {"filename", "subfolder", "type", "format"}
_ALLOWED_SEL_TYPES = {"output", "temp"}

# Allowed keys for inline edit state entries
_ALLOWED_EDIT_KEYS = {"segments", "crop_rect", "speed_map"}

# ─── FPS cache for latest_video API ──────────────────────────────────
# Caches {filepath: (fps, mtime)} to avoid repeated ffprobe calls.
_fps_cache: dict[str, tuple[float, float]] = {}


# ─── API Route ──────────────────────────────────────────────────────────
# Returns JSON with the latest video's filename, subfolder, and type
# so the JS widget can immediately load a preview via /view.

try:
    from aiohttp import web
    from server import PromptServer

    @PromptServer.instance.routes.get("/loadlast/latest_video")
    async def _api_latest_video(request):
        """Find the most recently modified video in output/temp."""
        source = request.query.get("source", "")
        prefix = request.query.get("prefix", "")

        scan_dirs = _resolve_scan_dirs(source)

        result = _find_latest_video_info(scan_dirs, prefix)
        if result is None:
            return web.json_response({"found": False})

        # Include FPS from a cached lightweight ffprobe
        fps = _probe_fps_cached(result)
        if fps:
            result["fps"] = fps

        return web.json_response({"found": True, **result})

    @PromptServer.instance.routes.get("/loadlast/video_list")
    async def _api_video_list(request):
        """Return list of all recent videos, sorted newest first."""
        source = request.query.get("source", "")
        prefix = request.query.get("prefix", "")
        try:
            limit = min(int(request.query.get("limit", "20")), 50)
        except (ValueError, TypeError):
            limit = 20

        scan_dirs = _resolve_scan_dirs(source)

        videos = _find_all_videos(scan_dirs, prefix, limit)
        return web.json_response({"videos": videos})

    @PromptServer.instance.routes.post("/loadlast/select_video")
    async def _api_select_video(request):
        """Store the user's video selection for a specific node."""
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "invalid JSON"}, status=400)

        node_id = str(body.get("node_id", ""))
        entry = body.get("entry")  # null to clear

        if not node_id:
            return web.json_response({"error": "node_id required"}, status=400)

        if entry:
            # Validate and sanitise: only keep known keys, coerce to str
            entry = {k: str(v) for k, v in entry.items() if k in _ALLOWED_ENTRY_KEYS}
            if not entry.get("filename"):
                return web.json_response({"error": "filename required in entry"}, status=400)
            # Cap dict size — evict oldest if at limit
            _capped_insert(_user_video_selections, node_id, {"data": entry, "ts": time.time()})
            logger.info("[LoadLast] Selection stored for node %s: %s", node_id, entry.get("filename", "?"))
        else:
            _user_video_selections.pop(node_id, None)
            logger.debug("[LoadLast] Selection cleared for node %s", node_id)

        return web.json_response({"ok": True})

    @PromptServer.instance.routes.post("/loadlast/apply_edits")
    async def _api_apply_edits(request):
        """Store the user's inline edit state for a specific node."""
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "invalid JSON"}, status=400)

        node_id = str(body.get("node_id", ""))
        if not node_id:
            return web.json_response({"error": "node_id required"}, status=400)

        edits = body.get("edits")  # null to clear
        if edits:
            # Validate and sanitise: only keep known keys, coerce to str
            edits = {k: str(v) for k, v in edits.items() if k in _ALLOWED_EDIT_KEYS}
            # Cap dict size — evict oldest if at limit
            _capped_insert(_user_edit_states, node_id, {"data": edits, "ts": time.time()})
            logger.info("[LoadLast] Edit state stored for node %s", node_id)
        else:
            _user_edit_states.pop(node_id, None)
            logger.debug("[LoadLast] Edit state cleared for node %s", node_id)

        return web.json_response({"ok": True})

except (ImportError, AttributeError):
    # Running outside ComfyUI (e.g. pytest) — skip route registration
    pass





def _get_allowed_directories() -> list[str]:
    """Return the set of directories users are allowed to access."""
    from .discovery.path_utils import get_allowed_directories
    return get_allowed_directories()


def _is_path_sandboxed(path: str) -> bool:
    """Check if a path is within ComfyUI's allowed directories."""
    from .discovery.path_utils import is_path_sandboxed
    return is_path_sandboxed(path)


def _probe_fps_cached(video_info: dict) -> float | None:
    """Return the FPS of a video file via a cached lightweight ffprobe.

    Uses the filename + subfolder + type from video_info to resolve the
    full path, then runs ffprobe for r_frame_rate.  Results are cached
    by filepath + mtime to avoid repeated subprocess calls on polls.
    Returns None if ffprobe fails or the file can't be located.
    """
    if folder_paths is None:
        return None
    try:
        vtype = video_info.get("type", "output")
        if vtype == "output":
            base = folder_paths.get_output_directory()
        else:
            base = folder_paths.get_temp_directory()
        subfolder = video_info.get("subfolder", "")
        filename = video_info.get("filename", "")
        if not filename:
            return None
        full_path = (
            os.path.join(base, subfolder, filename)
            if subfolder
            else os.path.join(base, filename)
        )
        if not os.path.isfile(full_path):
            return None
        if not _is_path_sandboxed(full_path):
            return None

        mtime = os.path.getmtime(full_path)
        cached = _fps_cache.get(full_path)
        if cached and cached[1] == mtime:
            return cached[0]

        ffprobe = shutil.which("ffprobe") or "ffprobe"
        result = subprocess.run(
            [ffprobe, "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=r_frame_rate",
             "-of", "json", full_path],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0:
            return None
        data = json.loads(result.stdout)
        streams = data.get("streams", [])
        if not streams:
            return None
        fps_str = streams[0].get("r_frame_rate", "")
        if "/" in fps_str:
            num, den = fps_str.split("/", 1)
            den_f = float(den)
            fps = float(num) / den_f if den_f else 24.0
        elif fps_str:
            fps = float(fps_str)
        else:
            return None

        # Cap unreasonable FPS values
        if fps <= 0 or fps > 240:
            return None

        _fps_cache[full_path] = (fps, mtime)
        # Limit cache size and purge entries for deleted files.
        # Purging deleted paths prevents the cache from hoarding stale
        # entries that would otherwise persist until evicted by the 200-
        # entry cap via insertion-order FIFO.
        if len(_fps_cache) > 200:
            stale_paths = [p for p in _fps_cache if not os.path.isfile(p)]
            for p in stale_paths:
                _fps_cache.pop(p, None)
            # Still over cap after purge — evict oldest by insertion order
            if len(_fps_cache) > 200:
                oldest_key = next(iter(_fps_cache))
                _fps_cache.pop(oldest_key, None)
        return fps
    except Exception:
        return None


def _resolve_scan_dirs(source: str) -> list[str]:
    """Return scan directories for a user-supplied source path."""
    from .discovery.path_utils import resolve_scan_dirs
    return resolve_scan_dirs(source)


def _find_latest_video_info(directories: list[str], prefix: str = "") -> dict | None:
    """Find latest video and return {filename, subfolder, type, format, mtime}."""
    all_entries = _scan_video_entries(directories, prefix)
    if not all_entries:
        return None
    # Sort by mtime descending, take the newest
    all_entries.sort(key=lambda x: x[2], reverse=True)
    info = _resolve_view_info(*all_entries[0][:2])
    if info:
        info["mtime"] = all_entries[0][2]
    return info


def _find_all_videos(directories: list[str], prefix: str = "", limit: int = 20) -> list[dict]:
    """Find all recent videos, sorted newest first, up to limit."""
    all_entries = _scan_video_entries(directories, prefix)
    all_entries.sort(key=lambda x: x[2], reverse=True)
    results = []
    for full_path, parent_dir, mtime in all_entries[:limit]:
        info = _resolve_view_info(full_path, parent_dir)
        if info:
            info["mtime"] = mtime
            results.append(info)
    return results


def _scan_video_entries(directories: list[str], prefix: str = "") -> list[tuple]:
    """Scan directories recursively for video files.

    Returns [(full_path, parent_dir, mtime), ...].
    """
    entries: list[tuple] = []
    for dir_path in directories:
        if not os.path.isdir(dir_path):
            continue
        _scan_video_dir(dir_path, prefix, entries)
    return entries


def _scan_video_dir(
    directory: str, prefix: str, entries: list[tuple], max_depth: int = 5,
) -> None:
    """Recursively collect video files from a directory."""
    if max_depth <= 0:
        return
    try:
        for entry in os.scandir(directory):
            try:
                if entry.is_file(follow_symlinks=False):
                    ext = entry.name.rsplit(".", 1)[-1].lower() if "." in entry.name else ""
                    if ext not in VIDEO_EXTENSIONS:
                        continue
                    if prefix and not entry.name.startswith(prefix):
                        continue
                    try:
                        # stat() follows symlinks — intentional: mtime of the
                        # actual file matters for "most recent" ordering.
                        mtime = entry.stat().st_mtime
                    except OSError:
                        continue
                    # realpath resolves symlinked *files*; symlinked dirs are
                    # already excluded by is_dir(follow_symlinks=False) above.
                    entries.append((os.path.realpath(entry.path), directory, mtime))
                elif entry.is_dir(follow_symlinks=False):
                    _scan_video_dir(entry.path, prefix, entries, max_depth - 1)
            except (PermissionError, OSError):
                continue
    except PermissionError:
        pass


def _resolve_view_info(full_path: str, parent_dir: str) -> dict | None:
    """Resolve a video file to {filename, subfolder, type, format} for /view."""
    if folder_paths is None:
        return None
    output_dir = folder_paths.get_output_directory()
    temp_dir = folder_paths.get_temp_directory()
    filename = os.path.basename(full_path)

    # Use startswith for reliable containment check (commonpath has edge cases)
    real_output = os.path.realpath(output_dir)
    real_temp = os.path.realpath(temp_dir)
    real_parent = os.path.realpath(parent_dir)

    is_output = real_parent == real_output or real_parent.startswith(real_output + os.sep)
    is_temp = real_parent == real_temp or real_parent.startswith(real_temp + os.sep)

    if is_output:
        subfolder = os.path.relpath(parent_dir, output_dir)
        view_type = "output"
    elif is_temp:
        subfolder = os.path.relpath(parent_dir, temp_dir)
        view_type = "temp"
    else:
        # Cap file size before copying into temp for preview
        try:
            file_size = os.path.getsize(full_path)
        except OSError:
            file_size = 0
        if file_size > _MAX_COPY_SIZE:
            logger.warning(
                "[LoadLast] Skipping copy of %s (%.0f MB exceeds %.0f MB cap)",
                filename, file_size / 1024 / 1024, _MAX_COPY_SIZE / 1024 / 1024,
            )
            return None
        preview_dir = os.path.join(temp_dir, "loadlast_previews")
        os.makedirs(preview_dir, exist_ok=True)

        # TTL-based cleanup of stale preview copies
        global _last_preview_cleanup_time
        now = time.time()
        if now - _last_preview_cleanup_time > _STALE_FRAME_TTL:
            _last_preview_cleanup_time = now
            try:
                with os.scandir(preview_dir) as it:
                    for entry in it:
                        try:
                            if entry.stat().st_mtime < now - _STALE_FRAME_TTL:
                                os.remove(entry.path)
                        except OSError:
                            pass
            except OSError:
                pass

        # Use content-hashed prefix to avoid collisions from different source paths
        path_hash = hashlib.sha256(full_path.encode()).hexdigest()[:12]
        safe_name = f"{path_hash}_{filename}"
        dest = os.path.join(preview_dir, safe_name)
        if not os.path.exists(dest) or os.path.getmtime(full_path) > os.path.getmtime(dest):
            tmp_dest = dest + ".tmp"
            shutil.copy2(full_path, tmp_dest)
            os.replace(tmp_dest, dest)
        filename = safe_name
        subfolder = "loadlast_previews"
        view_type = "temp"

    if subfolder == ".":
        subfolder = ""

    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "mp4"
    fmt_map = {"mp4": "mp4", "webm": "webm", "gif": "gif", "mkv": "x-matroska", "mov": "quicktime"}

    return {
        "filename": filename,
        "subfolder": subfolder,
        "type": view_type,
        "format": f"video/{fmt_map.get(ext, 'mp4')}",
    }


# ─── Node Class ─────────────────────────────────────────────────────────

class LoadLastVideo:
    """
    Automatically load the most recently saved video.

    Scans ComfyUI's output and temp directories for the newest video file,
    decodes it into an IMAGE tensor batch (with frame capping to prevent OOM),
    extracts audio, and outputs rich metadata. Shows an inline preview
    that loads *immediately* when the node is placed (no queue needed).
    """

    CATEGORY = "FFMPEGA"
    FUNCTION = "load"
    OUTPUT_NODE = True

    RETURN_TYPES = ("IMAGE", "IMAGE", "AUDIO", "STRING", "STRING", "MASK")
    RETURN_NAMES = ("images", "selected_frames", "audio", "video_path", "image_paths", "mask")

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "refresh_mode": (["auto", "manual"], {
                    "default": "auto",
                    "tooltip": "auto: reload when latest video changes. manual: only on input change.",
                }),
                "frame_select_mode": (FRAME_SELECT_MODES, {
                    "default": "manual",
                    "tooltip": (
                        "How to select frames. 'manual' = user clicks in preview. "
                        "Other modes auto-select frames based on the chosen strategy."
                    ),
                }),
                "auto_timestamps": ("STRING", {
                    "default": "",
                    "tooltip": "Comma-separated timestamps for 'timestamps' mode (e.g., '0.5,1.0,2.5').",
                }),
                "pause_for_selection": ("BOOLEAN", {
                    "default": False,
                    "label_on": "pause",
                    "label_off": "run",
                    "tooltip": (
                        "When ON and frame_select_mode is 'manual', blocks execution "
                        "if no frames are selected. Select frames, then re-queue."
                    ),
                }),
            },
            "optional": {
                "source_folder": ("STRING", {
                    "default": "",
                    "tooltip": "Custom folder to scan. Empty = default output/temp directories.",
                }),
                "filename_filter": ("STRING", {
                    "default": "",
                    "tooltip": "Only load files starting with this prefix.",
                }),
                "max_frames": ("INT", {
                    "default": DEFAULT_MAX_FRAMES,
                    "min": 0,
                    "max": BIGMAX,
                    "step": 1,
                    "tooltip": (
                        "Max frames to decode into the IMAGE tensor (0 = all). "
                        "Caps memory usage for long videos. Frames are evenly "
                        "sampled to preserve temporal coverage."
                    ),
                }),
                "images": ("IMAGE", {
                    "tooltip": "Override: video frames as IMAGE tensor. Overrides auto-discovery.",
                }),
                "audio": ("AUDIO", {
                    "tooltip": "Override: provide audio directly. Overrides audio extracted from video.",
                }),
                "video_path": ("STRING", {
                    "default": "",
                    "forceInput": True,
                    "tooltip": "Override: path to a video file. Overrides auto-discovery.",
                }),
                "mask": ("MASK", {
                    "tooltip": (
                        "Optional upstream MASK pass-through. "
                        "Forwarded as-is to the mask output."
                    ),
                }),
            },
            "hidden": {
                "unique_id": "UNIQUE_ID",
                "_selected_timestamps": ("STRING", {"default": "[]"}),
                "_edit_segments": ("STRING", {"default": "[]"}),
                "_edit_action": ("STRING", {"default": "none"}),
                "_crop_rect": ("STRING", {"default": ""}),
                "_speed_map": ("STRING", {"default": "{}"}),
            },
        }

    @classmethod
    def IS_CHANGED(cls, refresh_mode="auto", **kwargs):
        """Content-aware change detection.

        In auto mode, returns a hash based on the latest video's filename
        and mtime so the node only re-runs when a new video is generated.
        In manual mode, returns a constant so it never auto-reruns —
        unless the user has explicitly selected a video or applied edits
        via the server-side routes.
        """
        # Check for pending server state first — works in both modes.
        # If the user clicked a video in the browser strip or pressed
        # "Apply Edits", we must force a re-run regardless of refresh_mode.
        uid = str(kwargs.get("unique_id", ""))

        # Evict stale entries (TTL-based) to prevent state from lingering
        # when load() is never called (e.g. node disconnected from graph).
        # Rate-limited to avoid scanning on every scheduler poll.
        global _last_eviction_scan_time
        now = time.time()
        if now - _last_eviction_scan_time > _EVICTION_SCAN_INTERVAL:
            _last_eviction_scan_time = now
            for d in (_user_video_selections, _user_edit_states):
                stale = [k for k, v in d.items() if now - v.get("ts", 0) > _SERVER_STATE_TTL]
                for k in stale:
                    d.pop(k, None)

        if uid and uid in _user_video_selections:
            return f"selected_{uid}_{time.time()}"
        if uid and uid in _user_edit_states:
            return f"edits_{uid}_{time.time()}"

        if refresh_mode == "manual":
            return ""

        # Find the latest video and use its identity as the hash
        source = kwargs.get("source_folder", "")
        prefix = kwargs.get("filename_filter", "")

        scan_dirs = _resolve_scan_dirs(source)

        info = _find_latest_video_info(scan_dirs, prefix)
        if info is None:
            return ""

        # Hash filename + mtime — changes when a new video appears
        m = hashlib.sha256()
        m.update(info["filename"].encode())
        m.update(str(info.get("mtime", 0)).encode())
        m.update(str(kwargs.get("max_frames", DEFAULT_MAX_FRAMES)).encode())
        m.update(str(kwargs.get("_selected_timestamps", "[]")).encode())
        m.update(str(kwargs.get("frame_select_mode", "manual")).encode())
        m.update(str(kwargs.get("auto_timestamps", "")).encode())
        # Include edit state so the node re-runs when edits change
        m.update(str(kwargs.get("_edit_segments", "[]")).encode())
        m.update(str(kwargs.get("_edit_action", "none")).encode())
        m.update(str(kwargs.get("_crop_rect", "")).encode())
        m.update(str(kwargs.get("_speed_map", "{}")).encode())
        return m.hexdigest()

    def load(
        self,
        refresh_mode: str = "auto",
        source_folder: str = "",
        filename_filter: str = "",
        max_frames: int = DEFAULT_MAX_FRAMES,
        images=None,
        audio=None,
        video_path: str = "",
        mask=None,
        frame_select_mode: str = "manual",
        auto_timestamps: str = "",
        pause_for_selection: bool = False,
        unique_id: str = "",
        _selected_timestamps: str = "[]",
        _edit_segments: str = "[]",
        _edit_action: str = "none",
        _crop_rect: str = "",
        _speed_map: str = "{}",
    ):
        from .processing.video_decode import VideoDecoder
        from .processing.audio_extract import AudioExtractor

        empty_frames = torch.zeros(1, 512, 512, 3)
        silent_audio = {"waveform": torch.zeros(1, 1, 1), "sample_rate": 44100}
        empty_mask = mask if mask is not None else torch.zeros(1, 512, 512, dtype=torch.float32)
        empty_result = (empty_frames, empty_frames, silent_audio, "", "", empty_mask)

        # --- Resolve video source (priority: images > video_path > auto) ---
        resolved_path = None
        info = None
        temp_video_from_images = None

        if images is not None:
            # Input override: IMAGE tensor → convert to temp video
            try:
                temp_dir = folder_paths.get_temp_directory()
                os.makedirs(temp_dir, exist_ok=True)
                _fd, temp_video_from_images = tempfile.mkstemp(
                    prefix="loadlast_override_", suffix=".mp4", dir=temp_dir,
                )
                os.close(_fd)
                self._images_to_video(images, temp_video_from_images)
                resolved_path = temp_video_from_images
                info = _resolve_view_info(resolved_path, temp_dir)
            except Exception as e:
                logger.warning("[LoadLast] Failed to convert images to video: %s", e)

        if resolved_path is None and video_path and video_path.strip():
            # Input override: video_path STRING
            vp = video_path.strip()
            if not _is_path_sandboxed(vp):
                logger.warning(
                    "[LoadLast] video_path '%s' is outside allowed directories, ignoring", vp
                )
            elif os.path.isfile(vp):
                resolved_path = vp
                parent = os.path.dirname(vp)
                info = _resolve_view_info(resolved_path, parent)
            else:
                logger.warning("[LoadLast] video_path does not exist: %s", vp)

        if resolved_path is None:
            # Check for user-selected video from browser strip (server-side state)
            sel_wrapper = _user_video_selections.pop(str(unique_id), None)
            sel = (sel_wrapper.get("data") if isinstance(sel_wrapper, dict) else None)
            if sel:
                sel_filename = os.path.basename(sel.get("filename", ""))
                sel_subfolder = sel.get("subfolder", "")
                sel_type = sel.get("type", "output")
                # Reject path-traversal attempts in subfolder
                # Normalise both / and \ to catch traversal from any OS
                if ".." in sel_subfolder.replace("\\", "/").split("/"):
                    logger.warning(
                        "[LoadLast] Subfolder contains '..', rejecting selection for node %s",
                        unique_id,
                    )
                    sel_filename = ""
                if sel_type not in _ALLOWED_SEL_TYPES:
                    logger.warning(
                        "[LoadLast] Invalid selection type '%s' for node %s, skipping",
                        sel_type, unique_id,
                    )
                    sel_filename = ""  # skip this selection
                if sel_filename:
                    if sel_type == "output":
                        base = folder_paths.get_output_directory()
                    else:
                        base = folder_paths.get_temp_directory()
                    candidate = (
                        os.path.join(base, sel_subfolder, sel_filename)
                        if sel_subfolder
                        else os.path.join(base, sel_filename)
                    )
                    if _is_path_sandboxed(candidate) and os.path.isfile(candidate):
                        resolved_path = candidate
                        info = {
                            "filename": sel_filename,
                            "subfolder": sel_subfolder,
                            "type": sel_type,
                            "format": sel.get("format", "video/mp4"),
                        }
                        logger.info(
                            "[LoadLast] Using user-selected video: %s", resolved_path
                        )
                    else:
                        logger.warning(
                            "[LoadLast] Selected video not found or outside sandbox: %s",
                            candidate,
                        )

        if resolved_path is None:
            # Auto-discover latest video (default behavior)
            scan_dirs = _resolve_scan_dirs(source_folder)

            latest = _find_latest_video_info(scan_dirs, filename_filter)
            if latest is None:
                logger.warning("[LoadLast] No videos found")
                return {"ui": {"video": [], "gifs": []}, "result": empty_result}

            info = latest
            if info["type"] == "output":
                base = folder_paths.get_output_directory()
            else:
                base = folder_paths.get_temp_directory()
            resolved_path = (
                os.path.join(base, info["subfolder"], info["filename"])
                if info["subfolder"]
                else os.path.join(base, info["filename"])
            )

        if resolved_path is None or info is None:
            return {"ui": {"video": [], "gifs": []}, "result": empty_result}

        logger.info("[LoadLast] Loading video: %s", resolved_path)

        # --- Apply inline edits (trim/crop/speed) if present ---
        # Precedence chain for edit state:
        #   1. Server-side state (from "Apply Edits" button → POST /loadlast/apply_edits)
        #      — consumed one-shot via pop(), so it only applies once.
        #   2. Hidden widget values (from syncEditToWidgets in the frontend)
        #      — persist across runs as fallback when no server state exists.
        # If the user clicks "Apply Edits" and then modifies a widget before
        # re-queueing, the server state (if still present) wins; once consumed,
        # subsequent runs fall through to the widget path.
        if unique_id and unique_id in _user_edit_states:
            edits_wrapper = _user_edit_states.pop(unique_id)
            edits = edits_wrapper.get("data", {}) if isinstance(edits_wrapper, dict) else {}
            logger.info("[LoadLast] Consuming server-side edits for node %s", unique_id)
            resolved_path = self._apply_edits(
                resolved_path,
                edits.get("segments", "[]"),
                edits.get("crop_rect", ""),
                edits.get("speed_map", "{}"),
            )
            # Prevent the widget fallback (elif _edit_action == "passthrough")
            # from firing later *in this same call*.  This only reassigns the
            # local parameter — the widget value is unchanged, which is fine:
            # on subsequent runs the server state will have been popped and
            # the widget path is the correct fallback.
            _edit_action = "none"
        elif _edit_action == "passthrough":
            resolved_path = self._apply_edits(
                resolved_path,
                _edit_segments, _crop_rect, _speed_map,
            )

        # --- Decode frames via VideoDecoder ---
        decoder = VideoDecoder()
        ext = os.path.splitext(resolved_path)[1].lower()

        try:
            if ext == ".gif":
                frames, metadata = decoder.decode_gif(resolved_path, max_frames=max_frames)
            else:
                frames, metadata = decoder.decode_file(resolved_path, max_frames=max_frames)
        except Exception as e:
            logger.warning("[LoadLast] Failed to decode video: %s — %s", resolved_path, e)
            return {
                "ui": {"video": [], "gifs": []},
                "result": (empty_frames, empty_frames, silent_audio, resolved_path, "", empty_mask),
            }

        if frames is None or frames.shape[0] == 0:
            logger.warning("[LoadLast] No frames decoded from: %s", resolved_path)
            return {
                "ui": {"video": [], "gifs": []},
                "result": (empty_frames, empty_frames, silent_audio, resolved_path, "", empty_mask),
            }

        # --- Extract audio (input override wins) ---
        if audio is not None:
            pass  # Use the provided audio directly
        else:
            audio_extractor = AudioExtractor()
            audio = audio_extractor.extract(resolved_path)
            if audio is None:
                audio = silent_audio

        # --- Extract metadata ---
        frame_count = frames.shape[0]
        fps = float(metadata.get("fps", 24.0))
        duration = float(metadata.get("duration", 0.0))

        # --- Resolve timestamps (manual + auto-select) ---
        timestamps = self._resolve_timestamps(
            _selected_timestamps, frame_select_mode,
            auto_timestamps, duration, fps,
        )

        # --- Pause for selection (ExecutionBlocker) ---
        if (
            pause_for_selection
            and frame_select_mode == "manual"
            and not timestamps
        ):
            try:
                from comfy_execution.graph import ExecutionBlocker
                blocked = ExecutionBlocker(None)
                preview = {
                    "filename": info["filename"],
                    "subfolder": info.get("subfolder", ""),
                    "type": info.get("type", "temp"),
                    "format": info.get("format", "video/mp4"),
                }
                logger.info("[LoadLast] Paused — waiting for frame selection")
                return {
                    "ui": {"video": [preview], "gifs": [preview]},
                    "result": tuple(blocked for _ in range(6)),
                }
            except ImportError:
                logger.warning(
                    "[LoadLast] ExecutionBlocker not available — "
                    "pause_for_selection requires ComfyUI 0.1.3+. Continuing."
                )

        # --- Extract selected frames at specific timestamps ---
        selected_frames = self._extract_selected_frames(
            resolved_path, json.dumps(timestamps), frames,
            duration=duration, fps=fps,
        )

        # --- Save selected frames as PNGs → image_paths ---
        image_paths_str = self._save_selected_frames_as_png(
            selected_frames, timestamps,
        )

        logger.info(
            "[LoadLast] Decoded %d frames (of %d total) | %.1f fps | %.1fs | "
            "%d selected | %s",
            frames.shape[0], frame_count, fps, duration,
            selected_frames.shape[0], resolved_path,
        )

        # --- Return frames + preview metadata + new outputs ---
        preview = {
            "filename": info["filename"],
            "subfolder": info.get("subfolder", ""),
            "type": info.get("type", "temp"),
            "format": info.get("format", "video/mp4"),
        }

        return {
            "ui": {"video": [preview], "gifs": [preview]},
            "result": (
                frames, selected_frames, audio,
                resolved_path, image_paths_str,
                empty_mask,
            ),
        }

    def _apply_edits(
        self,
        source_path: str,
        segments_json: str,
        crop_json: str,
        speed_map_json: str,
    ) -> str:
        """Apply inline edits (trim/crop/speed) via the Video Editor render pipeline.

        Returns the path to the edited temp video, or the original path
        if no real edits are detected or rendering fails.
        """
        # Quick check: are there actually any edits?
        has_real_edits = (
            segments_json != "[]"
            or (crop_json and crop_json.strip() and crop_json != "{}")
            or self._has_speed_changes(speed_map_json)
        )
        if not has_real_edits:
            return source_path

        try:
            from ..videoeditor.processing.export import render_edits

            temp_dir = folder_paths.get_temp_directory() if folder_paths else "/tmp"
            os.makedirs(temp_dir, exist_ok=True)
            # Use a deterministic filename based on the source path so
            # repeated edits of the same video overwrite instead of
            # accumulating files.  Register for atexit cleanup once.
            source_hash = hashlib.sha256(source_path.encode()).hexdigest()[:12]
            output_path = os.path.join(
                temp_dir,
                f"loadlast_edit_{source_hash}.mp4",
            )

            result = render_edits(
                source_path,
                output_path,
                segments_json=segments_json,
                crop_json=crop_json,
                speed_map_json=speed_map_json,
                volume=1.0,
                text_overlays_json="[]",
                transitions_json="[]",
            )

            if result.get("success") and os.path.isfile(output_path):
                logger.info("[LoadLast] Edits applied → %s", output_path)
                if output_path not in _registered_atexit_paths:
                    _registered_atexit_paths.add(output_path)
                    global _atexit_registered
                    if not _atexit_registered:
                        atexit.register(_cleanup_registered_temps)
                        _atexit_registered = True
                return output_path
            else:
                logger.warning(
                    "[LoadLast] Edit render failed: %s — using original",
                    result.get("error", "unknown"),
                )
                return source_path
        except Exception as e:
            logger.warning("[LoadLast] Edit apply failed: %s — using original", e)
            return source_path

    @staticmethod
    def _has_speed_changes(speed_map_json: str) -> bool:
        """Check if any segment has a non-1.0 speed."""
        try:
            from ..videoeditor.processing.export import has_speed_changes
            return has_speed_changes(speed_map_json)
        except ImportError:
            return False

    def _resolve_timestamps(
        self,
        manual_json: str,
        mode: str,
        auto_ts_str: str,
        duration: float,
        fps: float,
    ) -> list[float]:
        """Merge manual selections with auto-select timestamps."""
        # Parse manual selections
        try:
            manual = json.loads(manual_json)
        except (json.JSONDecodeError, TypeError):
            manual = []
        manual = [float(t) for t in manual]

        # Generate auto-select timestamps based on mode
        auto: list[float] = []
        if mode == "uniform_5" and duration > 0:
            auto = [min(duration * i / 4, duration - 0.01) for i in range(5)]
        elif mode == "uniform_10" and duration > 0:
            auto = [min(duration * i / 9, duration - 0.01) for i in range(10)]
        elif mode == "first_last" and duration > 0:
            auto = [0.0, max(0.0, duration - 0.01)]
        elif mode == "every_2nd" and fps > 0 and duration > 0:
            step = 2.0 / fps
            cap = min(int(duration / step) + 1, _MAX_AUTO_TIMESTAMPS + 1)
            auto = [i * step for i in range(cap) if i * step < duration]
        elif mode == "every_5th" and fps > 0 and duration > 0:
            step = 5.0 / fps
            cap = min(int(duration / step) + 1, _MAX_AUTO_TIMESTAMPS + 1)
            auto = [i * step for i in range(cap) if i * step < duration]
        elif mode == "timestamps" and auto_ts_str.strip():
            try:
                auto = [float(t.strip()) for t in auto_ts_str.split(",") if t.strip()]
            except ValueError:
                logger.warning("[LoadLast] Invalid auto_timestamps: %s", auto_ts_str)

        if len(auto) > _MAX_AUTO_TIMESTAMPS:
            step = max(1, len(auto) // _MAX_AUTO_TIMESTAMPS)
            auto = auto[::step][:_MAX_AUTO_TIMESTAMPS]

        # Merge and deduplicate
        all_ts = sorted(set(manual + auto))
        return all_ts

    @staticmethod
    def _images_to_video(
        images: torch.Tensor, output_path: str, fps: int = 24,
    ) -> None:
        """Convert an IMAGE tensor batch to a temp video file.

        Delegates to ``core.images_to_video`` shared utility.
        """
        from ..core.images_to_video import images_to_video
        images_to_video(images, output_path, fps=fps)

    @staticmethod
    def _save_selected_frames_as_png(
        frames: torch.Tensor, timestamps: list[float],
    ) -> str:
        """Save selected frames as PNGs in temp dir, return comma-separated paths."""
        from PIL import Image

        if not timestamps or frames.shape[0] == 0:
            return ""

        temp_dir = folder_paths.get_temp_directory()
        sel_dir = os.path.join(temp_dir, "loadlast_selected")
        os.makedirs(sel_dir, exist_ok=True)

        # Clean up stale selected frames to prevent unbounded growth.
        # Rate-limited: scan at most once per _STALE_FRAME_TTL seconds
        # to avoid unnecessary I/O on rapid successive calls.
        global _last_selected_cleanup_time
        now = time.time()
        if now - _last_selected_cleanup_time > _STALE_FRAME_TTL:
            _last_selected_cleanup_time = now
            try:
                with os.scandir(sel_dir) as it:
                    for entry in it:
                        try:
                            if entry.stat().st_mtime < now - _STALE_FRAME_TTL:
                                os.remove(entry.path)
                        except OSError:
                            pass
            except OSError:
                pass

        paths = []
        for i in range(min(frames.shape[0], len(timestamps))):
            arr = (frames[i].cpu().numpy() * 255).astype(np.uint8)
            img = Image.fromarray(arr)
            fname = f"loadlast_sel_{i:04d}_{timestamps[i]:.3f}s.png"
            fpath = os.path.join(sel_dir, fname)
            img.save(fpath, "PNG")
            paths.append(fpath)

        return ",".join(paths)

    def _extract_selected_frames(
        self,
        video_path: str,
        timestamps_json: str,
        all_frames: torch.Tensor,
        duration: float = 0.0,
        fps: float = 0.0,
    ) -> torch.Tensor:
        """Extract frames at specific timestamps.

        If timestamps_json is empty or '[]', returns the first frame of all_frames
        as a single-frame batch (1, H, W, 3).
        Otherwise, seeks to each timestamp and extracts a frame.
        Always returns the same number of frames as timestamps (falls back
        to nearest pre-decoded frame on seek failure).
        """
        try:
            timestamps = json.loads(timestamps_json)
        except (json.JSONDecodeError, TypeError):
            timestamps = []

        if not timestamps:
            return all_frames[:1]

        timestamps = sorted(set(float(t) for t in timestamps))

        # Probe native video dimensions for accurate raw frame parsing
        native_w, native_h = self._probe_video_dimensions(video_path)

        selected = []
        for ts in timestamps:
            frame = self._seek_frame_ffmpeg(
                video_path, ts, all_frames, native_w, native_h,
                duration=duration, fps=fps,
            )
            # Always guaranteed to return a frame (fallback inside)
            selected.append(frame)

        return torch.stack(selected, dim=0)

    @staticmethod
    def _probe_video_dimensions(video_path: str) -> tuple[int, int]:
        """Probe native video width and height via ffprobe.

        Returns coded (non-rotated) dimensions — matches -noautorotate output.
        Returns (width, height) or (0, 0) if probing fails.
        """
        try:
            from ..core.bin_paths import get_ffprobe_bin
            ffprobe = get_ffprobe_bin()
            cmd = [
                ffprobe, "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=width,height",
                "-print_format", "csv=p=0:s=x",
                video_path,
            ]
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0 and "x" in result.stdout:
                parts = result.stdout.strip().split("x")
                return int(parts[0]), int(parts[1])
        except Exception:
            pass
        return 0, 0

    @staticmethod
    def _nearest_frame_fallback(
        timestamp: float, all_frames: torch.Tensor,
        duration: float = 0.0, fps: float = 0.0,
    ) -> torch.Tensor:
        """Return the nearest frame in all_frames for a given timestamp.

        Converts timestamp (seconds) to a frame index using the video duration
        or fps. Falls back to proportional estimate if neither is available.
        """
        n = all_frames.shape[0]
        if n <= 1:
            return all_frames[0]
        if duration > 0:
            # Map timestamp to [0, n-1] proportionally
            idx = min(n - 1, max(0, round(timestamp * (n - 1) / duration)))
        elif fps > 0:
            # Use fps to convert timestamp (seconds) to frame index
            idx = min(n - 1, max(0, round(timestamp * fps)))
        else:
            # No duration or fps — proportional guess
            idx = min(n - 1, max(0, round(timestamp * _FALLBACK_FPS_GUESS)))
        return all_frames[idx]

    def _seek_frame_ffmpeg(
        self,
        video_path: str,
        timestamp: float,
        all_frames: torch.Tensor,
        native_w: int = 0,
        native_h: int = 0,
        duration: float = 0.0,
        fps: float = 0.0,
    ) -> torch.Tensor:
        """Seek to a specific timestamp and extract a single frame.

        Uses native video dimensions (from ffprobe) for raw byte parsing.
        Falls back to nearest frame in all_frames if ffmpeg fails.
        """
        try:
            # Use native dimensions if available, otherwise fall back to all_frames
            w = native_w if native_w > 0 else all_frames.shape[2]
            h = native_h if native_h > 0 else all_frames.shape[1]

            from ..core.bin_paths import get_ffmpeg_bin
            ffmpeg = get_ffmpeg_bin()
            cmd = [
                ffmpeg, "-noautorotate",
                "-ss", str(timestamp),
                "-i", video_path,
                "-vframes", "1",
                "-f", "rawvideo",
                "-pix_fmt", "rgb24",
                "-v", "quiet",
                "-y", "pipe:1",
            ]
            result = subprocess.run(
                cmd, capture_output=True, timeout=10,
            )
            if result.returncode != 0 or not result.stdout:
                raise RuntimeError("ffmpeg seek failed")

            expected_bytes = h * w * 3
            raw = result.stdout[:expected_bytes]
            if len(raw) < expected_bytes:
                raise RuntimeError("Incomplete frame data")

            arr = np.frombuffer(raw, dtype=np.uint8).reshape(h, w, 3)
            frame = torch.from_numpy(arr.copy()).float() / 255.0

            # If native dims differ from all_frames, resize to match
            target_h, target_w = all_frames.shape[1], all_frames.shape[2]
            if h != target_h or w != target_w:
                frame_nchw = frame.permute(2, 0, 1).unsqueeze(0)
                frame_nchw = F.interpolate(
                    frame_nchw, size=(target_h, target_w),
                    mode='bilinear', align_corners=False,
                )
                frame = frame_nchw.squeeze(0).permute(1, 2, 0)

            return frame

        except Exception as e:
            logger.debug("[LoadLast] ffmpeg seek to %.2fs failed: %s", timestamp, e)
            return self._nearest_frame_fallback(timestamp, all_frames, duration, fps)
