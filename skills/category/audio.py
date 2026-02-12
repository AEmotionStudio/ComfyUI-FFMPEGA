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

    # Echo/reverb skill
    registry.register(Skill(
        name="echo",
        category=SkillCategory.AUDIO,
        description="Add echo/reverb effect to audio",
        parameters=[
            SkillParameter(
                name="delay",
                type=ParameterType.INT,
                description="Echo delay in milliseconds",
                required=False,
                default=500,
                min_value=50,
                max_value=5000,
            ),
            SkillParameter(
                name="decay",
                type=ParameterType.FLOAT,
                description="Echo decay (0 = no echo, 1 = full echo)",
                required=False,
                default=0.5,
                min_value=0.1,
                max_value=0.9,
            ),
        ],
        ffmpeg_template="aecho=0.8:0.88:{delay}:{decay}",
        examples=[
            "echo - Standard echo",
            "echo:delay=1000,decay=0.3 - Long subtle echo",
            "echo:delay=200,decay=0.7 - Short strong echo",
        ],
        tags=["reverb", "echo", "delay", "space", "room"],
    ))

    # Equalizer skill
    registry.register(Skill(
        name="equalizer",
        category=SkillCategory.AUDIO,
        description="Apply equalizer band adjustment",
        parameters=[
            SkillParameter(
                name="freq",
                type=ParameterType.INT,
                description="Center frequency in Hz",
                required=False,
                default=1000,
                min_value=20,
                max_value=20000,
            ),
            SkillParameter(
                name="width",
                type=ParameterType.INT,
                description="Band width in Hz",
                required=False,
                default=200,
                min_value=10,
                max_value=5000,
            ),
            SkillParameter(
                name="gain",
                type=ParameterType.FLOAT,
                description="Gain in dB (-20 to 20)",
                required=False,
                default=5.0,
                min_value=-20.0,
                max_value=20.0,
            ),
        ],
        ffmpeg_template="equalizer=f={freq}:width_type=h:width={width}:g={gain}",
        examples=[
            "equalizer:freq=100,gain=6 - Boost bass frequencies",
            "equalizer:freq=8000,gain=-3 - Reduce treble",
        ],
        tags=["eq", "frequency", "band", "boost", "cut"],
    ))

    # Stereo swap skill
    registry.register(Skill(
        name="stereo_swap",
        category=SkillCategory.AUDIO,
        description="Swap left and right audio channels",
        parameters=[],
        ffmpeg_template="channelmap=1|0",
        examples=[
            "stereo_swap - Swap left and right channels",
        ],
        tags=["stereo", "channels", "swap", "left", "right"],
    ))

    # Mono conversion skill
    registry.register(Skill(
        name="mono",
        category=SkillCategory.AUDIO,
        description="Convert audio to mono (single channel)",
        parameters=[],
        ffmpeg_template="pan=mono|c0=0.5*c0+0.5*c1",
        examples=[
            "mono - Convert stereo to mono",
        ],
        tags=["mono", "single", "channel", "downmix"],
    ))

    # Audio speed skill (audio only, no video change)
    registry.register(Skill(
        name="audio_speed",
        category=SkillCategory.AUDIO,
        description="Change audio speed/tempo without affecting video",
        parameters=[
            SkillParameter(
                name="factor",
                type=ParameterType.FLOAT,
                description="Speed factor (0.5 = half, 2.0 = double)",
                required=False,
                default=1.5,
                min_value=0.5,
                max_value=2.0,
            ),
        ],
        ffmpeg_template="atempo={factor}",
        examples=[
            "audio_speed:factor=1.5 - Speed up audio 1.5x",
            "audio_speed:factor=0.75 - Slow down audio",
        ],
        tags=["tempo", "speed", "fast", "slow", "pitch"],
    ))

    # Chorus effect skill
    registry.register(Skill(
        name="chorus",
        category=SkillCategory.AUDIO,
        description="Add chorus effect to audio (thickens/enriches sound)",
        parameters=[
            SkillParameter(
                name="depth",
                type=ParameterType.FLOAT,
                description="Chorus depth (modulation amount)",
                required=False,
                default=0.4,
                min_value=0.1,
                max_value=1.0,
            ),
        ],
        ffmpeg_template="chorus=0.7:0.9:55:{depth}:0.25:2",
        examples=[
            "chorus - Standard chorus effect",
            "chorus:depth=0.8 - Deep chorus",
        ],
        tags=["chorus", "thick", "rich", "vocal", "wide"],
    ))

    # Flanger effect skill
    registry.register(Skill(
        name="flanger",
        category=SkillCategory.AUDIO,
        description="Add flanger effect to audio (sweeping jet sound)",
        parameters=[
            SkillParameter(
                name="speed",
                type=ParameterType.FLOAT,
                description="Flanger speed in Hz",
                required=False,
                default=0.5,
                min_value=0.1,
                max_value=10.0,
            ),
            SkillParameter(
                name="depth",
                type=ParameterType.FLOAT,
                description="Flanger depth",
                required=False,
                default=2.0,
                min_value=0.1,
                max_value=10.0,
            ),
        ],
        ffmpeg_template="flanger=speed={speed}:depth={depth}",
        examples=[
            "flanger - Standard flanger",
            "flanger:speed=1.0,depth=5 - Intense flanger",
        ],
        tags=["flanger", "sweep", "jet", "modulation", "psychedelic"],
    ))

    # Low pass filter skill
    registry.register(Skill(
        name="lowpass",
        category=SkillCategory.AUDIO,
        description="Apply low pass filter (removes high frequencies, muffled sound)",
        parameters=[
            SkillParameter(
                name="freq",
                type=ParameterType.INT,
                description="Cutoff frequency in Hz",
                required=False,
                default=1000,
                min_value=100,
                max_value=20000,
            ),
        ],
        ffmpeg_template="lowpass=f={freq}",
        examples=[
            "lowpass - Muffle audio (1kHz cutoff)",
            "lowpass:freq=500 - Very muffled (behind wall effect)",
            "lowpass:freq=3000 - Slight warmth",
        ],
        tags=["filter", "muffle", "warm", "telephone", "lo-fi"],
    ))

    # High pass filter skill
    registry.register(Skill(
        name="highpass",
        category=SkillCategory.AUDIO,
        description="Apply high pass filter (removes low frequencies, thin sound)",
        parameters=[
            SkillParameter(
                name="freq",
                type=ParameterType.INT,
                description="Cutoff frequency in Hz",
                required=False,
                default=300,
                min_value=20,
                max_value=10000,
            ),
        ],
        ffmpeg_template="highpass=f={freq}",
        examples=[
            "highpass - Remove rumble (300Hz cutoff)",
            "highpass:freq=1000 - Tinny/telephone effect",
            "highpass:freq=80 - Subtle rumble removal",
        ],
        tags=["filter", "thin", "rumble", "clean", "telephone"],
    ))

    # Audio reverse skill
    registry.register(Skill(
        name="audio_reverse",
        category=SkillCategory.AUDIO,
        description="Reverse the audio track",
        parameters=[],
        ffmpeg_template="areverse",
        examples=[
            "audio_reverse - Reverse audio playback",
        ],
        tags=["reverse", "backwards", "creepy"],
    ))

    # Noise reduction — FFT-based audio denoising
    registry.register(Skill(
        name="noise_reduction",
        category=SkillCategory.AUDIO,
        description="Remove background noise from audio (hiss, hum, ambient noise)",
        parameters=[
            SkillParameter(
                name="floor",
                type=ParameterType.FLOAT,
                description="Noise floor in dB (lower = more aggressive, e.g. -40)",
                required=False,
                default=-30,
                min_value=-80,
                max_value=-10,
            ),
            SkillParameter(
                name="amount",
                type=ParameterType.FLOAT,
                description="Noise reduction amount in dB (higher = stronger)",
                required=False,
                default=12,
                min_value=1,
                max_value=50,
            ),
        ],
        ffmpeg_template="afftdn=nf={floor}:nr={amount}:nt=w",
        examples=[
            "noise_reduction - Standard background noise removal",
            "noise_reduction:floor=-40,amount=30 - Aggressive noise removal",
            "noise_reduction:floor=-25,amount=6 - Gentle cleanup",
        ],
        tags=["noise", "denoise", "clean", "hiss", "hum", "background", "fft"],
    ))

    # Audio crossfade
    registry.register(Skill(
        name="audio_crossfade",
        category=SkillCategory.AUDIO,
        description="Smooth audio crossfade transition between clips",
        parameters=[
            SkillParameter(
                name="duration",
                type=ParameterType.FLOAT,
                description="Crossfade duration in seconds",
                required=False,
                default=2.0,
                min_value=0.1,
                max_value=30.0,
            ),
            SkillParameter(
                name="curve",
                type=ParameterType.CHOICE,
                description="Fade curve shape",
                required=False,
                default="tri",
                choices=["tri", "exp", "log", "par", "qua", "squ", "nofade"],
            ),
        ],
        # acrossfade requires two audio inputs; handled in composer.py via filter_complex
        examples=[
            "audio_crossfade - 2 second triangle crossfade",
            "audio_crossfade:duration=5,curve=exp - 5s exponential crossfade",
        ],
        tags=["crossfade", "transition", "blend", "smooth", "mix"],
    ))

    # Replace audio — swap the audio track
    registry.register(Skill(
        name="replace_audio",
        category=SkillCategory.AUDIO,
        description="Replace video's audio with audio from another file (uses extra_inputs)",
        parameters=[],
        # replace_audio needs duplicate -map flags; handled in composer.py to avoid dedup
        examples=[
            "replace_audio - Replace audio track with second input's audio",
        ],
        tags=["swap", "replace", "dub", "music", "voiceover"],
    ))

    # Audio delay — sync offset correction
    registry.register(Skill(
        name="audio_delay",
        category=SkillCategory.AUDIO,
        description="Delay audio by a fixed amount (fix audio/video sync issues)",
        parameters=[
            SkillParameter(
                name="ms",
                type=ParameterType.INT,
                description="Delay in milliseconds (positive = delay audio, negative not supported)",
                required=False,
                default=200,
                min_value=1,
                max_value=10000,
            ),
        ],
        ffmpeg_template="adelay={ms}|{ms}",
        examples=[
            "audio_delay:ms=100 - Delay audio by 100ms",
            "audio_delay:ms=500 - Delay audio by half a second",
        ],
        tags=["delay", "sync", "offset", "lip", "latency", "fix"],
    ))

    # Ducking — lower music volume when voice is present
    registry.register(Skill(
        name="ducking",
        category=SkillCategory.AUDIO,
        description="Auto-duck music volume when voice/speech is detected (sidechain compression)",
        parameters=[
            SkillParameter(
                name="threshold",
                type=ParameterType.FLOAT,
                description="Voice detection threshold in dB",
                required=False,
                default=-30,
                min_value=-60,
                max_value=-5,
            ),
            SkillParameter(
                name="ratio",
                type=ParameterType.FLOAT,
                description="Compression ratio when voice detected",
                required=False,
                default=6,
                min_value=2,
                max_value=20,
            ),
            SkillParameter(
                name="release",
                type=ParameterType.FLOAT,
                description="Release time in seconds (how fast music returns)",
                required=False,
                default=0.5,
                min_value=0.05,
                max_value=5.0,
            ),
        ],
        ffmpeg_template="compand=attacks=0.05:decays={release}:points=-80/-80|{threshold}/{threshold}|0/-{ratio}|20/-{ratio}",
        examples=[
            "ducking - Auto-lower music during speech",
            "ducking:threshold=-25,ratio=8 - Aggressive ducking",
        ],
        tags=["duck", "sidechain", "compress", "voice", "speech", "music", "podcast"],
    ))

    # Dereverb — remove room echo / reverb
    registry.register(Skill(
        name="dereverb",
        category=SkillCategory.AUDIO,
        description="Reduce room echo and reverb from audio (dry up the sound)",
        parameters=[
            SkillParameter(
                name="amount",
                type=ParameterType.FLOAT,
                description="Dereverb strength in dB (higher = more aggressive)",
                required=False,
                default=12,
                min_value=1,
                max_value=50,
            ),
        ],
        ffmpeg_template="highpass=f=80,lowpass=f=12000,afftdn=nf=-20:nr={amount}:nt=w",
        examples=[
            "dereverb - Standard room echo removal",
            "dereverb:amount=30 - Aggressive reverb removal",
        ],
        tags=["reverb", "echo", "room", "dry", "clean", "voice"],
    ))

    # Split audio — isolate left/right channel
    registry.register(Skill(
        name="split_audio",
        category=SkillCategory.AUDIO,
        description="Extract a specific audio channel (left or right) from stereo audio",
        parameters=[
            SkillParameter(
                name="channel",
                type=ParameterType.CHOICE,
                description="Which channel to extract",
                required=False,
                default="FL",
                choices=["FL", "FR"],
            ),
        ],
        ffmpeg_template="pan=mono|c0={channel}",
        examples=[
            "split_audio - Extract left channel",
            "split_audio:channel=FR - Extract right channel",
        ],
        tags=["channel", "mono", "left", "right", "stereo", "isolate", "split"],
    ))

    # Audio normalize loudness — EBU R128 standard
    registry.register(Skill(
        name="audio_normalize_loudness",
        category=SkillCategory.AUDIO,
        description="Normalize audio loudness to broadcast standard (EBU R128 / -14 LUFS for streaming)",
        parameters=[
            SkillParameter(
                name="target",
                type=ParameterType.FLOAT,
                description="Target integrated loudness in LUFS (-24 = broadcast, -14 = streaming)",
                required=False,
                default=-14,
                min_value=-30,
                max_value=-5,
            ),
            SkillParameter(
                name="tp",
                type=ParameterType.FLOAT,
                description="Maximum true peak in dBTP",
                required=False,
                default=-1.0,
                min_value=-5.0,
                max_value=0.0,
            ),
        ],
        ffmpeg_template="loudnorm=I={target}:TP={tp}:LRA=11",
        examples=[
            "audio_normalize_loudness - Normalize to -14 LUFS (streaming standard)",
            "audio_normalize_loudness:target=-24 - Broadcast standard (-24 LUFS)",
        ],
        tags=["loudness", "lufs", "ebu", "r128", "broadcast", "normalize", "streaming"],
    ))
