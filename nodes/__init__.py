"""ComfyUI node definitions for FFMPEGA."""

from .agent_node import FFMPEGAgentNode
from .frame_extract_node import FrameExtractNode

# Node class mappings for ComfyUI
NODE_CLASS_MAPPINGS = {
    "FFMPEGAgent": FFMPEGAgentNode,
    "FFMPEGAFrameExtract": FrameExtractNode,
}

# Display names for nodes
NODE_DISPLAY_NAME_MAPPINGS = {
    "FFMPEGAgent": "FFMPEG Agent",
    "FFMPEGAFrameExtract": "Frame Extract (FFMPEGA)",
}

__all__ = [
    "FFMPEGAgentNode",
    "FrameExtractNode",
    "NODE_CLASS_MAPPINGS",
    "NODE_DISPLAY_NAME_MAPPINGS",
]
