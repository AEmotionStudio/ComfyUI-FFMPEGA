# coding: utf-8
"""LivePortrait expression widgets.

Extracted verbatim from FFMPEGAgentNode.INPUT_TYPES. The text is preserved
exactly because ComfyUI restores saved workflows by widget *position* — see
tests/test_widget_order.py, which pins the emitted order.

Each function is called once per INPUT_TYPES() call, so dropdowns that read
the filesystem (LoRA lists, expression presets) stay dynamic.
"""

from __future__ import annotations

from ._helpers import get_expression_presets as _get_expression_presets


def expression_controls() -> dict:
    """Advanced: LivePortrait expression controls."""
    return {
        "lp_rotate_pitch": ("FLOAT", {
            "default": 0.0, "min": -20.0, "max": 20.0, "step": 0.5,
            "tooltip": "Head pitch (nod up/down). Only for animate_portrait mode.",
        }),
        "lp_rotate_yaw": ("FLOAT", {
            "default": 0.0, "min": -20.0, "max": 20.0, "step": 0.5,
            "tooltip": "Head yaw (turn left/right). Only for animate_portrait mode.",
        }),
        "lp_rotate_roll": ("FLOAT", {
            "default": 0.0, "min": -20.0, "max": 20.0, "step": 0.5,
            "tooltip": "Head roll (tilt left/right). Only for animate_portrait mode.",
        }),
        "lp_blink": ("FLOAT", {
            "default": 0.0, "min": -20.0, "max": 5.0, "step": 0.5,
            "tooltip": "Eye blink (negative=close, positive=open). Only for animate_portrait mode.",
        }),
        "lp_eyebrow": ("FLOAT", {
            "default": 0.0, "min": -10.0, "max": 15.0, "step": 0.5,
            "tooltip": "Eyebrow raise/lower. Only for animate_portrait mode.",
        }),
        "lp_wink": ("FLOAT", {
            "default": 0.0, "min": 0.0, "max": 25.0, "step": 0.5,
            "tooltip": "Wink intensity. Only for animate_portrait mode.",
        }),
        "lp_pupil_x": ("FLOAT", {
            "default": 0.0, "min": -15.0, "max": 15.0, "step": 0.5,
            "tooltip": "Pupil horizontal (negative=left). Only for animate_portrait mode.",
        }),
        "lp_pupil_y": ("FLOAT", {
            "default": 0.0, "min": -15.0, "max": 15.0, "step": 0.5,
            "tooltip": "Pupil vertical (negative=up). Only for animate_portrait mode.",
        }),
        "lp_aaa": ("FLOAT", {
            "default": 0.0, "min": -30.0, "max": 120.0, "step": 1.0,
            "tooltip": "Mouth open (aaa shape). Only for animate_portrait mode.",
        }),
        "lp_eee": ("FLOAT", {
            "default": 0.0, "min": -20.0, "max": 15.0, "step": 0.5,
            "tooltip": "Mouth eee shape. Only for animate_portrait mode.",
        }),
        "lp_woo": ("FLOAT", {
            "default": 0.0, "min": -20.0, "max": 15.0, "step": 0.5,
            "tooltip": "Mouth woo/pucker shape. Only for animate_portrait mode.",
        }),
        "lp_smile": ("FLOAT", {
            "default": 0.0, "min": -0.3, "max": 1.3, "step": 0.05,
            "tooltip": "Smile intensity. Only for animate_portrait mode.",
        }),
        "lp_retargeting_eyes": ("FLOAT", {
            "default": 1.0, "min": 0.0, "max": 1.0, "step": 0.05,
            "tooltip": "Eye retargeting (0=ignore driver eyes, 1=full). Only for animate_portrait mode.",
        }),
        "lp_retargeting_mouth": ("FLOAT", {
            "default": 1.0, "min": 0.0, "max": 1.0, "step": 0.05,
            "tooltip": "Mouth retargeting (0=ignore driver mouth, 1=full). Only for animate_portrait mode.",
        }),
        "lp_crop_factor": ("FLOAT", {
            "default": 1.6, "min": 1.0, "max": 3.0, "step": 0.1,
            "tooltip": "Face crop expansion (larger=more context). Only for animate_portrait mode.",
        }),
        "lp_expression_preset": (["none"] + _get_expression_presets(), {
            "default": "none",
            "tooltip": "Load a saved expression preset. Overrides expression sliders with stored values. "
                       "Only for animate_portrait mode.",
        }),
        "lp_save_expression": ("STRING", {
            "default": "",
            "multiline": False,
            "placeholder": "Enter name to save current sliders",
            "tooltip": "Type a preset name and run to save current expression slider values. "
                       "Only for animate_portrait mode.",
        }),
    }

def expression_transfer() -> dict:
    """Advanced: LivePortrait expression transfer."""
    return {
        "lp_sample_image": ("STRING", {
            "default": "",
            "multiline": False,
            "placeholder": "Path to face image for expression transfer",
            "tooltip": "Sample face image whose expression will be transferred to the source. "
                       "Only for animate_portrait mode.",
        }),
        "lp_sample_ratio": ("FLOAT", {
            "default": 1.0, "min": 0.0, "max": 1.0, "step": 0.05,
            "tooltip": "Expression transfer blend ratio (0=source expression, 1=full sample expression). "
                       "Only for animate_portrait mode.",
        }),
        "lp_sample_parts": (["all", "mouth_only", "eyes_only", "rotation_only"], {
            "default": "all",
            "tooltip": "Which parts to transfer: all, mouth_only, eyes_only, or rotation_only. "
                       "Only for animate_portrait mode.",
        }),
    }
