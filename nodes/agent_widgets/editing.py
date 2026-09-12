# coding: utf-8
"""AI editing and object-removal widgets.

Extracted verbatim from FFMPEGAgentNode.INPUT_TYPES. The text is preserved
exactly because ComfyUI restores saved workflows by widget *position* — see
tests/test_widget_order.py, which pins the emitted order.

Each function is called once per INPUT_TYPES() call, so dropdowns that read
the filesystem (LoRA lists, expression presets) stay dynamic.
"""

from __future__ import annotations



def flux_klein() -> dict:
    """Advanced: FLUX Klein."""
    return {
        "use_flux_klein": ("BOOLEAN", {
            "default": False,
            "label_on": "FLUX On",
            "label_off": "FLUX Off",
            "tooltip": "Enable FLUX Klein 4B for AI-powered object removal (auto_mask:effect=remove) and text-guided editing (auto_mask:effect=edit). OFF by default to avoid high VRAM usage (~8–15 GB). When OFF, removal falls back to MiniMax-Remover (if enabled) or LaMa (~200 MB) and editing uses lightweight FFmpeg filter approximations.",
        }),
        "flux_smoothing": (["none", "gaussian", "adaptive"], {
            "default": "none",
            "tooltip": "Temporal smoothing for FLUX Klein effects (remove/edit). 'none' = no smoothing (fastest, least VRAM). 'gaussian' = Gaussian blur across time (reduces flicker, +700 MiB RAM). 'adaptive' = per-pixel deviation check, only smooths outlier frames (+700 MiB RAM).",
        }),
        "flux_image_source": ("BOOLEAN", {
            "default": False,
            "label_on": "Image Input",
            "label_off": "Video Input",
            "tooltip": "When On, use the first connected image (image_a or image_path_a) as the source to edit. "
                       "Subsequent images (image_path_b, etc.) become style references. "
                       "When Off, the source comes from video_path as usual. "
                       "Only used when no_llm_mode = 'flux_klein'.",
        }),
        "flux_klein_steps": ("INT", {
            "default": 4, "min": 1, "max": 50, "step": 1,
            "tooltip": "Number of denoising steps (used in 'flux_klein' no_llm_mode). "
                       "4 = fast (~2s/frame), 20+ = higher quality but slower. "
                       "Klein is distilled so low step counts work well.",
        }),
        "flux_klein_guidance": ("FLOAT", {
            "default": 1.0, "min": 0.0, "max": 10.0, "step": 0.5,
            "tooltip": "Classifier-free guidance scale (used in 'flux_klein' no_llm_mode). "
                       "1.0 = creative/natural. 4.0+ = strict prompt adherence. "
                       "Klein is distilled so guidance_scale=1.0 is typically optimal.",
        }),
        "flux_klein_seed": ("INT", {
            "default": 42, "min": 0, "max": 2147483647, "step": 1,
            "tooltip": "Random seed for reproducibility (used in 'flux_klein' no_llm_mode). "
                       "Different seeds produce different edit variations.",
        }),
        "flux_klein_width": ("INT", {
            "default": 1024, "min": 256, "max": 2048, "step": 32,
            "tooltip": "Output width in pixels (used in 'flux_klein' no_llm_mode). "
                       "Must be divisible by 32. Result is resized back to input dimensions after editing.",
        }),
        "flux_klein_height": ("INT", {
            "default": 1024, "min": 256, "max": 2048, "step": 32,
            "tooltip": "Output height in pixels (used in 'flux_klein' no_llm_mode). "
                       "Must be divisible by 32. Result is resized back to input dimensions after editing.",
        }),
        "flux_klein_model": (["4b", "9b", "9b_fp8"], {
            "default": "4b",
            "tooltip": "FLUX Klein model size (used in 'flux_klein' no_llm_mode and "
                       "auto_mask remove/edit when FLUX is enabled). "
                       "'4b' = ~15 GB, fast (default). "
                       "'9b' = ~35 GB bf16, higher quality but slower. "
                       "'9b_fp8' = 9B with FP8 transformer from "
                       "ComfyUI/models/diffusion_models/flux-2-klein-9b-fp8.safetensors "
                       "(must be present locally). "
                       "Weights download on first use into ComfyUI/models/flux_klein/ (4b) "
                       "or flux_klein_9b/ (9b/9b_fp8).",
        }),
    }

