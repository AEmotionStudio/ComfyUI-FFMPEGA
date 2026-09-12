# coding: utf-8
"""Onion-skin and comparison widgets.

Extracted verbatim from FFMPEGAgentNode.INPUT_TYPES. The text is preserved
exactly because ComfyUI restores saved workflows by widget *position* — see
tests/test_widget_order.py, which pins the emitted order.

Each function is called once per INPUT_TYPES() call, so dropdowns that read
the filesystem (LoRA lists, expression presets) stay dynamic.
"""

from __future__ import annotations



def onion_skin() -> dict:
    """Advanced: Onion Skin."""
    return {
        "onion_blend_mode": (["screen", "normal", "addition", "difference", "multiply", "overlay", "softlight"], {
            "default": "screen",
            "tooltip": "Blend mode for onion skin ghosting (used in 'onion_skin' no_llm_mode). "
                       "'screen' = classic light-table look. "
                       "'addition' = bright additive glow. "
                       "'difference' = motion-diff visualization.",
        }),
        "onion_opacity": ("FLOAT", {
            "default": 0.5,
            "min": 0.0,
            "max": 1.0,
            "step": 0.05,
            "tooltip": "Ghost trail opacity (used in 'onion_skin' no_llm_mode). "
                       "0.0 = invisible, 1.0 = fully opaque.",
        }),
        "onion_decay": ("FLOAT", {
            "default": 0.97,
            "min": 0.90,
            "max": 0.999,
            "step": 0.005,
            "tooltip": "Temporal decay rate for ghost trails (used in 'onion_skin' no_llm_mode). "
                       "Higher values = longer, more persistent trails. "
                       "0.90 = very short. 0.97 = medium. 0.999 = long persistence.",
        }),
    }

def comparison() -> dict:
    """Advanced: Comparison."""
    return {
        "comparison_style": (["swipe", "split", "side_by_side", "diagonal", "circular_reveal", "difference"], {
            "default": "swipe",
            "tooltip": "Comparison style (used in 'comparison' no_llm_mode). "
                       "'swipe' = animated divider sweeps left-to-right. "
                       "'split' = static 50/50 with divider line. "
                       "'side_by_side' = full frames side by side. "
                       "'diagonal' = diagonal split. "
                       "'circular_reveal' = expanding circle reveals 'after'. "
                       "'difference' = pixel difference visualization.",
        }),
        "comparison_labels": (["false", "true"], {
            "default": "false",
            "tooltip": "Show Before/After text labels on the comparison output (used in 'comparison' no_llm_mode).",
        }),
        "comparison_label_a": ("STRING", {
            "default": "Before",
            "tooltip": "Label for the main video (left / before) in comparison mode.",
        }),
        "comparison_label_b": ("STRING", {
            "default": "After",
            "tooltip": "Label for the video_a input (right / after) in comparison mode.",
        }),
    }
