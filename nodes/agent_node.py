"""FFMPEG Agent node for ComfyUI."""

import json
import os
import re
import shutil
import subprocess
import tempfile
import asyncio
from pathlib import Path
from typing import Optional, Any

import numpy as np  # type: ignore[import-not-found]
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

    @classmethod
    def _fetch_ollama_models(cls, base_url: str = "http://localhost:11434") -> list[str]:
        """Fetch available models from a running Ollama instance.

        Returns locally installed model names, or the fallback list
        if Ollama is unreachable.
        """
        try:
            import httpx  # type: ignore[import-not-found]
            with httpx.Client(timeout=3.0) as client:
                resp = client.get(f"{base_url}/api/tags")
                resp.raise_for_status()
                models = [m["name"] for m in resp.json().get("models", [])]
                return sorted(models) if models else cls.FALLBACK_OLLAMA_MODELS
        except Exception:
            return cls.FALLBACK_OLLAMA_MODELS

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

        Returns:
            Tuple of (images_tensor, audio, output_video_path, command_log, analysis).
        """
        from ..skills.composer import Pipeline  # type: ignore[import-not-found]

        # If images are provided, write them to a temporary video file
        # so the ffmpeg pipeline can use them as input
        temp_video_from_images = None
        if images is not None:
            temp_video_from_images = self._images_to_temp_video(images)
            effective_video_path = temp_video_from_images
        else:
            effective_video_path = video_path

        # Validate input
        if not effective_video_path or not Path(effective_video_path).exists():
            raise ValueError(f"Video file not found: {effective_video_path}")

        if not prompt.strip():
            raise ValueError("Prompt cannot be empty")

        # Analyze input video
        video_metadata = self.analyzer.analyze(effective_video_path)
        metadata_str = video_metadata.to_analysis_string()

        # Create LLM connector
        connector = self._create_connector(llm_model, ollama_url, api_key)

        # Generate pipeline using LLM
        try:
            pipeline_spec = await self._generate_pipeline(
                connector, prompt, metadata_str
            )
        finally:
            if hasattr(connector, 'close'):
                await connector.close()

        # Parse LLM response
        try:
            if not pipeline_spec or not pipeline_spec.strip():
                raise ValueError(
                    "LLM returned an empty response. This usually means the model "
                    "is overloaded, the prompt was too long, or the model couldn't "
                    "understand the request. Try again or use a different model."
                )
            spec = json.loads(pipeline_spec)
        except json.JSONDecodeError as e:
            # Try to extract JSON from response (LLM may wrap in markdown)
            spec = self._extract_json(pipeline_spec)
            if not spec:
                # Show a snippet of what the LLM actually returned for debugging
                preview = pipeline_spec[:300] if pipeline_spec else "(empty)"
                raise ValueError(
                    f"Failed to parse LLM response as JSON.\n"
                    f"LLM returned: {preview}\n"
                    f"Parse error: {e}\n"
                    f"Tip: Try running the prompt again or use a different model."
                )

        interpretation = spec.get("interpretation", "")
        warnings = spec.get("warnings", [])
        estimated_changes = spec.get("estimated_changes", "")
        pipeline_steps = spec.get("pipeline", [])

        # Build output path
        stem = Path(effective_video_path).stem
        suffix = "_preview" if preview_mode else "_edited"

        if not output_path:
            output_dir = folder_paths.get_output_directory()
            output_path = str(Path(output_dir) / f"{stem}{suffix}.mp4")
        elif Path(output_path).is_dir() or output_path.endswith(os.sep):
            # User gave a directory — generate a filename inside it
            output_dir = output_path.rstrip(os.sep)
            output_path = str(Path(output_dir) / f"{stem}{suffix}.mp4")
        elif not Path(output_path).suffix:
            # No extension — treat as directory and append filename
            os.makedirs(output_path, exist_ok=True)
            output_path = str(Path(output_path) / f"{stem}{suffix}.mp4")

        # Ensure output directory exists
        os.makedirs(Path(output_path).parent, exist_ok=True)

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
            pipeline.add_step("quality", {
                "crf": crf_map.get(quality_preset, 23),
                "preset": preset_map.get(quality_preset, "medium"),
            })

        # Validate pipeline (warn but don't block — LLMs are imprecise)
        is_valid, errors = self.composer.validate_pipeline(pipeline)
        if not is_valid:
            import logging
            logger = logging.getLogger("ffmpega")
            for err in errors:
                logger.warning(f"Pipeline validation: {err} (continuing anyway)")

        command = self.composer.compose(pipeline)

        # Execute
        if preview_mode:
            # Add preview-specific options
            command.video_filters.add_filter("scale", {"w": 480, "h": -1})
            command.output_options.extend(["-t", "10"])  # First 10 seconds only

        result = self.process_manager.execute(command, timeout=600)

        if not result.success:
            raise RuntimeError(
                f"FFMPEG execution failed: {result.error_message}\n"
                f"Command: {command.to_string()}"
            )

        # Build analysis string
        analysis = f"""Interpretation: {interpretation}

