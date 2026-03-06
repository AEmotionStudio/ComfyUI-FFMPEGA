"""AI Visual skills registration — AI-powered visual transformations."""

from ..registry import (
    SkillRegistry,
    Skill,
    SkillCategory,
    SkillParameter,
    ParameterType,
)


def register_skills(registry: SkillRegistry) -> None:
    """Register AI visual transformation skills."""

    # Animate portrait — LivePortrait
    registry.register(Skill(
        name="animate_portrait",
        category=SkillCategory.AI_VISUAL,
        description=(
            "AI-animate a portrait: transfer head pose, facial expressions, "
            "eye gaze, and lip movements from a driving video to a source "
            "face image or video using LivePortrait. Produces a video where "
            "the source face moves like the driver."
        ),
        parameters=[
            SkillParameter(
                name="driving_video",
                type=ParameterType.STRING,
                description="Path to the driving video whose motion will be transferred",
                required=True,
            ),
            SkillParameter(
                name="driving_multiplier",
                type=ParameterType.FLOAT,
                description="Scale factor for driving motion intensity (1.0 = normal)",
                required=False,
                default=1.0,
                min_value=0.1,
                max_value=3.0,
            ),
            SkillParameter(
                name="relative_motion",
                type=ParameterType.BOOL,
                description="Use relative motion transfer (recommended). If false, uses absolute pose.",
                required=False,
                default=True,
            ),
        ],
        examples=[
            "animate_portrait:driving_video=/path/to/driver.mp4 - Animate source with driver's expressions",
            "animate_portrait:driving_video=/path/to/driver.mp4,driving_multiplier=1.5 - Exaggerated motion",
            "animate_portrait:driving_video=/path/to/driver.mp4,relative_motion=false - Absolute pose transfer",
        ],
        tags=[
            "animate", "portrait", "liveportrait", "face", "expression",
            "pose", "reenactment", "puppet", "ai", "deepfake",
            "head", "motion",
        ],
    ))
