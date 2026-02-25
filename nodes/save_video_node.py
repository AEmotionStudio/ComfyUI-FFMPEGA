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

    RETURN_TYPES = ("IMAGE", "AUDIO", "STRING")
    RETURN_NAMES = ("images", "audio", "video_path")
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
            # Return empty results when no video is available (e.g. mask
            # overlay path is empty because SAM3 failed or was not used).
            empty_tensor = torch.zeros(1, 64, 64, 3, dtype=torch.float32)
            silent_audio = {"waveform": torch.zeros(1, 1, 1), "sample_rate": 44100}
            return {
                "ui": {"video": [], "file_size": ["0 B"]},
                "result": (empty_tensor, silent_audio, ""),
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

        # --- Extract frames as IMAGE tensor ---
        images_tensor = self._extract_frames(output_path)

        # --- Extract audio ---
        audio_out = self._extract_audio(output_path)

        return {
            "ui": {
                "video": [{
                    "filename": output_filename,
                    "subfolder": subfolder,
                    "type": self.type,
                }],
                "file_size": [size_str],
            },
            "result": (images_tensor, audio_out, output_path),
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

        ffmpeg_bin = shutil.which("ffmpeg")
        ffprobe_bin = shutil.which("ffprobe")
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
                [ffmpeg_bin, "-i", video_path, "-vn", "-f", "f32le", "-"],
                capture_output=True, check=True,
            )
            audio = torch.frombuffer(bytearray(res.stdout), dtype=torch.float32)
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
