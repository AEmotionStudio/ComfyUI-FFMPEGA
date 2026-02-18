"""Save Video node for ComfyUI.

Zero-memory video output node that takes a STRING video path, copies the
file to ComfyUI's output directory, and shows an inline video preview.

Replaces VHS Video Combine for FFMPEGA workflows — no tensor loading,
no re-encoding, no memory usage.  The video is already rendered by ffmpeg
(with audio already muxed in); this node just copies it and displays it.

Pipeline:  LoadVideoPath → FFMPEGA Agent → Save Video (FFMPEGA)
Memory:    ~0 MB          ~0 MB           ~0 MB
"""

import json
import logging
import os
import shutil
import subprocess
import tempfile

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
            "hidden": {
                "prompt": "PROMPT",
                "extra_pnginfo": "EXTRA_PNGINFO",
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
        "needed. Just a file copy. A workflow PNG thumbnail is saved "
        "alongside the video for drag-and-drop workflow loading."
    )

    def save_video(
        self,
        video_path: str = "",
        filename_prefix: str = "FFMPEGA",
        overwrite: bool = False,
        prompt=None,
        extra_pnginfo=None,
    ) -> dict:
        """Copy video to output directory and return UI data for preview."""
        # Guard against empty / non-string prefix — ComfyUI may send ""
        # if the user clears the field, or occasionally serialize a
        # boolean widget value as the string "False"/"True".
        if (
            not filename_prefix
            or not isinstance(filename_prefix, str)
            or not filename_prefix.strip()
            or filename_prefix.strip().lower() in ("false", "true")
        ):
            filename_prefix = "FFMPEGA"

        if not video_path or not os.path.isfile(video_path):
            raise FileNotFoundError(
                f"Video file not found: {video_path}"
            )

        # Determine output path
        ext = os.path.splitext(video_path)[1] or ".mp4"

        # Use ComfyUI's standard path resolution for output directory
        full_output_folder, filename, _counter, subfolder, _ = (
            folder_paths.get_save_image_path(
                filename_prefix, self.output_dir
            )
        )
        os.makedirs(full_output_folder, exist_ok=True)

        if overwrite:
            output_filename = f"{filename}{ext}"
        else:
            # Scan for existing files to find the next available counter.
            # ComfyUI's counter only tracks images, so we must compute
            # the correct next number for video files ourselves.
            import glob
            pattern = os.path.join(full_output_folder, f"{filename}_*")
            existing = glob.glob(pattern)
            max_counter = 0
            for path in existing:
                basename = os.path.splitext(os.path.basename(path))[0]
                # Extract the trailing number after the last underscore
                parts = basename.rsplit("_", 1)
                if len(parts) == 2 and parts[1].isdigit():
                    max_counter = max(max_counter, int(parts[1]))
            counter = max_counter + 1
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

        # --- Generate workflow PNG thumbnail ---
        png_filename = self._save_workflow_png(
            output_path, full_output_folder, output_filename,
            prompt, extra_pnginfo,
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

    def _save_workflow_png(
        self,
        video_path: str,
        output_folder: str,
        video_filename: str,
        prompt,
        extra_pnginfo,
    ) -> str | None:
        """Extract a thumbnail frame and embed workflow metadata.

        Returns the PNG filename on success, None on failure.
        """
        if prompt is None and extra_pnginfo is None:
            return None

        try:
            from PIL import Image
            from PIL.PngImagePlugin import PngInfo
        except ImportError:
            logger.warning(
                "SaveVideo: PIL not available — skipping workflow PNG"
            )
            return None

        # Extract a frame at 1 second (past any fade-in)
        tmp_frame = None
        try:
            tmp_frame = tempfile.NamedTemporaryFile(
                suffix=".png", delete=False,
            )
            tmp_frame.close()

            result = subprocess.run(
                [
                    "ffmpeg", "-y",
                    "-i", video_path,
                    "-ss", "1",
                    "-frames:v", "1",
                    "-q:v", "2",
                    tmp_frame.name,
                ],
                capture_output=True,
                timeout=15,
            )

            if result.returncode != 0 or not os.path.isfile(tmp_frame.name):
                logger.warning(
                    "SaveVideo: failed to extract thumbnail frame"
                )
                return None

            # Open the extracted frame
            img = Image.open(tmp_frame.name)
            img = img.convert("RGB")

            # Build PNG metadata with workflow
            metadata = PngInfo()
            if prompt is not None:
                metadata.add_text("prompt", json.dumps(prompt))
            if extra_pnginfo is not None:
                for key in extra_pnginfo:
                    metadata.add_text(key, json.dumps(extra_pnginfo[key]))

            # Save alongside the video with the same base name
            video_base = os.path.splitext(video_filename)[0]
            png_filename = f"{video_base}.png"
            png_path = os.path.join(output_folder, png_filename)

            img.save(png_path, pnginfo=metadata, compress_level=4)
            logger.info(
                "SaveVideo: workflow PNG saved → %s", png_filename,
            )
            return png_filename

        except Exception as e:
            logger.warning(
                "SaveVideo: workflow PNG generation failed: %s", e,
            )
            return None
        finally:
            if tmp_frame and os.path.isfile(tmp_frame.name):
                try:
                    os.unlink(tmp_frame.name)
                except OSError:
                    pass
