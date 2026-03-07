"""
ComfyUI-FFMPEGA: Intelligent FFMPEG Agent for ComfyUI

Transform natural language video editing prompts into precise, automated
video transformations using AI-powered pipeline generation.

Example usage:
    - "Make this video 720p and add a cinematic letterbox"
    - "Speed up 2x but keep the audio pitch normal"
    - "Create a vintage VHS look with grain and color shift"
"""

__version__ = "2.13.0"  
__author__ = "Æmotion Studio"

# Import node mappings for ComfyUI
# Guarded so the package can be imported standalone (e.g. during pytest)
try:
    from .nodes import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS
except ImportError:
    NODE_CLASS_MAPPINGS = {}
    NODE_DISPLAY_NAME_MAPPINGS = {}

# Web directory for custom JavaScript (relative to this module)
WEB_DIRECTORY = "./js"

# Register custom API routes (video preview, metadata endpoints)
try:
    from . import server as _server  # noqa: F401
except Exception:
    pass

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

    return issues


# Run dependency check on import
_dependency_issues = check_dependencies()
if _dependency_issues:
    print("=" * 50)
    print("FFMPEGA: Missing dependencies detected")
    print("=" * 50)
    for issue in _dependency_issues:
        print(f"  - {issue}")
    print("=" * 50)

# Clean up any leftover vision frames from prior crashes / early terminations
try:
    from .mcp.tools import cleanup_vision_frames as _cleanup_frames

    _cleanup_frames()
    del _cleanup_frames
except Exception:
    pass


def _check_optional_deps():
    """Log notices for missing optional AI features."""
    missing = []
    try:
        import sam3  # noqa: F401
    except ImportError:
        missing.append(
            "SAM3 (auto_mask): pip install --no-deps "
            "git+https://github.com/facebookresearch/sam3.git"
        )
    if missing:
        print("[FFMPEGA] Optional AI features not installed:")
        for m in missing:
            print(f"  → {m}")


_check_optional_deps()
