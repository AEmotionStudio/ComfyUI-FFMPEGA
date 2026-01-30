"""
ComfyUI-FFMPEGA: Intelligent FFMPEG Agent for ComfyUI

Transform natural language video editing prompts into precise, automated
video transformations using AI-powered pipeline generation.

Example usage:
    - "Make this video 720p and add a cinematic letterbox"
    - "Speed up 2x but keep the audio pitch normal"
    - "Create a vintage VHS look with grain and color shift"
"""

__version__ = "1.0.0"
__author__ = "FFMPEGA Team"

# Import node mappings for ComfyUI
from .nodes import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS

# Add additional utility nodes
from .nodes.preview_node import VideoInfoNode, FrameExtractNode
from .nodes.batch_node import BatchStatusNode

# Extend node mappings
NODE_CLASS_MAPPINGS.update({
    "VideoInfo": VideoInfoNode,
    "FrameExtract": FrameExtractNode,
    "BatchStatus": BatchStatusNode,
})

NODE_DISPLAY_NAME_MAPPINGS.update({
    "VideoInfo": "Video Info",
    "FrameExtract": "Frame Extract",
    "BatchStatus": "Batch Status",
})

# Web directory for custom UI widgets
WEB_DIRECTORY = "./web"

__all__ = [
    "NODE_CLASS_MAPPINGS",
    "NODE_DISPLAY_NAME_MAPPINGS",
    "WEB_DIRECTORY",
]


def check_dependencies():
    """Check if required dependencies are available."""
    import shutil

    issues = []

    # Check FFMPEG
    if not shutil.which("ffmpeg"):
        issues.append("FFMPEG not found in PATH. Please install FFMPEG.")

    if not shutil.which("ffprobe"):
        issues.append("FFprobe not found in PATH. Please install FFMPEG.")

    # Check optional dependencies
    try:
        import httpx
    except ImportError:
        issues.append("httpx not installed. Run: pip install httpx")

    try:
        import pydantic
    except ImportError:
        issues.append("pydantic not installed. Run: pip install pydantic")

    return issues


# Run dependency check on import
_dependency_issues = check_dependencies()
if _dependency_issues:
    print("FFMPEGA Warning - Missing dependencies:")
    for issue in _dependency_issues:
        print(f"  - {issue}")
