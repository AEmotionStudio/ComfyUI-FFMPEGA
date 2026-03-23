"""Frame Picker Node — Interactive frame selection and reordering.

Provides an inline editing UI where users can:
1. Browse video frames via a contact-sheet grid
2. Select/deselect frames (click, Shift+click, Ctrl+click)
3. Reorder selected frames via drag-and-drop
4. Use bulk tools: Select All, Deselect All, Invert, Every Nth
5. Apply selection to output only chosen frames downstream

Architecture follows the FacePoke / VideoEditor patterns:
- Upstream inputs (images/video_path) always win over uploaded video
- Pause mode: pause via ExecutionBlocker, show picker, resume on Apply
- Passthrough mode: skip selection, pass all frames unchanged
"""

from __future__ import annotations

import atexit
import hashlib
import json
import logging
import os
import subprocess
import tempfile
import time
from collections import OrderedDict
from typing import Optional

import cv2
import numpy as np
import torch

logger = logging.getLogger("ffmpega")

# Lazy import to avoid circular deps at module load
_folder_paths = None


def _get_folder_paths():
    """Lazy-load ComfyUI's folder_paths module."""
    global _folder_paths
    if _folder_paths is None:
        try:
            import folder_paths
            _folder_paths = folder_paths
        except ImportError:
            pass
    return _folder_paths


# ── Server-side state (node_id → selection dict) ────────────────────────
_MAX_STATE_ENTRIES = 50

_framepicker_selection_states: OrderedDict[str, dict] = OrderedDict()
_framepicker_frame_cache: OrderedDict[str, dict] = OrderedDict()


def _capped_insert(store: OrderedDict, key: str, value: dict) -> None:
    """Insert into an ordered dict, evicting oldest if over cap."""
    if key in store:
        store.move_to_end(key)
    store[key] = value
    while len(store) > _MAX_STATE_ENTRIES:
        store.popitem(last=False)


def _resolve_video_path(video_path: str) -> str | None:
    """Resolve a video path to an absolute path.

    Handles relative paths like ``input/file.mp4`` by resolving them
    against ComfyUI's input directory via ``folder_paths``.
    """
    if not video_path:
        return None
    # Already absolute and exists?
    if os.path.isabs(video_path) and os.path.isfile(video_path):
        return video_path
    # Try CWD-relative
    if os.path.isfile(video_path):
        return os.path.abspath(video_path)
    # Resolve via folder_paths (handles "input/file.mp4")
    fp = _get_folder_paths()
    if fp:
        # Strip leading "input/" prefix if present
        clean = video_path
        for prefix in ("input/", "input\\"):
            if clean.startswith(prefix):
                clean = clean[len(prefix):]
                break
        for getter in ("get_input_directory", "get_temp_directory",
                       "get_output_directory"):
            try:
                d = getattr(fp, getter)()
                candidate = os.path.join(d, clean)
                if os.path.isfile(candidate):
                    return candidate
            except Exception:
                pass
    return None


# ── API Routes ──────────────────────────────────────────────────────────

