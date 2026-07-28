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
try:
    from ..core.bin_paths import get_ffmpeg_bin, get_ffprobe_bin
except ImportError:
    from core.bin_paths import get_ffmpeg_bin, get_ffprobe_bin  # type: ignore

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
                "images_a": ("IMAGE", {
                    "tooltip": (
                        "Image batch to encode as video. When connected "
                        "without a video_path, encodes the images into "
                        "an MP4 video at the specified fps. More slots "
                        "appear automatically (images_b, images_c, ...) so "
                        "you can stack several sources for comparison."
                    ),
                }),
                "video_path_a": ("STRING", {
                    "forceInput": True,
                    "tooltip": (
                        "Path to a video file (typically from the "
                        "FFMPEGA Agent's video_path output). The file "
                        "already contains audio if the source had it. "
                        "More slots appear automatically (video_path_b, "
                        "video_path_c, ...) — connect several and set "
                        "'layout' to combine them side-by-side."
                    ),
                }),
                "layout": (
                    ["auto", "horizontal", "vertical", "grid", "none"],
                    {
                        "default": "auto",
                        "tooltip": (
                            "How to combine multiple connected sources. "
                            "auto = best-fit grid (2 side-by-side, 4 in a "
                            "2x2, ...). horizontal/vertical/grid force a "
                            "layout. none = save each source as its own "
                            "file (no combining)."
                        ),
                    },
                ),
                "label_panels": ("BOOLEAN", {
                    "default": False,
                    "label_on": "Label panels",
                    "label_off": "No labels",
                    "tooltip": (
                        "Draw a caption on each panel of a combined video "
                        "using the comma-separated 'labels' field."
                    ),
                }),
                "labels": ("STRING", {
                    "default": "",
                    "tooltip": (
                        "Comma-separated panel captions, e.g. "
                        "'Original, Upscaled'. Used only when 'label_panels' "
                        "is on. Extra panels beyond the list stay unlabeled."
                    ),
                }),
                "panel_gap": ("INT", {
                    "default": 4,
                    "min": 0,
                    "max": 128,
                    "tooltip": (
                        "Pixel gap between panels in a combined video."
                    ),
                }),
                "fps": ("INT", {
                    "default": 24,
                    "min": 1,
                    "max": 120,
                    "tooltip": (
                        "Frame rate for encoding images to video. "
                        "Only used when images are provided without "
                        "a video_path."
                    ),
                }),
                "audio": ("AUDIO", {
                    "tooltip": (
                        "Optional upstream AUDIO pass-through. "
                        "When connected, forwarded directly to the "
                        "audio output instead of extracting audio "
                        "from the video."
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
                "mask": ("MASK", {
                    "tooltip": (
                        "Optional upstream MASK pass-through. "
                        "Forwarded as-is to the mask output."
                    ),
                }),
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
            },
            "hidden": {
                "prompt": "PROMPT",
                "extra_pnginfo": "EXTRA_PNGINFO",
            },
        }

    RETURN_TYPES = ("IMAGE", "AUDIO", "STRING", "STRING", "MASK")
    RETURN_NAMES = ("images", "audio", "video_path", "mask_points", "mask")
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
        video_path_a: str = "",
        filename_prefix: str = "FFMPEGA",
        save_output: bool = True,
        overwrite: bool = False,
        mask_points: str = "",
        mask=None,
        images_a=None,
        audio=None,
        fps: int = 24,
        layout: str = "auto",
        label_panels: bool = False,
        labels: str = "",
        panel_gap: int = 4,
        prompt=None,
        extra_pnginfo=None,
        **kwargs,
    ) -> dict:
        """Copy video to output directory and return UI data for preview.

        Accepts dynamic ``video_path_a..z`` / ``images_a..z`` slots (plus the
        legacy bare ``video_path`` / ``images`` names for older workflows).
        When more than one source is connected and ``layout`` != ``none``,
        the sources are combined into one side-by-side / grid comparison clip.
        """
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

        # --- Gather all connected sources (paths and/or image batches) ---
        sources = self._collect_sources(video_path_a, images_a, kwargs)

        # --- "none": save each source as its own file (no combining) ---
        if len(sources) > 1 and str(layout).lower() == "none":
            return self._save_each(
                sources, filename_prefix, save_output, overwrite,
                mask_points, mask, audio, fps, prompt, extra_pnginfo,
            )

        # --- Combine multiple sources into one comparison clip ---
        combined_temp = None
        video_path = ""
        images = None
        if len(sources) > 1:
            label_list = self._parse_labels(labels) if label_panels else None
            try:
                try:
                    from ..core.video_compare import combine_videos
                except ImportError:
                    from core.video_compare import combine_videos  # type: ignore
                combined_temp = combine_videos(
                    sources, layout=str(layout), labels=label_list,
                    gap=int(panel_gap), fps=int(fps),
                )
            except Exception as e:
                logger.error("SaveVideo: combine failed: %s", e)
            if combined_temp and os.path.isfile(combined_temp):
                video_path = combined_temp
            else:
                # Fall back to the first source so the run still produces output
                logger.warning("SaveVideo: falling back to first source")
                first = sources[0]
                if isinstance(first, str):
                    video_path = first
                else:
                    images = first
        elif len(sources) == 1:
            first = sources[0]
            if isinstance(first, str):
                video_path = first
            else:
                images = first

        # --- Encode IMAGE batch → video if no video_path provided ---
        temp_video_from_images = None
        if (
            (not video_path or not os.path.isfile(video_path))
            and images is not None
            and hasattr(images, "shape")
            and images.shape[0] > 0
        ):
            try:
                try:
                    from ..core.media_converter import MediaConverter
                except ImportError:
                    from core.media_converter import MediaConverter  # type: ignore
                mc = MediaConverter()
                temp_video_from_images = mc.images_to_video(images, fps=fps)
                video_path = temp_video_from_images
                logger.info(
                    "SaveVideo: encoded %d images → %s @ %d fps",
                    images.shape[0], video_path, fps,
                )
            except Exception as e:
                logger.error("SaveVideo: failed to encode images → video: %s", e)

        if not video_path or not os.path.isfile(video_path):
            # Return empty results when no video is available (e.g. mask
            # overlay path is empty because SAM3 failed or was not used).
            empty_tensor = torch.zeros(1, 64, 64, 3, dtype=torch.float32)
            silent_audio = {"waveform": torch.zeros(1, 1, 1), "sample_rate": 44100}
            return {
                "ui": {"video": [], "file_size": ["0 B"]},
                "result": (empty_tensor, silent_audio, "", mask_points or "",
                           mask if mask is not None else torch.zeros(1, 64, 64, dtype=torch.float32)),
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

        # --- Extract frames as IMAGE tensor (unless provided upstream) ---
        images_tensor = images if images is not None else self._extract_frames(output_path)

        # --- Extract audio (unless provided upstream) ---
        audio_out = audio if audio is not None else self._extract_audio(output_path)

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

        # Clean up temp video from images encoding
        if temp_video_from_images and os.path.isfile(temp_video_from_images):
            try:
                os.remove(temp_video_from_images)
            except OSError:
                pass

        # Clean up the combined comparison temp (and its temp dir)
        if combined_temp and os.path.isfile(combined_temp):
            try:
                shutil.rmtree(os.path.dirname(combined_temp), ignore_errors=True)
            except OSError:
                pass

        return {
            "ui": {
                "video": video_ui,
                "file_size": [size_str],
            },
            "result": (images_tensor, audio_out, output_path, mask_points or "",
                       mask if mask is not None else torch.zeros(1, 64, 64, dtype=torch.float32)),
        }

    @staticmethod
    def _parse_labels(labels: str) -> list[str]:
        """Split a comma-separated labels string into a clean list."""
        if not labels or not isinstance(labels, str):
            return []
        return [part.strip() for part in labels.split(",")]

    @staticmethod
    def _collect_sources(video_path_a, images_a, kwargs: dict) -> list:
        """Collect connected sources in panel order (a, b, c, ...).

        Each panel prefers its ``video_path_<letter>`` string over its
        ``images_<letter>`` tensor.  Legacy bare ``video_path`` / ``images``
        inputs from older workflows are honored as a leading panel.
        """
        from string import ascii_lowercase

        sources: list = []

        def _valid_path(v) -> bool:
            return isinstance(v, str) and bool(v) and os.path.isfile(v)

        def _valid_tensor(v) -> bool:
            return v is not None and hasattr(v, "shape") and v.shape[0] > 0

        # Backward-compat: legacy bare names become the first panel.
        legacy_vp = kwargs.get("video_path")
        legacy_img = kwargs.get("images")
        if _valid_path(legacy_vp):
            sources.append(legacy_vp)
        elif _valid_tensor(legacy_img):
            sources.append(legacy_img)

        for letter in ascii_lowercase:
            vp = video_path_a if letter == "a" else kwargs.get(f"video_path_{letter}")
            img = images_a if letter == "a" else kwargs.get(f"images_{letter}")
            if _valid_path(vp):
                sources.append(vp)
            elif _valid_tensor(img):
                sources.append(img)
        return sources

    def _save_each(
        self, sources, filename_prefix, save_output, overwrite,
        mask_points, mask, audio, fps, prompt, extra_pnginfo,
    ) -> dict:
        """layout='none': save each source separately, preview them all."""
        video_ui: list = []
        first_path = ""
        temps: list[str] = []
        for src in sources:
            path = src
            if not isinstance(src, str):
                try:
                    try:
                        from ..core.media_converter import MediaConverter
                    except ImportError:
                        from core.media_converter import MediaConverter  # type: ignore
                    path = MediaConverter().images_to_video(src, fps=fps)
                    temps.append(path)
                except Exception as e:
                    logger.error("SaveVideo: encode for none-layout failed: %s", e)
                    continue
            if not path or not os.path.isfile(path):
                continue
            entry = self._copy_to_output(
                path, filename_prefix, save_output, overwrite,
                prompt, extra_pnginfo,
            )
            if entry:
                video_ui.append(entry["ui"])
                if not first_path:
                    first_path = entry["path"]

        for t in temps:
            try:
                os.remove(t)
            except OSError:
                pass

        if not first_path:
            empty_tensor = torch.zeros(1, 64, 64, 3, dtype=torch.float32)
            silent_audio = {"waveform": torch.zeros(1, 1, 1), "sample_rate": 44100}
            return {
                "ui": {"video": [], "file_size": ["0 B"]},
                "result": (empty_tensor, silent_audio, "", mask_points or "",
                           mask if mask is not None else torch.zeros(1, 64, 64, dtype=torch.float32)),
            }

        images_tensor = self._extract_frames(first_path)
        audio_out = audio if audio is not None else self._extract_audio(first_path)
        return {
            "ui": {"video": video_ui, "file_size": [f"{len(video_ui)} videos"]},
            "result": (
                images_tensor, audio_out, first_path, mask_points or "",
                mask if mask is not None else torch.zeros(1, 64, 64, dtype=torch.float32),
            ),
        }

    def _copy_to_output(
        self, video_path, filename_prefix, save_output, overwrite,
        prompt, extra_pnginfo,
    ) -> dict | None:
        """Copy one video to the output (or temp) dir; return a UI entry."""
        ext = os.path.splitext(video_path)[1] or ".mp4"
        full_output_folder, filename, _counter, subfolder, _ = (
            folder_paths.get_save_image_path(filename_prefix, self.output_dir)
        )
        os.makedirs(full_output_folder, exist_ok=True)

        if save_output:
            if overwrite:
                output_filename = f"{filename}{ext}"
            else:
                import glob
                existing = glob.glob(os.path.join(full_output_folder, f"{filename}_*"))
                max_counter = 0
                for path in existing:
                    base = os.path.splitext(os.path.basename(path))[0]
                    parts = base.rsplit("_", 1)
                    if len(parts) == 2 and parts[1].isdigit():
                        max_counter = max(max_counter, int(parts[1]))
                output_filename = f"{filename}_{max_counter + 1:05}{ext}"
            output_path = os.path.join(full_output_folder, output_filename)
            try:
                if os.path.abspath(video_path) != os.path.abspath(output_path):
                    shutil.copy2(video_path, output_path)
                self._save_workflow_png(
                    output_path, full_output_folder, output_filename,
                    prompt, extra_pnginfo,
                )
            except Exception as e:
                logger.error("SaveVideo: copy failed: %s", e)
                return None
            return {
                "ui": {"filename": output_filename, "subfolder": subfolder, "type": self.type},
                "path": output_path,
            }

        # preview-only
        temp_dir = folder_paths.get_temp_directory()
        os.makedirs(temp_dir, exist_ok=True)
        preview_name = f"ffmpega_preview_{os.getpid()}_{len(os.listdir(temp_dir))}{ext}"
        preview_path = os.path.join(temp_dir, preview_name)
        try:
            shutil.copy2(video_path, preview_path)
        except Exception as e:
            logger.warning("SaveVideo: preview copy failed: %s", e)
            return None
        return {
            "ui": {"filename": preview_name, "subfolder": "", "type": "temp"},
            "path": preview_path,
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

            ffmpeg_bin = get_ffmpeg_bin()
            if not ffmpeg_bin:
                logger.warning("SaveVideo: ffmpeg not found — skipping workflow PNG")
                return None

            # Try 1s mark first (past fade-in), fall back to 0s for short videos
            for seek in ("1", "0"):
                result = subprocess.run(
                    [
                        ffmpeg_bin, "-y",
                        "-i", video_path,
                        "-ss", seek,
                        "-frames:v", "1",
                        "-q:v", "2",
                        tmp_frame.name,
                    ],
                    capture_output=True,
                    timeout=15,
                )
                if (
                    result.returncode == 0
                    and os.path.isfile(tmp_frame.name)
                    and os.path.getsize(tmp_frame.name) > 0
                ):
                    break

            if not os.path.isfile(tmp_frame.name) or os.path.getsize(tmp_frame.name) == 0:
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
