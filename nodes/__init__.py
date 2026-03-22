"""ComfyUI node definitions for FFMPEGA."""

import logging

from .agent_node import FFMPEGAgentNode
from .frame_extract_node import FrameExtractNode
from .load_image_path_node import LoadImagePathNode
from .load_video_path_node import LoadVideoPathNode
from .text_input_node import TextInputNode
from .save_video_node import SaveVideoNode
from .media_bridge_node import MediaBridgeNode
from .effects_node import FFMPEGAEffectsNode
from .shader_overlay_node import ShaderOverlayNode

# Node class mappings for ComfyUI
NODE_CLASS_MAPPINGS = {
    "FFMPEGAgent": FFMPEGAgentNode,
    "FFMPEGAFrameExtract": FrameExtractNode,
    "FFMPEGALoadImagePath": LoadImagePathNode,
    "FFMPEGALoadVideoPath": LoadVideoPathNode,
    "FFMPEGASaveVideo": SaveVideoNode,
    "FFMPEGAMediaBridge": MediaBridgeNode,
    "FFMPEGATextInput": TextInputNode,
    "FFMPEGAEffects": FFMPEGAEffectsNode,
    "FFMPEGAShaderOverlay": ShaderOverlayNode,
}

# Display names for nodes
NODE_DISPLAY_NAME_MAPPINGS = {
    "FFMPEGAgent": "FFMPEG Agent",
    "FFMPEGAFrameExtract": "Frame Extract (FFMPEGA)",
    "FFMPEGALoadImagePath": "Load Image Path (FFMPEGA)",
    "FFMPEGALoadVideoPath": "Load Video Path (FFMPEGA)",
    "FFMPEGASaveVideo": "Save Video (FFMPEGA)",
    "FFMPEGAMediaBridge": "Media Bridge (FFMPEGA)",
    "FFMPEGATextInput": "FFMPEGA Text",
    "FFMPEGAEffects": "FFMPEGA Effects Builder",
    "FFMPEGAShaderOverlay": "Shader Overlay (FFMPEGA)",
}

# --- LoadLast nodes (merged from ComfyUI-LoadLast) ---
try:
    from ..loadlast import LoadLastImage, LoadLastVideo

    NODE_CLASS_MAPPINGS["LoadLastImage"] = LoadLastImage
    NODE_CLASS_MAPPINGS["LoadLastVideo"] = LoadLastVideo
    NODE_DISPLAY_NAME_MAPPINGS["LoadLastImage"] = "Load Last Image (FFMPEGA)"
    NODE_DISPLAY_NAME_MAPPINGS["LoadLastVideo"] = "Load Last Video (FFMPEGA)"
except ImportError:
    logging.getLogger("FFMPEGA").debug(
        "[FFMPEGA] LoadLast nodes not available (import error)", exc_info=True
    )

# --- Video Editor node ---
try:
    from ..videoeditor import VideoEditorNode
    if VideoEditorNode is None:
        raise ImportError("VideoEditorNode failed to load")

    NODE_CLASS_MAPPINGS["FFMPEGAVideoEditor"] = VideoEditorNode
    NODE_DISPLAY_NAME_MAPPINGS["FFMPEGAVideoEditor"] = "Video Editor (FFMPEGA)"
except ImportError:
    logging.getLogger("FFMPEGA").debug(
        "[FFMPEGA] VideoEditor node not available (import error)", exc_info=True
    )

# --- FacePoke node ---
try:
    from .facepoke_node import FacePokeNode
    if FacePokeNode is None:
        raise ImportError("FacePokeNode failed to load")

    NODE_CLASS_MAPPINGS["FFMPEGAFacePoke"] = FacePokeNode
    NODE_DISPLAY_NAME_MAPPINGS["FFMPEGAFacePoke"] = "Face Poke (FFMPEGA)"
except ImportError:
    logging.getLogger("FFMPEGA").debug(
        "[FFMPEGA] FacePoke node not available (import error)", exc_info=True
    )

__all__ = [
    "FFMPEGAgentNode",
    "FrameExtractNode",
    "LoadImagePathNode",
    "LoadVideoPathNode",
    "SaveVideoNode",
    "MediaBridgeNode",
    "TextInputNode",
    "FFMPEGAEffectsNode",
    "ShaderOverlayNode",
    "NODE_CLASS_MAPPINGS",
    "NODE_DISPLAY_NAME_MAPPINGS",
]

# Add LoadLast names only if they were successfully imported
if "LoadLastImage" in NODE_CLASS_MAPPINGS:
    __all__.extend(["LoadLastImage", "LoadLastVideo"])

# Add VideoEditor name only if successfully imported
if "FFMPEGAVideoEditor" in NODE_CLASS_MAPPINGS:
    __all__.append("FFMPEGAVideoEditor")

# Add FacePoke name only if successfully imported
if "FFMPEGAFacePoke" in NODE_CLASS_MAPPINGS:
    __all__.append("FacePokeNode")

# --- FramePicker node ---
try:
    from .frame_picker_node import FramePickerNode
    if FramePickerNode is None:
        raise ImportError("FramePickerNode failed to load")

    NODE_CLASS_MAPPINGS["FFMPEGAFramePicker"] = FramePickerNode
    NODE_DISPLAY_NAME_MAPPINGS["FFMPEGAFramePicker"] = "Frame Picker (FFMPEGA)"
except ImportError:
    logging.getLogger("FFMPEGA").debug(
        "[FFMPEGA] FramePicker node not available (import error)", exc_info=True
    )

# Add FramePicker name only if successfully imported
if "FFMPEGAFramePicker" in NODE_CLASS_MAPPINGS:
    __all__.append("FramePickerNode")

# --- FaceCam node ---
try:
    from .facecam_node import FaceCamNode
    if FaceCamNode is None:
        raise ImportError("FaceCamNode failed to load")

    NODE_CLASS_MAPPINGS["FFMPEGAFaceCam"] = FaceCamNode
    NODE_DISPLAY_NAME_MAPPINGS["FFMPEGAFaceCam"] = "FaceCam (FFMPEGA)"
except ImportError:
    logging.getLogger("FFMPEGA").debug(
        "[FFMPEGA] FaceCam node not available (import error)", exc_info=True
    )

# Add FaceCam name only if successfully imported
if "FFMPEGAFaceCam" in NODE_CLASS_MAPPINGS:
    __all__.append("FaceCamNode")
