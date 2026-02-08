"""Creative and artistic effect skills."""

from ..registry import SkillRegistry, Skill, SkillParameter, SkillCategory, ParameterType


def register_skills(registry: SkillRegistry) -> None:
    """Register creative effect skills with the registry."""

    # Neon glow skill
    registry.register(Skill(
        name="neon",
        category=SkillCategory.OUTCOME,
        description="Neon glow aesthetic with vibrant edges and colors",
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
            "saturation:value=1.8",
            "contrast:value=1.4",
            "brightness:value=-0.1",
            "sharpen:amount=2.0",
        ],
        examples=[
            "neon - Neon glow effect",
            "neon:intensity=strong - Intense neon",
        ],
        tags=["neon", "glow", "vibrant", "electric", "cyberpunk", "bright"],
    ))

    # Horror skill
    registry.register(Skill(
        name="horror",
        category=SkillCategory.OUTCOME,
        description="Horror movie atmosphere (dark, desaturated, high contrast)",
        parameters=[
            SkillParameter(
                name="intensity",
                type=ParameterType.CHOICE,
                description="Effect intensity",
                required=False,
                default="medium",
                choices=["subtle", "medium", "extreme"],
            ),
        ],
        pipeline=[
            "saturation:value=0.3",
            "contrast:value=1.5",
            "brightness:value=-0.2",
            "vignette:intensity=0.5",
            "noise:amount=15",
        ],
        examples=[
            "horror - Dark horror atmosphere",
            "horror:intensity=extreme - Maximum dread",
        ],
        tags=["horror", "dark", "scary", "creepy", "spooky", "halloween"],
    ))

    # Underwater skill
    registry.register(Skill(
        name="underwater",
        category=SkillCategory.OUTCOME,
        description="Simulate underwater look with blue tint and blur",
        parameters=[
            SkillParameter(
                name="depth",
                type=ParameterType.CHOICE,
                description="Simulated water depth",
                required=False,
                default="shallow",
                choices=["shallow", "medium", "deep"],
            ),
        ],
        pipeline=[
            "hue:value=-30",
            "saturation:value=0.7",
            "blur:radius=2",
            "brightness:value=-0.1",
            "contrast:value=0.9",
        ],
        examples=[
            "underwater - Shallow water look",
            "underwater:depth=deep - Deep ocean feel",
        ],
        tags=["water", "ocean", "blue", "aquatic", "sea", "dive"],
    ))

    # Sunset/golden hour skill
    registry.register(Skill(
        name="sunset",
        category=SkillCategory.OUTCOME,
        description="Golden hour / sunset warm glow effect",
        parameters=[
            SkillParameter(
                name="warmth",
                type=ParameterType.CHOICE,
                description="Warmth level",
                required=False,
                default="golden",
                choices=["warm", "golden", "fiery"],
            ),
        ],
        pipeline=[
            "hue:value=15",
            "saturation:value=1.3",
            "brightness:value=0.05",
            "contrast:value=1.1",
            "vignette:intensity=0.2",
        ],
        examples=[
            "sunset - Golden hour glow",
            "sunset:warmth=fiery - Intense sunset colors",
        ],
        tags=["golden", "warm", "sunset", "sunrise", "hour", "orange", "glow"],
    ))

    # Cyberpunk skill
    registry.register(Skill(
        name="cyberpunk",
        category=SkillCategory.OUTCOME,
        description="Cyberpunk aesthetic with high contrast and neon tones",
        parameters=[
            SkillParameter(
                name="style",
                type=ParameterType.CHOICE,
                description="Cyberpunk style",
                required=False,
                default="neon",
                choices=["neon", "dark", "matrix"],
            ),
        ],
        pipeline=[
            "saturation:value=1.6",
            "contrast:value=1.4",
            "hue:value=20",
            "sharpen:amount=1.5",
            "vignette:intensity=0.3",
        ],
        examples=[
            "cyberpunk - Neon cyberpunk aesthetic",
            "cyberpunk:style=matrix - Green-tinted matrix style",
        ],
        tags=["cyberpunk", "neon", "futuristic", "sci-fi", "blade_runner"],
    ))

    # Comic book skill
    registry.register(Skill(
        name="comic_book",
        category=SkillCategory.OUTCOME,
        description="Comic book / pop art style with bold edges and colors",
        parameters=[
            SkillParameter(
                name="style",
                type=ParameterType.CHOICE,
                description="Comic style",
                required=False,
                default="classic",
                choices=["classic", "manga", "pop_art"],
            ),
        ],
        pipeline=[
            "saturation:value=1.5",
            "contrast:value=1.6",
            "sharpen:amount=2.5",
        ],
        examples=[
            "comic_book - Classic comic book style",
            "comic_book:style=pop_art - Pop art look",
        ],
        tags=["comic", "cartoon", "pop_art", "bold", "graphic", "manga"],
    ))

    # Miniature/tilt-shift skill
    registry.register(Skill(
        name="miniature",
        category=SkillCategory.OUTCOME,
        description="Tilt-shift miniature effect (makes scenes look like toy models)",
        parameters=[
            SkillParameter(
                name="intensity",
                type=ParameterType.CHOICE,
                description="Effect strength",
                required=False,
                default="medium",
                choices=["subtle", "medium", "strong"],
            ),
        ],
        pipeline=[
            "saturation:value=1.4",
            "contrast:value=1.2",
            "sharpen:amount=1.5",
        ],
        examples=[
            "miniature - Tilt-shift miniature effect",
        ],
        tags=["tilt_shift", "miniature", "toy", "model", "diorama"],
    ))

    # Surveillance camera skill
    registry.register(Skill(
        name="surveillance",
        category=SkillCategory.OUTCOME,
        description="Security camera / CCTV footage look",
        parameters=[
            SkillParameter(
                name="style",
                type=ParameterType.CHOICE,
                description="Camera style",
                required=False,
                default="modern",
                choices=["modern", "old", "infrared"],
            ),
        ],
        pipeline=[
            "saturation:value=0.5",
            "contrast:value=1.2",
            "noise:amount=12",
            "sharpen:amount=0.5",
        ],
        examples=[
            "surveillance - Modern CCTV look",
            "surveillance:style=old - Old grainy security cam",
        ],
        tags=["cctv", "security", "camera", "footage", "spy"],
    ))

    # Music video skill
    registry.register(Skill(
        name="music_video",
        category=SkillCategory.OUTCOME,
        description="Music video aesthetic with punchy colors and contrast",
        parameters=[
            SkillParameter(
                name="genre",
                type=ParameterType.CHOICE,
                description="Music genre style",
                required=False,
                default="pop",
                choices=["pop", "hip_hop", "rock", "indie", "electronic"],
            ),
        ],
        pipeline=[
            "contrast:value=1.3",
            "saturation:value=1.4",
            "vignette:intensity=0.25",
            "sharpen:amount=1.0",
        ],
        examples=[
            "music_video - Pop music video look",
            "music_video:genre=hip_hop - Hip hop music video aesthetic",
        ],
        tags=["music", "video", "performance", "concert", "mv"],
    ))

    # Anime/cel style skill
    registry.register(Skill(
        name="anime",
        category=SkillCategory.OUTCOME,
        description="Anime / cel-shaded cartoon style",
        parameters=[
            SkillParameter(
                name="style",
                type=ParameterType.CHOICE,
                description="Anime style",
                required=False,
                default="standard",
                choices=["standard", "pastel", "dark"],
            ),
        ],
        pipeline=[
            "saturation:value=1.3",
            "contrast:value=1.3",
            "sharpen:amount=2.0",
            "denoise:strength=medium",
        ],
        examples=[
            "anime - Standard anime look",
            "anime:style=pastel - Soft pastel anime",
        ],
        tags=["anime", "cartoon", "cel", "japanese", "animation", "manga"],
    ))

    # Lo-fi / chill skill
    registry.register(Skill(
        name="lofi",
        category=SkillCategory.OUTCOME,
        description="Lo-fi / chill aesthetic (soft, warm, slightly degraded)",
        parameters=[],
        pipeline=[
            "saturation:value=0.85",
            "contrast:value=0.9",
            "brightness:value=0.05",
            "blur:radius=1",
            "noise:amount=8",
            "vignette:intensity=0.2",
        ],
        examples=[
            "lofi - Lo-fi chill aesthetic",
        ],
        tags=["lofi", "chill", "aesthetic", "study", "relax", "vaporwave"],
    ))

    # Thermal/heat vision skill
    registry.register(Skill(
        name="thermal",
        category=SkillCategory.OUTCOME,
        description="Thermal / heat vision camera effect",
        parameters=[],
        pipeline=[
            "hue:value=60",
            "saturation:value=2.0",
            "contrast:value=1.5",
        ],
        examples=[
            "thermal - Thermal camera effect",
        ],
        tags=["thermal", "heat", "infrared", "vision", "night"],
    ))

    # Posterize skill (handled by builtin composer handler using lutrgb)
    registry.register(Skill(
        name="posterize",
        category=SkillCategory.OUTCOME,
        description="Posterize effect (reduce color palette for poster/screen-print look)",
        parameters=[
            SkillParameter(
                name="levels",
                type=ParameterType.INT,
                description="Number of color levels per channel (2-8)",
                required=False,
                default=4,
                min_value=2,
                max_value=8,
            ),
        ],
        examples=[
            "posterize - Standard posterization (4 levels)",
            "posterize:levels=2 - Extreme posterization",
        ],
        tags=["poster", "print", "limited", "palette", "pop_art"],
    ))

    # Emboss skill
    registry.register(Skill(
        name="emboss",
        category=SkillCategory.OUTCOME,
        description="Emboss / relief effect (raised surface look)",
        parameters=[],
        ffmpeg_template="convolution=-2 -1 0 -1 1 1 0 1 2:-2 -1 0 -1 1 1 0 1 2:-2 -1 0 -1 1 1 0 1 2:-2 -1 0 -1 1 1 0 1 2",
        examples=[
            "emboss - Embossed relief effect",
        ],
        tags=["emboss", "relief", "3d", "texture", "carved"],
    ))
