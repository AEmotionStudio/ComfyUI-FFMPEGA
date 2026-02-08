"""Visual editing skills (color, effects, filters)."""

from ..registry import SkillRegistry, Skill, SkillParameter, SkillCategory, ParameterType


def register_skills(registry: SkillRegistry) -> None:
    """Register visual skills with the registry."""

    # Brightness skill
    registry.register(Skill(
        name="brightness",
        category=SkillCategory.VISUAL,
        description="Adjust video brightness",
        parameters=[
            SkillParameter(
                name="value",
                type=ParameterType.FLOAT,
                description="Brightness adjustment (-1.0 to 1.0, 0 = no change)",
                required=False,
                default=0.1,
                min_value=-1.0,
                max_value=1.0,
            ),
        ],
        examples=[
            "brightness:value=0.2 - Slightly brighter",
            "brightness:value=-0.1 - Slightly darker",
        ],
        tags=["light", "dark", "exposure"],
    ))

    # Contrast skill
    registry.register(Skill(
        name="contrast",
        category=SkillCategory.VISUAL,
        description="Adjust video contrast",
        parameters=[
            SkillParameter(
                name="value",
                type=ParameterType.FLOAT,
                description="Contrast multiplier (1.0 = no change)",
                required=False,
                default=1.2,
                min_value=0.0,
                max_value=3.0,
            ),
        ],
        examples=[
            "contrast:value=1.2 - Higher contrast",
            "contrast:value=0.8 - Lower contrast",
        ],
        tags=["pop", "flat", "dynamic"],
    ))

    # Saturation skill
    registry.register(Skill(
        name="saturation",
        category=SkillCategory.VISUAL,
        description="Adjust color saturation",
        parameters=[
            SkillParameter(
                name="value",
                type=ParameterType.FLOAT,
                description="Saturation multiplier (0 = grayscale, 1.0 = no change)",
                required=False,
                default=1.3,
                min_value=0.0,
                max_value=3.0,
            ),
        ],
        examples=[
            "saturation:value=1.3 - More vibrant colors",
            "saturation:value=0.7 - Muted colors",
            "saturation:value=0 - Black and white",
        ],
        tags=["color", "vibrant", "muted", "grayscale", "bw"],
    ))

    # Hue skill
    registry.register(Skill(
        name="hue",
        category=SkillCategory.VISUAL,
        description="Shift color hue",
        parameters=[
            SkillParameter(
                name="value",
                type=ParameterType.FLOAT,
                description="Hue shift in degrees (-180 to 180)",
                required=False,
                default=15,
                min_value=-180,
                max_value=180,
            ),
        ],
        examples=[
            "hue:value=30 - Warm shift",
            "hue:value=-30 - Cool shift",
        ],
        tags=["color", "tint", "shift"],
    ))

    # Sharpen skill
    registry.register(Skill(
        name="sharpen",
        category=SkillCategory.VISUAL,
        description="Increase image sharpness",
        parameters=[
            SkillParameter(
                name="amount",
                type=ParameterType.FLOAT,
                description="Sharpening amount (0.5 = subtle, 1.5 = strong)",
                required=False,
                default=1.0,
                min_value=0.1,
                max_value=3.0,
            ),
        ],
        examples=[
            "sharpen:amount=1.0 - Standard sharpening",
            "sharpen:amount=0.5 - Subtle sharpening",
        ],
        tags=["crisp", "detail", "clarity"],
    ))

    # Blur skill
    registry.register(Skill(
        name="blur",
        category=SkillCategory.VISUAL,
        description="Apply blur effect",
        parameters=[
            SkillParameter(
                name="radius",
                type=ParameterType.INT,
                description="Blur radius (higher = more blur)",
                required=False,
                default=5,
                min_value=1,
                max_value=50,
            ),
        ],
        examples=[
            "blur:radius=3 - Slight blur",
            "blur:radius=10 - Strong blur",
        ],
        tags=["soft", "smooth", "defocus"],
    ))

    # Denoise skill
    registry.register(Skill(
        name="denoise",
        category=SkillCategory.VISUAL,
        description="Reduce video noise",
        parameters=[
            SkillParameter(
                name="strength",
                type=ParameterType.CHOICE,
                description="Denoise strength",
                required=False,
                default="medium",
                choices=["light", "medium", "strong"],
            ),
        ],
        examples=[
            "denoise:strength=light - Subtle noise reduction",
            "denoise:strength=strong - Aggressive noise reduction",
        ],
        tags=["grain", "clean", "smooth"],
    ))

    # Vignette skill
    registry.register(Skill(
        name="vignette",
        category=SkillCategory.VISUAL,
        description="Add vignette effect (darkened edges)",
        parameters=[
            SkillParameter(
                name="intensity",
                type=ParameterType.FLOAT,
                description="Vignette intensity (0.1 = subtle, 0.5 = strong)",
                required=False,
                default=0.3,
                min_value=0.0,
                max_value=1.0,
            ),
        ],
        examples=[
            "vignette:intensity=0.2 - Subtle vignette",
            "vignette:intensity=0.5 - Strong vignette",
        ],
        tags=["edges", "focus", "cinematic"],
    ))

    # Fade skill
    registry.register(Skill(
        name="fade",
        category=SkillCategory.VISUAL,
        description="Add fade in/out effect",
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
            "fade:type=in,duration=2 - 2 second fade in from start",
            "fade:type=out,start=58,duration=2 - Fade out starting at 58s",
        ],
        tags=["transition", "black"],
    ))

    # Color balance skill
    registry.register(Skill(
        name="colorbalance",
        category=SkillCategory.VISUAL,
        description="Adjust color balance (shadows, midtones, highlights)",
        parameters=[
            SkillParameter(
                name="rs",
                type=ParameterType.FLOAT,
                description="Red shadows adjustment (-1 to 1)",
                required=False,
                default=0,
            ),
            SkillParameter(
                name="gs",
                type=ParameterType.FLOAT,
                description="Green shadows adjustment (-1 to 1)",
                required=False,
                default=0,
            ),
            SkillParameter(
                name="bs",
                type=ParameterType.FLOAT,
                description="Blue shadows adjustment (-1 to 1)",
                required=False,
                default=0,
            ),
            SkillParameter(
                name="rm",
                type=ParameterType.FLOAT,
                description="Red midtones adjustment (-1 to 1)",
                required=False,
                default=0,
            ),
            SkillParameter(
                name="gm",
                type=ParameterType.FLOAT,
                description="Green midtones adjustment (-1 to 1)",
                required=False,
                default=0,
            ),
            SkillParameter(
                name="bm",
                type=ParameterType.FLOAT,
                description="Blue midtones adjustment (-1 to 1)",
                required=False,
                default=0,
            ),
        ],
        ffmpeg_template="colorbalance=rs={rs}:gs={gs}:bs={bs}:rm={rm}:gm={gm}:bm={bm}",
        examples=[
            "colorbalance:rs=0.1,rm=0.05 - Warm tones",
            "colorbalance:bs=0.1,bm=0.05 - Cool tones",
        ],
        tags=["color", "grade", "warm", "cool", "tint"],
    ))

    # Noise/grain skill
    registry.register(Skill(
        name="noise",
        category=SkillCategory.VISUAL,
        description="Add noise/grain to video",
        parameters=[
            SkillParameter(
                name="amount",
                type=ParameterType.INT,
                description="Noise amount (0-100)",
                required=False,
                default=10,
                min_value=0,
                max_value=100,
            ),
            SkillParameter(
                name="type",
                type=ParameterType.CHOICE,
                description="Noise type",
                required=False,
                default="uniform",
                choices=["uniform", "gaussian"],
            ),
        ],
        ffmpeg_template="noise=alls={amount}:allf=t+u",
        examples=[
            "noise:amount=15 - Subtle film grain",
            "noise:amount=40,type=gaussian - Heavy grain",
        ],
        tags=["grain", "film", "texture", "analog"],
    ))

    # Curves skill
    registry.register(Skill(
        name="curves",
        category=SkillCategory.VISUAL,
        description="Apply color curves preset",
        parameters=[
            SkillParameter(
                name="preset",
                type=ParameterType.CHOICE,
                description="Curves preset",
                required=False,
                default="increase_contrast",
                choices=[
                    "none",
                    "color_negative",
                    "cross_process",
                    "darker",
                    "increase_contrast",
                    "lighter",
                    "linear_contrast",
                    "medium_contrast",
                    "negative",
                    "strong_contrast",
                    "vintage",
                ],
            ),
        ],
        ffmpeg_template="curves=preset={preset}",
        examples=[
            "curves:preset=vintage - Vintage color look",
            "curves:preset=increase_contrast - More contrast",
        ],
        tags=["color", "grade", "look", "lut"],
    ))
