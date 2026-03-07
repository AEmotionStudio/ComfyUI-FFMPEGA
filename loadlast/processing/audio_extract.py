"""
Audio track extraction from video files using ffmpeg.

Extracts audio as a raw waveform tensor compatible with ComfyUI's
native AUDIO type: {"waveform": Tensor, "sample_rate": int}.
"""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from typing import Optional

import numpy as np
import torch

from .video_decode import VideoDecoder

logger = logging.getLogger(__name__)


@dataclass
class _AudioProbeResult:
    """Result from a single ffprobe invocation for audio stream info."""
    has_audio: bool
    channels: int = 2        # default stereo
    sample_rate: int = 44100  # default 44.1 kHz


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

        probe = self._probe_audio(path)
        if not probe.has_audio:
            return None

        try:
            sample_rate = probe.sample_rate
            channels = probe.channels
            # Extract audio as raw PCM f32le at the probed sample rate
            cmd = [
                "ffmpeg", "-v", "error",
                "-i", path,
                "-vn",                    # No video
                "-acodec", "pcm_f32le",   # Float32 little-endian
                "-ar", str(sample_rate),  # Explicit rate to match probe
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
        return self._probe_audio(path).has_audio

    @staticmethod
    def _probe_audio(path: str) -> _AudioProbeResult:
        """Probe audio stream properties in a single ffprobe call.

        Returns codec_type, channels, and sample_rate from one invocation
        instead of three separate subprocess calls.
        """
        try:
            cmd = [
                "ffprobe", "-v", "error",
                "-select_streams", "a:0",
                "-show_entries", "stream=codec_type,channels,sample_rate",
                "-print_format", "csv=p=0",
                path,
            ]
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=5,
            )
            if result.returncode != 0 or not result.stdout.strip():
                return _AudioProbeResult(has_audio=False)

            # Output format: "audio,2,44100" (codec_type,channels,sample_rate)
            parts = result.stdout.strip().split(",")
            if not parts or "audio" not in parts[0].lower():
                return _AudioProbeResult(has_audio=False)

            channels = 2
            sample_rate = 44100
            if len(parts) >= 2 and parts[1].strip():
                try:
                    channels = int(parts[1].strip())
                except ValueError:
                    pass
            if len(parts) >= 3 and parts[2].strip():
                try:
                    rate = int(parts[2].strip())
                    if rate > 0:
                        sample_rate = rate
                except ValueError:
                    pass

            return _AudioProbeResult(
                has_audio=True,
                channels=channels,
                sample_rate=sample_rate,
            )
        except Exception:
            return _AudioProbeResult(has_audio=False)
