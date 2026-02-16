"""Save Video node for ComfyUI.

Zero-memory video output node that takes a STRING video path, copies the
file to ComfyUI's output directory, and shows an inline video preview.

Replaces VHS Video Combine for FFMPEGA workflows — no tensor loading,
no re-encoding, no memory usage.  The video is already rendered by ffmpeg
(with audio already muxed in); this node just copies it and displays it.

Pipeline:  LoadVideoPath → FFMPEGA Agent → Save Video (FFMPEGA)
Memory:    ~0 MB          ~0 MB           ~0 MB
"""

import logging
import os
import shutil

import folder_paths

logger = logging.getLogger("FFMPEGA")


class SaveVideoNode:
    """Save / preview a video from its file path — zero memory cost."""

    def __init__(self):
        self.output_dir = folder_paths.get_output_directory()
        self.type = "output"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "video_path": ("STRING", {
                    "forceInput": True,
                    "tooltip": (
                        "Path to a video file (typically from the "
                        "FFMPEGA Agent's video_path output). The file "
                        "already contains audio if the source had it. "
                        "It will be copied as-is to ComfyUI's output "
                        "directory."
                    ),
                }),
                "filename_prefix": ("STRING", {
                    "default": "FFMPEGA",
                    "tooltip": (
                        "Prefix for the saved video filename. "
                        "Supports ComfyUI formatting like "
                        "%date:yyyy-MM-dd%."
                    ),
                }),
            },
            "optional": {
                "overwrite": ("BOOLEAN", {
                    "default": False,
                    "tooltip": (
                        "If true, overwrite the output file if it "
                        "already exists. Otherwise, auto-increment "
                        "the filename counter."
                    ),
                }),
            },
        }

    RETURN_TYPES = ()
    FUNCTION = "save_video"
    OUTPUT_NODE = True
    CATEGORY = "FFMPEGA"
    DESCRIPTION = (
        "Zero-memory video output with inline preview. "
        "Takes a video path (from FFMPEGA Agent or Load Video Path), "
        "copies the file to ComfyUI's output directory, and shows a "
        "preview. The video already contains audio — no re-encoding "
        "needed. Just a file copy."
    )

    def save_video(
        self,
        video_path: str = "",
        filename_prefix: str = "FFMPEGA",
        overwrite: bool = False,
    ) -> dict:
        """Copy video to output directory and return UI data for preview."""
        if not video_path or not os.path.isfile(video_path):
            raise FileNotFoundError(
                f"Video file not found: {video_path}"
            )

        # Determine output path
        ext = os.path.splitext(video_path)[1] or ".mp4"

        # Use ComfyUI's standard path resolution for output directory
        full_output_folder, filename, counter, subfolder, _ = (
            folder_paths.get_save_image_path(
                filename_prefix, self.output_dir
            )
        )
        os.makedirs(full_output_folder, exist_ok=True)

        if overwrite:
            output_filename = f"{filename}{ext}"
        else:
            output_filename = f"{filename}_{counter:05}{ext}"

        output_path = os.path.join(full_output_folder, output_filename)

        # Copy the video file (or just reference if already in output)
        src = os.path.abspath(video_path)
        dst = os.path.abspath(output_path)

        if src != dst:
            shutil.copy2(video_path, output_path)
            logger.info(
                "SaveVideo: copied %s → %s",
                video_path, output_path,
            )
        else:
            logger.info(
                "SaveVideo: file already in output: %s", output_path,
            )

        # Get file size for display
        file_size = os.path.getsize(output_path)
        if file_size >= 1_073_741_824:
            size_str = f"{file_size / 1_073_741_824:.1f} GB"
        elif file_size >= 1_048_576:
            size_str = f"{file_size / 1_048_576:.1f} MB"
        elif file_size >= 1024:
            size_str = f"{file_size / 1024:.1f} KB"
        else:
            size_str = f"{file_size} B"

        logger.info(
            "SaveVideo: %s (%s)", output_filename, size_str,
        )

        return {
            "ui": {
                "video": [{
                    "filename": output_filename,
                    "subfolder": subfolder,
                    "type": self.type,
                }],
                "file_size": [size_str],
            },
        }
