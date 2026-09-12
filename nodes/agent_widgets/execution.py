# coding: utf-8
"""Batch processing, usage tracking and download policy widgets.

Extracted verbatim from FFMPEGAgentNode.INPUT_TYPES. The text is preserved
exactly because ComfyUI restores saved workflows by widget *position* — see
tests/test_widget_order.py, which pins the emitted order.

Each function is called once per INPUT_TYPES() call, so dropdowns that read
the filesystem (LoRA lists, expression presets) stay dynamic.
"""

from __future__ import annotations



def batch_processing() -> dict:
    """Advanced: Batch processing."""
    return {
        "batch_mode": ("BOOLEAN", {
            "default": False,
            "label_on": "Batch",
            "label_off": "Single",
            "tooltip": "When enabled, processes all matching videos in video_folder with the same prompt. Uses a single LLM call and applies the pipeline to every file.",
        }),
        "video_folder": ("STRING", {
            "default": "",
            "multiline": False,
            "placeholder": "Folder of videos to batch process",
            "tooltip": "Path to a folder containing videos to batch process. Only used when batch_mode is on.",
        }),
        "file_pattern": (["*.mp4", "*.avi", "*.mov", "*.mkv", "*.webm", "*.mp4 *.mov *.avi", "*.*"], {
            "default": "*.mp4",
            "tooltip": "File pattern to match videos in the folder. '*.mp4 *.mov *.avi' matches multiple formats. '*.*' matches all files. Only used when batch_mode is on.",
        }),
        "max_concurrent": ("INT", {
            "default": 4,
            "min": 1,
            "max": 16,
            "step": 1,
            "tooltip": "Maximum number of videos to process simultaneously in batch mode. Higher values use more CPU/GPU.",
        }),
    }

def usage_tracking() -> dict:
    """Advanced: Usage tracking & downloads."""
    return {
        "track_tokens": ("BOOLEAN", {
            "default": True,
            "label_on": "Track On",
            "label_off": "Track Off",
            "tooltip": "When On, prints token usage summary (prompt tokens, completion tokens, LLM calls) to the console after each run. Useful for monitoring costs with paid APIs.",
        }),
        "log_usage": ("BOOLEAN", {
            "default": False,
            "label_on": "Log On",
            "label_off": "Log Off",
            "tooltip": "When On, appends a JSON entry to usage_log.jsonl for each run. Useful for tracking cumulative token spend over time.",
        }),
        "allow_model_downloads": ("BOOLEAN", {
            "default": True,
            "label_on": "Downloads On",
            "label_off": "Downloads Off",
            "tooltip": "When On (default), AI models (SAM3, LaMa, Whisper) auto-download on first use. Turn Off to prevent any automatic downloads — runs requiring a missing model will fail with a clear message and a link to download manually.",
        }),
    }
