"""Media conversion utilities for FFMPEGA.

Handles conversions between ComfyUI tensor formats and video/audio files,
extracted from FFMPEGAgentNode to keep the node class focused on orchestration.
"""

import os
import re
import shutil
import subprocess
import tempfile
from typing import Optional

import numpy as np  # type: ignore[import-not-found]
import torch  # type: ignore[import-not-found]


class MediaConverter:
    """Convert between ComfyUI tensor formats and media files."""

    def frames_to_tensor(self, video_path: str) -> torch.Tensor:
        """Extract all frames from a video and return as a batched IMAGE tensor.

        Args:
            video_path: Path to the video file.

        Returns:
            Tensor of shape (B, H, W, 3) with float32 values in [0, 1].
        """
        try:
            import av  # type: ignore[import-not-found]

            container = av.open(video_path)
            frames = []
            for frame in container.decode(video=0):
                arr = frame.to_ndarray(format="rgb24")
                frames.append(arr)
            container.close()

            if not frames:
                return torch.zeros(1, 64, 64, 3, dtype=torch.float32)

            stacked = np.stack(frames).astype(np.float32) / 255.0
            return torch.from_numpy(stacked)

        except Exception:
            return torch.zeros(1, 64, 64, 3, dtype=torch.float32)

    def extract_audio(self, video_path: str) -> dict:
        """Extract audio from a video and return as ComfyUI AUDIO dict.

        Returns a dict with 'waveform' (Tensor of shape [1, channels, samples])
        and 'sample_rate' (int), compatible with ComfyUI's standard AUDIO type.

        If the video has no audio stream, returns a short silent mono buffer.
        """
        ffmpeg_bin = shutil.which("ffmpeg")
        ffprobe_bin = shutil.which("ffprobe")
        if not ffmpeg_bin or not ffprobe_bin:
            return self._silence()

        # Check whether the video actually contains an audio stream
        try:
            probe = subprocess.run(
                [ffprobe_bin, "-v", "error", "-select_streams", "a",
                 "-show_entries", "stream=codec_type", "-of", "csv=p=0", video_path],
                capture_output=True, check=True,
            )
            if not probe.stdout.decode("utf-8", "backslashreplace").strip():
                return self._silence()
        except subprocess.CalledProcessError:
            return self._silence()

        # Extract raw PCM audio via ffmpeg
        try:
            res = subprocess.run(
                [ffmpeg_bin, "-i", video_path, "-f", "f32le", "-"],
                capture_output=True, check=True,
            )
            audio = torch.frombuffer(bytearray(res.stdout), dtype=torch.float32)
            match = re.search(r", (\d+) Hz, (\w+), ", res.stderr.decode("utf-8", "backslashreplace"))
            if match:
                ar = int(match.group(1))
                ac = {"mono": 1, "stereo": 2}.get(match.group(2), 2)
            else:
                ar = 44100
                ac = 2
            audio = audio.reshape((-1, ac)).transpose(0, 1).unsqueeze(0)
            return {"waveform": audio, "sample_rate": ar}
        except Exception:
            return self._silence()

    def images_to_video(
        self, images: torch.Tensor, fps: int = 24
    ) -> str:
        """Convert an IMAGE tensor (B, H, W, 3) to a temporary video file.

        Args:
            images: Batched image tensor with float32 values in [0, 1].
            fps: Frame rate for the output video.

        Returns:
            Path to the created temporary video file.
        """
        ffmpeg_bin = shutil.which("ffmpeg")
        if not ffmpeg_bin:
            raise RuntimeError("ffmpeg not found in PATH")

        frames = (images.cpu().numpy() * 255.0).clip(0, 255).astype(np.uint8)
        h, w = frames.shape[1], frames.shape[2]

        tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
        tmp.close()

        proc = subprocess.Popen(
            [
                ffmpeg_bin, "-y",
                "-f", "rawvideo",
                "-vcodec", "rawvideo",
                "-s", f"{w}x{h}",
                "-pix_fmt", "rgb24",
                "-r", str(fps),
                "-i", "-",
                "-c:v", "libx264",
                "-pix_fmt", "yuv420p",
                "-preset", "fast",
                "-crf", "18",
                tmp.name,
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        proc.stdin.write(frames.tobytes())
        proc.stdin.close()
        proc.wait()

        if proc.returncode != 0:
            stderr = proc.stderr.read().decode("utf-8", "backslashreplace")
            os.remove(tmp.name)
            raise RuntimeError(f"Failed to create temp video from images: {stderr}")

        return tmp.name

    def save_frames_as_images(
        self, images: torch.Tensor, max_frames: int = 50
    ) -> list[str]:
        """Save individual frames from an IMAGE tensor as temporary PNG files.

        Used by multi-input skills (grid, slideshow, overlay) that need
        separate image files as FFMPEG inputs.

        Args:
            images: Batched image tensor (B, H, W, 3) with float32 in [0, 1].
            max_frames: Maximum number of frames to export (safety limit).

        Returns:
            List of paths to temporary PNG files.
        """
        from PIL import Image  # type: ignore[import-not-found]

        frames = (images.cpu().numpy() * 255.0).clip(0, 255).astype(np.uint8)
        num_frames = min(frames.shape[0], max_frames)
        tmp_dir = tempfile.mkdtemp(prefix="ffmpega_frames_")

        paths = []
        for i in range(num_frames):
            path = os.path.join(tmp_dir, f"frame_{i:03d}.png")
            img = Image.fromarray(frames[i])
            img.save(path)
            paths.append(path)

        return paths

    def mux_audio(self, video_path: str, audio: dict) -> None:
        """Mux a ComfyUI AUDIO dict into an existing video file.

        Writes the audio waveform to a temp WAV, then combines it with
        the video using ffmpeg, replacing the file in-place.
        """
        ffmpeg_bin = shutil.which("ffmpeg")
        if not ffmpeg_bin:
            return

        try:
            waveform = audio["waveform"]       # (1, channels, samples)
            sample_rate = audio["sample_rate"]
        except Exception as e:
            import logging
            logging.getLogger("ffmpega").warning(
                f"Skipping audio mux — could not extract audio: {e}"
            )
            return
        channels = waveform.size(1)

        audio_data = waveform.squeeze(0).transpose(0, 1).contiguous()  # (samples, channels)
        audio_bytes = (audio_data * 32767.0).clamp(-32768, 32767).to(torch.int16).numpy().tobytes()

        tmp_wav = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tmp_wav.close()
        tmp_out = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
        tmp_out.close()

        try:
            subprocess.run(
                [
                    ffmpeg_bin, "-y",
                    "-f", "s16le",
                    "-ar", str(sample_rate),
                    "-ac", str(channels),
                    "-i", "-",
                    tmp_wav.name,
                ],
                input=audio_bytes,
                capture_output=True,
            )

            subprocess.run(
                [
                    ffmpeg_bin, "-y",
                    "-i", video_path,
                    "-i", tmp_wav.name,
                    "-map", "0:v",
                    "-map", "1:a",
                    "-c:v", "copy",
                    "-c:a", "aac",
                    "-shortest",
                    tmp_out.name,
                ],
                capture_output=True, check=True,
            )

            shutil.move(tmp_out.name, video_path)
        except Exception:
            pass  # If muxing fails, keep the original video without audio
        finally:
            for f in [tmp_wav.name, tmp_out.name]:
                if os.path.exists(f):
                    try:
                        os.remove(f)
                    except OSError:
                        pass

    def mux_audio_mix(self, video_path: str, audio_dicts: list[dict]) -> None:
        """Mix multiple audio dicts together and mux into a video file.

        Uses ffmpeg's amix filter to blend all audio tracks into one,
        then replaces any existing audio in the video.
        """
        if not audio_dicts:
            return
        if len(audio_dicts) == 1:
            self.mux_audio(video_path, audio_dicts[0])
            return

        ffmpeg_bin = shutil.which("ffmpeg")
        if not ffmpeg_bin:
            return

        tmp_wavs = []
        tmp_out = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
        tmp_out.close()

        try:
            # Write each audio dict to a temp WAV
            for audio in audio_dicts:
                waveform = audio["waveform"]
                sample_rate = audio["sample_rate"]
                channels = waveform.size(1)
                audio_data = waveform.squeeze(0).transpose(0, 1).contiguous()
                audio_bytes = (
                    (audio_data * 32767.0)
                    .clamp(-32768, 32767)
                    .to(torch.int16)
                    .numpy()
                    .tobytes()
                )
                tmp_wav = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
                tmp_wav.close()
                subprocess.run(
                    [
                        ffmpeg_bin, "-y",
                        "-f", "s16le",
                        "-ar", str(sample_rate),
                        "-ac", str(channels),
                        "-i", "-",
                        tmp_wav.name,
                    ],
                    input=audio_bytes,
                    capture_output=True,
                )
                tmp_wavs.append(tmp_wav.name)

            # Build amix command: video + all audio WAVs
            cmd = [ffmpeg_bin, "-y", "-i", video_path]
            for wav in tmp_wavs:
                cmd.extend(["-i", wav])

            n = len(tmp_wavs)
            # Build filter: mix all audio inputs together
            filter_inputs = "".join(f"[{i+1}:a]" for i in range(n))
            amix_filter = f"{filter_inputs}amix=inputs={n}:duration=longest"

            cmd.extend([
                "-filter_complex", amix_filter,
                "-map", "0:v",
                "-c:v", "copy",
                "-c:a", "aac",
                "-shortest",
                tmp_out.name,
            ])

            subprocess.run(cmd, capture_output=True, check=True)
            shutil.move(tmp_out.name, video_path)
        except Exception:
            pass  # If mixing fails, keep the original video
        finally:
            for f in tmp_wavs + [tmp_out.name]:
                if os.path.exists(f):
                    try:
                        os.remove(f)
                    except OSError:
                        pass

    def has_audio_stream(self, video_path: str) -> bool:
        """Check whether a video file contains an audio stream."""
        ffprobe_bin = shutil.which("ffprobe")
        if not ffprobe_bin:
            return False
        try:
            probe = subprocess.run(
                [ffprobe_bin, "-v", "error", "-select_streams", "a",
                 "-show_entries", "stream=codec_type", "-of", "csv=p=0", video_path],
                capture_output=True, check=True,
            )
            return bool(probe.stdout.decode("utf-8", "backslashreplace").strip())
        except subprocess.CalledProcessError:
            return False

    @staticmethod
    def _silence() -> dict:
        """Return a silent audio buffer."""
        return {"waveform": torch.zeros(1, 1, 1, dtype=torch.float32), "sample_rate": 44100}
