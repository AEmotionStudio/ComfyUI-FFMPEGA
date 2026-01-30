"""ComfyUI node definitions for FFMPEGA."""

from .agent_node import FFMPEGAgentNode
from .preview_node import VideoPreviewNode, VideoInfoNode, FrameExtractNode
from .batch_node import BatchProcessorNode, BatchStatusNode

# Node class mappings for ComfyUI
NODE_CLASS_MAPPINGS = {
    "FFMPEGAgent": FFMPEGAgentNode,
    "FFMPEGAPreview": VideoPreviewNode,
    "FFMPEGAVideoInfo": VideoInfoNode,
    "FFMPEGAFrameExtract": FrameExtractNode,
    "FFMPEGABatchProcessor": BatchProcessorNode,
    "FFMPEGABatchStatus": BatchStatusNode,
}

# Display names for nodes
NODE_DISPLAY_NAME_MAPPINGS = {
    "FFMPEGAgent": "FFMPEG Agent",
    "FFMPEGAPreview": "Video Preview (FFMPEGA)",
    "FFMPEGAVideoInfo": "Video Info (FFMPEGA)",
    "FFMPEGAFrameExtract": "Frame Extract (FFMPEGA)",
    "FFMPEGABatchProcessor": "Batch Processor (FFMPEGA)",
    "FFMPEGABatchStatus": "Batch Status (FFMPEGA)",
}

__all__ = [
    "FFMPEGAgentNode",
    "VideoPreviewNode",
    "VideoInfoNode",
    "FrameExtractNode",
    "BatchProcessorNode",
    "BatchStatusNode",
    "NODE_CLASS_MAPPINGS",
    "NODE_DISPLAY_NAME_MAPPINGS",
]
