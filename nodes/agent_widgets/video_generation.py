# coding: utf-8
"""Long-form video generation widgets.

Extracted verbatim from FFMPEGAgentNode.INPUT_TYPES. The text is preserved
exactly because ComfyUI restores saved workflows by widget *position* — see
tests/test_widget_order.py, which pins the emitted order.

Each function is called once per INPUT_TYPES() call, so dropdowns that read
the filesystem (LoRA lists, expression presets) stay dynamic.
"""

from __future__ import annotations

import os
import folder_paths  # type: ignore[import-not-found]
from ._helpers import _svi_samplers
from ._helpers import _svi_schedulers


def svi() -> dict:
    """Advanced: SVI 2.0 Pro."""
    return {
        "svi_num_clips": ("INT", {
            "default": 10,
            "min": 1,
            "max": 200,
            "tooltip": "Number of clips to generate (used in 'svi' no_llm_mode). "
                       "Each clip is ~81 frames. More clips = longer video. "
                       "Only used when no_llm_mode = 'svi'.",
        }),
        "svi_height": ("INT", {
            "default": 480,
            "min": 128,
            "max": 1080,
            "step": 16,
            "tooltip": "Video height in pixels (used in 'svi' no_llm_mode). "
                       "Only used when no_llm_mode = 'svi'.",
        }),
        "svi_width": ("INT", {
            "default": 832,
            "min": 128,
            "max": 1920,
            "step": 16,
            "tooltip": "Video width in pixels (used in 'svi' no_llm_mode). "
                       "Only used when no_llm_mode = 'svi'.",
        }),
        "svi_fps": ("INT", {
            "default": 15,
            "min": 1,
            "max": 60,
            "tooltip": "Frames per second (used in 'svi' no_llm_mode). "
                       "Only used when no_llm_mode = 'svi'.",
        }),
        "svi_cfg_scale": ("FLOAT", {
            "default": 4.0,
            "min": 1.0,
            "max": 20.0,
            "step": 0.5,
            "tooltip": "Classifier-free guidance scale (used in 'svi' no_llm_mode). "
                       "Higher = more prompt adherence, lower = more creative. "
                       "Only used when no_llm_mode = 'svi'.",
        }),
        "svi_overlap_frames": ("INT", {
            "default": 5,
            "min": 0,
            "max": 20,
            "tooltip": "Overlap frames between clips for smooth transitions (used in 'svi' no_llm_mode). "
                       "Only used when no_llm_mode = 'svi'.",
        }),
        "svi_seed_multiplier": ("INT", {
            "default": 42,
            "min": 0,
            "max": 2147483647,
            "tooltip": "Seed multiplier — seed = clip_index × this value (used in 'svi' no_llm_mode). "
                       "Only used when no_llm_mode = 'svi'.",
        }),
        "svi_steps": ("INT", {
            "default": 30,
            "min": 1,
            "max": 100,
            "tooltip": "Number of inference/sampling steps per clip. "
                       "Higher = better quality but slower. 20-40 typical.",
        }),
        "svi_high_model_ratio": ("FLOAT", {
            "default": 0.5,
            "min": 0.0,
            "max": 1.0,
            "step": 0.05,
            "tooltip": "Fraction of steps using the HIGH-noise model (0-1). "
                       "At this ratio of total steps, generation switches "
                       "from high-noise LoRA to low-noise LoRA. "
                       "Lower = more detail refinement by low-noise model.",
        }),
        "svi_frames_per_clip": ("INT", {
            "default": 81,
            "min": 17,
            "max": 161,
            "step": 4,
            "tooltip": "Frames generated per clip. Must be 4n+1 for Wan 2.2 (e.g. 33, 49, 81, 121). "
                       "More frames = longer clips but more VRAM.",
        }),
        "svi_variant": (["pro", "standard"], {
            "default": "pro",
            "tooltip": "SVI variant: 'pro' has redesigned anchor + latent conditioning (better quality), "
                       "'standard' is the original SVI 2.0 (used in 'svi' no_llm_mode). "
                       "Only used when no_llm_mode = 'svi'.",
        }),
        "svi_model_high": ((lambda: sorted(set(["auto"] + [
            f for d in (
                folder_paths.get_folder_paths("unet")
                + folder_paths.get_folder_paths("diffusion_models")
            ) if os.path.isdir(d)
            for f in os.listdir(d)
            if f.endswith((".safetensors", ".gguf", ".bin", ".pt", ".pth", ".sft"))
        ])))() if hasattr(folder_paths, "get_folder_paths") else ["auto"], {
            "default": "auto",
            "tooltip": "HIGH NOISE Wan 2.2 I2V-A14B model for SVI (used in 'svi' no_llm_mode). "
                       "'auto' = auto-discover from ComfyUI model directories. "
                       "Select the HighNoise variant (e.g. Wan2.2-I2V-A14B-HighNoise-Q3_K_S.gguf). "
                       "Only used when no_llm_mode = 'svi'.",
        }),
        "svi_model_low": ((lambda: sorted(set(["auto"] + [
            f for d in (
                folder_paths.get_folder_paths("unet")
                + folder_paths.get_folder_paths("diffusion_models")
            ) if os.path.isdir(d)
            for f in os.listdir(d)
            if f.endswith((".safetensors", ".gguf", ".bin", ".pt", ".pth", ".sft"))
        ])))() if hasattr(folder_paths, "get_folder_paths") else ["auto"], {
            "default": "auto",
            "tooltip": "LOW NOISE Wan 2.2 I2V-A14B model for SVI (used in 'svi' no_llm_mode). "
                       "'auto' = auto-discover from ComfyUI model directories. "
                       "Select the LowNoise variant (e.g. Wan2.2-I2V-A14B-LowNoise-Q3_K_S.gguf). "
                       "Only used when no_llm_mode = 'svi'.",
        }),
        "svi_lora_high": ([
            "SVI_Wan2.2-I2V-A14B_high_noise_lora_v2.0_pro.safetensors",
            "SVI_Wan2.2-I2V-A14B_high_noise_lora_v2.0.safetensors",
        ] + ([
            f for f in folder_paths.get_filename_list("loras")
            if "svi" in f.lower() and "high" in f.lower()
        ] if hasattr(folder_paths, "get_filename_list") else []), {
            "default": "SVI_Wan2.2-I2V-A14B_high_noise_lora_v2.0_pro.safetensors",
            "tooltip": "SVI HIGH-noise LoRA (used in 'svi' no_llm_mode). "
                       "Auto-downloads from HuggingFace if not present. "
                       "Only used when no_llm_mode = 'svi'.",
        }),
        "svi_lora_low": ([
            "SVI_Wan2.2-I2V-A14B_low_noise_lora_v2.0_pro.safetensors",
            "SVI_Wan2.2-I2V-A14B_low_noise_lora_v2.0.safetensors",
        ] + ([
            f for f in folder_paths.get_filename_list("loras")
            if "svi" in f.lower() and "low" in f.lower()
        ] if hasattr(folder_paths, "get_filename_list") else []), {
            "default": "SVI_Wan2.2-I2V-A14B_low_noise_lora_v2.0_pro.safetensors",
            "tooltip": "SVI LOW-noise LoRA (used in 'svi' no_llm_mode). "
                       "Auto-downloads from HuggingFace if not present. "
                       "Only used when no_llm_mode = 'svi'.",
        }),
        "svi_extra_lora_high": (["none"] + (
            folder_paths.get_filename_list("loras")
            if hasattr(folder_paths, "get_filename_list") else []
        ), {
            "default": "none",
            "tooltip": "Optional extra LoRA applied to the HIGH-noise model (stacked on top of SVI LoRA). "
                       "Select any LoRA from your loras folder, or 'none' to skip. "
                       "Only used when no_llm_mode = 'svi'.",
        }),
        "svi_extra_lora_low": (["none"] + (
            folder_paths.get_filename_list("loras")
            if hasattr(folder_paths, "get_filename_list") else []
        ), {
            "default": "none",
            "tooltip": "Optional extra LoRA applied to the LOW-noise model (stacked on top of SVI LoRA). "
                       "Select any LoRA from your loras folder, or 'none' to skip. "
                       "Only used when no_llm_mode = 'svi'.",
        }),
        "svi_vae": (["auto"] + (
            folder_paths.get_filename_list("vae")
            if hasattr(folder_paths, "get_filename_list") else []
        ), {
            "default": "auto",
            "tooltip": "VAE model for SVI. 'auto' finds Wan2.1_VAE.safetensors automatically. "
                       "Select a specific VAE from your vae folder. "
                       "Only used when no_llm_mode = 'svi'.",
        }),
        "svi_text_encoder": (["auto"] + sorted(set(
            (folder_paths.get_filename_list("text_encoders")
             if hasattr(folder_paths, "get_filename_list") else []) +
            (folder_paths.get_filename_list("clip")
             if hasattr(folder_paths, "get_filename_list") else []) +
            [f for d in (folder_paths.get_folder_paths("text_encoders") if hasattr(folder_paths, "get_folder_paths") else [])
             for f in (os.listdir(d) if os.path.isdir(d) else [])
             if f.endswith(".gguf")] +
            [f for d in (folder_paths.get_folder_paths("clip") if hasattr(folder_paths, "get_folder_paths") else [])
             for f in (os.listdir(d) if os.path.isdir(d) else [])
             if f.endswith(".gguf")]
        )), {
            "default": "auto",
            "tooltip": "Text encoder for SVI (T5/UMT5). 'auto' finds best text encoder automatically. "
                       "Select a specific model (safetensors, GGUF, etc.) from text_encoders or clip folders. "
                       "Only used when no_llm_mode = 'svi'.",
        }),
        "svi_sampler": (_svi_samplers, {
            "default": "euler",
            "tooltip": "Sampler for SVI denoising. Default: euler. "
                       "Only used when no_llm_mode = 'svi'.",
        }),
        "svi_scheduler": (_svi_schedulers, {
            "default": "normal",
            "tooltip": "Noise scheduler for SVI denoising. Default: normal. "
                       "Only used when no_llm_mode = 'svi'.",
        }),
        "svi_blockswap_blocks": ("INT", {
            "default": 0,
            "min": 0,
            "max": 40,
            "tooltip": "Wan 2.2 transformer blocks (of 40) worth of weights kept in "
                       "CPU RAM during sampling (block swap). 0 = disabled. "
                       "Higher = less VRAM, slower. Try 4-8 if you hit OOM. "
                       "Only used when no_llm_mode = 'svi'.",
        }),
        "svi_tiled_vae": ("BOOLEAN", {
            "default": False,
            "tooltip": "Decode video latents with tiled VAE to reduce VRAM spikes "
                       "during decode. Use if VAE decode OOMs. "
                       "Only used when no_llm_mode = 'svi'.",
        }),
        "ace_negative_prompt": ("STRING", {
            "default": "",
            "multiline": False,
            "placeholder": "Avoid: drums, vocals, distortion...",
            "tooltip": "Negative prompt for ACE-Step music generation. Describes what to avoid in the output. "
                       "Only used when no_llm_mode = 'ace_step'.",
        }),
        "ace_cover_strength": ("FLOAT", {
            "default": 0.5,
            "min": 0.0,
            "max": 1.0,
            "step": 0.05,
            "tooltip": "Cover/repaint strength for ACE-Step (0.0–1.0). "
                       "Lower values (0.2–0.4) keep more of the original audio (mild enhancement). "
                       "Higher values (0.7–1.0) give ACE-Step more creative freedom. "
                       "Only used in repaint/cover mode when no_llm_mode = 'ace_step'.",
        }),
        "ace_steps": ("INT", {
            "default": 8,
            "min": 1,
            "max": 50,
            "step": 1,
            "tooltip": "Number of diffusion steps for ACE-Step. "
                       "4 = fast draft, 8 = turbo default, 16+ = higher quality. "
                       "Only used when no_llm_mode = 'ace_step'.",
        }),
        "ace_cfg_scale": ("FLOAT", {
            "default": 7.0,
            "min": 1.0,
            "max": 20.0,
            "step": 0.5,
            "tooltip": "Classifier-free guidance scale for ACE-Step. "
                       "Higher values follow the prompt more closely. "
                       "Only used when no_llm_mode = 'ace_step'.",
        }),
        "ace_bpm": ("STRING", {
            "default": "",
            "multiline": False,
            "placeholder": "e.g. 120",
            "tooltip": "Target BPM (beats per minute) for ACE-Step music. "
                       "Leave empty for automatic. Only used when no_llm_mode = 'ace_step'.",
        }),
        "ace_key": ("STRING", {
            "default": "",
            "multiline": False,
            "placeholder": "e.g. C major, A minor",
            "tooltip": "Target musical key/scale for ACE-Step. "
                       "Leave empty for automatic. Only used when no_llm_mode = 'ace_step'.",
        }),
        "ace_time_sig": ("STRING", {
            "default": "",
            "multiline": False,
            "placeholder": "e.g. 4/4, 3/4, 6/8",
            "tooltip": "Target time signature for ACE-Step. "
                       "Leave empty for automatic. Only used when no_llm_mode = 'ace_step'.",
        }),
    }
