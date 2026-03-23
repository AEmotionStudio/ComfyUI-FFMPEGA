# coding: utf-8
"""SCAIL Pose extraction — vendored from Kijai's ComfyUI-SCAIL-Pose.

This package provides pose extraction and rendering functionality
for SCAIL character animation, without requiring external ComfyUI nodes.

Pipeline stages:
1. YOLO detection → bounding boxes (ONNX)
2. ViTPose keypoint estimation → 2D/3D joints (ONNX)  
3. NLF 3D pose rendering → cylinder specs
4. PyTorch ray-marching renderer → skeleton images
5. DWPose face/hand overlay → final skeleton render
"""

from .nlf_render import (
    render_nlf_as_images,
    render_multi_nlf_as_images,
    intrinsic_matrix_from_field_of_view,
    process_data_to_COCO_format,
)
from .render_torch import render_whole

__all__ = [
    "render_nlf_as_images",
    "render_multi_nlf_as_images", 
    "render_whole",
    "intrinsic_matrix_from_field_of_view",
    "process_data_to_COCO_format",
]