try:
    import base64
    from aiohttp import web
    from server import PromptServer  # type: ignore[import-not-found]

    @PromptServer.instance.routes.post("/framepicker/get_frames")
    async def _api_fp_get_frames(request):
        """Return frame metadata for a video (used by the picker grid)."""
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "invalid JSON"}, status=400)

        node_id = str(body.get("node_id", ""))
        raw_path = str(body.get("video_path", ""))
        video_path = _resolve_video_path(raw_path)

        if not video_path:
            return web.json_response(
                {"error": f"video_path not found: {raw_path}"}, status=400)

        cache = _framepicker_frame_cache.get(node_id, {})
        if cache.get("path") == video_path and cache.get("meta"):
            return web.json_response(cache["meta"])

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            return web.json_response(
                {"error": "could not open video"}, status=400)

        fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        cap.release()

        meta = {
            "fps": fps,
            "total_frames": total_frames,
            "width": width,
            "height": height,
        }

        _capped_insert(_framepicker_frame_cache, node_id, {
            "path": video_path, "meta": meta,
        })

        return web.json_response(meta)

    @PromptServer.instance.routes.post("/framepicker/get_frame")
    async def _api_fp_get_frame(request):
        """Return a single frame as JPEG for the picker grid."""
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "invalid JSON"}, status=400)

        raw_path = str(body.get("video_path", ""))
        frame_idx = int(body.get("frame_idx", 0))
        thumb_width = int(body.get("thumb_width", 160))
        video_path = _resolve_video_path(raw_path)

        if not video_path:
            return web.json_response(
                {"error": f"video_path not found: {raw_path}"}, status=400)

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            return web.json_response(
                {"error": "could not open video"}, status=400)

        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ret, frame = cap.read()
        cap.release()

        if not ret or frame is None:
            return web.json_response(
                {"error": f"frame {frame_idx} not readable"}, status=400)

        # Resize for thumbnail
        h, w = frame.shape[:2]
        if w > thumb_width:
            scale = thumb_width / w
            new_h = max(1, int(h * scale))
            frame = cv2.resize(frame, (thumb_width, new_h),
                               interpolation=cv2.INTER_AREA)

        _, jpg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        return web.Response(
            body=jpg.tobytes(),
            content_type="image/jpeg",
        )

    @PromptServer.instance.routes.post("/framepicker/get_thumbnails")
    async def _api_fp_get_thumbnails(request):
        """Batch-fetch multiple frame thumbnails as base64 array."""
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "invalid JSON"}, status=400)

        raw_path = str(body.get("video_path", ""))
        frame_indices = body.get("frame_indices", [])
        thumb_width = int(body.get("thumb_width", 160))
        video_path = _resolve_video_path(raw_path)

        if not video_path:
            return web.json_response(
                {"error": f"video_path not found: {raw_path}"}, status=400)

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            return web.json_response(
                {"error": "could not open video"}, status=400)

        thumbnails = []
        for idx in frame_indices:
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(idx))
            ret, frame = cap.read()
            if not ret or frame is None:
                thumbnails.append(None)
                continue

            h, w = frame.shape[:2]
            if w > thumb_width:
                scale = thumb_width / w
                new_h = max(1, int(h * scale))
                frame = cv2.resize(frame, (thumb_width, new_h),
                                   interpolation=cv2.INTER_AREA)

            _, jpg = cv2.imencode(
                ".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
            thumbnails.append(base64.b64encode(jpg.tobytes()).decode("ascii"))

        cap.release()
        return web.json_response({"thumbnails": thumbnails})

    @PromptServer.instance.routes.post("/framepicker/apply_selection")
    async def _api_fp_apply_selection(request):
        """Store selected+ordered frame indices, then Allow re-queue."""
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "invalid JSON"}, status=400)

        node_id = str(body.get("node_id", ""))
        if not node_id:
            return web.json_response(
                {"error": "node_id required"}, status=400)

        selected_indices = body.get("selected_indices")  # list[int]
        transforms = body.get("transforms")  # dict[str, {flipH, flipV, rotate}]
        if selected_indices is not None:
            _capped_insert(_framepicker_selection_states, node_id, {
                "data": selected_indices,
                "transforms": transforms or {},
                "ts": time.time(),
            })
            logger.info("[FramePicker] Selection stored for node %s "
                        "(%d frames selected, %d transforms)", node_id,
                        len(selected_indices),
                        len(transforms) if transforms else 0)
        else:
            _framepicker_selection_states.pop(node_id, None)
            logger.debug("[FramePicker] Selection cleared for node %s",
                         node_id)

        return web.json_response({"ok": True})

except (ImportError, AttributeError):
    # Running outside ComfyUI (e.g. pytest) — skip route registration
    logger.debug("[FramePicker] API routes skipped (no PromptServer)")


# ── FramePicker ComfyUI Node ───────────────────────────────────────────

