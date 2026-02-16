"""ComfyUI node definitions for FFMPEGA."""

from .agent_node import FFMPEGAgentNode
from .frame_extract_node import FrameExtractNode
from .load_image_path_node import LoadImagePathNode
from .load_video_path_node import LoadVideoPathNode
from .save_video_node import SaveVideoNode
from .video_to_path_node import VideoToPathNode

# Node class mappings for ComfyUI
NODE_CLASS_MAPPINGS = {
    "FFMPEGAgent": FFMPEGAgentNode,
    "FFMPEGAFrameExtract": FrameExtractNode,
    "FFMPEGALoadImagePath": LoadImagePathNode,
    "FFMPEGALoadVideoPath": LoadVideoPathNode,
    "FFMPEGASaveVideo": SaveVideoNode,
    "FFMPEGAVideoToPath": VideoToPathNode,
}

# Display names for nodes
NODE_DISPLAY_NAME_MAPPINGS = {
    "FFMPEGAgent": "FFMPEG Agent",
    "FFMPEGAFrameExtract": "Frame Extract (FFMPEGA)",
    "FFMPEGALoadImagePath": "Load Image Path (FFMPEGA)",
    "FFMPEGALoadVideoPath": "Load Video Path (FFMPEGA)",
    "FFMPEGASaveVideo": "Save Video (FFMPEGA)",
    "FFMPEGAVideoToPath": "Video to Path (FFMPEGA)",
}

__all__ = [
    "FFMPEGAgentNode",
    "FrameExtractNode",
    "LoadImagePathNode",
    "LoadVideoPathNode",
    "SaveVideoNode",
    "VideoToPathNode",
    "NODE_CLASS_MAPPINGS",
    "NODE_DISPLAY_NAME_MAPPINGS",
]
