"""Motion and animation effect skills."""

from ..registry import SkillRegistry, Skill, SkillParameter, SkillCategory, ParameterType


def register_skills(registry: SkillRegistry) -> None:
    """Register motion effect skills with the registry."""

    # Spin - continuous rotation animation
    registry.register(Skill(
        name="spin",
        category=SkillCategory.OUTCOME,
        description="Continuously spin/rotate the video over time (animated rotation)",
        parameters=[
            SkillParameter(
                name="speed",
                type=ParameterType.FLOAT,
                description="Rotation speed in degrees per second",
                required=False,
                default=90.0,
                min_value=10.0,
                max_value=720.0,
            ),
            SkillParameter(
                name="direction",
                type=ParameterType.CHOICE,
                description="Rotation direction",
                required=False,
                default="cw",
                choices=["cw", "ccw"],
            ),
        ],
        examples=[
            "spin - Rotate 90 degrees per second clockwise",
            "spin:speed=360 - Full rotation every second",
            "spin:speed=45,direction=ccw - Slow counter-clockwise spin",
        ],
        tags=["rotate", "spinning", "twist", "turn", "animation", "dynamic"],
    ))

    # Shake - camera shake effect
    registry.register(Skill(
        name="shake",
        category=SkillCategory.OUTCOME,
        description="Add camera shake / earthquake effect to the video",
        parameters=[
            SkillParameter(
                name="intensity",
                type=ParameterType.CHOICE,
                description="Shake intensity",
                required=False,
                default="medium",
                choices=["light", "medium", "heavy"],
            ),
        ],
        examples=[
            "shake - Medium camera shake",
            "shake:intensity=heavy - Intense earthquake shake",
            "shake:intensity=light - Subtle handheld camera feel",
        ],
        tags=["camera", "earthquake", "shaky", "handheld", "vibrate", "wobble"],
    ))

    # Pulse - rhythmic zoom effect (breathing)
    registry.register(Skill(
        name="pulse",
        category=SkillCategory.OUTCOME,
        description="Rhythmic zoom in/out pulsing effect (like breathing)",
        parameters=[
            SkillParameter(
                name="rate",
                type=ParameterType.FLOAT,
                description="Pulses per second",
                required=False,
                default=1.0,
                min_value=0.2,
                max_value=5.0,
            ),
            SkillParameter(
                name="amount",
                type=ParameterType.FLOAT,
                description="Zoom range (0.02 = subtle, 0.1 = dramatic)",
                required=False,
                default=0.05,
                min_value=0.02,
                max_value=0.2,
            ),
        ],
        examples=[
            "pulse - Gentle 1 Hz breathing zoom",
            "pulse:rate=2,amount=0.1 - Fast dramatic pulsing",
            "pulse:rate=0.5,amount=0.03 - Very slow subtle pulse",
        ],
        tags=["zoom", "breathe", "rhythm", "heartbeat", "throb", "pulsate"],
    ))

    # Bounce - vertical bouncing animation
    registry.register(Skill(
        name="bounce",
        category=SkillCategory.OUTCOME,
        description="Bouncing vertical animation effect",
        parameters=[
            SkillParameter(
                name="height",
                type=ParameterType.INT,
                description="Maximum bounce height in pixels",
                required=False,
                default=30,
                min_value=5,
                max_value=100,
            ),
            SkillParameter(
                name="speed",
                type=ParameterType.FLOAT,
                description="Bounces per second",
                required=False,
                default=2.0,
                min_value=0.5,
                max_value=8.0,
            ),
        ],
        examples=[
            "bounce - Gentle bouncing effect",
            "bounce:height=50,speed=3 - Fast high bouncing",
            "bounce:height=10,speed=1 - Slow subtle bounce",
        ],
        tags=["jump", "hop", "spring", "animation", "playful", "fun"],
    ))

    # Drift - slow horizontal/vertical pan
    registry.register(Skill(
        name="drift",
        category=SkillCategory.OUTCOME,
        description="Slow cinematic drift/pan across the frame",
        parameters=[
            SkillParameter(
                name="direction",
                type=ParameterType.CHOICE,
                description="Drift direction",
                required=False,
                default="right",
                choices=["left", "right", "up", "down"],
            ),
            SkillParameter(
                name="amount",
                type=ParameterType.INT,
                description="Total drift distance in pixels",
                required=False,
                default=50,
                min_value=10,
                max_value=200,
            ),
        ],
        examples=[
            "drift - Slow rightward pan",
            "drift:direction=up,amount=100 - Upward drift",
            "drift:direction=left,amount=30 - Subtle leftward movement",
        ],
        tags=["pan", "move", "slide", "cinematic", "slow", "motion"],
    ))
