"""Frame Extract node for ComfyUI."""

import logging
import os
import re
import subprocess
from pathlib import Path

import numpy as np
import torch
from PIL import Image

import folder_paths
try:
    from ..core.sanitize import validate_video_path  # type: ignore[import-not-found]
    from ..core.bin_paths import get_ffmpeg_bin, get_ffprobe_bin
except ImportError:
    from core.sanitize import validate_video_path  # type: ignore
    from core.bin_paths import get_ffmpeg_bin, get_ffprobe_bin  # type: ignore

logger = logging.getLogger("ffmpega")


class FrameExtractNode:
    """Node for extracting frames from video."""

    @classmethod
    def INPUT_TYPES(cls):
        """Define input types for the node."""
        return {
            "required": {
                "video_path": ("STRING", {
                    "default": "",
                    "multiline": False,
                    "tooltip": "Absolute path to the video file to extract frames from.",
                }),
                "fps": ("FLOAT", {
                    "default": 1.0,
                    "min": 0.1,
                    "max": 60.0,
                    "step": 0.1,
                    "tooltip": "Frames per second to extract. 1.0 = one frame every second, higher values extract more frames.",
                }),
            },
            "optional": {
                "start_time": ("FLOAT", {
                    "default": 0.0,
                    "min": 0.0,
                    "max": 3600.0,
                    "tooltip": "Start time in seconds for frame extraction.",
                }),
                "duration": ("FLOAT", {
                    "default": 0,
                    "min": 0,
                    "max": 3600.0,
                    "tooltip": "Duration in seconds to extract frames from. 0 = full video from start_time.",
                }),
                "max_frames": ("INT", {
                    "default": 100,
                    "min": 1,
                    "max": 1000,
                    "tooltip": "Maximum number of frames to return. Limits output to prevent memory issues with long videos.",
                }),
                "images": ("IMAGE", {
                    "tooltip": (
                        "Optional upstream IMAGE input (e.g. from VHS "
                        "or Save Video). Accepted for wiring but "
                        "frames are always extracted from the video."
                    ),
                }),
                "audio": ("AUDIO", {
                    "tooltip": (
                        "Optional upstream AUDIO. If connected, this "
                        "audio is output instead of extracting from "
                        "the video."
                    ),
                }),
                "input_video_path": ("STRING", {
                    "forceInput": True,
                    "tooltip": (
                        "Optional upstream video path (e.g. from "
                        "Save Video or Load Video Path). Overrides "
                        "the video_path text field when connected."
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

    RETURN_TYPES = ("IMAGE", "AUDIO", "INT", "FLOAT", "FLOAT", "STRING", "STRING")
    RETURN_NAMES = ("frames", "audio", "frame_count", "fps", "duration", "video_path", "mask_points")
    OUTPUT_TOOLTIPS = (
        "Extracted video frames as a batched image tensor.",
        "Audio from the extracted segment in ComfyUI AUDIO format.",
        "Number of frames extracted.",
        "Source video FPS (native frame rate, not extraction rate).",
        "Actual duration of the extracted segment in seconds.",
        "Resolved absolute path to the video file.",
        "JSON-encoded point selection data from the Point Selector. "
        "Connect to FFMPEGA Agent's mask_points input for guided masking.",
    )
    FUNCTION = "extract_frames"
    OUTPUT_NODE = True
    CATEGORY = "FFMPEGA"
    DESCRIPTION = "Extract individual frames and audio from a video at a specified frame rate, time range, and frame limit."

    def __init__(self):
        """Initialize the frame extract node."""
        self._preview_generator = None

    @property
    def preview_generator(self):
        if self._preview_generator is None:
            from ..core.executor.preview import PreviewGenerator
            self._preview_generator = PreviewGenerator()
        return self._preview_generator

    def extract_frames(
        self,
        video_path: str,
        fps: float,
        start_time: float = 0.0,
        duration: float = 10.0,
        max_frames: int = 100,
        mask_points_data: str = "",
        images=None,
        audio=None,
        input_video_path=None,
        mask_points=None,
    ) -> dict:
        """Extract frames and audio from video.

        Args:
            video_path: Path to video file (text field).
            fps: Frames per second to extract.
            start_time: Start time in seconds.
            duration: Duration in seconds.
            max_frames: Maximum number of frames.
            images: Optional upstream IMAGE (accepted for wiring).
            audio: Optional upstream AUDIO (replaces extracted audio).
            input_video_path: Optional upstream video path (overrides
                video_path text field).

        Returns:
            Dict with 'ui' data and 'result' tuple for ComfyUI.
        """
        # --- Determine the actual video path ---
        if (
            input_video_path
            and isinstance(input_video_path, str)
            and input_video_path.strip()
        ):
            video_path = input_video_path.strip()
            logger.info(
                "FrameExtract: using upstream input_video_path: %s",
                video_path,
            )

        # Upstream mask_points overrides locally drawn points
        if mask_points and isinstance(mask_points, str) and mask_points.strip():
            mask_points_data = mask_points.strip()
            logger.info("FrameExtract: using upstream mask_points")

        # Resolve relative ComfyUI paths (e.g. "input/video.mp4")
        for prefix, getter in [
            ("input/", folder_paths.get_input_directory),
            ("output/", folder_paths.get_output_directory),
            ("temp/", folder_paths.get_temp_directory),
        ]:
            if video_path.startswith(prefix):
                relative = video_path[len(prefix):]
                candidate = os.path.join(getter(), relative)
                if os.path.isfile(candidate):
                    video_path = candidate
                break

        validate_video_path(video_path)

        # --- Get source video info ---
        source_fps, source_duration = self._probe_video(video_path)

        # Clamp duration to actual video length (0 = full video)
        remaining = max(0, source_duration - start_time)
        if duration <= 0 or duration > remaining:
            actual_duration = remaining
        else:
            actual_duration = duration

        # --- Extract frames ---
        output_dir = Path(folder_paths.get_temp_directory()) / "ffmpega_frames"
        output_dir.mkdir(exist_ok=True)

        frame_paths = self.preview_generator.extract_frames(
            input_path=video_path,
            output_dir=output_dir,
            fps=fps,
            start=start_time,
            duration=actual_duration,
        )

        # Limit frames
        frame_paths = frame_paths[:max_frames]

        # Load frames
        frames = []
        width, height = 0, 0
        for path in frame_paths:
            img = Image.open(path)
            if not width:
                width, height = img.size
            arr = np.array(img).astype(np.float32) / 255.0

            # Ensure RGB
            if len(arr.shape) == 2:
                arr = np.stack([arr, arr, arr], axis=-1)
            elif arr.shape[-1] == 4:
                arr = arr[:, :, :3]

            frames.append(arr)

        # Stack into batch tensor
        if frames:
            frames_array = np.stack(frames, axis=0)
            frames_tensor = torch.from_numpy(frames_array)
        else:
            frames_tensor = torch.zeros((1, 480, 640, 3), dtype=torch.float32)
            width, height = 640, 480

        frame_count = len(frames)

        # --- Audio: use upstream if connected, otherwise extract ---
        if audio is not None:
            audio_out = audio
            logger.info("FrameExtract: using upstream audio")
        else:
            audio_out = self._extract_audio(
                video_path, start_time, actual_duration,
            )

        logger.info(
            "FrameExtract: %d frames @ %.1f fps (%dx%d) from %.1f–%.1fs "
            "(source: %.1f fps, %.1fs total)",
            frame_count, fps, width, height,
            start_time, start_time + actual_duration,
            source_fps, source_duration,
        )

        # --- Create preview clip ---
        preview_data = self._create_preview_clip(
            video_path, start_time, actual_duration,
        )

        return {
            "ui": {
                "frame_info": [{
                    "count": frame_count,
                    "fps": round(fps, 2),
                    "source_fps": round(source_fps, 2),
                    "start": round(start_time, 2),
                    "end": round(start_time + actual_duration, 2),
                    "duration": round(actual_duration, 2),
                    "width": width,
                    "height": height,
                    "video_path": video_path,
                }],
                **preview_data,
            },
            "result": (
                frames_tensor,
                audio_out,
                frame_count,
                source_fps,
                round(actual_duration, 3),
                video_path,
                mask_points_data or "",
            ),
        }

    def _probe_video(self, video_path: str) -> tuple[float, float]:
        """Probe video for FPS and duration.

        Returns:
            (fps, duration_seconds) tuple.
        """
        ffprobe_bin = get_ffprobe_bin()
        if not ffprobe_bin:
            return 30.0, 0.0

        try:
            result = subprocess.run(
                [
                    ffprobe_bin, "-v", "error",
                    "-select_streams", "v:0",
                    "-show_entries", "stream=r_frame_rate",
                    "-show_entries", "format=duration",
                    "-of", "json",
                    video_path,
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            import json
            data = json.loads(result.stdout)

            # FPS
            stream = data.get("streams", [{}])[0]
            fps_str = stream.get("r_frame_rate", "30/1")
            if "/" in fps_str:
                num, den = fps_str.split("/")
                video_fps = float(num) / float(den) if float(den) != 0 else 30.0
            else:
                video_fps = float(fps_str) if fps_str else 30.0

            # Duration
            fmt = data.get("format", {})
            video_duration = float(fmt.get("duration", 0))

            return video_fps, video_duration

        except Exception as e:
            logger.warning("FrameExtract: probe failed: %s", e)
            return 30.0, 0.0

    def _extract_audio(
        self,
        video_path: str,
        start_time: float,
        duration: float,
    ) -> dict:
        """Extract audio from the same segment as the frames.

        Returns dict with 'waveform' (Tensor [1, channels, samples])
        and 'sample_rate' (int). Returns silence if no audio stream.
        """
        silence = {"waveform": torch.zeros(1, 1, 1), "sample_rate": 44100}

        ffmpeg_bin = get_ffmpeg_bin()
        ffprobe_bin = get_ffprobe_bin()
        if not ffmpeg_bin or not ffprobe_bin:
            return silence

        # Check for audio stream
        try:
            probe = subprocess.run(
                [
                    ffprobe_bin, "-v", "error",
                    "-select_streams", "a",
                    "-show_entries", "stream=codec_type",
                    "-of", "csv=p=0",
                    video_path,
                ],
                capture_output=True, check=True, timeout=10,
            )
            if not probe.stdout.decode("utf-8", "backslashreplace").strip():
                return silence
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            return silence

        # Extract raw PCM for the specified segment
        try:
            cmd = [
                ffmpeg_bin,
                "-ss", str(start_time),
                "-i", video_path,
                "-t", str(duration),
                "-vn",
                "-f", "f32le",
                "-",
            ]
            res = subprocess.run(
                cmd,
                capture_output=True, check=True, timeout=60,
            )

            # Ensure buffer size is a multiple of element size (4 bytes for float32)
            stdout_bytes = bytearray(res.stdout)
            rem = len(stdout_bytes) % 4
            if rem != 0:
                stdout_bytes = stdout_bytes[:-rem]

            audio = torch.frombuffer(stdout_bytes, dtype=torch.float32)

            # Parse sample rate and channel count from stderr
            match = re.search(
                r", (\d+) Hz, (\w+), ",
                res.stderr.decode("utf-8", "backslashreplace"),
            )
            if match:
                ar = int(match.group(1))
                ac = {"mono": 1, "stereo": 2}.get(match.group(2), 2)
            else:
                ar, ac = 44100, 2

            # Truncate if samples aren't divisible by channel count
            n_samples = audio.numel()
            usable = n_samples - (n_samples % ac)
            if usable == 0:
                return silence
            audio = audio[:usable].reshape((-1, ac)).transpose(0, 1).unsqueeze(0)
            return {"waveform": audio, "sample_rate": ar}

        except Exception as e:
            logger.warning("FrameExtract: audio extraction failed: %s", e)
            return silence

    def _create_preview_clip(
        self,
        video_path: str,
        start_time: float,
        duration: float,
    ) -> dict:
        """Create a temporary preview clip for the UI.

        Copies the relevant segment to ComfyUI's temp directory so it
        can be served via the standard /view endpoint.

        Returns:
            Dict with 'video' key for the UI, or empty dict on failure.
        """
        try:
            temp_dir = folder_paths.get_temp_directory()
            os.makedirs(temp_dir, exist_ok=True)

            preview_name = f"ffmpega_extract_preview_{os.getpid()}.mp4"
            preview_path = os.path.join(temp_dir, preview_name)

            cmd = [
                "ffmpeg", "-y",
                "-ss", str(start_time),
                "-i", video_path,
                "-t", str(duration),
                "-c:v", "libx264",
                "-preset", "ultrafast",
                "-crf", "28",
                "-an",
                "-pix_fmt", "yuv420p",
                preview_path,
            ]

            subprocess.run(
                cmd,
                capture_output=True,
                timeout=30,
            )

            if os.path.isfile(preview_path):
                return {
                    "video": [{
                        "filename": preview_name,
                        "subfolder": "",
                        "type": "temp",
                    }],
                }

        except Exception as e:
            logger.warning("FrameExtract: preview clip creation failed: %s", e)

        return {}
