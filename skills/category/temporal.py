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
                max_value=10000,
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

    # Scene detect — select frames at scene boundaries
    registry.register(Skill(
        name="scene_detect",
        category=SkillCategory.TEMPORAL,
        description="Detect and keep only scene-change frames (useful for auto-splitting or thumbnails)",
        parameters=[
            SkillParameter(
                name="threshold",
                type=ParameterType.FLOAT,
                description="Scene change sensitivity (0.1=sensitive, 0.5=major changes only)",
                required=False,
                default=0.3,
                min_value=0.05,
                max_value=0.9,
            ),
        ],
        ffmpeg_template="select='gt(scene,{threshold})',setpts=N/FRAME_RATE/TB",
        examples=[
            "scene_detect - Detect scene changes (default threshold)",
            "scene_detect:threshold=0.1 - Very sensitive scene detection",
            "scene_detect:threshold=0.5 - Only major scene changes",
        ],
        tags=["scene", "detect", "split", "cut", "auto", "boundary"],
    ))

    # Silence remove — strip silent audio segments
    registry.register(Skill(
        name="silence_remove",
        category=SkillCategory.AUDIO,
        description="Automatically remove silent segments from audio/video (great for podcasts, vlogs)",
        parameters=[
            SkillParameter(
                name="threshold",
                type=ParameterType.FLOAT,
                description="Silence threshold in dB (e.g. -30 = quiet, -50 = very quiet)",
                required=False,
                default=-30,
                min_value=-80,
                max_value=-10,
            ),
            SkillParameter(
                name="min_duration",
                type=ParameterType.FLOAT,
                description="Minimum silence duration to remove (seconds)",
                required=False,
                default=0.5,
                min_value=0.1,
                max_value=10.0,
            ),
        ],
        ffmpeg_template="silenceremove=start_periods=1:start_duration={min_duration}:start_threshold={threshold}dB:detection=peak",
        examples=[
            "silence_remove - Remove silences below -30dB",
            "silence_remove:threshold=-40,min_duration=1 - Remove longer quiet gaps",
        ],
        tags=["silence", "remove", "strip", "podcast", "vlog", "auto", "jump_cut"],
    ))

    # Time remap — variable speed with smooth ramping
    registry.register(Skill(
        name="time_remap",
        category=SkillCategory.TEMPORAL,
        description="Variable speed ramping — smoothly accelerate or decelerate playback",
        parameters=[
            SkillParameter(
                name="start_speed",
                type=ParameterType.FLOAT,
                description="Speed at the start of the clip (1.0 = normal)",
                required=False,
                default=1.0,
                min_value=0.1,
                max_value=10.0,
            ),
            SkillParameter(
                name="end_speed",
                type=ParameterType.FLOAT,
                description="Speed at the end of the clip (1.0 = normal)",
                required=False,
                default=0.25,
                min_value=0.1,
                max_value=10.0,
            ),
        ],
        ffmpeg_template="setpts=PTS*({start_speed}+({end_speed}-{start_speed})*T/5)",
        examples=[
            "time_remap:start_speed=1,end_speed=0.25 - Gradually slow to quarter speed",
            "time_remap:start_speed=0.5,end_speed=2 - Speed up from slow to fast",
        ],
        tags=["speed", "ramp", "variable", "ease", "acceleration", "deceleration"],
    ))
