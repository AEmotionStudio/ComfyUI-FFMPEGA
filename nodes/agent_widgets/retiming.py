# coding: utf-8
"""Frame-rate detection and re-timing widgets.

Extracted verbatim from FFMPEGAgentNode.INPUT_TYPES. The text is preserved
exactly because ComfyUI restores saved workflows by widget *position* — see
tests/test_widget_order.py, which pins the emitted order.

Each function is called once per INPUT_TYPES() call, so dropdowns that read
the filesystem (LoRA lists, expression presets) stay dynamic.
"""

from __future__ import annotations



def phyfps() -> dict:
    """Advanced: PhyFPS (Visual Chronometer)."""
    return {
        "phyfps_action": (["analyze_only", "correct"], {
            "default": "analyze_only",
            "tooltip": "Action for PhyFPS mode (used in 'phyfps' no_llm_mode). "
                       "'analyze_only' predicts the physical frame rate without modifying the video. "
                       "'correct' re-times the video so playback speed matches the detected PhyFPS.",
        }),
    }
