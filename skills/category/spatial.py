"""Spatial editing skills (resize, crop, rotate, etc.)."""

from ..registry import SkillRegistry, Skill, SkillParameter, SkillCategory, ParameterType


def register_skills(registry: SkillRegistry) -> None:
    """Register spatial skills with the registry."""

    # Resize skill
    registry.register(Skill(
        name="resize",
        category=SkillCategory.SPATIAL,
        description="Change video dimensions",
        parameters=[
            SkillParameter(
                name="width",
                type=ParameterType.INT,
                description="Target width in pixels (-1 to maintain aspect ratio)",
                required=False,
                default=1280,
            ),
            SkillParameter(
                name="height",
                type=ParameterType.INT,
                description="Target height in pixels (-1 to maintain aspect ratio)",
                required=False,
                default=720,
            ),
        ],
        examples=[
            "resize:width=1920,height=1080 - Full HD",
            "resize:width=1280,height=720 - HD 720p",
            "resize:width=-1,height=480 - 480p maintaining aspect",
            "resize:width=640,height=-1 - 640px wide maintaining aspect",
        ],
        tags=["scale", "dimensions", "resolution", "size"],
    ))

    # Crop skill
    registry.register(Skill(
        name="crop",
        category=SkillCategory.SPATIAL,
        description="Remove edges of frame",
        parameters=[
            SkillParameter(
                name="width",
                type=ParameterType.STRING,
                description="Output width (can be expression like 'iw/2')",
                required=True,
            ),
            SkillParameter(
                name="height",
                type=ParameterType.STRING,
                description="Output height (can be expression like 'ih/2')",
                required=True,
            ),
            SkillParameter(
                name="x",
                type=ParameterType.STRING,
                description="X offset (default: center)",
                required=False,
                default="(in_w-out_w)/2",
            ),
            SkillParameter(
                name="y",
                type=ParameterType.STRING,
                description="Y offset (default: center)",
                required=False,
                default="(in_h-out_h)/2",
            ),
        ],
        examples=[
            "crop:width=1280,height=720 - Crop to 1280x720 from center",
            "crop:width=in_w-100,height=in_h-100 - Remove 50px from each edge",
        ],
        tags=["cut", "frame", "trim"],
    ))

    # Pad skill
    registry.register(Skill(
        name="pad",
        category=SkillCategory.SPATIAL,
        description="Add borders/letterbox around video",
        parameters=[
            SkillParameter(
                name="width",
                type=ParameterType.STRING,
                description="Output width",
                required=True,
            ),
            SkillParameter(
                name="height",
                type=ParameterType.STRING,
                description="Output height",
                required=True,
            ),
            SkillParameter(
                name="x",
                type=ParameterType.STRING,
                description="X position of video (default: center)",
                required=False,
                default="(ow-iw)/2",
            ),
            SkillParameter(
                name="y",
                type=ParameterType.STRING,
                description="Y position of video (default: center)",
                required=False,
                default="(oh-ih)/2",
            ),
            SkillParameter(
                name="color",
                type=ParameterType.STRING,
                description="Padding color (name or hex)",
                required=False,
                default="black",
            ),
        ],
        examples=[
            "pad:width=1920,height=1080,color=black - Pad to 1080p with black bars",
            "pad:width=iw,height=iw*16/9 - Add letterbox for 16:9",
        ],
        tags=["border", "letterbox", "pillarbox", "bars"],
    ))

    # Rotate skill
    registry.register(Skill(
        name="rotate",
        category=SkillCategory.SPATIAL,
        description="Rotate video by angle",
        parameters=[
            SkillParameter(
                name="angle",
                type=ParameterType.INT,
                description="Rotation angle in degrees (90, -90, 180, or any angle)",
                required=False,
                default=90,
            ),
        ],
        examples=[
            "rotate:angle=90 - Rotate 90 degrees clockwise",
            "rotate:angle=-90 - Rotate 90 degrees counter-clockwise",
            "rotate:angle=180 - Rotate 180 degrees",
        ],
        tags=["turn", "orientation", "portrait", "landscape"],
    ))

    # Flip skill
    registry.register(Skill(
        name="flip",
        category=SkillCategory.SPATIAL,
        description="Mirror video horizontally or vertically",
        parameters=[
            SkillParameter(
                name="direction",
                type=ParameterType.CHOICE,
                description="Flip direction",
                required=False,
                default="horizontal",
                choices=["horizontal", "vertical"],
            ),
        ],
        examples=[
            "flip:direction=horizontal - Mirror left-right",
            "flip:direction=vertical - Mirror top-bottom",
        ],
        tags=["mirror", "reflect"],
    ))

    # Aspect ratio skill
    registry.register(Skill(
        name="aspect",
        category=SkillCategory.SPATIAL,
        description="Change aspect ratio with letterbox/pillarbox",
        parameters=[
            SkillParameter(
                name="ratio",
                type=ParameterType.STRING,
                description="Target aspect ratio (e.g., '16:9', '4:3', '2.35:1')",
                required=False,
                default="16:9",
            ),
            SkillParameter(
                name="mode",
                type=ParameterType.CHOICE,
                description="How to handle aspect change",
                required=False,
                default="pad",
                choices=["pad", "crop", "stretch"],
            ),
            SkillParameter(
                name="color",
                type=ParameterType.STRING,
                description="Padding color for letterbox",
                required=False,
                default="black",
            ),
        ],
        examples=[
            "aspect:ratio=16:9,mode=pad - Letterbox to 16:9",
            "aspect:ratio=9:16,mode=crop - Crop to vertical 9:16 for TikTok/Reels",
            "aspect:ratio=1:1,mode=crop - Crop to square for Instagram",
            "aspect:ratio=2.35:1 - Cinematic widescreen",
        ],
        tags=["widescreen", "letterbox", "format", "vertical", "portrait",
              "landscape", "tiktok", "reels", "shorts", "instagram", "9:16",
              "16:9", "4:3", "1:1", "square", "aspect"],
    ))

    # Auto crop — detect and remove black borders
    registry.register(Skill(
        name="auto_crop",
        category=SkillCategory.SPATIAL,
        description="Automatically detect and remove black borders/letterboxing from video",
        parameters=[
            SkillParameter(
                name="threshold",
                type=ParameterType.INT,
                description="Black detection threshold (higher = more aggressive, 0-255)",
                required=False,
                default=24,
                min_value=0,
                max_value=255,
            ),
        ],
        ffmpeg_template="cropdetect=limit={threshold}:round=2:reset=0,crop",
        examples=[
            "auto_crop - Remove black borders automatically",
            "auto_crop:threshold=40 - More aggressive border detection",
        ],
        tags=["crop", "black", "borders", "letterbox", "detect", "auto", "remove"],
    ))

    # Scale 2x — quick upscale with quality algorithm
    registry.register(Skill(
        name="scale_2x",
        category=SkillCategory.SPATIAL,
        description="Upscale video by 2x (or custom factor) with high-quality scaling algorithm",
        parameters=[
            SkillParameter(
                name="factor",
                type=ParameterType.INT,
                description="Scale factor (2 = double, 4 = quadruple)",
                required=False,
                default=2,
                min_value=1,
                max_value=4,
            ),
            SkillParameter(
                name="algorithm",
                type=ParameterType.CHOICE,
                description="Scaling algorithm (lanczos = sharpest, bicubic = smooth)",
                required=False,
                default="lanczos",
                choices=["lanczos", "bicubic", "bilinear", "spline"],
            ),
        ],
        ffmpeg_template="scale=iw*{factor}:ih*{factor}:flags={algorithm}",
        examples=[
            "scale_2x - Double resolution with Lanczos",
            "scale_2x:factor=4,algorithm=bicubic - 4x upscale with bicubic",
        ],
        tags=["upscale", "enlarge", "double", "super", "resolution", "enhance", "2x", "4x"],
    ))
