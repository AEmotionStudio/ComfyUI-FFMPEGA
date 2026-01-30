"""MCP Server for FFMPEGA.

Provides Model Context Protocol tools for interacting with
FFMPEG command database and video processing capabilities.
"""

from .server import FFMPEGAMCPServer
from .tools import (
    analyze_video,
    list_skills,
    build_pipeline,
    execute_pipeline,
)

__all__ = [
    "FFMPEGAMCPServer",
    "analyze_video",
    "list_skills",
    "build_pipeline",
    "execute_pipeline",
]
