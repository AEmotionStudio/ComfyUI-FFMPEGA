"""FFMPEGA Skill System.

The skill system provides a modular way to define and compose
video editing operations. Skills are divided into two types:

1. Category Skills: Low-level operations (trim, resize, filter)
2. Outcome Skills: High-level results (cinematic, vintage, stabilize)
"""

from .registry import SkillRegistry, Skill, SkillParameter, SkillCategory
from .composer import SkillComposer, Pipeline, PipelineStep

__all__ = [
    "SkillRegistry",
    "Skill",
    "SkillParameter",
    "SkillCategory",
    "SkillComposer",
    "Pipeline",
    "PipelineStep",
]
