"""Vintage and retro effect skills."""

from ..registry import SkillRegistry, Skill, SkillParameter, SkillCategory, ParameterType


def register_skills(registry: SkillRegistry) -> None:
    """Register vintage/retro skills with the registry."""

    # Vintage skill
    registry.register(Skill(
        name="vintage",
        category=SkillCategory.OUTCOME,
        description="Old film look with grain and color shift",
        parameters=[
            SkillParameter(
                name="era",
                type=ParameterType.CHOICE,
                description="Time period style",
                required=False,
                default="70s",
                choices=["50s", "60s", "70s", "80s", "90s"],
            ),
        ],
        pipeline=[
            "saturation:value=0.8",
            "noise:amount=20",
            "vignette:intensity=0.35",
            "curves:preset=vintage",
        ],
        examples=[
            "vintage - Classic vintage look",
            "vintage:era=80s - 1980s aesthetic",
        ],
        tags=["retro", "old", "film", "nostalgia", "throwback"],
    ))

    # VHS skill
    registry.register(Skill(
        name="vhs",
        category=SkillCategory.OUTCOME,
        description="VHS tape aesthetic with distortion",
        parameters=[
            SkillParameter(
                name="intensity",
                type=ParameterType.CHOICE,
                description="Effect intensity",
                required=False,
                default="medium",
                choices=["light", "medium", "heavy"],
            ),
        ],
        pipeline=[
            "noise:amount=30,type=gaussian",
            "saturation:value=1.1",
            "blur:radius=1",
        ],
        examples=[
            "vhs - VHS tape look",
            "vhs:intensity=heavy - Heavily degraded VHS",
        ],
        tags=["tape", "analog", "retro", "distortion", "80s", "90s"],
    ))

    # Sepia skill
    registry.register(Skill(
        name="sepia",
        category=SkillCategory.OUTCOME,
        description="Classic sepia tone effect",
        parameters=[
            SkillParameter(
                name="intensity",
                type=ParameterType.FLOAT,
                description="Sepia intensity (0-1)",
                required=False,
                default=0.8,
                min_value=0,
                max_value=1,
            ),
        ],
        ffmpeg_template="colorchannelmixer=.393:.769:.189:0:.349:.686:.168:0:.272:.534:.131",
        examples=[
            "sepia - Full sepia tone",
            "sepia:intensity=0.5 - Partial sepia",
        ],
        tags=["brown", "old", "antique", "photo"],
    ))

    # Super 8 skill
    registry.register(Skill(
        name="super8",
        category=SkillCategory.OUTCOME,
        description="Super 8 film look",
        parameters=[
            SkillParameter(
                name="jitter",
                type=ParameterType.BOOL,
                description="Add film jitter",
                required=False,
                default=True,
            ),
        ],
        pipeline=[
            "saturation:value=1.2",
            "contrast:value=1.15",
            "noise:amount=25",
            "vignette:intensity=0.4",
        ],
        examples=[
            "super8 - Classic Super 8 film look",
        ],
        tags=["film", "8mm", "home movie", "analog"],
    ))

    # Polaroid skill
    registry.register(Skill(
        name="polaroid",
        category=SkillCategory.OUTCOME,
        description="Polaroid instant photo aesthetic",
        parameters=[],
        pipeline=[
            "saturation:value=0.9",
            "contrast:value=0.95",
            "brightness:value=0.05",
            "vignette:intensity=0.2",
        ],
        examples=[
            "polaroid - Polaroid photo look",
        ],
        tags=["instant", "photo", "retro", "faded"],
    ))

    # Faded skill
    registry.register(Skill(
        name="faded",
        category=SkillCategory.OUTCOME,
        description="Faded, washed out look",
        parameters=[
            SkillParameter(
                name="amount",
                type=ParameterType.FLOAT,
                description="Fade amount (0-1)",
                required=False,
                default=0.3,
                min_value=0,
                max_value=0.6,
            ),
        ],
        pipeline=[
            "contrast:value=0.85",
            "saturation:value=0.8",
            "brightness:value=0.1",
        ],
        examples=[
            "faded - Soft faded look",
            "faded:amount=0.5 - More pronounced fade",
        ],
        tags=["washed", "light", "soft", "desaturated"],
    ))

    # Old TV skill
    registry.register(Skill(
        name="old_tv",
        category=SkillCategory.OUTCOME,
        description="Old CRT television look",
        parameters=[
            SkillParameter(
                name="scanlines",
                type=ParameterType.BOOL,
                description="Add scanlines",
                required=False,
                default=True,
            ),
        ],
        pipeline=[
            "saturation:value=0.9",
            "contrast:value=1.1",
            "noise:amount=10",
        ],
        examples=[
            "old_tv - CRT TV aesthetic",
        ],
        tags=["crt", "television", "analog", "scanlines"],
    ))

    # Damaged film skill
    registry.register(Skill(
        name="damaged_film",
        category=SkillCategory.OUTCOME,
        description="Simulated damaged/aged film",
        parameters=[
            SkillParameter(
                name="damage_level",
                type=ParameterType.CHOICE,
                description="Damage severity",
                required=False,
                default="medium",
                choices=["light", "medium", "heavy"],
            ),
        ],
        pipeline=[
            "noise:amount=35,type=gaussian",
            "saturation:value=0.7",
            "contrast:value=1.2",
            "vignette:intensity=0.45",
        ],
        examples=[
            "damaged_film - Weathered film look",
            "damaged_film:damage_level=heavy - Very aged appearance",
        ],
        tags=["aged", "worn", "scratches", "decay"],
    ))

    # Noir skill
    registry.register(Skill(
        name="noir",
        category=SkillCategory.OUTCOME,
        description="Film noir style black and white",
        parameters=[],
        pipeline=[
            "saturation:value=0",
            "contrast:value=1.4",
            "brightness:value=-0.1",
            "vignette:intensity=0.4",
        ],
        examples=[
            "noir - Classic film noir look",
        ],
        tags=["black_and_white", "detective", "shadow", "contrast"],
    ))
