"""Batch Processor node for ComfyUI."""

import asyncio
import json
import glob
from pathlib import Path
from typing import Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

import folder_paths


class BatchProcessorNode:
    """Node for batch processing multiple videos with the same prompt."""

    OLLAMA_MODELS = [
        "llama3.1:8b",
        "llama3.1:70b",
        "mistral:7b",
    ]

    @classmethod
    def INPUT_TYPES(cls):
        """Define input types for the node."""
        return {
            "required": {
                "video_folder": ("STRING", {
                    "default": "",
                    "multiline": False,
                    "placeholder": "Path to folder with videos",
                    "tooltip": "Absolute path to the folder containing the video files to process.",
                }),
                "prompt": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "placeholder": "Editing instruction for all videos...",
                    "tooltip": "Natural language editing instruction applied to every video in the batch.",
                }),
                "file_pattern": ("STRING", {
                    "default": "*.mp4",
                    "multiline": False,
                    "tooltip": "Glob pattern to match video files in the folder. Examples: '*.mp4', '*.avi', 'clip_*.mov'.",
                }),
            },
            "optional": {
                "output_folder": ("STRING", {
                    "default": "",
                    "multiline": False,
                    "placeholder": "Output folder (optional)",
                    "tooltip": "Folder to save edited videos. Leave empty to use ComfyUI's default output directory.",
                }),
                "llm_model": (cls.OLLAMA_MODELS, {
                    "default": "llama3.1:8b",
                    "tooltip": "Ollama model used to interpret the editing prompt.",
                }),
                "max_concurrent": ("INT", {
                    "default": 4,
                    "min": 1,
                    "max": 16,
                    "step": 1,
                    "tooltip": "Maximum number of videos to process simultaneously. Higher values use more CPU/GPU.",
                }),
                "continue_on_error": ("BOOLEAN", {
                    "default": True,
                    "tooltip": "When enabled, the batch continues processing remaining videos even if one fails.",
                }),
                "output_suffix": ("STRING", {
                    "default": "_edited",
                    "multiline": False,
                    "tooltip": "Suffix appended to each output filename. E.g. 'clip.mp4' becomes 'clip_edited.mp4'.",
                }),
                "ollama_url": ("STRING", {
                    "default": "http://localhost:11434",
                    "tooltip": "URL of the Ollama server for local LLM inference.",
                }),
            },
        }

    RETURN_TYPES = ("INT", "STRING", "STRING")
    RETURN_NAMES = ("processed_count", "output_paths", "error_log")
    OUTPUT_TOOLTIPS = (
        "Number of videos successfully processed.",
        "JSON array of output file paths for all processed videos.",
        "Log of any errors encountered during batch processing.",
    )
    FUNCTION = "process_batch"
    CATEGORY = "FFMPEGA"
    DESCRIPTION = "Process multiple videos in a folder with the same editing instruction. Uses a single LLM call and applies the pipeline to all matching files."
    OUTPUT_NODE = True

    def __init__(self):
        """Initialize the batch processor node."""
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

    def process_batch(
        self,
        video_folder: str,
        prompt: str,
        file_pattern: str,
        output_folder: str = "",
        llm_model: str = "llama3.1:8b",
        max_concurrent: int = 4,
        continue_on_error: bool = True,
        output_suffix: str = "_edited",
        ollama_url: str = "http://localhost:11434",
    ) -> tuple[int, str, str]:
        """Process multiple videos with the same editing instruction.

        Args:
            video_folder: Path to folder containing videos.
            prompt: Editing instruction for all videos.
            file_pattern: Glob pattern for video files.
            output_folder: Output destination folder.
            llm_model: LLM model to use.
            max_concurrent: Maximum concurrent processes.
            continue_on_error: Whether to continue on errors.
            output_suffix: Suffix for output files.
            ollama_url: Ollama server URL.

        Returns:
            Tuple of (processed_count, output_paths_json, error_log).
        """
        from ..core.llm.base import LLMConfig, LLMProvider
        from ..core.llm.ollama import OllamaConnector
        from ..skills.composer import Pipeline

        # Validate input folder
        video_folder_path = Path(video_folder)
        if not video_folder_path.exists():
            raise ValueError(f"Video folder not found: {video_folder}")

        # Find matching videos
        pattern = str(video_folder_path / file_pattern)
        video_files = glob.glob(pattern)

        # Filter valid video files
        from ..core.sanitize import validate_video_path  # type: ignore[import-not-found]
        valid_video_files = []
        validation_errors = []
        for vf in video_files:
            try:
                validate_video_path(vf)
                valid_video_files.append(vf)
            except ValueError as e:
                validation_errors.append(f"Skipped {Path(vf).name}: {str(e)}")

        video_files = valid_video_files

        if not video_files:
            msg = f"No valid video files matching pattern: {file_pattern}"
            if validation_errors:
                msg += "\nValidation errors:\n" + "\n".join(validation_errors)
            return (0, "[]", msg)

        # Set up output folder
        if output_folder:
            output_folder_path = Path(output_folder)
            output_folder_path.mkdir(parents=True, exist_ok=True)
        else:
            output_folder_path = Path(folder_paths.get_output_directory()) / "ffmpega_batch"
            output_folder_path.mkdir(exist_ok=True)

        # Generate pipeline once using sample video
        sample_video = video_files[0]
        sample_metadata = self.analyzer.analyze(sample_video)

        # Create LLM connector
        config = LLMConfig(
            provider=LLMProvider.OLLAMA,
            model=llm_model,
            base_url=ollama_url,
            temperature=0.3,
        )
        connector = OllamaConnector(config)

        # Generate pipeline spec
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            pipeline_spec = loop.run_until_complete(
                self._generate_batch_pipeline(
                    connector,
                    prompt,
                    sample_metadata.to_analysis_string(),
                    len(video_files),
                    file_pattern,
                )
            )
        finally:
            loop.close()

        # Parse pipeline
        try:
            spec = json.loads(pipeline_spec)
        except json.JSONDecodeError:
            spec = self._extract_json(pipeline_spec)
            if not spec:
                return (0, "[]", f"Failed to parse LLM response: {pipeline_spec[:500]}")

        pipeline_steps = spec.get("pipeline", [])

        # Process videos
        output_paths = []
        errors = []
        processed = 0

        def process_single(video_path: str) -> tuple[str, Optional[str]]:
            """Process a single video."""
            try:
                input_path = Path(video_path)
                output_path = output_folder_path / f"{input_path.stem}{output_suffix}.mp4"

                pipeline = Pipeline(
                    input_path=str(input_path),
                    output_path=str(output_path),
                )

                for step in pipeline_steps:
                    skill_name = step.get("skill")
                    params = step.get("params", {})
                    if skill_name:
                        pipeline.add_step(skill_name, params)

                # Compose and execute
                command = self.composer.compose(pipeline)
                result = self.process_manager.execute(command, timeout=600)

                if result.success:
                    return (str(output_path), None)
                else:
                    return (str(output_path), result.error_message)

            except Exception as e:
                return (video_path, str(e))

        # Use thread pool for concurrent processing
        with ThreadPoolExecutor(max_workers=max_concurrent) as executor:
            futures = {
                executor.submit(process_single, vf): vf
                for vf in video_files
            }

            for future in as_completed(futures):
                video_file = futures[future]
                try:
                    output_path, error = future.result()

                    if error:
                        errors.append(f"{Path(video_file).name}: {error}")
                        if not continue_on_error:
                            executor.shutdown(wait=False)
                            break
                    else:
                        output_paths.append(output_path)
                        processed += 1

                except Exception as e:
                    errors.append(f"{Path(video_file).name}: {str(e)}")
                    if not continue_on_error:
                        break

        # Build output
        output_paths_json = json.dumps(output_paths, indent=2)
        error_log = "\n".join(errors) if errors else "No errors"

        return (processed, output_paths_json, error_log)

    async def _generate_batch_pipeline(
        self,
        connector,
        prompt: str,
        sample_metadata: str,
        video_count: int,
        file_pattern: str,
    ) -> str:
        """Generate pipeline for batch processing.

        Args:
            connector: LLM connector.
            prompt: User's editing prompt.
            sample_metadata: Sample video metadata.
            video_count: Number of videos.
            file_pattern: File pattern.

        Returns:
            JSON string with pipeline specification.
        """
        from ..prompts.system import get_system_prompt
        from ..prompts.generation import get_batch_prompt

        system_prompt = get_system_prompt(
            video_metadata=sample_metadata,
            include_full_registry=False,
        )

        user_prompt = get_batch_prompt(
            prompt,
            sample_metadata,
            video_count,
            file_pattern,
        )

        response = await connector.generate(user_prompt, system_prompt)
        return response.content

    def _extract_json(self, text: str) -> Optional[dict]:
        """Try to extract JSON from text."""
        import re

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


