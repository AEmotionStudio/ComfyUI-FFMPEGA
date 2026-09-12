# coding: utf-8
"""Super-resolution widgets.

Extracted verbatim from FFMPEGAgentNode.INPUT_TYPES. The text is preserved
exactly because ComfyUI restores saved workflows by widget *position* — see
tests/test_widget_order.py, which pins the emitted order.

Each function is called once per INPUT_TYPES() call, so dropdowns that read
the filesystem (LoRA lists, expression presets) stay dynamic.
"""

from __future__ import annotations



def ai_upscale() -> dict:
    """Advanced: AI Upscale."""
    return {
        "upscale_model": (["realesrgan_x4plus", "realesrgan_x4_anime", "hat_x4", "dat_x4", "swinir_x4", "seedvr2_3b_int8", "seedvr2_7b_int8", "seedvr2_3b_fp8", "seedvr2_3b_gguf", "seedvr2_7b_fp8", "seedvr2_7b_fp8_mixed", "seedvr2_7b_gguf", "flashvsr_full", "flashvsr_tiny", "flashvsr_tiny_long", "rtx_vsr"], {
            "default": "realesrgan_x4plus",
            "tooltip": "AI upscaler model (used in 'ai_upscale' no_llm_mode). "
                       "'realesrgan_x4plus' = fast general-purpose. "
                       "'realesrgan_x4_anime' = anime/cartoon. "
                       "'hat_x4' = SOTA quality (Real-HAT-GAN). "
                       "'dat_x4' = balanced (DAT-2). "
                       "'swinir_x4' = classical SR. "
                       "'seedvr2_3b_int8' = INT8 diffusion upscaler, recommended 3B — fastest and smallest (~6-9 GB VRAM). "
                       "'seedvr2_7b_int8' = INT8 diffusion upscaler, recommended 7B — highest quality (~10-14 GB VRAM, use blockswap_blocks under 16 GB). "
                       "'seedvr2_3b_fp8' = diffusion upscaler, great quality (~8-12 GB VRAM). "
                       "'seedvr2_3b_gguf' = diffusion upscaler, lowest VRAM (~6-8 GB). "
                       "'seedvr2_7b_fp8' = highest quality diffusion upscaler (~16-24 GB VRAM). "
                       "'seedvr2_7b_fp8_mixed' = 7B with fp16 last block, fixes 7B seam/grid artifacts (recommended 7B, ~16-24 GB VRAM). "
                       "'seedvr2_7b_gguf' = highest quality diffusion upscaler, quantized (~8-12 GB VRAM). "
                       "'flashvsr_full' = FlashVSR one-step diffusion, best quality (~12-16 GB VRAM). "
                       "'flashvsr_tiny' = FlashVSR fast mode with TCDecoder (~8-12 GB VRAM). "
                       "'flashvsr_tiny_long' = FlashVSR streaming for long videos, low VRAM (~8-12 GB). "
                       "'rtx_vsr' = NVIDIA RTX Video Super Resolution (hardware-accelerated, RTX GPU required).",
        }),
        "upscale_scale": (["4", "2"], {
            "default": "4",
            "tooltip": "AI upscale factor (used in 'ai_upscale' no_llm_mode). "
                       "'4' = 4× resolution. '2' = 2× resolution.",
        }),
        "seedvr_resolution": (["1080", "720", "1440", "2160"], {
            "default": "1080",
            "tooltip": "SeedVR2 target output resolution (shortest edge, in pixels). "
                       "'1080' = 1080p (default, recommended). "
                       "'720' = 720p (faster, lower VRAM). "
                       "'1440' = 1440p/2K (higher quality). "
                       "'2160' = 4K (highest quality, high VRAM). "
                       "Only applies when a SeedVR2 upscale model is selected.",
        }),
        "blockswap_blocks": ("INT", {
            "default": 0,
            "min": -1,
            "max": 32,
            "step": 1,
            "tooltip": "BlockSwap: number of DiT blocks to offload to CPU during inference "
                       "(applies to SeedVR2 and FlashVSR diffusion upscalers). Streams "
                       "model WEIGHTS only — does not reduce activation/decode memory. "
                       "0 = disabled (default, manual). -1 = auto (size from free VRAM; "
                       "FlashVSR only). 4-30 = stream that many DiT blocks. "
                       "For SeedVR2, -1 behaves the same as 0 (disabled).",
        }),
        "flashvsr_processing": (["whole", "temporal", "spatial"], {
            "default": "whole",
            "tooltip": "FlashVSR memory/quality strategy (bounds ACTIVATION/decode memory, "
                       "the real OOM limiter). "
                       "'whole' = one whole-frame pass, best quality (use the "
                       "'flashvsr_tiny_long' model for long clips — it streams over time). "
                       "'temporal' = slide over frames in windows of flashvsr_frame_window "
                       "(no spatial tiling; keeps spatial quality). "
                       "'spatial' = split each frame into tiles (lowest quality, seams; "
                       "uses the VAE tile size). Only applies to FlashVSR models.",
        }),
        "flashvsr_frame_window": ("INT", {
            "default": 0,
            "min": 0,
            "max": 200,
            "step": 1,
            "tooltip": "FlashVSR temporal window: frames processed per pass when "
                       "flashvsr_processing='temporal'. 0 = whole clip. Smaller = less "
                       "VRAM, more passes. Minimum effective window is 21 frames. "
                       "Ignored for 'flashvsr_tiny_long' (it streams internally).",
        }),
        "flashvsr_color_fix": ("BOOLEAN", {
            "default": True,
            "label_on": "Color Fix On",
            "label_off": "Color Fix Off",
            "tooltip": "FlashVSR AdaIN/wavelet color correction (matches output color to the "
                       "low-res input). On = stable colors; can flatten enhancement. "
                       "Off = raw model output (matches the reference workflow, often "
                       "sharper/more contrasty). Only applies to FlashVSR models.",
        }),
        "flashvsr_decode_tile": ("INT", {
            "default": 512,
            "min": 0,
            "max": 2048,
            "step": 64,
            "tooltip": "FlashVSR decoder spatial tile size in pixels (tiny / tiny_long). "
                       "The decode step is the usual OOM point at high resolution; tiling "
                       "it is near-lossless (unlike tiling the DiT). 512 fits ~12 GB at "
                       "1024². 0 = whole-frame decode (may OOM). Smaller = less VRAM.",
        }),
        "rtx_quality": (["ULTRA", "HIGH", "MEDIUM", "LOW", "DENOISE_ULTRA", "DENOISE_HIGH", "DENOISE_MEDIUM", "DENOISE_LOW", "DEBLUR_ULTRA", "DEBLUR_HIGH", "DEBLUR_MEDIUM", "DEBLUR_LOW"], {
            "default": "ULTRA",
            "tooltip": "RTX VSR quality preset (used when 'rtx_vsr' upscale model is selected). "
                       "ULTRA/HIGH/MEDIUM/LOW = upscale quality levels. "
                       "DENOISE_* = same-resolution denoising. "
                       "DEBLUR_* = same-resolution deblurring. "
                       "Requires NVIDIA RTX GPU with Tensor Cores.",
        }),
        "vae_tiling": ("BOOLEAN", {
            "default": True,
            "label_on": "Tiling On",
            "label_off": "Tiling Off",
            "tooltip": "Tiling for diffusion upscalers (SeedVR2 / FlashVSR). "
                       "On (default) = spatial tiling, lower VRAM, slight seams possible "
                       "(needed at high scale even with block-swap — it bounds "
                       "activation memory, which block-swap does not). "
                       "Off = whole-frame, best quality/no seams, but may OOM at high "
                       "scale (FlashVSR auto-falls-back to tiles if it does). "
                       "Only applies when a SeedVR2 or FlashVSR upscale model is selected.",
        }),
        "vae_tile_preset": (["auto", "256", "384", "512", "768", "1024", "custom"], {
            "default": "auto",
            "tooltip": "Tile size preset (used when tiling is on). "
                       "'auto' = pick by VRAM (SeedVR2) / model default 384px (FlashVSR). "
                       "A number = square tile of that pixel size (larger = fewer seams, "
                       "more VRAM). "
                       "'custom' = use vae_tile_size / vae_tile_overlap below.",
        }),
        "vae_tile_size": ("INT", {
            "default": 512,
            "min": 64,
            "max": 2048,
            "step": 64,
            "tooltip": "Custom VAE tile size in pixels "
                       "(used when vae_tile_preset = 'custom').",
        }),
        "vae_tile_overlap": ("INT", {
            "default": 64,
            "min": 0,
            "max": 512,
            "step": 16,
            "tooltip": "Custom VAE tile overlap in pixels for blending "
                       "(used when vae_tile_preset = 'custom').",
        }),
    }
