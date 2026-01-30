"""Video Preview node for ComfyUI."""

import tempfile
from pathlib import Path
from typing import Optional

import numpy as np
import torch
from PIL import Image

import folder_paths


class VideoPreviewNode:
    """Node for generating video previews and thumbnails."""

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
                }),
            },
        }

    RETURN_TYPES = ("STRING", "IMAGE")
    RETURN_NAMES = ("preview_path", "thumbnail")
    FUNCTION = "generate_preview"
    CATEGORY = "FFMPEGA"

    def __init__(self):
        """Initialize the preview node."""
        self._preview_generator = None
        self._analyzer = None

    @property
    def preview_generator(self):
        if self._preview_generator is None:
            from ..core.executor.preview import PreviewGenerator
            self._preview_generator = PreviewGenerator()
        return self._preview_generator

    @property
    def analyzer(self):
        if self._analyzer is None:
            from ..core.video.analyzer import VideoAnalyzer
            self._analyzer = VideoAnalyzer()
        return self._analyzer

    def generate_preview(
        self,
        video_path: str,
        preview_resolution: str,
        frame_skip: int,
        thumbnail_time: float = 0.0,
        max_duration: float = 0.0,
    ) -> tuple[str, torch.Tensor]:
        """Generate a preview video and thumbnail.

        Args:
            video_path: Path to input video.
            preview_resolution: Target preview resolution.
            frame_skip: Process every Nth frame.
            thumbnail_time: Time in seconds for thumbnail.
            max_duration: Maximum preview duration (0 = full).

        Returns:
            Tuple of (preview_video_path, thumbnail_tensor).
        """
        # Validate input
        if not video_path or not Path(video_path).exists():
            raise ValueError(f"Video file not found: {video_path}")

        # Generate preview video
        output_dir = Path(folder_paths.get_temp_directory()) / "ffmpega_previews"
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

        # Load thumbnail as tensor for ComfyUI
        img = Image.open(thumbnail_path)
        img_array = np.array(img).astype(np.float32) / 255.0

        # Ensure correct shape for ComfyUI (batch, height, width, channels)
        if len(img_array.shape) == 2:
            # Grayscale, add channel dimension
            img_array = np.expand_dims(img_array, axis=-1)
            img_array = np.repeat(img_array, 3, axis=-1)
        elif img_array.shape[-1] == 4:
            # RGBA, convert to RGB
            img_array = img_array[:, :, :3]

        # Add batch dimension and convert to tensor
        thumbnail_tensor = torch.from_numpy(img_array).unsqueeze(0)

        return (str(preview_path), thumbnail_tensor)


class VideoInfoNode:
    """Node for displaying video information."""

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

    RETURN_TYPES = ("STRING", "INT", "INT", "FLOAT", "FLOAT")
    RETURN_NAMES = ("info_text", "width", "height", "duration", "fps")
    FUNCTION = "get_info"
    CATEGORY = "FFMPEGA"

    def __init__(self):
        """Initialize the info node."""
        self._analyzer = None

    @property
    def analyzer(self):
        if self._analyzer is None:
            from ..core.video.analyzer import VideoAnalyzer
            self._analyzer = VideoAnalyzer()
        return self._analyzer

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
        fps = metadata.primary_video.frame_rate if metadata.primary_video and metadata.primary_video.frame_rate else 0.0

        return (
            metadata.to_analysis_string(),
            width,
            height,
            metadata.duration,
            fps,
        )


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

    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("frames",)
    FUNCTION = "extract_frames"
    CATEGORY = "FFMPEGA"

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
    ) -> tuple[torch.Tensor]:
        """Extract frames from video.

        Args:
            video_path: Path to video file.
            fps: Frames per second to extract.
            start_time: Start time in seconds.
            duration: Duration in seconds.
            max_frames: Maximum number of frames.

        Returns:
            Tuple containing frames as tensor.
        """
        if not video_path or not Path(video_path).exists():
            raise ValueError(f"Video file not found: {video_path}")

        output_dir = Path(folder_paths.get_temp_directory()) / "ffmpega_frames"
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

        # Stack into batch tensor
        if frames:
            frames_array = np.stack(frames, axis=0)
            frames_tensor = torch.from_numpy(frames_array)
        else:
            # Return empty tensor with correct shape
            frames_tensor = torch.zeros((1, 480, 640, 3), dtype=torch.float32)

        return (frames_tensor,)
