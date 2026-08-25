"""Video analysis and format handling."""

from .analyzer import VideoAnalyzer, VideoMetadata
from .formats import VideoFormat, AudioFormat, ContainerFormat

__all__ = [
    "VideoAnalyzer",
    "VideoMetadata",
    "VideoFormat",
    "AudioFormat",
    "ContainerFormat",
]

# encode_opts / metadata are imported lazily by callers: they pull in torch,
# which must not become an import-time cost for `core.video.analyzer` users.
