"""Video Preview node for ComfyUI."""

import tempfile
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image

from ..core.executor.preview import PreviewGenerator
from ..core.video.analyzer import VideoAnalyzer


class VideoPreviewNode:
    """Node for generating video previews and thumbnails."""

    CATEGORY = "FFMPEGA/Utils"
    FUNCTION = "generate_preview"
    RETURN_TYPES = ("VIDEO", "IMAGE")
    RETURN_NAMES = ("preview", "thumbnail")

    RESOLUTIONS = ["360p", "480p", "720p"]

    @classmethod
    def INPUT_TYPES(cls):
        """Define input types for the node."""
        return {
            "required": {
                "video_path": ("STRING", {
                    "default": "",
                    "multiline": False,
                    "placeholder": "Path to input video file",
                }),
                "preview_resolution": (cls.RESOLUTIONS, {
                    "default": "480p",
                }),
                "frame_skip": ("INT", {
                    "default": 2,
                    "min": 1,
                    "max": 10,
                    "step": 1,
                }),
            },
            "optional": {
                "thumbnail_time": ("FLOAT", {
                    "default": 0.0,
                    "min": 0.0,
                    "max": 3600.0,
                    "step": 0.1,
                }),
                "max_duration": ("FLOAT", {
                    "default": 0.0,
                    "min": 0.0,
                    "max": 300.0,
                    "step": 1.0,
                    "placeholder": "0 = full video",
                }),
            },
        }

    def __init__(self):
        """Initialize the preview node."""
        self.preview_generator = PreviewGenerator()
        self.analyzer = VideoAnalyzer()

    def generate_preview(
        self,
        video_path: str,
        preview_resolution: str,
        frame_skip: int,
        thumbnail_time: float = 0.0,
        max_duration: float = 0.0,
    ) -> tuple[str, np.ndarray]:
        """Generate a preview video and thumbnail.

        Args:
            video_path: Path to input video.
            preview_resolution: Target preview resolution.
            frame_skip: Process every Nth frame.
            thumbnail_time: Time in seconds for thumbnail.
            max_duration: Maximum preview duration (0 = full).

        Returns:
            Tuple of (preview_video_path, thumbnail_image).
        """
        # Validate input
        if not video_path or not Path(video_path).exists():
            raise ValueError(f"Video file not found: {video_path}")

        # Generate preview video
        output_dir = Path(tempfile.gettempdir()) / "ffmpega_previews"
        output_dir.mkdir(exist_ok=True)

        preview_path = output_dir / f"{Path(video_path).stem}_preview.mp4"

        duration = max_duration if max_duration > 0 else None

        self.preview_generator.generate_preview(
            input_path=video_path,
            output_path=preview_path,
            resolution=preview_resolution,
            frame_skip=frame_skip,
            duration=duration,
        )

        # Generate thumbnail
        thumbnail_path = output_dir / f"{Path(video_path).stem}_thumb.png"

        self.preview_generator.generate_thumbnail(
            input_path=video_path,
            output_path=thumbnail_path,
            timestamp=thumbnail_time,
            width=640,
        )

        # Load thumbnail as numpy array for ComfyUI
        img = Image.open(thumbnail_path)
        thumbnail_array = np.array(img).astype(np.float32) / 255.0

        # Ensure correct shape for ComfyUI (batch, height, width, channels)
        if len(thumbnail_array.shape) == 2:
            # Grayscale, add channel dimension
            thumbnail_array = np.expand_dims(thumbnail_array, axis=-1)
            thumbnail_array = np.repeat(thumbnail_array, 3, axis=-1)
        elif thumbnail_array.shape[-1] == 4:
            # RGBA, convert to RGB
            thumbnail_array = thumbnail_array[:, :, :3]

        # Add batch dimension
        thumbnail_array = np.expand_dims(thumbnail_array, axis=0)

        return (str(preview_path), thumbnail_array)


