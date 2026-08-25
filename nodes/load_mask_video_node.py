"""Load Mask Video node for ComfyUI.

Loads a pre-generated mask video (B&W) and outputs it as a MASK tensor.
Avoids re-running SAM3 every execution by reusing saved mask videos.

Memory cost: minimal — decodes frames on demand via OpenCV.
"""

import hashlib
import logging
import os

import torch

import folder_paths

logger = logging.getLogger("FFMPEGA")


class LoadMaskVideoNode:
    """Load a pre-made mask video and output as a MASK tensor."""

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
            files = [""]
        return {
            "required": {
                "mask_video": (sorted(files), {
                    "tooltip": (
                        "Select a mask video file (B&W, white = masked area). "
                        "The video is decoded frame-by-frame into a MASK tensor."
                    ),
                }),
            },
        }

    RETURN_TYPES = ("MASK",)
    RETURN_NAMES = ("mask",)
    OUTPUT_TOOLTIPS = (
        "Multi-frame mask tensor (N, H, W) decoded from the mask video. "
        "White pixels = masked area. Connect to MatAnyone2, compositing, etc.",
    )
    FUNCTION = "load_mask"
    CATEGORY = "FFMPEGA"
    OUTPUT_NODE = True
    DESCRIPTION = (
        "Load a pre-generated mask video (B&W) and output as a MASK tensor. "
        "Use this to reuse SAM3 or manually created mask videos without "
        "regenerating them every run."
    )

    @classmethod
    def IS_CHANGED(cls, mask_video="", **kwargs) -> str:
        video_path = folder_paths.get_annotated_filepath(mask_video)
        if video_path and os.path.isfile(video_path):
            m = hashlib.sha256()
            with open(video_path, "rb") as f:
                m.update(f.read(65536))
            m.update(str(os.path.getsize(video_path)).encode())
            return m.hexdigest()
        return ""

    @classmethod
    def VALIDATE_INPUTS(cls, mask_video="", **kwargs) -> bool | str:
        if not mask_video:
            return True
        if not folder_paths.exists_annotated_filepath(mask_video):
            return f"Invalid mask video file: {mask_video}"
        return True

    def load_mask(self, mask_video: str = "") -> dict:
        """Decode mask video frames into a MASK tensor."""
        import cv2
        import numpy as np

        video_path = folder_paths.get_annotated_filepath(mask_video)
        if not video_path or not os.path.isfile(video_path):
            raise FileNotFoundError(f"Mask video not found: {mask_video}")

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise RuntimeError(f"Cannot open mask video: {video_path}")

        frames = []
        try:
            while True:
                ret, frame = cap.read()
                if not ret:
                    break
                if frame.ndim == 3:
                    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                else:
                    gray = frame
                frames.append(
                    torch.from_numpy(gray.astype(np.float32) / 255.0)
                )
        finally:
            cap.release()

        if not frames:
            raise RuntimeError(f"No frames decoded from mask video: {video_path}")

        mask_out = torch.stack(frames, dim=0)  # (N, H, W)
        logger.info(
            "LoadMaskVideo: %s | %d frames | %dx%d",
            os.path.basename(video_path),
            mask_out.shape[0], mask_out.shape[2], mask_out.shape[1],
        )

        return {
            "result": (mask_out,),
            "ui": {
                "video": [{
                    "filename": mask_video,
                    "type": "input",
                }],
            },
        }
