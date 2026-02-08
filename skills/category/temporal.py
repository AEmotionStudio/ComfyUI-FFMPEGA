"""Temporal editing skills (trim, speed, reverse, etc.)."""

from ..registry import SkillRegistry, Skill, SkillParameter, SkillCategory, ParameterType


def register_skills(registry: SkillRegistry) -> None:
    """Register temporal skills with the registry."""

    # Trim skill
    registry.register(Skill(
        name="trim",
        category=SkillCategory.TEMPORAL,
        description="Remove portions of video by time",
        parameters=[
            SkillParameter(
                name="start",
                type=ParameterType.TIME,
                description="Start time in seconds",
                required=False,
                default=None,
            ),
            SkillParameter(
                name="end",
                type=ParameterType.TIME,
                description="End time in seconds",
                required=False,
                default=None,
            ),
            SkillParameter(
                name="duration",
                type=ParameterType.TIME,
                description="Duration from start in seconds",
                required=False,
                default=None,
            ),
        ],
        examples=[
            "trim:start=5 - Remove first 5 seconds",
            "trim:start=10,end=30 - Keep only seconds 10-30",
            "trim:start=0,duration=60 - Keep first minute",
        ],
        tags=["cut", "slice", "timing", "duration"],
    ))

    # Speed skill
    registry.register(Skill(
        name="speed",
        category=SkillCategory.TEMPORAL,
        description="Adjust playback speed while maintaining audio pitch",
        parameters=[
            SkillParameter(
                name="factor",
                type=ParameterType.FLOAT,
                description="Speed multiplier (0.25=4x slower, 2.0=2x faster)",
                required=False,
                default=2.0,
                min_value=0.1,
                max_value=10.0,
            ),
        ],
        examples=[
            "speed:factor=2.0 - Double speed",
            "speed:factor=0.5 - Half speed (slow motion)",
            "speed:factor=0.25 - Quarter speed (dramatic slow-mo)",
        ],
        tags=["fast", "slow", "motion", "timelapse", "slowmo"],
    ))

    # Reverse skill
    registry.register(Skill(
        name="reverse",
        category=SkillCategory.TEMPORAL,
        description="Play video backwards",
        parameters=[],
        examples=[
            "reverse - Play the entire video in reverse",
        ],
        tags=["backwards", "rewind"],
    ))

    # Loop skill
    registry.register(Skill(
        name="loop",
        category=SkillCategory.TEMPORAL,
        description="Repeat video N times",
        parameters=[
            SkillParameter(
                name="count",
                type=ParameterType.INT,
                description="Number of times to repeat",
                required=False,
                default=2,
                min_value=2,
                max_value=100,
            ),
        ],
        examples=[
            "loop:count=3 - Repeat video 3 times",
        ],
        tags=["repeat", "cycle"],
    ))

    # Freeze frame skill
    registry.register(Skill(
        name="freeze_frame",
        category=SkillCategory.TEMPORAL,
        description="Hold on a specific frame for a duration",
        parameters=[
            SkillParameter(
                name="time",
                type=ParameterType.TIME,
                description="Time of frame to freeze",
                required=True,
            ),
            SkillParameter(
                name="duration",
                type=ParameterType.TIME,
                description="How long to hold the frame",
                required=True,
            ),
        ],
        ffmpeg_template="tpad=stop_mode=clone:stop_duration={duration}",
        examples=[
            "freeze_frame:time=10,duration=3 - Freeze frame at 10s for 3 seconds",
        ],
        tags=["pause", "still", "hold"],
    ))

    # FPS skill
    registry.register(Skill(
        name="fps",
        category=SkillCategory.TEMPORAL,
        description="Change the frame rate of the video",
        parameters=[
            SkillParameter(
                name="rate",
                type=ParameterType.FLOAT,
                description="Target frame rate",
                required=False,
                default=30,
                min_value=1,
                max_value=120,
            ),
        ],
        ffmpeg_template="fps={rate}",
        examples=[
            "fps:rate=30 - Convert to 30 fps",
            "fps:rate=60 - Convert to 60 fps",
            "fps:rate=24 - Convert to 24 fps (cinematic)",
        ],
        tags=["framerate", "frames"],
    ))
