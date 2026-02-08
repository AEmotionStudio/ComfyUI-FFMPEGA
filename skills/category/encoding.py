"""Encoding skills (compress, convert, quality settings)."""

from ..registry import SkillRegistry, Skill, SkillParameter, SkillCategory, ParameterType


def register_skills(registry: SkillRegistry) -> None:
    """Register encoding skills with the registry."""

    # Compress skill
    registry.register(Skill(
        name="compress",
        category=SkillCategory.ENCODING,
        description="Reduce file size through compression",
        parameters=[
            SkillParameter(
                name="preset",
                type=ParameterType.CHOICE,
                description="Compression level",
                required=False,
                default="medium",
                choices=["light", "medium", "heavy"],
            ),
        ],
        examples=[
            "compress:preset=light - Slight compression, good quality",
            "compress:preset=medium - Balanced compression",
            "compress:preset=heavy - Maximum compression, lower quality",
        ],
        tags=["size", "small", "reduce", "web"],
    ))

    # Convert skill
    registry.register(Skill(
        name="convert",
        category=SkillCategory.ENCODING,
        description="Change video codec",
        parameters=[
            SkillParameter(
                name="codec",
                type=ParameterType.CHOICE,
                description="Target video codec",
                required=False,
                default="h264",
                choices=["h264", "h265", "vp9", "av1", "prores"],
            ),
        ],
        examples=[
            "convert:codec=h264 - Convert to H.264 (most compatible)",
            "convert:codec=h265 - Convert to HEVC (smaller files)",
            "convert:codec=vp9 - Convert to VP9 (web optimized)",
            "convert:codec=prores - Convert to ProRes (editing)",
        ],
        tags=["codec", "transcode", "format"],
    ))

    # Bitrate skill
    registry.register(Skill(
        name="bitrate",
        category=SkillCategory.ENCODING,
        description="Set specific bitrate for encoding",
        parameters=[
            SkillParameter(
                name="video",
                type=ParameterType.STRING,
                description="Video bitrate (e.g., '5M', '2000k')",
                required=False,
            ),
            SkillParameter(
                name="audio",
                type=ParameterType.STRING,
                description="Audio bitrate (e.g., '192k', '320k')",
                required=False,
            ),
        ],
        examples=[
            "bitrate:video=5M - 5 Mbps video",
            "bitrate:video=2M,audio=128k - 2 Mbps video, 128k audio",
        ],
        tags=["quality", "size", "rate"],
    ))

    # Quality skill
    registry.register(Skill(
        name="quality",
        category=SkillCategory.ENCODING,
        description="Set quality level using CRF",
        parameters=[
            SkillParameter(
                name="crf",
                type=ParameterType.INT,
                description="CRF value (0=lossless, 23=default, 51=worst)",
                required=False,
                default=23,
                min_value=0,
                max_value=51,
            ),
            SkillParameter(
                name="preset",
                type=ParameterType.CHOICE,
                description="Encoding speed preset",
                required=False,
                default="medium",
                choices=["ultrafast", "superfast", "veryfast", "faster",
                         "fast", "medium", "slow", "slower", "veryslow"],
            ),
        ],
        examples=[
            "quality:crf=18 - High quality",
            "quality:crf=23 - Standard quality",
            "quality:crf=28 - Lower quality, smaller file",
            "quality:crf=18,preset=slow - High quality, better compression",
        ],
        tags=["crf", "level"],
    ))

    # Container skill
    registry.register(Skill(
        name="container",
        category=SkillCategory.ENCODING,
        description="Change container format",
        parameters=[
            SkillParameter(
                name="format",
                type=ParameterType.CHOICE,
                description="Container format",
                required=False,
                default="mp4",
                choices=["mp4", "mkv", "webm", "mov", "avi", "gif"],
            ),
        ],
        examples=[
            "container:format=mp4 - MP4 (most compatible)",
            "container:format=mkv - MKV (feature-rich)",
            "container:format=webm - WebM (web optimized)",
            "container:format=gif - Animated GIF",
        ],
        tags=["format", "extension", "wrapper"],
    ))

    # Web optimize skill
    registry.register(Skill(
        name="web_optimize",
        category=SkillCategory.ENCODING,
        description="Optimize video for web streaming",
        parameters=[
            SkillParameter(
                name="faststart",
                type=ParameterType.BOOL,
                description="Move moov atom to start for fast streaming",
                required=False,
                default=True,
            ),
        ],
        ffmpeg_template="-movflags +faststart",
        examples=[
            "web_optimize - Optimize for web playback",
        ],
        tags=["streaming", "faststart", "moov"],
    ))

    # Two-pass encoding skill
    registry.register(Skill(
        name="two_pass",
        category=SkillCategory.ENCODING,
        description="Enable two-pass encoding for better quality at target bitrate",
        parameters=[
            SkillParameter(
                name="target_bitrate",
                type=ParameterType.STRING,
                description="Target bitrate (e.g., '4M', '2500k')",
                required=True,
            ),
        ],
        examples=[
            "two_pass:target_bitrate=4M - Two-pass at 4 Mbps",
        ],
        tags=["quality", "bitrate", "vbr"],
    ))

    # Audio codec skill
    registry.register(Skill(
        name="audio_codec",
        category=SkillCategory.ENCODING,
        description="Set audio codec and quality",
        parameters=[
            SkillParameter(
                name="codec",
                type=ParameterType.CHOICE,
                description="Audio codec",
                required=False,
                default="aac",
                choices=["aac", "mp3", "opus", "flac", "copy"],
            ),
            SkillParameter(
                name="bitrate",
                type=ParameterType.STRING,
                description="Audio bitrate",
                required=False,
                default="128k",
            ),
        ],
        examples=[
            "audio_codec:codec=aac,bitrate=192k - AAC at 192kbps",
            "audio_codec:codec=copy - Copy audio without re-encoding",
        ],
        tags=["audio", "format", "quality"],
    ))

    # Pixel format skill
    registry.register(Skill(
        name="pixel_format",
        category=SkillCategory.ENCODING,
        description="Set output pixel format",
        parameters=[
            SkillParameter(
                name="format",
                type=ParameterType.CHOICE,
                description="Pixel format",
                required=False,
                default="yuv420p",
                choices=["yuv420p", "yuv422p", "yuv444p", "rgb24"],
            ),
        ],
        ffmpeg_template="-pix_fmt {format}",
        examples=[
            "pixel_format:format=yuv420p - Standard format (most compatible)",
            "pixel_format:format=yuv444p - Higher quality chroma",
        ],
        tags=["color", "chroma", "subsampling"],
    ))

    # Hardware acceleration skill
    registry.register(Skill(
        name="hwaccel",
        category=SkillCategory.ENCODING,
        description="Enable hardware acceleration for encoding",
        parameters=[
            SkillParameter(
                name="type",
                type=ParameterType.CHOICE,
                description="Hardware acceleration type",
                required=False,
                default="auto",
                choices=["auto", "cuda", "vaapi", "qsv", "videotoolbox"],
            ),
        ],
        examples=[
            "hwaccel:type=cuda - NVIDIA GPU acceleration",
            "hwaccel:type=vaapi - Intel/AMD VA-API",
            "hwaccel:type=qsv - Intel Quick Sync",
        ],
        tags=["gpu", "fast", "nvidia", "intel", "amd"],
    ))
