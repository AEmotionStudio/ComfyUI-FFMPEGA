"""Frame Extract node for ComfyUI."""

from pathlib import Path

import numpy as np
import torch
from PIL import Image

import folder_paths
from ..core.sanitize import validate_video_path  # type: ignore[import-not-found]


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
                    "default": 10.0,
                    "min": 0.1,
                    "max": 300.0,
                    "tooltip": "Duration in seconds to extract frames from, starting at start_time.",
                }),
                "max_frames": ("INT", {
                    "default": 100,
                    "min": 1,
                    "max": 1000,
                    "tooltip": "Maximum number of frames to return. Limits output to prevent memory issues with long videos.",
                }),
            },
        }

    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("frames",)
    OUTPUT_TOOLTIPS = ("Extracted video frames as a batched image tensor.",)
    FUNCTION = "extract_frames"
    CATEGORY = "FFMPEGA"
    DESCRIPTION = "Extract individual frames from a video at a specified frame rate, time range, and frame limit."

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
        validate_video_path(video_path)

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
