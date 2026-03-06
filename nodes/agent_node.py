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
                    "default": "gemini-cli" if "gemini-cli" in all_models else (ollama_models[0] if ollama_models != cls.FALLBACK_OLLAMA_MODELS else "none"),
                    "tooltip": "AI model for interpreting your prompt. "
                               "CLI models (gemini-cli, claude-cli, etc.) use locally installed CLI tools — no API key needed. "
                               "Ollama models run locally via the Ollama server. "
                               "Cloud API models (GPT, Claude, Gemini, Qwen) require an api_key. "
                               "Select 'custom' to type any model name manually. "
                               "Select 'none' to skip the LLM entirely and use no_llm_mode instead (manual pipeline, SAM3, Whisper, or MMAudio).",
                }),
                "no_llm_mode": (["manual", "sam3_masking", "transcribe", "karaoke_subtitles", "generate_audio", "lip_sync", "animate_portrait"], {
                    "default": "manual",
                    "tooltip": "What to do when llm_model is 'none'. "
                               "'manual' runs the Effects Builder pipeline directly (no AI). "
                               "'sam3_masking' uses the prompt as a SAM3 text target. "
                               "'transcribe' runs Whisper speech-to-text and burns SRT subtitles. "
                               "'karaoke_subtitles' runs Whisper and burns word-by-word karaoke subtitles. "
                               "'generate_audio' uses MMAudio to synthesize audio from video/prompt. "
                               "'lip_sync' uses MuseTalk to sync lip movements to connected audio_a. "
                               "'animate_portrait' uses LivePortrait to animate a face — connect driving video to video_a.",
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
                    "default": True,
                    "label_on": "Vision On",
                    "label_off": "Vision Off",
                    "tooltip": "When On, embeds video frames as images for vision-capable models (uses more tokens). When Off, uses numeric color analysis instead (cheaper, works with all models).",
                }),
                "verify_output": ("BOOLEAN", {
                    "default": True,
                    "label_on": "Verify On",
                    "label_off": "Verify Off",
                    "tooltip": "When On, the agent inspects the output video after rendering and auto-corrects if it doesn't match intent. Adds one extra LLM call (more tokens/time). Best for complex edits like overlays, color grading, or animations.",
                }),

                # ── Advanced toggle ───────────────────────────────────────
                "advanced_options": ("BOOLEAN", {
                    "default": False,
                    "label_on": "Advanced",
                    "label_off": "Simple",
                    "tooltip": "Show advanced options: preview, encoding, SAM3/Whisper tuning, FLUX smoothing, MMAudio mode, batch processing, and usage tracking.",
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

                # ── Advanced: FLUX Klein ──────────────────────────────────
                "flux_smoothing": (["none", "gaussian", "adaptive"], {
                    "default": "none",
                    "tooltip": "Temporal smoothing for FLUX Klein effects (remove/edit). 'none' = no smoothing (fastest, least VRAM). 'gaussian' = Gaussian blur across time (reduces flicker, +700 MiB RAM). 'adaptive' = per-pixel deviation check, only smooths outlier frames (+700 MiB RAM).",
                }),

                # ── Advanced: MMAudio ─────────────────────────────────────
                "mmaudio_mode": (["replace", "mix"], {
                    "default": "replace",
                    "tooltip": "How to combine AI-generated audio with existing audio (used in 'generate_audio' no_llm_mode). "
                               "'replace' replaces existing audio entirely. "
                               "'mix' blends generated audio with the original track.",
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

    RETURN_TYPES = ("IMAGE", "AUDIO", "STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("images", "audio", "video_path", "command_log", "analysis", "mask_overlay_path")
    OUTPUT_TOOLTIPS = (
        "Image frames from the output video. Returns ALL frames automatically when connected to a downstream node (e.g. VHS Video Combine). Returns only a thumbnail when unconnected (zero-memory preview).",
        "Audio extracted from the output video (or passed through from audio_a) in ComfyUI AUDIO format.",
        "Absolute path to the rendered output video file.",
        "The ffmpeg command that was executed.",
        "LLM interpretation, estimated changes, pipeline steps, and any warnings.",
        "Path to a mask overlay preview video with SAM3-style colored contours. Connect to Save Video (FFMPEGA) to view.",
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
            "picture_in_picture", "pip", "blend",
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

    def _collect_frame_output(self, output_path, unique_id, hidden_prompt, removes_audio):
        """Delegate to output_handler module."""
        return _oh.collect_frame_output(self.media_converter, output_path, unique_id, hidden_prompt, removes_audio)

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
        use_vision: bool = True,
        ptc_mode: str = "off",
        verify_output: bool = True,
        whisper_device: str = "cpu",
        whisper_model: str = "large-v3",
        sam3_device: str = "gpu",
        sam3_max_objects: int = 5,
        sam3_det_threshold: float = 0.7,
        mask_points: str = "",
        flux_smoothing: str = "none",
        mmaudio_mode: str = "replace",
        batch_mode: bool = False,
        video_folder: str = "",
        file_pattern: str = "*.mp4",
        max_concurrent: int = 4,
        track_tokens: bool = True,
        log_usage: bool = False,
        allow_model_downloads: bool = True,
        **kwargs,  # hidden: prompt (PROMPT dict), extra_pnginfo (EXTRA_PNGINFO)
    ) -> tuple[torch.Tensor, dict, str, str, str, str]:
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

        # --- Inject FFMPEGA Effects Builder pipeline if provided ---
        if pipeline_json and pipeline_json.strip():
            prompt = self._inject_effects_hints(prompt, pipeline_json)

        # --- Batch mode ---
        if batch_mode:
            return await self._process_batch(
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
                flux_smoothing=flux_smoothing,
                pipeline_json=pipeline_json,
            )

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
        # images_a is freed inside _resolve_inputs when a tensor; null out local ref
        images_a = None

        if not prompt.strip():
            # manual + whisper + lip_sync modes don't need a prompt
            if llm_model != "none" or no_llm_mode not in ("manual", "transcribe", "karaoke_subtitles", "generate_audio", "lip_sync", "animate_portrait"):
                raise ValueError("Prompt cannot be empty")

        # --- Analyze input video ---
        video_metadata = self.analyzer.analyze(effective_video_path)
        metadata_str = video_metadata.to_analysis_string()

        # ================================================================== #
        #  No-LLM mode — bypass pipeline generation entirely                #
        # ================================================================== #
        if llm_model == "none":
            # Effects Builder connected → execute its pipeline directly
            if pipeline_json and pipeline_json.strip():
                return await self._process_effects_pipeline(
                    pipeline_json=pipeline_json,
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
                    flux_smoothing=flux_smoothing,
                    temp_video_from_images=temp_video_from_images,
                    temp_video_with_audio=temp_video_with_audio,
                    image_a=image_a,
                    audio_a=audio_a,
                    _all_video_paths=_all_video_paths,
                    _all_image_paths=_all_image_paths,
                    _all_text_inputs=_all_text_inputs,
                    **kwargs,
                )
            # Whisper-only mode (transcribe or karaoke)
            if no_llm_mode in ("transcribe", "karaoke_subtitles"):
                return await self._process_whisper_only(
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
            # SAM3-only mode (prompt = text target)
            if no_llm_mode == "sam3_masking":
                return await self._process_sam3_only(
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
            # MMAudio-only mode (generate_audio from video/prompt)
            if no_llm_mode == "generate_audio":
                return await self._process_mmaudio_only(
                    prompt=prompt,
                    mmaudio_mode=mmaudio_mode,
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
            # Lip sync mode (MuseTalk from connected audio_a)
            if no_llm_mode == "lip_sync":
                return await self._process_lip_sync_only(
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
            # Animate portrait mode (LivePortrait from connected video_a)
            if no_llm_mode == "animate_portrait":
                # video_a is the driving video
                driving_video = _all_video_paths[0] if _all_video_paths else ""
                return await self._process_animate_portrait_only(
                    effective_video_path=effective_video_path,
                    video_metadata=video_metadata,
                    save_output=save_output,
                    output_path=output_path,
                    preview_mode=preview_mode,
                    quality_preset=quality_preset,
                    crf=crf,
                    encoding_preset=encoding_preset,
                    driving_video=driving_video,
                    temp_video_from_images=temp_video_from_images,
                    temp_video_with_audio=temp_video_with_audio,
                    **kwargs,
                )
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
                return await self._process_effects_pipeline(
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
                    flux_smoothing=flux_smoothing,
                    temp_video_from_images=temp_video_from_images,
                    temp_video_with_audio=temp_video_with_audio,
                    image_a=image_a,
                    audio_a=audio_a,
                    _all_video_paths=_all_video_paths,
                    _all_image_paths=_all_image_paths,
                    _all_text_inputs=_all_text_inputs,
                    **kwargs,
                )
            # manual mode without Effects Builder or text
            raise RuntimeError(
                "No-LLM 'manual' mode requires an Effects Builder node or "
                "FFMPEGA Text node. Connect one to the pipeline_json or "
                "text_a input, or switch no_llm_mode to 'sam3_masking', "
                "'transcribe', 'karaoke_subtitles', 'generate_audio', or 'lip_sync'."
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
            flux_smoothing=flux_smoothing,
            mmaudio_mode=mmaudio_mode,
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

        return (images_tensor, audio_out, output_path, command.to_string(), analysis, mask_overlay_path)

    # ------------------------------------------------------------------ #
    #  Effects Builder support                                             #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _inject_effects_hints(prompt: str, pipeline_json: str) -> str:
        """Append Effects Builder selections as explicit skill hints.

        When an LLM is active and the Effects Builder is connected, the
        selected skills are injected as anchors so the LLM doesn't have
        to search through all skills — particularly helpful for smaller
        models.
        """
        import json as _json
        try:
            data = _json.loads(pipeline_json)
        except (ValueError, TypeError):
            return prompt

        steps = data.get("pipeline", [])
        raw = data.get("raw_ffmpeg", "")
        if not steps and not raw:
            return prompt

        hint_lines = [
            "\n\n--- EFFECTS BUILDER (pre-selected by user) ---",
            "The user has pre-selected the following effects. You MUST include",
            "these EXACT skills in your pipeline with the specified parameters.",
            "You may add additional skills if the user's prompt requires them.",
        ]

        for step in steps:
            skill = step.get("skill", "")
            params = step.get("params", {})
            if skill:
                params_str = ", ".join(f"{k}={v}" for k, v in params.items()) if params else "defaults"
                hint_lines.append(f"  - {skill} ({params_str})")

        if raw:
            hint_lines.append(f"  - RAW FFMPEG FILTERS: {raw}")

        hint_lines.append("--- END EFFECTS BUILDER ---")

        return prompt + "\n".join(hint_lines)

    async def _process_effects_pipeline(self, pipeline_json, prompt, effective_video_path, video_metadata, save_output, output_path, preview_mode, quality_preset, crf, encoding_preset, whisper_device="cpu", whisper_model="large-v3", sam3_device="gpu", sam3_max_objects=5, sam3_det_threshold=0.7, mask_points="", flux_smoothing="none", temp_video_from_images=None, temp_video_with_audio=None, image_a=None, audio_a=None, _all_video_paths=None, _all_image_paths=None, _all_text_inputs=None, **kwargs):
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

    async def _process_mmaudio_only(self, prompt, mmaudio_mode, effective_video_path, video_metadata, save_output, output_path, preview_mode, quality_preset, crf, encoding_preset, temp_video_from_images=None, temp_video_with_audio=None, **kwargs):
        """Delegate to nollm_modes module."""
        return await _nollm.process_mmaudio_only(
            media_converter=self.media_converter,
            prompt=prompt, mmaudio_mode=mmaudio_mode,
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

    async def _process_animate_portrait_only(self, effective_video_path, video_metadata, save_output, output_path, preview_mode, quality_preset, crf, encoding_preset, driving_video="", temp_video_from_images=None, temp_video_with_audio=None, **kwargs):
        """Delegate to nollm_modes module."""
        return await _nollm.process_animate_portrait_only(
            media_converter=self.media_converter,
            effective_video_path=effective_video_path,
            video_metadata=video_metadata, save_output=save_output,
            output_path=output_path, preview_mode=preview_mode,
            quality_preset=quality_preset, crf=crf,
            encoding_preset=encoding_preset,
            driving_video=driving_video,
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

    async def _process_batch(self, video_folder, file_pattern, prompt, llm_model, quality_preset, ollama_url, api_key, custom_model, crf, encoding_preset, max_concurrent, save_output, output_path, use_vision=True, verify_output=False, ptc_mode="off", sam3_max_objects=5, sam3_det_threshold=0.7, mask_points="", pipeline_json="", flux_smoothing="none"):
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
            flux_smoothing=flux_smoothing,
        )
    @classmethod
    def IS_CHANGED(cls, video_path, prompt, seed=0, **kwargs):
        """Determine if the node needs to re-execute."""
        return f"{video_path}:{prompt}:{seed}"
