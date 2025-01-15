"""MCP Resource definitions for FFMPEGA."""

from typing import Any

from .database.commands import FFMPEG_COMMAND_REFERENCE
from .database.filters import FFMPEG_FILTERS
from .database.presets import ENCODING_PRESETS


def get_resource(uri: str) -> dict:
    """Get an MCP resource by URI.

    Args:
        uri: Resource URI.

    Returns:
        Resource content dictionary.
    """
    if uri == "ffmpeg://commands/reference":
        return get_commands_reference()
    elif uri == "ffmpeg://filters/list":
        return get_filters_list()
    elif uri == "ffmpeg://skills/registry":
        return get_skills_registry()
    elif uri == "ffmpeg://presets/list":
        return get_presets_list()
    else:
        raise ValueError(f"Unknown resource URI: {uri}")


def get_commands_reference() -> dict:
    """Get FFMPEG command reference documentation.

    Returns:
        Command reference dictionary.
    """
    return FFMPEG_COMMAND_REFERENCE


def get_filters_list() -> dict:
    """Get FFMPEG filters documentation.

    Returns:
        Filters dictionary.
    """
    return FFMPEG_FILTERS


def get_skills_registry() -> dict:
    """Get skill registry as a resource.

    Returns:
        Skills registry dictionary.
    """
    from ..skills.registry import get_registry

    registry = get_registry()
    skills = registry.list_all()

    result = {
        "total_skills": len(skills),
        "categories": {},
    }

    for skill in skills:
        cat = skill.category.value
        if cat not in result["categories"]:
            result["categories"][cat] = []

        result["categories"][cat].append({
            "name": skill.name,
            "description": skill.description,
            "parameters": [
                {
                    "name": p.name,
                    "type": p.type.value,
                    "required": p.required,
                }
                for p in skill.parameters
            ],
        })

    return result


def get_presets_list() -> dict:
    """Get encoding presets.

    Returns:
        Presets dictionary.
    """
    return ENCODING_PRESETS
