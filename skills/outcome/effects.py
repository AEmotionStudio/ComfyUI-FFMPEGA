"""Special effects skills."""

from ..registry import SkillRegistry, Skill, SkillParameter, SkillCategory, ParameterType


def register_skills(registry: SkillRegistry) -> None:
    """Register special effects skills with the registry."""

    # Timelapse skill
    registry.register(Skill(
        name="timelapse",
        category=SkillCategory.TEMPORAL,
        description="Speed up footage dramatically for timelapse effect",
        parameters=[
            SkillParameter(
                name="factor",
                type=ParameterType.FLOAT,
                description="Speed multiplier",
                required=False,
                default=10.0,
                min_value=2.0,
                max_value=100.0,
            ),
            SkillParameter(
                name="smooth",
                type=ParameterType.BOOL,
                description="Apply smoothing",
                required=False,
                default=True,
            ),
        ],
        pipeline=[
            "speed:factor={factor}",
        ],
        examples=[
            "timelapse - 10x speed timelapse",
            "timelapse:factor=30 - 30x speed",
        ],
        tags=["fast", "hyperlapse", "compress", "time"],
    ))

    # Slowmo skill
    registry.register(Skill(
        name="slowmo",
        category=SkillCategory.TEMPORAL,
        description="Smooth slow motion effect",
        parameters=[
            SkillParameter(
                name="factor",
                type=ParameterType.FLOAT,
                description="Slowdown factor (0.5 = half speed)",
                required=False,
                default=0.25,
                min_value=0.1,
                max_value=0.9,
            ),
        ],
        pipeline=[
            "speed:factor={factor}",
        ],
        examples=[
            "slowmo - 4x slow motion (0.25x speed)",
            "slowmo:factor=0.5 - Half speed",
        ],
        tags=["slow", "motion", "dramatic", "smooth"],
    ))

    # Stabilize skill
    registry.register(Skill(
        name="stabilize",
        category=SkillCategory.OUTCOME,
        description="Remove camera shake and stabilize footage",
        parameters=[
            SkillParameter(
                name="strength",
                type=ParameterType.CHOICE,
                description="Stabilization strength",
                required=False,
                default="medium",
                choices=["light", "medium", "strong"],
            ),
        ],
        ffmpeg_template="vidstabtransform=smoothing=10:input=transforms.trf",
        examples=[
            "stabilize - Medium stabilization",
            "stabilize:strength=strong - Maximum stabilization",
        ],
        tags=["steady", "smooth", "shake", "handheld"],
    ))

    # Meme/Deep fried skill
    registry.register(Skill(
        name="meme",
        category=SkillCategory.OUTCOME,
        description="Deep-fried meme aesthetic",
        parameters=[
            SkillParameter(
                name="intensity",
                type=ParameterType.CHOICE,
                description="Deep fry intensity",
                required=False,
                default="medium",
                choices=["light", "medium", "crispy"],
            ),
        ],
        pipeline=[
            "saturation:value=1.5",
            "contrast:value=1.4",
            "sharpen:amount=2.5",
            "noise:amount=20",
        ],
        examples=[
            "meme - Deep fried meme look",
            "meme:intensity=crispy - Extra deep fried",
        ],
        tags=["deep_fried", "funny", "oversaturated", "ironic"],
    ))

    # Glitch skill
    registry.register(Skill(
        name="glitch",
        category=SkillCategory.VISUAL,
        description="Digital glitch effect",
        parameters=[
            SkillParameter(
                name="intensity",
                type=ParameterType.CHOICE,
                description="Glitch intensity",
                required=False,
                default="medium",
                choices=["subtle", "medium", "extreme"],
            ),
        ],
        pipeline=[
            "noise:amount=25,type=gaussian",
        ],
        examples=[
            "glitch - Digital glitch effect",
            "glitch:intensity=extreme - Heavy glitching",
        ],
        tags=["digital", "error", "corruption", "aesthetic"],
    ))

    # Mirror skill
    registry.register(Skill(
        name="mirror",
        category=SkillCategory.SPATIAL,
        description="Create mirror/kaleidoscope effect",
        parameters=[
            SkillParameter(
                name="mode",
                type=ParameterType.CHOICE,
                description="Mirror mode",
                required=False,
                default="horizontal",
                choices=["horizontal", "vertical", "quad"],
            ),
        ],
        examples=[
            "mirror - Horizontal mirror effect",
            "mirror:mode=quad - Four-way mirror",
        ],
        tags=["reflection", "symmetric", "kaleidoscope"],
    ))

    # Zoom skill
    registry.register(Skill(
        name="zoom",
        category=SkillCategory.SPATIAL,
        description="Apply zoom effect",
        parameters=[
            SkillParameter(
                name="factor",
                type=ParameterType.FLOAT,
                description="Zoom factor (1.0 = no zoom)",
                required=True,
                min_value=1.0,
                max_value=4.0,
            ),
            SkillParameter(
                name="x",
                type=ParameterType.STRING,
                description="Center X position (0-1 or 'center')",
                required=False,
                default="center",
            ),
            SkillParameter(
                name="y",
                type=ParameterType.STRING,
                description="Center Y position (0-1 or 'center')",
                required=False,
                default="center",
            ),
        ],
        examples=[
            "zoom:factor=1.5 - 1.5x zoom on center",
            "zoom:factor=2.0,x=0.7,y=0.3 - Zoom on upper right",
        ],
        tags=["magnify", "crop", "focus", "closeup"],
    ))

    # Ken Burns skill
    registry.register(Skill(
        name="ken_burns",
        category=SkillCategory.SPATIAL,
        description="Pan and zoom animation (Ken Burns effect)",
        parameters=[
            SkillParameter(
                name="direction",
                type=ParameterType.CHOICE,
                description="Animation direction",
                required=False,
                default="zoom_in",
                choices=["zoom_in", "zoom_out", "pan_left", "pan_right"],
            ),
            SkillParameter(
                name="amount",
                type=ParameterType.FLOAT,
                description="Movement amount (0.1-0.5)",
                required=False,
                default=0.2,
                min_value=0.1,
                max_value=0.5,
            ),
        ],
        examples=[
            "ken_burns - Slow zoom in",
            "ken_burns:direction=pan_right - Pan to the right",
        ],
        tags=["pan", "animate", "documentary", "slideshow"],
    ))

    # Boomerang skill
    registry.register(Skill(
        name="boomerang",
        category=SkillCategory.TEMPORAL,
        description="Create looping boomerang effect",
        parameters=[
            SkillParameter(
                name="loops",
                type=ParameterType.INT,
                description="Number of loop cycles",
                required=False,
                default=3,
                min_value=1,
                max_value=10,
            ),
        ],
        examples=[
            "boomerang - Standard boomerang loop",
            "boomerang:loops=5 - More loop cycles",
        ],
        tags=["loop", "reverse", "instagram", "bounce"],
    ))

    # Iris reveal — circular reveal from center
    registry.register(Skill(
        name="iris_reveal",
        category=SkillCategory.OUTCOME,
        description="Circular reveal expanding from the center of the frame",
        parameters=[
            SkillParameter(
                name="duration",
                type=ParameterType.FLOAT,
                description="Duration of the reveal in seconds",
                required=False,
                default=2.0,
                min_value=0.5,
                max_value=10.0,
            ),
        ],
        examples=[
            "iris_reveal - 2 second circular reveal",
            "iris_reveal:duration=4 - Slow 4 second iris reveal",
        ],
        tags=["circle", "reveal", "iris", "mask", "opening", "transition"],
    ))

    # Wipe — directional wipe reveal
    registry.register(Skill(
        name="wipe",
        category=SkillCategory.OUTCOME,
        description="Reveal the video with a directional wipe from black",
        parameters=[
            SkillParameter(
                name="direction",
                type=ParameterType.CHOICE,
                description="Wipe direction",
                required=False,
                default="left",
                choices=["left", "right", "up", "down"],
            ),
            SkillParameter(
                name="duration",
                type=ParameterType.FLOAT,
                description="Wipe duration in seconds",
                required=False,
                default=1.5,
                min_value=0.3,
                max_value=10.0,
            ),
        ],
        examples=[
            "wipe - Left-to-right wipe reveal",
            "wipe:direction=down,duration=2 - Top-to-bottom wipe",
        ],
        tags=["wipe", "reveal", "transition", "slide", "curtain"],
    ))

    # Slide in — video slides in from edge
    registry.register(Skill(
        name="slide_in",
        category=SkillCategory.OUTCOME,
        description="Slide the video in from an edge of the frame",
        parameters=[
            SkillParameter(
                name="direction",
                type=ParameterType.CHOICE,
                description="Direction the video slides from",
                required=False,
                default="left",
                choices=["left", "right", "up", "down"],
            ),
            SkillParameter(
                name="duration",
                type=ParameterType.FLOAT,
                description="Slide animation duration in seconds",
                required=False,
                default=1.0,
                min_value=0.3,
                max_value=5.0,
            ),
        ],
        examples=[
            "slide_in - Slide in from the left",
            "slide_in:direction=down,duration=2 - Slide down from top",
        ],
        tags=["slide", "entrance", "animation", "motion", "transition"],
    ))

    # Chroma key (green/blue screen removal)
    registry.register(Skill(
        name="chromakey",
        category=SkillCategory.VISUAL,
        description="Remove green or blue screen background (chroma key)",
        parameters=[
            SkillParameter(
                name="color",
                type=ParameterType.STRING,
                description="Key color to remove (hex or name)",
                required=False,
                default="green",
            ),
            SkillParameter(
                name="similarity",
                type=ParameterType.FLOAT,
                description="Color similarity threshold (higher = more removal)",
                required=False,
                default=0.3,
                min_value=0.01,
                max_value=1.0,
            ),
            SkillParameter(
                name="blend",
                type=ParameterType.FLOAT,
                description="Edge blending (higher = softer edges)",
                required=False,
                default=0.1,
                min_value=0.0,
                max_value=1.0,
            ),
        ],
        examples=[
            "chromakey - Remove green screen",
            "chromakey:color=blue,similarity=0.4 - Remove blue screen",
            "chromakey:color=0x00FF00,similarity=0.2,blend=0.05 - Precise green removal",
        ],
        tags=["greenscreen", "bluescreen", "chroma", "key", "background", "remove", "transparent"],
    ))

    # Deband (remove gradient banding)
    registry.register(Skill(
        name="deband",
        category=SkillCategory.VISUAL,
        description="Remove banding artifacts from gradients (especially AI-generated video)",
        parameters=[
            SkillParameter(
                name="threshold",
                type=ParameterType.FLOAT,
                description="Banding detection threshold (0.08 = moderate, 0.2+ = heavy)",
                required=False,
                default=0.08,
                min_value=0.003,
                max_value=0.5,
            ),
            SkillParameter(
                name="range",
                type=ParameterType.INT,
                description="Banding detection range in pixels",
                required=False,
                default=16,
                min_value=8,
                max_value=64,
            ),
            SkillParameter(
                name="blur",
                type=ParameterType.BOOL,
                description="Enable dithering/blur to smooth band transitions",
                required=False,
                default=True,
            ),
        ],
        examples=[
            "deband - Remove gradient banding",
            "deband:threshold=0.15 - Aggressive debanding",
            "deband:threshold=0.3,range=32 - Heavy debanding (AI video)",
        ],
        tags=["banding", "gradient", "artifact", "fix", "quality", "ai"],
    ))

    # Lens correction
    registry.register(Skill(
        name="lens_correction",
        category=SkillCategory.SPATIAL,
        description="Fix barrel or pincushion lens distortion (GoPro, wide-angle)",
        parameters=[
            SkillParameter(
                name="k1",
                type=ParameterType.FLOAT,
                description="Quadratic correction (negative = barrel, positive = pincushion)",
                required=False,
                default=-0.2,
                min_value=-1.0,
                max_value=1.0,
            ),
            SkillParameter(
                name="k2",
                type=ParameterType.FLOAT,
                description="Double quadratic correction",
                required=False,
                default=0.0,
                min_value=-1.0,
                max_value=1.0,
            ),
        ],
        examples=[
            "lens_correction - Fix mild barrel distortion",
            "lens_correction:k1=-0.4 - Fix strong GoPro/wide-angle distortion",
        ],
        tags=["lens", "distortion", "barrel", "pincushion", "gopro", "fisheye", "fix"],
    ))

    # Deinterlace
    registry.register(Skill(
        name="deinterlace",
        category=SkillCategory.SPATIAL,
        description="Remove interlacing from old or TV footage",
        parameters=[
            SkillParameter(
                name="mode",
                type=ParameterType.CHOICE,
                description="Deinterlace mode",
                required=False,
                default="send_frame",
                choices=["send_frame", "send_field"],
            ),
        ],
        examples=[
            "deinterlace - Remove interlacing (standard)",
            "deinterlace:mode=send_field - Double framerate deinterlace",
        ],
        tags=["interlace", "deinterlace", "tv", "old", "footage", "fix"],
    ))

    # Frame interpolation (smooth slow-mo)
    registry.register(Skill(
        name="frame_interpolation",
        category=SkillCategory.SPATIAL,
        description="Smooth slow motion or frame rate conversion using motion interpolation",
        parameters=[
            SkillParameter(
                name="fps",
                type=ParameterType.INT,
                description="Target frames per second",
                required=False,
                default=60,
                min_value=15,
                max_value=120,
            ),
            SkillParameter(
                name="mode",
                type=ParameterType.CHOICE,
                description="Interpolation mode",
                required=False,
                default="mci",
                choices=["dup", "blend", "mci"],
            ),
        ],
        examples=[
            "frame_interpolation - Interpolate to 60fps",
            "frame_interpolation:fps=120,mode=mci - Smooth 120fps",
        ],
        tags=["interpolation", "slowmo", "smooth", "fps", "framerate", "motion"],
    ))

    # Scroll (scrolling credits/ticker)
    registry.register(Skill(
        name="scroll",
        category=SkillCategory.SPATIAL,
        description="Scroll the video horizontally or vertically (credits, ticker effect)",
        parameters=[
            SkillParameter(
                name="direction",
                type=ParameterType.CHOICE,
                description="Scroll direction",
                required=False,
                default="up",
                choices=["up", "down", "left", "right"],
            ),
            SkillParameter(
                name="speed",
                type=ParameterType.FLOAT,
                description="Scroll speed (0.01 = slow, 0.5 = fast)",
                required=False,
                default=0.05,
                min_value=0.01,
                max_value=1.0,
            ),
        ],
        examples=[
            "scroll - Scroll up slowly (credits style)",
            "scroll:direction=right,speed=0.1 - Scroll right (ticker style)",
        ],
        tags=["scroll", "credits", "ticker", "roll", "crawl"],
    ))

    # Perspective correction/warp
    registry.register(Skill(
        name="perspective",
        category=SkillCategory.SPATIAL,
        description="Skew or warp video perspective (tilt, lean)",
        parameters=[
            SkillParameter(
                name="preset",
                type=ParameterType.CHOICE,
                description="Perspective preset",
                required=False,
                default="tilt_forward",
                choices=["tilt_forward", "tilt_back", "lean_left", "lean_right"],
            ),
            SkillParameter(
                name="strength",
                type=ParameterType.FLOAT,
                description="Effect strength (0.0=none, 1.0=maximum)",
                required=False,
                default=0.3,
                min_value=0.0,
                max_value=1.0,
            ),
        ],
        examples=[
            "perspective:preset=tilt_forward - Tilt perspective forward",
            "perspective:preset=lean_left,strength=0.5 - Strong left lean",
        ],
        tags=["skew", "warp", "tilt", "perspective", "transform", "3d"],
    ))

    # Fill borders
    registry.register(Skill(
        name="fill_borders",
        category=SkillCategory.SPATIAL,
        description="Fill black borders (useful after rotation or stabilization)",
        parameters=[
            SkillParameter(
                name="left",
                type=ParameterType.INT,
                description="Left border width in pixels",
                required=False,
                default=10,
                min_value=0,
                max_value=200,
            ),
            SkillParameter(
                name="right",
                type=ParameterType.INT,
                description="Right border width in pixels",
                required=False,
                default=10,
                min_value=0,
                max_value=200,
            ),
            SkillParameter(
                name="top",
                type=ParameterType.INT,
                description="Top border width in pixels",
                required=False,
                default=10,
                min_value=0,
                max_value=200,
            ),
            SkillParameter(
                name="bottom",
                type=ParameterType.INT,
                description="Bottom border width in pixels",
                required=False,
                default=10,
                min_value=0,
                max_value=200,
            ),
            SkillParameter(
                name="mode",
                type=ParameterType.CHOICE,
                description="Fill mode",
                required=False,
                default="smear",
                choices=["smear", "mirror", "fixed", "reflect", "wrap", "fade"],
            ),
        ],
        examples=[
            "fill_borders - Fill 10px borders with smear",
            "fill_borders:left=20,right=20,mode=mirror - Mirror fill on sides",
        ],
        tags=["border", "fill", "edge", "fix", "stabilize", "rotation"],
    ))

    # Deshake (simple stabilization)
    registry.register(Skill(
        name="deshake",
        category=SkillCategory.SPATIAL,
        description="Simple video stabilization to reduce shakiness",
        parameters=[
            SkillParameter(
                name="rx",
                type=ParameterType.INT,
                description="Horizontal search radius (higher = more correction)",
                required=False,
                default=16,
                min_value=1,
                max_value=64,
            ),
            SkillParameter(
                name="ry",
                type=ParameterType.INT,
                description="Vertical search radius (higher = more correction)",
                required=False,
                default=16,
                min_value=1,
                max_value=64,
            ),
            SkillParameter(
                name="edge",
                type=ParameterType.CHOICE,
                description="How to handle edges after correction",
                required=False,
                default="mirror",
                choices=["blank", "original", "clamp", "mirror"],
            ),
        ],
        examples=[
            "deshake - Standard stabilization",
            "deshake:rx=32,ry=32 - Stronger stabilization",
            "deshake:edge=blank - Fill edges with black",
        ],
        tags=["stabilize", "shake", "shaky", "handheld", "fix", "smooth"],
    ))

    # Selective color
    registry.register(Skill(
        name="selective_color",
        category=SkillCategory.VISUAL,
        description="Adjust specific color ranges (like only reds or blues)",
        parameters=[
            SkillParameter(
                name="color_range",
                type=ParameterType.CHOICE,
                description="Color range to adjust",
                required=False,
                default="reds",
                choices=["reds", "yellows", "greens", "cyans", "blues", "magentas",
                         "whites", "neutrals", "blacks"],
            ),
            SkillParameter(
                name="cyan",
                type=ParameterType.FLOAT,
                description="Cyan adjustment (-1 to 1)",
                required=False,
                default=0.0,
                min_value=-1.0,
                max_value=1.0,
            ),
            SkillParameter(
                name="magenta",
                type=ParameterType.FLOAT,
                description="Magenta adjustment (-1 to 1)",
                required=False,
                default=0.0,
                min_value=-1.0,
                max_value=1.0,
            ),
            SkillParameter(
                name="yellow",
                type=ParameterType.FLOAT,
                description="Yellow adjustment (-1 to 1)",
                required=False,
                default=0.0,
                min_value=-1.0,
                max_value=1.0,
            ),
            SkillParameter(
                name="black",
                type=ParameterType.FLOAT,
                description="Black adjustment (-1 to 1)",
                required=False,
                default=0.0,
                min_value=-1.0,
                max_value=1.0,
            ),
        ],
        examples=[
            "selective_color:color_range=reds,cyan=0.5 - Add cyan to red areas",
            "selective_color:color_range=blues,yellow=-0.3 - Deepen blues",
        ],
        tags=["color", "selective", "range", "hue", "adjust", "grade"],
    ))

    # Monochrome tinting
    registry.register(Skill(
        name="monochrome",
        category=SkillCategory.VISUAL,
        description="Convert to monochrome with optional color tint",
        parameters=[
            SkillParameter(
                name="preset",
                type=ParameterType.CHOICE,
                description="Tint preset",
                required=False,
                default="neutral",
                choices=["neutral", "warm", "cool", "sepia_tone", "blue_tone", "green_tone"],
            ),
            SkillParameter(
                name="size",
                type=ParameterType.FLOAT,
                description="Color filter size (larger = more color bleed)",
                required=False,
                default=1.0,
                min_value=0.1,
                max_value=10.0,
            ),
        ],
        examples=[
            "monochrome - Neutral grayscale",
            "monochrome:preset=warm - Warm-tinted monochrome",
            "monochrome:preset=sepia_tone - Sepia-like monochrome",
        ],
        tags=["gray", "grayscale", "tint", "monochrome", "bw", "desaturate"],
    ))

    # Audio waveform visualization
    registry.register(Skill(
        name="waveform",
        category=SkillCategory.VISUAL,
        description="Visualize audio as a waveform overlay on the video",
        parameters=[
            SkillParameter(
                name="mode",
                type=ParameterType.CHOICE,
                description="Waveform drawing mode",
                required=False,
                default="cline",
                choices=["line", "point", "p2p", "cline"],
            ),
            SkillParameter(
                name="height",
                type=ParameterType.INT,
                description="Waveform height in pixels",
                required=False,
                default=200,
                min_value=50,
                max_value=600,
            ),
            SkillParameter(
                name="color",
                type=ParameterType.STRING,
                description="Waveform color (hex or name)",
                required=False,
                default="white",
            ),
            SkillParameter(
                name="position",
                type=ParameterType.CHOICE,
                description="Vertical position of waveform",
                required=False,
                default="bottom",
                choices=["bottom", "center", "top"],
            ),
            SkillParameter(
                name="opacity",
                type=ParameterType.FLOAT,
                description="Waveform opacity (0.0-1.0)",
                required=False,
                default=0.8,
                min_value=0.0,
                max_value=1.0,
            ),
        ],
        examples=[
            "waveform - Show audio waveform at bottom",
            "waveform:mode=line,color=cyan,position=center - Centered line waveform",
            "waveform:height=300,opacity=0.5 - Taller, semi-transparent waveform",
        ],
        tags=["audio", "waveform", "visualize", "music", "podcast", "sound", "showwaves"],
    ))


    # ── Multi-input skills ────────────────────────────────────────────── #

    registry.register(Skill(
        name="grid",
        category=SkillCategory.OUTCOME,
        description="Arrange multiple input images in a grid layout",
        parameters=[
            SkillParameter(
                name="columns",
                type=ParameterType.INT,
                description="Number of columns",
                required=False,
                default=2,
                min_value=1,
                max_value=6,
            ),
            SkillParameter(
                name="gap",
                type=ParameterType.INT,
                description="Gap between images in pixels",
                required=False,
                default=4,
                min_value=0,
                max_value=20,
            ),
            SkillParameter(
                name="duration",
                type=ParameterType.FLOAT,
                description="Output duration in seconds",
                required=False,
                default=5.0,
                min_value=1.0,
                max_value=60.0,
            ),
            SkillParameter(
                name="background",
                type=ParameterType.STRING,
                description="Background color (hex or name)",
                required=False,
                default="black",
            ),
            SkillParameter(
                name="include_video",
                type=ParameterType.BOOL,
                description="Include the main video as the first cell in the grid",
                required=False,
                default=True,
            ),
        ],
        examples=[
            "grid - Arrange video + extra images in a 2-column grid",
            "grid:columns=3,gap=8 - 3-column grid with 8px gap",
            "grid:include_video=false - Grid of only extra images (no video)",
            "grid:columns=4,duration=10,background=white - 4-column grid, 10s",
        ],
        tags=["grid", "mosaic", "collage", "layout", "multi", "images", "xstack"],
    ))


    registry.register(Skill(
        name="slideshow",
        category=SkillCategory.OUTCOME,
        description="Create a slideshow from multiple input images",
        parameters=[
            SkillParameter(
                name="duration_per_image",
                type=ParameterType.FLOAT,
                description="Seconds each image is displayed",
                required=False,
                default=3.0,
                min_value=0.5,
                max_value=30.0,
            ),
            SkillParameter(
                name="transition",
                type=ParameterType.CHOICE,
                description="Transition between images",
                required=False,
                default="fade",
                choices=["none", "fade"],
            ),
            SkillParameter(
                name="transition_duration",
                type=ParameterType.FLOAT,
                description="Transition duration in seconds",
                required=False,
                default=0.5,
                min_value=0.1,
                max_value=3.0,
            ),
            SkillParameter(
                name="width",
                type=ParameterType.INT,
                description="Output width (-1 keeps original)",
                required=False,
                default=1920,
                min_value=-1,
                max_value=3840,
            ),
            SkillParameter(
                name="height",
                type=ParameterType.INT,
                description="Output height (-1 keeps original)",
                required=False,
                default=1080,
                min_value=-1,
                max_value=2160,
            ),
            SkillParameter(
                name="include_video",
                type=ParameterType.BOOL,
                description="Include the main video as the first segment before image slides",
                required=False,
                default=False,
            ),
        ],
        examples=[
            "slideshow - Create slideshow with 3s per image, fade transitions",
            "slideshow:duration_per_image=5,transition=none - 5s per image, no transition",
            "slideshow:include_video=true - Video plays first, then image slides",
            "slideshow:transition_duration=1.0 - Slow fade transitions",
        ],
        tags=["slideshow", "slides", "presentation", "concat", "images", "multi", "sequence"],
    ))


    registry.register(Skill(
        name="overlay_image",
        category=SkillCategory.VISUAL,
        description="Overlay a second input image on top of the video (picture-in-picture)",
        parameters=[
            SkillParameter(
                name="position",
                type=ParameterType.CHOICE,
                description="Position of the overlay",
                required=False,
                default="bottom-right",
                choices=["top-left", "top-right", "bottom-left", "bottom-right", "center"],
            ),
            SkillParameter(
                name="scale",
                type=ParameterType.FLOAT,
                description="Scale of overlay relative to video (0.1-0.5)",
                required=False,
                default=0.25,
                min_value=0.05,
                max_value=0.8,
            ),
            SkillParameter(
                name="opacity",
                type=ParameterType.FLOAT,
                description="Overlay opacity (0.0-1.0)",
                required=False,
                default=1.0,
                min_value=0.0,
                max_value=1.0,
            ),
            SkillParameter(
                name="margin",
                type=ParameterType.INT,
                description="Margin from edge in pixels",
                required=False,
                default=10,
                min_value=0,
                max_value=100,
            ),
        ],
        examples=[
            "overlay_image - Overlay image in bottom-right corner at 25% scale",
            "overlay_image:position=top-left,scale=0.15,margin=20 - Small top-left logo",
            "overlay_image:opacity=0.7,position=center,scale=0.5 - Semi-transparent centered overlay",
            "overlay_image:scale=0.2 - Multiple images auto-placed in corners (connect image_a + image_b)",
        ],
        tags=["overlay", "pip", "picture-in-picture", "watermark", "logo", "stamp", "multi"],
    ))

    # ----- Enhanced effects (using advanced FFMPEG filters) ----- #

    # Glow / bloom effect
    registry.register(Skill(
        name="glow",
        category=SkillCategory.VISUAL,
        description="Bloom / soft glow effect (split → blur → screen blend)",
        parameters=[
            SkillParameter(
                name="radius",
                type=ParameterType.FLOAT,
                description="Blur radius for the glow (5-60)",
                required=False,
                default=30,
                min_value=5,
                max_value=60,
            ),
            SkillParameter(
                name="strength",
                type=ParameterType.FLOAT,
                description="Glow blend strength (0.1-0.8)",
                required=False,
                default=0.4,
                min_value=0.1,
                max_value=0.8,
            ),
        ],
        examples=[
            "glow - Soft bloom glow",
            "glow:radius=50,strength=0.6 - Strong dreamy glow",
            "glow:radius=10,strength=0.2 - Subtle halo",
        ],
        tags=["glow", "bloom", "soft", "dreamy", "halo", "light", "ethereal"],
    ))

    # Ghost trail / afterimage
    registry.register(Skill(
        name="ghost_trail",
        category=SkillCategory.VISUAL,
        description="Temporal trailing / afterimage effect (ghostly motion trails)",
        parameters=[
            SkillParameter(
                name="decay",
                type=ParameterType.FLOAT,
                description="Trail persistence (0.9=short, 0.99=long)",
                required=False,
                default=0.97,
                min_value=0.9,
                max_value=0.995,
            ),
        ],
        examples=[
            "ghost_trail - Motion afterimage trails",
            "ghost_trail:decay=0.99 - Long persistent trails",
            "ghost_trail:decay=0.92 - Brief ghost effect",
        ],
        tags=["ghost", "trail", "afterimage", "echo", "phantom", "motion", "persistence"],
    ))

    # Tilt-shift miniature
    registry.register(Skill(
        name="tilt_shift",
        category=SkillCategory.VISUAL,
        description="Real tilt-shift miniature effect with selective blur",
        parameters=[
            SkillParameter(
                name="focus_position",
                type=ParameterType.FLOAT,
                description="Vertical position of sharp band (0=top, 1=bottom)",
                required=False,
                default=0.5,
                min_value=0.1,
                max_value=0.9,
            ),
            SkillParameter(
                name="blur_amount",
                type=ParameterType.FLOAT,
                description="Blur strength for out-of-focus areas (2-20)",
                required=False,
                default=8,
                min_value=2,
                max_value=20,
            ),
        ],
        examples=[
            "tilt_shift - Miniature/toy model look",
            "tilt_shift:focus_position=0.3,blur_amount=12 - Focus near top, strong blur",
        ],
        tags=["tilt_shift", "miniature", "toy", "model", "diorama", "selective_blur", "focus"],
    ))

    # Frame blend / motion blur
    registry.register(Skill(
        name="frame_blend",
        category=SkillCategory.SPATIAL,
        description="Temporal frame blending for dreamy motion blur",
        parameters=[
            SkillParameter(
                name="frames",
                type=ParameterType.INT,
                description="Number of frames to blend together (2-10)",
                required=False,
                default=5,
                min_value=2,
                max_value=10,
            ),
        ],
        examples=[
            "frame_blend - Dreamy motion blur (5 frames)",
            "frame_blend:frames=3 - Subtle motion blur",
            "frame_blend:frames=10 - Heavy long-exposure look",
        ],
        tags=["motion_blur", "blend", "dreamy", "smooth", "long_exposure", "temporal"],
    ))

    # Chromatic aberration
    registry.register(Skill(
        name="chromatic_aberration",
        category=SkillCategory.VISUAL,
        description="RGB channel offset for chromatic aberration / color fringing",
        parameters=[
            SkillParameter(
                name="amount",
                type=ParameterType.INT,
                description="Pixel offset of color channels (1-20)",
                required=False,
                default=4,
                min_value=1,
                max_value=20,
            ),
        ],
        examples=[
            "chromatic_aberration - Subtle color fringing",
            "chromatic_aberration:amount=10 - Strong RGB split",
            "chromatic_aberration:amount=2 - Barely visible fringe",
        ],
        tags=["chromatic", "aberration", "rgb", "split", "fringe", "lens", "distortion", "glitch"],
    ))

    # Sketch / line art
    registry.register(Skill(
        name="sketch",
        category=SkillCategory.VISUAL,
        description="Pencil drawing / ink line art effect using edge detection",
        parameters=[
            SkillParameter(
                name="mode",
                type=ParameterType.CHOICE,
                description="Drawing style",
                required=False,
                default="pencil",
                choices=["pencil", "ink", "color"],
            ),
        ],
        examples=[
            "sketch - Pencil drawing effect",
            "sketch:mode=ink - Bold ink outline",
            "sketch:mode=color - Colored edge detection",
        ],
        tags=["sketch", "pencil", "drawing", "line_art", "ink", "outline", "edges", "artistic"],
    ))

    # Watermark
    registry.register(Skill(
        name="watermark",
        category=SkillCategory.OUTCOME,
        description="Add a semi-transparent watermark overlay in a corner. Requires an extra image input (image_a).",
        parameters=[
            SkillParameter(
                name="position",
                type=ParameterType.CHOICE,
                description="Where to place the watermark",
                required=False,
                default="bottom-right",
                choices=["top-left", "top-right", "bottom-left", "bottom-right", "center"],
            ),
            SkillParameter(
                name="opacity",
                type=ParameterType.FLOAT,
                description="Watermark transparency (0.0 = invisible, 1.0 = fully opaque)",
                required=False,
                default=0.3,
                min_value=0.05,
                max_value=1.0,
            ),
            SkillParameter(
                name="scale",
                type=ParameterType.FLOAT,
                description="Watermark size relative to video (0.1 = 10% of video width)",
                required=False,
                default=0.15,
                min_value=0.05,
                max_value=0.5,
            ),
        ],
        examples=[
            "watermark - Semi-transparent watermark in bottom-right corner",
            "watermark:position=top-left,opacity=0.5 - More visible watermark in top left",
            "watermark:scale=0.25 - Larger watermark",
        ],
        tags=["watermark", "logo", "brand", "overlay", "stamp", "copyright"],
    ))

    # Chroma key (green screen)
    registry.register(Skill(
        name="chromakey",
        category=SkillCategory.VISUAL,
        description="Remove a solid-color background (chroma key / green screen removal)",
        parameters=[
            SkillParameter(
                name="color",
                type=ParameterType.STRING,
                description="Hex color to remove (default 0x00FF00 = green)",
                required=False,
                default="0x00FF00",
            ),
            SkillParameter(
                name="similarity",
                type=ParameterType.FLOAT,
                description="How similar a color must be to key out (0.0 = exact, 1.0 = very loose)",
                required=False,
                default=0.3,
                min_value=0.01,
                max_value=1.0,
            ),
            SkillParameter(
                name="blend",
                type=ParameterType.FLOAT,
                description="Edge blending for smoother keying (0.0 = hard edge, 1.0 = very soft)",
                required=False,
                default=0.1,
                min_value=0.0,
                max_value=1.0,
            ),
            SkillParameter(
                name="background",
                type=ParameterType.STRING,
                description="Replacement background color or 'transparent' for alpha output",
                required=False,
                default="black",
            ),
        ],
        examples=[
            "chromakey - Remove green screen with default settings",
            "chromakey:color=0x0000FF - Remove blue screen",
            "chromakey:similarity=0.5,blend=0.2 - Looser key with soft edges",
            "chromakey:background=white - Replace green with white",
        ],
        tags=["chroma", "key", "green_screen", "blue_screen", "remove_background", "transparent", "keying"],
    ))

    # Color key (general-purpose key out any color)
    registry.register(Skill(
        name="colorkey",
        category=SkillCategory.VISUAL,
        description="Key out any arbitrary color and replace with a background (general-purpose color removal)",
        parameters=[
            SkillParameter(
                name="color",
                type=ParameterType.STRING,
                description="Hex color to key out (e.g. '0xFF0000' for red, '0x00FF00' for green)",
                required=False,
                default="0x00FF00",
            ),
            SkillParameter(
                name="similarity",
                type=ParameterType.FLOAT,
                description="How similar a color must be to key out (0.0 = exact, 1.0 = very loose)",
                required=False,
                default=0.3,
                min_value=0.01,
                max_value=1.0,
            ),
            SkillParameter(
                name="blend",
                type=ParameterType.FLOAT,
                description="Edge blending for smoother keying (0.0 = hard edge, 1.0 = very soft)",
                required=False,
                default=0.1,
                min_value=0.0,
                max_value=1.0,
            ),
            SkillParameter(
                name="background",
                type=ParameterType.STRING,
                description="Replacement background color or 'transparent' for alpha output",
                required=False,
                default="black",
            ),
        ],
        examples=[
            "colorkey:color=0xFF0000 - Remove red background",
            "colorkey:color=0xFFFFFF,similarity=0.2 - Remove white background",
            "colorkey:background=transparent - Output with alpha channel",
        ],
        tags=["color", "key", "remove", "background", "mask", "transparent", "keying"],
    ))

    # Luma key (key out by brightness)
    registry.register(Skill(
        name="lumakey",
        category=SkillCategory.VISUAL,
        description="Key out regions based on brightness (luma). Remove dark or bright areas.",
        parameters=[
            SkillParameter(
                name="threshold",
                type=ParameterType.FLOAT,
                description="Luma value to key out (0.0 = black, 1.0 = white)",
                required=False,
                default=0.0,
                min_value=0.0,
                max_value=1.0,
            ),
            SkillParameter(
                name="tolerance",
                type=ParameterType.FLOAT,
                description="Range around threshold to also key out",
                required=False,
                default=0.1,
                min_value=0.0,
                max_value=1.0,
            ),
            SkillParameter(
                name="softness",
                type=ParameterType.FLOAT,
                description="Edge softness (0 = hard, 1 = very soft)",
                required=False,
                default=0.0,
                min_value=0.0,
                max_value=1.0,
            ),
            SkillParameter(
                name="background",
                type=ParameterType.STRING,
                description="Replacement background color or 'transparent'",
                required=False,
                default="black",
            ),
        ],
        examples=[
            "lumakey - Remove black background",
            "lumakey:threshold=1.0,tolerance=0.2 - Remove white background",
            "lumakey:threshold=0.0,tolerance=0.3,softness=0.2 - Soft black key",
        ],
        tags=["luma", "key", "brightness", "black", "white", "mask", "background", "transparent"],
    ))

    # Color hold (sin-city effect — keep one color, desaturate rest)
    registry.register(Skill(
        name="colorhold",
        category=SkillCategory.VISUAL,
        description="Keep only a selected color while desaturating everything else (sin-city / spot color effect)",
        parameters=[
            SkillParameter(
                name="color",
                type=ParameterType.STRING,
                description="Hex color to preserve (e.g. '0xFF0000' for red)",
                required=False,
                default="0xFF0000",
            ),
            SkillParameter(
                name="similarity",
                type=ParameterType.FLOAT,
                description="How close to the held color counts (0.0 = exact, 1.0 = very loose)",
                required=False,
                default=0.3,
                min_value=0.01,
                max_value=1.0,
            ),
            SkillParameter(
                name="blend",
                type=ParameterType.FLOAT,
                description="Edge blend between held color and desaturated areas",
                required=False,
                default=0.1,
                min_value=0.0,
                max_value=1.0,
            ),
        ],
        examples=[
            "colorhold - Keep red, desaturate rest (sin-city effect)",
            "colorhold:color=0x0000FF - Keep blue, desaturate rest",
            "colorhold:color=0xFFFF00,similarity=0.4 - Keep yellow tones",
        ],
        tags=["color", "hold", "sin_city", "spot_color", "selective", "desaturate", "mask", "effect"],
    ))

    # Despill (clean color spill from chroma key edges)
    registry.register(Skill(
        name="despill",
        category=SkillCategory.VISUAL,
        description="Remove green/blue color spill from chroma-keyed footage edges",
        parameters=[
            SkillParameter(
                name="type",
                type=ParameterType.CHOICE,
                description="Spill color to remove",
                required=False,
                default="green",
                choices=["green", "blue"],
            ),
            SkillParameter(
                name="mix",
                type=ParameterType.FLOAT,
                description="Spill removal mix factor (0.0 = none, 1.0 = full)",
                required=False,
                default=0.5,
                min_value=0.0,
                max_value=1.0,
            ),
            SkillParameter(
                name="expand",
                type=ParameterType.FLOAT,
                description="How far spill correction extends (0.0 = minimal, 1.0 = wide)",
                required=False,
                default=0.0,
                min_value=0.0,
                max_value=1.0,
            ),
            SkillParameter(
                name="brightness",
                type=ParameterType.FLOAT,
                description="Brightness correction for despill areas",
                required=False,
                default=0.0,
                min_value=-1.0,
                max_value=1.0,
            ),
        ],
        examples=[
            "despill - Remove green spill (after chromakey)",
            "despill:type=blue - Remove blue spill",
            "despill:mix=0.8,expand=0.3 - Aggressive despill with wider reach",
        ],
        tags=["despill", "spill", "chroma", "key", "edge", "cleanup", "green", "blue"],
    ))

    # Remove background (rembg-based, optional dependency)
    registry.register(Skill(
        name="remove_background",
        category=SkillCategory.VISUAL,
        description="Remove arbitrary backgrounds using AI (rembg). Requires optional masking dependency.",
        parameters=[
            SkillParameter(
                name="model",
                type=ParameterType.CHOICE,
                description="AI model for background removal",
                required=False,
                default="silueta",
                choices=["silueta", "u2net", "birefnet-general"],
            ),
            SkillParameter(
                name="background",
                type=ParameterType.STRING,
                description="Replacement background color or 'transparent'",
                required=False,
                default="transparent",
            ),
        ],
        examples=[
            "remove_background - Remove background (fast silueta model)",
            "remove_background:model=birefnet-general - High quality background removal",
            "remove_background:background=white - Replace background with white",
        ],
        tags=["remove", "background", "mask", "ai", "rembg", "segment", "cutout", "transparent"],
    ))

    # Concat
    registry.register(Skill(
        name="concat",
        category=SkillCategory.OUTCOME,
        description="Concatenate (append) video segments sequentially. Requires extra image inputs (image_a, image_b, ...) which become additional segments.",
        parameters=[
            SkillParameter(
                name="width",
                type=ParameterType.INT,
                description="Output width",
                required=False,
                default=1920,
            ),
            SkillParameter(
                name="height",
                type=ParameterType.INT,
                description="Output height",
                required=False,
                default=1080,
            ),
            SkillParameter(
                name="still_duration",
                type=ParameterType.FLOAT,
                description="Duration for each still image segment (seconds)",
                required=False,
                default=5.0,
            ),
        ],
        examples=[
            "concat - Join main video with extra inputs",
            "concat:still_duration=3 - Shorter still image segments",
        ],
        tags=["concat", "join", "append", "combine", "merge", "sequence"],
    ))

    # xfade (transition)
    registry.register(Skill(
        name="xfade",
        category=SkillCategory.OUTCOME,
        description="Concatenate segments with smooth xfade transitions (fade, dissolve, wipe, slide, pixelize, radial). Requires extra image inputs.",
        parameters=[
            SkillParameter(
                name="transition",
                type=ParameterType.CHOICE,
                description="Transition effect type",
                required=False,
                default="fade",
                choices=[
                    "fade", "fadeblack", "fadewhite", "wipeleft", "wiperight",
                    "wipeup", "wipedown", "slideleft", "slideright",
                    "dissolve", "pixelize", "radial", "circlecrop",
                    "smoothleft", "smoothright", "squeezev", "squeezeh",
                ],
            ),
            SkillParameter(
                name="duration",
                type=ParameterType.FLOAT,
                description="Transition duration in seconds",
                required=False,
                default=1.0,
                min_value=0.1,
                max_value=5.0,
            ),
            SkillParameter(
                name="still_duration",
                type=ParameterType.FLOAT,
                description="Display time per segment in seconds",
                required=False,
                default=4.0,
            ),
        ],
        examples=[
            "xfade - Smooth crossfade between segments",
            "xfade:transition=dissolve,duration=2 - Slow dissolve",
            "xfade:transition=wipeleft - Left wipe transition",
            "xfade:transition=pixelize - Pixelated transition",
        ],
        tags=["xfade", "transition", "crossfade", "dissolve", "wipe", "slide"],
    ))

    # Split screen
    registry.register(Skill(
        name="split_screen",
        category=SkillCategory.VISUAL,
        description="Show videos/images side-by-side (horizontal) or stacked (vertical). Requires extra image inputs.",
        parameters=[
            SkillParameter(
                name="layout",
                type=ParameterType.CHOICE,
                description="Layout direction",
                required=False,
                default="horizontal",
                choices=["horizontal", "vertical"],
            ),
            SkillParameter(
                name="width",
                type=ParameterType.INT,
                description="Per-cell width",
                required=False,
                default=960,
            ),
            SkillParameter(
                name="height",
                type=ParameterType.INT,
                description="Per-cell height",
                required=False,
                default=540,
            ),
            SkillParameter(
                name="duration",
                type=ParameterType.FLOAT,
                description="Output duration in seconds",
                required=False,
                default=10.0,
            ),
        ],
        examples=[
            "split_screen - Side-by-side view",
            "split_screen:layout=vertical - Top and bottom",
            "split_screen:width=640,height=480 - Custom cell size",
        ],
        tags=["split", "screen", "side_by_side", "dual", "comparison", "hstack", "vstack"],
    ))

    # Animated overlay
    registry.register(Skill(
        name="animated_overlay",
        category=SkillCategory.VISUAL,
        description="Overlay an image with animated motion (scroll, float, bounce, slide). Requires image_a as the overlay image.",
        parameters=[
            SkillParameter(
                name="animation",
                type=ParameterType.CHOICE,
                description="Motion animation type",
                required=False,
                default="scroll_right",
                choices=[
                    "scroll_right", "scroll_left", "scroll_up", "scroll_down",
                    "float", "bounce", "slide_in", "slide_in_top",
                ],
            ),
            SkillParameter(
                name="speed",
                type=ParameterType.FLOAT,
                description="Motion speed multiplier",
                required=False,
                default=1.0,
                min_value=0.1,
                max_value=10.0,
            ),
            SkillParameter(
                name="scale",
                type=ParameterType.FLOAT,
                description="Overlay size relative to video (0.1 = 10% width)",
                required=False,
                default=0.2,
                min_value=0.05,
                max_value=1.0,
            ),
            SkillParameter(
                name="opacity",
                type=ParameterType.FLOAT,
                description="Overlay opacity (0.0 = invisible, 1.0 = opaque)",
                required=False,
                default=1.0,
                min_value=0.0,
                max_value=1.0,
            ),
        ],
        examples=[
            "animated_overlay - Scrolling overlay from left to right",
            "animated_overlay:animation=float,speed=0.5 - Slow floating effect",
            "animated_overlay:animation=bounce - Bouncing overlay",
            "animated_overlay:animation=slide_in - Slide in from left edge",
        ],
        tags=["animated", "overlay", "scroll", "float", "bounce", "slide", "motion", "moving"],
    ))

    # Text overlay
    registry.register(Skill(
        name="text_overlay",
        category=SkillCategory.OUTCOME,
        description="Draw text on the video with style presets (title, subtitle, lower_third, caption)",
        parameters=[
            SkillParameter(
                name="text",
                type=ParameterType.STRING,
                description="Text to display",
                required=True,
            ),
            SkillParameter(
                name="preset",
                type=ParameterType.CHOICE,
                description="Style preset",
                required=False,
                default="title",
                choices=["title", "subtitle", "lower_third", "caption", "top"],
            ),
            SkillParameter(
                name="fontsize",
                type=ParameterType.INT,
                description="Font size in pixels (auto if not set)",
                required=False,
                default=None,
            ),
            SkillParameter(
                name="fontcolor",
                type=ParameterType.STRING,
                description="Text color",
                required=False,
                default="white",
            ),
            SkillParameter(
                name="start",
                type=ParameterType.FLOAT,
                description="Start time in seconds",
                required=False,
                default=0.0,
            ),
            SkillParameter(
                name="duration",
                type=ParameterType.FLOAT,
                description="Display duration in seconds (0 = entire video)",
                required=False,
                default=0.0,
            ),
            SkillParameter(
                name="background",
                type=ParameterType.STRING,
                description="Background box color (empty = no background)",
                required=False,
                default="",
            ),
        ],
        examples=[
            "text_overlay:text=My Video - Centered title",
            "text_overlay:text=Scene 1,preset=lower_third - Lower third text",
            "text_overlay:text=Hello,preset=subtitle,fontcolor=yellow - Yellow subtitle",
            "text_overlay:text=Breaking News,background=red@0.7,fontsize=48 - News-style banner",
        ],
        tags=["text", "title", "subtitle", "caption", "drawtext", "overlay", "typography", "lower_third"],
    ))

    # Delogo — remove watermark/logo
    registry.register(Skill(
        name="delogo",
        category=SkillCategory.VISUAL,
        description="Remove or obscure a watermark/logo from a fixed region of the video",
        parameters=[
            SkillParameter(
                name="x",
                type=ParameterType.INT,
                description="X position of the logo region (pixels from left)",
                required=True,
                default=10,
            ),
            SkillParameter(
                name="y",
                type=ParameterType.INT,
                description="Y position of the logo region (pixels from top)",
                required=True,
                default=10,
            ),
            SkillParameter(
                name="w",
                type=ParameterType.INT,
                description="Width of the logo region in pixels",
                required=True,
                default=100,
            ),
            SkillParameter(
                name="h",
                type=ParameterType.INT,
                description="Height of the logo region in pixels",
                required=True,
                default=40,
            ),
        ],
        ffmpeg_template="delogo=x={x}:y={y}:w={w}:h={h}",
        examples=[
            "delogo:x=10,y=10,w=100,h=40 - Remove logo at top-left corner",
            "delogo:x=1700,y=50,w=200,h=60 - Remove watermark at top-right (1080p)",
        ],
        tags=["watermark", "logo", "remove", "clean", "copyright"],
    ))

    # Remove duplicate frames — clean stuttery footage
    registry.register(Skill(
        name="remove_dup_frames",
        category=SkillCategory.TEMPORAL,
        description="Remove duplicate/near-duplicate frames (fix stuttery or low-FPS footage)",
        parameters=[
            SkillParameter(
                name="max_drop",
                type=ParameterType.INT,
                description="Max consecutive frames to drop (0 = unlimited)",
                required=False,
                default=0,
                min_value=0,
                max_value=100,
            ),
        ],
        ffmpeg_template="mpdecimate=max={max_drop},setpts=N/FRAME_RATE/TB",
        examples=[
            "remove_dup_frames - Remove all duplicate frames",
            "remove_dup_frames:max_drop=5 - Drop up to 5 consecutive duplicates",
        ],
        tags=["duplicate", "stutter", "clean", "fps", "decimate", "fix"],
    ))

    # Mask blur — blur a region (privacy)
    registry.register(Skill(
        name="mask_blur",
        category=SkillCategory.VISUAL,
        description="Blur a rectangular region of the video (face/plate privacy)",
        parameters=[
            SkillParameter(
                name="x",
                type=ParameterType.INT,
                description="X position of blur region",
                required=True,
                default=100,
            ),
            SkillParameter(
                name="y",
                type=ParameterType.INT,
                description="Y position of blur region",
                required=True,
                default=100,
            ),
            SkillParameter(
                name="w",
                type=ParameterType.INT,
                description="Width of blur region in pixels",
                required=True,
                default=200,
            ),
            SkillParameter(
                name="h",
                type=ParameterType.INT,
                description="Height of blur region in pixels",
                required=True,
                default=200,
            ),
            SkillParameter(
                name="strength",
                type=ParameterType.INT,
                description="Blur strength (higher = more blur)",
                required=False,
                default=20,
                min_value=1,
                max_value=100,
            ),
        ],
        # mask_blur needs filter_complex syntax (split/overlay); handled in composer.py
        examples=[
            "mask_blur:x=500,y=200,w=150,h=150 - Blur a face region",
            "mask_blur:x=100,y=600,w=300,h=80,strength=40 - Heavy blur on license plate",
        ],
        tags=["blur", "mask", "privacy", "face", "censor", "region", "plate"],
    ))

    # LUT apply — load .cube/.3dl LUT file
    registry.register(Skill(
        name="lut_apply",
        category=SkillCategory.VISUAL,
        description="Apply a color LUT file (.cube or .3dl) for professional color grading",
        parameters=[
            SkillParameter(
                name="path",
                type=ParameterType.STRING,
                description="Path to the .cube or .3dl LUT file",
                required=True,
            ),
            SkillParameter(
                name="intensity",
                type=ParameterType.FLOAT,
                description="LUT blend intensity (0.0=none, 1.0=full LUT)",
                required=False,
                default=1.0,
                min_value=0.0,
                max_value=1.0,
            ),
        ],
        # lut_apply with intensity blending requires filter_complex; handled in composer.py
        examples=[
            "lut_apply:path=/path/to/grade.cube - Apply a .cube LUT",
            "lut_apply:path=cinematic.3dl - Apply a 3DL LUT",
        ],
        tags=["lut", "cube", "3dl", "grade", "color", "professional", "cinema", "look"],
    ))

    # ── Phase 2: Handler-based skills ──────────────────────────────── #
    # These have Python handlers in composer.py for filter_complex support.

    # Picture-in-picture
    registry.register(Skill(
        name="picture_in_picture",
        category=SkillCategory.VISUAL,
        description="Overlay a second video in a corner (picture-in-picture / PiP)",
        parameters=[
            SkillParameter(
                name="position",
                type=ParameterType.CHOICE,
                description="Corner position for the overlay",
                required=False,
                default="bottom_right",
                choices=["bottom_right", "bottom_left", "top_right", "top_left", "center"],
            ),
            SkillParameter(
                name="scale",
                type=ParameterType.FLOAT,
                description="Scale of the overlay (0.25 = quarter size)",
                required=False,
                default=0.25,
                min_value=0.05,
                max_value=1.0,
            ),
            SkillParameter(
                name="margin",
                type=ParameterType.INT,
                description="Margin from edge in pixels",
                required=False,
                default=20,
                min_value=0,
                max_value=200,
            ),
        ],
        examples=[
            "picture_in_picture - PiP in bottom-right corner",
            "picture_in_picture:position=top_left,scale=0.3 - Larger PiP top-left",
        ],
        tags=["pip", "picture", "overlay", "corner", "webcam", "inset", "compositing"],
    ))

    # Blend / double exposure
    registry.register(Skill(
        name="blend",
        category=SkillCategory.VISUAL,
        description="Blend two video inputs together (double exposure, multiply, screen, etc.)",
        parameters=[
            SkillParameter(
                name="mode",
                type=ParameterType.CHOICE,
                description="Blend mode",
                required=False,
                default="addition",
                choices=["addition", "multiply", "screen", "overlay", "darken", "lighten", "softlight", "hardlight"],
            ),
            SkillParameter(
                name="opacity",
                type=ParameterType.FLOAT,
                description="Blend opacity (0.0-1.0)",
                required=False,
                default=0.5,
                min_value=0.0,
                max_value=1.0,
            ),
        ],
        examples=[
            "blend:mode=screen,opacity=0.6 - Dreamy screen blend",
            "blend:mode=multiply,opacity=0.4 - Dark multiply blend",
        ],
        tags=["blend", "double_exposure", "composite", "mix", "layer", "screen", "multiply"],
    ))

    # Burn subtitles
    registry.register(Skill(
        name="burn_subtitles",
        category=SkillCategory.OUTCOME,
        description="Hardcode/burn subtitles from .srt or .ass file into the video",
        parameters=[
            SkillParameter(
                name="path",
                type=ParameterType.STRING,
                description="Path to subtitle file (.srt, .ass, .ssa)",
                required=True,
            ),
            SkillParameter(
                name="fontsize",
                type=ParameterType.INT,
                description="Font size in pixels",
                required=False,
                default=24,
                min_value=8,
                max_value=200,
            ),
            SkillParameter(
                name="fontcolor",
                type=ParameterType.STRING,
                description="Font color",
                required=False,
                default="white",
            ),
        ],
        examples=[
            "burn_subtitles:path=subs.srt - Burn SRT subtitles",
            "burn_subtitles:path=captions.ass,fontsize=32 - Large ASS subtitles",
        ],
        tags=["subtitle", "burn", "hardcode", "srt", "ass", "caption", "text"],
    ))

    # Countdown timer
    registry.register(Skill(
        name="countdown",
        category=SkillCategory.OUTCOME,
        description="Animated countdown timer overlay on the video",
        parameters=[
            SkillParameter(
                name="start_from",
                type=ParameterType.INT,
                description="Number to start counting down from",
                required=False,
                default=10,
                min_value=1,
                max_value=999,
            ),
            SkillParameter(
                name="fontsize",
                type=ParameterType.INT,
                description="Font size",
                required=False,
                default=96,
                min_value=12,
                max_value=300,
            ),
            SkillParameter(
                name="fontcolor",
                type=ParameterType.STRING,
                description="Font color",
                required=False,
                default="white",
            ),
        ],
        examples=[
            "countdown - 10 second countdown",
            "countdown:start_from=5,fontsize=120 - 5 second large countdown",
        ],
        tags=["countdown", "timer", "count", "number", "overlay", "animation"],
    ))

    # Animated text
    registry.register(Skill(
        name="animated_text",
        category=SkillCategory.OUTCOME,
        description="Text overlay with animation effects (fade in, slide, typewriter)",
        parameters=[
            SkillParameter(
                name="text",
                type=ParameterType.STRING,
                description="Text to display",
                required=True,
            ),
            SkillParameter(
                name="animation",
                type=ParameterType.CHOICE,
                description="Animation style",
                required=False,
                default="fade_in",
                choices=["fade_in", "slide_up", "slide_down", "typewriter"],
            ),
            SkillParameter(
                name="fontsize",
                type=ParameterType.INT,
                description="Font size",
                required=False,
                default=64,
                min_value=12,
                max_value=300,
            ),
            SkillParameter(
                name="fontcolor",
                type=ParameterType.STRING,
                description="Font color",
                required=False,
                default="white",
            ),
            SkillParameter(
                name="start",
                type=ParameterType.FLOAT,
                description="Start time in seconds",
                required=False,
                default=0,
            ),
            SkillParameter(
                name="duration",
                type=ParameterType.FLOAT,
                description="Duration in seconds",
                required=False,
                default=3,
            ),
        ],
        examples=[
            "animated_text:text=Welcome,animation=fade_in - Fade in text",
            "animated_text:text=Chapter 1,animation=slide_up,duration=5 - Slide up title",
        ],
        tags=["animated", "text", "fade", "slide", "typewriter", "motion", "title"],
    ))

    # Scrolling text (credits roll)
    registry.register(Skill(
        name="scrolling_text",
        category=SkillCategory.OUTCOME,
        description="Vertical scrolling text overlay (credits roll, end card)",
        parameters=[
            SkillParameter(
                name="text",
                type=ParameterType.STRING,
                description="Text to scroll (use \\n for line breaks)",
                required=True,
            ),
            SkillParameter(
                name="speed",
                type=ParameterType.INT,
                description="Scroll speed in pixels per second",
                required=False,
                default=60,
                min_value=10,
                max_value=500,
            ),
            SkillParameter(
                name="fontsize",
                type=ParameterType.INT,
                description="Font size",
                required=False,
                default=36,
                min_value=12,
                max_value=200,
            ),
            SkillParameter(
                name="fontcolor",
                type=ParameterType.STRING,
                description="Font color",
                required=False,
                default="white",
            ),
        ],
        examples=[
            "scrolling_text:text=Directed by\\nJohn Doe - Credits scroll",
            "scrolling_text:text=Thank you!,speed=30 - Slow scroll",
        ],
        tags=["scroll", "credits", "roll", "vertical", "end", "text"],
    ))

    # Ticker (horizontal scroll)
    registry.register(Skill(
        name="ticker",
        category=SkillCategory.OUTCOME,
        description="Horizontal scrolling text bar (news ticker, banner)",
        parameters=[
            SkillParameter(
                name="text",
                type=ParameterType.STRING,
                description="Ticker text",
                required=True,
            ),
            SkillParameter(
                name="speed",
                type=ParameterType.INT,
                description="Scroll speed in pixels per second",
                required=False,
                default=100,
                min_value=20,
                max_value=1000,
            ),
            SkillParameter(
                name="fontsize",
                type=ParameterType.INT,
                description="Font size",
                required=False,
                default=32,
                min_value=12,
                max_value=100,
            ),
            SkillParameter(
                name="fontcolor",
                type=ParameterType.STRING,
                description="Font color",
                required=False,
                default="white",
            ),
            SkillParameter(
                name="background",
                type=ParameterType.STRING,
                description="Background color (e.g. black@0.6)",
                required=False,
                default="black@0.6",
            ),
        ],
        examples=[
            "ticker:text=Breaking News: Stock market surges - News ticker",
            "ticker:text=Subscribe!,speed=50,fontcolor=yellow - Slow yellow ticker",
        ],
        tags=["ticker", "horizontal", "scroll", "news", "banner", "bar", "crawl"],
    ))

    # Lower third
    registry.register(Skill(
        name="lower_third",
        category=SkillCategory.OUTCOME,
        description="Professional lower third name plate with optional subtitle",
        parameters=[
            SkillParameter(
                name="text",
                type=ParameterType.STRING,
                description="Main text (e.g. person name)",
                required=True,
            ),
            SkillParameter(
                name="subtext",
                type=ParameterType.STRING,
                description="Secondary text (e.g. title/role)",
                required=False,
                default="",
            ),
            SkillParameter(
                name="fontsize",
                type=ParameterType.INT,
                description="Font size",
                required=False,
                default=36,
                min_value=16,
                max_value=100,
            ),
            SkillParameter(
                name="fontcolor",
                type=ParameterType.STRING,
                description="Font color",
                required=False,
                default="white",
            ),
            SkillParameter(
                name="background",
                type=ParameterType.STRING,
                description="Background color",
                required=False,
                default="black@0.7",
            ),
            SkillParameter(
                name="start",
                type=ParameterType.FLOAT,
                description="Start time in seconds",
                required=False,
                default=0,
            ),
            SkillParameter(
                name="duration",
                type=ParameterType.FLOAT,
                description="Display duration in seconds",
                required=False,
                default=5,
            ),
        ],
        examples=[
            "lower_third:text=John Doe,subtext=CEO - Name plate with title",
            "lower_third:text=Jane Smith,start=5,duration=8 - Timed lower third",
        ],
        tags=["lower_third", "name", "plate", "title", "interview", "identification"],
    ))

    # Jump cut
    registry.register(Skill(
        name="jump_cut",
        category=SkillCategory.TEMPORAL,
        description="Auto-create jump cuts by removing static/still segments",
        parameters=[
            SkillParameter(
                name="threshold",
                type=ParameterType.FLOAT,
                description="Scene-change threshold (lower = more cuts)",
                required=False,
                default=0.03,
                min_value=0.001,
                max_value=0.5,
            ),
        ],
        examples=[
            "jump_cut - Auto jump cut (default sensitivity)",
            "jump_cut:threshold=0.01 - Very aggressive jump cutting",
        ],
        tags=["jump", "cut", "auto", "edit", "static", "remove", "vlog"],
    ))

    # Beat sync
    registry.register(Skill(
        name="beat_sync",
        category=SkillCategory.TEMPORAL,
        description="Volume-based beat detection — keep only frames on audio peaks",
        parameters=[
            SkillParameter(
                name="threshold",
                type=ParameterType.FLOAT,
                description="Volume threshold (0.0-1.0, higher = fewer cuts)",
                required=False,
                default=0.1,
                min_value=0.01,
                max_value=1.0,
            ),
        ],
        examples=[
            "beat_sync - Sync cuts to audio beats",
            "beat_sync:threshold=0.3 - Only keep loud beats",
        ],
        tags=["beat", "sync", "rhythm", "music", "edit", "auto", "cuts"],
    ))

    # ── Phase 3: Text animation extras & utility ───────────────── #

    # Typewriter text
    registry.register(Skill(
        name="typewriter_text",
        category=SkillCategory.OUTCOME,
        description="Character-by-character typewriter text reveal animation",
        parameters=[
            SkillParameter(
                name="text",
                type=ParameterType.STRING,
                description="Text to reveal",
                required=True,
            ),
            SkillParameter(
                name="speed",
                type=ParameterType.FLOAT,
                description="Characters per second",
                required=False,
                default=5,
                min_value=1,
                max_value=30,
            ),
            SkillParameter(
                name="fontsize",
                type=ParameterType.INT,
                description="Font size",
                required=False,
                default=48,
                min_value=12,
                max_value=200,
            ),
            SkillParameter(
                name="fontcolor",
                type=ParameterType.STRING,
                description="Font color",
                required=False,
                default="white",
            ),
            SkillParameter(
                name="start",
                type=ParameterType.FLOAT,
                description="Start time in seconds",
                required=False,
                default=0,
            ),
        ],
        examples=[
            "typewriter_text:text=Hello World - Typewriter reveal",
            "typewriter_text:text=Loading...,speed=3 - Slow typewriter",
        ],
        tags=["typewriter", "type", "reveal", "character", "text", "animation"],
    ))

    # Bounce text
    registry.register(Skill(
        name="bounce_text",
        category=SkillCategory.OUTCOME,
        description="Text with elastic bounce-in animation (drops in and settles)",
        parameters=[
            SkillParameter(
                name="text",
                type=ParameterType.STRING,
                description="Text to display",
                required=True,
            ),
            SkillParameter(
                name="fontsize",
                type=ParameterType.INT,
                description="Font size",
                required=False,
                default=72,
                min_value=16,
                max_value=300,
            ),
            SkillParameter(
                name="fontcolor",
                type=ParameterType.STRING,
                description="Font color",
                required=False,
                default="white",
            ),
            SkillParameter(
                name="start",
                type=ParameterType.FLOAT,
                description="Start time in seconds",
                required=False,
                default=0,
            ),
            SkillParameter(
                name="duration",
                type=ParameterType.FLOAT,
                description="Duration in seconds",
                required=False,
                default=4,
            ),
        ],
        examples=[
            "bounce_text:text=WOW! - Bouncing text",
            "bounce_text:text=SALE,fontsize=120,fontcolor=red - Large red bounce",
        ],
        tags=["bounce", "elastic", "text", "animation", "drop", "spring"],
    ))

    # Fade text
    registry.register(Skill(
        name="fade_text",
        category=SkillCategory.OUTCOME,
        description="Text with smooth fade in and fade out animation",
        parameters=[
            SkillParameter(
                name="text",
                type=ParameterType.STRING,
                description="Text to display",
                required=True,
            ),
            SkillParameter(
                name="fontsize",
                type=ParameterType.INT,
                description="Font size",
                required=False,
                default=64,
                min_value=12,
                max_value=300,
            ),
            SkillParameter(
                name="fontcolor",
                type=ParameterType.STRING,
                description="Font color",
                required=False,
                default="white",
            ),
            SkillParameter(
                name="start",
                type=ParameterType.FLOAT,
                description="Start time in seconds",
                required=False,
                default=0,
            ),
            SkillParameter(
                name="duration",
                type=ParameterType.FLOAT,
                description="Total duration in seconds",
                required=False,
                default=4,
            ),
            SkillParameter(
                name="fade_time",
                type=ParameterType.FLOAT,
                description="Fade in/out duration in seconds",
                required=False,
                default=1.0,
                min_value=0.1,
                max_value=5.0,
            ),
        ],
        examples=[
            "fade_text:text=Welcome - Fade in/out text",
            "fade_text:text=Coming Soon,duration=6,fade_time=2 - Slow fade",
        ],
        tags=["fade", "text", "alpha", "dissolve", "smooth", "animation"],
    ))

    # Karaoke text
    registry.register(Skill(
        name="karaoke_text",
        category=SkillCategory.OUTCOME,
        description="Karaoke-style text with color fill synced to time",
        parameters=[
            SkillParameter(
                name="text",
                type=ParameterType.STRING,
                description="Text to display",
                required=True,
            ),
            SkillParameter(
                name="fontsize",
                type=ParameterType.INT,
                description="Font size",
                required=False,
                default=48,
                min_value=16,
                max_value=200,
            ),
            SkillParameter(
                name="base_color",
                type=ParameterType.STRING,
                description="Base (unfilled) text color",
                required=False,
                default="gray",
            ),
            SkillParameter(
                name="fill_color",
                type=ParameterType.STRING,
                description="Fill (highlighted) text color",
                required=False,
                default="yellow",
            ),
            SkillParameter(
                name="start",
                type=ParameterType.FLOAT,
                description="Start time in seconds",
                required=False,
                default=0,
            ),
            SkillParameter(
                name="duration",
                type=ParameterType.FLOAT,
                description="Duration of the fill sweep",
                required=False,
                default=5,
            ),
        ],
        examples=[
            "karaoke_text:text=Sing Along - Karaoke highlight",
            "karaoke_text:text=La La La,fill_color=cyan - Cyan karaoke fill",
        ],
        tags=["karaoke", "lyrics", "sing", "highlight", "fill", "music", "text"],
    ))

    # Color match
    registry.register(Skill(
        name="color_match",
        category=SkillCategory.VISUAL,
        description="Auto-match colors and brightness via histogram equalization",
        parameters=[],
        examples=[
            "color_match - Auto color/brightness matching",
        ],
        tags=["color", "match", "histogram", "equalize", "grade", "auto"],
    ))

    # Datamosh — glitch art with motion vectors
    registry.register(Skill(
        name="datamosh",
        category=SkillCategory.VISUAL,
        description="Create datamosh/glitch art effect by visualizing motion vectors",
        parameters=[
            SkillParameter(
                name="mode",
                type=ParameterType.CHOICE,
                description="Motion vector visualization flags (pf=forward, bf=backward, bb=bidir)",
                required=False,
                default="pf+bf+bb",
                choices=["pf", "bf", "bb", "pf+bf", "pf+bb", "bf+bb", "pf+bf+bb"],
            ),
        ],
        # Handler in composer.py provides input options + vf
        examples=[
            "datamosh - Standard datamosh effect (all motion vectors)",
            "datamosh:mode=pf - Forward-predicted vectors only",
        ],
        tags=["glitch", "datamosh", "motion", "vectors", "art", "corrupt", "aesthetic"],
    ))

    # Radial blur — spinning/zoom blur effect
    registry.register(Skill(
        name="radial_blur",
        category=SkillCategory.VISUAL,
        description="Create a radial/zoom blur effect for dynamic motion emphasis",
        parameters=[
            SkillParameter(
                name="radius",
                type=ParameterType.INT,
                description="Blur radius in pixels (higher = more blur)",
                required=False,
                default=5,
                min_value=1,
                max_value=50,
            ),
        ],
        ffmpeg_template="avgblur=sizeX={radius}:sizeY={radius}",
        examples=[
            "radial_blur - Subtle blur effect (5px radius)",
            "radial_blur:radius=15 - Strong blur effect",
        ],
        tags=["blur", "radial", "zoom", "motion", "spin", "dynamic", "focus"],
    ))

    # Grain overlay — cinematic film grain
    registry.register(Skill(
        name="grain_overlay",
        category=SkillCategory.VISUAL,
        description="Add cinematic film grain with precise intensity control (different from film_grain)",
        parameters=[
            SkillParameter(
                name="intensity",
                type=ParameterType.INT,
                description="Grain intensity (1 = subtle, 50 = heavy)",
                required=False,
                default=15,
                min_value=1,
                max_value=80,
            ),
            SkillParameter(
                name="seed",
                type=ParameterType.INT,
                description="Random seed for reproducible grain",
                required=False,
                default=-1,
                min_value=-1,
                max_value=99999,
            ),
        ],
        ffmpeg_template="noise=alls={intensity}:allf=t:seed={seed}",
        examples=[
            "grain_overlay - Subtle cinematic grain",
            "grain_overlay:intensity=40 - Heavy gritty grain",
            "grain_overlay:intensity=8 - Very subtle grain for clean footage",
        ],
        tags=["grain", "film", "noise", "cinematic", "texture", "analog", "organic"],
    ))

    # ── Missing registrations (Fix 1) ────────────────────────────── #

    registry.register(Skill(
        name="audio_crossfade",
        category=SkillCategory.AUDIO,
        description="Crossfade between two audio inputs, blending the end of one into the start of another.",
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
                type=ParameterType.STRING,
                description="Fade curve shape",
                required=False,
                default="tri",
                choices=["tri", "log", "exp", "qsin", "hsin", "esin", "ipar", "qua", "cub", "squ", "cbr", "par", "nofade"],
            ),
        ],
        examples=[
            "audio_crossfade - 2-second triangular crossfade",
            "audio_crossfade:duration=5:curve=log - 5-second logarithmic fade",
        ],
        tags=["audio", "crossfade", "transition", "blend", "mix"],
    ))

    registry.register(Skill(
        name="extract_frames",
        category=SkillCategory.ENCODING,
        description="Export video frames as an image sequence (PNG). Useful for inspection or frame-by-frame editing.",
        parameters=[
            SkillParameter(
                name="rate",
                type=ParameterType.FLOAT,
                description="Frames per second to extract",
                required=False,
                default=1.0,
                min_value=0.1,
                max_value=60.0,
            ),
        ],
        examples=[
            "extract_frames - Extract 1 frame per second",
            "extract_frames:rate=0.5 - Extract 1 frame every 2 seconds",
            "extract_frames:rate=24 - Extract every frame (at 24 fps)",
        ],
        tags=["frames", "export", "image", "sequence", "png", "extract"],
    ))

    registry.register(Skill(
        name="replace_audio",
        category=SkillCategory.AUDIO,
        description="Replace the video's original audio track with audio from a second input file.",
        parameters=[],
        examples=[
            "replace_audio - Replace audio with second input",
        ],
        tags=["audio", "replace", "swap", "soundtrack", "music"],
    ))

    registry.register(Skill(
        name="thumbnail",
        category=SkillCategory.ENCODING,
        description="Generate a single representative thumbnail image from the video.",
        parameters=[
            SkillParameter(
                name="width",
                type=ParameterType.INT,
                description="Output thumbnail width in pixels (0 = original)",
                required=False,
                default=0,
                min_value=0,
                max_value=7680,
            ),
            SkillParameter(
                name="time",
                type=ParameterType.FLOAT,
                description="Specific time in seconds to capture (0 = auto-detect best frame)",
                required=False,
                default=0,
                min_value=0,
                max_value=86400,
            ),
        ],
        examples=[
            "thumbnail - Auto-detect best representative frame",
            "thumbnail:time=5 - Capture frame at 5 seconds",
            "thumbnail:width=640:time=10 - 640px wide thumbnail at 10s",
        ],
        tags=["thumbnail", "poster", "preview", "screenshot", "frame", "image"],
    ))