class VideoInfoNode:
    """Node for displaying video information."""

    CATEGORY = "FFMPEGA/Utils"
    FUNCTION = "get_info"
    RETURN_TYPES = ("STRING", "INT", "INT", "FLOAT", "FLOAT")
    RETURN_NAMES = ("info_text", "width", "height", "duration", "fps")

    @classmethod
    def INPUT_TYPES(cls):
        """Define input types for the node."""
        return {
            "required": {
                "video_path": ("STRING", {
                    "default": "",
                    "multiline": False,
                    "placeholder": "Path to video file",
                }),
            },
        }

    def __init__(self):
        """Initialize the info node."""
        self.analyzer = VideoAnalyzer()

    def get_info(self, video_path: str) -> tuple[str, int, int, float, float]:
        """Get video information.

        Args:
            video_path: Path to video file.

        Returns:
            Tuple of (info_text, width, height, duration, fps).
        """
        if not video_path or not Path(video_path).exists():
            raise ValueError(f"Video file not found: {video_path}")

        metadata = self.analyzer.analyze(video_path)

        width = metadata.primary_video.width if metadata.primary_video else 0
        height = metadata.primary_video.height if metadata.primary_video else 0
        fps = metadata.primary_video.frame_rate if metadata.primary_video else 0.0

        return (
            metadata.to_analysis_string(),
            width,
            height,
            metadata.duration,
            fps,
        )


class FrameExtractNode:
    """Node for extracting frames from video."""

    CATEGORY = "FFMPEGA/Utils"
    FUNCTION = "extract_frames"
    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("frames",)

    @classmethod
    def INPUT_TYPES(cls):
        """Define input types for the node."""
        return {
            "required": {
                "video_path": ("STRING", {
                    "default": "",
                    "multiline": False,
                }),
                "fps": ("FLOAT", {
                    "default": 1.0,
                    "min": 0.1,
                    "max": 60.0,
                    "step": 0.1,
                }),
            },
            "optional": {
                "start_time": ("FLOAT", {
                    "default": 0.0,
                    "min": 0.0,
                    "max": 3600.0,
                }),
                "duration": ("FLOAT", {
                    "default": 10.0,
                    "min": 0.1,
                    "max": 300.0,
                }),
                "max_frames": ("INT", {
                    "default": 100,
                    "min": 1,
                    "max": 1000,
                }),
            },
        }

    def __init__(self):
        """Initialize the frame extract node."""
        self.preview_generator = PreviewGenerator()

    def extract_frames(
        self,
        video_path: str,
        fps: float,
        start_time: float = 0.0,
        duration: float = 10.0,
        max_frames: int = 100,
    ) -> tuple[np.ndarray]:
        """Extract frames from video.

        Args:
            video_path: Path to video file.
            fps: Frames per second to extract.
            start_time: Start time in seconds.
            duration: Duration in seconds.
            max_frames: Maximum number of frames.

        Returns:
            Tuple containing frames as numpy array.
        """
        if not video_path or not Path(video_path).exists():
            raise ValueError(f"Video file not found: {video_path}")

        output_dir = Path(tempfile.gettempdir()) / "ffmpega_frames"
        output_dir.mkdir(exist_ok=True)

        frame_paths = self.preview_generator.extract_frames(
            input_path=video_path,
            output_dir=output_dir,
            fps=fps,
            start=start_time,
            duration=duration,
        )

        # Limit frames
        frame_paths = frame_paths[:max_frames]

        # Load frames
        frames = []
        for path in frame_paths:
            img = Image.open(path)
            arr = np.array(img).astype(np.float32) / 255.0

            # Ensure RGB
            if len(arr.shape) == 2:
                arr = np.stack([arr, arr, arr], axis=-1)
            elif arr.shape[-1] == 4:
                arr = arr[:, :, :3]

            frames.append(arr)

        # Stack into batch
        if frames:
            frames_array = np.stack(frames, axis=0)
        else:
            # Return empty array with correct shape
            frames_array = np.zeros((1, 480, 640, 3), dtype=np.float32)

        return (frames_array,)
