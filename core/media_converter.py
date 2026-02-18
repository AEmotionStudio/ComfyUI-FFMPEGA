"""Media conversion utilities for FFMPEGA.

Handles conversions between ComfyUI tensor formats and video/audio files,
extracted from FFMPEGAgentNode to keep the node class focused on orchestration.
"""

import concurrent.futures
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
            stream = container.streams.video[0]
            num_frames = getattr(stream, "frames", 0)

            # Optimization: Pre-allocate tensor if frame count is known to avoid large list overhead
            if num_frames > 0:
                frames_iter = container.decode(video=0)
                try:
                    first_frame = next(frames_iter)
                except StopIteration:
                    container.close()
                    return torch.zeros(1, 64, 64, 3, dtype=torch.float32)

                # Get dimensions from first frame
                arr = first_frame.to_ndarray(format="rgb24")
                h, w, c = arr.shape

                # Allocate full float32 tensor
                tensor = torch.empty((num_frames, h, w, c), dtype=torch.float32)

                # Fill first frame
                tensor[0] = torch.from_numpy(arr)
                tensor[0].div_(255.0)

                count = 1
                overflow = []

                # Fill remaining frames
                for frame in frames_iter:
                    arr = frame.to_ndarray(format="rgb24")
                    if count < num_frames:
                        # Optimization: Write directly to target tensor slice to avoid
                        # intermediate float32 allocation and copy.
                        tensor[count] = torch.from_numpy(arr)
                        tensor[count].div_(255.0)
                    else:
                        frame_tensor = torch.from_numpy(arr).float().div_(255.0)
                        overflow.append(frame_tensor)
                    count += 1

                container.close()

                # Handle frame count mismatch (common with VFR or corrupt metadata)
                if count < num_frames:
                    return tensor[:count]
                elif overflow:
                    overflow_tensor = torch.stack(overflow)
                    return torch.cat([tensor, overflow_tensor], dim=0)
                else:
                    return tensor

            # Fallback for unknown frame count: accumulate in list
            frames = []
            for frame in container.decode(video=0):
                arr = frame.to_ndarray(format="rgb24")
                frames.append(arr)
            container.close()

            if not frames:
                return torch.zeros(1, 64, 64, 3, dtype=torch.float32)

            # Optimization: avoid intermediate float32 copy in numpy
            stacked = np.stack(frames)
            return torch.from_numpy(stacked).float().div_(255.0)

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

        h, w = images.shape[1], images.shape[2]

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
        # Write frames in chunks to avoid materializing the entire tensor
        # as a single numpy array (~1.2GB for 192 frames at 1080p).
        CHUNK = 32
        n_frames = images.shape[0]
        for start in range(0, n_frames, CHUNK):
            end = min(start + CHUNK, n_frames)
            # Optimization: Use in-place operations (mul, clamp_) to avoid intermediate
            # float tensor allocation for the chunk scaling step.
            chunk = images[start:end].mul(255.0).clamp_(0, 255).to(torch.uint8).cpu().numpy()
            proc.stdin.write(chunk)
            del chunk
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

        # Optimization: Slice frames first to avoid processing the entire video
        # when we only need a few frames (e.g., for previews or overlay inputs).
        num_frames = min(images.shape[0], max_frames)
        images_slice = images[:num_frames]

        # Optimization: Use in-place operations to reduce memory allocation
        # Original: (images * 255.0).clamp(0, 255).to(torch.uint8)
        frames = images_slice.mul(255.0).clamp_(0, 255).to(torch.uint8).cpu().numpy()

        tmp_dir = tempfile.mkdtemp(prefix="ffmpega_frames_")

        # Optimization: Parallelize PNG saving (I/O and compression bound)
        paths = [os.path.join(tmp_dir, f"frame_{i:03d}.png") for i in range(num_frames)]

        def save_one_frame(idx: int) -> None:
            img = Image.fromarray(frames[idx])
            img.save(paths[idx])

        # Use ThreadPoolExecutor to save images in parallel
        # Default workers is usually min(32, os.cpu_count() + 4), which is good for I/O
        with concurrent.futures.ThreadPoolExecutor() as executor:
            list(executor.map(save_one_frame, range(num_frames)))

        return paths

    @staticmethod
    def _probe_media_duration(path: str) -> float:
        """Probe duration of a media file in seconds.

        Returns 0.0 if probing fails.
        """
        ffprobe_bin = shutil.which("ffprobe")
        if not ffprobe_bin:
            return 0.0
        try:
            result = subprocess.run(
                [ffprobe_bin, "-v", "error", "-show_entries",
                 "format=duration", "-of",
                 "default=noprint_wrappers=1:nokey=1", path],
                capture_output=True, text=True, check=True,
            )
            return float(result.stdout.strip())
        except Exception:
            return 0.0

    def mux_audio(
        self, video_path: str, audio: dict, audio_mode: str = "loop",
    ) -> None:
        """Mux a ComfyUI AUDIO dict into an existing video file.

        Writes the audio waveform to a temp WAV, then combines it with
        the video using ffmpeg, replacing the file in-place.

        Args:
            video_path: Path to the video file (replaced in-place).
            audio: ComfyUI AUDIO dict with 'waveform' and 'sample_rate'.
            audio_mode: How to handle duration mismatch:
                - "loop" (default): Loop audio with crossfade to match
                  video length. If audio is longer, trim to video.
                - "pad": Pad audio with silence to match video length.
                  If audio is longer, the full audio plays.
                - "trim": Use -shortest — output ends at the shorter
                  stream (original behavior).
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

            # Build mux command based on audio_mode
            cmd = [ffmpeg_bin, "-y"]
            af_filters = []

            if audio_mode == "loop":
                # Probe durations to decide whether looping is needed
                vid_dur = self._probe_media_duration(video_path)
                aud_dur = self._probe_media_duration(tmp_wav.name)

                if aud_dur > 0 and vid_dur > 0 and aud_dur < vid_dur:
                    # Loop the audio enough times and add crossfade
                    import math
                    loops_needed = math.ceil(vid_dur / aud_dur)
                    # -stream_loop N repeats N *additional* times
                    cmd.extend(["-i", video_path])
                    cmd.extend([
                        "-stream_loop", str(loops_needed - 1),
                        "-i", tmp_wav.name,
                    ])
                    # Crossfade at each loop boundary for smooth transitions
                    xfade_dur = min(2.0, aud_dur * 0.25)  # 2s or 25% of clip
                    af_filters.append(
                        f"afade=t=out:st={aud_dur - xfade_dur}:d={xfade_dur}"
                    )
                    # Trim the looped audio to video duration
                    af_filters.append(f"atrim=0:{vid_dur}")
                    af_filters.append("asetpts=N/SR/TB")
                else:
                    # Audio is longer or equal — just trim to video
                    cmd.extend(["-i", video_path, "-i", tmp_wav.name])
                cmd.extend(["-map", "0:v", "-map", "1:a"])
                cmd.extend(["-c:v", "copy", "-c:a", "aac"])
                if af_filters:
                    cmd.extend(["-af", ",".join(af_filters)])
                cmd.extend(["-shortest", tmp_out.name])

            elif audio_mode == "pad":
                # Pad audio with silence to match video length
                cmd.extend(["-i", video_path, "-i", tmp_wav.name])
                cmd.extend(["-map", "0:v", "-map", "1:a"])
                cmd.extend(["-c:v", "copy", "-c:a", "aac"])
                cmd.extend(["-af", "apad"])
                # Use -shortest so the padded audio stops at video end
                cmd.extend(["-shortest", tmp_out.name])

            else:  # trim
                cmd.extend(["-i", video_path, "-i", tmp_wav.name])
                cmd.extend(["-map", "0:v", "-map", "1:a"])
                cmd.extend(["-c:v", "copy", "-c:a", "aac"])
                cmd.extend(["-shortest", tmp_out.name])

            subprocess.run(cmd, capture_output=True, check=True)
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

    def mux_audio_mix(
        self, video_path: str, audio_dicts: list[dict],
        audio_mode: str = "loop",
    ) -> None:
        """Mix multiple audio dicts together and mux into a video file.

        Uses ffmpeg's amix filter to blend all audio tracks into one,
        then replaces any existing audio in the video.

        Args:
            video_path: Path to the video file (replaced in-place).
            audio_dicts: List of ComfyUI AUDIO dicts.
            audio_mode: Duration mismatch handling (see mux_audio docs).
        """
        if not audio_dicts:
            return
        if len(audio_dicts) == 1:
            self.mux_audio(video_path, audio_dicts[0], audio_mode=audio_mode)
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

            # Duration strategy for amix depends on audio_mode
            if audio_mode == "pad":
                amix_filter = f"{filter_inputs}amix=inputs={n}:duration=longest,apad[aout]"
            else:
                amix_filter = f"{filter_inputs}amix=inputs={n}:duration=longest[aout]"

            cmd.extend([
                "-filter_complex", amix_filter,
                "-map", "0:v",
                "-map", "[aout]",
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

    def add_silent_audio(self, video_path: str) -> None:
        """Add a silent audio stream to a video-only file (in-place).

        Uses ffmpeg's anullsrc filter to generate silence matching the
        video duration. This ensures [idx:a] references work in concat/xfade
        filter graphs where all inputs must have audio streams.
        """
        ffmpeg_bin = shutil.which("ffmpeg")
        if not ffmpeg_bin:
            return

        tmp_out = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
        tmp_out.close()

        try:
            subprocess.run(
                [
                    ffmpeg_bin, "-y",
                    "-i", video_path,
                    "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
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
            pass  # If adding silence fails, keep the original video
        finally:
            if os.path.exists(tmp_out.name):
                try:
                    os.remove(tmp_out.name)
                except OSError:
                    pass

    @staticmethod
    def _silence() -> dict:
        """Return a silent audio buffer."""
        return {"waveform": torch.zeros(1, 1, 1, dtype=torch.float32), "sample_rate": 44100}
