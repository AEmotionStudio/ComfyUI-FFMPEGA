# coding: utf-8
"""Single-image 3D view synthesis widgets.

Extracted verbatim from FFMPEGAgentNode.INPUT_TYPES. The text is preserved
exactly because ComfyUI restores saved workflows by widget *position* — see
tests/test_widget_order.py, which pins the emitted order.

Each function is called once per INPUT_TYPES() call, so dropdowns that read
the filesystem (LoRA lists, expression presets) stay dynamic.
"""

from __future__ import annotations



def sharp() -> dict:
    """Advanced: SHARP (3D Gaussian View Synthesis)."""
    return {
        "sharp_trajectory": (["rotate_forward", "swipe", "shake", "rotate"], {
            "default": "rotate_forward",
            "tooltip": "Camera trajectory type for SHARP 3D view synthesis (used in 'sharp' no_llm_mode). "
                       "'rotate_forward' = orbit with zoom, 'swipe' = left-to-right, "
                       "'shake' = horizontal + vertical, 'rotate' = full orbit.",
        }),
        "sharp_num_frames": ("INT", {
            "default": 60,
            "min": 10,
            "max": 300,
            "tooltip": "Number of frames in the SHARP trajectory video (used in 'sharp' no_llm_mode). "
                       "More frames = smoother/longer video.",
        }),
        "sharp_max_disparity": ("FLOAT", {
            "default": 0.08,
            "min": 0.01,
            "max": 0.5,
            "step": 0.01,
            "tooltip": "Lateral camera movement range for SHARP (used in 'sharp' no_llm_mode). "
                       "Higher = wider camera sweep.",
        }),
        "sharp_max_zoom": ("FLOAT", {
            "default": 0.15,
            "min": 0.0,
            "max": 1.0,
            "step": 0.05,
            "tooltip": "Zoom intensity for SHARP camera trajectory (used in 'sharp' no_llm_mode). "
                       "Higher = more forward/backward motion.",
        }),
        "sharp_save_ply": (["false", "true"], {
            "default": "false",
            "tooltip": "Export the 3D Gaussian splat as a .ply file (used in 'sharp' no_llm_mode). "
                       "PLY files are compatible with Luma, Nerfstudio, and other 3DGS viewers. "
                       "Saved to the standard outputs folder.",
        }),
        "sharp_device": (["auto", "cuda", "cpu"], {
            "default": "auto",
            "tooltip": "Device for SHARP inference (used in 'sharp' no_llm_mode). "
                       "Prediction works on all devices; video rendering requires CUDA.",
        }),
    }
