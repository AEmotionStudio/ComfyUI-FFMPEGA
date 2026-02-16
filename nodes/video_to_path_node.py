"""VideoToPath node for ComfyUI.

Converts an IMAGE tensor (video frames) into a temp video file and outputs
the file path as a STRING.  This is the memory-efficient bridge between
Load Video nodes (which output IMAGE tensors) and FFMPEGA's video_a/b/c
connection slots.

By inserting this node between a Load Video and the FFMPEGA Agent,
ComfyUI can free the ~21 GB IMAGE tensor after this node finishes,
before the FFMPEGA Agent even starts running.
"""

import gc
import logging
import tempfile

import torch

logger = logging.getLogger("FFMPEGA")


class VideoToPathNode:
    """Convert IMAGE tensor to a temp video file and output the path."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "images": ("IMAGE", {
                    "tooltip": "Video frames from a Load Video node or any node that outputs IMAGE tensors.",
                }),
            },
            "optional": {
                "fps": ("INT", {
                    "default": 24,
                    "min": 1,
                    "max": 120,
                    "step": 1,
                    "tooltip": "Frames per second for the output video. Match this to your source video's FPS.",
                }),
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("video_path",)
    OUTPUT_TOOLTIPS = ("File path to the temp video. Connect to FFMPEGA Agent's video_a/b/c slots.",)
    FUNCTION = "convert"
    CATEGORY = "FFMPEGA"
    DESCRIPTION = (
        "Converts video frames (IMAGE tensor) into a temp video file and "
        "outputs the file path. Use this between a Load Video node and "
        "FFMPEGA Agent's video_a/b/c inputs to avoid out-of-memory errors "
        "when working with multiple or long videos."
    )

    def convert(
        self,
        images: torch.Tensor,
        fps: int = 24,
    ) -> tuple[str]:
        """Convert IMAGE tensor to video file.

        Args:
            images: Video frames as IMAGE tensor (N, H, W, 3) float32.
            fps: Frames per second.

        Returns:
            Tuple containing the file path to the temp video.
        """
        from ..core.media_converter import MediaConverter

        converter = MediaConverter()
        video_path = converter.images_to_video(images, fps=fps)

        # Release our reference to the tensor immediately.
        # ComfyUI may still cache it, but at least our frame is clean.
        del images
        gc.collect()
        try:
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass

        logger.info("VideoToPath: saved %s", video_path)
        return (video_path,)
