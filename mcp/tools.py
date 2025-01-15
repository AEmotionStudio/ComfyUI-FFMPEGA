"""MCP Tool implementations for FFMPEGA."""

import asyncio
from pathlib import Path
from typing import Any, Optional

from ..core.video.analyzer import VideoAnalyzer
from ..core.executor.command_builder import CommandBuilder
from ..core.executor.process_manager import ProcessManager
from ..skills.registry import get_registry, SkillCategory
from ..skills.composer import SkillComposer, Pipeline, PipelineStep


def analyze_video(video_path: str) -> dict:
    """Analyze input video properties and metadata.

    Args:
        video_path: Path to the video file.

    Returns:
        Dictionary with video metadata.
    """
    analyzer = VideoAnalyzer()
    metadata = analyzer.analyze(video_path)

    return {
        "file_path": metadata.file_path,
        "file_size_mb": round(metadata.file_size / (1024 * 1024), 2),
        "format": metadata.format_name,
        "duration_seconds": round(metadata.duration, 2),
        "video": {
            "width": metadata.primary_video.width if metadata.primary_video else None,
            "height": metadata.primary_video.height if metadata.primary_video else None,
            "codec": metadata.primary_video.codec_name if metadata.primary_video else None,
            "fps": round(metadata.primary_video.frame_rate, 2) if metadata.primary_video and metadata.primary_video.frame_rate else None,
            "pixel_format": metadata.primary_video.pixel_format if metadata.primary_video else None,
        },
        "audio": {
            "codec": metadata.primary_audio.codec_name if metadata.primary_audio else None,
            "sample_rate": metadata.primary_audio.sample_rate if metadata.primary_audio else None,
            "channels": metadata.primary_audio.channels if metadata.primary_audio else None,
        },
        "analysis_text": metadata.to_analysis_string(),
    }


def list_skills(category: Optional[str] = None) -> dict:
    """List available editing skills.

    Args:
        category: Optional category to filter by.

    Returns:
        Dictionary with skill information.
    """
    registry = get_registry()

    if category:
        try:
            cat_enum = SkillCategory(category)
            skills = registry.list_by_category(cat_enum)
        except ValueError:
            return {"error": f"Unknown category: {category}"}
    else:
        skills = registry.list_all()

    skill_list = []
    for skill in skills:
        skill_info = {
            "name": skill.name,
            "category": skill.category.value,
            "description": skill.description,
            "parameters": [
                {
                    "name": p.name,
                    "type": p.type.value,
                    "description": p.description,
                    "required": p.required,
                    "default": p.default,
                }
                for p in skill.parameters
            ],
            "tags": skill.tags,
            "examples": skill.examples,
        }
        skill_list.append(skill_info)

    # Group by category
    by_category = {}
    for skill in skill_list:
        cat = skill["category"]
        if cat not in by_category:
            by_category[cat] = []
        by_category[cat].append(skill)

    return {
        "total_count": len(skill_list),
        "skills": skill_list,
        "by_category": by_category,
    }


def build_pipeline(
    skills: list[dict],
    input_path: str,
    output_path: str,
) -> dict:
    """Build an FFMPEG command pipeline from skill specifications.

    Args:
        skills: List of skill specifications with 'name' and optional 'params'.
        input_path: Input video path.
        output_path: Output video path.

    Returns:
        Dictionary with pipeline information and command string.
    """
    registry = get_registry()
    composer = SkillComposer(registry)

    # Build pipeline
    pipeline = Pipeline(input_path=input_path, output_path=output_path)

    for skill_spec in skills:
        skill_name = skill_spec.get("name")
        params = skill_spec.get("params", {})

        if not skill_name:
            continue

        pipeline.add_step(skill_name, params)

    # Validate pipeline
    is_valid, errors = composer.validate_pipeline(pipeline)
    if not is_valid:
        return {
            "success": False,
            "errors": errors,
        }

    # Compose FFMPEG command
    try:
        command = composer.compose(pipeline)
        command_str = command.to_string()
        command_args = command.to_args()

        return {
            "success": True,
            "command": command_str,
            "command_args": command_args,
            "explanation": composer.explain_pipeline(pipeline),
            "step_count": len([s for s in pipeline.steps if s.enabled]),
        }
    except Exception as e:
        return {
            "success": False,
            "errors": [str(e)],
        }


async def execute_pipeline(command: str) -> dict:
    """Execute a built pipeline command.

    Args:
        command: FFMPEG command string to execute.

    Returns:
        Dictionary with execution results.
    """
    import shlex

    process_manager = ProcessManager()

    # Parse command string to args
    args = shlex.split(command)

    # Execute
    result = process_manager.execute(args)

    return {
        "success": result.success,
        "return_code": result.return_code,
        "output_path": result.output_path,
        "output_size_bytes": result.output_size,
        "error_message": result.error_message,
        "stderr": result.stderr[:1000] if result.stderr else None,  # Truncate
    }


def search_skills(query: str) -> dict:
    """Search for skills by name, description, or tags.

    Args:
        query: Search query string.

    Returns:
        Dictionary with matching skills.
    """
    registry = get_registry()
    matches = registry.search(query)

    return {
        "query": query,
        "match_count": len(matches),
        "matches": [
            {
                "name": s.name,
                "category": s.category.value,
                "description": s.description,
                "tags": s.tags,
            }
            for s in matches
        ],
    }


def get_skill_details(skill_name: str) -> dict:
    """Get detailed information about a specific skill.

    Args:
        skill_name: Name of the skill.

    Returns:
        Dictionary with skill details.
    """
    registry = get_registry()
    skill = registry.get(skill_name)

    if not skill:
        return {"error": f"Skill not found: {skill_name}"}

    return {
        "name": skill.name,
        "category": skill.category.value,
        "description": skill.description,
        "parameters": [
            {
                "name": p.name,
                "type": p.type.value,
                "description": p.description,
                "required": p.required,
                "default": p.default,
                "min_value": p.min_value,
                "max_value": p.max_value,
                "choices": p.choices,
            }
            for p in skill.parameters
        ],
        "ffmpeg_template": skill.ffmpeg_template,
        "pipeline": skill.pipeline,
        "examples": skill.examples,
        "tags": skill.tags,
    }


def validate_skill_params(skill_name: str, params: dict) -> dict:
    """Validate parameters for a skill.

    Args:
        skill_name: Name of the skill.
        params: Parameters to validate.

    Returns:
        Dictionary with validation results.
    """
    registry = get_registry()
    skill = registry.get(skill_name)

    if not skill:
        return {"valid": False, "errors": [f"Skill not found: {skill_name}"]}

    is_valid, errors = skill.validate_params(params)

    return {
        "valid": is_valid,
        "errors": errors,
        "skill": skill_name,
        "params": params,
    }
