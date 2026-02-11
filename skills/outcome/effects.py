"""Special effects skills."""

from ..registry import SkillRegistry, Skill, SkillParameter, SkillCategory, ParameterType


def register_skills(registry: SkillRegistry) -> None:
    """Register special effects skills with the registry."""

    # Timelapse skill
    registry.register(Skill(
        name="timelapse",
        category=SkillCategory.OUTCOME,
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
        category=SkillCategory.OUTCOME,
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
        category=SkillCategory.OUTCOME,
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
        category=SkillCategory.OUTCOME,
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
        category=SkillCategory.OUTCOME,
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
        category=SkillCategory.OUTCOME,
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
        category=SkillCategory.OUTCOME,
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
        category=SkillCategory.OUTCOME,
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
        category=SkillCategory.OUTCOME,
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
        category=SkillCategory.OUTCOME,
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
        category=SkillCategory.OUTCOME,
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
        category=SkillCategory.OUTCOME,
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
        category=SkillCategory.OUTCOME,
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
        category=SkillCategory.OUTCOME,
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
        category=SkillCategory.OUTCOME,
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
        category=SkillCategory.OUTCOME,
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
        category=SkillCategory.OUTCOME,
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
        category=SkillCategory.OUTCOME,
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
        category=SkillCategory.OUTCOME,
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
        category=SkillCategory.OUTCOME,
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
