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
import re
import shutil
import subprocess
import tempfile

import numpy as np
import torch

import folder_paths
from ..core.bin_paths import get_ffmpeg_bin, get_ffprobe_bin

logger = logging.getLogger("FFMPEGA")

MAX_PREVIEW_FRAMES = 64  # cap to avoid memory blowout


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
                "save_output": ("BOOLEAN", {
                    "default": True,
                    "label_on": "Save to Output",
                    "label_off": "Preview Only",
                    "tooltip": (
                        "When On, copies the video to ComfyUI's output "
                        "directory. When Off, shows the inline preview "
                        "and outputs frames/audio/path without saving "
                        "a copy — useful for previewing before committing."
                    ),
                }),
                "overwrite": ("BOOLEAN", {
                    "default": False,
                    "tooltip": (
                        "If true, overwrite the output file if it "
                        "already exists. Otherwise, auto-increment "
                        "the filename counter."
                    ),
                }),
                "mask_points": ("STRING", {
                    "forceInput": True,
                    "tooltip": (
                        "Optional upstream mask_points pass-through. "
                        "Forwarded as-is to the mask_points output "
                        "for downstream nodes."
                    ),
                }),
            },
            "hidden": {
                "prompt": "PROMPT",
                "extra_pnginfo": "EXTRA_PNGINFO",
            },
        }

    RETURN_TYPES = ("IMAGE", "AUDIO", "STRING", "STRING")
    RETURN_NAMES = ("images", "audio", "video_path", "mask_points")
    FUNCTION = "save_video"
    OUTPUT_NODE = True
    CATEGORY = "FFMPEGA"
    DESCRIPTION = (
        "Zero-memory video output with inline preview. "
        "Takes a video path (from FFMPEGA Agent or Load Video Path), "
        "copies the file to ComfyUI's output directory, and shows a "
        "preview. Also outputs IMAGE frames and the saved video_path "
        "for chaining with downstream nodes. A workflow PNG thumbnail "
        "is saved alongside the video for drag-and-drop workflow loading."
    )

    def save_video(
        self,
        video_path: str = "",
        filename_prefix: str = "FFMPEGA",
        save_output: bool = True,
        overwrite: bool = False,
        mask_points: str = "",
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
            # Return empty results when no video is available (e.g. mask
            # overlay path is empty because SAM3 failed or was not used).
            empty_tensor = torch.zeros(1, 64, 64, 3, dtype=torch.float32)
            silent_audio = {"waveform": torch.zeros(1, 1, 1), "sample_rate": 44100}
            return {
                "ui": {"video": [], "file_size": ["0 B"]},
                "result": (empty_tensor, silent_audio, "", mask_points or ""),
            }

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

        # --- Copy to output directory (if save_output is on) ---
        if save_output:
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

            # --- Generate workflow PNG thumbnail ---
            png_filename = self._save_workflow_png(
                output_path, full_output_folder, output_filename,
                prompt, extra_pnginfo,
            )
        else:
            # Preview-only mode: copy to temp directory so /view can serve it
            temp_dir = folder_paths.get_temp_directory()
            os.makedirs(temp_dir, exist_ok=True)
            preview_name = f"ffmpega_preview_{os.getpid()}{ext}"
            preview_path = os.path.join(temp_dir, preview_name)
            try:
                shutil.copy2(video_path, preview_path)
            except Exception as e:
                logger.warning("SaveVideo: preview copy failed: %s", e)
            output_path = preview_path if os.path.isfile(preview_path) else video_path
            logger.info(
                "SaveVideo: preview-only mode — copied to temp for preview",
            )

        # --- Get file size for display ---
        file_size = os.path.getsize(video_path)  # always show source size
        if file_size >= 1_073_741_824:
            size_str = f"{file_size / 1_073_741_824:.1f} GB"
        elif file_size >= 1_048_576:
            size_str = f"{file_size / 1_048_576:.1f} MB"
        elif file_size >= 1024:
            size_str = f"{file_size / 1024:.1f} KB"
        else:
            size_str = f"{file_size} B"

        logger.info(
            "SaveVideo: %s (%s)", os.path.basename(output_path), size_str,
        )

        # --- Extract frames as IMAGE tensor ---
        images_tensor = self._extract_frames(output_path)

        # --- Extract audio ---
        audio_out = self._extract_audio(output_path)

        # Build UI data
        if save_output:
            video_ui = [{
                "filename": output_filename,
                "subfolder": subfolder,
                "type": self.type,
            }]
        else:
            # For preview-only, reference the temp copy
            video_ui = [{
                "filename": preview_name,
                "subfolder": "",
                "type": "temp",
            }]

        return {
            "ui": {
                "video": video_ui,
                "file_size": [size_str],
            },
            "result": (images_tensor, audio_out, output_path, mask_points or ""),
        }

    def _extract_frames(self, video_path: str) -> torch.Tensor:
        """Extract frames from video as an IMAGE tensor.

        Samples up to MAX_PREVIEW_FRAMES frames evenly from the video.
        Only decodes the frames we actually need to avoid OOM on long videos.
        Returns shape (B, H, W, 3) float32 in [0, 1].
        """
        try:
            import av  # type: ignore[import-not-found]

            with av.open(video_path) as container:
                stream = container.streams.video[0]
                total = stream.frames or 0

                # First pass: count frames if metadata is missing
                if total <= 0:
                    for _ in container.decode(video=0):
                        total += 1
                    if total == 0:
                        return torch.zeros(1, 64, 64, 3, dtype=torch.float32)
                    # Reopen to decode selected frames
                    container.close()
                    container2 = av.open(video_path)
                else:
                    container2 = container

                # Determine which frame indices to keep
                if total <= MAX_PREVIEW_FRAMES:
                    keep = set(range(total))
                else:
                    keep = set(np.linspace(0, total - 1, MAX_PREVIEW_FRAMES, dtype=int).tolist())

                sampled = []
                try:
                    for idx, frame in enumerate(container2.decode(video=0)):
                        if idx in keep:
                            sampled.append(frame.to_ndarray(format="rgb24"))
                        if idx >= total - 1:
                            break
                finally:
                    if container2 is not container:
                        container2.close()

            if not sampled:
                return torch.zeros(1, 64, 64, 3, dtype=torch.float32)

            stacked = np.stack(sampled)
            return torch.from_numpy(stacked).float().div_(255.0)

        except Exception as e:
            logger.warning("SaveVideo: frame extraction failed: %s", e)
            return torch.zeros(1, 64, 64, 3, dtype=torch.float32)

    def _extract_audio(self, video_path: str) -> dict:
        """Extract audio from video as a ComfyUI AUDIO dict.

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
                [ffprobe_bin, "-v", "error", "-select_streams", "a",
                 "-show_entries", "stream=codec_type", "-of", "csv=p=0",
                 video_path],
                capture_output=True, check=True,
            )
            if not probe.stdout.decode("utf-8", "backslashreplace").strip():
                return silence
        except subprocess.CalledProcessError:
            return silence

        # Extract raw PCM
        try:
            res = subprocess.run(
                [ffmpeg_bin, "-i", video_path, "-vn",
                 "-t", "120",  # cap at 2 min to avoid OOM on long videos
                 "-f", "f32le", "-"],
                capture_output=True, check=True,
            )

            # Ensure buffer size is a multiple of element size (4 bytes for float32)
            stdout_bytes = bytearray(res.stdout)
            rem = len(stdout_bytes) % 4
            if rem != 0:
                stdout_bytes = stdout_bytes[:-rem]

            audio = torch.frombuffer(stdout_bytes, dtype=torch.float32)
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
            logger.warning("SaveVideo: audio extraction failed: %s", e)
            return silence

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
