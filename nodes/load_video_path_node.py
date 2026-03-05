"""Load Video Path node for ComfyUI.

Zero-memory alternative to the standard Load Video node for multi-video
workflows.  Instead of loading all frames as a ~21 GB IMAGE tensor, this
node simply validates that the video file exists and outputs the file path
as a STRING.  Connect the output to FFMPEGA Agent's video_a / video_b / …
slots so ffmpeg reads the file directly from disk.

Features:
  - ComfyUI file picker dropdown + custom upload button (video files only)
  - Inline video preview via ComfyUI's /view endpoint
  - Video metadata via ffprobe (fps, duration, resolution, frame count)
  - VHS-style trim parameters (force_rate, skip_first_frames, etc.)
  - Multiple outputs: video_path, frame_count, fps, duration

Memory cost: ~0 MB regardless of video length or resolution.
"""

import hashlib
import json
import logging
import math
import os
import subprocess

import torch

import folder_paths
try:
    from ..core.bin_paths import get_ffmpeg_bin, get_ffprobe_bin
except ImportError:
    from core.bin_paths import get_ffmpeg_bin, get_ffprobe_bin  # type: ignore

logger = logging.getLogger("FFMPEGA")

# Maximum values for integer parameters
BIGMAX = 2**31 - 1


def _probe_video(video_path: str) -> dict:
    """Get video metadata via ffprobe.

    Returns dict with keys: width, height, fps, duration, total_frames.
    Returns sensible defaults on failure.
    """
    defaults = {
        "width": 0, "height": 0,
        "fps": 24.0, "duration": 0.0, "total_frames": 0,
    }
    ffprobe_bin = get_ffprobe_bin()
    if not ffprobe_bin or not os.path.isfile(video_path):
        return defaults

    try:
        result = subprocess.run(
            [
                ffprobe_bin, "-v", "quiet",
                "-print_format", "json",
                "-show_format", "-show_streams",
                video_path,
            ],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode != 0:
            return defaults

        data = json.loads(result.stdout)

        # Find the video stream
        video_stream = None
        for s in data.get("streams", []):
            if s.get("codec_type") == "video":
                video_stream = s
                break
        if not video_stream:
            return defaults

        # Resolution
        width = int(video_stream.get("width", 0))
        height = int(video_stream.get("height", 0))

        # FPS — parse r_frame_rate fraction like "30/1" or "30000/1001"
        fps = 24.0
        r_fps = video_stream.get("r_frame_rate", "")
        if "/" in r_fps:
            num, den = r_fps.split("/")
            if int(den) > 0:
                fps = int(num) / int(den)
        elif r_fps:
            fps = float(r_fps)

        # Duration — try stream duration, then format duration
        duration = 0.0
        if "duration" in video_stream:
            duration = float(video_stream["duration"])
        elif "duration" in data.get("format", {}):
            duration = float(data["format"]["duration"])

        # Total frames — try nb_frames, else compute from fps * duration
        total_frames = 0
        if "nb_frames" in video_stream:
            total_frames = int(video_stream["nb_frames"])
        elif fps > 0 and duration > 0:
            total_frames = int(math.ceil(fps * duration))

        return {
            "width": width,
            "height": height,
            "fps": round(fps, 3),
            "duration": round(duration, 3),
            "total_frames": total_frames,
        }
    except Exception as e:
        logger.warning("ffprobe failed for %s: %s", video_path, e)
        return defaults


class LoadVideoPathNode:
    """Pick a video file and output its path + metadata — zero memory cost."""

    @classmethod
    def INPUT_TYPES(cls):
        input_dir = folder_paths.get_input_directory()
        try:
            files = [
                f for f in os.listdir(input_dir)
                if os.path.isfile(os.path.join(input_dir, f))
            ]
            files = folder_paths.filter_files_content_types(files, ["video"])
        except Exception:
            files = []
        if not files:
            files = [""]  # Fallback so the combo isn't empty
        return {
            "required": {
                "video": (sorted(files), {
                    "tooltip": (
                        "Select or upload a video file. The file is NOT "
                        "loaded into memory — only the path is forwarded "
                        "to the FFMPEGA Agent so ffmpeg reads it directly."
                    ),
                }),
                "force_rate": ("FLOAT", {
                    "default": 0, "min": 0, "max": 60, "step": 0.01,
                    "tooltip": (
                        "Override the video's FPS. 0 = use source FPS."
                    ),
                }),
                "skip_first_frames": ("INT", {
                    "default": 0, "min": 0, "max": BIGMAX, "step": 1,
                    "tooltip": "Number of frames to skip from the start.",
                }),
                "frame_load_cap": ("INT", {
                    "default": 0, "min": 0, "max": BIGMAX, "step": 1,
                    "tooltip": (
                        "Maximum number of frames to use. 0 = all frames."
                    ),
                }),
                "select_every_nth": ("INT", {
                    "default": 1, "min": 1, "max": BIGMAX, "step": 1,
                    "tooltip": "Select every Nth frame (1 = every frame).",
                }),
            },
            "optional": {
                "images": ("IMAGE", {
                    "tooltip": (
                        "Optional upstream IMAGE pass-through "
                        "(e.g. from Save Video or VHS)."
                    ),
                }),
                "audio": ("AUDIO", {
                    "tooltip": (
                        "Optional upstream AUDIO pass-through. "
                        "If connected, this audio is forwarded "
                        "instead of silence."
                    ),
                }),
                "video_path": ("STRING", {
                    "forceInput": True,
                    "tooltip": (
                        "Optional upstream video path string "
                        "(e.g. from Save Video). Overrides "
                        "the file-picker selector when connected."
                    ),
                }),
                "mask_points": ("STRING", {
                    "forceInput": True,
                    "tooltip": (
                        "Optional upstream mask_points pass-through. "
                        "When connected, overrides the locally drawn "
                        "mask points."
                    ),
                }),
            },
            "hidden": {
                "mask_points_data": "STRING",
            },
        }

    RETURN_TYPES = ("STRING", "INT", "FLOAT", "FLOAT", "STRING", "IMAGE", "AUDIO")
    RETURN_NAMES = ("video_path", "frame_count", "fps", "duration", "mask_points", "images", "audio")
    OUTPUT_TOOLTIPS = (
        "Validated video file path — connect to FFMPEGA Agent's "
        "video_a / video_b / video_c input slots.",
        "Total usable frames after applying trim parameters.",
        "Effective FPS (source FPS or force_rate override).",
        "Effective duration in seconds after applying trim parameters.",
        "JSON-encoded point selection data from the Point Selector. "
        "Connect to FFMPEGA Agent's mask_points input for guided masking.",
        "Upstream IMAGE pass-through (or empty tensor if not connected).",
        "Upstream AUDIO pass-through (or silence if not connected).",
    )
    FUNCTION = "load_path"
    CATEGORY = "FFMPEGA"
    DESCRIPTION = (
        "Zero-memory video input with inline preview. "
        "Select or upload a video file and connect the output to "
        "FFMPEGA Agent's video_a/b/c slots. Features video preview, "
        "metadata display, and VHS-style trim parameters. Loads ZERO "
        "frames into memory — perfect for long videos or combining "
        "many clips without running out of memory. Accepts optional "
        "upstream IMAGE, AUDIO, and video_path inputs for chaining "
        "from Save Video or VHS nodes."
    )

    @classmethod
    def IS_CHANGED(
        cls, video="", force_rate=0, skip_first_frames=0,
        frame_load_cap=0, select_every_nth=1, **kwargs,
    ) -> str:
        """Return hash so ComfyUI re-runs if the file or params change."""
        video_path = folder_paths.get_annotated_filepath(video)
        if video_path and os.path.isfile(video_path):
            m = hashlib.sha256()
            with open(video_path, "rb") as f:
                m.update(f.read(65536))
            m.update(str(os.path.getsize(video_path)).encode())
            m.update(f"{force_rate}:{skip_first_frames}:{frame_load_cap}"
                     f":{select_every_nth}".encode())
            m.update(str(kwargs.get("mask_points_data", "")).encode())
            return m.hexdigest()
        return ""

    @classmethod
    def VALIDATE_INPUTS(cls, video="", **kwargs) -> bool | str:
        if not video:
            return True  # Empty is OK on first load
        if not folder_paths.exists_annotated_filepath(video):
            return f"Invalid video file: {video}"
        return True

    def load_path(
        self,
        video: str = "",
        force_rate: float = 0,
        skip_first_frames: int = 0,
        frame_load_cap: int = 0,
        select_every_nth: int = 1,
        mask_points_data: str = "",
        images=None,
        audio=None,
        video_path=None,
        mask_points=None,
    ) -> dict:
        """Resolve path, probe metadata, compute effective values.

        Returns dict with outputs and UI data for video preview.

        If ``video_path`` is provided (upstream connection), it overrides
        the file-picker combo.  ``images`` and ``audio`` are passed
        through to the new output slots.
        """
        # --- Determine the actual video path ---
        upstream = False
        if video_path and isinstance(video_path, str) and video_path.strip():
            # Upstream connection overrides the file-picker
            resolved_path = video_path.strip()
            upstream = True
            logger.info("LoadVideoPath: using upstream video_path: %s", resolved_path)
        else:
            resolved_path = folder_paths.get_annotated_filepath(video)

        # Upstream mask_points overrides locally drawn points
        if mask_points and isinstance(mask_points, str) and mask_points.strip():
            mask_points_data = mask_points.strip()
            logger.info("LoadVideoPath: using upstream mask_points")

        if not resolved_path or not os.path.isfile(resolved_path):
            raise FileNotFoundError(
                f"Video file not found: {video_path if upstream else video}"
            )

        # Probe metadata
        meta = _probe_video(resolved_path)
        source_fps = meta["fps"]
        source_frames = meta["total_frames"]
        source_duration = meta["duration"]

        # Effective FPS
        effective_fps = force_rate if force_rate > 0 else source_fps

        # Compute effective frame count after trim parameters
        if force_rate > 0 and source_fps > 0:
            # Re-sample: total frames at new rate
            available_frames = int(math.ceil(source_duration * force_rate))
        else:
            available_frames = source_frames

        # Skip
        available_frames = max(0, available_frames - skip_first_frames)

        # Select every Nth
        if select_every_nth > 1:
            available_frames = max(0, available_frames // select_every_nth)

        # Cap
        if frame_load_cap > 0:
            available_frames = min(available_frames, frame_load_cap)

        # Effective duration
        if effective_fps > 0 and available_frames > 0:
            effective_duration = round(available_frames / effective_fps, 3)
        else:
            effective_duration = source_duration

        effective_fps = round(effective_fps, 3)

        # --- Pre-trim video when trim parameters are active ---
        # Creates a trimmed temp video using ffmpeg so all downstream
        # consumers (SAM3, FLUX Klein, etc.) operate on exactly the
        # frames the user requested.
        needs_trim = (
            skip_first_frames > 0
            or (frame_load_cap > 0 and frame_load_cap < source_frames)
            or select_every_nth > 1
            or (force_rate > 0 and force_rate != source_fps)
        )
        if needs_trim and available_frames > 0:
            temp_dir = folder_paths.get_temp_directory()
            os.makedirs(temp_dir, exist_ok=True)
            ext = os.path.splitext(resolved_path)[1] or ".mp4"
            # Hash input path + params for a unique, collision-free name
            _trim_key = f"{resolved_path}:{skip_first_frames}:{frame_load_cap}:{select_every_nth}:{force_rate}"
            _trim_hash = hashlib.sha256(_trim_key.encode()).hexdigest()[:12]
            trim_name = f"ffmpega_trim_{_trim_hash}{ext}"
            trim_path = os.path.join(temp_dir, trim_name)

            # Skip if already trimmed (cache hit)
            if os.path.isfile(trim_path):
                logger.info(
                    "LoadVideoPath: reusing cached trim: %s",
                    os.path.basename(trim_path),
                )
                resolved_path = trim_path
                needs_trim = False  # skip the ffmpeg block below

            if needs_trim:
                ffmpeg_bin = get_ffmpeg_bin()
                ffmpeg_cmd = [ffmpeg_bin, "-y"]

                # Skip frames: convert to time offset for fast seeking
                if skip_first_frames > 0 and source_fps > 0:
                    ss_time = skip_first_frames / source_fps
                    ffmpeg_cmd += ["-ss", f"{ss_time:.4f}"]

                ffmpeg_cmd += ["-i", resolved_path]

                # Force rate (re-sample FPS)
                if force_rate > 0:
                    ffmpeg_cmd += ["-r", str(force_rate)]

                # Select every Nth frame
                if select_every_nth > 1:
                    ffmpeg_cmd += ["-vf", f"select='not(mod(n\\,{select_every_nth}))',setpts=N/FRAME_RATE/TB"]

                # Frame cap
                if frame_load_cap > 0:
                    ffmpeg_cmd += ["-frames:v", str(frame_load_cap)]

                # Use stream copy when no filtering is needed, otherwise re-encode
                if select_every_nth <= 1 and force_rate <= 0:
                    ffmpeg_cmd += ["-c:v", "copy"]
                else:
                    ffmpeg_cmd += ["-c:v", "libx264", "-crf", "18",
                                   "-pix_fmt", "yuv420p"]

                ffmpeg_cmd += ["-c:a", "copy", trim_path]

                try:
                    result = subprocess.run(
                        ffmpeg_cmd,
                        capture_output=True, text=True, timeout=60,
                    )
                    if result.returncode == 0 and os.path.isfile(trim_path):
                        logger.info(
                            "LoadVideoPath: pre-trimmed %s → %s "
                            "(skip=%d, cap=%d, nth=%d, rate=%.1f)",
                            os.path.basename(resolved_path),
                            os.path.basename(trim_path),
                            skip_first_frames, frame_load_cap,
                            select_every_nth, force_rate,
                        )
                        resolved_path = trim_path
                    else:
                        logger.warning(
                            "LoadVideoPath: ffmpeg trim failed (rc=%d): %s",
                            result.returncode, result.stderr[:500],
                        )
                except Exception as e:
                    logger.warning("LoadVideoPath: trim failed: %s", e)

        logger.info(
            "LoadVideoPath: %s | %dx%d | %.1ffps | %d frames | %.1fs",
            resolved_path, meta["width"], meta["height"],
            effective_fps, available_frames, effective_duration,
        )

        # Prepare the video preview data for the frontend.
        # ComfyUI serves files from the input directory via /view endpoint.
        # We also pass metadata as a JSON string in an extra field.
        video_info = {
            "source_fps": source_fps,
            "source_frames": source_frames,
            "source_duration": source_duration,
            "source_width": meta["width"],
            "source_height": meta["height"],
            "effective_fps": effective_fps,
            "effective_frames": available_frames,
            "effective_duration": effective_duration,
        }

        # --- Pass-through upstream IMAGE / AUDIO ---
        images_out = images if images is not None else torch.zeros(
            1, 64, 64, 3, dtype=torch.float32,
        )
        audio_out = audio if audio is not None else {
            "waveform": torch.zeros(1, 1, 1), "sample_rate": 44100,
        }

        # --- Build UI data ---
        # For upstream paths, copy to temp so /view can serve it
        if upstream:
            import shutil as _shutil
            temp_dir = folder_paths.get_temp_directory()
            os.makedirs(temp_dir, exist_ok=True)
            ext = os.path.splitext(resolved_path)[1] or ".mp4"
            preview_name = f"ffmpega_lvp_upstream_{os.getpid()}{ext}"
            preview_path = os.path.join(temp_dir, preview_name)
            try:
                _shutil.copy2(resolved_path, preview_path)
            except Exception as e:
                logger.warning("LoadVideoPath: upstream preview copy failed: %s", e)
            ui_video = [{
                "filename": preview_name,
                "subfolder": "",
                "type": "temp",
            }]
        else:
            ui_video = [{
                "filename": video,
                "type": "input",
            }]

        return {
            "result": (resolved_path, available_frames, effective_fps,
                       effective_duration, mask_points_data or "",
                       images_out, audio_out),
            "ui": {
                "video": ui_video,
                "video_info": [video_info],
            },
        }
