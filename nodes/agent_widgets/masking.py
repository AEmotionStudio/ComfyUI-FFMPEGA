# coding: utf-8
"""Segmentation, matting and background-removal widgets.

Extracted verbatim from FFMPEGAgentNode.INPUT_TYPES. The text is preserved
exactly because ComfyUI restores saved workflows by widget *position* — see
tests/test_widget_order.py, which pins the emitted order.

Each function is called once per INPUT_TYPES() call, so dropdowns that read
the filesystem (LoRA lists, expression presets) stay dynamic.
"""

from __future__ import annotations



def sam3() -> dict:
    """Advanced: SAM3."""
    return {
        "sam3_max_objects": ("INT", {
            "default": 2,
            "min": 1,
            "max": 20,
            "step": 1,
            "tooltip": "Maximum number of objects SAM3 will track per frame. Lower values reduce VRAM usage. Objects are ranked by detection confidence — lowest-confidence detections are dropped first.",
        }),
        "sam3_det_threshold": ("FLOAT", {
            "default": 0.70,
            "min": 0.0,
            "max": 1.0,
            "step": 0.05,
            "tooltip": "Minimum detection confidence for SAM3 to track a new object (0.0–1.0). Higher values = fewer objects tracked = less VRAM. Default 0.7 filters out low-confidence detections.",
        }),
        "mask_output_type": (["black_white", "colored_overlay"], {
            "default": "black_white",
            "tooltip": "Mask preview output format. 'black_white' outputs a raw B&W mask video (white = detected object) for use in external compositing. 'colored_overlay' composites colored SAM3-style regions + contours onto the video.",
        }),
    }

def sam3_premask() -> dict:
    """Advanced: SAM3 Pre-Masking for No-LLM Modes."""
    return {
        "use_sam3": ("BOOLEAN", {
            "default": False,
            "label_on": "SAM3 On",
            "label_off": "SAM3 Off",
            "tooltip": "Enable SAM3 pre-masking for no-LLM modes. When ON, the prompt text is used as a SAM3 target "
                       "to mask specific objects before the effect runs. The effect is then composited onto the original "
                       "via the mask. Works with: lip_sync, animate_portrait, marigold, normalcrafter, video_depth, "
                       "flux_klein, minimax_remover, ai_upscale, rembg, onion_skin, comparison.",
        }),
    }

def rembg() -> dict:
    """Advanced: Rembg Background Removal."""
    return {
        "rembg_model": (["bria-rmbg", "birefnet-general", "birefnet-general-lite", "isnet-general-use", "u2net", "silueta"], {
            "default": "bria-rmbg",
            "tooltip": "Rembg model (used in 'rembg' no_llm_mode). "
                       "'bria-rmbg' = BRIA RMBG (SotA quality, recommended). "
                       "'birefnet-general' = BiRefNet high quality. "
                       "'birefnet-general-lite' = BiRefNet fast. "
                       "'isnet-general-use' = ISNet general. "
                       "'u2net' = U²-Net classic. "
                       "'silueta' = Silueta (fastest, lightweight).",
        }),
        "rembg_background": (["transparent", "green", "black", "white", "blue"], {
            "default": "transparent",
            "tooltip": "Background replacement (used in 'rembg' no_llm_mode). "
                       "'transparent' = alpha channel (outputs VP9/WebM). "
                       "'green' = green screen for compositing. "
                       "Other colors fill the background with a solid color.",
        }),
    }

def matanyone2() -> dict:
    """Advanced: MatAnyone2 Video Matting."""
    return {
        "matting_output": (["foreground", "alpha", "both", "green_screen"], {
            "default": "foreground",
            "tooltip": "MatAnyone2 output type (used in 'video_matting' no_llm_mode). "
                       "'foreground' composites subject on chosen background color. "
                       "'alpha' outputs grayscale alpha matte video. "
                       "'both' outputs foreground + alpha as separate videos. "
                       "'green_screen' is an alias for foreground with green background.",
        }),
        "matting_background": (["green", "black", "white", "blue"], {
            "default": "green",
            "tooltip": "Background color for MatAnyone2 foreground output (used in 'video_matting' no_llm_mode). "
                       "Choose a solid color for compositing.",
        }),
        "matting_max_size": ("INT", {
            "default": 0,
            "min": 0,
            "max": 4096,
            "step": 64,
            "tooltip": "Resolution cap for MatAnyone2 processing (used in 'video_matting' no_llm_mode). "
                       "0 = no limit (process at original resolution). "
                       "Set to e.g. 512 or 720 to reduce VRAM usage on high-res videos.",
        }),
    }
