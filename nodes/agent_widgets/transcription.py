# coding: utf-8
"""Whisper transcription widgets.

Extracted verbatim from FFMPEGAgentNode.INPUT_TYPES. The text is preserved
exactly because ComfyUI restores saved workflows by widget *position* — see
tests/test_widget_order.py, which pins the emitted order.

Each function is called once per INPUT_TYPES() call, so dropdowns that read
the filesystem (LoRA lists, expression presets) stay dynamic.
"""

from __future__ import annotations



def whisper() -> dict:
    """Advanced: Whisper."""
    return {
        "whisper_device": (["cpu", "gpu"], {
            "default": "cpu",
            "tooltip": "Device for Whisper transcription model. 'gpu' is faster but uses ~3 GB VRAM (frees ComfyUI models first). 'cpu' is slower but avoids VRAM pressure — best for low-VRAM GPUs or intensive workflows.",
        }),
        "whisper_model": (["large-v3", "medium", "small", "base", "tiny"], {
            "default": "large-v3",
            "tooltip": "Whisper model size for transcription. 'large-v3' is most accurate (~3 GB VRAM). Smaller models use less memory: medium (~1.5 GB), small (~1 GB), base (~150 MB), tiny (~75 MB). Models auto-download on first use.",
        }),
    }
