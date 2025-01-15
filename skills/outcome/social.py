"""Social media optimization skills."""

from ..registry import SkillRegistry, Skill, SkillParameter, SkillCategory, ParameterType


def register_skills(registry: SkillRegistry) -> None:
    """Register social media skills with the registry."""

    # Social vertical skill
    registry.register(Skill(
        name="social_vertical",
        category=SkillCategory.OUTCOME,
        description="Optimize for vertical social media (TikTok, Reels, Shorts)",
        parameters=[
            SkillParameter(
                name="platform",
                type=ParameterType.CHOICE,
                description="Target platform",
                required=False,
                default="tiktok",
                choices=["tiktok", "reels", "shorts", "stories"],
            ),
        ],
        pipeline=[
            "crop:width=iw,height=iw*16/9",
            "resize:width=1080,height=1920",
            "compress:preset=medium",
        ],
        examples=[
            "social_vertical - Vertical 9:16 for TikTok/Reels",
            "social_vertical:platform=stories - Optimized for stories",
        ],
        tags=["tiktok", "instagram", "reels", "shorts", "vertical", "portrait"],
    ))

    # Social square skill
    registry.register(Skill(
        name="social_square",
        category=SkillCategory.OUTCOME,
        description="Optimize for square social media posts",
        parameters=[],
        pipeline=[
            "crop:width=min(iw\\,ih),height=min(iw\\,ih)",
            "resize:width=1080,height=1080",
            "compress:preset=medium",
        ],
        examples=[
            "social_square - Square 1:1 for Instagram feed",
        ],
        tags=["instagram", "facebook", "square", "1:1"],
    ))

    # YouTube skill
    registry.register(Skill(
        name="youtube",
        category=SkillCategory.OUTCOME,
        description="Optimize for YouTube upload",
        parameters=[
            SkillParameter(
                name="quality",
                type=ParameterType.CHOICE,
                description="Target quality",
                required=False,
                default="1080p",
                choices=["720p", "1080p", "1440p", "4k"],
            ),
        ],
        pipeline=[
            "resize:width=1920,height=1080",
            "quality:crf=18,preset=slow",
            "audio_codec:codec=aac,bitrate=192k",
            "web_optimize",
        ],
        examples=[
            "youtube - Optimized for YouTube at 1080p",
            "youtube:quality=4k - 4K YouTube upload",
        ],
        tags=["youtube", "upload", "streaming", "hd"],
    ))

    # Twitter/X skill
    registry.register(Skill(
        name="twitter",
        category=SkillCategory.OUTCOME,
        description="Optimize for Twitter/X video",
        parameters=[],
        pipeline=[
            "resize:width=1280,height=720",
            "compress:preset=medium",
            "trim:duration=140",
        ],
        examples=[
            "twitter - Optimized for Twitter (max 2:20)",
        ],
        tags=["twitter", "x", "social", "short"],
    ))

    # GIF export skill
    registry.register(Skill(
        name="gif",
        category=SkillCategory.OUTCOME,
        description="Convert video to animated GIF",
        parameters=[
            SkillParameter(
                name="width",
                type=ParameterType.INT,
                description="GIF width (height auto)",
                required=False,
                default=480,
                min_value=100,
                max_value=800,
            ),
            SkillParameter(
                name="fps",
                type=ParameterType.INT,
                description="Frames per second",
                required=False,
                default=15,
                min_value=5,
                max_value=30,
            ),
        ],
        examples=[
            "gif - Convert to GIF (480px, 15fps)",
            "gif:width=320,fps=10 - Smaller GIF",
        ],
        tags=["gif", "animated", "loop", "meme"],
    ))

    # Thumbnail skill
    registry.register(Skill(
        name="thumbnail",
        category=SkillCategory.OUTCOME,
        description="Generate video thumbnail",
        parameters=[
            SkillParameter(
                name="time",
                type=ParameterType.TIME,
                description="Timestamp for thumbnail",
                required=False,
                default=0,
            ),
            SkillParameter(
                name="width",
                type=ParameterType.INT,
                description="Thumbnail width",
                required=False,
                default=1280,
            ),
        ],
        examples=[
            "thumbnail - Extract thumbnail from start",
            "thumbnail:time=30 - Thumbnail at 30 seconds",
        ],
        tags=["image", "preview", "poster", "cover"],
    ))

    # Caption space skill
    registry.register(Skill(
        name="caption_space",
        category=SkillCategory.OUTCOME,
        description="Add space for captions/text overlay",
        parameters=[
            SkillParameter(
                name="position",
                type=ParameterType.CHOICE,
                description="Space position",
                required=False,
                default="bottom",
                choices=["top", "bottom"],
            ),
            SkillParameter(
                name="height",
                type=ParameterType.INT,
                description="Space height in pixels",
                required=False,
                default=200,
                min_value=50,
                max_value=500,
            ),
            SkillParameter(
                name="color",
                type=ParameterType.STRING,
                description="Background color",
                required=False,
                default="black",
            ),
        ],
        examples=[
            "caption_space - Add caption area at bottom",
            "caption_space:position=top,height=100 - Space at top",
        ],
        tags=["text", "subtitle", "overlay", "space"],
    ))

    # Watermark skill
    registry.register(Skill(
        name="watermark",
        category=SkillCategory.OUTCOME,
        description="Add watermark/logo to video",
        parameters=[
            SkillParameter(
                name="image",
                type=ParameterType.STRING,
                description="Path to watermark image",
                required=True,
            ),
            SkillParameter(
                name="position",
                type=ParameterType.CHOICE,
                description="Watermark position",
                required=False,
                default="bottom_right",
                choices=["top_left", "top_right", "bottom_left", "bottom_right", "center"],
            ),
            SkillParameter(
                name="opacity",
                type=ParameterType.FLOAT,
                description="Watermark opacity (0-1)",
                required=False,
                default=0.5,
                min_value=0.1,
                max_value=1.0,
            ),
            SkillParameter(
                name="scale",
                type=ParameterType.FLOAT,
                description="Watermark scale factor",
                required=False,
                default=0.15,
                min_value=0.05,
                max_value=0.5,
            ),
        ],
        examples=[
            "watermark:image=logo.png - Add logo watermark",
            "watermark:image=logo.png,position=top_left,opacity=0.3 - Subtle top-left",
        ],
        tags=["logo", "brand", "overlay", "copyright"],
    ))

    # Intro/outro skill
    registry.register(Skill(
        name="intro_outro",
        category=SkillCategory.OUTCOME,
        description="Add intro and/or outro segments",
        parameters=[
            SkillParameter(
                name="intro",
                type=ParameterType.STRING,
                description="Path to intro video",
                required=False,
            ),
            SkillParameter(
                name="outro",
                type=ParameterType.STRING,
                description="Path to outro video",
                required=False,
            ),
        ],
        examples=[
            "intro_outro:intro=intro.mp4 - Add intro only",
            "intro_outro:intro=intro.mp4,outro=outro.mp4 - Add both",
        ],
        tags=["concat", "join", "branding"],
    ))