def kiwi_edit() -> dict:
    """Advanced: Kiwi-Edit."""
    return {
        "use_kiwi_edit": ("BOOLEAN", {
            "default": False,
            "label_on": "Kiwi On",
            "label_off": "Kiwi Off",
            "tooltip": "Enable Kiwi-Edit 5B for AI-powered video editing (auto_mask:effect=edit). "
                       "Provides native video-level editing with temporal consistency. "
                       "Takes priority over FLUX Klein for edit effects when both are enabled. "
                       "OFF by default to avoid high VRAM usage (~10–16 GB).",
        }),
        "kiwi_model": (["auto", "instruct", "reference", "instruct_reference"], {
            "default": "auto",
            "tooltip": "Kiwi-Edit model variant (used in 'kiwi_edit' no_llm_mode). "
                       "'auto' = auto-select based on inputs (prompt → instruct, ref image → reference, both → instruct_reference). "
                       "'instruct' = text instruction only. "
                       "'reference' = reference image only. "
                       "'instruct_reference' = both text + reference image.",
        }),
        "kiwi_precision": (["auto", "fp8", "bf16"], {
            "default": "auto",
            "tooltip": "Kiwi-Edit weight precision. "
                       "'auto' = prefer FP8 if available, fall back to BF16 (~10 GB). "
                       "'fp8' = FP8 scaled (~5 GB, half VRAM). "
                       "'bf16' = full BF16 precision (~10 GB). "
                       "Run scripts/convert_kiwi_edit_fp8.py to create the FP8 model.",
        }),
        "kiwi_resolution": (["auto", "480p", "512", "640", "720p", "custom"], {
            "default": "640",
            "tooltip": "Kiwi-Edit output resolution. "
                       "'auto' = match input resolution (capped at 720p). "
                       "'480p' = 480×640 (fast, lower VRAM). "
                       "'512' = 512×512 (fast, square). "
                       "'640' = 640×640 (balanced, recommended). "
                       "'720p' = 720×1280 (highest quality, high VRAM). "
                       "'custom' = use kiwi_width/kiwi_height values.",
        }),
        "kiwi_width": ("INT", {
            "default": 640,
            "min": 128,
            "max": 1920,
            "step": 16,
            "tooltip": "Custom width for Kiwi-Edit output (only used when kiwi_resolution='custom'). Must be a multiple of 16.",
        }),
        "kiwi_height": ("INT", {
            "default": 640,
            "min": 128,
            "max": 1920,
            "step": 16,
            "tooltip": "Custom height for Kiwi-Edit output (only used when kiwi_resolution='custom'). Must be a multiple of 16.",
        }),
        "kiwi_max_frames": ("INT", {
            "default": 0,
            "min": 0,
            "max": 161,
            "step": 1,
            "tooltip": "Maximum frames per Kiwi-Edit processing chunk. "
                       "0 = auto (match input video frame count). "
                       "Higher = more temporal context but more VRAM. Lower = faster with less VRAM.",
        }),
        "kiwi_steps": ("INT", {
            "default": 50,
            "min": 1,
            "max": 100,
            "step": 1,
            "tooltip": "Number of inference steps for Kiwi-Edit. Default 50. Lower = faster but lower quality.",
        }),
        "kiwi_guidance": ("FLOAT", {
            "default": 5.0,
            "min": 1.0,
            "max": 20.0,
            "step": 0.5,
            "tooltip": "Classifier-free guidance scale for Kiwi-Edit. Default 5.0. Higher = stronger prompt adherence.",
        }),
        "kiwi_block_swap": ("INT", {
            "default": 0,
            "min": 0,
            "max": 40,
            "step": 1,
            "tooltip": "Kiwi-Edit BlockSwap: number of transformer blocks to offload to CPU. "
                       "0 = disabled (keep on GPU). 4-16 = saves VRAM for lower-end cards.",
        }),
        "kiwi_long_video": ("BOOLEAN", {
            "default": False,
            "label_on": "Long Video On",
            "label_off": "Long Video Off",
            "tooltip": "Enable chunked processing for videos longer than kiwi_max_frames. "
                       "Splits into overlapping chunks, processes each, and stitches with crossfade blending.",
        }),
        "kiwi_seed": ("INT", {
            "default": 0,
            "min": 0,
            "max": 2147483647,
            "step": 1,
            "tooltip": "Random seed for Kiwi-Edit. 0 = random seed each run. "
                       "Set a fixed value for reproducible results.",
        }),
        "kiwi_flow_shift": ("FLOAT", {
            "default": 5.0,
            "min": 1.0,
            "max": 15.0,
            "step": 0.5,
            "tooltip": "Flow matching shift for the UniPC scheduler. Default 5.0. "
                       "Higher values = more aggressive denoising (stronger edits). "
                       "Lower values = subtler, more conservative changes.",
        }),
        "kiwi_task_type": (["auto", "global_style", "local_change", "background_change", "local_remove", "local_add"], {
            "default": "auto",
            "tooltip": "Override automatic task type detection for prompt enhancement. "
                       "'auto' = detect from keywords in prompt. "
                       "'global_style' = style/aesthetic changes (e.g. 'make it look like a painting'). "
                       "'local_change' = change a specific object (e.g. 'change shirt to red'). "
                       "'background_change' = change background only. "
                       "'local_remove' = remove an object. "
                       "'local_add' = add a new object.",
        }),
        "kiwi_scheduler": (["unipc", "euler", "heun", "dpm++"], {
            "default": "unipc",
            "tooltip": "Scheduler (sampler) for Kiwi-Edit denoising. "
                       "'unipc' = UniPC predictor-corrector (default, fast convergence at 30 steps). "
                       "'euler' = Flow Match Euler (original model default, needs ~50 steps). "
                       "'heun' = Flow Match Heun (higher quality per step, 2x cost). "
                       "'dpm++' = DPM++ Multistep (alternative fast solver).",
        }),
    }

def minimax_remover() -> dict:
    """Advanced: MiniMax-Remover."""
    return {
        "use_minimax_remover": ("BOOLEAN", {
            "default": False,
            "label_on": "MiniMax On",
            "label_off": "MiniMax Off",
            "tooltip": "Enable MiniMax-Remover for high-quality video object removal (auto_mask:effect=remove). Uses a purpose-built DiT model (~2.5 GB, ~5–8 GB VRAM). Takes priority over FLUX Klein for removal when both are enabled. When OFF, removal falls back to FLUX Klein (if enabled) or LaMa (~200 MB).",
        }),
    }