Estimated Changes: {estimated_changes}

Pipeline Steps:
{self.composer.explain_pipeline(pipeline)}

Warnings: {', '.join(warnings) if warnings else 'None'}"""

        # If audio_input was provided, mux it into the output video
        if audio_input is not None:
            self._mux_audio_into_video(output_path, audio_input)

        # Extract frames from output video as IMAGE tensor
        images_tensor = self._extract_frames_as_tensor(output_path)

        # For audio output: prefer the audio_input passthrough, else extract from output
        if audio_input is not None:
            audio_out = audio_input
        else:
            audio_out = self._extract_audio(output_path)

        # Clean up temp video if we created one
        if temp_video_from_images and os.path.exists(temp_video_from_images):
            os.remove(temp_video_from_images)

        return (images_tensor, audio_out, output_path, command.to_string(), analysis)

    def _extract_frames_as_tensor(self, video_path: str) -> torch.Tensor:
        """Extract all frames from a video and return as a batched IMAGE tensor.

        Args:
            video_path: Path to the video file.

        Returns:
            Tensor of shape (B, H, W, 3) with float32 values in [0, 1].
        """
        import imageio.v3 as iio  # type: ignore[import-not-found]

        try:
            # Read all frames from the video
            frames_raw = iio.imread(video_path, plugin="pyav")

            # frames_raw: (B, H, W, C) uint8 numpy array
            frames = frames_raw.astype(np.float32) / 255.0

            # Ensure RGB (drop alpha if present)
            if frames.shape[-1] == 4:
                frames = frames[:, :, :, :3]
            elif frames.shape[-1] == 1:
                frames = np.repeat(frames, 3, axis=-1)

            return torch.from_numpy(frames)

        except Exception:
            # Fallback: return a single black frame
            return torch.zeros(1, 64, 64, 3, dtype=torch.float32)

    def _extract_audio(self, video_path: str) -> dict:
        """Extract audio from a video and return as ComfyUI AUDIO dict.

        Returns a dict with 'waveform' (Tensor of shape [1, channels, samples])
        and 'sample_rate' (int), compatible with ComfyUI's standard AUDIO type.

        If the video has no audio stream, returns a short silent mono buffer.
        """
        ffmpeg_bin = shutil.which("ffmpeg")
        ffprobe_bin = shutil.which("ffprobe")
        if not ffmpeg_bin or not ffprobe_bin:
            # No ffmpeg/ffprobe — return silence
            return {"waveform": torch.zeros(1, 1, 1, dtype=torch.float32), "sample_rate": 44100}

        # Check whether the video actually contains an audio stream
        try:
            probe = subprocess.run(
                [ffprobe_bin, "-v", "error", "-select_streams", "a",
                 "-show_entries", "stream=codec_type", "-of", "csv=p=0", video_path],
                capture_output=True, check=True,
            )
            if not probe.stdout.decode("utf-8", "backslashreplace").strip():
                # No audio stream
                return {"waveform": torch.zeros(1, 1, 1, dtype=torch.float32), "sample_rate": 44100}
        except subprocess.CalledProcessError:
            return {"waveform": torch.zeros(1, 1, 1, dtype=torch.float32), "sample_rate": 44100}

        # Extract raw PCM audio via ffmpeg
        try:
            res = subprocess.run(
                [ffmpeg_bin, "-i", video_path, "-f", "f32le", "-"],
                capture_output=True, check=True,
            )
            audio = torch.frombuffer(bytearray(res.stdout), dtype=torch.float32)
            # Parse sample rate and channel layout from stderr
            match = re.search(r", (\d+) Hz, (\w+), ", res.stderr.decode("utf-8", "backslashreplace"))
            if match:
                ar = int(match.group(1))
                ac = {"mono": 1, "stereo": 2}.get(match.group(2), 2)
            else:
                ar = 44100
                ac = 2
            audio = audio.reshape((-1, ac)).transpose(0, 1).unsqueeze(0)
            return {"waveform": audio, "sample_rate": ar}
        except Exception:
            return {"waveform": torch.zeros(1, 1, 1, dtype=torch.float32), "sample_rate": 44100}

    def _images_to_temp_video(
        self, images: torch.Tensor, fps: int = 24
    ) -> str:
        """Convert an IMAGE tensor (B, H, W, 3) to a temporary video file.

        Args:
            images: Batched image tensor with float32 values in [0, 1].
            fps: Frame rate for the output video.

        Returns:
            Path to the created temporary video file.
        """
        ffmpeg_bin = shutil.which("ffmpeg")
        if not ffmpeg_bin:
            raise RuntimeError("ffmpeg not found in PATH")

        # Convert tensor to uint8 numpy frames
        frames = (images.cpu().numpy() * 255.0).clip(0, 255).astype(np.uint8)
        h, w = frames.shape[1], frames.shape[2]

        # Write to a temp file via ffmpeg rawvideo pipe
        tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
        tmp.close()

        proc = subprocess.Popen(
            [
                ffmpeg_bin, "-y",
                "-f", "rawvideo",
                "-vcodec", "rawvideo",
                "-s", f"{w}x{h}",
                "-pix_fmt", "rgb24",
                "-r", str(fps),
                "-i", "-",
                "-c:v", "libx264",
                "-pix_fmt", "yuv420p",
                "-preset", "fast",
                "-crf", "18",
                tmp.name,
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        proc.stdin.write(frames.tobytes())
        proc.stdin.close()
        proc.wait()

        if proc.returncode != 0:
            stderr = proc.stderr.read().decode("utf-8", "backslashreplace")
            os.remove(tmp.name)
            raise RuntimeError(f"Failed to create temp video from images: {stderr}")

        return tmp.name

    def _mux_audio_into_video(self, video_path: str, audio: dict) -> None:
        """Mux a ComfyUI AUDIO dict into an existing video file.

        Writes the audio waveform to a temp WAV, then combines it with
        the video using ffmpeg, replacing the file in-place.
        """
        ffmpeg_bin = shutil.which("ffmpeg")
        if not ffmpeg_bin:
            return

        waveform = audio["waveform"]       # (1, channels, samples)
        sample_rate = audio["sample_rate"]
        channels = waveform.size(1)

        # Write raw PCM to a temp WAV file
        audio_data = waveform.squeeze(0).transpose(0, 1).contiguous()  # (samples, channels)
        audio_bytes = (audio_data * 32767.0).clamp(-32768, 32767).to(torch.int16).numpy().tobytes()

        tmp_wav = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tmp_wav.close()
        tmp_out = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
        tmp_out.close()

        try:
            # Create WAV via ffmpeg
            proc = subprocess.run(
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

            # Mux video + audio
            subprocess.run(
                [
                    ffmpeg_bin, "-y",
                    "-i", video_path,
                    "-i", tmp_wav.name,
                    "-c:v", "copy",
                    "-c:a", "aac",
                    "-shortest",
                    tmp_out.name,
                ],
                capture_output=True, check=True,
            )

            # Replace original with muxed version
            shutil.move(tmp_out.name, video_path)
        except Exception:
            pass  # If muxing fails, keep the original video without audio
        finally:
            for f in [tmp_wav.name, tmp_out.name]:
                if os.path.exists(f):
                    try:
                        os.remove(f)
                    except OSError:
                        pass

    def _create_connector(
        self,
        model: str,
        ollama_url: str,
        api_key: str,
    ):
        """Create appropriate LLM connector based on model selection."""
        from ..core.llm.base import LLMConfig, LLMProvider  # type: ignore[import-not-found]
        from ..core.llm.ollama import OllamaConnector  # type: ignore[import-not-found]
        from ..core.llm.api import APIConnector  # type: ignore[import-not-found]

        if model not in self.API_MODELS and not model.startswith(("gpt", "claude", "gemini")):
            config = LLMConfig(
                provider=LLMProvider.OLLAMA,
                model=model,
                base_url=ollama_url,
                temperature=0.3,
            )
            return OllamaConnector(config)

        elif model.startswith("gpt"):
            config = LLMConfig(
                provider=LLMProvider.OPENAI,
                model=model,
                api_key=api_key,
                temperature=0.3,
            )
            return APIConnector(config)

        elif model.startswith("claude"):
            config = LLMConfig(
                provider=LLMProvider.ANTHROPIC,
                model=model,
                api_key=api_key,
                temperature=0.3,
            )
            return APIConnector(config)

        elif model.startswith("gemini"):
            config = LLMConfig(
                provider=LLMProvider.GEMINI,
                model=model,
                api_key=api_key,
                temperature=0.3,
            )
            return APIConnector(config)

        else:
            # Default to Ollama
            config = LLMConfig(
                provider=LLMProvider.OLLAMA,
                model="llama3.1:8b",
                base_url=ollama_url,
                temperature=0.3,
            )
            return OllamaConnector(config)

    async def _generate_pipeline(
        self,
        connector,
        prompt: str,
        video_metadata: str,
    ) -> str:
        """Generate pipeline specification using LLM.

        Uses agentic tool-calling if the connector supports it,
        otherwise falls back to single-shot generation.

        Args:
            connector: LLM connector to use.
            prompt: User's editing prompt.
            video_metadata: Video analysis string.

        Returns:
            JSON string with pipeline specification.
        """
        # Try agentic mode first (tool-calling)
        try:
            return await self._generate_pipeline_agentic(
                connector, prompt, video_metadata
            )
        except NotImplementedError:
            # Connector doesn't support tool calling — use single-shot
            return await self._generate_pipeline_single_shot(
                connector, prompt, video_metadata
            )

    async def _generate_pipeline_single_shot(
        self,
        connector,
        prompt: str,
        video_metadata: str,
    ) -> str:
        """Single-shot pipeline generation (original approach).

        Sends the full skill registry in the system prompt and expects
        a complete pipeline JSON in one response.

        Args:
            connector: LLM connector to use.
            prompt: User's editing prompt.
            video_metadata: Video analysis string.

        Returns:
            JSON string with pipeline specification.
        """
        from ..prompts.system import get_system_prompt  # type: ignore[import-not-found]
        from ..prompts.generation import get_generation_prompt  # type: ignore[import-not-found]

        system_prompt = get_system_prompt(
            video_metadata=video_metadata,
            include_full_registry=True,
        )

        user_prompt = get_generation_prompt(prompt, video_metadata)

        response = await connector.generate(user_prompt, system_prompt)
        return response.content

    async def _generate_pipeline_agentic(
        self,
        connector,
        prompt: str,
        video_metadata: str,
        max_iterations: int = 10,
    ) -> str:
        """Agentic pipeline generation with tool calling.

        The LLM dynamically discovers skills using MCP tools,
        iterating until it produces a final pipeline.

        Args:
            connector: LLM connector to use (must support chat_with_tools).
            prompt: User's editing prompt.
            video_metadata: Video analysis string.
            max_iterations: Maximum tool-calling rounds.

        Returns:
            JSON string with pipeline specification.

        Raises:
            NotImplementedError: If connector doesn't support tool calling.
        """
        from ..prompts.system import get_agentic_system_prompt  # type: ignore[import-not-found]
        from ..prompts.generation import get_generation_prompt  # type: ignore[import-not-found]
        from ..mcp.tool_defs import TOOL_DEFINITIONS  # type: ignore[import-not-found]
        from ..mcp.tools import (  # type: ignore[import-not-found]
            analyze_video,
            list_skills,
            search_skills,
            get_skill_details,
        )

        system_prompt = get_agentic_system_prompt(video_metadata=video_metadata)
        user_prompt = get_generation_prompt(prompt, video_metadata)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        # Tool dispatch map
        tool_handlers = {
            "list_skills": lambda args: list_skills(args.get("category")),
            "search_skills": lambda args: search_skills(args.get("query", "")),
            "get_skill_details": lambda args: get_skill_details(args.get("skill_name", "")),
            "analyze_video": lambda args: analyze_video(args.get("video_path", "")),
        }

        import logging
        logger = logging.getLogger("ffmpega")

        for iteration in range(max_iterations):
            response = await connector.chat_with_tools(messages, TOOL_DEFINITIONS)

            if not response.tool_calls:
                # Model returned a final answer — return it
                return response.content

            # Process tool calls
            # Append the assistant's message with tool calls
            assistant_msg = {"role": "assistant", "content": response.content or ""}
            assistant_msg["tool_calls"] = [
                {
                    "function": {
                        "name": tc["function"]["name"],
                        "arguments": tc["function"]["arguments"],
                    }
                }
                for tc in response.tool_calls
            ]
            messages.append(assistant_msg)

            for tool_call in response.tool_calls:
                func_name = tool_call["function"]["name"]
                func_args = tool_call["function"]["arguments"]

                logger.info(f"Tool call [{iteration+1}]: {func_name}({func_args})")

                handler = tool_handlers.get(func_name)
                if handler:
                    try:
                        result = handler(func_args)
                        result_str = json.dumps(result, indent=2)
                    except Exception as e:
                        result_str = json.dumps({"error": str(e)})
                        logger.warning(f"Tool error: {func_name} -> {e}")
                else:
                    result_str = json.dumps({"error": f"Unknown tool: {func_name}"})

                # Add tool result to conversation
                messages.append({
                    "role": "tool",
                    "content": result_str,
                })

        # If we exhausted iterations, try to get a final answer
        logger.warning(f"Agentic loop hit max iterations ({max_iterations})")
        # Send one more message asking for the final pipeline
        messages.append({
            "role": "user",
            "content": (
                "You have used all available tool calls. Based on "
                "what you've learned, please output the final JSON "
                "pipeline now."
            ),
        })
        response = await connector.chat_with_tools(messages, [])
        return response.content

    def _extract_json(self, text: str) -> Optional[dict]:
        """Try to extract JSON from text that may contain other content."""
        import re

        # Try to find JSON block
        patterns = [
            r'```json\s*(.*?)\s*```',
            r'```\s*(.*?)\s*```',
            r'\{[\s\S]*\}',
        ]

        for pattern in patterns:
            matches = re.findall(pattern, text, re.DOTALL)
            for match in matches:
                try:
                    return json.loads(match)
                except json.JSONDecodeError:
                    continue

        return None

    @classmethod
    def IS_CHANGED(cls, video_path, prompt, **kwargs):
        """Determine if the node needs to re-execute."""
        # Re-execute if inputs change
        return f"{video_path}:{prompt}"
