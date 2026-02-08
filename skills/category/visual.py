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

    # Text overlay skill
    registry.register(Skill(
        name="text_overlay",
        category=SkillCategory.VISUAL,
        description="Add text overlay on video",
        parameters=[
            SkillParameter(
                name="text",
                type=ParameterType.STRING,
                description="Text to display",
                required=True,
            ),
            SkillParameter(
                name="size",
                type=ParameterType.INT,
                description="Font size",
                required=False,
                default=48,
                min_value=8,
                max_value=200,
            ),
            SkillParameter(
                name="color",
                type=ParameterType.STRING,
                description="Text color (name or hex)",
                required=False,
                default="white",
            ),
            SkillParameter(
                name="position",
                type=ParameterType.CHOICE,
                description="Text position",
                required=False,
                default="center",
                choices=["center", "top", "bottom", "top_left", "top_right", "bottom_left", "bottom_right"],
            ),
            SkillParameter(
                name="font",
                type=ParameterType.STRING,
                description="Font name or path",
                required=False,
                default="Sans",
            ),
            SkillParameter(
                name="border",
                type=ParameterType.BOOL,
                description="Add black border/shadow around text",
                required=False,
                default=True,
            ),
        ],
        examples=[
            "text_overlay:text=Hello World - Center text",
            "text_overlay:text=Subscribe!,position=bottom,color=yellow,size=72 - Large yellow text at bottom",
        ],
        tags=["text", "title", "caption", "subtitle", "watermark", "label"],
    ))

    # Invert/negative skill
    registry.register(Skill(
        name="invert",
        category=SkillCategory.VISUAL,
        description="Invert colors (photo negative effect)",
        parameters=[],
        ffmpeg_template="negate",
        examples=[
            "invert - Invert all colors",
        ],
        tags=["negative", "negate", "reverse", "invert"],
    ))

    # Edge detection skill
    registry.register(Skill(
        name="edge_detect",
        category=SkillCategory.VISUAL,
        description="Apply edge detection effect",
        parameters=[
            SkillParameter(
                name="mode",
                type=ParameterType.CHOICE,
                description="Edge detection mode",
                required=False,
                default="canny",
                choices=["canny", "colormix"],
            ),
            SkillParameter(
                name="low",
                type=ParameterType.FLOAT,
                description="Low threshold (canny mode)",
                required=False,
                default=0.1,
                min_value=0.0,
                max_value=1.0,
            ),
            SkillParameter(
                name="high",
                type=ParameterType.FLOAT,
                description="High threshold (canny mode)",
                required=False,
                default=0.4,
                min_value=0.0,
                max_value=1.0,
            ),
        ],
        ffmpeg_template="edgedetect=low={low}:high={high}:mode={mode}",
        examples=[
            "edge_detect - Standard edge detection",
            "edge_detect:mode=colormix - Colorful edges",
        ],
        tags=["edge", "outline", "sketch", "line", "cartoon"],
    ))

    # Pixelate/mosaic skill
    registry.register(Skill(
        name="pixelate",
        category=SkillCategory.VISUAL,
        description="Pixelate video (mosaic/pixel art effect)",
        parameters=[
            SkillParameter(
                name="factor",
                type=ParameterType.INT,
                description="Pixelation factor (higher = more pixelated)",
                required=False,
                default=10,
                min_value=2,
                max_value=50,
            ),
        ],
        examples=[
            "pixelate - Standard pixelation",
            "pixelate:factor=20 - Heavy pixelation",
            "pixelate:factor=4 - Subtle pixelation",
        ],
        tags=["mosaic", "pixel", "censor", "blur", "8bit", "retro"],
    ))

    # Gamma correction skill
    registry.register(Skill(
        name="gamma",
        category=SkillCategory.VISUAL,
        description="Adjust gamma correction",
        parameters=[
            SkillParameter(
                name="value",
                type=ParameterType.FLOAT,
                description="Gamma value (< 1.0 = darker, > 1.0 = brighter)",
                required=False,
                default=1.2,
                min_value=0.1,
                max_value=4.0,
            ),
        ],
        ffmpeg_template="eq=gamma={value}",
        examples=[
            "gamma:value=1.5 - Brighter midtones",
            "gamma:value=0.7 - Darker midtones",
        ],
        tags=["gamma", "midtones", "exposure", "light"],
    ))

    # Exposure adjustment skill
    registry.register(Skill(
        name="exposure",
        category=SkillCategory.VISUAL,
        description="Adjust video exposure",
        parameters=[
            SkillParameter(
                name="value",
                type=ParameterType.FLOAT,
                description="Exposure adjustment (-3 to 3 stops)",
                required=False,
                default=0.5,
                min_value=-3.0,
                max_value=3.0,
            ),
        ],
        ffmpeg_template="exposure=exposure={value}",
        examples=[
            "exposure:value=1.0 - One stop brighter",
            "exposure:value=-0.5 - Half stop darker",
        ],
        tags=["light", "bright", "dark", "ev", "stops"],
    ))

    # Chroma key (green screen) skill
    registry.register(Skill(
        name="chromakey",
        category=SkillCategory.VISUAL,
        description="Remove a color background (green screen / chroma key)",
        parameters=[
            SkillParameter(
                name="color",
                type=ParameterType.STRING,
                description="Color to remove (hex or name, e.g. '0x00FF00' for green)",
                required=False,
                default="0x00FF00",
            ),
            SkillParameter(
                name="similarity",
                type=ParameterType.FLOAT,
                description="Color match tolerance (0.01 = exact, 0.5 = loose)",
                required=False,
                default=0.15,
                min_value=0.01,
                max_value=0.5,
            ),
            SkillParameter(
                name="blend",
                type=ParameterType.FLOAT,
                description="Edge blend amount",
                required=False,
                default=0.1,
                min_value=0.0,
                max_value=1.0,
            ),
        ],
        ffmpeg_template="chromakey=color={color}:similarity={similarity}:blend={blend}",
        examples=[
            "chromakey - Remove green screen",
            "chromakey:color=0x0000FF,similarity=0.2 - Remove blue screen",
        ],
        tags=["greenscreen", "bluescreen", "key", "remove", "background", "transparent"],
    ))

    # Deband skill
    registry.register(Skill(
        name="deband",
        category=SkillCategory.VISUAL,
        description="Remove color banding artifacts",
        parameters=[
            SkillParameter(
                name="threshold",
                type=ParameterType.FLOAT,
                description="Deband threshold (higher = more aggressive)",
                required=False,
                default=0.02,
                min_value=0.0,
                max_value=0.1,
            ),
        ],
        ffmpeg_template="deband=1thr={threshold}:2thr={threshold}:3thr={threshold}:4thr={threshold}",
        examples=[
            "deband - Remove color banding",
            "deband:threshold=0.05 - Aggressive debanding",
        ],
        tags=["banding", "gradient", "smooth", "quality"],
    ))
