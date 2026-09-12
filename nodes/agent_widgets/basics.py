# coding: utf-8
"""Always-visible widgets and core rendering options.

Extracted verbatim from FFMPEGAgentNode.INPUT_TYPES. The text is preserved
exactly because ComfyUI restores saved workflows by widget *position* — see
tests/test_widget_order.py, which pins the emitted order.

Each function is called once per INPUT_TYPES() call, so dropdowns that read
the filesystem (LoRA lists, expression presets) stay dynamic.
"""

from __future__ import annotations



def connection_inputs() -> dict:
    """Connection inputs (always visible, forceInput)."""
    return {
        "images_a": ("IMAGE", {
            "tooltip": "Video input as image frames (e.g. from Load Video Upload). Connect additional video inputs and more slots appear automatically (images_b, images_c, ...). Used for concat, split screen, and multi-video workflows.",
        }),
        "image_a": ("IMAGE", {
            "tooltip": "Extra image/video input. Connect additional inputs and more slots appear automatically (image_b, image_c, ...). Used for multi-input skills like grid, slideshow, overlay, concat, and split screen.",
        }),
        "audio_a": ("AUDIO", {
            "tooltip": "Audio input. Connect additional audio and more slots appear automatically (audio_b, audio_c, ...). Used for muxing audio into video, lip sync, or for multi-audio skills like concat.",
        }),
        "video_a": ("STRING", {
            "forceInput": True,
            "tooltip": "File path to an extra video for concat, split screen, grid, or xfade. Uses zero extra memory vs tensor inputs. Connect and more slots appear (video_b, video_c, ...). Connect a primitive STRING node or any node that outputs a file path.",
        }),
        "image_path_a": ("STRING", {
            "forceInput": True,
            "tooltip": "File path to an image for overlay, grid, slideshow, or multi-image skills. Uses zero memory vs IMAGE tensor. Connect and more slots appear (image_path_b, image_path_c, ...). Use Load Image Path (FFMPEGA).",
        }),
        "text_a": ("STRING", {
            "forceInput": True,
            "tooltip": "Text input for subtitles, overlays, watermarks, or title cards. Connect an FFMPEGA Text node or any STRING source. More slots appear automatically (text_b, text_c, ...).",
        }),
        "pipeline_json": ("STRING", {
            "forceInput": True,
            "tooltip": "Connect the output from the FFMPEGA Effects Builder node here. The agent will inject the selected effects as hints into your prompt.",
        }),
        "mask_points": ("STRING", {
            "forceInput": True,
            "tooltip": "JSON-encoded point selection data from the Load Image/Video Path node's Point Selector. Guides SAM3 masking with click-to-select points instead of relying on text prompts alone.",
        }),
        "crop_data": ("STRING", {
            "forceInput": True,
            "tooltip": "JSON-encoded crop rectangle from the Load Video Path or Frame Extract node's Crop Selector. Format: {\"x\":N, \"y\":N, \"w\":N, \"h\":N}. Crops the input video before processing.",
        }),
        "mask": ("MASK", {
            "tooltip": (
                "Optional upstream MASK pass-through. When "
                "connected, this binary mask tensor is forwarded "
                "to the mask output for downstream compositing."
            ),
        }),
    }

def basic_options() -> dict:
    """Basic options (always visible)."""
    return {
        "save_output": ("BOOLEAN", {
            "default": False,
            "label_on": "Save to Output",
            "label_off": "Pass Through",
            "tooltip": "When On, saves video and a workflow PNG to the output folder. Turn Off when a downstream Save node handles output to avoid double saves. Note: downstream nodes may re-encode with their own settings (format, quality, resolution), so the final saved file may differ from FFMPEGA's output.",
        }),
        "output_path": ("STRING", {
            "default": "",
            "multiline": False,
            "placeholder": "Output path (optional)",
            "tooltip": "Custom output file or folder path. Leave empty to save to ComfyUI's default output directory.",
        }),
        "ollama_url": ("STRING", {
            "default": "http://localhost:11434",
            "multiline": False,
            "tooltip": "URL of the Ollama server for local LLM inference. Default: http://localhost:11434.",
        }),
        "custom_model": ("STRING", {
            "default": "",
            "multiline": False,
            "placeholder": "Ollama model name (e.g. qwen3:14b)",
            "tooltip": "When 'custom' is selected in llm_model, type the exact Ollama model name here — useful for models the dropdown doesn't list, such as ones on a remote server set via ollama_url.",
        }),
    }

def llm_behavior() -> dict:
    """LLM Behavior (always visible)."""
    return {
        "use_vision": ("BOOLEAN", {
            "default": False,
            "label_on": "Vision On",
            "label_off": "Vision Off",
            "tooltip": "When On, embeds video frames as images for vision-capable models (uses more tokens). When Off, uses numeric color analysis instead (cheaper, works with all models).",
        }),
        "verify_output": ("BOOLEAN", {
            "default": False,
            "label_on": "Verify On",
            "label_off": "Verify Off",
            "tooltip": "When On, the agent inspects the output video after rendering and auto-corrects if it doesn't match intent. Adds one extra LLM call (more tokens/time). Best for complex edits like overlays, color grading, or animations.",
        }),
    }

def advanced_toggle() -> dict:
    """Advanced toggle."""
    return {
        "advanced_options": ("BOOLEAN", {
            "default": False,
            "label_on": "Advanced",
            "label_off": "Simple",
            "tooltip": "Show advanced options: preview, encoding, SAM3/Whisper tuning, FLUX smoothing, MMAudio mode, SAM-Audio model, batch processing, and usage tracking.",
        }),
    }

def rendering() -> dict:
    """Advanced: Rendering."""
    return {
        "preview_mode": ("BOOLEAN", {
            "default": False,
            "label_on": "Preview",
            "label_off": "Full Render",
            "tooltip": "When enabled, generates a quick low-res preview (480p, first 10 seconds) instead of a full render.",
        }),
        "subtitle_path": ("STRING", {
            "default": "",
            "multiline": False,
            "placeholder": "Path to .srt or .ass subtitle file",
            "tooltip": "Direct path to a subtitle file (.srt or .ass). Alternative to using text_a with subtitle mode.",
        }),
        "crf": ("INT", {
            "default": -1,
            "min": -1,
            "max": 51,
            "step": 1,
            "tooltip": "Override CRF (Constant Rate Factor) for output quality. 0 = lossless, 23 = default, 51 = worst. Set to -1 to use quality_preset value.",
        }),
        "encoding_preset": (["auto", "ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow"], {
            "default": "auto",
            "tooltip": "Override x264/x265 encoding speed preset. Slower = better compression. 'auto' uses the quality_preset value.",
        }),
    }