class BatchStatusNode:
    """Node for monitoring batch processing status."""

    @classmethod
    def INPUT_TYPES(cls):
        """Define input types for the node."""
        return {
            "required": {
                "output_folder": ("STRING", {
                    "default": "",
                    "multiline": False,
                    "tooltip": "Path to the batch output folder to monitor.",
                }),
                "expected_count": ("INT", {
                    "default": 0,
                    "min": 0,
                    "tooltip": "Expected total number of output files. Set to 0 if unknown.",
                }),
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("status",)
    OUTPUT_TOOLTIPS = ("Summary of batch progress: completed count and list of finished files.",)
    FUNCTION = "get_status"
    CATEGORY = "FFMPEGA"
    DESCRIPTION = "Monitor the progress of a batch processing job by checking the output folder."

    def get_status(
        self,
        output_folder: str,
        expected_count: int,
    ) -> tuple[str]:
        """Get batch processing status.

        Args:
            output_folder: Output folder to check.
            expected_count: Expected number of files.

        Returns:
            Tuple containing status string.
        """
        if not output_folder or not Path(output_folder).exists():
            return ("Output folder not found",)

        output_path = Path(output_folder)
        completed = list(output_path.glob("*.mp4"))

        status_lines = [
            f"Completed: {len(completed)} / {expected_count if expected_count else '?'}",
            "",
            "Completed files:",
        ]

        for f in completed[:20]:  # Show first 20
            status_lines.append(f"  - {f.name}")

        if len(completed) > 20:
            status_lines.append(f"  ... and {len(completed) - 20} more")

        return ("\n".join(status_lines),)
