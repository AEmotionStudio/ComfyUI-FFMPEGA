"""Video analysis and metadata extraction using FFMPEG."""

import json
import subprocess
import shutil
from pathlib import Path
from typing import Optional
from pydantic import BaseModel


class StreamInfo(BaseModel):
    """Information about a single stream."""
    index: int
    codec_name: str
    codec_type: str
    codec_long_name: Optional[str] = None
    profile: Optional[str] = None
    bit_rate: Optional[int] = None
    extra: dict = {}


class VideoStreamInfo(StreamInfo):
    """Video stream specific information."""
    width: int
    height: int
    display_aspect_ratio: Optional[str] = None
    pixel_format: Optional[str] = None
    frame_rate: Optional[float] = None
    avg_frame_rate: Optional[str] = None
    duration: Optional[float] = None
    nb_frames: Optional[int] = None


class AudioStreamInfo(StreamInfo):
    """Audio stream specific information."""
    sample_rate: Optional[int] = None
    channels: Optional[int] = None
    channel_layout: Optional[str] = None
    duration: Optional[float] = None


class VideoMetadata(BaseModel):
    """Complete video metadata."""
    file_path: str
    file_size: int
    format_name: str
    format_long_name: Optional[str] = None
    duration: float
    bit_rate: Optional[int] = None
    nb_streams: int
    video_streams: list[VideoStreamInfo] = []
    audio_streams: list[AudioStreamInfo] = []
    subtitle_streams: list[StreamInfo] = []

    @property
    def primary_video(self) -> Optional[VideoStreamInfo]:
        """Get the primary video stream."""
        return self.video_streams[0] if self.video_streams else None

    @property
    def primary_audio(self) -> Optional[AudioStreamInfo]:
        """Get the primary audio stream."""
        return self.audio_streams[0] if self.audio_streams else None

    @property
    def resolution(self) -> Optional[tuple[int, int]]:
        """Get video resolution as (width, height)."""
        if self.primary_video:
            return (self.primary_video.width, self.primary_video.height)
        return None

    @property
    def aspect_ratio(self) -> Optional[float]:
        """Calculate aspect ratio."""
        if self.primary_video:
            return self.primary_video.width / self.primary_video.height
        return None

    def to_analysis_string(self) -> str:
        """Generate human-readable analysis for LLM context."""
        lines = [
            f"File: {Path(self.file_path).name}",
            f"Format: {self.format_name}",
            f"Duration: {self.duration:.2f} seconds",
            f"File size: {self.file_size / (1024*1024):.2f} MB",
        ]

        if self.primary_video:
            v = self.primary_video
            lines.extend([
                f"Video: {v.width}x{v.height} @ {v.frame_rate:.2f} fps" if v.frame_rate else f"Video: {v.width}x{v.height}",
                f"Video codec: {v.codec_name}",
                f"Pixel format: {v.pixel_format}",
            ])

        if self.primary_audio:
            a = self.primary_audio
            lines.extend([
                f"Audio: {a.codec_name} @ {a.sample_rate} Hz, {a.channels} channels",
            ])

        return "\n".join(lines)


