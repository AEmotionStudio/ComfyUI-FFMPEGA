"""FFMPEG Agent node for ComfyUI."""

import os
import time
from pathlib import Path
from typing import Optional

import torch  # type: ignore[import-not-found]

import folder_paths  # type: ignore[import-not-found]


class FFMPEGAgentNode:
    """Main FFMPEG Agent node that transforms natural language prompts into video edits."""

    # Fallback models if Ollama is unreachable
    FALLBACK_OLLAMA_MODELS = [
        "llama3.1:8b",
        "mistral:7b",
        "qwen2.5:7b",
    ]

    API_MODELS = [
        "gpt-4o",
        "gpt-4o-mini",
        "claude-sonnet-4-20250514",
        "claude-3-5-haiku-20241022",
        "gemini-2.0-flash",
        "gemini-2.0-flash-lite",
        "gemini-1.5-flash",
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
            },
            "optional": {
                "images": ("IMAGE", {
                    "tooltip": "Optional image frames from an upstream node (e.g. Load Video Upload). When connected, these frames are used as the video input instead of video_path.",
                }),
                "audio_input": ("AUDIO", {
                    "tooltip": "Optional audio from an upstream node (e.g. Load Video Upload). When connected, this audio is muxed into the output video and passed through on the audio output.",
                }),
                "preview_mode": ("BOOLEAN", {
                    "default": False,
                    "label_on": "Preview",
                    "label_off": "Full Render",
                    "tooltip": "When enabled, generates a quick low-res preview (480p, first 10 seconds) instead of a full render.",
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
            },
        }

    RETURN_TYPES = ("IMAGE", "AUDIO", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("images", "audio", "video_path", "command_log", "analysis")
    OUTPUT_TOOLTIPS = (
        "All frames from the output video as a batched image tensor.",
        "Audio extracted from the output video (or passed through from audio_input) in ComfyUI AUDIO format.",
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
        images: Optional[torch.Tensor] = None,
        audio_input: Optional[dict] = None,
        preview_mode: bool = False,
        output_path: str = "",
        ollama_url: str = "http://localhost:11434",
        api_key: str = "",
        crf: int = -1,
        encoding_preset: str = "auto",
    ) -> tuple[torch.Tensor, dict, str, str, str]:
        """Process the video based on the natural language prompt.

        Args:
            video_path: Path to input video.
            prompt: Natural language editing instruction.
            llm_model: LLM model to use.
            quality_preset: Output quality preset.
            images: Optional input IMAGE tensor from upstream nodes.
            audio_input: Optional input AUDIO dict from upstream nodes.
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

        # --- Resolve input video ---
        temp_video_from_images = None
        temp_video_with_audio = None
        if images is not None:
            temp_video_from_images = self.media_converter.images_to_video(images)
            effective_video_path = temp_video_from_images
        else:
            effective_video_path = video_path

        # Validate input
        from ..core.sanitize import validate_video_path  # type: ignore[import-not-found]
        effective_video_path = validate_video_path(effective_video_path)

        # Pre-mux audio_input into the input video so audio filters
        # (e.g. loudnorm, echo) have an audio stream to process.
        # Without this, images-only inputs have no audio track and
        # audio filters silently produce no output.
        if audio_input is not None and not self.media_converter.has_audio_stream(effective_video_path):
            import tempfile as _tmpmod
            tmp = _tmpmod.NamedTemporaryFile(suffix=".mp4", delete=False)
            tmp.close()
            import shutil as _shmod
            _shmod.copy2(effective_video_path, tmp.name)
            self.media_converter.mux_audio(tmp.name, audio_input)
            temp_video_with_audio = tmp.name
            effective_video_path = tmp.name

        if not prompt.strip():
            raise ValueError("Prompt cannot be empty")

        # --- Analyze input video ---
        video_metadata = self.analyzer.analyze(effective_video_path)
        metadata_str = video_metadata.to_analysis_string()

        # --- Generate pipeline via LLM ---
        connector = self.pipeline_generator.create_connector(llm_model, ollama_url, api_key)
        try:
            spec = await self.pipeline_generator.generate(connector, prompt, metadata_str)
        except Exception:
            if hasattr(connector, 'close'):
                await connector.close()
            raise

        interpretation = spec.get("interpretation", "")
        warnings = spec.get("warnings", [])
        estimated_changes = spec.get("estimated_changes", "")
        pipeline_steps = spec.get("pipeline", [])

        # --- Build output path ---
        stem = Path(effective_video_path).stem
        suffix = "_preview" if preview_mode else "_edited"

        if not output_path:
            output_dir = folder_paths.get_output_directory()
            output_path = str(Path(output_dir) / f"{stem}{suffix}.mp4")
        elif Path(output_path).is_dir() or output_path.endswith(os.sep):
            output_dir = output_path.rstrip(os.sep)
            output_path = str(Path(output_dir) / f"{stem}{suffix}.mp4")
        elif not Path(output_path).suffix:
            os.makedirs(output_path, exist_ok=True)
            output_path = str(Path(output_path) / f"{stem}{suffix}.mp4")

        os.makedirs(Path(output_path).parent, exist_ok=True)

        # --- Build pipeline ---
        pipeline = Pipeline(
            input_path=effective_video_path,
            output_path=output_path,
        )

        for step in pipeline_steps:
            skill_name = step.get("skill")
            params = step.get("params", {})
            if skill_name:
                pipeline.add_step(skill_name, params)

        # Add quality preset if not already specified
        if quality_preset and not any(s.skill_name in ["quality", "compress"] for s in pipeline.steps):
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
            import logging
            logger = logging.getLogger("ffmpega")
            for err in errors:
                logger.warning(f"Pipeline validation: {err} (continuing anyway)")

        # --- Multi-input frame extraction ---
        # Skills that need individual image files as extra FFMPEG inputs
        MULTI_INPUT_SKILLS = {"grid", "slideshow", "overlay_image"}
        needs_multi_input = any(
            s.skill_name in MULTI_INPUT_SKILLS for s in pipeline.steps
        )
        temp_frames_dir = None
        if needs_multi_input and images is not None:
            frame_paths = self.media_converter.save_frames_as_images(images)
            pipeline.extra_inputs = frame_paths
            # Track temp dir for cleanup
            if frame_paths:
                temp_frames_dir = os.path.dirname(frame_paths[0])
            # Store frame count in metadata for handlers
            pipeline.metadata["frame_count"] = len(frame_paths)

        command = self.composer.compose(pipeline)

        # Debug: print exact command to console
        print(f"[FFMPEGA DEBUG] Command: {command.to_string()}")
        print(f"[FFMPEGA DEBUG] Audio filters: '{command.audio_filters.to_string()}'")
        print(f"[FFMPEGA DEBUG] Video filters: '{command.video_filters.to_string()}'")
        if command.complex_filter:
            print(f"[FFMPEGA DEBUG] Complex filter: '{command.complex_filter}'")
        print(f"[FFMPEGA DEBUG] Pipeline steps: {[(s.skill_name, s.params) for s in pipeline.steps]}")

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
                import logging
                logger = logging.getLogger("ffmpega")
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
                        connector, error_prompt, metadata_str
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
                    print(f"[FFMPEGA DEBUG] Retry command: {command.to_string()}")
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

        # Close LLM connector now that all retries are done
        if hasattr(connector, 'close'):
            await connector.close()

        # --- Build analysis string ---
        analysis = f"""Interpretation: {interpretation}

Estimated Changes: {estimated_changes}

Pipeline Steps:
{self.composer.explain_pipeline(pipeline)}

Warnings: {', '.join(warnings) if warnings else 'None'}"""

        # --- Handle audio ---
        removes_audio = "-an" in command.output_options
        has_audio_processing = removes_audio or bool(command.audio_filters.to_string())

        if audio_input is not None and not has_audio_processing:
            self.media_converter.mux_audio(output_path, audio_input)

        # --- Extract output frames ---
        images_tensor = self.media_converter.frames_to_tensor(output_path)

        # --- Extract output audio ---
        if removes_audio:
            audio_out = {"waveform": torch.zeros(1, 1, 1, dtype=torch.float32), "sample_rate": 44100}
        else:
            audio_out = self.media_converter.extract_audio(output_path)

        # Clean up temp videos and frame images
        for tmp_path in [temp_video_from_images, temp_video_with_audio]:
            if tmp_path and os.path.exists(tmp_path):
                os.remove(tmp_path)
        if temp_frames_dir and os.path.isdir(temp_frames_dir):
            import shutil
            shutil.rmtree(temp_frames_dir, ignore_errors=True)

        return (images_tensor, audio_out, output_path, command.to_string(), analysis)

    @classmethod
    def IS_CHANGED(cls, video_path, prompt, **kwargs):
        """Determine if the node needs to re-execute."""
        return f"{video_path}:{prompt}"
