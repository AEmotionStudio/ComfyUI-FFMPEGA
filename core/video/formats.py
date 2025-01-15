"""Video, audio, and container format definitions."""

from enum import Enum
from typing import Optional
from pydantic import BaseModel


class VideoCodec(str, Enum):
    """Supported video codecs."""
    H264 = "libx264"
    H265 = "libx265"
    VP9 = "libvpx-vp9"
    AV1 = "libaom-av1"
    PRORES = "prores_ks"
    COPY = "copy"


class AudioCodec(str, Enum):
    """Supported audio codecs."""
    AAC = "aac"
    MP3 = "libmp3lame"
    OPUS = "libopus"
    FLAC = "flac"
    PCM = "pcm_s16le"
    COPY = "copy"


class ContainerFormat(str, Enum):
    """Supported container formats."""
    MP4 = "mp4"
    MKV = "matroska"
    WEBM = "webm"
    MOV = "mov"
    AVI = "avi"
    GIF = "gif"


class PixelFormat(str, Enum):
    """Common pixel formats."""
    YUV420P = "yuv420p"
    YUV422P = "yuv422p"
    YUV444P = "yuv444p"
    RGB24 = "rgb24"
    RGBA = "rgba"


class VideoFormat(BaseModel):
    """Video format specification."""
    codec: VideoCodec = VideoCodec.H264
    width: Optional[int] = None
    height: Optional[int] = None
    fps: Optional[float] = None
    bitrate: Optional[str] = None
    crf: Optional[int] = None
    preset: Optional[str] = None
    pixel_format: PixelFormat = PixelFormat.YUV420P

    def to_ffmpeg_args(self) -> list[str]:
        """Convert to FFMPEG command arguments."""
        args = ["-c:v", self.codec.value]

        if self.crf is not None:
            args.extend(["-crf", str(self.crf)])
        elif self.bitrate:
            args.extend(["-b:v", self.bitrate])

        if self.preset:
            args.extend(["-preset", self.preset])

        args.extend(["-pix_fmt", self.pixel_format.value])

        return args


class AudioFormat(BaseModel):
    """Audio format specification."""
    codec: AudioCodec = AudioCodec.AAC
    bitrate: Optional[str] = None
    sample_rate: Optional[int] = None
    channels: Optional[int] = None

    def to_ffmpeg_args(self) -> list[str]:
        """Convert to FFMPEG command arguments."""
        args = ["-c:a", self.codec.value]

        if self.bitrate:
            args.extend(["-b:a", self.bitrate])

        if self.sample_rate:
            args.extend(["-ar", str(self.sample_rate)])

        if self.channels:
            args.extend(["-ac", str(self.channels)])

        return args


class OutputFormat(BaseModel):
    """Combined output format specification."""
    container: ContainerFormat = ContainerFormat.MP4
    video: Optional[VideoFormat] = None
    audio: Optional[AudioFormat] = None

    def to_ffmpeg_args(self) -> list[str]:
        """Convert to FFMPEG command arguments."""
        args = ["-f", self.container.value]

        if self.video:
            args.extend(self.video.to_ffmpeg_args())

        if self.audio:
            args.extend(self.audio.to_ffmpeg_args())

        return args


# Preset configurations
QUALITY_PRESETS = {
    "draft": OutputFormat(
        video=VideoFormat(codec=VideoCodec.H264, crf=28, preset="ultrafast"),
        audio=AudioFormat(codec=AudioCodec.AAC, bitrate="96k"),
    ),
    "standard": OutputFormat(
        video=VideoFormat(codec=VideoCodec.H264, crf=23, preset="medium"),
        audio=AudioFormat(codec=AudioCodec.AAC, bitrate="128k"),
    ),
    "high": OutputFormat(
        video=VideoFormat(codec=VideoCodec.H264, crf=18, preset="slow"),
        audio=AudioFormat(codec=AudioCodec.AAC, bitrate="256k"),
    ),
    "lossless": OutputFormat(
        video=VideoFormat(codec=VideoCodec.H264, crf=0, preset="veryslow"),
        audio=AudioFormat(codec=AudioCodec.FLAC),
    ),
}

WEB_PRESETS = {
    "web_optimized": OutputFormat(
        container=ContainerFormat.MP4,
        video=VideoFormat(codec=VideoCodec.H264, crf=23, preset="medium"),
        audio=AudioFormat(codec=AudioCodec.AAC, bitrate="128k"),
    ),
    "youtube": OutputFormat(
        container=ContainerFormat.MP4,
        video=VideoFormat(codec=VideoCodec.H264, crf=18, preset="slow"),
        audio=AudioFormat(codec=AudioCodec.AAC, bitrate="192k"),
    ),
    "twitter": OutputFormat(
        container=ContainerFormat.MP4,
        video=VideoFormat(codec=VideoCodec.H264, crf=23, preset="medium"),
        audio=AudioFormat(codec=AudioCodec.AAC, bitrate="128k"),
    ),
}
