"""Transition effect skills - fades and dissolves."""

from ..registry import SkillRegistry, Skill, SkillParameter, SkillCategory, ParameterType


def register_skills(registry: SkillRegistry) -> None:
    """Register transition skills with the registry."""

    # Fade to black (both in and out)
    registry.register(Skill(
        name="fade_to_black",
        category=SkillCategory.OUTCOME,
        description="Fade in from black at the start and/or fade out to black at the end",
        parameters=[
            SkillParameter(
                name="in_duration",
                type=ParameterType.FLOAT,
                description="Fade-in duration in seconds (0 to skip)",
                required=False,
                default=1.0,
                min_value=0,
                max_value=10.0,
            ),
            SkillParameter(
                name="out_duration",
                type=ParameterType.FLOAT,
                description="Fade-out duration in seconds (0 to skip)",
                required=False,
                default=1.0,
                min_value=0,
                max_value=10.0,
            ),
        ],
        examples=[
            "fade_to_black - 1s fade in + 1s fade out",
            "fade_to_black:in_duration=2,out_duration=3 - 2s fade in, 3s fade out",
            "fade_to_black:in_duration=0,out_duration=2 - Only fade out at end",
        ],
        tags=["fade", "black", "transition", "intro", "outro", "smooth"],
    ))

    # Scene fade - fade in from white
    registry.register(Skill(
        name="fade_to_white",
        category=SkillCategory.OUTCOME,
        description="Fade in from white at the start and/or fade out to white at the end",
        parameters=[
            SkillParameter(
                name="in_duration",
                type=ParameterType.FLOAT,
                description="Fade-in duration in seconds (0 to skip)",
                required=False,
                default=1.0,
                min_value=0,
                max_value=10.0,
            ),
            SkillParameter(
                name="out_duration",
                type=ParameterType.FLOAT,
                description="Fade-out duration in seconds (0 to skip)",
                required=False,
                default=1.0,
                min_value=0,
                max_value=10.0,
            ),
        ],
        examples=[
            "fade_to_white - 1s white fade in + 1s white fade out",
            "fade_to_white:in_duration=2,out_duration=0 - Only fade in from white",
        ],
        tags=["fade", "white", "transition", "dream", "bright", "smooth"],
    ))

    # Flash transition
    registry.register(Skill(
        name="flash",
        category=SkillCategory.OUTCOME,
        description="Add a bright flash effect at a specific time (like a camera flash)",
        parameters=[
            SkillParameter(
                name="time",
                type=ParameterType.FLOAT,
                description="Time of the flash in seconds",
                required=False,
                default=0,
            ),
            SkillParameter(
                name="duration",
                type=ParameterType.FLOAT,
                description="Flash duration in seconds",
                required=False,
                default=0.3,
                min_value=0.1,
                max_value=2.0,
            ),
        ],
        examples=[
            "flash - Flash at the start",
            "flash:time=5,duration=0.5 - Flash at 5 seconds",
        ],
        tags=["flash", "bright", "white", "strobe", "impact"],
    ))