class VideoAnalyzer:
    """Analyzes video files using ffprobe."""

    def __init__(self, ffprobe_path: Optional[str] = None):
        """Initialize the analyzer.

        Args:
            ffprobe_path: Path to ffprobe executable. If None, will search PATH.
        """
        self.ffprobe_path = ffprobe_path or shutil.which("ffprobe")
        if not self.ffprobe_path:
            raise RuntimeError("ffprobe not found in PATH")

    def analyze(self, video_path: str | Path) -> VideoMetadata:
        """Analyze a video file and extract metadata.

        Args:
            video_path: Path to the video file.

        Returns:
            VideoMetadata object with all extracted information.

        Raises:
            FileNotFoundError: If the video file doesn't exist.
            RuntimeError: If ffprobe fails to analyze the file.
        """
        video_path = Path(video_path)
        if not video_path.exists():
            raise FileNotFoundError(f"Video file not found: {video_path}")

        cmd = [
            self.ffprobe_path,
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            str(video_path),
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"ffprobe failed: {result.stderr}")

        data = json.loads(result.stdout)
        return self._parse_probe_data(str(video_path), data)

    def _parse_probe_data(self, file_path: str, data: dict) -> VideoMetadata:
        """Parse ffprobe JSON output into VideoMetadata."""
        format_info = data.get("format", {})
        streams = data.get("streams", [])

        video_streams = []
        audio_streams = []
        subtitle_streams = []

        for stream in streams:
            codec_type = stream.get("codec_type", "")

            if codec_type == "video":
                video_streams.append(self._parse_video_stream(stream))
            elif codec_type == "audio":
                audio_streams.append(self._parse_audio_stream(stream))
            elif codec_type == "subtitle":
                subtitle_streams.append(self._parse_stream(stream))

        return VideoMetadata(
            file_path=file_path,
            file_size=int(format_info.get("size", 0)),
            format_name=format_info.get("format_name", "unknown"),
            format_long_name=format_info.get("format_long_name"),
            duration=float(format_info.get("duration", 0)),
            bit_rate=int(format_info.get("bit_rate", 0)) if format_info.get("bit_rate") else None,
            nb_streams=int(format_info.get("nb_streams", 0)),
            video_streams=video_streams,
            audio_streams=audio_streams,
            subtitle_streams=subtitle_streams,
        )

    def _parse_stream(self, stream: dict) -> StreamInfo:
        """Parse basic stream information."""
        return StreamInfo(
            index=stream.get("index", 0),
            codec_name=stream.get("codec_name", "unknown"),
            codec_type=stream.get("codec_type", "unknown"),
            codec_long_name=stream.get("codec_long_name"),
            profile=stream.get("profile"),
            bit_rate=int(stream.get("bit_rate", 0)) if stream.get("bit_rate") else None,
        )

    def _parse_video_stream(self, stream: dict) -> VideoStreamInfo:
        """Parse video stream information."""
        frame_rate = None
        if stream.get("r_frame_rate"):
            try:
                num, den = map(int, stream["r_frame_rate"].split("/"))
                frame_rate = num / den if den != 0 else None
            except (ValueError, ZeroDivisionError):
                pass

        return VideoStreamInfo(
            index=stream.get("index", 0),
            codec_name=stream.get("codec_name", "unknown"),
            codec_type="video",
            codec_long_name=stream.get("codec_long_name"),
            profile=stream.get("profile"),
            bit_rate=int(stream.get("bit_rate", 0)) if stream.get("bit_rate") else None,
            width=stream.get("width", 0),
            height=stream.get("height", 0),
            display_aspect_ratio=stream.get("display_aspect_ratio"),
            pixel_format=stream.get("pix_fmt"),
            frame_rate=frame_rate,
            avg_frame_rate=stream.get("avg_frame_rate"),
            duration=float(stream.get("duration", 0)) if stream.get("duration") else None,
            nb_frames=int(stream.get("nb_frames", 0)) if stream.get("nb_frames") else None,
        )

    def _parse_audio_stream(self, stream: dict) -> AudioStreamInfo:
        """Parse audio stream information."""
        return AudioStreamInfo(
            index=stream.get("index", 0),
            codec_name=stream.get("codec_name", "unknown"),
            codec_type="audio",
            codec_long_name=stream.get("codec_long_name"),
            profile=stream.get("profile"),
            bit_rate=int(stream.get("bit_rate", 0)) if stream.get("bit_rate") else None,
            sample_rate=int(stream.get("sample_rate", 0)) if stream.get("sample_rate") else None,
            channels=stream.get("channels"),
            channel_layout=stream.get("channel_layout"),
            duration=float(stream.get("duration", 0)) if stream.get("duration") else None,
        )

    def get_frame(self, video_path: str | Path, timestamp: float = 0) -> bytes:
        """Extract a single frame from the video as PNG bytes.

        Args:
            video_path: Path to the video file.
            timestamp: Time in seconds to extract frame from.

        Returns:
            PNG image data as bytes.
        """
        ffmpeg_path = shutil.which("ffmpeg")
        if not ffmpeg_path:
            raise RuntimeError("ffmpeg not found in PATH")

        cmd = [
            ffmpeg_path,
            "-ss", str(timestamp),
            "-i", str(video_path),
            "-vframes", "1",
            "-f", "image2pipe",
            "-vcodec", "png",
            "-",
        ]

        result = subprocess.run(cmd, capture_output=True)
        if result.returncode != 0:
            raise RuntimeError(f"Failed to extract frame: {result.stderr.decode()}")

        return result.stdout
