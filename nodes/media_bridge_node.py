"""MediaBridge node for ComfyUI.

Bidirectional switch between IMAGE tensors and video file paths:

  images_to_path — Encode an IMAGE tensor to a temp video file, output the path.
  path_to_images — Decode a video file path into IMAGE tensor + AUDIO.

This is the lightweight "media switch" for quickly converting between
tensor-based and path-based video representations without needing the
full Load Video Path node.
"""

import gc
import logging

import torch

try:
    from ..core.media_converter import MediaConverter
except ImportError:
    from core.media_converter import MediaConverter  # type: ignore

logger = logging.getLogger("FFMPEGA")


class MediaBridgeNode:
    """Bidirectional IMAGE ↔ video-path converter."""

    MODES = ["images_to_path", "path_to_images"]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "mode": (cls.MODES, {
                    "default": "images_to_path",
                    "tooltip": (
                        "images_to_path: encode IMAGE tensor → temp video file path.\n"
                        "path_to_images: decode video file path → IMAGE tensor + AUDIO."
                    ),
                }),
            },
            "optional": {
                "images": ("IMAGE", {
                    "tooltip": (
                        "Video frames from a Load Video node or any IMAGE source. "
                        "Used in images_to_path mode."
                    ),
                }),
                "video_path": ("STRING", {
                    "forceInput": True,
                    "tooltip": (
                        "Path to a video file. Used in path_to_images mode."
                    ),
                }),
                "fps": ("INT", {
                    "default": 24,
                    "min": 1,
                    "max": 120,
                    "step": 1,
                    "tooltip": (
                        "Frames per second for encoding (images_to_path mode). "
                        "Ignored in path_to_images mode — FPS is read from the file."
                    ),
                }),
                "audio": ("AUDIO", {
                    "tooltip": (
                        "Optional audio to mux into the encoded video "
                        "(images_to_path mode only)."
                    ),
                }),
            },
        }

    RETURN_TYPES = ("STRING", "IMAGE", "AUDIO", "FLOAT", "INT")
    RETURN_NAMES = ("video_path", "images", "audio", "fps", "frame_count")
    OUTPUT_TOOLTIPS = (
        "File path to the temp video (images_to_path) or empty string (path_to_images).",
        "Decoded video frames (path_to_images) or empty tensor (images_to_path).",
        "Extracted audio (path_to_images) or silent fallback (images_to_path).",
        "Frames per second — always populated regardless of mode.",
        "Total frame count — always populated regardless of mode.",
    )
    FUNCTION = "convert"
    CATEGORY = "FFMPEGA"
    DESCRIPTION = (
        "Bidirectional media switch: convert IMAGE tensors to a video "
        "file path, or a video file path back to IMAGE tensors + audio. "
        "Use mode dropdown to pick the conversion direction."
    )

    def convert(
        self,
        mode: str = "images_to_path",
        images: torch.Tensor | None = None,
        video_path: str | None = None,
        fps: int = 24,
        audio: dict | None = None,
    ) -> tuple:
        """Run the selected conversion.

        Args:
            mode: Conversion direction.
            images: IMAGE tensor (N, H, W, 3) — required for images_to_path.
            video_path: Path string — required for path_to_images.
            fps: Frame rate for encoding.
            audio: Optional AUDIO dict to mux (images_to_path only).

        Returns:
            Tuple of (video_path, images, audio, fps, frame_count).
        """
        if mode == "images_to_path":
            return self._images_to_path(images, fps, audio)
        else:
            return self._path_to_images(video_path)

    # ── images → path ────────────────────────────────────────────────

    def _images_to_path(
        self,
        images: torch.Tensor | None,
        fps: int,
        audio: dict | None,
    ) -> tuple:
        if images is None:
            raise ValueError(
                "Media Bridge: 'images' input is required in images_to_path mode. "
                "Connect an IMAGE source or switch mode to path_to_images."
            )

        converter = MediaConverter()
        out_path = converter.images_to_video(images, fps=fps)

        frame_count = images.shape[0]
        out_fps = float(fps)

        # Mux audio if provided
        if audio is not None:
            converter.mux_audio(out_path, audio)

        # Release tensor reference early
        del images
        gc.collect()
        try:
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass

        logger.info("MediaBridge: images→path  %s  (%d frames, %.1f fps)", out_path, frame_count, out_fps)

        # Unused outputs get safe defaults
        empty_images = torch.zeros(1, 64, 64, 3, dtype=torch.float32)
        silent_audio = {"waveform": torch.zeros(1, 1, 1), "sample_rate": 44100}

        return (out_path, empty_images, silent_audio, out_fps, frame_count)

    # ── path → images ────────────────────────────────────────────────

    def _path_to_images(self, video_path: str | None) -> tuple:
        if not video_path or not isinstance(video_path, str) or not video_path.strip():
            raise ValueError(
                "Media Bridge: 'video_path' input is required in path_to_images mode. "
                "Connect a video path STRING or switch mode to images_to_path."
            )

        import os
        video_path = video_path.strip()
        if not os.path.isfile(video_path):
            raise FileNotFoundError(
                f"Media Bridge: video file not found: {video_path}"
            )

        converter = MediaConverter()
        images = converter.frames_to_tensor(video_path)
        audio = converter.extract_audio(video_path)

        frame_count = images.shape[0]

        # Probe FPS from file
        fps = self._probe_fps(video_path)

        logger.info("MediaBridge: path→images  %s  (%d frames, %.1f fps)", video_path, frame_count, fps)

        return ("", images, audio, fps, frame_count)

    @staticmethod
    def _probe_fps(video_path: str) -> float:
        """Read FPS from a video file via ffprobe."""
        import json
        import subprocess
        try:
            from ..core.bin_paths import get_ffprobe_bin
        except ImportError:
            from core.bin_paths import get_ffprobe_bin  # type: ignore

        ffprobe_bin = get_ffprobe_bin()
        if not ffprobe_bin:
            return 24.0

        try:
            result = subprocess.run(
                [
                    ffprobe_bin, "-v", "quiet",
                    "-print_format", "json",
                    "-show_streams", video_path,
                ],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode != 0:
                return 24.0

            data = json.loads(result.stdout)
            for s in data.get("streams", []):
                if s.get("codec_type") == "video":
                    r_fps = s.get("r_frame_rate", "")
                    if "/" in r_fps:
                        num, den = r_fps.split("/")
                        if int(den) > 0:
                            return round(int(num) / int(den), 3)
                    elif r_fps:
                        return round(float(r_fps), 3)
        except Exception as e:
            logger.warning("MediaBridge: ffprobe fps failed: %s", e)

        return 24.0
