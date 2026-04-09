"""ComfyUI node definitions for FFMPEGA."""

import logging

_log = logging.getLogger("FFMPEGA")

# All node modules require torch (provided by ComfyUI runtime).
# Each import is guarded individually so a broken module doesn't
# hide all other nodes.  See bugbot_journal.md 2026-04-09.

# Node class mappings for ComfyUI
NODE_CLASS_MAPPINGS = {}
NODE_DISPLAY_NAME_MAPPINGS = {}

# --- Core nodes (each guarded independently) ---

try:
    from .agent_node import FFMPEGAgentNode
    NODE_CLASS_MAPPINGS["FFMPEGAgent"] = FFMPEGAgentNode
    NODE_DISPLAY_NAME_MAPPINGS["FFMPEGAgent"] = "FFMPEG Agent"
except ImportError as e:
    _log.warning("[FFMPEGA] Node FFMPEGAgent unavailable: %s", e)

try:
    from .frame_extract_node import FrameExtractNode
    NODE_CLASS_MAPPINGS["FFMPEGAFrameExtract"] = FrameExtractNode
    NODE_DISPLAY_NAME_MAPPINGS["FFMPEGAFrameExtract"] = "Frame Extract (FFMPEGA)"
except ImportError as e:
    _log.warning("[FFMPEGA] Node FFMPEGAFrameExtract unavailable: %s", e)

try:
    from .load_image_path_node import LoadImagePathNode
    NODE_CLASS_MAPPINGS["FFMPEGALoadImagePath"] = LoadImagePathNode
    NODE_DISPLAY_NAME_MAPPINGS["FFMPEGALoadImagePath"] = "Load Image Path (FFMPEGA)"
except ImportError as e:
    _log.warning("[FFMPEGA] Node FFMPEGALoadImagePath unavailable: %s", e)

try:
    from .load_video_path_node import LoadVideoPathNode
    NODE_CLASS_MAPPINGS["FFMPEGALoadVideoPath"] = LoadVideoPathNode
    NODE_DISPLAY_NAME_MAPPINGS["FFMPEGALoadVideoPath"] = "Load Video Path (FFMPEGA)"
except ImportError as e:
    _log.warning("[FFMPEGA] Node FFMPEGALoadVideoPath unavailable: %s", e)

try:
    from .load_mask_video_node import LoadMaskVideoNode
    NODE_CLASS_MAPPINGS["FFMPEGALoadMaskVideo"] = LoadMaskVideoNode
    NODE_DISPLAY_NAME_MAPPINGS["FFMPEGALoadMaskVideo"] = "Load Mask Video (FFMPEGA)"
except ImportError as e:
    _log.warning("[FFMPEGA] Node FFMPEGALoadMaskVideo unavailable: %s", e)

try:
    from .text_input_node import TextInputNode
    NODE_CLASS_MAPPINGS["FFMPEGATextInput"] = TextInputNode
    NODE_DISPLAY_NAME_MAPPINGS["FFMPEGATextInput"] = "FFMPEGA Text"
except ImportError as e:
    _log.warning("[FFMPEGA] Node FFMPEGATextInput unavailable: %s", e)

try:
    from .save_video_node import SaveVideoNode
    NODE_CLASS_MAPPINGS["FFMPEGASaveVideo"] = SaveVideoNode
    NODE_DISPLAY_NAME_MAPPINGS["FFMPEGASaveVideo"] = "Save Video (FFMPEGA)"
except ImportError as e:
    _log.warning("[FFMPEGA] Node FFMPEGASaveVideo unavailable: %s", e)

try:
    from .save_image_node import SaveImageNode
    NODE_CLASS_MAPPINGS["FFMPEGASaveImage"] = SaveImageNode
    NODE_DISPLAY_NAME_MAPPINGS["FFMPEGASaveImage"] = "Save Image (FFMPEGA)"
except ImportError as e:
    _log.warning("[FFMPEGA] Node FFMPEGASaveImage unavailable: %s", e)

try:
    from .media_bridge_node import MediaBridgeNode
    NODE_CLASS_MAPPINGS["FFMPEGAMediaBridge"] = MediaBridgeNode
    NODE_DISPLAY_NAME_MAPPINGS["FFMPEGAMediaBridge"] = "Media Bridge (FFMPEGA)"
except ImportError as e:
    _log.warning("[FFMPEGA] Node FFMPEGAMediaBridge unavailable: %s", e)

try:
    from .effects_node import FFMPEGAEffectsNode
    NODE_CLASS_MAPPINGS["FFMPEGAEffects"] = FFMPEGAEffectsNode
    NODE_DISPLAY_NAME_MAPPINGS["FFMPEGAEffects"] = "FFMPEGA Effects Builder"
except ImportError as e:
    _log.warning("[FFMPEGA] Node FFMPEGAEffects unavailable: %s", e)

try:
    from .shader_overlay_node import ShaderOverlayNode
    NODE_CLASS_MAPPINGS["FFMPEGAShaderOverlay"] = ShaderOverlayNode
    NODE_DISPLAY_NAME_MAPPINGS["FFMPEGAShaderOverlay"] = "Shader Overlay (FFMPEGA)"
except ImportError as e:
    _log.warning("[FFMPEGA] Node FFMPEGAShaderOverlay unavailable: %s", e)

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
    "LoadMaskVideoNode",
    "SaveVideoNode",
    "SaveImageNode",
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
