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
try:
    from ..core.sanitize import validate_video_path
except ImportError:
    from core.sanitize import validate_video_path

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
        from ..core.llm.cli_utils import resolve_cli_binary

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
                    "default": all_models[0],
                    "tooltip": "AI model used to interpret your prompt. Select 'none' for no-LLM mode — use 'no_llm_mode' to choose between SAM3 masking, Whisper transcription, or karaoke subtitles. Local Ollama models appear next, followed by cloud API models (require api_key).",
                }),
                "no_llm_mode": (["manual", "sam3_masking", "transcribe", "karaoke_subtitles"], {
                    "default": "manual",
                    "tooltip": "What to do when llm_model is 'none'. "
                               "'manual' runs the Effects Builder pipeline directly (no AI). "
                               "'sam3_masking' uses the prompt as a SAM3 text target. "
                               "'transcribe' runs Whisper speech-to-text and burns SRT subtitles. "
                               "'karaoke_subtitles' runs Whisper and burns word-by-word karaoke subtitles.",
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
                    "tooltip": "Audio input. Connect additional audio and more slots appear automatically (audio_b, audio_c, ...). Used for muxing audio into video, or for multi-audio skills like concat.",
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

                # ── Advanced toggle ───────────────────────────────────────
                "advanced_options": ("BOOLEAN", {
                    "default": False,
                    "label_on": "Advanced",
                    "label_off": "Simple",
                    "tooltip": "Show advanced options: preview, encoding, vision, verification, SAM3/Whisper tuning, batch processing, and usage tracking.",
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

                # ── Advanced: LLM Behavior ────────────────────────────────
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
                    "default": 5,
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

    @staticmethod
    def _inject_effects_hints(prompt: str, pipeline_json: str) -> str:
        """Inject FFMPEGAEffectsBuilder parameters into the prompt.

        This converts the pipeline_json from the effects builder node
        into explicit instructions for the LLM to follow.
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

    def _resolve_inputs(
        self,
        video_path: str,
        images_a,
        image_a,
        image_path_a: str,
        video_a: str,
        text_a: str,
        subtitle_path: str,
        audio_a,
        **kwargs,
    ):
        """Resolve all input types and return effective_video_path plus
        collected extras.

        Returns
        -------
        tuple of:
            effective_video_path (str),
            temp_video_from_images (str | None),
            temp_video_with_audio (str | None),
            _all_video_paths (list[str]),
            _all_image_paths (list[str]),
            _all_text_inputs (list[str]),
            _images_a_shape (tuple | None),  -- shape before tensor was freed
        """
        temp_video_from_images = None
        temp_video_with_audio = None
        _images_a_shape = None

        # Collect all video_* path inputs
        _all_video_paths = []
        if video_a and video_a.strip() and os.path.isfile(video_a.strip()):
            _all_video_paths.append(video_a.strip())
        for k in sorted(kwargs):
            if k.startswith("video_") and k not in ("video_folder", "video_path") and kwargs[k]:
                vp = str(kwargs[k]).strip()
                if vp and os.path.isfile(vp):
                    _all_video_paths.append(vp)

        # Collect all image_path_* inputs
        _all_image_paths = []
        if image_path_a and image_path_a.strip() and os.path.isfile(image_path_a.strip()):
            _all_image_paths.append(image_path_a.strip())
        for k in sorted(kwargs):
            if k.startswith("image_path_") and kwargs[k]:
                ip = str(kwargs[k]).strip()
                if ip and os.path.isfile(ip):
                    _all_image_paths.append(ip)

        # Collect all text_* inputs
        _all_text_inputs = []
        if text_a and text_a.strip():
            _all_text_inputs.append(text_a.strip())
        for k in sorted(kwargs):
            if k.startswith("text_") and kwargs[k]:
                tv = str(kwargs[k]).strip()
                if tv:
                    _all_text_inputs.append(tv)
        if subtitle_path and subtitle_path.strip():
            sp = subtitle_path.strip()
            if os.path.isfile(sp):
                _all_text_inputs.insert(0, json.dumps({
                    "text": "",
                    "mode": "subtitle",
                    "path": sp,
                    "position": "bottom_center",
                    "font_size": 24,
                    "font_color": "white",
                    "start_time": 0.0,
                    "end_time": -1.0,
                    "auto_mode": True,
                }))

        has_extra_images = (
            image_a is not None
            or any(k.startswith("image_") and not k.startswith("image_path_") and kwargs.get(k) is not None for k in kwargs)
            or len(_all_video_paths) > 0
            or len(_all_image_paths) > 0
        )

        if images_a is not None:
            _images_a_shape = images_a.shape
            temp_video_from_images = self.media_converter.images_to_video(images_a)
            effective_video_path = temp_video_from_images
            del images_a
            import gc
            gc.collect()
            try:
                import torch as _torch
                if _torch.cuda.is_available():
                    _torch.cuda.empty_cache()
            except Exception:
                pass
        elif video_path and video_path.strip():
            effective_video_path = video_path
        elif _all_video_paths:
            effective_video_path = _all_video_paths.pop(0)
        elif has_extra_images:
            dummy = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
            dummy.close()
            import subprocess
            subprocess.run(
                ["ffmpeg", "-y", "-f", "lavfi", "-i",
                 "color=c=black:s=1920x1080:d=1:r=25",
                 "-c:v", "libx264", "-t", "1", dummy.name],
                capture_output=True,
            )
            temp_video_from_images = dummy.name
            effective_video_path = dummy.name
        else:
            effective_video_path = video_path

        from ..core.sanitize import validate_video_path  # type: ignore[import-not-found]
        effective_video_path = validate_video_path(effective_video_path)

        # Pre-mux audio into the video if it has no audio stream
        if audio_a is not None and not self.media_converter.has_audio_stream(effective_video_path):
            tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
            tmp.close()
            import shutil as _shmod
            _shmod.copy2(effective_video_path, tmp.name)
            self.media_converter.mux_audio(tmp.name, audio_a)
            temp_video_with_audio = tmp.name
            effective_video_path = tmp.name

        return (
            effective_video_path,
            temp_video_from_images,
            temp_video_with_audio,
            _all_video_paths,
            _all_image_paths,
            _all_text_inputs,
            _images_a_shape,
        )

    def _build_connected_inputs_summary(
        self,
        images_a,
        _images_a_shape,
        video_path: str,
        audio_a,
        image_a,
        _all_video_paths: list,
        _all_image_paths: list,
        _all_text_inputs: list,
        video_metadata,
        **kwargs,
    ) -> str:
        """Build the connected-inputs context string sent to the LLM."""
        input_lines = []

        if images_a is not None:
            dur = (video_metadata.primary_video.duration
                   if video_metadata.primary_video and video_metadata.primary_video.duration else "unknown")
            fps = (video_metadata.primary_video.frame_rate
                   if video_metadata.primary_video and video_metadata.primary_video.frame_rate else "unknown")
            input_lines.append(
                f"- images_a (video): connected — primary video input, "
                f"{images_a.shape[0]} frames, {dur}s, {fps}fps"
            )
        elif _images_a_shape is not None:
            dur = (video_metadata.primary_video.duration
                   if video_metadata.primary_video and video_metadata.primary_video.duration else "unknown")
            fps = (video_metadata.primary_video.frame_rate
                   if video_metadata.primary_video and video_metadata.primary_video.frame_rate else "unknown")
            input_lines.append(
                f"- images_a (video): connected — primary video input, "
                f"{_images_a_shape[0]} frames, {dur}s, {fps}fps"
            )
        elif video_path and video_path.strip():
            input_lines.append("- video_path: connected — file input")

        for k in sorted(kwargs):
            if k.startswith("images_") and k != "images_a" and kwargs[k] is not None:
                tensor = kwargs[k]
                input_lines.append(f"- {k} (video): connected — {tensor.shape[0]} frames")

        for vi, vp in enumerate(_all_video_paths):
            letter = chr(ord('a') + vi)
            input_lines.append(f"- video_{letter} (video file): connected — {vp}")

        if audio_a is not None:
            sr = audio_a.get("sample_rate", "unknown")
            wf = audio_a.get("waveform")
            dur_str = "unknown"
            if wf is not None and sr and sr != "unknown":
                dur_str = f"{wf.shape[-1] / sr:.1f}s"
            input_lines.append(f"- audio_a: connected — {dur_str}, {sr}Hz")
        for k in sorted(kwargs):
            if k.startswith("audio_") and k != "audio_a" and kwargs[k] is not None:
                ad = kwargs[k]
                sr = ad.get("sample_rate", "unknown")
                wf = ad.get("waveform")
                dur_str = "unknown"
                if wf is not None and sr and sr != "unknown":
                    dur_str = f"{wf.shape[-1] / sr:.1f}s"
                input_lines.append(f"- {k}: connected — {dur_str}, {sr}Hz")

        if image_a is not None:
            input_lines.append(
                f"- image_a: connected — single image "
                f"{image_a.shape[2]}x{image_a.shape[1]}"
            )
        for k in sorted(kwargs):
            if (k.startswith("image_") and k != "image_a"
                    and not k.startswith("images_")
                    and not k.startswith("image_path_")
                    and kwargs[k] is not None):
                img = kwargs[k]
                input_lines.append(
                    f"- {k}: connected — single image {img.shape[2]}x{img.shape[1]}"
                )

        for ii, ip in enumerate(_all_image_paths):
            letter = chr(ord('a') + ii)
            input_lines.append(f"- image_path_{letter} (image file): connected — {ip}")

        for ti, raw_text in enumerate(_all_text_inputs):
            letter = chr(ord('a') + ti)
            try:
                meta = json.loads(raw_text)
                if isinstance(meta, dict) and "mode" in meta:
                    mode = meta.get("mode", "raw")
                    text_preview = meta.get("text", "")[:60]
                    path = meta.get("path", "")
                    if path:
                        input_lines.append(
                            f"- text_{letter} ({mode}): connected — subtitle file: {path}"
                        )
                    else:
                        input_lines.append(
                            f"- text_{letter} ({mode}): connected — "
                            f"\"{text_preview}{'...' if len(meta.get('text', '')) > 60 else ''}\" "
                            f"({len(meta.get('text', ''))} chars)"
                        )
                    continue
            except (json.JSONDecodeError, TypeError):
                pass
            preview = raw_text[:60]
            input_lines.append(
                f"- text_{letter} (raw text): connected — "
                f"\"{preview}{'...' if len(raw_text) > 60 else ''}\" "
                f"({len(raw_text)} chars)"
            )

        return "\n".join(input_lines) if input_lines else "No extra inputs connected"

    def _build_output_path(
        self,
        effective_video_path: str,
        save_output: bool,
        output_path: str,
        preview_mode: bool,
    ):
        """Determine output path and optional temp render directory.

        Returns
        -------
        (output_path: str, temp_render_dir: str | None)
        """
        from ..core.sanitize import (  # type: ignore[import-not-found]
            validate_output_file_path,
            validate_output_path as _validate_output_path,
        )
        stem = Path(effective_video_path).stem
        suffix = "_preview" if preview_mode else "_edited"
        temp_render_dir = None

        if save_output:
            if not output_path:
                output_dir = folder_paths.get_output_directory()
                output_path = str(Path(output_dir) / f"{stem}{suffix}.mp4")
            elif Path(output_path).is_dir() or output_path.endswith(os.sep):
                output_dir = _validate_output_path(output_path.rstrip(os.sep))
                output_path = str(Path(output_dir) / f"{stem}{suffix}.mp4")
            elif not Path(output_path).suffix:
                output_dir = _validate_output_path(output_path)
                os.makedirs(output_dir, exist_ok=True)
                output_path = str(Path(output_dir) / f"{stem}{suffix}.mp4")
            else:
                output_path = validate_output_file_path(output_path)
        else:
            temp_render_dir = tempfile.mkdtemp(prefix="ffmpega_")
            output_path = str(Path(temp_render_dir) / f"{stem}{suffix}.mp4")

        os.makedirs(Path(output_path).parent, exist_ok=True)
        return output_path, temp_render_dir

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

        return (
            effective_video_path,
            temp_multi_videos,
            temp_audio_files,
            temp_frames_dirs,
            temp_audio_input,
        )

    async def _execute_pipeline(
        self,
        pipeline,
        command,
        connector,
        prompt: str,
        metadata_str: str,
        connected_inputs_str: str,
        effective_video_path: str,
        output_path: str,
        quality_preset: str,
        crf: int,
        encoding_preset: str,
        preview_mode: bool,
        verify_output: bool,
        use_vision: bool,
        ptc_mode: str,
        video_metadata,
        _all_text_inputs: list,
    ):
        """Dry-run validate, execute, retry on error, and optionally verify output.

        Returns
        -------
        (result, pipeline, command)
        """
        from ..skills.composer import Pipeline  # type: ignore[import-not-found]

        # FPS normalization for speed changes
        vf_str = command.video_filters.to_string()
        if "setpts=" in vf_str and not command.complex_filter:
            input_fps = (
                video_metadata.primary_video.frame_rate
                if video_metadata.primary_video and video_metadata.primary_video.frame_rate
                else 30
            )
            command.video_filters.add_filter("fps", {"fps": int(round(input_fps))})

        logger.debug("Command: %s", command.to_string())
        logger.debug("Audio filters: '%s'", command.audio_filters.to_string())
        logger.debug("Video filters: '%s'", command.video_filters.to_string())
        if command.complex_filter:
            logger.debug("Complex filter: '%s'", command.complex_filter)
        logger.debug("Pipeline steps: %s", [(s.skill_name, s.params) for s in pipeline.steps])

        # Dry-run validation
        dry_result = self.process_manager.dry_run(command, timeout=30)
        if not dry_result.success:
            logger.warning("Dry-run failed: %s (will attempt execution anyway)", dry_result.error_message)

        # Preview downscale
        if preview_mode:
            if command.complex_filter:
                command.output_options.extend(["-s", "480x270"])
            else:
                command.video_filters.add_filter("scale", {"w": 480, "h": -1})
            command.output_options.extend(["-t", "10"])

        # Execute with error-feedback retry
        max_attempts = 2
        result = None
        for attempt in range(max_attempts):
            result = self.process_manager.execute(command, timeout=600)
            if result.success:
                break
            if attempt < max_attempts - 1:
                logger.warning(
                    "FFMPEG failed (attempt %d), feeding error back to LLM: %s",
                    attempt + 1, result.error_message,
                )
                error_prompt = (
                    f"The previous FFMPEG command failed.\n"
                    f"Original request: {prompt}\n"
                    f"Failed command: {command.to_string()}\n"
                    f"Error: {result.error_message}\n"
                    f"Stderr: {result.stderr[-500:] if result.stderr else 'N/A'}\n\n"
                    f"Please fix the pipeline to avoid this error. "
                    f"Return only the corrected pipeline JSON."
                )
                try:
                    retry_spec = await self.pipeline_generator.generate(
                        connector, error_prompt, metadata_str,
                        connected_inputs=connected_inputs_str,
                        video_path=effective_video_path,
                        use_vision=use_vision,
                        ptc_mode=ptc_mode,
                    )
                    pipeline = Pipeline(
                        input_path=effective_video_path,
                        output_path=output_path,
                        extra_inputs=pipeline.extra_inputs,
                        metadata=pipeline.metadata,
                    )
                    pipeline.text_inputs = _all_text_inputs
                    for step in retry_spec.get("pipeline", []):
                        skill_name = step.get("skill")
                        params = step.get("params", {})
                        if skill_name:
                            pipeline.add_step(skill_name, params)
                    if quality_preset and not any(
                        s.skill_name in ["quality", "compress"] for s in pipeline.steps
                    ):
                        _crf_map = {"draft": 28, "standard": 23, "high": 18, "lossless": 0}
                        _preset_map = {"draft": "ultrafast", "standard": "medium", "high": "slow", "lossless": "veryslow"}
                        pipeline.add_step("quality", {
                            "crf": crf if crf >= 0 else _crf_map.get(quality_preset, 23),
                            "preset": encoding_preset if encoding_preset != "auto" else _preset_map.get(quality_preset, "medium"),
                        })
                    command = self.composer.compose(pipeline)
                    retry_vf = command.video_filters.to_string()
                    if "setpts=" in retry_vf and not command.complex_filter:
                        _input_fps = (
                            video_metadata.primary_video.frame_rate
                            if video_metadata.primary_video and video_metadata.primary_video.frame_rate
                            else 30
                        )
                        command.video_filters.add_filter("fps", {"fps": int(round(_input_fps))})
                    logger.debug("Retry command: %s", command.to_string())
                    if preview_mode:
                        if command.complex_filter:
                            command.output_options.extend(["-s", "480x270"])
                        else:
                            command.video_filters.add_filter("scale", {"w": 480, "h": -1})
                        command.output_options.extend(["-t", "10"])
                except Exception as retry_err:
                    logger.warning("Error feedback retry failed: %s", retry_err)
                    break

        if not result.success:
            if hasattr(connector, 'close'):
                await connector.close()
            raise RuntimeError(
                f"FFMPEG execution failed: {result.error_message}\n"
                f"Command: {command.to_string()}"
            )

        # Output verification
        _VERIFICATION_TIMEOUT = 90.0
        _MAX_CORRECTION_ATTEMPTS = 2
        _skill_degraded = pipeline.metadata.get("_skill_degraded", False)
        if _skill_degraded:
            logger.info("Skipping output verification — skill handler reported degraded output (e.g. SAM3 OOM fallback)")
        elif verify_output and result.success:
            logger.info("Output verification enabled — inspecting result...")
            for attempt in range(_MAX_CORRECTION_ATTEMPTS):
                try:
                    verification_result = await asyncio.wait_for(
                        self._verify_output(
                            connector=connector,
                            output_path=output_path,
                            prompt=prompt,
                            pipeline=pipeline,
                            effective_video_path=effective_video_path,
                            use_vision=use_vision,
                        ),
                        timeout=_VERIFICATION_TIMEOUT,
                    )
                    if verification_result is not None:
                        result, pipeline, command = verification_result
                        logger.info("Correction attempt %d applied — re-verifying...", attempt + 1)
                        continue
                    else:
                        logger.info("Verification PASS (attempt %d)", attempt + 1)
                        break
                except asyncio.TimeoutError:
                    logger.warning(
                        "Output verification timed out after %.0fs — keeping current output",
                        _VERIFICATION_TIMEOUT,
                    )
                    break
                except Exception as verify_err:
                    logger.warning("Output verification failed: %s", verify_err)
                    break

        return result, pipeline, command

    def _handle_audio_output(
        self,
        command,
        pipeline,
        audio_a,
        audio_source: str,
        audio_mode: str,
        output_path: str,
        **kwargs,
    ) -> None:
        """Mux or replace audio in the output file as directed by the LLM spec."""
        removes_audio = "-an" in command.output_options
        has_audio_processing = removes_audio or bool(command.audio_filters.to_string())
        audio_already_embedded = pipeline.metadata.get("_has_embedded_audio", False)

        audio_inputs = {}
        if audio_a is not None:
            audio_inputs["audio_a"] = audio_a
        for k in sorted(kwargs):
            if k.startswith("audio_") and k != "audio_a" and kwargs[k] is not None:
                audio_inputs[k] = kwargs[k]

        if audio_source == "mix":
            for step in pipeline.steps:
                step_audio = step.params.get("audio_source")
                if step_audio and step_audio != "mix":
                    audio_source = step_audio
                    break

        logger.debug(
            "Audio decision: removes=%s, has_processing=%s, "
            "already_embedded=%s, audio_source=%s, available=%s",
            removes_audio, has_audio_processing,
            audio_already_embedded, audio_source, list(audio_inputs.keys()),
        )

        if audio_inputs and not removes_audio and not has_audio_processing and not audio_already_embedded:
            if audio_source and audio_source != "mix" and audio_source in audio_inputs:
                logger.debug("Using specific audio: %s", audio_source)
                self.media_converter.mux_audio(output_path, audio_inputs[audio_source], audio_mode=audio_mode)
            elif len(audio_inputs) == 1:
                name = list(audio_inputs.keys())[0]
                logger.debug("Using only available audio: %s", name)
                self.media_converter.mux_audio(output_path, audio_inputs[name], audio_mode=audio_mode)
            else:
                logger.debug("Mixing %d audio tracks: %s", len(audio_inputs), list(audio_inputs.keys()))
                self.media_converter.mux_audio_mix(output_path, list(audio_inputs.values()), audio_mode=audio_mode)
        elif audio_inputs and audio_already_embedded and not removes_audio:
            if audio_source and audio_source != "mix" and audio_source in audio_inputs:
                logger.info("Replacing concat audio with explicit audio source: %s", audio_source)
                self.media_converter.mux_audio(output_path, audio_inputs[audio_source], audio_mode="replace")
            elif len(audio_inputs) == 1:
                name = list(audio_inputs.keys())[0]
                logger.info("Replacing concat audio with connected %s", name)
                self.media_converter.mux_audio(output_path, audio_inputs[name], audio_mode="replace")
            else:
                logger.debug(
                    "Multiple audio inputs with embedded audio — skipping "
                    "replacement (ambiguous intent)"
                )

    def _collect_frame_output(
        self,
        output_path: str,
        unique_id: str,
        hidden_prompt: dict,
        removes_audio: bool,
    ):
        """Extract output frames and audio. Returns (images_tensor, audio_out)."""
        images_connected = False
        if unique_id and hidden_prompt:
            for node_id, node_data in hidden_prompt.items():
                if str(node_id) == unique_id:
                    continue
                for inp_val in (node_data.get("inputs") or {}).values():
                    if (
                        isinstance(inp_val, list)
                        and len(inp_val) == 2
                        and str(inp_val[0]) == unique_id
                        and inp_val[1] == 0
                    ):
                        images_connected = True
                        break
                if images_connected:
                    break

        if images_connected:
            logger.info("images output is connected — loading all frames from output video")
            images_tensor = self.media_converter.frames_to_tensor(output_path)
            logger.debug("Output full frames shape: %s", images_tensor.shape)
        else:
            images_tensor = self._extract_thumbnail_frame(output_path)
            logger.debug("Output thumbnail shape: %s", images_tensor.shape)

        if removes_audio:
            audio_out = {"waveform": torch.zeros(1, 1, 1, dtype=torch.float32), "sample_rate": 44100}
        else:
            audio_out = self.media_converter.extract_audio(output_path)

        return images_tensor, audio_out

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
            # manual + whisper modes don't need a prompt
            if llm_model != "none" or no_llm_mode not in ("manual", "transcribe", "karaoke_subtitles"):
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
                "'transcribe', or 'karaoke_subtitles'."
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

        # --- Generate pipeline via LLM ---
        if not ollama_url or not ollama_url.startswith(("http://", "https://")):
            ollama_url = "http://localhost:11434"
        effective_model = llm_model
        if llm_model == "custom":
            if not custom_model or not custom_model.strip():
                raise ValueError(
                    "Please enter a model name in the 'custom_model' field "
                    "when using 'custom' mode."
                )
            effective_model = custom_model.strip()
        connector = self.pipeline_generator.create_connector(effective_model, ollama_url, api_key)

        # --- LLM Hint Mode: inject Effects Builder selections into prompt ---
        effective_prompt = prompt
        if pipeline_json and pipeline_json.strip():
            effective_prompt = self._inject_effects_hints(prompt, pipeline_json)

        try:
            spec = await self.pipeline_generator.generate(
                connector, effective_prompt, metadata_str,
                connected_inputs=connected_inputs_str,
                video_path=effective_video_path,
                use_vision=use_vision,
                ptc_mode=ptc_mode,
            )
        except Exception as e:
            if hasattr(connector, 'close'):
                await connector.close()
            if api_key and api_key in str(e):
                from core.sanitize import sanitize_api_key
                raise RuntimeError(sanitize_api_key(str(e), api_key)) from None
            raise

        interpretation = spec.get("interpretation", "")
        warnings = spec.get("warnings", [])
        estimated_changes = spec.get("estimated_changes", "")
        pipeline_steps = spec.get("pipeline", [])
        audio_source = spec.get("audio_source", "mix")
        audio_mode = spec.get("audio_mode", "loop")
        if audio_mode not in ("loop", "pad", "trim"):
            audio_mode = "loop"
        logger.debug("audio_source from LLM: %s, audio_mode: %s", audio_source, audio_mode)

        # --- Build output path ---
        output_path, temp_render_dir = self._build_output_path(
            effective_video_path=effective_video_path,
            save_output=save_output,
            output_path=output_path,
            preview_mode=preview_mode,
        )

        # --- Assemble pipeline object ---
        pipeline = Pipeline(input_path=effective_video_path, output_path=output_path)
        input_fps = (
            video_metadata.primary_video.frame_rate
            if video_metadata.primary_video and video_metadata.primary_video.frame_rate
            else 24
        )
        pipeline.metadata["_input_fps"] = int(round(input_fps))
        input_duration = (
            video_metadata.primary_video.duration
            if video_metadata.primary_video and video_metadata.primary_video.duration
            else 0
        )
        if input_duration:
            pipeline.metadata["_video_duration"] = input_duration
        if video_metadata.primary_video:
            pipeline.metadata["_input_width"] = video_metadata.primary_video.width
            pipeline.metadata["_input_height"] = video_metadata.primary_video.height

        for step in pipeline_steps:
            skill_name = step.get("skill")
            params = step.get("params", {})
            if skill_name:
                pipeline.add_step(skill_name, params)

        # Fix format-changing skill output extension
        _FORMAT_SKILLS = {"gif": ".gif", "webm": ".webm"}
        new_ext = None
        for step in pipeline.steps:
            if step.skill_name in _FORMAT_SKILLS:
                new_ext = _FORMAT_SKILLS[step.skill_name]
            elif step.skill_name == "container":
                fmt = step.params.get("format", "mp4")
                new_ext = f".{fmt}"
        if new_ext and not output_path.endswith(new_ext):
            old_path = output_path
            output_path = str(Path(output_path).with_suffix(new_ext))
            pipeline.output_path = output_path
            logger.debug("Output format changed: %s → %s", old_path, output_path)

        # Add quality preset
        _NO_QUALITY_PRESET_SKILLS = {"gif", "webm"}
        has_incompatible_format = any(
            s.skill_name in _NO_QUALITY_PRESET_SKILLS for s in pipeline.steps
        ) or (new_ext and new_ext in {".gif", ".webm"})
        if quality_preset and not has_incompatible_format and not any(
            s.skill_name in ["quality", "compress"] for s in pipeline.steps
        ):
            crf_map = {"draft": 28, "standard": 23, "high": 18, "lossless": 0}
            preset_map = {"draft": "ultrafast", "standard": "medium", "high": "slow", "lossless": "veryslow"}
            pipeline.add_step("quality", {
                "crf": crf if crf >= 0 else crf_map.get(quality_preset, 23),
                "preset": encoding_preset if encoding_preset != "auto" else preset_map.get(quality_preset, "medium"),
            })

        # Validate pipeline
        is_valid, errors = self.composer.validate_pipeline(pipeline)
        if not is_valid:
            for err in errors:
                logger.warning("Pipeline validation: %s (continuing anyway)", err)

        # Pass whisper/SAM3 preferences
        has_transcribe_skill = any(
            s.skill_name in {"auto_transcribe", "transcribe", "speech_to_text",
                             "karaoke_subtitles", "whisper", "auto_subtitle", "auto_caption"}
            for s in pipeline.steps
        )
        if has_transcribe_skill:
            pipeline.metadata["_whisper_device"] = whisper_device
            pipeline.metadata["_whisper_model"] = whisper_model
        pipeline.metadata["_sam3_device"] = sam3_device
        pipeline.metadata["_sam3_max_objects"] = sam3_max_objects
        pipeline.metadata["_sam3_det_threshold"] = sam3_det_threshold
        if mask_points and mask_points.strip():
            pipeline.metadata["_mask_points"] = mask_points.strip()

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
            await connector.close()

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
        analysis = f"""Interpretation: {interpretation}

Estimated Changes: {estimated_changes}

Pipeline Steps:
{self.composer.explain_pipeline(pipeline)}

Warnings: {', '.join(warnings) if warnings else 'None'}"""

        # --- Token usage tracking ---
        token_usage = getattr(self.pipeline_generator, 'last_token_usage', None)
        if token_usage and (track_tokens or log_usage):
            est_tag = " (estimated)" if token_usage.get("estimated") else ""
            analysis += f"""

Token Usage{est_tag}:
  Prompt tokens:     {token_usage.get('total_prompt_tokens', 0):,}
  Completion tokens: {token_usage.get('total_completion_tokens', 0):,}
  Total tokens:      {token_usage.get('total_tokens', 0):,}
  LLM calls:         {token_usage.get('llm_calls', 0)}
  Tool calls:        {token_usage.get('tool_calls', 0)}
  Elapsed:           {token_usage.get('elapsed_sec', 0)}s"""

            if track_tokens:
                est_label = " (estimated)" if token_usage.get("estimated") else ""
                logger.info("┌─ Token Usage%s ────────────────────────────┐", est_label)
                logger.info("│ Model:       %-30s │", token_usage.get("model", "unknown"))
                logger.info("│ Provider:    %-30s │", token_usage.get("provider", "unknown"))
                logger.info("│ Prompt:      %-30s │", f"{token_usage.get('total_prompt_tokens', 0):,} tokens")
                logger.info("│ Completion:  %-30s │", f"{token_usage.get('total_completion_tokens', 0):,} tokens")
                logger.info("│ Total:       %-30s │", f"{token_usage.get('total_tokens', 0):,} tokens")
                logger.info("│ LLM calls:   %-30s │", str(token_usage.get("llm_calls", 0)))
                logger.info("│ Tool calls:  %-30s │", str(token_usage.get("tool_calls", 0)))
                logger.info("│ Elapsed:     %-30s │", f"{token_usage.get('elapsed_sec', 0)}s")
                logger.info("└────────────────────────────────────────────┘")

            if log_usage:
                from ..core.token_tracker import TokenTracker as _TT  # type: ignore[import-not-found]
                entry = {
                    "timestamp": __import__("time").strftime("%Y-%m-%dT%H:%M:%S"),
                    "model": token_usage.get("model", "unknown"),
                    "provider": token_usage.get("provider", "unknown"),
                    "prompt_tokens": token_usage.get("total_prompt_tokens", 0),
                    "completion_tokens": token_usage.get("total_completion_tokens", 0),
                    "total_tokens": token_usage.get("total_tokens", 0),
                    "estimated": token_usage.get("estimated", False),
                    "llm_calls": token_usage.get("llm_calls", 0),
                    "tool_calls": token_usage.get("tool_calls", 0),
                    "elapsed_sec": token_usage.get("elapsed_sec", 0),
                    "prompt_preview": prompt[:120] if prompt else "",
                }
                _TT.append_to_log(entry)

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

        # --- Generate mask output if auto_mask was used ---
        # IMPORTANT: This must run BEFORE temp file cleanup because
        # effective_video_path may point to a temp file (e.g. from image
        # inputs or audio muxing) that gets deleted in the cleanup block.
        mask_overlay_path = ""
        has_auto_mask = any(
            s.skill_name in {"auto_mask", "auto_segment", "segment",
                             "smart_mask", "sam_mask", "ai_mask", "object_mask"}
            for s in pipeline.steps
        )
        if has_auto_mask:
            # Look for the mask video generated by _f_auto_mask
            mask_video_path = pipeline.metadata.get("_mask_video_path", "")
            if mask_video_path and os.path.isfile(mask_video_path):
                mask_type = kwargs.get("mask_output_type", "colored_overlay")
                if mask_type == "black_white":
                    # Pass through the raw B&W mask video directly
                    mask_overlay_path = mask_video_path
                    logger.info("Using B&W mask video: %s", mask_overlay_path)
                else:
                    try:
                        from ..core.sam3_masker import generate_mask_overlay
                        mask_overlay_path = generate_mask_overlay(
                            video_path=effective_video_path,
                            mask_video_path=mask_video_path,
                        )
                        logger.info("Generated mask overlay: %s", mask_overlay_path)
                    except Exception as e:
                        logger.warning("Mask overlay generation failed: %s", e)

        # --- Cleanup temp files ---
        for tmp_path in (
            [temp_video_from_images, temp_video_with_audio, temp_audio_input]
            + temp_multi_videos
            + temp_audio_files
        ):
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
        for d in temp_frames_dirs:
            if os.path.isdir(d):
                shutil.rmtree(d, ignore_errors=True)
        if not save_output and temp_render_dir and os.path.isdir(temp_render_dir):
            if not os.listdir(temp_render_dir):
                shutil.rmtree(temp_render_dir, ignore_errors=True)

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

    async def _process_effects_pipeline(
        self,
        pipeline_json: str,
        prompt: str,
        effective_video_path: str,
        video_metadata,
        save_output: bool,
        output_path: str,
        preview_mode: bool,
        quality_preset: str,
        crf: int,
        encoding_preset: str,
        whisper_device: str = "cpu",
        whisper_model: str = "large-v3",
        sam3_device: str = "gpu",
        sam3_max_objects: int = 5,
        sam3_det_threshold: float = 0.7,
        mask_points: str = "",
        temp_video_from_images: Optional[str] = None,
        temp_video_with_audio: Optional[str] = None,
        image_a=None,
        audio_a=None,
        _all_video_paths: Optional[list] = None,
        _all_image_paths: Optional[list] = None,
        _all_text_inputs: Optional[list] = None,
        **kwargs,
    ) -> tuple[torch.Tensor, dict, str, str, str, str]:
        """Execute an Effects Builder pipeline directly (no LLM).

        Parses the JSON from the Effects Builder node and constructs a
        Pipeline from the skill steps + optional raw FFmpeg filters.

        Returns the standard 6-tuple.
        """
        import json as _json
        from ..skills.composer import Pipeline  # type: ignore[import-not-found]

        try:
            data = _json.loads(pipeline_json)
        except (ValueError, TypeError) as exc:
            raise RuntimeError(f"Effects Builder: invalid pipeline JSON: {exc}") from exc

        steps = data.get("pipeline", [])
        raw_ffmpeg = data.get("raw_ffmpeg", "")
        effects_mode = data.get("effects_mode", "empty")

        if effects_mode == "empty" and not raw_ffmpeg:
            raise RuntimeError(
                "Effects Builder: no effects selected and no raw FFmpeg filters. "
                "Please select at least one effect or provide raw filters."
            )

        logger.info(
            "Effects Builder mode: %s — %d skills, raw=%s",
            effects_mode, len(steps), bool(raw_ffmpeg),
        )

        # --- Build output path ---
        output_path, temp_render_dir = self._build_output_path(
            effective_video_path=effective_video_path,
            save_output=save_output,
            output_path=output_path,
            preview_mode=preview_mode,
        )

        # --- Construct Pipeline from effects JSON ---
        pipeline = Pipeline(input_path=effective_video_path, output_path=output_path)

        # Set metadata
        input_fps = (
            video_metadata.primary_video.frame_rate
            if video_metadata.primary_video and video_metadata.primary_video.frame_rate
            else 24
        )
        pipeline.metadata["_input_fps"] = int(round(input_fps))
        if video_metadata.primary_video:
            pipeline.metadata["_input_width"] = video_metadata.primary_video.width
            pipeline.metadata["_input_height"] = video_metadata.primary_video.height

        # SAM3 preferences (for auto_mask steps)
        pipeline.metadata["_sam3_device"] = sam3_device
        pipeline.metadata["_sam3_max_objects"] = sam3_max_objects
        pipeline.metadata["_sam3_det_threshold"] = sam3_det_threshold
        if mask_points and mask_points.strip():
            pipeline.metadata["_mask_points"] = mask_points.strip()

        # Whisper preferences (for transcription steps)
        pipeline.metadata["_whisper_device"] = whisper_device
        pipeline.metadata["_whisper_model"] = whisper_model

        # Add skill steps from the effects builder
        for step in steps:
            skill_name = step.get("skill", "")
            params = step.get("params", {})
            if skill_name:
                pipeline.add_step(skill_name, params)

        # --- Inject extra inputs (multi-input for concat/grid/etc.) ---
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
            _all_image_paths=_all_image_paths or [],
            _all_video_paths=_all_video_paths or [],
            _all_text_inputs=_all_text_inputs or [],
            audio_a=audio_a,
            **kwargs,
        )
        pipeline.input_path = effective_video_path

        # Quality preset (unless overridden by skills)
        _NO_QUALITY_PRESET_SKILLS = {"gif", "webm"}
        if quality_preset and not any(
            s.skill_name in _NO_QUALITY_PRESET_SKILLS for s in pipeline.steps
        ):
            crf_map = {"draft": 28, "standard": 23, "high": 18, "lossless": 0}
            preset_map = {"draft": "ultrafast", "standard": "medium", "high": "slow", "lossless": "veryslow"}
            pipeline.add_step("quality", {
                "crf": crf if crf >= 0 else crf_map.get(quality_preset, 23),
                "preset": encoding_preset if encoding_preset != "auto" else preset_map.get(quality_preset, "medium"),
            })

        # --- Compose & execute ---
        command = self.composer.compose(pipeline)

        # Inject raw FFmpeg filters (appended to video filter chain)
        if raw_ffmpeg and raw_ffmpeg.strip():
            for raw_filter in raw_ffmpeg.strip().split(","):
                raw_filter = raw_filter.strip()
                if raw_filter:
                    # Parse "name=params" into a Filter object
                    if "=" in raw_filter:
                        name, _, param_str = raw_filter.partition("=")
                        command.video_filters.add_filter(name.strip(), {"": param_str})
                    else:
                        command.video_filters.add_filter(raw_filter)
            logger.info("Effects Builder: appended raw filters: %s", raw_ffmpeg.strip())

        logger.debug("Effects Builder command: %s", command.to_string())

        if preview_mode:
            if command.complex_filter:
                command.output_options.extend(["-s", "480x270"])
            else:
                command.video_filters.add_filter("scale", {"w": 480, "h": -1})
            command.output_options.extend(["-t", "10"])

        result = self.process_manager.execute(command, timeout=600)
        if not result.success:
            raise RuntimeError(
                f"Effects Builder: FFMPEG execution failed: {result.error_message}\n"
                f"Command: {command.to_string()}"
            )

        # --- Collect frame/audio output ---
        unique_id = str(kwargs.get("unique_id", ""))
        hidden_prompt = kwargs.get("hidden_prompt") or {}
        images_tensor, audio_out = self._collect_frame_output(
            output_path=output_path,
            unique_id=unique_id,
            hidden_prompt=hidden_prompt,
            removes_audio="-an" in command.output_options,
        )

        # --- Mask overlay (if auto_mask was used) ---
        mask_overlay_path = ""
        mask_video_path = pipeline.metadata.get("_mask_video_path", "")
        if mask_video_path and os.path.isfile(mask_video_path):
            mask_type = kwargs.get("mask_output_type", "colored_overlay")
            if mask_type == "black_white":
                mask_overlay_path = mask_video_path
            else:
                try:
                    from ..core.sam3_masker import generate_mask_overlay
                    mask_overlay_path = generate_mask_overlay(
                        video_path=effective_video_path,
                        mask_video_path=mask_video_path,
                    )
                except Exception as e:
                    logger.warning("Effects Builder: mask overlay failed: %s", e)

        # --- Build analysis string ---
        step_summary = "\n".join(
            f"  {i+1}. {s.get('skill', '?')} {s.get('params', {})}"
            for i, s in enumerate(steps)
        )
        analysis = (
            f"Effects Builder Mode (no LLM)\n"
            f"Mode: {effects_mode}\n"
            f"Steps:\n{step_summary}\n"
            f"{'Raw filters: ' + raw_ffmpeg if raw_ffmpeg else ''}\n\n"
            f"Pipeline:\n{self.composer.explain_pipeline(pipeline)}"
        )

        # --- Cleanup temp files ---
        for tmp_path in [temp_video_from_images, temp_video_with_audio, temp_audio_input]:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
        for tmp_path in temp_multi_videos + temp_audio_files:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
        for tmp_dir in temp_frames_dirs:
            if tmp_dir and os.path.isdir(tmp_dir):
                shutil.rmtree(tmp_dir, ignore_errors=True)
        if not save_output and temp_render_dir and os.path.isdir(temp_render_dir):
            if not os.listdir(temp_render_dir):
                shutil.rmtree(temp_render_dir, ignore_errors=True)

        return (images_tensor, audio_out, output_path, command.to_string(), analysis, mask_overlay_path)

    # ------------------------------------------------------------------ #
    #  SAM3-only mode (no LLM)                                            #
    # ------------------------------------------------------------------ #

    async def _process_sam3_only(
        self,
        prompt: str,
        effective_video_path: str,
        video_metadata,
        save_output: bool,
        output_path: str,
        preview_mode: bool,
        quality_preset: str,
        crf: int,
        encoding_preset: str,
        sam3_device: str,
        sam3_max_objects: int,
        sam3_det_threshold: float,
        mask_points: str,
        temp_video_from_images: Optional[str],
        temp_video_with_audio: Optional[str],
        **kwargs,
    ) -> tuple[torch.Tensor, dict, str, str, str, str]:
        """Run SAM3 masking directly without any LLM involvement.

        Calls ``mask_video_subprocess`` directly — the main video output is
        a clean copy of the source (no effects applied).  The SAM3 mask is
        output via the ``mask_overlay_path`` (colored overlay or raw B&W).

        Returns the standard 6-tuple:
            (images_tensor, audio, output_path, command_log, analysis, mask_overlay_path)
        """
        import subprocess as _sp

        logger.info("SAM3-only mode: using prompt as text target → '%s'", prompt)

        # --- Build output path ---
        output_path, temp_render_dir = self._build_output_path(
            effective_video_path=effective_video_path,
            save_output=save_output,
            output_path=output_path,
            preview_mode=preview_mode,
        )

        # --- Parse point prompts (from the JS point selector) ---
        point_coords = None
        point_labels = None
        point_src_w = 0
        point_src_h = 0
        if mask_points and mask_points.strip():
            import json as _json
            try:
                pt_data = _json.loads(mask_points)
                if isinstance(pt_data, dict):
                    point_coords = pt_data.get("points")
                    point_labels = pt_data.get("labels")
                    point_src_w = int(pt_data.get("image_width", 0))
                    point_src_h = int(pt_data.get("image_height", 0))
                    if point_coords and point_labels:
                        logger.info("SAM3-only: using %d point prompt(s) (src %dx%d)",
                                    len(point_coords), point_src_w, point_src_h)
            except (ValueError, TypeError) as exc:
                logger.warning("SAM3-only: failed to parse mask_points JSON: %s", exc)

        # --- Run SAM3 directly (no auto_mask handler, no effects) ---
        try:
            from ..core.sam3_masker import mask_video_subprocess as sam3_mask_video
        except ImportError:
            from core.sam3_masker import mask_video_subprocess as sam3_mask_video

        try:
            mask_video_path = sam3_mask_video(
                video_path=effective_video_path,
                prompt=prompt,
                device=sam3_device,
                max_objects=sam3_max_objects,
                det_threshold=sam3_det_threshold,
                points=point_coords,
                labels=point_labels,
                point_src_width=point_src_w,
                point_src_height=point_src_h,
            )
        except Exception as e:
            logger.error("SAM3-only: mask generation failed: %s", e)
            raise RuntimeError(f"SAM3 mask generation failed: {e}") from e

        # --- Copy source video through as the main output (no effects) ---
        crf_map = {"draft": 28, "standard": 23, "high": 18, "lossless": 0}
        preset_map = {"draft": "ultrafast", "standard": "medium", "high": "slow", "lossless": "veryslow"}
        effective_crf = crf if crf >= 0 else crf_map.get(quality_preset, 23)
        effective_preset = encoding_preset if encoding_preset != "auto" else preset_map.get(quality_preset, "medium")

        ffmpeg_cmd = [
            "ffmpeg", "-y",
            "-i", effective_video_path,
            "-c:v", "libx264",
            "-crf", str(effective_crf),
            "-preset", effective_preset,
            "-pix_fmt", "yuv420p",
            "-c:a", "copy",
            output_path,
        ]

        if preview_mode:
            # Insert scale + duration limit before output path
            ffmpeg_cmd = [
                "ffmpeg", "-y",
                "-i", effective_video_path,
                "-vf", "scale=480:trunc(ow/a/2)*2",
                "-t", "10",
                "-c:v", "libx264",
                "-crf", str(effective_crf),
                "-preset", effective_preset,
                "-pix_fmt", "yuv420p",
                "-c:a", "copy",
                output_path,
            ]

        logger.debug("SAM3-only passthrough command: %s", " ".join(ffmpeg_cmd))
        proc = _sp.run(ffmpeg_cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(
                f"SAM3-only mode: video passthrough failed:\n{proc.stderr[-500:]}"
            )

        # --- Collect frame/audio output ---
        unique_id = str(kwargs.get("unique_id", ""))
        hidden_prompt = kwargs.get("hidden_prompt") or {}
        images_tensor, audio_out = self._collect_frame_output(
            output_path=output_path,
            unique_id=unique_id,
            hidden_prompt=hidden_prompt,
            removes_audio=False,
        )

        # --- Generate mask overlay ---
        mask_overlay_path = ""
        if mask_video_path and os.path.isfile(mask_video_path):
            mask_type = kwargs.get("mask_output_type", "colored_overlay")
            if mask_type == "black_white":
                mask_overlay_path = mask_video_path
                logger.info("SAM3-only: B&W mask video → %s", mask_overlay_path)
            else:
                try:
                    from ..core.sam3_masker import generate_mask_overlay
                    mask_overlay_path = generate_mask_overlay(
                        video_path=effective_video_path,
                        mask_video_path=mask_video_path,
                    )
                    logger.info("SAM3-only: colored overlay → %s", mask_overlay_path)
                except Exception as e:
                    logger.warning("SAM3-only: mask overlay generation failed: %s", e)

        # --- Build analysis string ---
        cmd_log = " ".join(ffmpeg_cmd)
        analysis = (
            f"SAM3-Only Mode (no LLM)\n"
            f"Text target: {prompt}\n"
            f"Device: {sam3_device}\n"
            f"Max objects: {sam3_max_objects}\n"
            f"Detection threshold: {sam3_det_threshold}\n"
            f"Point prompts: {'yes' if mask_points else 'no'}\n\n"
            f"Main output: clean passthrough (no effects)\n"
            f"Mask output: {mask_overlay_path or mask_video_path or 'none'}"
        )

        # --- Cleanup temp files ---
        for tmp_path in [temp_video_from_images, temp_video_with_audio]:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
        if not save_output and temp_render_dir and os.path.isdir(temp_render_dir):
            if not os.listdir(temp_render_dir):
                shutil.rmtree(temp_render_dir, ignore_errors=True)

        return (images_tensor, audio_out, output_path, cmd_log, analysis, mask_overlay_path)

    # ------------------------------------------------------------------ #
    #  Whisper-only mode (no LLM)                                         #
    # ------------------------------------------------------------------ #

    async def _process_whisper_only(
        self,
        mode: str,
        effective_video_path: str,
        video_metadata,
        save_output: bool,
        output_path: str,
        preview_mode: bool,
        quality_preset: str,
        crf: int,
        encoding_preset: str,
        whisper_device: str = "cpu",
        whisper_model: str = "large-v3",
        temp_video_from_images: Optional[str] = None,
        temp_video_with_audio: Optional[str] = None,
        **kwargs,
    ) -> tuple[torch.Tensor, dict, str, str, str, str]:
        """Run Whisper transcription directly without any LLM involvement.

        Transcribes the video audio using Whisper and burns subtitles
        (SRT or karaoke ASS) into the output video.  The full transcription
        text is included in the ``analysis`` return field.

        Args:
            mode: "transcribe" for SRT subtitles, "karaoke_subtitles" for
                  word-by-word karaoke ASS subtitles.

        Returns the standard 6-tuple:
            (images_tensor, audio, output_path, command_log, analysis, mask_overlay_path)
        """
        import atexit
        import subprocess as _sp
        import tempfile

        try:
            from ..core.whisper_transcriber import (
                transcribe_audio,
                segments_to_srt,
                words_to_karaoke_ass,
            )
        except ImportError:
            from core.whisper_transcriber import (
                transcribe_audio,
                segments_to_srt,
                words_to_karaoke_ass,
            )

        logger.info(
            "Whisper-only mode (%s): device=%s, model=%s",
            mode, whisper_device, whisper_model,
        )

        # --- Build output path ---
        output_path, temp_render_dir = self._build_output_path(
            effective_video_path=effective_video_path,
            save_output=save_output,
            output_path=output_path,
            preview_mode=preview_mode,
        )

        # --- Transcribe ---
        result = transcribe_audio(
            effective_video_path,
            model_size=whisper_model,
            device=whisper_device,
        )

        # --- Generate subtitle file ---
        if mode == "karaoke_subtitles":
            if not result.words:
                logger.warning("Whisper found no words — producing clean passthrough")
                sub_filter = None
            else:
                ass_content = words_to_karaoke_ass(result.words)
                tmp = tempfile.NamedTemporaryFile(
                    mode="w", suffix=".ass", delete=False, encoding="utf-8",
                )
                tmp.write(ass_content)
                tmp.close()
                atexit.register(os.unlink, tmp.name)

                from ..core.sanitize import ffmpeg_escape_path
                escaped_path = ffmpeg_escape_path(tmp.name)
                sub_filter = f"ass={escaped_path}"
        else:
            # mode == "transcribe"
            if not result.segments:
                logger.warning("Whisper found no speech — producing clean passthrough")
                sub_filter = None
            else:
                srt_content = segments_to_srt(result.segments)
                tmp = tempfile.NamedTemporaryFile(
                    mode="w", suffix=".srt", delete=False, encoding="utf-8",
                )
                tmp.write(srt_content)
                tmp.close()
                atexit.register(os.unlink, tmp.name)

                from ..core.sanitize import ffmpeg_escape_path
                escaped_path = ffmpeg_escape_path(tmp.name)
                sub_filter = f"subtitles={escaped_path}"

        # --- Build ffmpeg command ---
        crf_map = {"draft": 28, "standard": 23, "high": 18, "lossless": 0}
        preset_map = {"draft": "ultrafast", "standard": "medium", "high": "slow", "lossless": "veryslow"}
        effective_crf = crf if crf >= 0 else crf_map.get(quality_preset, 23)
        effective_preset = encoding_preset if encoding_preset != "auto" else preset_map.get(quality_preset, "medium")

        ffmpeg_cmd = ["ffmpeg", "-y", "-i", effective_video_path]

        if sub_filter:
            ffmpeg_cmd.extend(["-vf", sub_filter])

        ffmpeg_cmd.extend([
            "-c:v", "libx264",
            "-crf", str(effective_crf),
            "-preset", effective_preset,
            "-pix_fmt", "yuv420p",
            "-c:a", "copy",
        ])

        if preview_mode:
            # Insert scale + duration limit
            if sub_filter:
                # Append scale to existing vf
                vf_idx = ffmpeg_cmd.index("-vf")
                ffmpeg_cmd[vf_idx + 1] += ",scale=480:trunc(ow/a/2)*2"
            else:
                ffmpeg_cmd.extend(["-vf", "scale=480:trunc(ow/a/2)*2"])
            ffmpeg_cmd.extend(["-t", "10"])

        ffmpeg_cmd.append(output_path)

        logger.debug("Whisper-only command: %s", " ".join(ffmpeg_cmd))
        proc = _sp.run(ffmpeg_cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(
                f"Whisper-only mode: ffmpeg failed:\n{proc.stderr[-500:]}"
            )

        # --- Collect frame/audio output ---
        unique_id = str(kwargs.get("unique_id", ""))
        hidden_prompt = kwargs.get("hidden_prompt") or {}
        images_tensor, audio_out = self._collect_frame_output(
            output_path=output_path,
            unique_id=unique_id,
            hidden_prompt=hidden_prompt,
            removes_audio=False,
        )

        # --- Build analysis string (includes full transcription) ---
        cmd_log = " ".join(ffmpeg_cmd)
        mode_label = "Karaoke Subtitles" if mode == "karaoke_subtitles" else "SRT Subtitles"
        analysis = (
            f"Whisper-Only Mode (no LLM)\n"
            f"Mode: {mode_label}\n"
            f"Model: {whisper_model}\n"
            f"Device: {whisper_device}\n"
            f"Language: {result.language or 'auto-detected'}\n"
            f"Segments: {len(result.segments)}\n"
            f"Words: {len(result.words)}\n\n"
            f"--- Transcription ---\n"
            f"{result.full_text or '(no speech detected)'}"
        )

        # --- Cleanup temp files ---
        for tmp_path in [temp_video_from_images, temp_video_with_audio]:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
        if not save_output and temp_render_dir and os.path.isdir(temp_render_dir):
            if not os.listdir(temp_render_dir):
                shutil.rmtree(temp_render_dir, ignore_errors=True)

        return (images_tensor, audio_out, output_path, cmd_log, analysis, "")

    async def _verify_output(
        self,
        connector,
        output_path: str,
        prompt: str,
        pipeline,
        effective_video_path: str,
        use_vision: bool,
    ) -> Optional[tuple]:
        """Run output verification via LLM and optionally correct the pipeline.

        Returns:
            A tuple of (result, pipeline, command) if a correction was applied,
            or None if the original output is fine (PASS or unparseable).
        """
        from ..mcp.tools import extract_frames as _extract_frames
        from ..mcp.tools import analyze_colors as _analyze_colors
        from ..mcp.tools import cleanup_vision_frames as _cleanup_frames
        from ..mcp.vision import frames_to_base64 as _frames_to_b64
        from ..mcp.vision import frames_to_base64_raw_strings as _frames_to_b64_raw
        from ..mcp.vision import generate_audio_visualization as _gen_audio_viz
        from ..prompts.system import get_verification_prompt
        from ..skills.composer import Pipeline
        from ..core.llm.ollama import OllamaConnector as _OllamaConnector

        # Extract 3 frames from output — fewer to save tokens for audio viz
        verify_frames = _extract_frames(
            video_path=output_path,
            start=2.0,
            duration=9999,  # full video
            fps=0.5,
            max_frames=3,
        )
        verify_run_id = verify_frames.get("run_id")

        # --- Audio visualization (only for pipelines with audio skills) ---
        _AUDIO_SKILLS = {
            "normalize", "fade_audio", "replace_audio", "bass", "treble",
            "echo", "noise_reduction", "volume", "audio_bitrate",
            "compress_audio", "lowpass", "highpass", "remove_audio",
            "loudnorm", "audio_speed", "reverb",
        }
        has_audio_skills = any(
            s.skill_name in _AUDIO_SKILLS for s in pipeline.steps
        )
        audio_viz = None
        audio_viz_folder = None
        if has_audio_skills:
            try:
                audio_viz = _gen_audio_viz(output_path)
                audio_viz_folder = audio_viz.get("folder")
            except Exception as e:
                logger.warning(f"Audio visualization failed: {e}")

        try:
            # Build output analysis data
            if use_vision and verify_frames.get("paths"):
                b64_data = _frames_to_b64(verify_frames["paths"], max_size=256)
                output_data = (
                    f"Extracted {len(verify_frames['paths'])} frames from output.\n"
                    f"[Vision frames are embedded in this message]"
                )

                # Add audio visualization images if available
                if audio_viz:
                    audio_image_paths = []
                    if audio_viz.get("waveform_path"):
                        audio_image_paths.append(audio_viz["waveform_path"])
                    if audio_viz.get("spectrogram_path"):
                        audio_image_paths.append(audio_viz["spectrogram_path"])
                    if audio_image_paths:
                        audio_b64 = _frames_to_b64(audio_image_paths, max_size=256)
                        b64_data.extend(audio_b64)

                    # Add audio metrics as text
                    metrics = audio_viz.get("audio_metrics", {})
                    if metrics.get("has_audio"):
                        import json as _json
                        output_data += (
                            f"\n\n## Audio Analysis\n"
                            f"[Waveform and spectrogram images are embedded — "
                            f"the waveform shows amplitude over time (fades visible "
                            f"as tapered ends, silence as flat lines), the spectrogram "
                            f"shows frequency content (bass=bottom, treble=top)]\n"
                            f"{_json.dumps(metrics, indent=2)}"
                        )
                    elif not metrics.get("has_audio"):
                        output_data += (
                            "\n\n## Audio Analysis\n"
                            "No audio stream found in output."
                        )
            else:
                color_data = _analyze_colors(video_path=output_path)
                import json as _json
                output_data = (
                    f"Color analysis of output:\n"
                    f"{_json.dumps(color_data, indent=2)}"
                )
                b64_data = None

                # Add audio metrics as text even without vision
                if audio_viz:
                    metrics = audio_viz.get("audio_metrics", {})
                    if metrics:
                        output_data += (
                            f"\n\nAudio analysis:\n"
                            f"{_json.dumps(metrics, indent=2)}"
                        )

            # Build pipeline summary
            pipeline_summary = self.composer.explain_pipeline(pipeline)

            # Build verification prompt
            verify_prompt = get_verification_prompt(
                prompt=prompt,
                pipeline_summary=pipeline_summary,
                output_data=output_data,
            )

            # Send to LLM — use chat_with_tools for vision (multimodal),
            # or generate() for text-only
            if b64_data:
                _is_ollama = isinstance(connector, _OllamaConnector)
                if _is_ollama:
                    # Ollama requires raw base64 strings in an 'images'
                    # field — NOT OpenAI-style multimodal content blocks.
                    raw_b64 = _frames_to_b64_raw(
                        verify_frames["paths"], max_size=256
                    )
                    # Add audio viz frames if available
                    if audio_viz:
                        audio_paths = []
                        if audio_viz.get("waveform_path"):
                            audio_paths.append(audio_viz["waveform_path"])
                        if audio_viz.get("spectrogram_path"):
                            audio_paths.append(audio_viz["spectrogram_path"])
                        if audio_paths:
                            raw_b64.extend(_frames_to_b64_raw(
                                audio_paths, max_size=256
                            ))
                    verify_msg = {
                        "role": "user",
                        "content": verify_prompt,
                        "images": raw_b64,
                    }
                    verify_messages = [verify_msg]
                    logger.info(
                        "Verification: sending %d images via Ollama "
                        "native format", len(raw_b64),
                    )
                else:
                    content_parts = [{"type": "text", "text": verify_prompt}]
                    for img_block in b64_data:
                        content_parts.append(img_block)
                    verify_messages = [
                        {"role": "user", "content": content_parts}
                    ]
                verify_response = await connector.chat_with_tools(
                    verify_messages, tools=[],
                )
            else:
                verify_response = await connector.generate(
                    verify_prompt,
                    system_prompt="You are a video and audio quality reviewer.",
                )

            verify_text = (verify_response.content or "").strip()
            logger.info(f"Verification result: {verify_text}")

            if verify_text.upper() == "PASS":
                logger.info("Output verification: PASS — output looks good")
                return None

            # Try to parse corrected pipeline — strip markdown fences first
            cleaned = verify_text
            # Remove ```json ... ``` or ``` ... ``` fencing
            import re as _re
            fence_match = _re.search(
                r'```(?:json)?\s*(\{.*\})\s*```', cleaned, _re.DOTALL
            )
            if fence_match:
                cleaned = fence_match.group(1).strip()

            corrected = None
            try:
                corrected = json.loads(cleaned)
            except (json.JSONDecodeError, ValueError):
                # Fall back to the general extractor
                corrected = self.pipeline_generator.parse_response(verify_text)

            if corrected and corrected.get("pipeline"):
                logger.warning(
                    "Output verification: NEEDS CORRECTION — "
                    "re-executing with corrected pipeline"
                )
                # Rebuild and re-execute
                fix_pipeline = Pipeline(
                    input_path=effective_video_path,
                    output_path=output_path,
                    extra_inputs=pipeline.extra_inputs,
                    metadata=pipeline.metadata,
                )
                for step in corrected.get("pipeline", []):
                    skill_name = step.get("skill")
                    params = step.get("params", {})
                    if skill_name:
                        fix_pipeline.add_step(skill_name, params)
                fix_command = self.composer.compose(fix_pipeline)
                fix_result = self.process_manager.execute(
                    fix_command, timeout=600
                )
                if fix_result.success:
                    logger.info(
                        "Verification fix succeeded — using corrected output"
                    )
                    logger.info(
                        "Corrected command: %s", fix_command.to_string()
                    )
                    logger.info(
                        "Corrected pipeline:\n%s",
                        self.composer.explain_pipeline(fix_pipeline),
                    )
                    return (fix_result, fix_pipeline, fix_command)
                else:
                    logger.warning(
                        f"Verification fix failed: {fix_result.error_message} "
                        "— keeping original output"
                    )
                    return None
            else:
                logger.info(
                    "Verification response was not PASS or valid JSON "
                    "— keeping original output"
                )
                if corrected:
                    logger.debug(
                        f"Parsed verification response (no pipeline key): "
                        f"{corrected}"
                    )
                else:
                    logger.debug(
                        f"Could not parse verification response: "
                        f"{verify_text[:500]}"
                    )
                return None
        finally:
            # Cleanup verification frames
            if verify_run_id:
                try:
                    _cleanup_frames(verify_run_id)
                except Exception:
                    pass
            # Cleanup audio visualization files
            if audio_viz_folder:
                try:
                    import shutil
                    shutil.rmtree(audio_viz_folder, ignore_errors=True)
                except Exception:
                    pass

    @staticmethod
    def _audio_dict_to_wav(audio: dict) -> Optional[str]:
        """Convert a ComfyUI AUDIO dict to a temporary WAV file.

        Args:
            audio: ComfyUI AUDIO dict with 'waveform' and 'sample_rate'.

        Returns:
            Path to the created temporary WAV file, or None on failure.
        """
        import subprocess

        try:
            waveform = audio["waveform"]       # (1, channels, samples)
            sample_rate = audio["sample_rate"]
        except (KeyError, TypeError):
            return None

        channels = waveform.size(1)
        audio_data = waveform.squeeze(0).transpose(0, 1).contiguous()  # (samples, channels)
        audio_bytes = (audio_data * 32767.0).clamp(-32768, 32767).to(torch.int16).numpy().tobytes()

        tmp_wav = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tmp_wav.close()

        ffmpeg_bin = shutil.which("ffmpeg")
        if not ffmpeg_bin:
            return None

        result = subprocess.run(
            [
                ffmpeg_bin, "-y",
                "-f", "s16le",
                "-ar", str(sample_rate),
                "-ac", str(channels),
                "-i", "-",
                tmp_wav.name,
            ],
            input=audio_bytes,
            capture_output=True,
        )
        if result.returncode != 0:
            if os.path.exists(tmp_wav.name):
                os.remove(tmp_wav.name)
            return None

        return tmp_wav.name

    @staticmethod
    def _probe_duration(video_path: str) -> float:
        """Probe the duration of a video file using ffprobe.

        Returns:
            Duration in seconds, or 0.0 if probing fails.
        """
        import subprocess
        ffprobe_bin = shutil.which("ffprobe")
        if not ffprobe_bin:
            return 0.0
        try:
            valid_path = validate_video_path(str(video_path))
            result = subprocess.run(
                [ffprobe_bin, "-v", "error", "-show_entries",
                 "format=duration", "-of", "default=noprint_wrappers=1:nokey=1",
                 valid_path],
                capture_output=True, text=True, check=True,
            )
            return float(result.stdout.strip())
        except Exception:
            return 0.0

    @staticmethod
    def _extract_thumbnail_frame(video_path: str) -> torch.Tensor:
        """Extract only the first frame from a video as a (1, H, W, 3) tensor.

        This is vastly cheaper than loading all frames (~6 MB vs ~13 GB for
        a typical 74s 1080p video).  The single frame is used for:
         - The IMAGE output (thumbnail preview)
         - The workflow PNG embed
        """
        try:
            import av  # type: ignore[import-not-found]
            container = av.open(video_path)
            for frame in container.decode(video=0):
                arr = frame.to_ndarray(format="rgb24")
                container.close()
                return (
                    torch.from_numpy(arr)
                    .float()
                    .div_(255.0)
                    .unsqueeze(0)  # (H,W,3) → (1,H,W,3)
                )
            container.close()
        except Exception:
            pass
        return torch.zeros(1, 64, 64, 3, dtype=torch.float32)

    @staticmethod
    def _save_workflow_png(
        first_frame: torch.Tensor,
        png_path: str,
        prompt: Optional[dict],
        extra_pnginfo: Optional[dict],
        extra_info: Optional[dict] = None,
    ) -> None:
        """Save a first-frame PNG with embedded ComfyUI workflow metadata.

        This allows the PNG to be dragged into ComfyUI to reload the
        workflow, matching the behavior of ComfyUI's SaveImage node.
        """
        from PIL import Image  # type: ignore[import-untyped]
        from PIL.PngImagePlugin import PngInfo
        import numpy as np

        # Convert tensor (H, W, C) float [0,1] -> uint8 PIL Image
        frame_np = (255.0 * first_frame.cpu().numpy()).clip(0, 255).astype(np.uint8)
        img = Image.fromarray(frame_np)

        metadata = PngInfo()
        if prompt is not None:
            metadata.add_text("prompt", json.dumps(prompt))
        if extra_pnginfo is not None:
            for key in extra_pnginfo:
                metadata.add_text(key, json.dumps(extra_pnginfo[key]))
        if extra_info is not None:
            for key, value in extra_info.items():
                metadata.add_text(key, value if isinstance(value, str) else json.dumps(value))

        img.save(png_path, pnginfo=metadata, compress_level=4)

    @staticmethod
    def _strip_api_key_from_metadata(
        api_key: str,
        prompt: Optional[dict],
        extra_pnginfo: Optional[dict],
    ) -> None:
        """Remove api_key values from workflow metadata in-place.

        This prevents API keys from being embedded in output files
        when downstream Save Image/Video nodes serialize the workflow.
        """
        # Strip from the prompt graph (api format — keyed by node id)
        if prompt:
            for node_id, node_data in prompt.items():
                inputs = node_data.get("inputs", {})
                if "api_key" in inputs:
                    inputs["api_key"] = ""

        # Strip from the workflow JSON (drag-drop format)
        if extra_pnginfo and "workflow" in extra_pnginfo:
            workflow = extra_pnginfo["workflow"]
            for node in workflow.get("nodes", []):
                # widgets_values is a positional array — scan for the
                # actual key value and replace it
                widgets = node.get("widgets_values", [])
                if isinstance(widgets, list):
                    for i, val in enumerate(widgets):
                        if val == api_key:
                            widgets[i] = ""

    async def _process_batch(
        self,
        video_folder: str,
        file_pattern: str,
        prompt: str,
        llm_model: str,
        quality_preset: str,
        ollama_url: str,
        api_key: str,
        custom_model: str,
        crf: int,
        encoding_preset: str,
        max_concurrent: int,
        save_output: bool,
        output_path: str,
        use_vision: bool = True,
        verify_output: bool = False,
        ptc_mode: str = "off",
        sam3_max_objects: int = 5,
        sam3_det_threshold: float = 0.7,
        mask_points: str = "",
        pipeline_json: str = "",
    ) -> tuple[torch.Tensor, dict, str, str, str, str]:
        """Process all matching videos in a folder with the same pipeline.

        Uses one LLM call to generate the pipeline, then applies it to
        every video concurrently via ThreadPoolExecutor.
        """
        import glob
        from concurrent.futures import ThreadPoolExecutor, as_completed
        from ..skills.composer import Pipeline
        from ..core.sanitize import validate_video_path as _validate, validate_output_path as _validate_out

        # --- Validate folder ---
        folder = Path(video_folder)
        if not folder.exists() or not folder.is_dir():
            raise ValueError(f"Batch mode: video_folder not found or not a directory: {video_folder}")

        if not prompt.strip():
            raise ValueError("Prompt cannot be empty")

        # --- Discover videos ---
        patterns = file_pattern.split()
        video_files = []
        for pat in patterns:
            video_files.extend(glob.glob(str(folder / pat)))
        video_files = sorted(set(video_files))

        valid_files = []
        for vf in video_files:
            try:
                _validate(vf)
                valid_files.append(vf)
            except ValueError:
                pass

        if not valid_files:
            raise ValueError(
                f"Batch mode: no valid video files matching '{file_pattern}' in {video_folder}"
            )

        # --- Output folder ---
        if save_output and output_path:
            out_dir = Path(_validate_out(output_path))
        elif save_output:
            out_dir = Path(folder_paths.get_output_directory()) / "ffmpega_batch"
        else:
            out_dir = Path(tempfile.mkdtemp(prefix="ffmpega_batch_"))
        out_dir.mkdir(parents=True, exist_ok=True)

        # --- Generate pipeline via LLM (once from sample) ---
        sample_video = valid_files[0]
        video_metadata = self.analyzer.analyze(sample_video)
        metadata_str = video_metadata.to_analysis_string()

        if not ollama_url or not ollama_url.startswith(("http://", "https://")):
            ollama_url = "http://localhost:11434"
        effective_model = llm_model
        if llm_model == "custom":
            if not custom_model or not custom_model.strip():
                raise ValueError(
                    "Please enter a model name in the 'custom_model' field "
                    "when using 'custom' mode."
                )
            effective_model = custom_model.strip()

        connected_inputs_str = f"Batch mode: {len(valid_files)} videos in {video_folder}"
        connector = self.pipeline_generator.create_connector(effective_model, ollama_url, api_key)
        try:
            spec = await self.pipeline_generator.generate(
                connector, prompt, metadata_str,
                connected_inputs=connected_inputs_str,
                video_path=valid_files[0] if valid_files else "",
                use_vision=use_vision,
                ptc_mode=ptc_mode,
            )
        finally:
            if hasattr(connector, 'close'):
                await connector.close()

        pipeline_steps = spec.get("pipeline", [])
        interpretation = spec.get("interpretation", "")

        # --- Quality preset ---
        crf_map = {"draft": 28, "standard": 23, "high": 18, "lossless": 0}
        preset_map = {"draft": "ultrafast", "standard": "medium", "high": "slow", "lossless": "veryslow"}
        effective_crf = crf if crf >= 0 else crf_map.get(quality_preset, 23)
        effective_preset = encoding_preset if encoding_preset != "auto" else preset_map.get(quality_preset, "medium")

        # --- Process each video ---
        output_paths = []
        errors = []
        command_logs = []

        def process_single(vpath: str) -> tuple[str, str | None, str]:
            """Process one video file."""
            try:
                stem = Path(vpath).stem
                out_file = str(out_dir / f"{stem}_edited.mp4")

                pipeline = Pipeline(input_path=vpath, output_path=out_file)
                pipeline.metadata["_sam3_max_objects"] = sam3_max_objects
                pipeline.metadata["_sam3_det_threshold"] = sam3_det_threshold
                if mask_points and mask_points.strip():
                    pipeline.metadata["_mask_points"] = mask_points.strip()
                for step in pipeline_steps:
                    skill_name = step.get("skill")
                    params = step.get("params", {})
                    if skill_name:
                        pipeline.add_step(skill_name, params)

                pipeline.add_step("quality", {
                    "crf": effective_crf,
                    "preset": effective_preset,
                })

                command = self.composer.compose(pipeline)
                result = self.process_manager.execute(command, timeout=600)

                if result.success:
                    return (out_file, None, command.to_string())
                else:
                    return (out_file, result.error_message, command.to_string())
            except Exception as e:
                return (vpath, str(e), "")

        with ThreadPoolExecutor(max_workers=max_concurrent) as executor:
            futures = {
                executor.submit(process_single, vf): vf
                for vf in valid_files
            }
            for future in as_completed(futures):
                vf = futures[future]
                try:
                    out_file, error, cmd_log = future.result()
                    if error:
                        errors.append(f"{Path(vf).name}: {error}")
                    else:
                        output_paths.append(out_file)
                    if cmd_log:
                        command_logs.append(f"[{Path(vf).name}] {cmd_log}")
                except Exception as e:
                    errors.append(f"{Path(vf).name}: {str(e)}")

        # --- Build results ---
        processed = len(output_paths)
        failed = len(errors)
        total = len(valid_files)

        # Return the last successful video as frames, or a placeholder
        last_path = output_paths[-1] if output_paths else valid_files[0]
        frames_tensor = self.media_converter.frames_to_tensor(last_path)
        audio_dict = self.media_converter.extract_audio(last_path)

        import json
        paths_json = json.dumps(output_paths, indent=2)

        # Per-file status table
        status_lines = [
            f"Batch complete: {processed}/{total} succeeded, {failed} failed.",
            f"Output folder: {out_dir}",
            "",
            "File results:",
        ]
        # Map each source filename stem -> actual output path for reporting
        _stem_to_out: dict[str, str] = {Path(p).stem.replace("_edited", ""): p
                                         for p in output_paths}
        for vf in valid_files:
            stem = Path(vf).stem
            actual_out = _stem_to_out.get(stem)
            if actual_out is not None:
                # Successful — show output size if available
                try:
                    size_kb = Path(actual_out).stat().st_size // 1024
                    status_lines.append(f"  ✓ {Path(vf).name} → {Path(actual_out).name} ({size_kb:,} KB)")
                except OSError:
                    status_lines.append(f"  ✓ {Path(vf).name} → {Path(actual_out).name}")
            else:
                # Find the error message for this file (default if no match)
                err_msg = next(
                    ((e.split(": ", 1)[1] if ": " in e else e)
                     for e in errors
                     if e.startswith(Path(vf).name)),
                    "unknown error",
                )
                status_lines.append(f"  ✗ {Path(vf).name}: {err_msg}")

        analysis = (
            f"Batch Mode — {interpretation}\n\n"
            + "\n".join(status_lines)
        )

        command_log = "\n\n".join(command_logs) if command_logs else "No commands executed"

        # --- Cleanup batch temp directory ---
        if not save_output and out_dir and out_dir.exists():
            try:
                shutil.rmtree(str(out_dir), ignore_errors=True)
            except OSError:
                pass

        return (frames_tensor, audio_dict, paths_json, command_log, analysis, "")

    @classmethod
    def IS_CHANGED(cls, video_path, prompt, seed=0, **kwargs):
        """Determine if the node needs to re-execute."""
        return f"{video_path}:{prompt}:{seed}"
