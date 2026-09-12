# coding: utf-8
"""Identity-preserving talking-head widgets.

Extracted verbatim from FFMPEGAgentNode.INPUT_TYPES. The text is preserved
exactly because ComfyUI restores saved workflows by widget *position* — see
tests/test_widget_order.py, which pins the emitted order.

Each function is called once per INPUT_TYPES() call, so dropdowns that read
the filesystem (LoRA lists, expression presets) stay dynamic.
"""

from __future__ import annotations



def dreamid_omni() -> dict:
    """Advanced: DreamID-Omni (WIP)."""
    return {
        "use_dreamid_omni": ("BOOLEAN", {
            "default": False,
            "label_on": "DreamID On ⚠️ WIP",
            "label_off": "DreamID Off",
            "tooltip": "⚠️ EXPERIMENTAL / WORK IN PROGRESS — Quality may be poor on low-VRAM GPUs. "
                       "Enable DreamID-Omni for identity-preserving video generation with speech. "
                       "Generates video where subjects speak with their voice and face identity preserved. "
                       "Heavy model (~15+ GB VRAM). OFF by default for low-VRAM GPUs. "
                       "Requires face image(s) on image_a and reference audio on audio_a.",
        }),
        "dreamid_precision": (["auto", "fp8", "bf16"], {
            "default": "auto",
            "tooltip": "DreamID-Omni model precision. "
                       "'auto' = prefer FP8 if available (~12 GB), else BF16 (~23 GB). "
                       "'fp8' = FP8 quantized (fastest, lowest VRAM, requires converted checkpoint). "
                       "'bf16' = BFloat16 (best quality, higher VRAM).",
        }),
        "dreamid_resolution": (["auto", "992x512", "1280x704"], {
            "default": "auto",
            "tooltip": "DreamID-Omni output resolution (used in 'dreamid_omni' no_llm_mode). "
                       "'auto' = pick based on available VRAM (~30+ GB → 1280x704, else 992x512). "
                       "'992x512' = standard quality, lower VRAM (~20 GB). "
                       "'1280x704' = high quality, higher VRAM (~30+ GB).",
        }),
        "dreamid_steps": ("INT", {
            "default": 50,
            "min": 1,
            "max": 100,
            "step": 1,
            "tooltip": "Number of diffusion sampling steps for DreamID-Omni. Default 50. Lower = faster but lower quality.",
        }),
        "dreamid_seed": ("INT", {
            "default": 100,
            "min": 0,
            "max": 2147483647,
            "step": 1,
            "tooltip": "Random seed for DreamID-Omni. Set a fixed value for reproducible results.",
        }),
        "dreamid_solver": (["unipc", "euler", "dpm++"], {
            "default": "unipc",
            "tooltip": "Solver for DreamID-Omni denoising. "
                       "'unipc' = UniPC predictor-corrector (default, fast). "
                       "'euler' = Flow Match Euler. "
                       "'dpm++' = DPM++ Multistep.",
        }),
        "dreamid_video_cfg": ("FLOAT", {
            "default": 3.0,
            "min": 1.0,
            "max": 10.0,
            "step": 0.5,
            "tooltip": "Video classifier-free guidance scale. Higher = stronger prompt adherence. Default 3.0.",
        }),
        "dreamid_video_ref_cfg": ("FLOAT", {
            "default": 1.5,
            "min": 0.0,
            "max": 5.0,
            "step": 0.5,
            "tooltip": "Video reference (face identity) guidance scale. Higher = stronger identity preservation. Default 1.5.",
        }),
        "dreamid_audio_cfg": ("FLOAT", {
            "default": 4.0,
            "min": 1.0,
            "max": 10.0,
            "step": 0.5,
            "tooltip": "Audio classifier-free guidance scale. Higher = stronger audio guidance. Default 4.0.",
        }),
        "dreamid_audio_ref_cfg": ("FLOAT", {
            "default": 2.0,
            "min": 0.0,
            "max": 5.0,
            "step": 0.5,
            "tooltip": "Audio reference guidance scale. Higher = stronger voice identity preservation. Default 2.0.",
        }),
    }
