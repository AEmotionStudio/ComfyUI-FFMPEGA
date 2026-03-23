"""FFMPEG Agent node for ComfyUI."""

import asyncio
import json
import logging
import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger("ffmpega")

import torch  # type: ignore[import-not-found]

import folder_paths  # type: ignore[import-not-found]

from . import input_resolver as _ir
from . import output_handler as _oh
from . import execution_engine as _ee
from . import nollm_modes as _nollm
from . import batch_processor as _bp
from . import pipeline_assembler as _pa


def _get_expression_presets() -> list[str]:
    """List available expression preset names for the dropdown widget."""
    try:
        try:
            from core.expression_presets import list_expressions
        except ImportError:
            from ..core.expression_presets import list_expressions  # type: ignore
        return list_expressions()
    except Exception:
        return []


class FFMPEGAgentNode:
    """Main FFMPEG Agent node that transforms natural language prompts into video edits."""

    # Fallback models if Ollama is unreachable
    FALLBACK_OLLAMA_MODELS = [
        "qwen3:8b",
        "mistral-nemo",
        "llama3.3:8b",
    ]

    # Stable pointer/alias names — these auto-update and rarely break.
    # Users can also select "custom" and type any model name.
    # The list is read from config/models.yaml via core.model_config.load_api_models().
    # Edit that YAML file to add or remove models without touching Python code.
    @classmethod
    def _get_api_models(cls) -> list[str]:
        """Read API model names from config/models.yaml (cached after first load)."""
        try:
            from ..core.model_config import load_api_models  # type: ignore[import-not-found]
            return load_api_models()
        except Exception as exc:
            import logging
            logging.getLogger("ffmpega").warning(
                "Failed to load model list from config/models.yaml: %s — "
                "using built-in fallback list", exc
            )
            return [
                "gpt-5.2", "gpt-5-mini", "gpt-4.1",
                "claude-sonnet-4-6", "claude-haiku-4-5",
                "gemini-3-flash", "gemini-2.5-flash",
                "qwen-max", "qwen-plus", "qwen-turbo",
            ]

    QUALITY_PRESETS = ["draft", "standard", "high", "lossless"]

    # Class-level TTL cache for Ollama model list
    _ollama_cache: list[str] | None = None
    _ollama_cache_time: float = 0.0
    _OLLAMA_CACHE_TTL: float = 30.0  # seconds

    @classmethod
    def _fetch_ollama_models(cls, base_url: str = "http://localhost:11434") -> list[str]:
        """Fetch available models from a running Ollama instance.

        Returns locally installed model names, or the fallback list
        if Ollama is unreachable.  Results are cached for 30 seconds
        to avoid redundant API calls.
        """
        now = time.monotonic()
        if cls._ollama_cache is not None and (now - cls._ollama_cache_time) < cls._OLLAMA_CACHE_TTL:
            return cls._ollama_cache

        try:
            import httpx  # type: ignore[import-not-found]
            with httpx.Client(timeout=3.0) as client:
                resp = client.get(f"{base_url}/api/tags")
                resp.raise_for_status()
                models = [m["name"] for m in resp.json().get("models", [])]
                result = sorted(models) if models else cls.FALLBACK_OLLAMA_MODELS
        except Exception:
            result = cls.FALLBACK_OLLAMA_MODELS

        cls._ollama_cache = result
        cls._ollama_cache_time = now
        return result

    @classmethod
    def INPUT_TYPES(cls):
        """Define input types for the node."""
        ollama_models = cls._fetch_ollama_models()
        all_models = ["none"] + ollama_models + cls._get_api_models() + ["custom"]

        # --- CLI auto-detection -------------------------------------------
        # Use shared resolver that checks PATH + well-known user-local dirs.
        try:
            from ..core.llm.cli_utils import resolve_cli_binary
        except ImportError:
            from core.llm.cli_utils import resolve_cli_binary  # type: ignore

        cli_models: list[str] = []
        if resolve_cli_binary("gemini", "gemini.cmd"):
            cli_models.append("gemini-cli")
        if resolve_cli_binary("claude", "claude.cmd"):
            cli_models.append("claude-cli")
        if resolve_cli_binary("agent", "agent.cmd"):
            cli_models.append("cursor-agent")
        if resolve_cli_binary("qwen", "qwen.cmd"):
            cli_models.append("qwen-cli")

        # Insert all CLI models at the boundary between Ollama and API models
        # so they appear in the intended order.
        insert_pos = len(ollama_models)
        for model in cli_models:
            all_models.insert(insert_pos, model)
            insert_pos += 1

        return {
            "required": {
                "prompt": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "placeholder": "Describe how you want to edit the video...",
                    "tooltip": "Natural language instruction describing the desired edit. Examples: 'Add a cinematic letterbox', 'Speed up 2x', 'Apply a vintage VHS look'.",
                }),
                "video_path": ("STRING", {
                    "default": "",
                    "multiline": False,
                    "placeholder": "Path to input video file",
                    "tooltip": "Absolute path to the source video file. Used as the ffmpeg input unless images are connected.",
                }),
                "llm_model": (all_models, {
                    "default": "none",
                    "tooltip": "AI model for interpreting your prompt. "
                               "CLI models (gemini-cli, claude-cli, etc.) use locally installed CLI tools — no API key needed. "
                               "Ollama models run locally via the Ollama server. "
                               "Cloud API models (GPT, Claude, Gemini, Qwen) require an api_key. "
                               "Select 'custom' to type any model name manually. "
                               "Select 'none' to skip the LLM entirely and use no_llm_mode instead (manual pipeline, SAM3, Whisper, or MMAudio).",
                }),
                "no_llm_mode": (["manual", "sam3_masking", "transcribe", "karaoke_subtitles", "generate_audio", "generate_music", "foundation1", "fish_speech", "audio_inpaint", "audio_separate", "ace_step", "lip_sync", "animate_portrait", "marigold", "normalcrafter", "video_depth", "flux_klein", "kiwi_edit", "minimax_remover", "dreamid_omni", "scail (WIP)", "ai_upscale", "rembg", "video_matting", "onion_skin", "comparison"], {
                    "default": "manual",
                    "tooltip": "What to do when llm_model is 'none'. "
                               "'manual' runs the Effects Builder pipeline directly (no AI). "
                               "'sam3_masking' uses the prompt as a SAM3 text target. "
                               "'transcribe' runs Whisper speech-to-text and burns SRT subtitles. "
                               "'karaoke_subtitles' runs Whisper and burns word-by-word karaoke subtitles. "
                               "'generate_audio' uses MMAudio to synthesize audio from video/prompt. "
                               "'generate_music' uses AudioX to generate music from video/prompt (CC-BY-NC). "
                               "'foundation1' uses Foundation-1 to generate BPM/key-aware music loops from prompt. "
                               "'fish_speech' uses Fish Speech S2 Pro for text-to-speech with voice cloning and emotion control (80+ languages). "
                               "'audio_inpaint' uses AudioX to inpaint/complete audio (CC-BY-NC). "
                               "'audio_separate' uses SAM-Audio to isolate specific sounds from audio — prompt describes what to isolate (e.g. 'drums', 'vocals'). "
                               "'lip_sync' uses MuseTalk to sync lip movements to connected audio_a. "
                               "'animate_portrait' uses LivePortrait to animate a face — connect driving video to video_a. "
                               "'marigold' runs Marigold dense vision analysis (depth/normals/intrinsics) — choose output via marigold_output_type. "
                               "'normalcrafter' runs NormalCrafter for temporally-consistent video surface normals — choose res via normalcrafter_max_res. "
                               "'video_depth' runs Video Depth Anything for temporally-consistent depth — choose encoder via video_depth_encoder. "
                               "'flux_klein' runs FLUX Klein editing directly — prompt is the edit instruction, works on images and videos (full-frame, no mask needed). "
                               "'rembg' removes the video background using AI segmentation — choose model via rembg_model and background via rembg_background. "
                               "'video_matting' runs MatAnyone2 temporal video matting — uses SAM3 for auto-mask or connect mask to image_a. Choose output via matting_output (⚠️ non-commercial license). "
                               "'onion_skin' applies temporal ghosting (onion skin) — adjust blend mode, opacity, and trail decay in advanced options. "
                               "'comparison' creates a comparison video from two inputs (before/after) — connect video_a as the 'after' video. "
                               "Styles: swipe, split, side_by_side, diagonal, circular_reveal, difference.",
                }),
                "quality_preset": (cls.QUALITY_PRESETS, {
                    "default": "standard",
                    "tooltip": "Output quality level. 'draft' is fast/low quality, 'standard' is balanced, 'high' is slow/best quality, 'lossless' preserves full quality.",
                }),
                "seed": ("INT", {
                    "default": 0,
                    "min": 0,
                    "max": 0xffffffffffffffff,
                    "tooltip": "Change this value to force re-execution with the same prompt. Use the randomize control to auto-increment between runs.",
                    "control_after_generate": True,
                }),
            },
            "optional": {
                # ── Connection inputs (always visible, forceInput) ────────
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

                # ── Basic options (always visible) ────────────────────────
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
                "api_key": ("STRING", {
                    "default": "",
                    "multiline": False,
                    "placeholder": "API key for OpenAI/Anthropic",
                    "tooltip": "API key required when using cloud models (GPT, Claude, Gemini). Not needed for local Ollama models.",
                }),
                "custom_model": ("STRING", {
                    "default": "",
                    "multiline": False,
                    "placeholder": "Model name (e.g. gpt-5.2, claude-sonnet-4-6)",
                    "tooltip": "When 'custom' is selected in llm_model, type the exact model name here. Use provider prefixes: gpt-* for OpenAI, claude-* for Anthropic, gemini-* for Google, anything else for Ollama.",
                }),

                # ── LLM Behavior (always visible) ─────────────────────────
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

                # ── Advanced toggle ───────────────────────────────────────
                "advanced_options": ("BOOLEAN", {
                    "default": False,
                    "label_on": "Advanced",
                    "label_off": "Simple",
                    "tooltip": "Show advanced options: preview, encoding, SAM3/Whisper tuning, FLUX smoothing, MMAudio mode, SAM-Audio model, batch processing, and usage tracking.",
                }),

                # ── Advanced: Rendering ───────────────────────────────────
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


                # ── Advanced: Whisper ─────────────────────────────────────
                "whisper_device": (["cpu", "gpu"], {
                    "default": "cpu",
                    "tooltip": "Device for Whisper transcription model. 'gpu' is faster but uses ~3 GB VRAM (frees ComfyUI models first). 'cpu' is slower but avoids VRAM pressure — best for low-VRAM GPUs or intensive workflows.",
                }),
                "whisper_model": (["large-v3", "medium", "small", "base", "tiny"], {
                    "default": "large-v3",
                    "tooltip": "Whisper model size for transcription. 'large-v3' is most accurate (~3 GB VRAM). Smaller models use less memory: medium (~1.5 GB), small (~1 GB), base (~150 MB), tiny (~75 MB). Models auto-download on first use.",
                }),

                # ── Advanced: SAM3 ────────────────────────────────────────
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

                # ── Advanced: SAM3 Pre-Masking for No-LLM Modes ──────────
                "use_sam3": ("BOOLEAN", {
                    "default": False,
                    "label_on": "SAM3 On",
                    "label_off": "SAM3 Off",
                    "tooltip": "Enable SAM3 pre-masking for no-LLM modes. When ON, the prompt text is used as a SAM3 target "
                               "to mask specific objects before the effect runs. The effect is then composited onto the original "
                               "via the mask. Works with: lip_sync, animate_portrait, marigold, normalcrafter, video_depth, "
                               "flux_klein, minimax_remover, ai_upscale, rembg, onion_skin, comparison.",
                }),

                # ── Advanced: FLUX Klein ──────────────────────────────────
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
                "flux_klein_model": (["auto", "fp8", "bf16"], {
                    "default": "auto",
                    "tooltip": "FLUX Klein model variant (used in 'flux_klein' no_llm_mode or when use_flux_klein=On). "
                               "'auto' = prefer FP8 if available, fall back to BF16 (~15 GB). "
                               "'fp8' = FP8 scaled (~8 GB, half VRAM). "
                               "'bf16' = full BF16 precision (~15 GB). "
                               "Run scripts/convert_flux_klein_fp8.py to create the FP8 model.",
                }),

                # ── Advanced: Kiwi-Edit ──────────────────────────────────
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
                "kiwi_lora_enabled": ("BOOLEAN", {
                    "default": False,
                    "label_on": "LoRA On",
                    "label_off": "LoRA Off",
                    "tooltip": "Enable LightX2V distill LoRA for 4-step inference. "
                               "Dramatically speeds up Kiwi-Edit by reducing steps from 50 to 4. "
                               "Downloads the LoRA (~600 MB) on first use from lightx2v/Wan2.2-Distill-Loras.",
                }),
                "kiwi_lora_variant": (["high_noise", "low_noise"], {
                    "default": "high_noise",
                    "tooltip": "LightX2V LoRA noise variant (only used when kiwi_lora_enabled is On). "
                               "'high_noise' = more creative/diverse output. "
                               "'low_noise' = more faithful to the original input.",
                }),
                # ── Advanced: MiniMax-Remover ─────────────────────────────
                "use_minimax_remover": ("BOOLEAN", {
                    "default": False,
                    "label_on": "MiniMax On",
                    "label_off": "MiniMax Off",
                    "tooltip": "Enable MiniMax-Remover for high-quality video object removal (auto_mask:effect=remove). Uses a purpose-built DiT model (~2.5 GB, ~5–8 GB VRAM). Takes priority over FLUX Klein for removal when both are enabled. When OFF, removal falls back to FLUX Klein (if enabled) or LaMa (~200 MB).",
                }),

                # ── Advanced: DreamID-Omni (WIP) ────────────────────────────
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

                # ── Advanced: SCAIL (WIP — memory optimization incomplete) ─
                "scail_precision": (["auto", "fp8", "bf16"], {
                    "default": "auto",
                    "tooltip": "SCAIL model precision. "
                               "'auto' = prefer FP8 if available (~12 GB), else BF16 (~23 GB). "
                               "'fp8' = FP8 quantized (fastest, lowest VRAM). "
                               "'bf16' = BFloat16 (best quality, higher VRAM).",
                }),
                "scail_steps": ("INT", {
                    "default": 40,
                    "min": 1,
                    "max": 100,
                    "step": 1,
                    "tooltip": "Number of diffusion sampling steps for SCAIL. Default 40. Lower = faster but less detailed.",
                }),
                "scail_guidance": ("FLOAT", {
                    "default": 5.0,
                    "min": 1.0,
                    "max": 15.0,
                    "step": 0.5,
                    "tooltip": "Classifier-free guidance scale. Higher = stronger prompt adherence. Default 5.0.",
                }),
                "scail_shift": ("FLOAT", {
                    "default": 3.0,
                    "min": 1.0,
                    "max": 10.0,
                    "step": 0.5,
                    "tooltip": "Flow matching shift parameter. Controls noise schedule. Default 3.0.",
                }),
                "scail_solver": (["unipc", "dpm++"], {
                    "default": "unipc",
                    "tooltip": "Solver for SCAIL denoising. "
                               "'unipc' = UniPC predictor-corrector (default, fast). "
                               "'dpm++' = DPM++ Multistep (slightly different quality).",
                }),
                "scail_seed": ("INT", {
                    "default": 0,
                    "min": 0,
                    "max": 2147483647,
                    "step": 1,
                    "tooltip": "Random seed for SCAIL. Set a fixed value for reproducible results. 0 = random.",
                }),

                # ── Advanced: SAM-Audio ──────────────────────────────────
                "sam_audio_model": (["base", "base-fp8", "large-fp8", "large"], {
                    "default": "base",
                    "tooltip": "SAM-Audio model variant for audio_separate mode. "
                               "'base' = 3.6 GiB BF16 (default). "
                               "'base-fp8' = 1.8 GiB FP8 scaled (half VRAM, ~same quality). "
                               "'large-fp8' = 3.5 GiB FP8 scaled (large quality at base VRAM — recommended). "
                               "'large' = 6.9 GiB BF16 (best quality, needs 12+ GB VRAM). "
                               "Models auto-download on first use.",
                }),

                # ── Advanced: Marigold ────────────────────────────────────
                "marigold_output_type": (["depth", "normals", "appearance", "lighting"], {
                    "default": "depth",
                    "tooltip": "Marigold output type (used in 'marigold' no_llm_mode or agentic mode). "
                               "'depth' = monocular depth map. "
                               "'normals' = surface normals. "
                               "'appearance' = albedo + roughness + metallicity. "
                               "'lighting' = albedo + shading + residual.",
                }),
                "marigold_colormap": (["Spectral", "gray", "inferno", "turbo", "plasma", "magma", "viridis", "hot", "bone"], {
                    "default": "Spectral",
                    "tooltip": "Depth map colormap (used in 'marigold' no_llm_mode, depth output only). "
                               "'Spectral' = standard red-to-blue depth map. "
                               "'gray' = B&W depth (for ControlNet/compositing). "
                               "Others are artistic colormaps for creative visualization.",
                }),

                # ── Advanced: NormalCrafter ────────────────────────────────
                "normalcrafter_max_res": (["auto", "1024", "768", "512"], {
                    "default": "auto",
                    "tooltip": "NormalCrafter max resolution (used in 'normalcrafter' no_llm_mode). "
                               "'auto' = auto-detect GPU VRAM and pick the safest resolution (~12 GB → 768, ~8 GB → 512). "
                               "'1024' = highest quality (needs ~12+ GB VRAM). "
                               "'768' = balanced quality/VRAM (~8–12 GB). "
                               "'512' = lowest VRAM (~6 GB).",
                }),

                # ── Advanced: Video Depth Anything ─────────────────────────
                "video_depth_encoder": (["vits", "vitb", "vitl"], {
                    "default": "vits",
                    "tooltip": "Video Depth Anything model size (used in 'video_depth' no_llm_mode or agentic mode). "
                               "'vits' = Small (~7 GB, fastest). "
                               "'vitb' = Base (~12 GB). "
                               "'vitl' = Large (~24 GB, best quality).",
                }),
                "video_depth_colormap": (["gray", "inferno", "turbo", "plasma", "magma", "viridis", "hot", "bone"], {
                    "default": "gray",
                    "tooltip": "Depth map colormap (used in 'video_depth' no_llm_mode). "
                               "'gray' = standard B&W depth (for ControlNet/compositing). "
                               "Others are artistic colormaps for creative visualization.",
                }),

                # ── Advanced: AI Upscale ───────────────────────────────────
                "upscale_model": (["realesrgan_x4plus", "realesrgan_x4_anime", "hat_x4", "dat_x4", "swinir_x4", "seedvr2_3b_fp8", "seedvr2_3b_gguf", "seedvr2_7b_fp8", "seedvr2_7b_gguf", "flashvsr_full", "flashvsr_tiny", "flashvsr_tiny_long", "rtx_vsr"], {
                    "default": "realesrgan_x4plus",
                    "tooltip": "AI upscaler model (used in 'ai_upscale' no_llm_mode). "
                               "'realesrgan_x4plus' = fast general-purpose. "
                               "'realesrgan_x4_anime' = anime/cartoon. "
                               "'hat_x4' = SOTA quality (Real-HAT-GAN). "
                               "'dat_x4' = balanced (DAT-2). "
                               "'swinir_x4' = classical SR. "
                               "'seedvr2_3b_fp8' = diffusion upscaler, great quality (~8-12 GB VRAM). "
                               "'seedvr2_3b_gguf' = diffusion upscaler, lowest VRAM (~6-8 GB). "
                               "'seedvr2_7b_fp8' = highest quality diffusion upscaler (~16-24 GB VRAM). "
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
                    "min": 0,
                    "max": 32,
                    "step": 1,
                    "tooltip": "SeedVR2 BlockSwap: number of DiT blocks to offload to CPU during inference. "
                               "0 = disabled (keep everything on GPU, recommended for ≥16 GB VRAM). "
                               "4-8 = saves ~1-3 GB VRAM (for 8-12 GB cards). "
                               "Only applies when a SeedVR2 upscale model is selected.",
                }),
                "rtx_quality": (["ULTRA", "HIGH", "MEDIUM", "LOW", "DENOISE_ULTRA", "DENOISE_HIGH", "DENOISE_MEDIUM", "DENOISE_LOW", "DEBLUR_ULTRA", "DEBLUR_HIGH", "DEBLUR_MEDIUM", "DEBLUR_LOW"], {
                    "default": "ULTRA",
                    "tooltip": "RTX VSR quality preset (used when 'rtx_vsr' upscale model is selected). "
                               "ULTRA/HIGH/MEDIUM/LOW = upscale quality levels. "
                               "DENOISE_* = same-resolution denoising. "
                               "DEBLUR_* = same-resolution deblurring. "
                               "Requires NVIDIA RTX GPU with Tensor Cores.",
                }),

                # ── Advanced: Rembg Background Removal ─────────────────────
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

                # ── Advanced: MatAnyone2 Video Matting ──────────────────────
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

                # ── Advanced: Audio Output Mode ───────────────────────────
                "audio_output_mode": (["auto", "replace", "mix", "save_only"], {
                    "default": "auto",
                    "tooltip": "How to combine AI-generated audio with existing audio. "
                               "Applies to all audio-generating modes: generate_audio (MMAudio), generate_music (AudioX), foundation1 (Foundation-1), fish_speech (Fish Speech TTS), audio_inpaint (AudioX), audio_separate (SAM-Audio), ace_step. "
                               "'auto' lets the LLM decide in agentic mode; defaults to 'replace' in no-LLM modes. "
                               "'replace' replaces existing audio entirely. "
                               "'mix' blends generated audio with the original track. "
                               "'save_only' generates the audio file without muxing it into the video.",
                }),

                # ── Advanced: Audio Resample Rate ──────────────────────────
                "audio_resample_rate": (["off", "44100", "48000"], {
                    "default": "off",
                    "tooltip": "Resample the audio output to this sample rate. "
                               "Enable this if your audio effects (e.g. clean_audio with loudnorm) "
                               "produce non-standard sample rates (like 96kHz) that ComfyUI's "
                               "Save Audio MP3 node can't handle. "
                               "'off' = pass through original sample rate. "
                               "'44100' = CD quality, universal MP3 compatibility. "
                               "'48000' = studio quality, universal compatibility.",
                }),

                # ── Advanced: Onion Skin ──────────────────────────────────
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

                # ── Advanced: Comparison ─────────────────────────────────
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

                # ── Advanced: ACE-Step Music Generation ───────────────────
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

                # ── Advanced: Foundation-1 controls ────────────────────────
                "f1_preset": (["none", "warm_pad", "synth_lead", "bass_loop", "string_ensemble", "electric_piano", "plucked_arp", "ambient_texture", "brass_stab", "guitar_clean", "mallet_vibes"], {
                    "default": "none",
                    "tooltip": "Built-in timbre preset for Foundation-1. "
                               "Provides structured instrument/timbre tags. "
                               "Combine with a text prompt for customization. "
                               "Only used when no_llm_mode = 'foundation1'.",
                }),
                "f1_instrument": (["none", "synth", "keys", "bass", "strings", "mallet", "winds", "guitar", "brass", "vocals", "plucked"], {
                    "default": "none",
                    "tooltip": "Instrument family to guide Foundation-1 generation. "
                               "Appended to prompt automatically. 'none' = let the prompt decide. "
                               "Only used when no_llm_mode = 'foundation1'.",
                }),
                "f1_fx": (["none", "dry", "low_reverb", "medium_reverb", "high_reverb", "plate_reverb", "low_delay", "medium_delay", "ping_pong_delay", "stereo_delay", "low_distortion", "medium_distortion", "phaser", "bitcrush", "chorus"], {
                    "default": "none",
                    "tooltip": "FX processing applied to Foundation-1 output. "
                               "'dry' = minimal processing, other options add specific effects. "
                               "Only used when no_llm_mode = 'foundation1'.",
                }),
                "f1_structure": (["none", "chord_progression", "melody", "arp", "sustained", "staccato", "legato", "triplets", "rhythmic", "rising", "falling", "simple", "complex"], {
                    "default": "none",
                    "tooltip": "Musical structure/notation tag to guide phrasing. "
                               "Controls melodic motion, rhythmic behavior, and harmonic feel. "
                               "Only used when no_llm_mode = 'foundation1'.",
                }),
                "f1_negative_prompt": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "placeholder": "e.g. harsh, distorted, noise",
                    "tooltip": "Negative prompt describing what to avoid in Foundation-1 output. "
                               "Only used when no_llm_mode = 'foundation1'.",
                }),
                "f1_bpm": (["auto", "100", "110", "120", "128", "130", "140", "150"], {
                    "default": "auto",
                    "tooltip": "Target BPM. Foundation-1 supports specific BPM denominations. "
                               "'auto' = let the model decide. "
                               "Only used when no_llm_mode = 'foundation1'.",
                }),
                "f1_bars": (["auto", "4", "8"], {
                    "default": "auto",
                    "tooltip": "Number of bars for the loop. Foundation-1 supports 4 or 8 bars. "
                               "'auto' = let the model decide. Combined with BPM for precise duration. "
                               "Only used when no_llm_mode = 'foundation1'.",
                }),
                "f1_key": ("STRING", {
                    "default": "",
                    "multiline": False,
                    "placeholder": "e.g. C major, A minor, F# dorian",
                    "tooltip": "Musical key and mode. Supports all keys and modes. "
                               "Leave empty for automatic. "
                               "Only used when no_llm_mode = 'foundation1'.",
                }),
                "f1_duration": ("FLOAT", {
                    "default": 0.0,
                    "min": 0.0,
                    "max": 60.0,
                    "step": 0.5,
                    "tooltip": "Duration in seconds. 0 = auto-calculate from BPM/bars (or default 10s). "
                               "Max 60s. Only used when no_llm_mode = 'foundation1'.",
                }),
                "f1_steps": ("INT", {
                    "default": 100,
                    "min": 10,
                    "max": 250,
                    "step": 10,
                    "tooltip": "Number of diffusion steps. Higher = better quality but slower. "
                               "100 is a good default. Only used when no_llm_mode = 'foundation1'.",
                }),
                "f1_cfg_scale": ("FLOAT", {
                    "default": 7.0,
                    "min": 1.0,
                    "max": 15.0,
                    "step": 0.5,
                    "tooltip": "Classifier-free guidance scale. Higher = follows prompt more closely. "
                               "7.0 is a good default. Only used when no_llm_mode = 'foundation1'.",
                }),
                "f1_style_transfer": ("BOOLEAN", {
                    "default": False,
                    "tooltip": "Enable audio style transfer mode. "
                               "When on, Foundation-1 takes connected audio_a input and re-styles it "
                               "based on the text prompt — like img2img but for audio. "
                               "Requires audio_a to be connected. "
                               "Only used when no_llm_mode = 'foundation1'.",
                }),
                "f1_noise_level": ("FLOAT", {
                    "default": 0.7,
                    "min": 0.0,
                    "max": 1.0,
                    "step": 0.05,
                    "tooltip": "Style transfer strength. "
                               "0.0 = keep original audio (no change), "
                               "0.3 = subtle variation, "
                               "0.7 = strong restyling (default), "
                               "1.0 = fully regenerate (ignore source). "
                               "Only used when f1_style_transfer is enabled.",
                }),

                # ── Advanced: Fish Speech TTS controls ──────────────────────
                "fish_model_variant": (["bf16", "fp8"], {
                    "default": "bf16",
                    "tooltip": "Fish Speech model precision. "
                               "'fp8' = FP8 quantized (~12 GB VRAM, recommended). "
                               "'bf16' = full BF16 precision (~24 GB VRAM). "
                               "Only used when no_llm_mode = 'fish_speech'.",
                }),
                "fish_voice": ("STRING", {
                    "default": "",
                    "multiline": False,
                    "placeholder": "Voice name or path to .wav reference",
                    "tooltip": "Voice reference for cloning. Enter a name from the voice library "
                               "(models/fish_speech/voices/) or a path to a .wav file (10-30s). "
                               "Leave empty for default voice. "
                               "Only used when no_llm_mode = 'fish_speech'.",
                }),
                "fish_emotion": (["(none)", "[happy]", "[sad]", "[angry]", "[excited]", "[whisper]", "[shouting]", "[laughing]", "[laughing tone]", "[chuckling]", "[chuckle]", "[crying]", "[singing]", "[pause]", "[short pause]", "[breath]", "[inhale]", "[exhale]", "[emphasis]", "[sigh]", "[tsk]", "[nervous]", "[calm]", "[serious]", "[cheerful]", "[sarcastic]", "[surprised]", "[shocked]", "[disgusted]", "[fearful]", "[tender]", "[delight]", "[monotone]", "[interrupting]", "[fast]", "[slow]", "[loud]", "[soft]", "[low voice]", "[volume up]", "[volume down]", "[echo]", "[panting]", "[clearing throat]", "[audience laughter]", "[with strong accent]"], {
                    "default": "(none)",
                    "tooltip": "Emotion/prosody tag prepended to the text. "
                               "Fish Speech supports 15K+ inline tags — including free-form "
                               "descriptions like '[whisper in small voice]' or "
                               "'[professional broadcast tone]'. Type tags directly in the prompt "
                               "for fine-grained control. Only used when no_llm_mode = 'fish_speech'.",
                }),
                "fish_temperature": ("FLOAT", {
                    "default": 0.8,
                    "min": 0.1,
                    "max": 1.0,
                    "step": 0.05,
                    "tooltip": "Sampling temperature for Fish Speech. "
                               "Lower = more deterministic, higher = more varied. "
                               "Only used when no_llm_mode = 'fish_speech'.",
                }),
                "fish_top_p": ("FLOAT", {
                    "default": 0.8,
                    "min": 0.1,
                    "max": 1.0,
                    "step": 0.05,
                    "tooltip": "Top-p (nucleus) sampling for Fish Speech. "
                               "Only used when no_llm_mode = 'fish_speech'.",
                }),
                "fish_repetition_penalty": ("FLOAT", {
                    "default": 1.1,
                    "min": 1.0,
                    "max": 2.0,
                    "step": 0.05,
                    "tooltip": "Repetition penalty for Fish Speech. "
                               "Higher values reduce repetitive patterns. "
                               "Only used when no_llm_mode = 'fish_speech'.",
                }),

                # ── Advanced: LivePortrait expression controls ─────────────
                "lp_rotate_pitch": ("FLOAT", {
                    "default": 0.0, "min": -20.0, "max": 20.0, "step": 0.5,
                    "tooltip": "Head pitch (nod up/down). Only for animate_portrait mode.",
                }),
                "lp_rotate_yaw": ("FLOAT", {
                    "default": 0.0, "min": -20.0, "max": 20.0, "step": 0.5,
                    "tooltip": "Head yaw (turn left/right). Only for animate_portrait mode.",
                }),
                "lp_rotate_roll": ("FLOAT", {
                    "default": 0.0, "min": -20.0, "max": 20.0, "step": 0.5,
                    "tooltip": "Head roll (tilt left/right). Only for animate_portrait mode.",
                }),
                "lp_blink": ("FLOAT", {
                    "default": 0.0, "min": -20.0, "max": 5.0, "step": 0.5,
                    "tooltip": "Eye blink (negative=close, positive=open). Only for animate_portrait mode.",
                }),
                "lp_eyebrow": ("FLOAT", {
                    "default": 0.0, "min": -10.0, "max": 15.0, "step": 0.5,
                    "tooltip": "Eyebrow raise/lower. Only for animate_portrait mode.",
                }),
                "lp_wink": ("FLOAT", {
                    "default": 0.0, "min": 0.0, "max": 25.0, "step": 0.5,
                    "tooltip": "Wink intensity. Only for animate_portrait mode.",
                }),
                "lp_pupil_x": ("FLOAT", {
                    "default": 0.0, "min": -15.0, "max": 15.0, "step": 0.5,
                    "tooltip": "Pupil horizontal (negative=left). Only for animate_portrait mode.",
                }),
                "lp_pupil_y": ("FLOAT", {
                    "default": 0.0, "min": -15.0, "max": 15.0, "step": 0.5,
                    "tooltip": "Pupil vertical (negative=up). Only for animate_portrait mode.",
                }),
                "lp_aaa": ("FLOAT", {
                    "default": 0.0, "min": -30.0, "max": 120.0, "step": 1.0,
                    "tooltip": "Mouth open (aaa shape). Only for animate_portrait mode.",
                }),
                "lp_eee": ("FLOAT", {
                    "default": 0.0, "min": -20.0, "max": 15.0, "step": 0.5,
                    "tooltip": "Mouth eee shape. Only for animate_portrait mode.",
                }),
                "lp_woo": ("FLOAT", {
                    "default": 0.0, "min": -20.0, "max": 15.0, "step": 0.5,
                    "tooltip": "Mouth woo/pucker shape. Only for animate_portrait mode.",
                }),
                "lp_smile": ("FLOAT", {
                    "default": 0.0, "min": -0.3, "max": 1.3, "step": 0.05,
                    "tooltip": "Smile intensity. Only for animate_portrait mode.",
                }),
                "lp_retargeting_eyes": ("FLOAT", {
                    "default": 1.0, "min": 0.0, "max": 1.0, "step": 0.05,
                    "tooltip": "Eye retargeting (0=ignore driver eyes, 1=full). Only for animate_portrait mode.",
                }),
                "lp_retargeting_mouth": ("FLOAT", {
                    "default": 1.0, "min": 0.0, "max": 1.0, "step": 0.05,
                    "tooltip": "Mouth retargeting (0=ignore driver mouth, 1=full). Only for animate_portrait mode.",
                }),
                "lp_crop_factor": ("FLOAT", {
                    "default": 1.6, "min": 1.0, "max": 3.0, "step": 0.1,
                    "tooltip": "Face crop expansion (larger=more context). Only for animate_portrait mode.",
                }),
                "lp_expression_preset": (["none"] + _get_expression_presets(), {
                    "default": "none",
                    "tooltip": "Load a saved expression preset. Overrides expression sliders with stored values. "
                               "Only for animate_portrait mode.",
                }),
                "lp_save_expression": ("STRING", {
                    "default": "",
                    "multiline": False,
                    "placeholder": "Enter name to save current sliders",
                    "tooltip": "Type a preset name and run to save current expression slider values. "
                               "Only for animate_portrait mode.",
                }),
                # ── Advanced: LivePortrait expression transfer ────────────
                "lp_sample_image": ("STRING", {
                    "default": "",
                    "multiline": False,
                    "placeholder": "Path to face image for expression transfer",
                    "tooltip": "Sample face image whose expression will be transferred to the source. "
                               "Only for animate_portrait mode.",
                }),
                "lp_sample_ratio": ("FLOAT", {
                    "default": 1.0, "min": 0.0, "max": 1.0, "step": 0.05,
                    "tooltip": "Expression transfer blend ratio (0=source expression, 1=full sample expression). "
                               "Only for animate_portrait mode.",
                }),
                "lp_sample_parts": (["all", "mouth_only", "eyes_only", "rotation_only"], {
                    "default": "all",
                    "tooltip": "Which parts to transfer: all, mouth_only, eyes_only, or rotation_only. "
                               "Only for animate_portrait mode.",
                }),

                # ── Advanced: Batch processing ────────────────────────────
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

                # ── Advanced: Usage tracking & downloads ──────────────────
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
            },
            "hidden": {
                "hidden_prompt": "PROMPT",
                "extra_pnginfo": "EXTRA_PNGINFO",
                "unique_id": "UNIQUE_ID",
            },
        }

    RETURN_TYPES = ("IMAGE", "AUDIO", "STRING", "STRING", "STRING", "STRING", "STRING", "MASK")
    RETURN_NAMES = ("images", "audio", "video_path", "command_log", "analysis", "mask_overlay_path", "mask_points", "mask")
    OUTPUT_TOOLTIPS = (
        "Image frames from the output video. Returns ALL frames automatically when connected to a downstream node (e.g. VHS Video Combine). Returns only a thumbnail when unconnected (zero-memory preview).",
        "Audio extracted from the output video (or passed through from audio_a) in ComfyUI AUDIO format.",
        "Absolute path to the rendered output video file.",
        "The ffmpeg command that was executed.",
        "LLM interpretation, estimated changes, pipeline steps, and any warnings.",
        "Path to a mask overlay preview video with SAM3-style colored contours. Connect to Save Video (FFMPEGA) to view the visual overlay.",
        "Pass-through of upstream mask_points JSON data for downstream nodes. Contains click coordinates and labels.",
        "Raw binary MASK tensor for downstream compositing (MatAnyone2, inpainting, etc.). Upstream mask passthrough or empty mask if no mask source.",
    )
    FUNCTION = "process"
    CATEGORY = "FFMPEGA"
    DESCRIPTION = "AI-powered video editor: describe edits in natural language and the agent generates and runs the ffmpeg pipeline automatically."
    OUTPUT_NODE = True

    def __init__(self):
        """Initialize the agent node."""
        self._analyzer = None
        self._process_manager = None
        self._registry = None
        self._composer = None
        self._preview_generator = None
        self._media_converter = None
        self._pipeline_generator = None

    @property
    def analyzer(self):
        if self._analyzer is None:
            from ..core.video.analyzer import VideoAnalyzer  # type: ignore[import-not-found]
            self._analyzer = VideoAnalyzer()
        return self._analyzer

    @property
    def process_manager(self):
        if self._process_manager is None:
            from ..core.executor.process_manager import ProcessManager  # type: ignore[import-not-found]
            self._process_manager = ProcessManager()
        return self._process_manager

    @property
    def registry(self):
        if self._registry is None:
            from ..skills.registry import get_registry  # type: ignore[import-not-found]
            self._registry = get_registry()
        return self._registry

    @property
    def composer(self):
        if self._composer is None:
            from ..skills.composer import SkillComposer  # type: ignore[import-not-found]
            self._composer = SkillComposer(self.registry)
        return self._composer

    @property
    def preview_generator(self):
        if self._preview_generator is None:
            from ..core.executor.preview import PreviewGenerator  # type: ignore[import-not-found]
            self._preview_generator = PreviewGenerator()
        return self._preview_generator

    @property
    def media_converter(self):
        if self._media_converter is None:
            from ..core.media_converter import MediaConverter  # type: ignore[import-not-found]
            self._media_converter = MediaConverter()
        return self._media_converter

    @property
    def pipeline_generator(self):
        if self._pipeline_generator is None:
            from ..core.pipeline_generator import PipelineGenerator  # type: ignore[import-not-found]
            self._pipeline_generator = PipelineGenerator(self.registry)
        return self._pipeline_generator

    # ------------------------------------------------------------------ #
    #  Private helpers extracted from process()                           #
    # ------------------------------------------------------------------ #

    def _resolve_inputs(self, video_path, images_a, image_a, image_path_a, video_a, text_a, subtitle_path, audio_a, **kwargs):
        """Delegate to input_resolver module."""
        return _ir.resolve_inputs(self.media_converter, video_path, images_a, image_a, image_path_a, video_a, text_a, subtitle_path, audio_a, **kwargs)

    def _build_connected_inputs_summary(self, images_a, _images_a_shape, video_path, audio_a, image_a, _all_video_paths, _all_image_paths, _all_text_inputs, video_metadata, **kwargs):
        """Delegate to input_resolver module."""
        return _ir.build_connected_inputs_summary(images_a, _images_a_shape, video_path, audio_a, image_a, _all_video_paths, _all_image_paths, _all_text_inputs, video_metadata, **kwargs)

    def _build_output_path(self, effective_video_path, save_output, output_path, preview_mode):
        """Delegate to output_handler module."""
        return _oh.build_output_path(effective_video_path, save_output, output_path, preview_mode)

    def _inject_extra_inputs(
        self,
        pipeline,
        effective_video_path: str,
        image_a,
        _all_image_paths: list,
        _all_video_paths: list,
        _all_text_inputs: list,
        audio_a,
        **kwargs,
    ):
        """Inject multi-input tensors/paths into the pipeline's extra_inputs.

        Handles: video tensors, image tensors, video file paths, image file
        paths. Converts tensors to temp files and releases them immediately to
        keep peak memory low. Also handles audio muxing for concat/xfade.

        Returns
        -------
        tuple of:
            effective_video_path (str),      -- may be updated by COW copy
            temp_multi_videos (list[str]),
            temp_audio_files (list[str]),
            temp_frames_dirs (set[str]),
            temp_audio_input (str | None),
        """

        temp_multi_videos = []
        temp_audio_files = []
        temp_frames_dirs = set()
        temp_audio_input = None

        # --- replace_audio: save audio_a as input [1] ---
        has_replace_audio = any(s.skill_name == "replace_audio" for s in pipeline.steps)
        if has_replace_audio and audio_a is not None:
            try:
                waveform = audio_a["waveform"]
                sample_rate = audio_a["sample_rate"]
                channels = waveform.size(1)
                audio_data = waveform.squeeze(0).transpose(0, 1).contiguous()
                audio_bytes = (audio_data * 32767.0).clamp(-32768, 32767).to(torch.int16).numpy().tobytes()
                import subprocess
                _tmp_wav = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
                _tmp_wav.close()
                subprocess.run(
                    ["ffmpeg", "-y", "-f", "s16le", "-ar", str(sample_rate),
                     "-ac", str(channels), "-i", "-", _tmp_wav.name],
                    input=audio_bytes, capture_output=True,
                )
                pipeline.extra_inputs.insert(0, _tmp_wav.name)
                temp_audio_input = _tmp_wav.name
                logger.debug("Saved audio_a as temp WAV for replace_audio: %s", _tmp_wav.name)
            except Exception as e:
                logger.warning("Could not save audio_a for replace_audio: %s", e)

        # --- Multi-input frame extraction ---
        MULTI_INPUT_SKILLS = {
            "grid", "slideshow", "overlay_image", "overlay",
            "concat", "split_screen", "watermark", "chromakey",
            "xfade", "transition", "animated_overlay", "moving_overlay",
            "picture_in_picture", "pip", "blend", "onion_skin",
            "picture-in-picture", "pictureinpicture",
        }
        needs_multi_input = any(s.skill_name in MULTI_INPUT_SKILLS for s in pipeline.steps)

        if needs_multi_input:
            all_frame_paths = []

            if _all_video_paths:
                all_frame_paths.extend(_all_video_paths)
                logger.debug("File-path video inputs (zero memory): %s", _all_video_paths)

            _SEGMENT_SKILLS = {"xfade", "slideshow", "concat"}
            _OVERLAY_SKILLS = {"overlay_image", "overlay", "watermark", "animated_overlay", "moving_overlay"}
            _pipeline_skill_names = {
                self.composer.SKILL_ALIASES.get(s.skill_name, s.skill_name)
                for s in pipeline.steps
            }
            _has_overlay = bool(_pipeline_skill_names & _OVERLAY_SKILLS)
            _has_segments = bool(_pipeline_skill_names & _SEGMENT_SKILLS)
            _images_are_segments = _has_segments and not _has_overlay

            if _all_image_paths:
                if _images_are_segments:
                    all_frame_paths.extend(_all_image_paths)
                    logger.debug("Image paths routed as segments: %s", _all_image_paths)
                else:
                    pipeline.metadata["_image_paths"] = _all_image_paths
                    logger.debug("Image paths routed for overlay: %s", _all_image_paths)

            # Collect image/video tensors
            all_image_keys = []
            if image_a is not None:
                all_image_keys.append(('__image_a__', image_a))
            for k in sorted(kwargs):
                if (k.startswith("image_") and not k.startswith("images_")
                        and not k.startswith("image_path_") and kwargs[k] is not None):
                    all_image_keys.append((k, kwargs[k]))
            for k in sorted(kwargs):
                if k.startswith("images_") and kwargs[k] is not None:
                    all_image_keys.append((k, kwargs[k]))

            for ti, (tkey, tensor) in enumerate(all_image_keys):
                logger.debug("Multi-input tensor %d (%s): shape=%s", ti, tkey, tensor.shape)
                if tensor.shape[0] > 10:
                    tmp_vid = self.media_converter.images_to_video(tensor)
                    all_frame_paths.append(tmp_vid)
                    temp_multi_videos.append(tmp_vid)
                    try:
                        import subprocess as _sp
                        _dur = _sp.run(
                            ["ffprobe", "-v", "error", "-show_entries",
                             "format=duration", "-of", "default=noprint_wrappers=1", tmp_vid],
                            capture_output=True, text=True,
                        )
                        logger.debug("Temp video %s: %s, size=%d",
                                     tmp_vid, _dur.stdout.strip(), os.path.getsize(tmp_vid))
                    except Exception:
                        pass
                else:
                    paths = self.media_converter.save_frames_as_images(tensor)
                    all_frame_paths.extend(paths)
                    if paths:
                        temp_frames_dirs.add(os.path.dirname(paths[0]))
                all_image_keys[ti] = (tkey, None)
                del tensor
                if tkey == '__image_a__':
                    image_a = None
                elif tkey in kwargs:
                    kwargs[tkey] = None

            del all_image_keys
            try:
                import torch as _torch
                if _torch.cuda.is_available():
                    _torch.cuda.empty_cache()
            except Exception:
                pass

            if all_frame_paths:
                existing = pipeline.extra_inputs or []
                pipeline.extra_inputs = existing + all_frame_paths
                pipeline.metadata["frame_count"] = len(all_frame_paths)

        # Attach text inputs
        if _all_text_inputs:
            pipeline.text_inputs = _all_text_inputs

        # Auto-set include_video for slideshow/grid.
        # A "real video" means the pipeline has at least one multi-frame input
        # (the primary video path, any extra video file paths, or a tensor with
        # enough frames to constitute a video).
        _tensor_has_many_frames = (
            image_a is not None
            and hasattr(image_a, 'shape')
            and len(image_a.shape) >= 1
            and image_a.shape[0] > 10
        )
        _extra_images_have_many_frames = any(
            v is not None
            and hasattr(v, 'shape')
            and len(v.shape) >= 1
            and v.shape[0] > 10
            for k, v in kwargs.items()
            if k.startswith("images_")
        )
        has_real_video = (
            len(_all_video_paths) > 0
            or _tensor_has_many_frames
            or _extra_images_have_many_frames
        )
        for step in pipeline.steps:
            if step.skill_name in ("slideshow", "grid"):
                step.params["include_video"] = has_real_video

        # --- Multi-audio muxing for concat/xfade ---
        if needs_multi_input:
            all_audio_dicts = []
            if audio_a is not None:
                all_audio_dicts.append(audio_a)
            for k in sorted(kwargs):
                if k.startswith("audio_") and k != "audio_a" and kwargs[k] is not None:
                    all_audio_dicts.append(kwargs[k])

            _tmpdir = tempfile.gettempdir()

            def _ensure_temp_copy(filepath: str) -> str:
                if not filepath or not os.path.isfile(filepath):
                    return filepath
                if os.path.commonpath([filepath, _tmpdir]) == _tmpdir:
                    return filepath
                ext = os.path.splitext(filepath)[1] or ".mp4"
                tmp = tempfile.NamedTemporaryFile(suffix=ext, delete=False)
                tmp.close()
                import shutil as _shutil
                _shutil.copy2(filepath, tmp.name)
                return tmp.name

            if all_audio_dicts or any(s.skill_name in ("concat", "xfade") for s in pipeline.steps):
                new_evp = _ensure_temp_copy(effective_video_path)
                if new_evp != effective_video_path:
                    effective_video_path = new_evp
                pipeline.extra_inputs = [_ensure_temp_copy(ep) for ep in pipeline.extra_inputs]
                pipeline.input_path = effective_video_path

            if all_audio_dicts:
                video_segments = [effective_video_path] + list(pipeline.extra_inputs)
                for ai, audio_dict in enumerate(all_audio_dicts):
                    if ai >= len(video_segments):
                        break
                    vid_path = video_segments[ai]
                    if not os.path.isfile(vid_path):
                        continue
                    if self.media_converter.has_audio_stream(vid_path):
                        continue
                    try:
                        self.media_converter.mux_audio(vid_path, audio_dict)
                    except Exception as e:
                        logger.warning("Could not mux audio %d into %s: %s", ai, vid_path, e)

            _vid_exts = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv", ".wmv", ".ts", ".m4v"}
            video_segments = [
                p for p in [effective_video_path] + list(pipeline.extra_inputs)
                if p and os.path.splitext(p)[1].lower() in _vid_exts
            ]

            is_audio_filter_skill = any(s.skill_name in ("concat", "xfade") for s in pipeline.steps)
            if is_audio_filter_skill:
                for vid_path in video_segments:
                    if not os.path.isfile(vid_path):
                        continue
                    if not self.media_converter.has_audio_stream(vid_path):
                        try:
                            self.media_converter.add_silent_audio(vid_path)
                        except Exception as e:
                            logger.warning("Could not add silent audio to %s: %s", vid_path, e)
                audio_segment_count = sum(
                    1 for vp in video_segments
                    if os.path.isfile(vp) and self.media_converter.has_audio_stream(vp)
                )
                if audio_segment_count >= 2:
                    pipeline.metadata["_has_embedded_audio"] = True

        # --- Transcription audio input path ---
        _TRANSCRIBE_SKILLS = {
            "auto_transcribe", "transcribe", "speech_to_text",
            "karaoke_subtitles", "whisper", "auto_subtitle", "auto_caption",
        }
        has_transcribe_skill = any(s.skill_name in _TRANSCRIBE_SKILLS for s in pipeline.steps)
        if has_transcribe_skill and audio_a is not None:
            audio_wav_path = self._audio_dict_to_wav(audio_a)
            if audio_wav_path:
                pipeline.metadata["_audio_input_path"] = audio_wav_path
                temp_audio_files.append(audio_wav_path)
                logger.info("Transcription will use connected audio_a input: %s", audio_wav_path)

        # --- Lip sync audio input path ---
        _LIP_SYNC_SKILLS = {
            "lip_sync", "lipsync", "dub", "dubbing",
            "sync_lips", "talking_head", "lip_dub", "voice_sync",
        }
        has_lip_sync_skill = any(s.skill_name in _LIP_SYNC_SKILLS for s in pipeline.steps)
        if has_lip_sync_skill and audio_a is not None:
            audio_wav_path = self._audio_dict_to_wav(audio_a)
            if audio_wav_path:
                for step in pipeline.steps:
                    if step.skill_name in _LIP_SYNC_SKILLS:
                        step.params["audio_path"] = audio_wav_path
                temp_audio_files.append(audio_wav_path)
                logger.info("Lip sync will use connected audio_a input: %s", audio_wav_path)

        return (
            effective_video_path,
            temp_multi_videos,
            temp_audio_files,
            temp_frames_dirs,
            temp_audio_input,
        )

    async def _execute_pipeline(self, pipeline, command, connector, prompt, metadata_str, connected_inputs_str, effective_video_path, output_path, quality_preset, crf, encoding_preset, preview_mode, verify_output, use_vision, ptc_mode, video_metadata, _all_text_inputs):
        """Delegate to execution_engine module."""
        return await _ee.execute_pipeline(
            pipeline=pipeline, command=command, connector=connector,
            composer=self.composer, process_manager=self.process_manager,
            pipeline_generator=self.pipeline_generator,
            prompt=prompt, metadata_str=metadata_str,
            connected_inputs_str=connected_inputs_str,
            effective_video_path=effective_video_path, output_path=output_path,
            quality_preset=quality_preset, crf=crf,
            encoding_preset=encoding_preset, preview_mode=preview_mode,
            verify_output=verify_output, use_vision=use_vision,
            ptc_mode=ptc_mode, video_metadata=video_metadata,
            _all_text_inputs=_all_text_inputs,
        )

    def _handle_audio_output(self, command, pipeline, audio_a, audio_source, audio_mode, output_path, **kwargs):
        """Delegate to output_handler module."""
        return _oh.handle_audio_output(command, pipeline, self.media_converter, audio_a, audio_source, audio_mode, output_path, **kwargs)

    def _collect_frame_output(self, output_path, unique_id, hidden_prompt, removes_audio, resample_rate=None):
        """Delegate to output_handler module."""
        return _oh.collect_frame_output(self.media_converter, output_path, unique_id, hidden_prompt, removes_audio, resample_rate=resample_rate)

    # ------------------------------------------------------------------ #
    #  Main entry point                                                   #
    # ------------------------------------------------------------------ #

    async def process(
        self,
        video_path: str,
        prompt: str,
        llm_model: str,
        quality_preset: str,
        seed: int = 0,
        no_llm_mode: str = "manual",
        images_a: Optional[torch.Tensor] = None,
        image_a: Optional[torch.Tensor] = None,
        audio_a: Optional[dict] = None,
        video_a: str = "",
        image_path_a: str = "",
        text_a: str = "",
        pipeline_json: str = "",
        advanced_options: bool = False,
        subtitle_path: str = "",
        preview_mode: bool = False,
        save_output: bool = False,
        output_path: str = "",
        ollama_url: str = "http://localhost:11434",
        api_key: str = "",
        custom_model: str = "",
        crf: int = -1,
        encoding_preset: str = "auto",
        use_vision: bool = False,
        ptc_mode: str = "off",
        verify_output: bool = False,
        whisper_device: str = "cpu",
        whisper_model: str = "large-v3",
        sam3_device: str = "gpu",
        sam3_max_objects: int = 5,
        sam3_det_threshold: float = 0.7,
        mask_points: str = "",
        mask=None,
        crop_data: str = "",
        use_flux_klein: bool = False,
        use_kiwi_edit: bool = False,
        use_minimax_remover: bool = False,
        use_dreamid_omni: bool = False,
        flux_smoothing: str = "none",
        audio_output_mode: str = "auto",
        audio_resample_rate: str = "off",
        ace_negative_prompt: str = "",
        ace_cover_strength: float = 0.5,
        ace_steps: int = 8,
        ace_cfg_scale: float = 7.0,
        ace_bpm: str = "",
        ace_key: str = "",
        ace_time_sig: str = "",
        f1_preset: str = "none",
        f1_instrument: str = "none",
        f1_fx: str = "none",
        f1_structure: str = "none",
        f1_negative_prompt: str = "",
        f1_bpm: str = "auto",
        f1_bars: str = "auto",
        f1_key: str = "",
        f1_duration: float = 0.0,
        f1_steps: int = 100,
        f1_cfg_scale: float = 7.0,
        f1_style_transfer: bool = False,
        f1_noise_level: float = 0.7,
        batch_mode: bool = False,
        video_folder: str = "",
        file_pattern: str = "*.mp4",
        max_concurrent: int = 4,
        track_tokens: bool = True,
        log_usage: bool = False,
        allow_model_downloads: bool = True,
        fish_model_variant: str = "bf16",
        fish_voice: str = "",
        fish_emotion: str = "(none)",
        fish_temperature: float = 0.8,
        fish_top_p: float = 0.8,
        fish_repetition_penalty: float = 1.1,
        **kwargs,  # hidden: prompt (PROMPT dict), extra_pnginfo (EXTRA_PNGINFO)
    ) -> tuple[torch.Tensor, dict, str, str, str, str, str, torch.Tensor]:
        """Process the video based on the natural language prompt.

        Args:
            video_path: Path to input video.
            prompt: Natural language editing instruction.
            llm_model: LLM model to use.
            quality_preset: Output quality preset.
            images_a: First video input as IMAGE tensor from upstream nodes.
            audio_a: Optional input AUDIO dict from upstream nodes.
            preview_mode: Generate preview instead of full render.
            output_path: Custom output path.
            ollama_url: Ollama server URL.
            api_key: API key for cloud providers.
            crf: Override CRF value (-1 = use preset).
            encoding_preset: Override encoding preset ("auto" = use preset).

        Returns:
            Tuple of (images_tensor, audio, output_video_path, command_log, analysis).
        """
        from ..skills.composer import Pipeline  # type: ignore[import-not-found]

        # --- Apply model-download permission flag ---
        try:
            from ..core import model_manager  # type: ignore[import-not-found]
        except ImportError:
            from core import model_manager  # type: ignore
        model_manager.set_downloads_allowed(allow_model_downloads)

        # Mask pass-through: upstream mask or empty fallback
        empty_mask = mask if mask is not None else torch.zeros(1, 64, 64, dtype=torch.float32)

        # --- Inject FFMPEGA Effects Builder pipeline if provided ---
        # Save the raw prompt BEFORE injecting effects hints — the hint
        # text appended by inject_effects_hints corrupts SAM3's text-based
        # grounding detector (it can't parse multi-line hint blocks).
        _raw_prompt = prompt
        if pipeline_json and pipeline_json.strip():
            prompt = _nollm.inject_effects_hints(prompt, pipeline_json)

        # --- Batch mode ---
        if batch_mode:
            result6 = await self._process_batch(
                video_folder=video_folder,
                file_pattern=file_pattern,
                prompt=prompt,
                llm_model=llm_model,
                quality_preset=quality_preset,
                ollama_url=ollama_url,
                api_key=api_key,
                custom_model=custom_model,
                crf=crf,
                encoding_preset=encoding_preset,
                max_concurrent=max_concurrent,
                save_output=save_output,
                output_path=output_path,
                use_vision=use_vision,
                verify_output=verify_output,
                ptc_mode=ptc_mode,
                sam3_max_objects=sam3_max_objects,
                sam3_det_threshold=sam3_det_threshold,
                mask_points=mask_points,
                use_flux_klein=use_flux_klein,
                use_kiwi_edit=use_kiwi_edit,
                use_minimax_remover=use_minimax_remover,
                flux_smoothing=flux_smoothing,
                pipeline_json=pipeline_json,
            )
            return result6 + (mask_points or "", empty_mask)

        # --- Foundation-1 (audio-only, no video resolution needed) ---
        if no_llm_mode == "foundation1":
            result6 = await self._process_foundation1_only(
                prompt=prompt,
                audio_output_mode=audio_output_mode,
                effective_video_path=video_path or "",
                video_metadata=None,
                save_output=save_output,
                output_path=output_path,
                preview_mode=preview_mode,
                quality_preset=quality_preset,
                crf=crf,
                encoding_preset=encoding_preset,
                temp_video_from_images=None,
                temp_video_with_audio=None,
                f1_preset=f1_preset,
                f1_instrument=f1_instrument,
                f1_fx=f1_fx,
                f1_structure=f1_structure,
                f1_negative_prompt=f1_negative_prompt,
                f1_bpm=f1_bpm,
                f1_bars=f1_bars,
                f1_key=f1_key,
                f1_duration=f1_duration,
                f1_steps=f1_steps,
                f1_cfg_scale=f1_cfg_scale,
                f1_style_transfer=f1_style_transfer,
                f1_noise_level=f1_noise_level,
                audio_a=audio_a,
                **kwargs,
            )
            return result6 + (mask_points or "", empty_mask)

        # --- Fish Speech TTS (audio-only, no video resolution needed) ---
        if no_llm_mode == "fish_speech":
            result6 = await self._process_fish_speech_only(
                prompt=prompt,
                audio_output_mode=audio_output_mode,
                effective_video_path=video_path or "",
                video_metadata=None,
                save_output=save_output,
                output_path=output_path,
                preview_mode=preview_mode,
                quality_preset=quality_preset,
                crf=crf,
                encoding_preset=encoding_preset,
                temp_video_from_images=None,
                temp_video_with_audio=None,
                fish_model_variant=fish_model_variant,
                fish_voice=fish_voice,
                fish_emotion=fish_emotion,
                fish_temperature=fish_temperature,
                fish_top_p=fish_top_p,
                fish_repetition_penalty=fish_repetition_penalty,
                audio_a=audio_a,
                **kwargs,
            )
            return result6 + (mask_points or "", empty_mask)

        # --- Resolve inputs ---
        (
            effective_video_path,
            temp_video_from_images,
            temp_video_with_audio,
            _all_video_paths,
            _all_image_paths,
            _all_text_inputs,
            _images_a_shape,
        ) = self._resolve_inputs(
            video_path=video_path,
            images_a=images_a,
            image_a=image_a,
            image_path_a=image_path_a,
            video_a=video_a,
            text_a=text_a,
            subtitle_path=subtitle_path,
            audio_a=audio_a,
            **kwargs,
        )
        images_a = None

        # --- Apply crop if crop_data is provided ---
        if crop_data and crop_data.strip():
            try:
                from ..videoeditor.processing.crop import apply_crop
                import tempfile as _crop_tmp
                _crop_out = _crop_tmp.NamedTemporaryFile(
                    suffix=".mp4", delete=False,
                )
                _crop_out.close()
                cropped = apply_crop(
                    effective_video_path, crop_data, _crop_out.name,
                )
                if cropped != effective_video_path:
                    logger.info(
                        "Applied crop %s → %s", crop_data.strip(), cropped,
                    )
                    effective_video_path = cropped
                else:
                    # Crop wasn't applied (e.g. invalid rect), clean up
                    try:
                        os.unlink(_crop_out.name)
                    except OSError:
                        pass
            except Exception as e:
                logger.warning("Could not apply crop_data: %s", e)

        if not prompt.strip():
            # manual + whisper + lip_sync modes don't need a prompt
            if llm_model != "none" or no_llm_mode not in ("manual", "transcribe", "karaoke_subtitles", "generate_audio", "generate_music", "foundation1", "fish_speech", "audio_inpaint", "audio_separate", "ace_step", "lip_sync", "animate_portrait", "marigold", "normalcrafter", "video_depth", "kiwi_edit", "minimax_remover", "dreamid_omni", "scail (WIP)", "ai_upscale", "rembg", "video_matting", "onion_skin"):
                raise ValueError("Prompt cannot be empty")

        # --- Analyze input video ---
        video_metadata = self.analyzer.analyze(effective_video_path)
        metadata_str = video_metadata.to_analysis_string()

        # ================================================================== #
        #  No-LLM mode — bypass pipeline generation entirely                #
        # ================================================================== #
        if llm_model == "none":
            # Effects Builder connected → execute its pipeline directly
            # When sam3_masking mode is active, wrap visual effects as
            # auto_mask steps so they apply to the SAM3-masked region.
            if pipeline_json and pipeline_json.strip():
                _effective_pipeline_json = pipeline_json
                if no_llm_mode == "sam3_masking":
                    _effective_pipeline_json = _nollm.merge_sam3_into_effects_pipeline(
                        pipeline_json, _raw_prompt,
                    )
                    logger.info(
                        "SAM3 masking + Effects Builder: merged pipeline for target '%s'",
                        _raw_prompt.strip(),
                    )
                result6 = await self._process_effects_pipeline(
                    pipeline_json=_effective_pipeline_json,
                    prompt=prompt,
                    effective_video_path=effective_video_path,
                    video_metadata=video_metadata,
                    save_output=save_output,
                    output_path=output_path,
                    preview_mode=preview_mode,
                    quality_preset=quality_preset,
                    crf=crf,
                    encoding_preset=encoding_preset,
                    whisper_device=whisper_device,
                    whisper_model=whisper_model,
                    sam3_device=sam3_device,
                    sam3_max_objects=sam3_max_objects,
                    sam3_det_threshold=sam3_det_threshold,
                    mask_points=mask_points,
                    use_flux_klein=use_flux_klein,
                    use_kiwi_edit=use_kiwi_edit,
                    use_minimax_remover=use_minimax_remover,
                    use_dreamid_omni=use_dreamid_omni,
                    flux_smoothing=flux_smoothing,
                    temp_video_from_images=temp_video_from_images,
                    temp_video_with_audio=temp_video_with_audio,
                    image_a=image_a,
                    audio_a=audio_a,
                    _all_video_paths=_all_video_paths,
                    _all_image_paths=_all_image_paths,
                    _all_text_inputs=_all_text_inputs,
                    audio_resample_rate=audio_resample_rate,
                    **kwargs,
                )
                return result6 + (mask_points or "", empty_mask)
            # Whisper-only mode (transcribe or karaoke)
            if no_llm_mode in ("transcribe", "karaoke_subtitles"):
                result6 = await self._process_whisper_only(
                    mode=no_llm_mode,
                    effective_video_path=effective_video_path,
                    video_metadata=video_metadata,
                    save_output=save_output,
                    output_path=output_path,
                    preview_mode=preview_mode,
                    quality_preset=quality_preset,
                    crf=crf,
                    encoding_preset=encoding_preset,
                    whisper_device=whisper_device,
                    whisper_model=whisper_model,
                    temp_video_from_images=temp_video_from_images,
                    temp_video_with_audio=temp_video_with_audio,
                    **kwargs,
                )
                return result6 + (mask_points or "", empty_mask)
            # SAM3-only mode (prompt = text target)
            if no_llm_mode == "sam3_masking":
                result6 = await self._process_sam3_only(
                    prompt=prompt,
                    effective_video_path=effective_video_path,
                    video_metadata=video_metadata,
                    save_output=save_output,
                    output_path=output_path,
                    preview_mode=preview_mode,
                    quality_preset=quality_preset,
                    crf=crf,
                    encoding_preset=encoding_preset,
                    sam3_device=sam3_device,
                    sam3_max_objects=sam3_max_objects,
                    sam3_det_threshold=sam3_det_threshold,
                    mask_points=mask_points,
                    temp_video_from_images=temp_video_from_images,
                    temp_video_with_audio=temp_video_with_audio,
                    **kwargs,
                )
                return result6 + (mask_points or "", empty_mask)
            # MMAudio-only mode (generate_audio from video/prompt)
            if no_llm_mode == "generate_audio":
                result6 = await self._process_mmaudio_only(
                    prompt=prompt,
                    audio_output_mode=audio_output_mode,
                    effective_video_path=effective_video_path,
                    video_metadata=video_metadata,
                    save_output=save_output,
                    output_path=output_path,
                    preview_mode=preview_mode,
                    quality_preset=quality_preset,
                    crf=crf,
                    encoding_preset=encoding_preset,
                    temp_video_from_images=temp_video_from_images,
                    temp_video_with_audio=temp_video_with_audio,
                    **kwargs,
                )
                return result6 + (mask_points or "", empty_mask)
            # AudioX music-only mode (generate_music from video/prompt)
            if no_llm_mode == "generate_music":
                result6 = await self._process_audiox_music_only(
                    prompt=prompt,
                    audio_output_mode=audio_output_mode,
                    effective_video_path=effective_video_path,
                    video_metadata=video_metadata,
                    save_output=save_output,
                    output_path=output_path,
                    preview_mode=preview_mode,
                    quality_preset=quality_preset,
                    crf=crf,
                    encoding_preset=encoding_preset,
                    temp_video_from_images=temp_video_from_images,
                    temp_video_with_audio=temp_video_with_audio,
                    **kwargs,
                )
                return result6 + (mask_points or "", empty_mask)
            # AudioX inpaint-only mode (audio_inpaint from video audio)
            if no_llm_mode == "audio_inpaint":
                result6 = await self._process_audiox_inpaint_only(
                    prompt=prompt,
                    audio_output_mode=audio_output_mode,
                    effective_video_path=effective_video_path,
                    video_metadata=video_metadata,
                    save_output=save_output,
                    output_path=output_path,
                    preview_mode=preview_mode,
                    quality_preset=quality_preset,
                    crf=crf,
                    encoding_preset=encoding_preset,
                    temp_video_from_images=temp_video_from_images,
                    temp_video_with_audio=temp_video_with_audio,
                    **kwargs,
                )
                return result6 + (mask_points or "", empty_mask)
            # ACE-Step music generation mode
            if no_llm_mode == "ace_step":
                result6 = await self._process_ace_step_only(
                    prompt=prompt,
                    audio_output_mode=audio_output_mode,
                    effective_video_path=effective_video_path,
                    video_metadata=video_metadata,
                    save_output=save_output,
                    output_path=output_path,
                    preview_mode=preview_mode,
                    quality_preset=quality_preset,
                    crf=crf,
                    encoding_preset=encoding_preset,
                    temp_video_from_images=temp_video_from_images,
                    temp_video_with_audio=temp_video_with_audio,
                    text_a=text_a,
                    audio_a=audio_a,
                    ace_negative_prompt=ace_negative_prompt,
                    ace_cover_strength=ace_cover_strength,
                    ace_steps=ace_steps,
                    ace_cfg_scale=ace_cfg_scale,
                    ace_bpm=ace_bpm,
                    ace_key=ace_key,
                    ace_time_sig=ace_time_sig,
                    **kwargs,
                )
                return result6 + (mask_points or "", empty_mask)
            # SAM-Audio separation mode (isolate sounds from audio)
            if no_llm_mode == "audio_separate":
                result6 = await self._process_sam_audio_separate(
                    prompt=prompt,
                    audio_output_mode=audio_output_mode,
                    effective_video_path=effective_video_path,
                    video_metadata=video_metadata,
                    save_output=save_output,
                    output_path=output_path,
                    preview_mode=preview_mode,
                    quality_preset=quality_preset,
                    crf=crf,
                    encoding_preset=encoding_preset,
                    temp_video_from_images=temp_video_from_images,
                    temp_video_with_audio=temp_video_with_audio,
                    **kwargs,
                )
                return result6 + (mask_points or "", empty_mask)

            # ── SAM3 Pre-Masking for No-LLM Modes ──────────────────
            # When use_sam3 is on and we have a prompt, pre-generate a
            # SAM3 mask before the mode runs. After the mode produces
            # its output, we composite via maskedmerge.
            _SAM3_ELIGIBLE_MODES = {
                "lip_sync", "animate_portrait", "marigold", "normalcrafter",
                "video_depth", "flux_klein", "kiwi_edit", "minimax_remover",
                "ai_upscale", "rembg", "video_matting", "onion_skin", "comparison",
            }
            _use_sam3 = bool(kwargs.pop("use_sam3", False))
            _sam3_mask_path = None
            if _use_sam3 and no_llm_mode in _SAM3_ELIGIBLE_MODES and _raw_prompt.strip():
                _sam3_mask_path = _nollm.sam3_premask(
                    video_path=effective_video_path,
                    prompt=_raw_prompt,
                    sam3_device=sam3_device,
                    sam3_max_objects=sam3_max_objects,
                    sam3_det_threshold=sam3_det_threshold,
                )
                if _sam3_mask_path:
                    logger.info(
                        "SAM3 pre-mask: will composite %s output over original",
                        no_llm_mode,
                    )

            # Lip sync mode (MuseTalk from connected audio_a)
            if no_llm_mode == "lip_sync":
                result6 = await self._process_lip_sync_only(
                    effective_video_path=effective_video_path,
                    video_metadata=video_metadata,
                    save_output=save_output,
                    output_path=output_path,
                    preview_mode=preview_mode,
                    quality_preset=quality_preset,
                    crf=crf,
                    encoding_preset=encoding_preset,
                    audio_a=audio_a,
                    temp_video_from_images=temp_video_from_images,
                    temp_video_with_audio=temp_video_with_audio,
                    **kwargs,
                )
                if _sam3_mask_path and result6[2]:
                    _nollm.sam3_composite(effective_video_path, result6[2], _sam3_mask_path, result6[2])
                return result6 + (mask_points or "", empty_mask)
            # Animate portrait mode (LivePortrait from connected video_a)
            if no_llm_mode == "animate_portrait":
                # video_a is the driving video
                driving_video = _all_video_paths[0] if _all_video_paths else ""

                # Pop expression params from kwargs
                _lp_vals = {
                    "lp_rotate_pitch": float(kwargs.pop("lp_rotate_pitch", 0.0)),
                    "lp_rotate_yaw": float(kwargs.pop("lp_rotate_yaw", 0.0)),
                    "lp_rotate_roll": float(kwargs.pop("lp_rotate_roll", 0.0)),
                    "lp_blink": float(kwargs.pop("lp_blink", 0.0)),
                    "lp_eyebrow": float(kwargs.pop("lp_eyebrow", 0.0)),
                    "lp_wink": float(kwargs.pop("lp_wink", 0.0)),
                    "lp_pupil_x": float(kwargs.pop("lp_pupil_x", 0.0)),
                    "lp_pupil_y": float(kwargs.pop("lp_pupil_y", 0.0)),
                    "lp_aaa": float(kwargs.pop("lp_aaa", 0.0)),
                    "lp_eee": float(kwargs.pop("lp_eee", 0.0)),
                    "lp_woo": float(kwargs.pop("lp_woo", 0.0)),
                    "lp_smile": float(kwargs.pop("lp_smile", 0.0)),
                    "lp_retargeting_eyes": float(kwargs.pop("lp_retargeting_eyes", 1.0)),
                    "lp_retargeting_mouth": float(kwargs.pop("lp_retargeting_mouth", 1.0)),
                    "lp_crop_factor": float(kwargs.pop("lp_crop_factor", 1.6)),
                }
                _lp_preset = str(kwargs.pop("lp_expression_preset", "none"))
                _lp_save = str(kwargs.pop("lp_save_expression", "")).strip()

                # Load preset (overrides slider values)
                if _lp_preset and _lp_preset != "none":
                    try:
                        try:
                            from core.expression_presets import load_expression
                        except ImportError:
                            from ..core.expression_presets import load_expression  # type: ignore
                        preset_data = load_expression(_lp_preset)
                        if preset_data:
                            logger.info("[animate_portrait] Loading preset '%s'", _lp_preset)
                            for key, val in preset_data.items():
                                lp_key = f"lp_{key}" if not key.startswith("lp_") else key
                                if lp_key in _lp_vals:
                                    _lp_vals[lp_key] = float(val)
                    except Exception as e:
                        logger.warning("[animate_portrait] Preset load failed: %s", e)

                # Save current values as preset (if name provided)
                if _lp_save:
                    try:
                        try:
                            from core.expression_presets import save_expression
                        except ImportError:
                            from ..core.expression_presets import save_expression  # type: ignore
                        # Strip lp_ prefix for storage
                        save_data = {k.removeprefix("lp_"): v for k, v in _lp_vals.items()}
                        save_expression(_lp_save, save_data)
                        logger.info("[animate_portrait] Saved preset '%s'", _lp_save)
                    except Exception as e:
                        logger.warning("[animate_portrait] Preset save failed: %s", e)

                result6 = await self._process_animate_portrait_only(
                    effective_video_path=effective_video_path,
                    video_metadata=video_metadata,
                    save_output=save_output,
                    output_path=output_path,
                    preview_mode=preview_mode,
                    quality_preset=quality_preset,
                    crf=crf,
                    encoding_preset=encoding_preset,
                    driving_video=driving_video,
                    **_lp_vals,
                    lp_sample_image=str(kwargs.pop("lp_sample_image", "")),
                    lp_sample_ratio=float(kwargs.pop("lp_sample_ratio", 1.0)),
                    lp_sample_parts=str(kwargs.pop("lp_sample_parts", "all")),
                    temp_video_from_images=temp_video_from_images,
                    temp_video_with_audio=temp_video_with_audio,
                    **kwargs,
                )
                if _sam3_mask_path and result6[2]:
                    _nollm.sam3_composite(effective_video_path, result6[2], _sam3_mask_path, result6[2])
                return result6 + (mask_points or "", empty_mask)
            # Marigold mode (dense vision analysis)
            if no_llm_mode == "marigold":
                result6 = await self._process_marigold_only(
                    effective_video_path=effective_video_path,
                    video_metadata=video_metadata,
                    save_output=save_output,
                    output_path=output_path,
                    preview_mode=preview_mode,
                    quality_preset=quality_preset,
                    crf=crf,
                    encoding_preset=encoding_preset,
                    marigold_output_type=kwargs.pop("marigold_output_type", "depth"),
                    marigold_colormap=kwargs.pop("marigold_colormap", "Spectral"),
                    temp_video_from_images=temp_video_from_images,
                    temp_video_with_audio=temp_video_with_audio,
                    **kwargs,
                )
                if _sam3_mask_path and result6[2]:
                    _nollm.sam3_composite(effective_video_path, result6[2], _sam3_mask_path, result6[2])
                return result6 + (mask_points or "", empty_mask)
            # NormalCrafter mode (temporally consistent video normals)
            if no_llm_mode == "normalcrafter":
                result6 = await self._process_normalcrafter_only(
                    effective_video_path=effective_video_path,
                    video_metadata=video_metadata,
                    save_output=save_output,
                    output_path=output_path,
                    preview_mode=preview_mode,
                    quality_preset=quality_preset,
                    crf=crf,
                    encoding_preset=encoding_preset,
                    normalcrafter_max_res=kwargs.pop("normalcrafter_max_res", "auto"),
                    temp_video_from_images=temp_video_from_images,
                    temp_video_with_audio=temp_video_with_audio,
                    **kwargs,
                )
                if _sam3_mask_path and result6[2]:
                    _nollm.sam3_composite(effective_video_path, result6[2], _sam3_mask_path, result6[2])
                return result6 + (mask_points or "", empty_mask)
            # Video Depth Anything mode (temporal depth estimation)
            if no_llm_mode == "video_depth":
                result6 = await self._process_video_depth_only(
                    effective_video_path=effective_video_path,
                    video_metadata=video_metadata,
                    save_output=save_output,
                    output_path=output_path,
                    preview_mode=preview_mode,
                    quality_preset=quality_preset,
                    crf=crf,
                    encoding_preset=encoding_preset,
                    video_depth_encoder=kwargs.pop("video_depth_encoder", "vits"),
                    video_depth_colormap=kwargs.pop("video_depth_colormap", "gray"),
                    temp_video_from_images=temp_video_from_images,
                    temp_video_with_audio=temp_video_with_audio,
                    **kwargs,
                )
                if _sam3_mask_path and result6[2]:
                    _nollm.sam3_composite(effective_video_path, result6[2], _sam3_mask_path, result6[2])
                return result6 + (mask_points or "", empty_mask)
            # MiniMax-Remover mode
            if no_llm_mode == "minimax_remover":
                result6 = await self._process_minimax_remover_only(
                    prompt=prompt,
                    effective_video_path=effective_video_path,
                    video_metadata=video_metadata,
                    save_output=save_output,
                    output_path=output_path,
                    preview_mode=preview_mode,
                    quality_preset=quality_preset,
                    crf=crf,
                    encoding_preset=encoding_preset,
                    temp_video_from_images=temp_video_from_images,
                    temp_video_with_audio=temp_video_with_audio,
                    **kwargs,
                )
                if _sam3_mask_path and result6[2]:
                    _nollm.sam3_composite(effective_video_path, result6[2], _sam3_mask_path, result6[2])
                return result6 + (mask_points or "", empty_mask)
            # FLUX Klein mode
            if no_llm_mode == "flux_klein":
                result6 = await self._process_flux_klein_only(
                    prompt=prompt,
                    effective_video_path=effective_video_path,
                    video_metadata=video_metadata,
                    save_output=save_output,
                    output_path=output_path,
                    preview_mode=preview_mode,
                    quality_preset=quality_preset,
                    crf=crf,
                    encoding_preset=encoding_preset,
                    flux_smoothing=flux_smoothing,
                    image_a=image_a,
                    _all_image_paths=_all_image_paths,
                    temp_video_from_images=temp_video_from_images,
                    temp_video_with_audio=temp_video_with_audio,
                    **kwargs,
                )
                if _sam3_mask_path and result6[2]:
                    _nollm.sam3_composite(effective_video_path, result6[2], _sam3_mask_path, result6[2])
                return result6 + (mask_points or "", empty_mask)
            # Kiwi-Edit mode (native video editing via instruction/reference)
            if no_llm_mode == "kiwi_edit":
                result6 = await self._process_kiwi_edit_only(
                    prompt=prompt,
                    effective_video_path=effective_video_path,
                    video_metadata=video_metadata,
                    save_output=save_output,
                    output_path=output_path,
                    preview_mode=preview_mode,
                    quality_preset=quality_preset,
                    crf=crf,
                    encoding_preset=encoding_preset,
                    image_a=image_a,
                    _all_image_paths=_all_image_paths,
                    temp_video_from_images=temp_video_from_images,
                    temp_video_with_audio=temp_video_with_audio,
                    **kwargs,
                )
                if _sam3_mask_path and result6[2]:
                    _nollm.sam3_composite(effective_video_path, result6[2], _sam3_mask_path, result6[2])
                return result6 + (mask_points or "", empty_mask)
            # DreamID-Omni mode (identity-preserving talking-head generation)
            if no_llm_mode == "dreamid_omni":
                result6 = await _nollm.process_dreamid_omni_only(
                    prompt=prompt,
                    effective_video_path=effective_video_path,
                    video_metadata=video_metadata,
                    save_output=save_output,
                    output_path=output_path,
                    preview_mode=preview_mode,
                    quality_preset=quality_preset,
                    crf=crf,
                    encoding_preset=encoding_preset,
                    image_a=image_a,
                    audio_a=audio_a,
                    temp_video_from_images=temp_video_from_images,
                    temp_video_with_audio=temp_video_with_audio,
                    **kwargs,
                )
                return result6 + (mask_points or "", empty_mask)
            # SCAIL mode (WIP — pose-driven character animation)
            if no_llm_mode == "scail (WIP)":
                result6 = await _nollm.process_scail_only(
                    prompt=prompt,
                    effective_video_path=effective_video_path,
                    video_metadata=video_metadata,
                    save_output=save_output,
                    output_path=output_path,
                    preview_mode=preview_mode,
                    quality_preset=quality_preset,
                    crf=crf,
                    encoding_preset=encoding_preset,
                    image_a=image_a,
                    image_path_a=image_path_a,
                    **kwargs,
                )
                return result6 + (mask_points or "", empty_mask)
            # AI Upscale mode (spandrel-based super-resolution)
            if no_llm_mode == "ai_upscale":
                result6 = await self._process_ai_upscale_only(
                    effective_video_path=effective_video_path,
                    video_metadata=video_metadata,
                    save_output=save_output,
                    output_path=output_path,
                    preview_mode=preview_mode,
                    quality_preset=quality_preset,
                    crf=crf,
                    encoding_preset=encoding_preset,
                    upscale_model=kwargs.pop("upscale_model", "realesrgan_x4plus"),
                    upscale_scale=int(kwargs.pop("upscale_scale", "4")),
                    tile_size=int(kwargs.pop("tile_size", "512")),
                    blockswap_blocks=int(kwargs.pop("blockswap_blocks", 0)),
                    seedvr_resolution=int(kwargs.pop("seedvr_resolution", "1080")),
                    rtx_quality=kwargs.pop("rtx_quality", "ULTRA"),
                    temp_video_from_images=temp_video_from_images,
                    temp_video_with_audio=temp_video_with_audio,
                    **kwargs,
                )
                if _sam3_mask_path and result6[2]:
                    _nollm.sam3_composite(effective_video_path, result6[2], _sam3_mask_path, result6[2])
                return result6 + (mask_points or "", empty_mask)
            # Rembg background removal mode
            if no_llm_mode == "rembg":
                result6 = await self._process_rembg_only(
                    effective_video_path=effective_video_path,
                    video_metadata=video_metadata,
                    save_output=save_output,
                    output_path=output_path,
                    preview_mode=preview_mode,
                    quality_preset=quality_preset,
                    crf=crf,
                    encoding_preset=encoding_preset,
                    rembg_model=kwargs.pop("rembg_model", "bria-rmbg"),
                    rembg_background=kwargs.pop("rembg_background", "transparent"),
                    temp_video_from_images=temp_video_from_images,
                    temp_video_with_audio=temp_video_with_audio,
                    **kwargs,
                )
                if _sam3_mask_path and result6[2]:
                    _nollm.sam3_composite(effective_video_path, result6[2], _sam3_mask_path, result6[2])
                return result6 + (mask_points or "", empty_mask)
            # Video Matting mode (MatAnyone2)
            if no_llm_mode == "video_matting":
                result6 = await self._process_video_matting_only(
                    prompt=_raw_prompt,
                    effective_video_path=effective_video_path,
                    video_metadata=video_metadata,
                    save_output=save_output,
                    output_path=output_path,
                    preview_mode=preview_mode,
                    quality_preset=quality_preset,
                    crf=crf,
                    encoding_preset=encoding_preset,
                    matting_output=kwargs.pop("matting_output", "foreground"),
                    matting_background=kwargs.pop("matting_background", "green"),
                    matting_max_size=int(kwargs.pop("matting_max_size", 0)),
                    mask_output_type=kwargs.pop("mask_output_type", "black_white"),
                    temp_video_from_images=temp_video_from_images,
                    temp_video_with_audio=temp_video_with_audio,
                    image_a=image_a,
                    image_path_a=image_path_a,
                    video_path=video_path,
                    **kwargs,
                )
                return result6 + (mask_points or "", empty_mask)
            # Onion Skin mode (temporal ghosting / composite)
            if no_llm_mode == "onion_skin":
                result6 = await self._process_onion_skin_only(
                    effective_video_path=effective_video_path,
                    video_metadata=video_metadata,
                    save_output=save_output,
                    output_path=output_path,
                    preview_mode=preview_mode,
                    quality_preset=quality_preset,
                    crf=crf,
                    encoding_preset=encoding_preset,
                    onion_blend_mode=kwargs.pop("onion_blend_mode", "screen"),
                    onion_opacity=float(kwargs.pop("onion_opacity", 0.5)),
                    onion_decay=float(kwargs.pop("onion_decay", 0.97)),
                    _all_video_paths=_all_video_paths,
                    temp_video_from_images=temp_video_from_images,
                    temp_video_with_audio=temp_video_with_audio,
                    **kwargs,
                )
                if _sam3_mask_path and result6[2]:
                    _nollm.sam3_composite(effective_video_path, result6[2], _sam3_mask_path, result6[2])
                return result6 + (mask_points or "", empty_mask)
            # Comparison mode (A/B video comparison)
            if no_llm_mode == "comparison":
                result6 = await self._process_comparison_only(
                    effective_video_path=effective_video_path,
                    video_metadata=video_metadata,
                    save_output=save_output,
                    output_path=output_path,
                    preview_mode=preview_mode,
                    quality_preset=quality_preset,
                    crf=crf,
                    encoding_preset=encoding_preset,
                    comparison_style=kwargs.pop("comparison_style", "swipe"),
                    comparison_labels=str(kwargs.pop("comparison_labels", "false")).lower() in ("true", "1", "yes"),
                    comparison_label_a=kwargs.pop("comparison_label_a", "Before"),
                    comparison_label_b=kwargs.pop("comparison_label_b", "After"),
                    _all_video_paths=_all_video_paths,
                    temp_video_from_images=temp_video_from_images,
                    temp_video_with_audio=temp_video_with_audio,
                    **kwargs,
                )
                if _sam3_mask_path and result6[2]:
                    _nollm.sam3_composite(effective_video_path, result6[2], _sam3_mask_path, result6[2])
                return result6 + (mask_points or "", empty_mask)
            # Text inputs connected → build a text overlay pipeline
            if _all_text_inputs:
                # Auto-generate a pipeline from text inputs
                text_steps = []
                for raw in _all_text_inputs:
                    try:
                        meta = json.loads(raw)
                    except (json.JSONDecodeError, TypeError):
                        meta = {"text": raw, "mode": "overlay"}
                    mode = meta.get("mode", "overlay")
                    if mode in ("subtitle",):
                        text_steps.append({
                            "skill": "burn_subtitles",
                            "params": {"path": "text_a"},
                        })
                    else:
                        text_steps.append({
                            "skill": "text_overlay",
                            "params": {
                                "text": meta.get("text", raw if isinstance(raw, str) else ""),
                                "position": meta.get("position", "center"),
                                "font_size": meta.get("font_size", 48),
                                "font_color": meta.get("font_color", "white"),
                            },
                        })
                if not text_steps:
                    text_steps = [{"skill": "text_overlay", "params": {"text": _all_text_inputs[0]}}]

                synth_pipeline = json.dumps({"steps": text_steps})
                logger.info("No-LLM: auto-generated text pipeline from %d text input(s)", len(_all_text_inputs))
                result6 = await self._process_effects_pipeline(
                    pipeline_json=synth_pipeline,
                    prompt=prompt,
                    effective_video_path=effective_video_path,
                    video_metadata=video_metadata,
                    save_output=save_output,
                    output_path=output_path,
                    preview_mode=preview_mode,
                    quality_preset=quality_preset,
                    crf=crf,
                    encoding_preset=encoding_preset,
                    whisper_device=whisper_device,
                    whisper_model=whisper_model,
                    sam3_device=sam3_device,
                    sam3_max_objects=sam3_max_objects,
                    sam3_det_threshold=sam3_det_threshold,
                    mask_points=mask_points,
                    use_flux_klein=use_flux_klein,
                    use_kiwi_edit=use_kiwi_edit,
                    use_minimax_remover=use_minimax_remover,
                    use_dreamid_omni=use_dreamid_omni,
                    flux_smoothing=flux_smoothing,
                    temp_video_from_images=temp_video_from_images,
                    temp_video_with_audio=temp_video_with_audio,
                    image_a=image_a,
                    audio_a=audio_a,
                    _all_video_paths=_all_video_paths,
                    _all_image_paths=_all_image_paths,
                    _all_text_inputs=_all_text_inputs,
                    audio_resample_rate=audio_resample_rate,
                    **kwargs,
                )
                return result6 + (mask_points or "", empty_mask)
            # manual mode without Effects Builder or text
            raise RuntimeError(
                "No-LLM 'manual' mode requires an Effects Builder node or "
                "FFMPEGA Text node. Connect one to the pipeline_json or "
                "text_a input, or switch no_llm_mode to 'sam3_masking', "
                "'transcribe', 'karaoke_subtitles', 'generate_audio', 'generate_music', 'generate_sample', 'fish_speech', 'audio_inpaint', 'audio_separate', 'ace_step', 'lip_sync', 'marigold', 'normalcrafter', 'video_depth', 'flux_klein', 'kiwi_edit', 'minimax_remover', or 'ai_upscale'."
            )
        # --- Build connected-inputs context string ---
        connected_inputs_str = self._build_connected_inputs_summary(
            images_a=images_a,
            _images_a_shape=_images_a_shape,
            video_path=video_path,
            audio_a=audio_a,
            image_a=image_a,
            _all_video_paths=_all_video_paths,
            _all_image_paths=_all_image_paths,
            _all_text_inputs=_all_text_inputs,
            video_metadata=video_metadata,
            **kwargs,
        )

        # --- Generate pipeline spec via LLM ---
        spec, connector = await _pa.generate_pipeline_spec(
            pipeline_generator=self.pipeline_generator,
            prompt=prompt,
            metadata_str=metadata_str,
            connected_inputs_str=connected_inputs_str,
            effective_video_path=effective_video_path,
            llm_model=llm_model,
            custom_model=custom_model,
            ollama_url=ollama_url,
            api_key=api_key,
            use_vision=use_vision,
            ptc_mode=ptc_mode,
        )

        # --- Build output path ---
        output_path, temp_render_dir = self._build_output_path(
            effective_video_path=effective_video_path,
            save_output=save_output,
            output_path=output_path,
            preview_mode=preview_mode,
        )

        # --- Assemble pipeline from LLM spec ---
        (
            pipeline, output_path, interpretation, warnings,
            estimated_changes, audio_source, audio_mode,
        ) = _pa.assemble_pipeline(
            Pipeline=Pipeline,
            spec=spec,
            effective_video_path=effective_video_path,
            output_path=output_path,
            video_metadata=video_metadata,
            quality_preset=quality_preset,
            crf=crf,
            encoding_preset=encoding_preset,
            whisper_device=whisper_device,
            whisper_model=whisper_model,
            sam3_device=sam3_device,
            sam3_max_objects=sam3_max_objects,
            sam3_det_threshold=sam3_det_threshold,
            mask_points=mask_points,
            use_flux_klein=use_flux_klein,
            use_kiwi_edit=use_kiwi_edit,
            use_minimax_remover=use_minimax_remover,
            flux_smoothing=flux_smoothing,
            audio_output_mode=audio_output_mode,
            composer=self.composer,
        )

        # --- Inject extra inputs (multi-input, audio muxing, etc.) ---
        (
            effective_video_path,
            temp_multi_videos,
            temp_audio_files,
            temp_frames_dirs,
            temp_audio_input,
        ) = self._inject_extra_inputs(
            pipeline=pipeline,
            effective_video_path=effective_video_path,
            image_a=image_a,
            _all_image_paths=_all_image_paths,
            _all_video_paths=_all_video_paths,
            _all_text_inputs=_all_text_inputs,
            audio_a=audio_a,
            **kwargs,
        )
        pipeline.input_path = effective_video_path

        # --- Compose command ---
        command = self.composer.compose(pipeline)

        # --- Movie-override: skill produced a pre-built video (VDA, Marigold) ---
        movie_override = pipeline.metadata.get("_movie_override")
        if movie_override and os.path.isfile(movie_override):
            import shutil
            shutil.copy2(movie_override, output_path)
            cmd_log = f"cp {movie_override} → {output_path}"
            unique_id = str(kwargs.get("unique_id", ""))
            hidden_prompt = kwargs.get("hidden_prompt") or {}
            try:
                from .nollm_modes import collect_frame_output
            except ImportError:
                from nodes.nollm_modes import collect_frame_output
            images_tensor, audio_out = collect_frame_output(
                media_converter=self.media_converter,
                output_path=output_path,
                unique_id=unique_id,
                hidden_prompt=hidden_prompt,
                removes_audio=True,
            )
            analysis = f"AI Skill produced video: {os.path.basename(movie_override)}"
            if hasattr(connector, 'close'):
                await connector.close()
            return (images_tensor, audio_out, output_path, cmd_log, analysis, "", mask_points or "", empty_mask)

        # --- Execute ---
        result, pipeline, command = await self._execute_pipeline(
            pipeline=pipeline,
            command=command,
            connector=connector,
            prompt=prompt,
            metadata_str=metadata_str,
            connected_inputs_str=connected_inputs_str,
            effective_video_path=effective_video_path,
            output_path=output_path,
            quality_preset=quality_preset,
            crf=crf,
            encoding_preset=encoding_preset,
            preview_mode=preview_mode,
            verify_output=verify_output,
            use_vision=use_vision,
            ptc_mode=ptc_mode,
            video_metadata=video_metadata,
            _all_text_inputs=_all_text_inputs,
        )

        # Close LLM connector
        if hasattr(connector, 'close'):
            await connector.close()  # type: ignore[union-attr]

        # Debug probe output duration
        try:
            import subprocess as _sp
            _probe = _sp.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1", output_path],
                capture_output=True, text=True
            )
            logger.debug("Output duration BEFORE audio mux: %s", _probe.stdout.strip())
        except Exception:
            pass

        # --- Build analysis string ---
        analysis = _oh.build_analysis_string(
            interpretation=interpretation,
            estimated_changes=estimated_changes,
            warnings=warnings,
            composer=self.composer,
            pipeline=pipeline,
            pipeline_generator=self.pipeline_generator,
            track_tokens=track_tokens,
            log_usage=log_usage,
            prompt=prompt,
        )

        # --- Handle audio output ---
        self._handle_audio_output(
            command=command,
            pipeline=pipeline,
            audio_a=audio_a,
            audio_source=audio_source,
            audio_mode=audio_mode,
            output_path=output_path,
            **kwargs,
        )
        removes_audio = "-an" in command.output_options

        # --- Collect frame/audio output ---
        unique_id = str(kwargs.get("unique_id", ""))
        hidden_prompt = kwargs.get("hidden_prompt") or {}
        images_tensor, audio_out = self._collect_frame_output(
            output_path=output_path,
            unique_id=unique_id,
            hidden_prompt=hidden_prompt,
            removes_audio=removes_audio,
            resample_rate=int(audio_resample_rate) if audio_resample_rate and audio_resample_rate != "off" else None,
        )

        # --- Sanitize API key from workflow metadata ---
        hidden_extra_pnginfo = kwargs.get("extra_pnginfo")
        if api_key:
            self._strip_api_key_from_metadata(api_key, hidden_prompt, hidden_extra_pnginfo)

        # --- Save first-frame workflow PNG ---
        if save_output and images_tensor is not None and images_tensor.shape[0] > 0:
            png_path = str(Path(output_path).with_suffix(".png"))
            self._save_workflow_png(
                images_tensor[0],
                png_path,
                hidden_prompt,
                hidden_extra_pnginfo,
            )

        # --- Generate mask output (must run BEFORE temp cleanup) ---
        mask_overlay_path = _oh.generate_mask_output(
            pipeline=pipeline,
            effective_video_path=effective_video_path,
            mask_output_type=kwargs.get("mask_output_type", "colored_overlay"),
        )

        # --- Cleanup temp files ---
        _oh.cleanup_temp_files(
            temp_video_from_images=temp_video_from_images,
            temp_video_with_audio=temp_video_with_audio,
            temp_audio_input=temp_audio_input,
            temp_multi_videos=temp_multi_videos,
            temp_audio_files=temp_audio_files,
            temp_frames_dirs=temp_frames_dirs,
            temp_render_dir=temp_render_dir,
            save_output=save_output,
        )

        return (images_tensor, audio_out, output_path, command.to_string(), analysis, mask_overlay_path, mask_points or "", empty_mask)

    # ------------------------------------------------------------------ #
    #  Effects Builder support                                             #
    # ------------------------------------------------------------------ #

    async def _process_effects_pipeline(self, pipeline_json, prompt, effective_video_path, video_metadata, save_output, output_path, preview_mode, quality_preset, crf, encoding_preset, whisper_device="cpu", whisper_model="large-v3", sam3_device="gpu", sam3_max_objects=5, sam3_det_threshold=0.7, mask_points="", use_flux_klein=False, use_kiwi_edit=False, use_minimax_remover=False, use_dreamid_omni=False, flux_smoothing="none", temp_video_from_images=None, temp_video_with_audio=None, image_a=None, audio_a=None, _all_video_paths=None, _all_image_paths=None, _all_text_inputs=None, **kwargs):
        """Delegate to nollm_modes module."""
        return await _nollm.process_effects_pipeline(
            composer=self.composer, process_manager=self.process_manager,
            media_converter=self.media_converter,
            pipeline_json=pipeline_json, prompt=prompt,
            effective_video_path=effective_video_path,
            video_metadata=video_metadata, save_output=save_output,
            output_path=output_path, preview_mode=preview_mode,
            quality_preset=quality_preset, crf=crf,
            encoding_preset=encoding_preset,
            whisper_device=whisper_device, whisper_model=whisper_model,
            sam3_device=sam3_device, sam3_max_objects=sam3_max_objects,
            sam3_det_threshold=sam3_det_threshold, mask_points=mask_points,
            use_flux_klein=use_flux_klein,
            use_kiwi_edit=use_kiwi_edit,
            use_minimax_remover=use_minimax_remover,
            use_dreamid_omni=use_dreamid_omni,
            flux_smoothing=flux_smoothing,
            temp_video_from_images=temp_video_from_images,
            temp_video_with_audio=temp_video_with_audio,
            image_a=image_a, audio_a=audio_a,
            _all_video_paths=_all_video_paths,
            _all_image_paths=_all_image_paths,
            _all_text_inputs=_all_text_inputs,
            _inject_extra_inputs_fn=self._inject_extra_inputs,
            **kwargs,
        )
    # ------------------------------------------------------------------ #
    #  SAM3-only mode (no LLM)                                            #
    # ------------------------------------------------------------------ #

    async def _process_sam3_only(self, prompt, effective_video_path, video_metadata, save_output, output_path, preview_mode, quality_preset, crf, encoding_preset, sam3_device, sam3_max_objects, sam3_det_threshold, mask_points, temp_video_from_images, temp_video_with_audio, **kwargs):
        """Delegate to nollm_modes module."""
        return await _nollm.process_sam3_only(
            media_converter=self.media_converter,
            prompt=prompt, effective_video_path=effective_video_path,
            video_metadata=video_metadata, save_output=save_output,
            output_path=output_path, preview_mode=preview_mode,
            quality_preset=quality_preset, crf=crf,
            encoding_preset=encoding_preset, sam3_device=sam3_device,
            sam3_max_objects=sam3_max_objects,
            sam3_det_threshold=sam3_det_threshold,
            mask_points=mask_points,
            temp_video_from_images=temp_video_from_images,
            temp_video_with_audio=temp_video_with_audio,
            **kwargs,
        )
    # ------------------------------------------------------------------ #
    #  Whisper-only mode (no LLM)                                         #
    # ------------------------------------------------------------------ #

    async def _process_whisper_only(self, mode, effective_video_path, video_metadata, save_output, output_path, preview_mode, quality_preset, crf, encoding_preset, whisper_device="cpu", whisper_model="large-v3", temp_video_from_images=None, temp_video_with_audio=None, **kwargs):
        """Delegate to nollm_modes module."""
        return await _nollm.process_whisper_only(
            media_converter=self.media_converter,
            mode=mode, effective_video_path=effective_video_path,
            video_metadata=video_metadata, save_output=save_output,
            output_path=output_path, preview_mode=preview_mode,
            quality_preset=quality_preset, crf=crf,
            encoding_preset=encoding_preset,
            whisper_device=whisper_device, whisper_model=whisper_model,
            temp_video_from_images=temp_video_from_images,
            temp_video_with_audio=temp_video_with_audio,
            **kwargs,
        )
    # ------------------------------------------------------------------ #
    #  MMAudio-only mode (no LLM)                                         #
    # ------------------------------------------------------------------ #

    async def _process_mmaudio_only(self, prompt, audio_output_mode, effective_video_path, video_metadata, save_output, output_path, preview_mode, quality_preset, crf, encoding_preset, temp_video_from_images=None, temp_video_with_audio=None, **kwargs):
        """Delegate to nollm_modes module."""
        return await _nollm.process_mmaudio_only(
            media_converter=self.media_converter,
            prompt=prompt, audio_output_mode=audio_output_mode,
            effective_video_path=effective_video_path,
            video_metadata=video_metadata, save_output=save_output,
            output_path=output_path, preview_mode=preview_mode,
            quality_preset=quality_preset, crf=crf,
            encoding_preset=encoding_preset,
            temp_video_from_images=temp_video_from_images,
            temp_video_with_audio=temp_video_with_audio,
            **kwargs,
        )

    # ------------------------------------------------------------------ #
    #  AudioX music-only mode (no LLM)                                    #
    # ------------------------------------------------------------------ #

    async def _process_audiox_music_only(self, prompt, audio_output_mode, effective_video_path, video_metadata, save_output, output_path, preview_mode, quality_preset, crf, encoding_preset, temp_video_from_images=None, temp_video_with_audio=None, **kwargs):
        """Delegate to nollm_modes module."""
        return await _nollm.process_audiox_music_only(
            media_converter=self.media_converter,
            prompt=prompt, audio_output_mode=audio_output_mode,
            effective_video_path=effective_video_path,
            video_metadata=video_metadata, save_output=save_output,
            output_path=output_path, preview_mode=preview_mode,
            quality_preset=quality_preset, crf=crf,
            encoding_preset=encoding_preset,
            temp_video_from_images=temp_video_from_images,
            temp_video_with_audio=temp_video_with_audio,
            **kwargs,
        )

    # ------------------------------------------------------------------ #
    #  Foundation-1 sample-only mode (no LLM)                              #
    # ------------------------------------------------------------------ #

    async def _process_foundation1_only(self, prompt, audio_output_mode, effective_video_path, video_metadata, save_output, output_path, preview_mode, quality_preset, crf, encoding_preset, temp_video_from_images=None, temp_video_with_audio=None, **kwargs):
        """Delegate to nollm_modes module."""
        return await _nollm.process_foundation1_only(
            media_converter=self.media_converter,
            prompt=prompt, audio_output_mode=audio_output_mode,
            effective_video_path=effective_video_path,
            video_metadata=video_metadata, save_output=save_output,
            output_path=output_path, preview_mode=preview_mode,
            quality_preset=quality_preset, crf=crf,
            encoding_preset=encoding_preset,
            temp_video_from_images=temp_video_from_images,
            temp_video_with_audio=temp_video_with_audio,
            **kwargs,
        )

    # ------------------------------------------------------------------ #
    #  Fish Speech TTS mode (no LLM)                                       #
    # ------------------------------------------------------------------ #

    async def _process_fish_speech_only(self, prompt, audio_output_mode, effective_video_path, video_metadata, save_output, output_path, preview_mode, quality_preset, crf, encoding_preset, temp_video_from_images=None, temp_video_with_audio=None, **kwargs):
        """Delegate to nollm_modes module."""
        return await _nollm.process_fish_speech_only(
            media_converter=self.media_converter,
            prompt=prompt, audio_output_mode=audio_output_mode,
            effective_video_path=effective_video_path,
            video_metadata=video_metadata, save_output=save_output,
            output_path=output_path, preview_mode=preview_mode,
            quality_preset=quality_preset, crf=crf,
            encoding_preset=encoding_preset,
            temp_video_from_images=temp_video_from_images,
            temp_video_with_audio=temp_video_with_audio,
            **kwargs,
        )

    # ------------------------------------------------------------------ #

    async def _process_ace_step_only(self, prompt, audio_output_mode, effective_video_path, video_metadata, save_output, output_path, preview_mode, quality_preset, crf, encoding_preset, temp_video_from_images=None, temp_video_with_audio=None, **kwargs):
        """Delegate to nollm_modes module."""
        return await _nollm.process_ace_step_only(
            media_converter=self.media_converter,
            prompt=prompt, audio_output_mode=audio_output_mode,
            effective_video_path=effective_video_path,
            video_metadata=video_metadata, save_output=save_output,
            output_path=output_path, preview_mode=preview_mode,
            quality_preset=quality_preset, crf=crf,
            encoding_preset=encoding_preset,
            temp_video_from_images=temp_video_from_images,
            temp_video_with_audio=temp_video_with_audio,
            **kwargs,
        )

    # ------------------------------------------------------------------ #
    #  AudioX inpaint-only mode (no LLM)                                  #
    # ------------------------------------------------------------------ #

    async def _process_audiox_inpaint_only(self, prompt, audio_output_mode, effective_video_path, video_metadata, save_output, output_path, preview_mode, quality_preset, crf, encoding_preset, temp_video_from_images=None, temp_video_with_audio=None, **kwargs):
        """Delegate to nollm_modes module."""
        return await _nollm.process_audiox_inpaint_only(
            media_converter=self.media_converter,
            prompt=prompt, audio_output_mode=audio_output_mode,
            effective_video_path=effective_video_path,
            video_metadata=video_metadata, save_output=save_output,
            output_path=output_path, preview_mode=preview_mode,
            quality_preset=quality_preset, crf=crf,
            encoding_preset=encoding_preset,
            temp_video_from_images=temp_video_from_images,
            temp_video_with_audio=temp_video_with_audio,
            **kwargs,
        )

    async def _process_sam_audio_separate(self, prompt, audio_output_mode, effective_video_path, video_metadata, save_output, output_path, preview_mode, quality_preset, crf, encoding_preset, temp_video_from_images=None, temp_video_with_audio=None, **kwargs):
        """Delegate to nollm_modes module."""
        return await _nollm.process_sam_audio_separate(
            media_converter=self.media_converter,
            prompt=prompt, audio_output_mode=audio_output_mode,
            effective_video_path=effective_video_path,
            video_metadata=video_metadata, save_output=save_output,
            output_path=output_path, preview_mode=preview_mode,
            quality_preset=quality_preset, crf=crf,
            encoding_preset=encoding_preset,
            temp_video_from_images=temp_video_from_images,
            temp_video_with_audio=temp_video_with_audio,
            **kwargs,
        )

    # ------------------------------------------------------------------ #
    #  Lip sync mode (no LLM)                                             #
    # ------------------------------------------------------------------ #

    async def _process_lip_sync_only(self, effective_video_path, video_metadata, save_output, output_path, preview_mode, quality_preset, crf, encoding_preset, audio_a=None, temp_video_from_images=None, temp_video_with_audio=None, **kwargs):
        """Delegate to nollm_modes module."""
        return await _nollm.process_lip_sync_only(
            media_converter=self.media_converter,
            effective_video_path=effective_video_path,
            video_metadata=video_metadata, save_output=save_output,
            output_path=output_path, preview_mode=preview_mode,
            quality_preset=quality_preset, crf=crf,
            encoding_preset=encoding_preset,
            audio_a=audio_a,
            temp_video_from_images=temp_video_from_images,
            temp_video_with_audio=temp_video_with_audio,
            **kwargs,
        )

    # ------------------------------------------------------------------ #
    #  Animate portrait mode (no LLM)                                     #
    # ------------------------------------------------------------------ #

    async def _process_animate_portrait_only(self, effective_video_path, video_metadata, save_output, output_path, preview_mode, quality_preset, crf, encoding_preset, driving_video="", lp_rotate_pitch=0.0, lp_rotate_yaw=0.0, lp_rotate_roll=0.0, lp_blink=0.0, lp_eyebrow=0.0, lp_wink=0.0, lp_pupil_x=0.0, lp_pupil_y=0.0, lp_aaa=0.0, lp_eee=0.0, lp_woo=0.0, lp_smile=0.0, lp_retargeting_eyes=1.0, lp_retargeting_mouth=1.0, lp_crop_factor=1.6, lp_sample_image="", lp_sample_ratio=1.0, lp_sample_parts="all", temp_video_from_images=None, temp_video_with_audio=None, **kwargs):
        """Delegate to nollm_modes module."""
        return await _nollm.process_animate_portrait_only(
            media_converter=self.media_converter,
            effective_video_path=effective_video_path,
            video_metadata=video_metadata, save_output=save_output,
            output_path=output_path, preview_mode=preview_mode,
            quality_preset=quality_preset, crf=crf,
            encoding_preset=encoding_preset,
            driving_video=driving_video,
            lp_rotate_pitch=lp_rotate_pitch,
            lp_rotate_yaw=lp_rotate_yaw,
            lp_rotate_roll=lp_rotate_roll,
            lp_blink=lp_blink,
            lp_eyebrow=lp_eyebrow,
            lp_wink=lp_wink,
            lp_pupil_x=lp_pupil_x,
            lp_pupil_y=lp_pupil_y,
            lp_aaa=lp_aaa,
            lp_eee=lp_eee,
            lp_woo=lp_woo,
            lp_smile=lp_smile,
            lp_retargeting_eyes=lp_retargeting_eyes,
            lp_retargeting_mouth=lp_retargeting_mouth,
            lp_crop_factor=lp_crop_factor,
            lp_sample_image=lp_sample_image,
            lp_sample_ratio=lp_sample_ratio,
            lp_sample_parts=lp_sample_parts,
            temp_video_from_images=temp_video_from_images,
            temp_video_with_audio=temp_video_with_audio,
            **kwargs,
        )

    # ------------------------------------------------------------------ #
    #  Marigold mode (no LLM)                                             #
    # ------------------------------------------------------------------ #

    async def _process_marigold_only(self, effective_video_path, video_metadata, save_output, output_path, preview_mode, quality_preset, crf, encoding_preset, marigold_output_type="depth", marigold_colormap="Spectral", temp_video_from_images=None, temp_video_with_audio=None, **kwargs):
        """Delegate to nollm_modes module."""
        return await _nollm.process_marigold_only(
            media_converter=self.media_converter,
            effective_video_path=effective_video_path,
            video_metadata=video_metadata, save_output=save_output,
            output_path=output_path, preview_mode=preview_mode,
            quality_preset=quality_preset, crf=crf,
            encoding_preset=encoding_preset,
            marigold_output_type=marigold_output_type,
            marigold_colormap=marigold_colormap,
            temp_video_from_images=temp_video_from_images,
            temp_video_with_audio=temp_video_with_audio,
            **kwargs,
        )

    # ------------------------------------------------------------------ #
    #  NormalCrafter mode (no LLM)                                        #
    # ------------------------------------------------------------------ #

    async def _process_normalcrafter_only(self, effective_video_path, video_metadata, save_output, output_path, preview_mode, quality_preset, crf, encoding_preset, normalcrafter_max_res="auto", temp_video_from_images=None, temp_video_with_audio=None, **kwargs):
        """Delegate to nollm_modes module."""
        return await _nollm.process_normalcrafter_only(
            media_converter=self.media_converter,
            effective_video_path=effective_video_path,
            video_metadata=video_metadata, save_output=save_output,
            output_path=output_path, preview_mode=preview_mode,
            quality_preset=quality_preset, crf=crf,
            encoding_preset=encoding_preset,
            normalcrafter_max_res=normalcrafter_max_res,
            temp_video_from_images=temp_video_from_images,
            temp_video_with_audio=temp_video_with_audio,
            **kwargs,
        )

    # ------------------------------------------------------------------ #
    #  Video Depth mode (no LLM)                                          #
    # ------------------------------------------------------------------ #

    async def _process_video_depth_only(self, effective_video_path, video_metadata, save_output, output_path, preview_mode, quality_preset, crf, encoding_preset, video_depth_encoder="vits", video_depth_colormap="gray", temp_video_from_images=None, temp_video_with_audio=None, **kwargs):
        """Delegate to nollm_modes module."""
        return await _nollm.process_video_depth_only(
            media_converter=self.media_converter,
            effective_video_path=effective_video_path,
            video_metadata=video_metadata, save_output=save_output,
            output_path=output_path, preview_mode=preview_mode,
            quality_preset=quality_preset, crf=crf,
            encoding_preset=encoding_preset,
            video_depth_encoder=video_depth_encoder,
            video_depth_colormap=video_depth_colormap,
            temp_video_from_images=temp_video_from_images,
            temp_video_with_audio=temp_video_with_audio,
            **kwargs,
        )

    # ------------------------------------------------------------------ #
    #  AI Upscale mode (no LLM)                                            #
    # ------------------------------------------------------------------ #

    async def _process_ai_upscale_only(self, effective_video_path, video_metadata, save_output, output_path, preview_mode, quality_preset, crf, encoding_preset, upscale_model="realesrgan_x4plus", upscale_scale=4, tile_size=512, blockswap_blocks=0, seedvr_resolution=1080, rtx_quality="ULTRA", temp_video_from_images=None, temp_video_with_audio=None, **kwargs):
        """Delegate to nollm_modes module."""
        return await _nollm.process_ai_upscale_only(
            media_converter=self.media_converter,
            effective_video_path=effective_video_path,
            video_metadata=video_metadata, save_output=save_output,
            output_path=output_path, preview_mode=preview_mode,
            quality_preset=quality_preset, crf=crf,
            encoding_preset=encoding_preset,
            upscale_model=upscale_model,
            upscale_scale=upscale_scale,
            tile_size=tile_size,
            blockswap_blocks=blockswap_blocks,
            seedvr_resolution=seedvr_resolution,
            rtx_quality=rtx_quality,
            temp_video_from_images=temp_video_from_images,
            temp_video_with_audio=temp_video_with_audio,
            **kwargs,
        )

    # ------------------------------------------------------------------ #
    #  MiniMax-Remover mode (no LLM)                                       #
    # ------------------------------------------------------------------ #

    async def _process_minimax_remover_only(self, prompt, effective_video_path, video_metadata, save_output, output_path, preview_mode, quality_preset, crf, encoding_preset, temp_video_from_images=None, temp_video_with_audio=None, **kwargs):
        """Delegate to nollm_modes module."""
        return await _nollm.process_minimax_remover_only(
            media_converter=self.media_converter,
            prompt=prompt,
            effective_video_path=effective_video_path,
            video_metadata=video_metadata, save_output=save_output,
            output_path=output_path, preview_mode=preview_mode,
            quality_preset=quality_preset, crf=crf,
            encoding_preset=encoding_preset,
            temp_video_from_images=temp_video_from_images,
            temp_video_with_audio=temp_video_with_audio,
            **kwargs,
        )

    # ------------------------------------------------------------------ #
    #  FLUX Klein mode (no LLM)                                            #
    # ------------------------------------------------------------------ #

    async def _process_flux_klein_only(self, prompt, effective_video_path, video_metadata, save_output, output_path, preview_mode, quality_preset, crf, encoding_preset, flux_smoothing="none", image_a=None, _all_image_paths=None, temp_video_from_images=None, temp_video_with_audio=None, **kwargs):
        """Delegate to nollm_modes module."""
        return await _nollm.process_flux_klein_only(
            media_converter=self.media_converter,
            prompt=prompt,
            effective_video_path=effective_video_path,
            video_metadata=video_metadata, save_output=save_output,
            output_path=output_path, preview_mode=preview_mode,
            quality_preset=quality_preset, crf=crf,
            encoding_preset=encoding_preset,
            flux_smoothing=flux_smoothing,
            image_a=image_a,
            _all_image_paths=_all_image_paths,
            temp_video_from_images=temp_video_from_images,
            temp_video_with_audio=temp_video_with_audio,
            **kwargs,
        )

    # ------------------------------------------------------------------ #
    #  Kiwi-Edit mode (no LLM)                                              #
    # ------------------------------------------------------------------ #

    async def _process_kiwi_edit_only(self, prompt, effective_video_path, video_metadata, save_output, output_path, preview_mode, quality_preset, crf, encoding_preset, image_a=None, _all_image_paths=None, temp_video_from_images=None, temp_video_with_audio=None, **kwargs):
        """Delegate to nollm_modes module."""
        return await _nollm.process_kiwi_edit_only(
            media_converter=self.media_converter,
            prompt=prompt,
            effective_video_path=effective_video_path,
            video_metadata=video_metadata, save_output=save_output,
            output_path=output_path, preview_mode=preview_mode,
            quality_preset=quality_preset, crf=crf,
            encoding_preset=encoding_preset,
            image_a=image_a,
            _all_image_paths=_all_image_paths,
            temp_video_from_images=temp_video_from_images,
            temp_video_with_audio=temp_video_with_audio,
            **kwargs,
        )

    # ------------------------------------------------------------------ #
    #  Rembg background removal mode (no LLM)                              #
    # ------------------------------------------------------------------ #

    async def _process_rembg_only(self, effective_video_path, video_metadata, save_output, output_path, preview_mode, quality_preset, crf, encoding_preset, rembg_model="bria-rmbg", rembg_background="transparent", temp_video_from_images=None, temp_video_with_audio=None, **kwargs):
        """Delegate to nollm_modes module."""
        return await _nollm.process_rembg_only(
            media_converter=self.media_converter,
            effective_video_path=effective_video_path,
            video_metadata=video_metadata, save_output=save_output,
            output_path=output_path, preview_mode=preview_mode,
            quality_preset=quality_preset, crf=crf,
            encoding_preset=encoding_preset,
            rembg_model=rembg_model,
            rembg_background=rembg_background,
            temp_video_from_images=temp_video_from_images,
            temp_video_with_audio=temp_video_with_audio,
            **kwargs,
        )

    # ------------------------------------------------------------------ #
    #  Video Matting mode (no LLM) — MatAnyone2                            #
    # ------------------------------------------------------------------ #

    async def _process_video_matting_only(self, prompt, effective_video_path, video_metadata, save_output, output_path, preview_mode, quality_preset, crf, encoding_preset, matting_output="foreground", matting_background="green", matting_max_size=0, mask_output_type="black_white", temp_video_from_images=None, temp_video_with_audio=None, **kwargs):
        """Delegate to nollm_modes module."""
        return await _nollm.process_video_matting_only(
            media_converter=self.media_converter,
            prompt=prompt,
            effective_video_path=effective_video_path,
            video_metadata=video_metadata, save_output=save_output,
            output_path=output_path, preview_mode=preview_mode,
            quality_preset=quality_preset, crf=crf,
            encoding_preset=encoding_preset,
            matting_output=matting_output,
            matting_background=matting_background,
            matting_max_size=matting_max_size,
            mask_output_type=mask_output_type,
            temp_video_from_images=temp_video_from_images,
            temp_video_with_audio=temp_video_with_audio,
            **kwargs,
        )

    # ------------------------------------------------------------------ #
    #  Onion Skin mode (no LLM)                                            #
    # ------------------------------------------------------------------ #

    async def _process_onion_skin_only(self, effective_video_path, video_metadata, save_output, output_path, preview_mode, quality_preset, crf, encoding_preset, onion_blend_mode="screen", onion_opacity=0.5, onion_decay=0.97, _all_video_paths=None, temp_video_from_images=None, temp_video_with_audio=None, **kwargs):
        """Delegate to nollm_modes module."""
        return await _nollm.process_onion_skin_only(
            composer=self.composer,
            process_manager=self.process_manager,
            media_converter=self.media_converter,
            effective_video_path=effective_video_path,
            video_metadata=video_metadata, save_output=save_output,
            output_path=output_path, preview_mode=preview_mode,
            quality_preset=quality_preset, crf=crf,
            encoding_preset=encoding_preset,
            onion_blend_mode=onion_blend_mode,
            onion_opacity=onion_opacity,
            onion_decay=onion_decay,
            _all_video_paths=_all_video_paths,
            temp_video_from_images=temp_video_from_images,
            temp_video_with_audio=temp_video_with_audio,
            **kwargs,
        )

    async def _process_comparison_only(self, effective_video_path, video_metadata, save_output, output_path, preview_mode, quality_preset, crf, encoding_preset, comparison_style="swipe", comparison_labels=False, comparison_label_a="Before", comparison_label_b="After", _all_video_paths=None, temp_video_from_images=None, temp_video_with_audio=None, **kwargs):
        """Delegate to nollm_modes module."""
        return await _nollm.process_comparison_only(
            composer=self.composer,
            process_manager=self.process_manager,
            media_converter=self.media_converter,
            effective_video_path=effective_video_path,
            video_metadata=video_metadata, save_output=save_output,
            output_path=output_path, preview_mode=preview_mode,
            quality_preset=quality_preset, crf=crf,
            encoding_preset=encoding_preset,
            comparison_style=comparison_style,
            comparison_labels=comparison_labels,
            comparison_label_a=comparison_label_a,
            comparison_label_b=comparison_label_b,
            _all_video_paths=_all_video_paths,
            temp_video_from_images=temp_video_from_images,
            temp_video_with_audio=temp_video_with_audio,
            **kwargs,
        )

    async def _verify_output(self, connector, output_path, prompt, pipeline, effective_video_path, use_vision):
        """Delegate to execution_engine module."""
        return await _ee._verify_output(
            connector=connector, output_path=output_path,
            prompt=prompt, pipeline=pipeline,
            effective_video_path=effective_video_path,
            use_vision=use_vision,
            composer=self.composer,
            process_manager=self.process_manager,
            pipeline_generator=self.pipeline_generator,
        )
    @staticmethod
    def _audio_dict_to_wav(audio: dict) -> Optional[str]:
        """Delegate to output_handler module."""
        return _oh.audio_dict_to_wav(audio)

    @staticmethod
    def _probe_duration(video_path: str) -> float:
        """Delegate to output_handler module."""
        return _oh.probe_duration(video_path)

    @staticmethod
    def _extract_thumbnail_frame(video_path: str) -> torch.Tensor:
        """Delegate to output_handler module."""
        return _oh.extract_thumbnail_frame(video_path)

    @staticmethod
    def _save_workflow_png(first_frame, png_path, prompt, extra_pnginfo, extra_info=None):
        """Delegate to output_handler module."""
        return _oh.save_workflow_png(first_frame, png_path, prompt, extra_pnginfo, extra_info)

    @staticmethod
    def _strip_api_key_from_metadata(api_key, prompt, extra_pnginfo):
        """Delegate to output_handler module."""
        return _oh.strip_api_key_from_metadata(api_key, prompt, extra_pnginfo)

    async def _process_batch(self, video_folder, file_pattern, prompt, llm_model, quality_preset, ollama_url, api_key, custom_model, crf, encoding_preset, max_concurrent, save_output, output_path, use_vision=False, verify_output=False, ptc_mode="off", sam3_max_objects=5, sam3_det_threshold=0.7, mask_points="", pipeline_json="", use_flux_klein=False, use_minimax_remover=False, flux_smoothing="none"):
        """Delegate to batch_processor module."""
        return await _bp.process_batch(
            analyzer=self.analyzer, composer=self.composer,
            process_manager=self.process_manager,
            pipeline_generator=self.pipeline_generator,
            media_converter=self.media_converter,
            video_folder=video_folder, file_pattern=file_pattern,
            prompt=prompt, llm_model=llm_model,
            quality_preset=quality_preset, ollama_url=ollama_url,
            api_key=api_key, custom_model=custom_model,
            crf=crf, encoding_preset=encoding_preset,
            max_concurrent=max_concurrent, save_output=save_output,
            output_path=output_path, use_vision=use_vision,
            verify_output=verify_output, ptc_mode=ptc_mode,
            sam3_max_objects=sam3_max_objects,
            sam3_det_threshold=sam3_det_threshold,
            mask_points=mask_points, pipeline_json=pipeline_json,
            use_flux_klein=use_flux_klein,
            use_minimax_remover=use_minimax_remover,
            flux_smoothing=flux_smoothing,
        )
    @classmethod
    def IS_CHANGED(cls, video_path, prompt, seed=0, **kwargs):
        """Determine if the node needs to re-execute."""
        return f"{video_path}:{prompt}:{seed}"
