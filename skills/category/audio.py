"""Audio editing skills."""

from ..registry import SkillRegistry, Skill, SkillParameter, SkillCategory, ParameterType


def register_skills(registry: SkillRegistry) -> None:
    """Register audio skills with the registry."""

    # Volume skill
    registry.register(Skill(
        name="volume",
        category=SkillCategory.AUDIO,
        description="Adjust audio volume level",
        parameters=[
            SkillParameter(
                name="level",
                type=ParameterType.FLOAT,
                description="Volume multiplier (1.0 = no change, 2.0 = double)",
                required=False,
                default=1.5,
                min_value=0.0,
                max_value=10.0,
            ),
        ],
        examples=[
            "volume:level=1.5 - 50% louder",
            "volume:level=0.5 - 50% quieter",
            "volume:level=2.0 - Double volume",
        ],
        tags=["loud", "quiet", "gain", "level"],
    ))

    # Normalize skill
    registry.register(Skill(
        name="normalize",
        category=SkillCategory.AUDIO,
        description="Normalize audio levels for consistent volume",
        parameters=[],
        examples=[
            "normalize - Automatically adjust audio to standard levels",
        ],
        tags=["loudness", "level", "standard"],
    ))

    # Fade audio skill
    registry.register(Skill(
        name="fade_audio",
        category=SkillCategory.AUDIO,
        description="Add audio fade in/out",
        parameters=[
            SkillParameter(
                name="type",
                type=ParameterType.CHOICE,
                description="Fade type",
                required=False,
                default="in",
                choices=["in", "out"],
            ),
            SkillParameter(
                name="start",
                type=ParameterType.TIME,
                description="Start time of fade",
                required=False,
                default=0,
            ),
            SkillParameter(
                name="duration",
                type=ParameterType.TIME,
                description="Fade duration in seconds",
                required=False,
                default=1,
            ),
        ],
        examples=[
            "fade_audio:type=in,duration=2 - 2 second audio fade in",
            "fade_audio:type=out,start=55,duration=5 - Fade out last 5 seconds",
        ],
        tags=["transition", "silence"],
    ))

    # Remove audio skill
    registry.register(Skill(
        name="remove_audio",
        category=SkillCategory.AUDIO,
        description="Strip audio track from video",
        parameters=[],
        examples=[
            "remove_audio - Remove all audio, output video only",
        ],
        tags=["mute", "silent", "strip"],
    ))

    # Extract audio skill
    registry.register(Skill(
        name="extract_audio",
        category=SkillCategory.AUDIO,
        description="Export audio track only",
        parameters=[
            SkillParameter(
                name="format",
                type=ParameterType.CHOICE,
                description="Output audio format",
                required=False,
                default="mp3",
                choices=["mp3", "aac", "wav", "flac", "ogg"],
            ),
        ],
        examples=[
            "extract_audio:format=mp3 - Extract audio as MP3",
            "extract_audio:format=wav - Extract audio as WAV",
        ],
        tags=["export", "rip", "audio only"],
    ))

    # Audio pitch skill
    registry.register(Skill(
        name="pitch",
        category=SkillCategory.AUDIO,
        description="Change audio pitch without affecting speed",
        parameters=[
            SkillParameter(
                name="semitones",
                type=ParameterType.FLOAT,
                description="Pitch shift in semitones (-12 to 12)",
                required=False,
                default=2,
                min_value=-12,
                max_value=12,
            ),
        ],
        ffmpeg_template="asetrate=44100*2^({semitones}/12),aresample=44100",
        examples=[
            "pitch:semitones=2 - Higher pitch",
            "pitch:semitones=-3 - Lower pitch",
        ],
        tags=["tone", "frequency"],
    ))

    # Audio echo skill
    registry.register(Skill(
        name="echo",
        category=SkillCategory.AUDIO,
        description="Add echo effect to audio",
        parameters=[
            SkillParameter(
                name="delay",
                type=ParameterType.INT,
                description="Echo delay in milliseconds",
                required=False,
                default=500,
                min_value=50,
                max_value=2000,
            ),
            SkillParameter(
                name="decay",
                type=ParameterType.FLOAT,
                description="Echo decay (0.0-1.0)",
                required=False,
                default=0.5,
                min_value=0.0,
                max_value=1.0,
            ),
        ],
        ffmpeg_template="aecho=0.8:0.9:{delay}:{decay}",
        examples=[
            "echo:delay=300,decay=0.4 - Short echo",
            "echo:delay=1000,decay=0.6 - Long reverberant echo",
        ],
        tags=["reverb", "effect"],
    ))

    # Audio bass boost skill
    registry.register(Skill(
        name="bass",
        category=SkillCategory.AUDIO,
        description="Boost or reduce bass frequencies",
        parameters=[
            SkillParameter(
                name="gain",
                type=ParameterType.FLOAT,
                description="Bass gain in dB (-20 to 20)",
                required=False,
                default=6,
                min_value=-20,
                max_value=20,
            ),
            SkillParameter(
                name="frequency",
                type=ParameterType.INT,
                description="Center frequency in Hz",
                required=False,
                default=100,
                min_value=20,
                max_value=500,
            ),
        ],
        ffmpeg_template="bass=g={gain}:f={frequency}",
        examples=[
            "bass:gain=6 - Boost bass",
            "bass:gain=-3 - Reduce bass",
        ],
        tags=["eq", "low", "boost"],
    ))

    # Audio treble skill
    registry.register(Skill(
        name="treble",
        category=SkillCategory.AUDIO,
        description="Boost or reduce treble frequencies",
        parameters=[
            SkillParameter(
                name="gain",
                type=ParameterType.FLOAT,
                description="Treble gain in dB (-20 to 20)",
                required=False,
                default=4,
                min_value=-20,
                max_value=20,
            ),
            SkillParameter(
                name="frequency",
                type=ParameterType.INT,
                description="Center frequency in Hz",
                required=False,
                default=3000,
                min_value=1000,
                max_value=10000,
            ),
        ],
        ffmpeg_template="treble=g={gain}:f={frequency}",
        examples=[
            "treble:gain=4 - Boost highs",
            "treble:gain=-2 - Reduce highs",
        ],
        tags=["eq", "high", "bright"],
    ))

    # Audio compressor skill
    registry.register(Skill(
        name="compress_audio",
        category=SkillCategory.AUDIO,
        description="Apply dynamic range compression",
        parameters=[
            SkillParameter(
                name="threshold",
                type=ParameterType.FLOAT,
                description="Threshold in dB",
                required=False,
                default=-20,
                min_value=-60,
                max_value=0,
            ),
            SkillParameter(
                name="ratio",
                type=ParameterType.FLOAT,
                description="Compression ratio",
                required=False,
                default=4,
                min_value=1,
                max_value=20,
            ),
        ],
        ffmpeg_template="acompressor=threshold={threshold}dB:ratio={ratio}",
        examples=[
            "compress_audio:threshold=-15,ratio=3 - Light compression",
            "compress_audio:threshold=-25,ratio=8 - Heavy compression",
        ],
        tags=["dynamics", "limiter"],
    ))