class FramePickerNode:
    """Interactive frame selection and reordering node.

    Provides a grid-based picker UI for selecting, removing, and
    reordering video frames. Follows the FacePoke / VideoEditor
    patterns for upstream input priority + ExecutionBlocker.

    Input priority: upstream video_path > upstream images > uploaded.
    """

    CATEGORY = "FFMPEGA"
    FUNCTION = "execute"
    RETURN_TYPES = ("IMAGE", "STRING", "AUDIO", "STRING", "MASK")
    RETURN_NAMES = ("images", "video_path", "audio", "selected_indices", "mask")
    OUTPUT_NODE = True

    # Cache for images→video conversions (keyed by node_id)
    _temp_video_cache: dict[str, tuple[str, str]] = {}

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "pause_on_input": ("BOOLEAN", {
                    "default": True,
                    "label_on": "pause & pick",
                    "label_off": "passthrough",
                    "tooltip": (
                        "When ON, pauses the workflow and shows the frame "
                        "picker. Click Apply to pass selected frames "
                        "downstream. When OFF, passes all frames unchanged."
                    ),
                }),
                "auto_open_editor": ("BOOLEAN", {
                    "default": True,
                    "tooltip": (
                        "When ON, the frame picker modal auto-opens when "
                        "the workflow pauses. When OFF, click 'Open Frame "
                        "Picker' manually."
                    ),
                }),
            },
            "optional": {
                "images": ("IMAGE", {
                    "tooltip": "Video frames as IMAGE tensor batch [N,H,W,3].",
                }),
                "video_path": ("STRING", {
                    "default": "",
                    "forceInput": True,
                    "tooltip": "Path to a video file on disk. "
                               "Upstream connections always win over "
                               "uploaded video.",
                }),
                "audio": ("AUDIO", {
                    "tooltip": "Audio track to associate with the video.",
                }),
                "fps": ("FLOAT", {
                    "default": 0.0,
                    "min": 0.0, "max": 120.0, "step": 0.01,
                    "forceInput": True,
                    "tooltip": "Framerate for IMAGE tensor input. "
                               "0 = auto-detect from source.",
                }),
                "mask": ("MASK", {
                    "tooltip": (
                        "Optional upstream MASK pass-through. "
                        "When connected, selected frames extract "
                        "corresponding mask frames."
                    ),
                }),
            },
            "hidden": {
                "_edit_action": ("STRING", {"default": "none"}),
                "unique_id": "UNIQUE_ID",
            },
        }

    @classmethod
    def IS_CHANGED(cls, pause_on_input=True, _edit_action="none", **kwargs):
        if not pause_on_input:
            return ""  # passthrough never re-runs on its own
        m = hashlib.sha256()
        m.update(str(_edit_action).encode())
        m.update(str(time.time()).encode())
        return m.hexdigest()

    @classmethod
    def VALIDATE_INPUTS(cls, **kwargs):
        fps_val = kwargs.get("fps", 0.0)
        if fps_val is not None and fps_val != "":
            try:
                float(fps_val)
            except (ValueError, TypeError):
                return f"Invalid fps value: {fps_val}"
        return True

    def execute(
        self,
        pause_on_input: bool = True,
        auto_open_editor: bool = True,
        images=None,
        video_path: str = "",
        audio=None,
        fps: float = 0.0,
        mask=None,
        _edit_action: str = "none",
        unique_id=None,
        **kwargs,
    ):
        """Execute the Frame Picker node.

        Flow:
        1. Resolve video source (priority: video_path > images > uploaded)
        2. Passthrough mode: skip selection, pass all frames unchanged
        3. Pause mode + no selection: show picker UI, return ExecutionBlocker
        4. Apply mode: filter/reorder frames per stored selection
        """
        # Defensive cast — fps may arrive as "" from an unconnected widget
        try:
            fps = float(fps) if fps is not None and fps != "" else 0.0
        except (ValueError, TypeError):
            fps = 0.0

        folder_paths = _get_folder_paths()
        empty_frames = torch.zeros(1, 512, 512, 3)
        silent_audio = {
            "waveform": torch.zeros(1, 1, 1), "sample_rate": 44100}
        empty_mask = mask if mask is not None else torch.zeros(1, 512, 512, dtype=torch.float32)

        # ── Resolve video source (priority: video_path > images) ──
        resolved_path = None

        if video_path and video_path.strip():
            vp = video_path.strip()
            if images is not None:
                logger.info("[FramePicker] Both video_path and images "
                            "connected — using video_path")
            if not self._is_path_sandboxed(vp):
                logger.warning("[FramePicker] video_path '%s' outside "
                               "allowed directories, ignoring", vp)
            elif os.path.isfile(vp):
                resolved_path = vp
                logger.info("[FramePicker] using upstream video_path: %s", vp)
            else:
                logger.warning("[FramePicker] video_path not found: %s", vp)

        if resolved_path is None and images is not None:
            resolved_path = self._resolve_images_input(
                images, fps, unique_id, folder_paths)

        if resolved_path is None:
            logger.info("[FramePicker] No input connected")
            return {
                "ui": {"text": ["Connect a video path, IMAGE tensor, "
                                "or upload a video"]},
                "result": (empty_frames, "", silent_audio, "[]", empty_mask),
            }

        # ── Extract audio from video if no upstream audio ──
        if audio is None and resolved_path:
            audio = self._extract_audio(resolved_path)
        if audio is None:
            audio = silent_audio

        # ── Get video metadata ──
        cap = cv2.VideoCapture(resolved_path)
        actual_fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        cap.release()

        # Use upstream fps if provided, otherwise video's fps
        if fps > 0:
            actual_fps = fps

        # ── Passthrough mode: skip selection ──
        if not pause_on_input:
            frames = self._load_frames(resolved_path)
            all_indices = list(range(frames.shape[0]))
            return {
                "ui": {"video_path": [resolved_path]},
                "result": (frames, resolved_path, audio,
                           json.dumps(all_indices), empty_mask),
            }

        # ── Check for server-side selection (from Apply button) ──
        node_id = str(unique_id) if unique_id else ""
        server_selection = None
        state = _framepicker_selection_states.pop(node_id, None)
        if state and state.get("data") is not None:
            server_selection = state["data"]
            logger.info("[FramePicker] Found server-side selection for "
                        "node %s (%d frames)",
                        node_id, len(server_selection))

        if server_selection is not None or _edit_action == "apply":
            selected = server_selection if server_selection is not None \
                else list(range(total_frames))

            # Get transforms from stored state
            transforms = {}
            if state and state.get("transforms"):
                transforms = state["transforms"]

            # Build output from selected frames in order
            output_path, frames = self._build_selected_output(
                resolved_path, selected, actual_fps, transforms)
            selected_json = json.dumps(selected)

            # Extract matching mask frames for selection
            if mask is not None and mask.shape[0] > 1:
                valid_idx = [i for i in selected if 0 <= i < mask.shape[0]]
                if valid_idx:
                    selected_mask = mask[valid_idx]
                else:
                    selected_mask = empty_mask
            else:
                selected_mask = empty_mask

            return {
                "ui": {"video_path": [output_path]},
                "result": (frames, output_path, audio,
                           selected_json,
                           selected_mask),
            }

        if _edit_action == "passthrough":
            frames = self._load_frames(resolved_path)
            all_indices = list(range(frames.shape[0]))
            return {
                "ui": {"video_path": [resolved_path]},
                "result": (frames, resolved_path, audio,
                           json.dumps(all_indices), empty_mask),
            }

        # ── First run: show picker UI and pause ──
        logger.info("[FramePicker] Pausing — waiting for frame selection")

        try:
            from comfy_execution.graph import ExecutionBlocker
            blocked = ExecutionBlocker(None)

            return {
                "ui": {
                    "video_path": [resolved_path],
                    "framepicker_meta": [{
                        "video_path": resolved_path,
                        "total_frames": total_frames,
                        "fps": actual_fps,
                        "width": width,
                        "height": height,
                    }],
                },
                "result": tuple(blocked for _ in range(5)),
            }
        except ImportError:
            logger.warning(
                "[FramePicker] ExecutionBlocker not available — "
                "requires ComfyUI 0.1.3+. Passing through.")
            frames = self._load_frames(resolved_path)
            all_indices = list(range(frames.shape[0]))
            return {
                "result": (frames, resolved_path, audio,
                           json.dumps(all_indices), empty_mask),
            }

    # ─── Private helpers ────────────────────────────────────────────

    def _resolve_images_input(
        self,
        images: torch.Tensor,
        fps: float,
        unique_id,
        folder_paths,
    ) -> str | None:
        """Convert IMAGE tensor batch to a temp video file."""
        if images is None or images.shape[0] == 0:
            return None

        node_id = str(unique_id) if unique_id else "default"
        batch_hash = hashlib.md5(
            f"{images.shape}:{images.sum().item():.6f}".encode()
        ).hexdigest()[:12]

        # Check cache
        if node_id in self._temp_video_cache:
            cached_path, cached_hash = self._temp_video_cache[node_id]
            if cached_hash == batch_hash and os.path.isfile(cached_path):
                logger.debug("[FramePicker] Using cached temp video: %s",
                             cached_path)
                return cached_path

        # Create temp video from IMAGE tensor
        use_fps = fps if fps > 0 else 24.0
        temp_dir = (folder_paths.get_temp_directory()
                    if folder_paths else tempfile.mkdtemp(
                        prefix="ffmpega_fpick_"))
        os.makedirs(temp_dir, exist_ok=True)
        out_path = os.path.join(temp_dir,
                                f"framepicker_{node_id}_{batch_hash}.mp4")

        n, h, w, c = images.shape
        fourcc = cv2.VideoWriter.fourcc(*"mp4v")
        writer = cv2.VideoWriter(out_path, fourcc, use_fps, (w, h))

        for i in range(n):
            frame = (images[i].cpu().numpy() * 255.0).clip(
                0, 255).astype(np.uint8)
            bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
            writer.write(bgr)

        writer.release()

        self._temp_video_cache[node_id] = (out_path, batch_hash)
        logger.info("[FramePicker] Created temp video from %d frames: %s",
                    n, out_path)
        return out_path

    def _extract_audio(self, video_path: str) -> dict | None:
        """Extract audio track from video as ComfyUI AUDIO dict."""
        try:
            from ..core.bin_paths import get_ffmpeg_bin
            ffmpeg = get_ffmpeg_bin()
        except ImportError:
            try:
                from core.bin_paths import get_ffmpeg_bin  # type: ignore
                ffmpeg = get_ffmpeg_bin()
            except ImportError:
                ffmpeg = "ffmpeg"

        try:
            sample_rate = 44100
            channels = 2
            result = subprocess.run(
                [
                    ffmpeg, "-i", video_path,
                    "-vn", "-f", "wav",
                    "-acodec", "pcm_s16le",
                    "-ac", str(channels),
                    "-ar", str(sample_rate),
                    "pipe:1",
                ],
                capture_output=True, timeout=30,
            )
            if result.returncode != 0 or not result.stdout:
                return None

            import struct
            data = result.stdout
            if len(data) <= 44:
                return None

            idx = data.find(b'data', 12)
            if idx < 0:
                return None
            data_size = struct.unpack_from('<I', data, idx + 4)[0]
            pcm_start = idx + 8
            available = len(data) - pcm_start
            if available <= 0:
                return None
            if data_size > available:
                data_size = available
            pcm_bytes = data[pcm_start:pcm_start + data_size]

            samples = np.frombuffer(
                pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
            remainder = len(samples) % channels
            if remainder:
                samples = samples[:-remainder]
            if len(samples) == 0:
                return None
            samples = samples.reshape(-1, channels).T
            waveform = torch.from_numpy(samples).unsqueeze(0)

            return {"waveform": waveform, "sample_rate": sample_rate}
        except Exception as e:
            logger.warning("[FramePicker] Audio extraction failed: %s", e)
            return None

    def _load_frames(self, video_path: str) -> torch.Tensor:
        """Load all frames from a video as a normalized tensor."""
        cap = cv2.VideoCapture(video_path)
        frames = []
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            frames.append(
                torch.from_numpy(rgb).float() / 255.0)
        cap.release()

        if not frames:
            return torch.zeros(1, 64, 64, 3)

        return torch.stack(frames)

    def _build_selected_output(
        self,
        video_path: str,
        selected_indices: list[int],
        fps: float,
        transforms: dict | None = None,
    ) -> tuple[str, torch.Tensor]:
        """Build output video + tensor from selected frame indices.

        Applies per-frame transforms (flipH, flipV, rotate) if present.
        Returns (output_video_path, frames_tensor).
        """
        logger.info("[FramePicker] Building output with %d selected frames",
                    len(selected_indices))
        if transforms:
            logger.info("[FramePicker] Applying %d frame transforms",
                        len(transforms))

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise RuntimeError(f"Cannot open video: {video_path}")

        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        # Read all frames needed (seek to each)
        frames_bgr: dict[int, np.ndarray] = {}
        for idx in selected_indices:
            if idx in frames_bgr:
                continue
            if idx < 0 or idx >= total:
                continue
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ret, frame = cap.read()
            if ret and frame is not None:
                frames_bgr[idx] = frame
        cap.release()

        if not frames_bgr:
            return video_path, torch.zeros(1, 64, 64, 3)

        # Apply per-frame transforms
        if transforms:
            for idx_str, t in transforms.items():
                idx = int(idx_str)
                if idx not in frames_bgr:
                    continue
                frame = frames_bgr[idx]
                if t.get("flipH"):
                    frame = cv2.flip(frame, 1)  # horizontal flip
                if t.get("flipV"):
                    frame = cv2.flip(frame, 0)  # vertical flip
                rot = t.get("rotate", 0)
                if rot == 90:
                    frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
                elif rot == 180:
                    frame = cv2.rotate(frame, cv2.ROTATE_180)
                elif rot == 270:
                    frame = cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)
                frames_bgr[idx] = frame

        # Recalculate output dimensions (rotation may change w/h)
        # Use first available frame's dimensions
        sample_frame = next(iter(frames_bgr.values()))
        out_h, out_w = sample_frame.shape[:2]

        # Build tensor in selection order
        tensors = []
        for idx in selected_indices:
            if idx in frames_bgr:
                rgb = cv2.cvtColor(frames_bgr[idx], cv2.COLOR_BGR2RGB)
                tensors.append(
                    torch.from_numpy(rgb).float() / 255.0)
        if not tensors:
            return video_path, torch.zeros(1, 64, 64, 3)

        stacked = torch.stack(tensors)

        # Write output video
        folder_paths = _get_folder_paths()
        out_dir = (folder_paths.get_temp_directory()
                   if folder_paths
                   else tempfile.mkdtemp(prefix="ffmpega_fpick_"))
        os.makedirs(out_dir, exist_ok=True)
        base = os.path.splitext(os.path.basename(video_path))[0]
        out_path = os.path.join(
            out_dir, f"{base}_framepick.mp4")

        fourcc = cv2.VideoWriter.fourcc(*"mp4v")
        writer = cv2.VideoWriter(
            out_path, fourcc, fps, (out_w, out_h))

        for idx in selected_indices:
            if idx in frames_bgr:
                writer.write(frames_bgr[idx])
        writer.release()

        # Re-mux with proper codec
        try:
            from ..core.bin_paths import get_ffmpeg_bin
            ffmpeg = get_ffmpeg_bin()
        except ImportError:
            try:
                from core.bin_paths import get_ffmpeg_bin  # type: ignore
                ffmpeg = get_ffmpeg_bin()
            except ImportError:
                ffmpeg = "ffmpeg"

        final_path = os.path.join(
            out_dir, f"{base}_framepick_final.mp4")
        cmd = [
            ffmpeg, "-y",
            "-i", out_path,
            "-c:v", "libx264",
            "-crf", "18",
            "-preset", "fast",
            "-pix_fmt", "yuv420p",
            "-an",  # No audio for selected-frames output
            final_path,
        ]
        try:
            subprocess.run(cmd, capture_output=True, timeout=300)
            if os.path.isfile(final_path):
                os.remove(out_path)
                return final_path, stacked
        except Exception as e:
            logger.warning("[FramePicker] FFmpeg remux failed: %s", e)

        return out_path, stacked

    @staticmethod
    def _is_path_sandboxed(path: str) -> bool:
        """Check if a path is within ComfyUI's or system temp directories."""
        try:
            from ..loadlast.discovery.path_utils import is_path_sandboxed
            if is_path_sandboxed(path):
                return True
        except ImportError:
            pass

        real = os.path.realpath(path)
        sys_tmp = os.path.realpath(tempfile.gettempdir())
        return real == sys_tmp or real.startswith(sys_tmp + os.sep)


# Clean up temp video files on process exit
def _cleanup_temp_video_cache():
    for path, _hash in list(FramePickerNode._temp_video_cache.values()):
        try:
            os.unlink(path)
        except OSError:
            pass
    FramePickerNode._temp_video_cache.clear()


atexit.register(_cleanup_temp_video_cache)
