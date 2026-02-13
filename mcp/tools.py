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


def extract_frames(
    video_path: str,
    start: float = 0.0,
    duration: float = 5.0,
    fps: float = 1.0,
    max_frames: int = 8,
) -> dict:
    """Extract frames from a video for visual inspection.

    Extracts PNG frames to a temp folder so CLI agents with vision
    capabilities can view the actual video content.

    Args:
        video_path: Path to the input video file.
        start: Start time in seconds.
        duration: Duration in seconds to extract from.
        fps: Frames per second to extract.
        max_frames: Maximum number of frames (capped at 16).

    Returns:
        Dictionary with frame_count, paths, and folder.
    """
    from pathlib import Path
    from ..core.executor.preview import PreviewGenerator
    from ..core.executor.process_manager import ProcessManager

    if not video_path or not Path(video_path).is_file():
        return {"error": f"Video file not found: {video_path}"}

    # Cap max_frames to prevent excessive disk/token usage
    max_frames = min(max(max_frames, 1), 16)
    fps = max(fps, 0.1)

    # Create a unique per-run subfolder to avoid cross-run interference
    import uuid
    node_dir = Path(__file__).resolve().parent.parent
    run_id = uuid.uuid4().hex[:8]
    frames_dir = node_dir / "_vision_frames" / run_id
    frames_dir.mkdir(parents=True, exist_ok=True)

    preview = PreviewGenerator()

    try:
        frame_paths = preview.extract_frames(
            input_path=video_path,
            output_dir=frames_dir,
            fps=fps,
            start=start if start > 0 else None,
            duration=duration,
        )
    except Exception as e:
        # Clean up the created directory on failure
        import shutil
        shutil.rmtree(frames_dir, ignore_errors=True)
        return {"error": f"Frame extraction failed: {e}", "run_id": run_id}

    # Limit to max_frames
    frame_paths = frame_paths[:max_frames]

    path_strings = [str(p.resolve()) for p in frame_paths]

    return {
        "frame_count": len(path_strings),
        "paths": path_strings,
        "folder": str(frames_dir.resolve()),
        "run_id": run_id,
        "hint": (
            "These are absolute paths to PNG frame images extracted from "
            "the video. You can view them to understand the video content, "
            "colors, composition, and lighting before choosing effects."
        ),
    }


def cleanup_vision_frames(run_id: str = "") -> None:
    """Remove the temporary vision frames folder.

    Args:
        run_id: If provided, removes only the specific run's subfolder.
                If empty, removes the entire _vision_frames directory.

    Called after pipeline generation completes to clean up disk space.
    """
    import shutil
    from pathlib import Path

    base_dir = Path(__file__).resolve().parent.parent / "_vision_frames"
    if run_id:
        target = base_dir / run_id
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)
        # Remove parent if empty (ignore errors to avoid masking success)
        try:
            if base_dir.exists() and not any(base_dir.iterdir()):
                base_dir.rmdir()
        except OSError:
            pass
    elif base_dir.exists():
        shutil.rmtree(base_dir, ignore_errors=True)


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
