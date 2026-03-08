"""VideoEditorNode — interactive NLE video editing node for ComfyUI.

Provides an in-canvas editing UI with trim, split, crop, speed-ramp,
volume, text overlay, and transition editing.  Operates in two modes:

1. **Passthrough** (mid-pipeline): Pauses execution via ExecutionBlocker,
   shows the editor, and passes edited clip downstream on "Continue".
2. **Terminal** (end-of-pipeline): Acts as an output node with an
   "Export" button that saves directly to disk.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import subprocess
import tempfile
import atexit
import time

import numpy as np
import torch

log = logging.getLogger("ffmpega.videoeditor")

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


class VideoEditorNode:
    """Interactive non-linear video editor node.

    Allows users to trim, split, crop, speed-ramp, adjust audio, and
    add text overlays to video clips — all inside a rich timeline UI
    rendered directly on the node canvas.
    """

    CATEGORY = "FFMPEGA"
    FUNCTION = "process"
    OUTPUT_NODE = True

    RETURN_TYPES = ("IMAGE", "STRING", "AUDIO", "FLOAT", "INT")
    RETURN_NAMES = ("IMAGE", "video_path", "AUDIO", "fps", "frame_count")

    # Class-level cache for tensor-to-file conversions (keyed by node_id)
    # Stores (file_path, content_hash) so re-execution with different
    # images invalidates the stale entry.
    _temp_video_cache: dict[str, tuple[str, str]] = {}

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "pause_on_input": ("BOOLEAN", {
                    "default": True,
                    "label_on": "pause & edit",
                    "label_off": "passthrough",
                    "tooltip": (
                        "When ON, pauses the workflow and shows the editor. "
                        "Click Continue to pass the edited clip downstream. "
                        "When OFF, passes through without editing."
                    ),
                }),
                "auto_open_editor": ("BOOLEAN", {
                    "default": False,
                    "label_on": "auto-open",
                    "label_off": "manual",
                    "tooltip": (
                        "When ON, the editor modal automatically opens "
                        "when a video arrives. When OFF, click the Open "
                        "Editor button manually."
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
                    "tooltip": "Path to a video file on disk.",
                }),
                "audio": ("AUDIO", {
                    "tooltip": "Audio track to associate with the video.",
                }),
                "fps": ("FLOAT", {
                    "default": 0.0,
                    "min": 0.0,
                    "max": 120.0,
                    "step": 0.01,
                    "tooltip": "Framerate for IMAGE tensor input. 0 = auto-detect from source.",
                }),
            },
            "hidden": {
                "_edit_segments": ("STRING", {"default": "[]"}),
                "_edit_action": ("STRING", {"default": "none"}),
                "_crop_rect": ("STRING", {"default": ""}),
                "_speed_map": ("STRING", {"default": "{}"}),
                "_volume": ("FLOAT", {"default": 1.0}),
                "_text_overlays": ("STRING", {"default": "[]"}),
                "_transitions": ("STRING", {"default": "[]"}),
                "unique_id": "UNIQUE_ID",
            },
        }

    @classmethod
    def IS_CHANGED(cls, pause_on_input=True, _edit_action="none", **kwargs):
        """Re-run when edit action changes (user clicked Continue)."""
        if not pause_on_input:
            return ""  # passthrough never re-runs on its own
        # Hash the action + segments so the node re-executes when edits change
        m = hashlib.sha256()
        m.update(_edit_action.encode())
        m.update(kwargs.get("_edit_segments", "[]").encode())
        return m.hexdigest()

    def process(
        self,
        pause_on_input: bool = True,
        auto_open_editor: bool = False,
        images=None,
        video_path: str = "",
        audio=None,
        fps: float = 0.0,
        _edit_segments: str = "[]",
        _edit_action: str = "none",
        _crop_rect: str = "",
        _speed_map: str = "{}",
        _volume: float = 1.0,
        _text_overlays: str = "[]",
        _transitions: str = "[]",
        unique_id=None,
    ):
        """Main execution method."""
        from .processing.export import render_edits

        folder_paths = _get_folder_paths()
        empty_frames = torch.zeros(1, 512, 512, 3)
        silent_audio = {"waveform": torch.zeros(1, 1, 1), "sample_rate": 44100}

        # --- Resolve video source (priority: images > video_path) ---
        resolved_path = None

        if images is not None:
            resolved_path = self._resolve_images_input(
                images, fps, unique_id, folder_paths,
            )

        if resolved_path is None and video_path and video_path.strip():
            vp = video_path.strip()
            if not self._is_path_sandboxed(vp):
                log.warning(
                    "[VideoEditor] video_path '%s' is outside allowed directories, ignoring", vp,
                )
            elif os.path.isfile(vp):
                resolved_path = vp
            else:
                log.warning("[VideoEditor] video_path not found: %s", vp)

        if resolved_path is None:
            log.info("[VideoEditor] No input connected")
            return {
                "ui": {"text": ["Connect a video path or IMAGE tensor"]},
                "result": (empty_frames, "", silent_audio, 0.0, 0),
            }

        # --- Passthrough mode: skip editing ---
        if not pause_on_input:
            frames, frame_count, actual_fps = self._decode_video(
                resolved_path, folder_paths,
            )
            if audio is None:
                audio = silent_audio
            return {
                "ui": {},
                "result": (frames, resolved_path, audio, actual_fps, frame_count),
            }

        # --- Pause mode: ExecutionBlocker if no edits yet ---
        if _edit_action == "none":
            return self._return_blocked(resolved_path, folder_paths)

        # --- Apply edits (user clicked Continue) ---
        if _edit_action == "passthrough":
            # Check if there are actually any edits to apply
            has_real_edits = (
                _edit_segments != "[]"
                or (_crop_rect and _crop_rect.strip() and _crop_rect != "{}")
                or self._has_speed_changes(_speed_map)
                or abs(_volume - 1.0) > 0.01
                or (_text_overlays and _text_overlays != "[]")
                or (_transitions and _transitions != "[]")
            )

            if not has_real_edits:
                # No edits — fast path, pass through original
                frames, frame_count, actual_fps = self._decode_video(
                    resolved_path, folder_paths,
                )
                if audio is None:
                    audio = silent_audio
                return {
                    "ui": {},
                    "result": (
                        frames, resolved_path, audio,
                        actual_fps, frame_count,
                    ),
                }

            # Apply edits via FFmpeg
            temp_dir = folder_paths.get_temp_directory() if folder_paths else "/tmp"
            os.makedirs(temp_dir, exist_ok=True)
            output_path = os.path.join(
                temp_dir,
                f"videoeditor_{unique_id or 'out'}_{int(time.time())}.mp4",
            )

            result = render_edits(
                resolved_path,
                output_path,
                segments_json=_edit_segments,
                crop_json=_crop_rect,
                speed_map_json=_speed_map,
                volume=_volume,
                text_overlays_json=_text_overlays,
                transitions_json=_transitions,
            )

            if not result.get("success"):
                log.warning(
                    "[VideoEditor] Render failed: %s",
                    result.get("error", "unknown"),
                )
                # Fall back to original
                output_path = resolved_path

            # Decode edited video to frames
            frames, frame_count, actual_fps = self._decode_video(
                output_path, folder_paths,
            )
            if audio is None:
                audio = silent_audio

            return {
                "ui": {},
                "result": (
                    frames, output_path, audio,
                    actual_fps, frame_count,
                ),
            }

        # Unknown action — pass through
        frames, frame_count, actual_fps = self._decode_video(
            resolved_path, folder_paths,
        )
        if audio is None:
            audio = silent_audio
        return {
            "ui": {},
            "result": (frames, resolved_path, audio, actual_fps, frame_count),
        }

    # ─── Private helpers ────────────────────────────────────────────

    def _resolve_images_input(
        self,
        images: torch.Tensor,
        fps: float,
        unique_id,
        folder_paths,
    ) -> str | None:
        """Convert IMAGE tensor to a temp video file."""
        try:
            temp_dir = folder_paths.get_temp_directory() if folder_paths else "/tmp"
            os.makedirs(temp_dir, exist_ok=True)

            cache_key = str(unique_id) if unique_id else "default"
            content_hash = self._tensor_content_hash(images)

            # Check cache — invalidate if tensor content changed
            cached = self._temp_video_cache.get(cache_key)
            if cached:
                cached_path, cached_hash = cached
                if cached_hash == content_hash and os.path.isfile(cached_path):
                    return cached_path
                # Stale — delete old file
                try:
                    os.unlink(cached_path)
                except OSError:
                    pass

            _fd, temp_path = tempfile.mkstemp(
                prefix="videoeditor_", suffix=".mp4", dir=temp_dir,
            )
            os.close(_fd)

            self._images_to_video(images, temp_path, fps=int(fps) if fps > 0 else 24)
            self._temp_video_cache[cache_key] = (temp_path, content_hash)
            return temp_path

        except Exception as e:
            log.warning("[VideoEditor] Failed to convert images: %s", e)
            return None

    @staticmethod
    def _tensor_content_hash(images: torch.Tensor) -> str:
        """Compute a lightweight hash of tensor shape + sampled content."""
        m = hashlib.sha256()
        m.update(str(images.shape).encode())
        # Sample first and last frame to detect content changes
        m.update(images[0].cpu().numpy().tobytes()[:1024])
        if images.shape[0] > 1:
            m.update(images[-1].cpu().numpy().tobytes()[:1024])
        return m.hexdigest()

    @staticmethod
    def _images_to_video(
        images: torch.Tensor, output_path: str, fps: int = 24,
    ) -> None:
        """Stream IMAGE tensor frames to FFmpeg → temp video.

        Delegates to ``core.images_to_video`` shared utility.
        """
        from ..core.images_to_video import images_to_video
        images_to_video(images, output_path, fps=fps)

    def _return_blocked(self, resolved_path: str, folder_paths):
        """Return ExecutionBlocker to pause the workflow for editing."""
        try:
            from comfy_execution.graph import ExecutionBlocker
            blocked = ExecutionBlocker(None)

            log.info("[VideoEditor] Paused — waiting for user edits")
            return {
                "ui": {
                    "video_path": [resolved_path],
                },
                "result": tuple(blocked for _ in range(5)),
            }
        except ImportError:
            log.warning(
                "[VideoEditor] ExecutionBlocker not available — "
                "requires ComfyUI 0.1.3+. Passing through."
            )
            # Graceful fallback: pass through without pausing
            frames, frame_count, actual_fps = self._decode_video(
                resolved_path, folder_paths,
            )
            silent_audio = {
                "waveform": torch.zeros(1, 1, 1), "sample_rate": 44100,
            }
            return {
                "ui": {},
                "result": (
                    frames, resolved_path, silent_audio,
                    actual_fps, frame_count,
                ),
            }

    @staticmethod
    def _decode_video(
        video_path: str, folder_paths,
    ) -> tuple[torch.Tensor, int, float]:
        """Decode video to frames + metadata.

        Uses the LoadLast VideoDecoder if available, otherwise falls back
        to simple FFmpeg frame extraction.
        """
        try:
            from ..loadlast.processing.video_decode import VideoDecoder
            decoder = VideoDecoder()
            frames, metadata = decoder.decode_file(video_path, max_frames=256)
            if frames is not None and frames.shape[0] > 0:
                return (
                    frames,
                    frames.shape[0],
                    float(metadata.get("fps", 24.0)),
                )
        except Exception as e:
            log.debug("[VideoEditor] VideoDecoder fallback: %s", e)

        # Minimal fallback
        return torch.zeros(1, 512, 512, 3), 0, 24.0

    @staticmethod
    def _has_speed_changes(speed_map_json: str) -> bool:
        """Check if any segment has a non-1.0 speed."""
        from .processing.export import _has_speed_changes
        return _has_speed_changes(speed_map_json)

    @staticmethod
    def _is_path_sandboxed(path: str) -> bool:
        """Check if a path is within ComfyUI's allowed directories."""
        try:
            from ..loadlast.discovery.path_utils import is_path_sandboxed
            return is_path_sandboxed(path)
        except ImportError:
            # Fallback: deny if we can't verify (fail-closed, matches server.py)
            return False


# Clean up temp video files on process exit
def _cleanup_temp_video_cache():
    """Remove all cached temp videos (called at interpreter exit)."""
    for path, _hash in list(VideoEditorNode._temp_video_cache.values()):
        try:
            os.unlink(path)
        except OSError:
            pass
    VideoEditorNode._temp_video_cache.clear()


atexit.register(_cleanup_temp_video_cache)
