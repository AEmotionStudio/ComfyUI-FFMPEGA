"""FFMPEG Agent node for ComfyUI."""

import json
import os
import tempfile
import asyncio
from pathlib import Path
from typing import Optional, Any

import folder_paths


class FFMPEGAgentNode:
    """Main FFMPEG Agent node that transforms natural language prompts into video edits."""

    # Available LLM models
    OLLAMA_MODELS = [
        "llama3.1:8b",
        "llama3.1:70b",
        "mistral:7b",
        "codellama:13b",
        "deepseek-coder:6.7b",
        "qwen2.5:7b",
    ]

    API_MODELS = [
        "gpt-4o",
        "gpt-4o-mini",
        "claude-sonnet-4-20250514",
        "claude-3-5-haiku-20241022",
    ]

    QUALITY_PRESETS = ["draft", "standard", "high", "lossless"]

    @classmethod
    def INPUT_TYPES(cls):
        """Define input types for the node."""
        all_models = cls.OLLAMA_MODELS + cls.API_MODELS + ["custom"]

        return {
            "required": {
                "video_path": ("STRING", {
                    "default": "",
                    "multiline": False,
                    "placeholder": "Path to input video file",
                }),
                "prompt": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "placeholder": "Describe how you want to edit the video...",
                }),
                "llm_model": (all_models, {
                    "default": "llama3.1:8b",
                }),
                "quality_preset": (cls.QUALITY_PRESETS, {
                    "default": "standard",
                }),
            },
            "optional": {
                "preview_mode": ("BOOLEAN", {
                    "default": False,
                    "label_on": "Preview",
                    "label_off": "Full Render",
                }),
                "output_path": ("STRING", {
                    "default": "",
                    "multiline": False,
                    "placeholder": "Output path (optional)",
                }),
                "ollama_url": ("STRING", {
                    "default": "http://localhost:11434",
                    "multiline": False,
                }),
                "api_key": ("STRING", {
                    "default": "",
                    "multiline": False,
                    "placeholder": "API key for OpenAI/Anthropic",
                }),
            },
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("video_path", "command_log", "analysis")
    FUNCTION = "process"
    CATEGORY = "FFMPEGA"
    OUTPUT_NODE = True

    def __init__(self):
        """Initialize the agent node."""
        self._analyzer = None
        self._process_manager = None
        self._registry = None
        self._composer = None

    @property
    def analyzer(self):
        if self._analyzer is None:
            from ..core.video.analyzer import VideoAnalyzer
            self._analyzer = VideoAnalyzer()
        return self._analyzer

    @property
    def process_manager(self):
        if self._process_manager is None:
            from ..core.executor.process_manager import ProcessManager
            self._process_manager = ProcessManager()
        return self._process_manager

    @property
    def registry(self):
        if self._registry is None:
            from ..skills.registry import get_registry
            self._registry = get_registry()
        return self._registry

    @property
    def composer(self):
        if self._composer is None:
            from ..skills.composer import SkillComposer
            self._composer = SkillComposer(self.registry)
        return self._composer

    def process(
        self,
        video_path: str,
        prompt: str,
        llm_model: str,
        quality_preset: str,
        preview_mode: bool = False,
        output_path: str = "",
        ollama_url: str = "http://localhost:11434",
        api_key: str = "",
    ) -> tuple[str, str, str]:
        """Process the video based on the natural language prompt.

        Args:
            video_path: Path to input video.
            prompt: Natural language editing instruction.
            llm_model: LLM model to use.
            quality_preset: Output quality preset.
            preview_mode: Generate preview instead of full render.
            output_path: Custom output path.
            ollama_url: Ollama server URL.
            api_key: API key for cloud providers.

        Returns:
            Tuple of (output_video_path, command_log, analysis).
        """
        from ..skills.composer import Pipeline

        # Validate input
        if not video_path or not Path(video_path).exists():
            raise ValueError(f"Video file not found: {video_path}")

        if not prompt.strip():
            raise ValueError("Prompt cannot be empty")

        # Analyze input video
        video_metadata = self.analyzer.analyze(video_path)
        metadata_str = video_metadata.to_analysis_string()

        # Create LLM connector
        connector = self._create_connector(llm_model, ollama_url, api_key)

        # Generate pipeline using LLM
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            pipeline_spec = loop.run_until_complete(
                self._generate_pipeline(connector, prompt, metadata_str)
            )
        finally:
            loop.close()

        # Parse LLM response
        try:
            spec = json.loads(pipeline_spec)
        except json.JSONDecodeError as e:
            # Try to extract JSON from response
            spec = self._extract_json(pipeline_spec)
            if not spec:
                raise ValueError(f"Failed to parse LLM response: {e}")

        interpretation = spec.get("interpretation", "")
        warnings = spec.get("warnings", [])
        estimated_changes = spec.get("estimated_changes", "")
        pipeline_steps = spec.get("pipeline", [])

        # Build pipeline
        if not output_path:
            output_dir = folder_paths.get_output_directory()
            stem = Path(video_path).stem
            suffix = "_preview" if preview_mode else "_edited"
            output_path = str(Path(output_dir) / f"{stem}{suffix}.mp4")

        pipeline = Pipeline(
            input_path=video_path,
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

        # Validate and compose pipeline
        is_valid, errors = self.composer.validate_pipeline(pipeline)
        if not is_valid:
            raise ValueError(f"Invalid pipeline: {errors}")

        command = self.composer.compose(pipeline)

        # Execute
        if preview_mode:
            # Add preview-specific options
            command.video_filters.add_filter("scale", {"w": 480, "h": -1})
            command.output_options.extend(["-t", "10"])  # First 10 seconds only

        result = self.process_manager.execute(command, timeout=600)

        if not result.success:
            raise RuntimeError(f"FFMPEG execution failed: {result.error_message}")

        # Build analysis string
        analysis = f"""Interpretation: {interpretation}

Estimated Changes: {estimated_changes}

Pipeline Steps:
{self.composer.explain_pipeline(pipeline)}

Warnings: {', '.join(warnings) if warnings else 'None'}"""

        return (output_path, command.to_string(), analysis)

    def _create_connector(
        self,
        model: str,
        ollama_url: str,
        api_key: str,
    ):
        """Create appropriate LLM connector based on model selection."""
        from ..core.llm.base import LLMConfig, LLMProvider
        from ..core.llm.ollama import OllamaConnector
        from ..core.llm.api import APIConnector

        if model in self.OLLAMA_MODELS:
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

        Args:
            connector: LLM connector to use.
            prompt: User's editing prompt.
            video_metadata: Video analysis string.

        Returns:
            JSON string with pipeline specification.
        """
        from ..prompts.system import get_system_prompt
        from ..prompts.generation import get_generation_prompt

        system_prompt = get_system_prompt(
            video_metadata=video_metadata,
            include_full_registry=False,  # Use abbreviated to save tokens
        )

        user_prompt = get_generation_prompt(prompt, video_metadata)

        response = await connector.generate(user_prompt, system_prompt)
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
