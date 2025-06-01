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
            "crop:width=ih*9/16,height=ih",
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
            "crop:width=ih,height=ih",
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
