"""
Audio track extraction from video files using ffmpeg.

Extracts audio as a raw waveform tensor compatible with ComfyUI's
native AUDIO type: {"waveform": Tensor, "sample_rate": int}.
"""

from __future__ import annotations

import logging
import subprocess
from typing import Optional

import numpy as np
import torch

from .video_decode import VideoDecoder

logger = logging.getLogger(__name__)


class AudioExtractor:
    """Extracts audio tracks from video files using ffmpeg."""

    def extract(self, path: str) -> Optional[dict]:
        """
        Extract audio from a video file.

        Returns:
            ComfyUI AUDIO dict {"waveform": Tensor [B, channels, samples], "sample_rate": int}
            or None if no audio track / ffmpeg unavailable.
        """
        if not VideoDecoder.check_ffmpeg():
            return None

        if not self.has_audio(path):
            return None

        try:
            # Extract audio as raw PCM f32le
            sample_rate = 44100
            cmd = [
                "ffmpeg", "-v", "error",
                "-i", path,
                "-vn",                    # No video
                "-acodec", "pcm_f32le",   # Float32 little-endian
                "-ar", str(sample_rate),  # Resample to standard rate
                "-f", "f32le",            # Raw format
                "-"
            ]

            result = subprocess.run(
                cmd, capture_output=True, timeout=30
            )

            if result.returncode != 0:
                error_msg = result.stderr.decode('utf-8', errors='replace')[:200]
                logger.debug("[LoadLast] Audio extraction failed: %s", error_msg)
                return None

            raw_bytes = result.stdout
            if len(raw_bytes) == 0:
                return None

            # Parse raw PCM data
            # Detect channels by probing
            channels = self._get_audio_channels(path)

            samples_per_channel = len(raw_bytes) // (4 * channels)
            if samples_per_channel == 0:
                return None

            # Parse float32 samples
            total_samples = samples_per_channel * channels
            audio_data = np.frombuffer(
                raw_bytes[:total_samples * 4], dtype=np.float32
            )

            # Reshape to [channels, samples]
            if channels > 1:
                # Interleaved format: [L R L R ...] -> [channels, samples]
                audio_data = audio_data[:samples_per_channel * channels]
                audio_data = audio_data.reshape(-1, channels).T
            else:
                audio_data = audio_data.reshape(1, -1)

            # Convert to tensor and add batch dim: [1, channels, samples]
            waveform = torch.from_numpy(audio_data.copy()).unsqueeze(0)

            return {
                "waveform": waveform,
                "sample_rate": sample_rate,
            }

        except subprocess.TimeoutExpired:
            logger.warning("[LoadLast] Audio extraction timed out for %s", path)
            return None
        except Exception as e:
            logger.debug("[LoadLast] Audio extraction error: %s", e)
            return None

    def has_audio(self, path: str) -> bool:
        """Quick probe: does the video contain an audio stream?"""
        try:
            cmd = [
                "ffprobe", "-v", "error",
                "-select_streams", "a:0",
                "-show_entries", "stream=codec_type",
                "-print_format", "csv=p=0",
                path
            ]
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=5
            )
            return result.returncode == 0 and "audio" in result.stdout.lower()
        except Exception:
            return False

    def _get_audio_channels(self, path: str) -> int:
        """Detect number of audio channels."""
        try:
            cmd = [
                "ffprobe", "-v", "error",
                "-select_streams", "a:0",
                "-show_entries", "stream=channels",
                "-print_format", "csv=p=0",
                path
            ]
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0 and result.stdout.strip():
                return int(result.stdout.strip())
        except Exception:
            pass
        return 2  # Default to stereo
