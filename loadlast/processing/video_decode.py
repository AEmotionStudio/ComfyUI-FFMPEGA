"""
Video frame decoder using ffmpeg subprocess and PIL.

Supports MP4/WebM (via ffmpeg), GIF (via PIL), and image sequences (via PIL).
Provides uniform subsampling that always preserves first and last frames.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from typing import Optional

import numpy as np
import torch
from PIL import Image

logger = logging.getLogger(__name__)


class VideoDecoder:
    """Decodes video files and image sequences into frame tensors."""

    _ffmpeg_available: Optional[bool] = None

    @classmethod
    def check_ffmpeg(cls) -> bool:
        """Check if ffmpeg is available in PATH. Caches the result."""
        if cls._ffmpeg_available is None:
            cls._ffmpeg_available = shutil.which("ffmpeg") is not None
            if cls._ffmpeg_available:
                logger.info("[LoadLast] ffmpeg found in PATH")
            else:
                logger.info("[LoadLast] ffmpeg not found — MP4/WebM decoding unavailable")
        return cls._ffmpeg_available

    def decode_file(
        self,
        path: str,
        max_frames: int = 0,
        start_frame: int = 0,
        end_frame: int = -1,
    ) -> tuple[torch.Tensor, dict]:
        """
        Decode a video file (MP4/WebM) into a frame tensor using ffmpeg.

        Args:
            path: absolute path to the video file
            max_frames: max frames to return (0 = all)
            start_frame: first frame to extract (0-indexed)
            end_frame: last frame to extract (-1 = end)

        Returns:
            (frames [N, H, W, 3] float32, metadata dict)

        Raises:
            RuntimeError: if ffmpeg is not available
        """
        if not self.check_ffmpeg():
            raise RuntimeError(
                "ffmpeg not found. Install ffmpeg to load MP4/WebM videos. "
                "GIF and image sequences are still available."
            )

        # Probe video metadata first
        metadata = self._probe_video(path)
        total_frames = metadata.get("frame_count", 0)
        fps = metadata.get("fps", 24)

        if total_frames == 0:
            # If probe failed to get frame count, decode all and count
            total_frames = self._count_frames(path)

        # Resolve frame range
        start, end = self._resolve_range(start_frame, end_frame, total_frames)

        # Compute which frame indices to extract
        range_length = end - start + 1
        if max_frames > 0 and range_length > max_frames:
            indices = self.subsample_indices(range_length, max_frames)
            indices = [i + start for i in indices]
        else:
            indices = list(range(start, end + 1))

        # Decode frames using ffmpeg
        frames = self._decode_frames_ffmpeg(path, indices, metadata)

        if not frames:
            raise RuntimeError(f"No frames decoded from {path}")

        # Stack into tensor
        frame_tensor = torch.stack(frames, dim=0)  # [N, H, W, 3]
        metadata["frame_count"] = len(frames)

        return frame_tensor, metadata

    def decode_gif(
        self,
        path: str,
        max_frames: int = 0,
        start_frame: int = 0,
        end_frame: int = -1,
    ) -> tuple[torch.Tensor, dict]:
        """
        Decode GIF using PIL. Extracts frame durations for FPS estimation.

        Returns:
            (frames [N, H, W, 3] float32, metadata dict)
        """
        img = Image.open(path)
        total_frames = getattr(img, 'n_frames', 1)

        # Collect frame durations for FPS estimation
        durations = []
        all_frames_pil = []

        for i in range(total_frames):
            img.seek(i)
            frame = img.convert('RGB')
            all_frames_pil.append(frame.copy())
            duration = img.info.get('duration', 100)  # ms, default 100ms = 10fps
            durations.append(duration)

        # Estimate FPS from average duration
        avg_duration = sum(durations) / len(durations) if durations else 100
        fps = round(1000 / avg_duration) if avg_duration > 0 else 10

        # Resolve frame range
        start, end = self._resolve_range(start_frame, end_frame, total_frames)
        selected_frames = all_frames_pil[start:end + 1]

        # Subsample if needed
        if max_frames > 0 and len(selected_frames) > max_frames:
            indices = self.subsample_indices(len(selected_frames), max_frames)
            selected_frames = [selected_frames[i] for i in indices]

        # Convert to tensors
        frames = []
        for frame_pil in selected_frames:
            arr = np.array(frame_pil).astype(np.float32) / 255.0
            frames.append(torch.from_numpy(arr))

        frame_tensor = torch.stack(frames, dim=0)

        w, h = all_frames_pil[0].size
        metadata = {
            "fps": fps,
            "duration": total_frames * avg_duration / 1000.0,
            "frame_count": len(frames),
            "source_frame_count": total_frames,
            "width": w,
            "height": h,
            "codec": "gif",
            "container": "gif",
            "bitrate": 0,
        }

        return frame_tensor, metadata

    def decode_sequence(
        self,
        frame_paths: list[str],
        max_frames: int = 0,
        start_frame: int = 0,
        end_frame: int = -1,
        default_fps: int = 24,
    ) -> tuple[torch.Tensor, dict]:
        """
        Load an image sequence as a frame tensor.

        Args:
            frame_paths: ordered list of frame file paths
            max_frames: max frames to return (0 = all)
            start_frame: first frame index
            end_frame: last frame index (-1 = end)
            default_fps: assumed FPS when not detectable

        Returns:
            (frames [N, H, W, 3] float32, metadata dict)
        """
        total_frames = len(frame_paths)

        # Resolve frame range
        start, end = self._resolve_range(start_frame, end_frame, total_frames)
        selected_paths = frame_paths[start:end + 1]

        # Subsample if needed
        if max_frames > 0 and len(selected_paths) > max_frames:
            indices = self.subsample_indices(len(selected_paths), max_frames)
            selected_paths = [selected_paths[i] for i in indices]

        # Load frames
        frames = []
        target_size = None

        for i, path in enumerate(selected_paths):
            try:
                img = Image.open(path).convert('RGB')

                if target_size is None:
                    target_size = img.size  # (W, H)
                elif img.size != target_size:
                    img = img.resize(target_size, Image.BILINEAR)

                arr = np.array(img).astype(np.float32) / 255.0
                frames.append(torch.from_numpy(arr))
            except Exception as e:
                logger.warning("[LoadLast] Skipping frame %s: %s", path, e)
                continue

        if not frames:
            raise RuntimeError(f"No frames loaded from sequence starting at {frame_paths[0]}")

        frame_tensor = torch.stack(frames, dim=0)

        w, h = target_size if target_size else (0, 0)
        metadata = {
            "fps": default_fps,
            "duration": total_frames / default_fps,
            "frame_count": len(frames),
            "source_frame_count": total_frames,
            "width": w,
            "height": h,
            "codec": "image_sequence",
            "container": "image_sequence",
            "bitrate": 0,
        }

        return frame_tensor, metadata

    @staticmethod
    def subsample_indices(total: int, max_frames: int) -> list[int]:
        """
        Compute evenly-spaced frame indices.
        Always includes first (0) and last (total-1) frame.

        Args:
            total: total number of frames
            max_frames: target number of frames

        Returns:
            Sorted list of frame indices
        """
        if max_frames >= total:
            return list(range(total))

        if max_frames <= 1:
            return [0]

        if max_frames == 2:
            return [0, total - 1]

        # Evenly space frames including endpoints
        indices = set()
        indices.add(0)
        indices.add(total - 1)

        for i in range(1, max_frames - 1):
            idx = round(i * (total - 1) / (max_frames - 1))
            indices.add(idx)

        return sorted(indices)

    def _probe_video(self, path: str) -> dict:
        """Probe video metadata using ffprobe."""
        metadata = {
            "fps": 24,
            "duration": 0.0,
            "frame_count": 0,
            "source_frame_count": 0,
            "width": 0,
            "height": 0,
            "codec": "",
            "container": "",
            "bitrate": 0,
        }

        try:
            cmd = [
                "ffprobe", "-v", "quiet",
                "-print_format", "json",
                "-show_format", "-show_streams",
                path
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if result.returncode != 0:
                return metadata

            info = json.loads(result.stdout)

            # Find video stream
            video_stream = None
            for stream in info.get("streams", []):
                if stream.get("codec_type") == "video":
                    video_stream = stream
                    break

            if video_stream:
                metadata["width"] = int(video_stream.get("width", 0))
                metadata["height"] = int(video_stream.get("height", 0))
                metadata["codec"] = video_stream.get("codec_name", "")

                # Store raw frame rate strings for VFR detection
                metadata["r_frame_rate"] = video_stream.get("r_frame_rate", "")
                metadata["avg_frame_rate"] = video_stream.get("avg_frame_rate", "")

                # Parse FPS from r_frame_rate (e.g., "30/1" or "30000/1001")
                fps_str = metadata["r_frame_rate"] or "24/1"
                try:
                    num, den = fps_str.split("/")
                    metadata["fps"] = round(int(num) / int(den))
                except (ValueError, ZeroDivisionError):
                    pass

                # Frame count
                nb_frames = video_stream.get("nb_frames")
                if nb_frames and nb_frames != "N/A":
                    metadata["frame_count"] = int(nb_frames)
                    metadata["source_frame_count"] = int(nb_frames)

            fmt = info.get("format", {})
            metadata["container"] = fmt.get("format_name", "")
            duration = fmt.get("duration")
            if duration:
                metadata["duration"] = float(duration)
            bitrate = fmt.get("bit_rate")
            if bitrate:
                metadata["bitrate"] = int(bitrate)

            # Estimate frame count from duration if not available
            if metadata["frame_count"] == 0 and metadata["duration"] > 0:
                metadata["frame_count"] = int(metadata["duration"] * metadata["fps"])
                metadata["source_frame_count"] = metadata["frame_count"]

        except Exception as e:
            logger.debug("[LoadLast] ffprobe failed for %s: %s", path, e)

        return metadata

    def _count_frames(self, path: str) -> int:
        """Count frames in a video using ffprobe."""
        try:
            cmd = [
                "ffprobe", "-v", "error",
                "-count_frames",
                "-select_streams", "v:0",
                "-show_entries", "stream=nb_read_frames",
                "-print_format", "csv=p=0",
                path
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode == 0 and result.stdout.strip():
                return int(result.stdout.strip())
        except Exception:
            pass
        return 0

    def _decode_frames_ffmpeg(
        self, path: str, indices: list[int], metadata: dict
    ) -> list[torch.Tensor]:
        """Decode specific frame indices from a video file using ffmpeg.

        Uses two strategies:
        - Dense sampling (span <= 4x frame count): decode the entire range and pick.
        - Sparse sampling: seek to each frame individually to avoid OOM.
        """
        w, h = metadata.get("width", 0), metadata.get("height", 0)

        if w == 0 or h == 0:
            # Need to probe dimensions
            probe = self._probe_video(path)
            w, h = probe["width"], probe["height"]
            if w == 0 or h == 0:
                raise RuntimeError(f"Cannot determine video dimensions for {path}")

        min_idx = min(indices)
        max_idx = max(indices)
        span = max_idx - min_idx + 1

        # Use per-frame seeking when range is sparse to avoid decoding
        # huge numbers of frames into memory (OOM prevention).
        # Skip for VFR content where timestamp = idx/fps is unreliable.
        is_vfr = metadata.get("r_frame_rate", "") != metadata.get("avg_frame_rate", "") and metadata.get("avg_frame_rate", "")
        if span > len(indices) * 4 and len(indices) < span:
            if is_vfr:
                logger.debug(
                    "[LoadLast] Skipping sparse seek for VFR content "
                    "(r_frame_rate=%s, avg_frame_rate=%s)",
                    metadata.get("r_frame_rate", "?"),
                    metadata.get("avg_frame_rate", "?"),
                )
            else:
                result = self._decode_frames_by_seeking(path, indices, w, h, metadata)
                if result is not None:
                    return result
                # Sparse seek failed or dropped too many frames — fall through to dense decode

        # Use ffmpeg to decode frame range to raw RGB
        # -noautorotate: output coded dimensions, consistent with _seek_frame_ffmpeg
        cmd = [
            "ffmpeg", "-noautorotate", "-v", "error",
            "-i", path,
            "-vf", f"select='between(n\\,{min_idx}\\,{max_idx})',setpts=N/FRAME_RATE/TB",
            "-vsync", "vfr",
            "-pix_fmt", "rgb24",
            "-f", "rawvideo",
            "-"
        ]

        try:
            result = subprocess.run(
                cmd, capture_output=True, timeout=120
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"ffmpeg decode timed out for {path}")

        if result.returncode != 0:
            error_msg = result.stderr.decode('utf-8', errors='replace')[:200]
            raise RuntimeError(f"ffmpeg decode failed: {error_msg}")

        raw_bytes = result.stdout
        frame_size = w * h * 3
        total_decoded = len(raw_bytes) // frame_size

        if total_decoded == 0:
            raise RuntimeError(f"ffmpeg produced no frame data for {path}")

        # Parse raw bytes into frames
        all_decoded = []
        for i in range(total_decoded):
            start = i * frame_size
            frame_bytes = raw_bytes[start:start + frame_size]
            arr = np.frombuffer(frame_bytes, dtype=np.uint8).reshape(h, w, 3)
            tensor = torch.from_numpy(arr.copy()).float() / 255.0
            all_decoded.append(tensor)

        # Select the requested indices (relative to min_idx)
        frames = []
        for idx in indices:
            relative_idx = idx - min_idx
            if 0 <= relative_idx < len(all_decoded):
                frames.append(all_decoded[relative_idx])

        return frames

    def _decode_frames_by_seeking(
        self, path: str, indices: list[int], w: int, h: int, metadata: dict,
    ) -> list[torch.Tensor] | None:
        """Decode specific frame indices by seeking to each one individually.

        Used for sparse sampling to avoid buffering the entire frame range.
        Converts frame indices to timestamps and seeks with ffmpeg.

        Returns a list with the same length as *indices* — failed seeks are
        filled with the nearest successfully-decoded frame to maintain 1:1
        index↔frame correspondence.

        Note: timestamp conversion assumes constant frame rate (CFR).
        For VFR content, seek positions may be slightly inaccurate.
        """
        fps = metadata.get("fps", 24)
        frame_size = w * h * 3
        # Store (position, tensor) so we can backfill gaps
        decoded: dict[int, torch.Tensor] = {}

        for pos, idx in enumerate(indices):
            timestamp = idx / fps if fps > 0 else 0.0
            cmd = [
                "ffmpeg", "-noautorotate",
                "-ss", str(timestamp),
                "-i", path,
                "-vframes", "1",
                "-f", "rawvideo",
                "-pix_fmt", "rgb24",
                "-v", "quiet",
                "-y", "pipe:1",
            ]
            try:
                result = subprocess.run(cmd, capture_output=True, timeout=10)
                if result.returncode != 0 or len(result.stdout) < frame_size:
                    logger.debug(
                        "[LoadLast] Seek to frame %d (%.2fs) failed, skipping", idx, timestamp,
                    )
                    continue
                raw = result.stdout[:frame_size]
                arr = np.frombuffer(raw, dtype=np.uint8).reshape(h, w, 3)
                decoded[pos] = torch.from_numpy(arr.copy()).float() / 255.0
            except Exception as e:
                logger.debug("[LoadLast] Seek to frame %d failed: %s", idx, e)
                continue

        dropped = len(indices) - len(decoded)
        if not decoded:
            logger.warning(
                "[LoadLast] Sparse seek decoded 0/%d frames from %s, "
                "falling back to dense decode",
                len(indices), path,
            )
            return None  # Signal caller to fall back to dense path
        elif dropped > len(indices) // 4:
            logger.warning(
                "[LoadLast] Sparse seek dropped %d/%d frames from %s, "
                "falling back to dense decode",
                dropped, len(indices), path,
            )
            return None  # Signal caller to fall back to dense path
        elif dropped > 0:
            logger.warning(
                "[LoadLast] Sparse seek dropped %d/%d frames from %s",
                dropped, len(indices), path,
            )

        # Build output with 1:1 correspondence — fill gaps with nearest decoded frame
        frames: list[torch.Tensor] = []
        for pos in range(len(indices)):
            if pos in decoded:
                frames.append(decoded[pos])
            else:
                # Find nearest successfully-decoded position
                nearest = min(decoded.keys(), key=lambda p: abs(p - pos))
                frames.append(decoded[nearest])
        return frames

    @staticmethod
    def _resolve_range(start: int, end: int, total: int) -> tuple[int, int]:
        """Resolve frame range, clamping to valid bounds."""
        if total <= 0:
            return 0, 0

        start = max(0, min(start, total - 1))

        if end < 0:
            end = total - 1
        else:
            end = min(end, total - 1)

        if end < start:
            start, end = end, start
            logger.warning("[LoadLast] start_frame > end_frame — swapped")

        return start, end
