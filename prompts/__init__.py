"""LLM prompt templates for FFMPEGA."""

from .system import get_system_prompt, SYSTEM_PROMPT_TEMPLATE
from .analysis import get_analysis_prompt
from .generation import get_generation_prompt

__all__ = [
    "get_system_prompt",
    "SYSTEM_PROMPT_TEMPLATE",
    "get_analysis_prompt",
    "get_generation_prompt",
]
