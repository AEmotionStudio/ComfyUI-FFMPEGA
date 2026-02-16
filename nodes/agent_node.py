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
    API_MODELS = [
        "gpt-5.2",
        "gpt-5-mini",
        "gpt-4.1",
        "claude-sonnet-4-6",
        "claude-haiku-4-5",
        "gemini-3-flash",
        "gemini-2.5-flash",
        "qwen-max",
        "qwen-plus",
        "qwen-turbo",
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
        all_models = ollama_models + cls.API_MODELS + ["custom"]

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
                "video_path": ("STRING", {
                    "default": "",
                    "multiline": False,
                    "placeholder": "Path to input video file",
                    "tooltip": "Absolute path to the source video file. Used as the ffmpeg input unless images are connected.",
                }),
                "prompt": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "placeholder": "Describe how you want to edit the video...",
                    "tooltip": "Natural language instruction describing the desired edit. Examples: 'Add a cinematic letterbox', 'Speed up 2x', 'Apply a vintage VHS look'.",
                }),
                "llm_model": (all_models, {
                    "default": all_models[0],
                    "tooltip": "AI model used to interpret your prompt. Local Ollama models appear first, followed by cloud API models (require api_key).",
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
                "preview_mode": ("BOOLEAN", {
                    "default": False,
                    "label_on": "Preview",
                    "label_off": "Full Render",
                    "tooltip": "When enabled, generates a quick low-res preview (480p, first 10 seconds) instead of a full render.",
                }),
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
                "track_tokens": ("BOOLEAN", {
                    "default": False,
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
            },
            "hidden": {
                "hidden_prompt": "PROMPT",
                "extra_pnginfo": "EXTRA_PNGINFO",
            },
        }

    RETURN_TYPES = ("IMAGE", "AUDIO", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("images", "audio", "video_path", "command_log", "analysis")
    OUTPUT_TOOLTIPS = (
        "All frames from the output video as a batched image tensor.",
        "Audio extracted from the output video (or passed through from audio_a) in ComfyUI AUDIO format.",
        "Absolute path to the rendered output video file.",
        "The ffmpeg command that was executed.",
        "LLM interpretation, estimated changes, pipeline steps, and any warnings.",
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

    async def process(
        self,
        video_path: str,
        prompt: str,
        llm_model: str,
        quality_preset: str,
        seed: int = 0,
        images_a: Optional[torch.Tensor] = None,
        image_a: Optional[torch.Tensor] = None,
        audio_a: Optional[dict] = None,
        video_a: str = "",
        image_path_a: str = "",
        preview_mode: bool = False,
        save_output: bool = False,
        output_path: str = "",
        ollama_url: str = "http://localhost:11434",
        api_key: str = "",
        custom_model: str = "",
        crf: int = -1,
        encoding_preset: str = "auto",
        use_vision: bool = True,
        verify_output: bool = True,
        batch_mode: bool = False,
        video_folder: str = "",
        file_pattern: str = "*.mp4",
        max_concurrent: int = 4,
        track_tokens: bool = False,
        log_usage: bool = False,
        **kwargs,  # hidden: prompt (PROMPT dict), extra_pnginfo (EXTRA_PNGINFO)
    ) -> tuple[torch.Tensor, dict, str, str, str]:
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

        # --- Batch mode: process all matching videos in a folder ---
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
            )

        # --- Resolve input video ---
        temp_video_from_images = None
        temp_video_with_audio = None
        # Collect all video_* path inputs (video_a, video_b, video_c, ...)
        _all_video_paths = []
        if video_a and video_a.strip() and os.path.isfile(video_a.strip()):
            _all_video_paths.append(video_a.strip())
        for k in sorted(kwargs):
            if k.startswith("video_") and k not in ("video_folder", "video_path") and kwargs[k]:
                vp = str(kwargs[k]).strip()
                if vp and os.path.isfile(vp):
                    _all_video_paths.append(vp)
        has_extra_video_paths = len(_all_video_paths) > 0

        # Collect all image_path_* inputs (image_path_a, image_path_b, ...)
        _all_image_paths = []
        if image_path_a and image_path_a.strip() and os.path.isfile(image_path_a.strip()):
            _all_image_paths.append(image_path_a.strip())
        for k in sorted(kwargs):
            if k.startswith("image_path_") and kwargs[k]:
                ip = str(kwargs[k]).strip()
                if ip and os.path.isfile(ip):
                    _all_image_paths.append(ip)
        has_extra_image_paths = len(_all_image_paths) > 0

        has_extra_images = (
            image_a is not None
            or any(k.startswith("image_") and not k.startswith("image_path_") and kwargs.get(k) is not None for k in kwargs)
            or has_extra_video_paths
            or has_extra_image_paths
        )
        if images_a is not None:
            _images_a_shape = images_a.shape  # Capture shape before release
            temp_video_from_images = self.media_converter.images_to_video(images_a)
            effective_video_path = temp_video_from_images
            # Release primary video tensor immediately — it's been encoded
            # to a temp file. For 8s@1080p this frees ~4.7GB.
            del images_a
            images_a = None  # Keep name in scope for later None checks
            import gc; gc.collect()
            try:
                import torch as _torch
                if _torch.cuda.is_available():
                    _torch.cuda.empty_cache()
            except Exception:
                pass
        elif video_path and video_path.strip():
            effective_video_path = video_path
        elif has_extra_images:
            # No main video but extra images are connected (slideshow/grid mode)
            # Generate a short dummy black video as a placeholder base input
            import tempfile as _tmpmod
            dummy = _tmpmod.NamedTemporaryFile(suffix=".mp4", delete=False)
            dummy.close()
            import subprocess
            subprocess.run(
                [
                    "ffmpeg", "-y", "-f", "lavfi", "-i",
                    "color=c=black:s=1920x1080:d=1:r=25",
                    "-c:v", "libx264", "-t", "1", dummy.name,
                ],
                capture_output=True,
            )
            temp_video_from_images = dummy.name  # track for cleanup
            effective_video_path = dummy.name
        else:
            effective_video_path = video_path

        # Validate input
        from ..core.sanitize import validate_video_path, validate_output_file_path  # type: ignore[import-not-found]
        effective_video_path = validate_video_path(effective_video_path)

        # Pre-mux audio_a into the input video so audio filters
        # (e.g. loudnorm, echo) have an audio stream to process.
        # Without this, images-only inputs have no audio track and
        # audio filters silently produce no output.
        if audio_a is not None and not self.media_converter.has_audio_stream(effective_video_path):
            import tempfile as _tmpmod
            tmp = _tmpmod.NamedTemporaryFile(suffix=".mp4", delete=False)
            tmp.close()
            import shutil as _shmod
            _shmod.copy2(effective_video_path, tmp.name)
            self.media_converter.mux_audio(tmp.name, audio_a)
            temp_video_with_audio = tmp.name
            effective_video_path = tmp.name

        if not prompt.strip():
            raise ValueError("Prompt cannot be empty")

        # --- Analyze input video ---
        video_metadata = self.analyzer.analyze(effective_video_path)
        metadata_str = video_metadata.to_analysis_string()

        # --- Build connected inputs summary for LLM context ---
        input_lines = []
        # Primary video
        if images_a is not None:
            dur = (
                video_metadata.primary_video.duration
                if video_metadata.primary_video and video_metadata.primary_video.duration
                else "unknown"
            )
            fps = (
                video_metadata.primary_video.frame_rate
                if video_metadata.primary_video and video_metadata.primary_video.frame_rate
                else "unknown"
            )
            input_lines.append(
                f"- images_a (video): connected — primary video input, "
                f"{images_a.shape[0]} frames, {dur}s, {fps}fps"
            )
        elif '_images_a_shape' in dir():
            # images_a was released after video conversion — use saved shape
            dur = (
                video_metadata.primary_video.duration
                if video_metadata.primary_video and video_metadata.primary_video.duration
                else "unknown"
            )
            fps = (
                video_metadata.primary_video.frame_rate
                if video_metadata.primary_video and video_metadata.primary_video.frame_rate
                else "unknown"
            )
            input_lines.append(
                f"- images_a (video): connected — primary video input, "
                f"{_images_a_shape[0]} frames, {dur}s, {fps}fps"
            )
        elif video_path and video_path.strip():
            input_lines.append(f"- video_path: connected — file input")

        # Extra video inputs (images_b, images_c, ...)
        for k in sorted(kwargs):
            if k.startswith("images_") and k != "images_a" and kwargs[k] is not None:
                tensor = kwargs[k]
                input_lines.append(
                    f"- {k} (video): connected — {tensor.shape[0]} frames"
                )

        # File-path video inputs (video_a, video_b, video_c, ...)
        for vi, vp in enumerate(_all_video_paths):
            letter = chr(ord('a') + vi)
            input_lines.append(
                f"- video_{letter} (video file): connected — {vp}"
            )

        # Audio inputs
        if audio_a is not None:
            sr = audio_a.get("sample_rate", "unknown")
            wf = audio_a.get("waveform")
            dur_str = "unknown"
            if wf is not None and sr and sr != "unknown":
                dur_str = f"{wf.shape[-1] / sr:.1f}s"
            input_lines.append(
                f"- audio_a: connected — {dur_str}, {sr}Hz"
            )
        for k in sorted(kwargs):
            if k.startswith("audio_") and k != "audio_a" and kwargs[k] is not None:
                ad = kwargs[k]
                sr = ad.get("sample_rate", "unknown")
                wf = ad.get("waveform")
                dur_str = "unknown"
                if wf is not None and sr and sr != "unknown":
                    dur_str = f"{wf.shape[-1] / sr:.1f}s"
                input_lines.append(
                    f"- {k}: connected — {dur_str}, {sr}Hz"
                )

        # Image inputs
        if image_a is not None:
            input_lines.append(
                f"- image_a: connected — single image "
                f"{image_a.shape[2]}x{image_a.shape[1]}"
            )
        for k in sorted(kwargs):
            if k.startswith("image_") and k != "image_a" and not k.startswith("images_") and not k.startswith("image_path_") and kwargs[k] is not None:
                img = kwargs[k]
                input_lines.append(
                    f"- {k}: connected — single image "
                    f"{img.shape[2]}x{img.shape[1]}"
                )

        # File-path image inputs (image_path_a, image_path_b, ...)
        for ii, ip in enumerate(_all_image_paths):
            letter = chr(ord('a') + ii)
            input_lines.append(
                f"- image_path_{letter} (image file): connected — {ip}"
            )

        connected_inputs_str = "\n".join(input_lines) if input_lines else "No extra inputs connected"

        # --- Generate pipeline via LLM ---
        if not ollama_url or not ollama_url.startswith(("http://", "https://")):
            ollama_url = "http://localhost:11434"
        # Resolve custom model name
        effective_model = llm_model
        if llm_model == "custom":
            if not custom_model or not custom_model.strip():
                raise ValueError(
                    "Please enter a model name in the 'custom_model' field "
                    "when using 'custom' mode."
                )
            effective_model = custom_model.strip()
        connector = self.pipeline_generator.create_connector(effective_model, ollama_url, api_key)
        try:
            spec = await self.pipeline_generator.generate(
                connector, prompt, metadata_str,
                connected_inputs=connected_inputs_str,
                video_path=effective_video_path,
                use_vision=use_vision,
            )
        except Exception as e:
            if hasattr(connector, 'close'):
                await connector.close()
            # Sanitize any API key from the error before propagating
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
        logger.debug("Connected inputs: %s", connected_inputs_str)

        # --- Build output path ---
        stem = Path(effective_video_path).stem
        suffix = "_preview" if preview_mode else "_edited"

        # Determine final output directory
        temp_render_dir = None
        if save_output:
            # Save to output folder (default behaviour)
            if not output_path:
                output_dir = folder_paths.get_output_directory()
                output_path = str(Path(output_dir) / f"{stem}{suffix}.mp4")
            elif Path(output_path).is_dir() or output_path.endswith(os.sep):
                output_dir = output_path.rstrip(os.sep)
                output_path = str(Path(output_dir) / f"{stem}{suffix}.mp4")
            elif not Path(output_path).suffix:
                os.makedirs(output_path, exist_ok=True)
                output_path = str(Path(output_path) / f"{stem}{suffix}.mp4")
            else:
                # User provided a specific file path
                output_path = validate_output_file_path(output_path)
        else:
            # Pass-through mode: render to temp dir so downstream nodes
            # handle the final save. The temp file is cleaned up later.
            temp_render_dir = tempfile.mkdtemp(prefix="ffmpega_")
            output_path = str(Path(temp_render_dir) / f"{stem}{suffix}.mp4")

        os.makedirs(Path(output_path).parent, exist_ok=True)

        # --- Build pipeline ---
        pipeline = Pipeline(
            input_path=effective_video_path,
            output_path=output_path,
        )
        # Store input FPS so concat can match it (avoids FPS mismatch
        # when external save nodes re-encode our frame tensors)
        input_fps = (
            video_metadata.primary_video.frame_rate
            if video_metadata.primary_video and video_metadata.primary_video.frame_rate
            else 24
        )
        pipeline.metadata["_input_fps"] = int(round(input_fps))
        # Store input video duration for xfade offset calculation
        input_duration = (
            video_metadata.primary_video.duration
            if video_metadata.primary_video and video_metadata.primary_video.duration
            else 0
        )
        if input_duration:
            pipeline.metadata["_video_duration"] = input_duration

        for step in pipeline_steps:
            skill_name = step.get("skill")
            params = step.get("params", {})
            if skill_name:
                pipeline.add_step(skill_name, params)

        # --- Detect format-changing skills and fix output extension ---
        # Skills like 'gif' or 'container' change the output format, but the
        # output path was set to .mp4 by default. Rewrite the extension so
        # ffmpeg uses the correct muxer.
        _FORMAT_SKILLS = {
            "gif": ".gif",
            "webm": ".webm",
        }
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

        # Add quality preset if not already specified.
        # Skip for formats incompatible with H.264 (GIF uses palettegen,
        # WebM uses VP9 — their handlers set their own encoding).
        _NO_QUALITY_PRESET_SKILLS = {"gif", "webm"}
        has_incompatible_format = any(
            s.skill_name in _NO_QUALITY_PRESET_SKILLS for s in pipeline.steps
        ) or (new_ext and new_ext in {".gif", ".webm"})
        if quality_preset and not has_incompatible_format and not any(
            s.skill_name in ["quality", "compress"] for s in pipeline.steps
        ):
            crf_map = {"draft": 28, "standard": 23, "high": 18, "lossless": 0}
            preset_map = {"draft": "ultrafast", "standard": "medium", "high": "slow", "lossless": "veryslow"}
            effective_crf = crf if crf >= 0 else crf_map.get(quality_preset, 23)
            effective_preset = encoding_preset if encoding_preset != "auto" else preset_map.get(quality_preset, "medium")
            pipeline.add_step("quality", {
                "crf": effective_crf,
                "preset": effective_preset,
            })

        # Validate pipeline (warn but don't block — LLMs are imprecise)
        is_valid, errors = self.composer.validate_pipeline(pipeline)
        if not is_valid:
            for err in errors:
                logger.warning(f"Pipeline validation: {err} (continuing anyway)")

        # --- replace_audio handling ---
        # When replace_audio is in the pipeline, the audio_a input must be
        # registered as a separate ffmpeg input (input index 1) so the
        # handler's `-map 0:v -map 1:a` works correctly.
        has_replace_audio = any(
            s.skill_name == "replace_audio" for s in pipeline.steps
        )

        temp_audio_input = None
        if has_replace_audio and audio_a is not None:
            # Save audio_a to a temp WAV so it can be used as ffmpeg input [1]
            try:
                waveform = audio_a["waveform"]
                sample_rate = audio_a["sample_rate"]
                channels = waveform.size(1)
                audio_data = waveform.squeeze(0).transpose(0, 1).contiguous()
                audio_bytes = (audio_data * 32767.0).clamp(-32768, 32767).to(torch.int16).numpy().tobytes()

                import tempfile as _tmpmod
                import subprocess
                _tmp_wav = _tmpmod.NamedTemporaryFile(suffix=".wav", delete=False)
                _tmp_wav.close()
                subprocess.run(
                    [
                        "ffmpeg", "-y",
                        "-f", "s16le",
                        "-ar", str(sample_rate),
                        "-ac", str(channels),
                        "-i", "-",
                        _tmp_wav.name,
                    ],
                    input=audio_bytes,
                    capture_output=True,
                )
                # Insert at the beginning so it becomes input [1]
                # (input [0] is the main video)
                pipeline.extra_inputs.insert(0, _tmp_wav.name)
                temp_audio_input = _tmp_wav.name
                logger.debug("Saved audio_a as temp WAV for replace_audio: %s", _tmp_wav.name)
            except Exception as e:
                logger.warning(f"Could not save audio_a for replace_audio: {e}")

        # --- Multi-input frame extraction ---
        # Collect all dynamically-connected image inputs (image_a, image_b, ...)
        # for multi-input skills (grid, slideshow, overlay_image, concat, etc.)
        MULTI_INPUT_SKILLS = {"grid", "slideshow", "overlay_image", "overlay",
                              "concat", "split_screen", "watermark", "chromakey",
                              "xfade", "transition", "animated_overlay", "moving_overlay"}
        needs_multi_input = any(
            s.skill_name in MULTI_INPUT_SKILLS for s in pipeline.steps
        )
        temp_frames_dirs = set()
        temp_multi_videos = []  # Track temp videos for cleanup
        if needs_multi_input:
            all_frame_paths = []

            # --- File-path-based video inputs (zero memory cost) ---
            # Uses _all_video_paths collected earlier from video_a, video_b, ...
            if _all_video_paths:
                all_frame_paths.extend(_all_video_paths)
                logger.debug("File-path video inputs (zero memory): %s", _all_video_paths)

            # --- File-path-based image inputs (zero memory cost) ---
            # Image paths are NOT added to all_frame_paths because that list
            # feeds _extra_input_paths which xfade/concat treat as video
            # segments.  Instead, pass them via pipeline metadata so the
            # composer can add them as separate -i entries for overlay.
            if _all_image_paths:
                pipeline.metadata["_image_paths"] = _all_image_paths
                logger.debug("File-path image inputs (zero memory): %s", _all_image_paths)

            # Collect all image_* tensors in alphabetical order
            # (exclude images_* which are collected separately as video inputs)
            all_image_keys = []
            if image_a is not None:
                all_image_keys.append(('__image_a__', image_a))
            for k in sorted(kwargs):
                if k.startswith("image_") and not k.startswith("images_") and not k.startswith("image_path_") and kwargs[k] is not None:
                    all_image_keys.append((k, kwargs[k]))

            # Also collect images_b, images_c, ... (additional video inputs)
            for k in sorted(kwargs):
                if k.startswith("images_") and kwargs[k] is not None:
                    all_image_keys.append((k, kwargs[k]))

            # Process each tensor one at a time and RELEASE it immediately
            # to avoid holding all video frames in memory simultaneously.
            # With 8 × 8s × 24fps × 1080p float32 tensors, keeping all in
            # memory would require ~38GB — processing one at a time keeps
            # peak at ~5GB.
            for ti, (tkey, tensor) in enumerate(all_image_keys):
                logger.debug("Multi-input tensor %d (%s): shape=%s", ti, tkey, tensor.shape)
                if tensor.shape[0] > 10:
                    # Save as temp video for performance
                    tmp_vid = self.media_converter.images_to_video(tensor)
                    all_frame_paths.append(tmp_vid)
                    temp_multi_videos.append(tmp_vid)
                    # Probe duration for debugging
                    try:
                        import subprocess as _sp
                        _dur = _sp.run(
                            ["ffprobe", "-v", "error", "-show_entries",
                             "format=duration", "-of",
                             "default=noprint_wrappers=1", tmp_vid],
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

                # Release tensor memory immediately after conversion
                del tensor
                # Clear the reference from kwargs too
                if tkey == '__image_a__':
                    image_a = None
                elif tkey in kwargs:
                    kwargs[tkey] = None

            # Release the key list and trigger garbage collection
            del all_image_keys
            try:
                import torch as _torch
                if _torch.cuda.is_available():
                    _torch.cuda.empty_cache()
            except Exception:
                pass

            # Fallback: primary images_a tensor with multiple frames
            if not all_frame_paths and images_a is not None and images_a.shape[0] > 1:
                all_frame_paths = self.media_converter.save_frames_as_images(images_a)
                if all_frame_paths:
                    temp_frames_dirs.add(os.path.dirname(all_frame_paths[0]))

            if all_frame_paths:
                pipeline.extra_inputs = all_frame_paths
                pipeline.metadata["frame_count"] = len(all_frame_paths)

            # Auto-set include_video for slideshow/grid based on whether
            # a real video is connected (not a dummy placeholder).
            has_real_video = '_images_a_shape' in dir() or images_a is not None or (video_path and video_path.strip())
            for step in pipeline.steps:
                if step.skill_name in ("slideshow", "grid"):
                    step.params["include_video"] = has_real_video

        # --- Multi-audio input collection ---
        # Mux each audio directly into its paired video segment so the
        # concat filter can simply read [idx:a] from each video input.
        temp_audio_files = []
        if needs_multi_input:
            all_audio_dicts = []
            if audio_a is not None:
                all_audio_dicts.append(audio_a)
            for k in sorted(kwargs):
                if k.startswith("audio_") and k != "audio_a" and kwargs[k] is not None:
                    all_audio_dicts.append(kwargs[k])

            if all_audio_dicts:
                video_segments = [effective_video_path] + list(pipeline.extra_inputs)
                for ai, audio_dict in enumerate(all_audio_dicts):
                    if ai >= len(video_segments):
                        break
                    vid_path = video_segments[ai]
                    if not os.path.isfile(vid_path):
                        continue
                    # Skip if already has audio (e.g. audio_a pre-muxed earlier)
                    if self.media_converter.has_audio_stream(vid_path):
                        continue
                    try:
                        self.media_converter.mux_audio(vid_path, audio_dict)
                    except Exception as e:
                        import logging
                        logging.getLogger("ffmpega").warning(
                            f"Could not mux audio {ai} into {vid_path}: {e}"
                        )

            # Build video_segments list for audio detection below
            video_segments = [effective_video_path] + list(pipeline.extra_inputs)

            # --- Detect embedded audio in video files (zero-memory path) ---
            # When using video_path STRING inputs, the video files already
            # contain audio but no AUDIO tensor inputs are connected.
            # We still need _has_embedded_audio so xfade/concat generates
            # proper audio crossfade filters and -map directives.
            is_audio_filter_skill = any(
                s.skill_name in ("concat", "xfade")
                for s in pipeline.steps
            )
            if is_audio_filter_skill:
                # Ensure ALL segments have audio — inject silent track
                # into any that lack it so [idx:a] references work.
                for vid_path in video_segments:
                    if not os.path.isfile(vid_path):
                        continue
                    if not self.media_converter.has_audio_stream(vid_path):
                        try:
                            self.media_converter.add_silent_audio(vid_path)
                        except Exception as e:
                            import logging
                            logging.getLogger("ffmpega").warning(
                                f"Could not add silent audio to {vid_path}: {e}"
                            )
                # Only flag if all segments truly have audio now
                all_have_audio = all(
                    self.media_converter.has_audio_stream(vp)
                    for vp in video_segments
                    if os.path.isfile(vp)
                )
                if all_have_audio:
                    pipeline.metadata["_has_embedded_audio"] = True

        command = self.composer.compose(pipeline)

        # --- FPS normalization for speed changes ---
        # setpts changes timestamps but doesn't alter frame count, so
        # frames_to_tensor reads the same number of frames.  Downstream
        # save nodes then write at the original FPS, collapsing the
        # duration back.  Appending an fps filter resamples the frame
        # count to match the new duration at the original frame rate.
        vf_str = command.video_filters.to_string()
        if "setpts=" in vf_str and not command.complex_filter:
            input_fps = (
                video_metadata.primary_video.frame_rate
                if video_metadata.primary_video and video_metadata.primary_video.frame_rate
                else 30
            )
            command.video_filters.add_filter("fps", {"fps": int(round(input_fps))})

        # Debug: log exact command
        logger.debug("Command: %s", command.to_string())
        logger.debug("Audio filters: '%s'", command.audio_filters.to_string())
        logger.debug("Video filters: '%s'", command.video_filters.to_string())
        if command.complex_filter:
            logger.debug("Complex filter: '%s'", command.complex_filter)
        logger.debug("Pipeline steps: %s", [(s.skill_name, s.params) for s in pipeline.steps])

        # --- Dry-run validation ---
        dry_result = self.process_manager.dry_run(command, timeout=30)
        if not dry_result.success:
            import logging
            logging.getLogger("ffmpega").warning(
                f"Dry-run failed: {dry_result.error_message} "
                "(will attempt execution anyway)"
            )

        # --- Execute with error-feedback retry ---
        if preview_mode:
            if command.complex_filter:
                # Use -s output option to avoid appending scale to audio chains
                command.output_options.extend(["-s", "480x270"])
            else:
                command.video_filters.add_filter("scale", {"w": 480, "h": -1})
            command.output_options.extend(["-t", "10"])

        max_attempts = 2
        result = None
        for attempt in range(max_attempts):
            result = self.process_manager.execute(command, timeout=600)
            if result.success:
                break

            if attempt < max_attempts - 1:
                # Feed error back to LLM for correction
                logger.warning(
                    f"FFMPEG failed (attempt {attempt + 1}), "
                    f"feeding error back to LLM: {result.error_message}"
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
                    )
                    # Rebuild pipeline from corrected spec
                    pipeline = Pipeline(
                        input_path=effective_video_path,
                        output_path=output_path,
                        extra_inputs=pipeline.extra_inputs,
                        metadata=pipeline.metadata,
                    )
                    for step in retry_spec.get("pipeline", []):
                        skill_name = step.get("skill")
                        params = step.get("params", {})
                        if skill_name:
                            pipeline.add_step(skill_name, params)
                    # Re-add quality preset
                    if quality_preset and not any(
                        s.skill_name in ["quality", "compress"]
                        for s in pipeline.steps
                    ):
                        _crf_map = {"draft": 28, "standard": 23, "high": 18, "lossless": 0}
                        _preset_map = {"draft": "ultrafast", "standard": "medium", "high": "slow", "lossless": "veryslow"}
                        pipeline.add_step("quality", {
                            "crf": crf if crf >= 0 else _crf_map.get(quality_preset, 23),
                            "preset": encoding_preset if encoding_preset != "auto" else _preset_map.get(quality_preset, "medium"),
                        })
                    command = self.composer.compose(pipeline)
                    # FPS normalization for retry path (same as main path)
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
                    import logging
                    logging.getLogger("ffmpega").warning(
                        f"Error feedback retry failed: {retry_err}"
                    )
                    break

        if not result.success:
            if hasattr(connector, 'close'):
                await connector.close()
            raise RuntimeError(
                f"FFMPEG execution failed: {result.error_message}\n"
                f"Command: {command.to_string()}"
            )

        # --- Output verification loop ---
        # Flow: verify → if fail → fix → re-verify the fix (max 2 correction attempts)
        _VERIFICATION_TIMEOUT = 90.0  # seconds per attempt
        _MAX_CORRECTION_ATTEMPTS = 2
        if verify_output and result.success:
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
                        logger.info(
                            "Correction attempt %d applied — re-verifying...",
                            attempt + 1,
                        )
                        # Loop again to re-verify the corrected output
                        continue
                    else:
                        # PASS or unparseable — output is accepted
                        logger.info(
                            "Verification PASS (attempt %d)", attempt + 1
                        )
                        break
                except asyncio.TimeoutError:
                    logger.warning(
                        "Output verification timed out after %.0fs "
                        "— keeping current output",
                        _VERIFICATION_TIMEOUT,
                    )
                    break
                except Exception as verify_err:
                    logger.warning(f"Output verification failed: {verify_err}")
                    # Non-fatal — keep current output
                    break

        # Close LLM connector now that all retries/verification are done
        if hasattr(connector, 'close'):
            await connector.close()

        # Debug: probe output duration
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

        # --- Handle audio (respecting audio_source from LLM) ---
        removes_audio = "-an" in command.output_options
        has_audio_processing = removes_audio or bool(command.audio_filters.to_string())
        # Complex filters that already embed audio (concat, xfade) should not be muxed again
        audio_already_embedded = pipeline.metadata.get("_has_embedded_audio", False)

        # Build dict of all available audio inputs
        audio_inputs = {}
        if audio_a is not None:
            audio_inputs["audio_a"] = audio_a
        for k in sorted(kwargs):
            if k.startswith("audio_") and k != "audio_a" and kwargs[k] is not None:
                audio_inputs[k] = kwargs[k]

        # Also check pipeline step params for audio_source (LLM may put it there)
        if audio_source == "mix":
            for step in pipeline_steps:
                step_audio = step.get("params", {}).get("audio_source")
                if step_audio and step_audio != "mix":
                    audio_source = step_audio
                    break

        logger.debug("Audio decision: removes=%s, has_processing=%s, "
                     "already_embedded=%s, audio_source=%s, available=%s",
                     removes_audio, has_audio_processing,
                     audio_already_embedded, audio_source,
                     list(audio_inputs.keys()))

        if audio_inputs and not removes_audio and not has_audio_processing and not audio_already_embedded:
            if audio_source and audio_source != "mix" and audio_source in audio_inputs:
                # Specific audio track requested by LLM
                logger.debug("Using specific audio: %s", audio_source)
                self.media_converter.mux_audio(output_path, audio_inputs[audio_source], audio_mode=audio_mode)
            elif len(audio_inputs) == 1:
                # Only one audio input — just use it
                name = list(audio_inputs.keys())[0]
                logger.debug("Using only available audio: %s", name)
                self.media_converter.mux_audio(output_path, audio_inputs[name], audio_mode=audio_mode)
            else:
                # "mix" mode — blend all audio tracks together
                logger.debug("Mixing %d audio tracks: %s", len(audio_inputs), list(audio_inputs.keys()))
                self.media_converter.mux_audio_mix(
                    output_path, list(audio_inputs.values()), audio_mode=audio_mode
                )

        # --- Extract a single thumbnail frame (NOT all frames) ---
        # Loading all frames into a tensor uses ~6 MB × frame_count
        # (e.g. 13 GB for 74s @ 30fps 1080p).  For the zero-memory
        # pipeline (LoadVideoPath → Agent → SaveVideo) this is pure
        # waste.  We extract only the first frame for the IMAGE output
        # (used as a thumbnail / workflow PNG preview).  Users who need
        # all frames should use the Frame Extract node or VHS Load.
        images_tensor = self._extract_thumbnail_frame(output_path)
        logger.debug("Output thumbnail shape: %s", images_tensor.shape)

        # --- Extract output audio ---
        if removes_audio:
            audio_out = {"waveform": torch.zeros(1, 1, 1, dtype=torch.float32), "sample_rate": 44100}
        else:
            audio_out = self.media_converter.extract_audio(output_path)

        # --- Sanitize api_key from workflow metadata ---
        # ComfyUI embeds PROMPT/EXTRA_PNGINFO in output files.
        # Strip the api_key so it never leaks into saved images/videos.
        hidden_prompt = kwargs.get("hidden_prompt")
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

        # Clean up temp videos, frame images, and audio files
        for tmp_path in [temp_video_from_images, temp_video_with_audio, temp_audio_input] + temp_multi_videos + temp_audio_files:
            if tmp_path and os.path.exists(tmp_path):
                os.remove(tmp_path)
        if temp_frames_dirs:
            for d in temp_frames_dirs:
                if os.path.isdir(d):
                    shutil.rmtree(d, ignore_errors=True)
        # Clean up temp render dir (pass-through mode)
        if not save_output and temp_render_dir and os.path.isdir(temp_render_dir):
            # The output file is referenced by the returned path — downstream
            # nodes will read it.  We schedule cleanup for *after* this node
            # returns by removing only the directory if the file has already
            # been consumed, or leaving it for ComfyUI's own temp management.
            # For now, do NOT delete — ComfyUI still needs the file.  We only
            # ensure we are not silently leaking empty dirs if the render
            # produced nothing.
            if not os.listdir(temp_render_dir):
                shutil.rmtree(temp_render_dir, ignore_errors=True)

        return (images_tensor, audio_out, output_path, command.to_string(), analysis)

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
        from ..mcp.vision import generate_audio_visualization as _gen_audio_viz
        from ..prompts.system import get_verification_prompt
        from ..skills.composer import Pipeline

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
                content_parts = [{"type": "text", "text": verify_prompt}]
                for img_block in b64_data:
                    content_parts.append(img_block)
                verify_messages = [{"role": "user", "content": content_parts}]
                verify_response = await connector.chat_with_tools(
                    verify_messages, tools=[],
                )
            else:
                verify_response = await connector.generate(
                    verify_prompt,
                    system_prompt="You are a video and audio quality reviewer.",
                )

            verify_text = (verify_response.content or "").strip()
            logger.info(f"Verification result: {verify_text[:200]}")

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
            result = subprocess.run(
                [ffprobe_bin, "-v", "error", "-show_entries",
                 "format=duration", "-of", "default=noprint_wrappers=1:nokey=1",
                 video_path],
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
    ) -> tuple[torch.Tensor, dict, str, str, str]:
        """Process all matching videos in a folder with the same pipeline.

        Uses one LLM call to generate the pipeline, then applies it to
        every video concurrently via ThreadPoolExecutor.
        """
        import glob
        from concurrent.futures import ThreadPoolExecutor, as_completed
        from ..skills.composer import Pipeline
        from ..core.sanitize import validate_video_path as _validate

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
            out_dir = Path(output_path)
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
        total = len(valid_files)

        # Return the last successful video as frames, or a placeholder
        last_path = output_paths[-1] if output_paths else valid_files[0]
        frames_tensor = self.media_converter.frames_to_tensor(last_path)
        audio_dict = self.media_converter.extract_audio(last_path)

        import json
        paths_json = json.dumps(output_paths, indent=2)

        status_lines = [
            f"Batch complete: {processed}/{total} videos processed",
            f"Output folder: {out_dir}",
        ]
        if errors:
            status_lines.append(f"\nErrors ({len(errors)}):")
            for err in errors:
                status_lines.append(f"  - {err}")

        analysis = (
            f"Batch Mode — {interpretation}\n\n"
            + "\n".join(status_lines)
        )

        command_log = "\n\n".join(command_logs) if command_logs else "No commands executed"

        return (frames_tensor, audio_dict, paths_json, command_log, analysis)

    @classmethod
    def IS_CHANGED(cls, video_path, prompt, seed=0, **kwargs):
        """Determine if the node needs to re-execute."""
        return f"{video_path}:{prompt}:{seed}"
