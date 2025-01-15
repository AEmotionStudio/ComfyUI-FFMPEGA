"""Cinematic outcome skills."""

from ..registry import SkillRegistry, Skill, SkillParameter, SkillCategory, ParameterType


def register_skills(registry: SkillRegistry) -> None:
    """Register cinematic skills with the registry."""

    # Cinematic look skill
    registry.register(Skill(
        name="cinematic",
        category=SkillCategory.OUTCOME,
        description="Apply cinematic look with letterbox and color grade",
        parameters=[
            SkillParameter(
                name="intensity",
                type=ParameterType.CHOICE,
                description="Effect intensity",
                required=False,
                default="medium",
                choices=["subtle", "medium", "strong"],
            ),
        ],
        pipeline=[
            "aspect:ratio=2.35:1,mode=pad,color=black",
            "contrast:value=1.1",
            "saturation:value=0.9",
            "vignette:intensity=0.25",
        ],
        examples=[
            "cinematic - Apply full cinematic treatment",
            "cinematic:intensity=subtle - Light cinematic touch",
        ],
        tags=["film", "movie", "widescreen", "letterbox", "grade"],
    ))

    # Letterbox skill
    registry.register(Skill(
        name="letterbox",
        category=SkillCategory.OUTCOME,
        description="Add cinematic letterbox bars",
        parameters=[
            SkillParameter(
                name="ratio",
                type=ParameterType.STRING,
                description="Target aspect ratio",
                required=False,
                default="2.35:1",
            ),
            SkillParameter(
                name="color",
                type=ParameterType.STRING,
                description="Bar color",
                required=False,
                default="black",
            ),
        ],
        pipeline=[
            "aspect:ratio={ratio},mode=pad,color={color}",
        ],
        examples=[
            "letterbox - Standard 2.35:1 letterbox",
            "letterbox:ratio=2.39:1 - Anamorphic letterbox",
            "letterbox:ratio=1.85:1 - Academy flat letterbox",
        ],
        tags=["widescreen", "bars", "aspect", "cinematic"],
    ))

    # Film grain skill
    registry.register(Skill(
        name="film_grain",
        category=SkillCategory.OUTCOME,
        description="Add authentic film grain texture",
        parameters=[
            SkillParameter(
                name="intensity",
                type=ParameterType.CHOICE,
                description="Grain intensity",
                required=False,
                default="medium",
                choices=["light", "medium", "heavy"],
            ),
        ],
        pipeline=[
            "noise:amount=15",
        ],
        examples=[
            "film_grain - Medium film grain",
            "film_grain:intensity=light - Subtle grain",
        ],
        tags=["texture", "analog", "35mm", "noise"],
    ))

    # Color grade skill
    registry.register(Skill(
        name="color_grade",
        category=SkillCategory.OUTCOME,
        description="Apply cinematic color grading",
        parameters=[
            SkillParameter(
                name="style",
                type=ParameterType.CHOICE,
                description="Color grade style",
                required=True,
                choices=["teal_orange", "warm", "cool", "desaturated", "high_contrast"],
            ),
        ],
        examples=[
            "color_grade:style=teal_orange - Popular cinema look",
            "color_grade:style=desaturated - Bleach bypass style",
        ],
        tags=["lut", "look", "color", "grade"],
    ))

    # Black and white skill
    registry.register(Skill(
        name="black_and_white",
        category=SkillCategory.OUTCOME,
        description="Convert to black and white with optional tinting",
        parameters=[
            SkillParameter(
                name="style",
                type=ParameterType.CHOICE,
                description="B&W style",
                required=False,
                default="standard",
                choices=["standard", "high_contrast", "soft", "sepia"],
            ),
        ],
        pipeline=[
            "saturation:value=0",
            "contrast:value=1.1",
        ],
        examples=[
            "black_and_white - Standard B&W conversion",
            "black_and_white:style=high_contrast - Dramatic B&W",
        ],
        tags=["bw", "monochrome", "grayscale", "noir"],
    ))

    # Day for night skill
    registry.register(Skill(
        name="day_for_night",
        category=SkillCategory.OUTCOME,
        description="Simulate night time from day footage",
        parameters=[
            SkillParameter(
                name="intensity",
                type=ParameterType.CHOICE,
                description="Effect intensity",
                required=False,
                default="medium",
                choices=["light", "medium", "strong"],
            ),
        ],
        pipeline=[
            "brightness:value=-0.3",
            "saturation:value=0.6",
            "hue:value=-15",
            "contrast:value=1.2",
        ],
        examples=[
            "day_for_night - Simulate night from day footage",
        ],
        tags=["night", "dark", "mood", "simulate"],
    ))

    # Dreamy skill
    registry.register(Skill(
        name="dreamy",
        category=SkillCategory.OUTCOME,
        description="Create a soft, dreamy look",
        parameters=[
            SkillParameter(
                name="intensity",
                type=ParameterType.CHOICE,
                description="Effect intensity",
                required=False,
                default="medium",
                choices=["subtle", "medium", "strong"],
            ),
        ],
        pipeline=[
            "blur:radius=2",
            "brightness:value=0.05",
            "saturation:value=0.85",
            "contrast:value=0.9",
        ],
        examples=[
            "dreamy - Soft dreamy look",
            "dreamy:intensity=subtle - Light glow effect",
        ],
        tags=["soft", "glow", "romantic", "ethereal"],
    ))

    # HDR tone mapping skill
    registry.register(Skill(
        name="hdr_look",
        category=SkillCategory.OUTCOME,
        description="Simulate HDR-like dynamic range",
        parameters=[],
        pipeline=[
            "contrast:value=1.3",
            "saturation:value=1.2",
            "sharpen:amount=0.8",
        ],
        examples=[
            "hdr_look - HDR-style processing",
        ],
        tags=["dynamic", "vibrant", "punch", "pop"],
    ))
