"""ComfyUI node definitions for FFMPEGA."""

from .agent_node import FFMPEGAgentNode
from .frame_extract_node import FrameExtractNode
from .load_image_path_node import LoadImagePathNode
from .load_video_path_node import LoadVideoPathNode
from .text_input_node import TextInputNode
from .save_video_node import SaveVideoNode
from .video_to_path_node import VideoToPathNode
from .effects_node import FFMPEGAEffectsNode

# Node class mappings for ComfyUI
NODE_CLASS_MAPPINGS = {
    "FFMPEGAgent": FFMPEGAgentNode,
    "FFMPEGAFrameExtract": FrameExtractNode,
    "FFMPEGALoadImagePath": LoadImagePathNode,
    "FFMPEGALoadVideoPath": LoadVideoPathNode,
    "FFMPEGASaveVideo": SaveVideoNode,
    "FFMPEGAVideoToPath": VideoToPathNode,
    "FFMPEGATextInput": TextInputNode,
    "FFMPEGAEffects": FFMPEGAEffectsNode,
}

# Display names for nodes
NODE_DISPLAY_NAME_MAPPINGS = {
    "FFMPEGAgent": "FFMPEG Agent",
    "FFMPEGAFrameExtract": "Frame Extract (FFMPEGA)",
    "FFMPEGALoadImagePath": "Load Image Path (FFMPEGA)",
    "FFMPEGALoadVideoPath": "Load Video Path (FFMPEGA)",
    "FFMPEGASaveVideo": "Save Video (FFMPEGA)",
    "FFMPEGAVideoToPath": "Video to Path (FFMPEGA)",
    "FFMPEGATextInput": "FFMPEGA Text",
    "FFMPEGAEffects": "FFMPEGA Effects Builder",
}

# --- LoadLast nodes (merged from ComfyUI-LoadLast) ---
try:
    from ..loadlast import LoadLastImage, LoadLastVideo

    NODE_CLASS_MAPPINGS["LoadLastImage"] = LoadLastImage
    NODE_CLASS_MAPPINGS["LoadLastVideo"] = LoadLastVideo
    NODE_DISPLAY_NAME_MAPPINGS["LoadLastImage"] = "Load Last Image 🔄"
    NODE_DISPLAY_NAME_MAPPINGS["LoadLastVideo"] = "Load Last Video 🎬"
except ImportError:
    import logging
    logging.getLogger("FFMPEGA").debug(
        "[FFMPEGA] LoadLast nodes not available (import error)", exc_info=True
    )

__all__ = [
    "FFMPEGAgentNode",
    "FrameExtractNode",
    "LoadImagePathNode",
    "LoadVideoPathNode",
    "SaveVideoNode",
    "VideoToPathNode",
    "TextInputNode",
    "FFMPEGAEffectsNode",
    "NODE_CLASS_MAPPINGS",
    "NODE_DISPLAY_NAME_MAPPINGS",
]

# Add LoadLast names only if they were successfully imported
if "LoadLastImage" in NODE_CLASS_MAPPINGS:
    __all__.extend(["LoadLastImage", "LoadLastVideo"])
