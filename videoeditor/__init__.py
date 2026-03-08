"""
VideoEditor — interactive NLE video editing node for ComfyUI-FFMPEGA.

Provides trim, split, crop, speed-ramp, volume, text overlay, and
transition editing inside a rich timeline UI on the node canvas.
"""

# Lazy import: VideoEditorNode depends on torch/numpy which are only
# available inside ComfyUI's runtime.  Processing modules can be
# imported independently for testing.
try:
    from .video_editor_node import VideoEditorNode
except ImportError:
    VideoEditorNode = None  # type: ignore[assignment,misc]

__all__ = ["VideoEditorNode"]
