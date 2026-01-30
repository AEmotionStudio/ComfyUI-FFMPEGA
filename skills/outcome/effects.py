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

    # Picture in picture skill
    registry.register(Skill(
        name="pip",
        category=SkillCategory.OUTCOME,
        description="Add picture-in-picture overlay",
        parameters=[
            SkillParameter(
                name="overlay",
                type=ParameterType.STRING,
                description="Path to overlay video",
                required=True,
            ),
            SkillParameter(
                name="position",
                type=ParameterType.CHOICE,
                description="PiP position",
                required=False,
                default="bottom_right",
                choices=["top_left", "top_right", "bottom_left", "bottom_right"],
            ),
            SkillParameter(
                name="scale",
                type=ParameterType.FLOAT,
                description="Overlay scale (0.1-0.5)",
                required=False,
                default=0.25,
                min_value=0.1,
                max_value=0.5,
            ),
        ],
        examples=[
            "pip:overlay=facecam.mp4 - Add facecam PiP",
            "pip:overlay=reaction.mp4,position=top_left,scale=0.3 - Reaction video",
        ],
        tags=["overlay", "facecam", "reaction", "inset"],
    ))

    # Split screen skill
    registry.register(Skill(
        name="split_screen",
        category=SkillCategory.OUTCOME,
        description="Create split screen with another video",
        parameters=[
            SkillParameter(
                name="other",
                type=ParameterType.STRING,
                description="Path to second video",
                required=True,
            ),
            SkillParameter(
                name="layout",
                type=ParameterType.CHOICE,
                description="Split layout",
                required=False,
                default="horizontal",
                choices=["horizontal", "vertical"],
            ),
        ],
        examples=[
            "split_screen:other=video2.mp4 - Side by side",
            "split_screen:other=video2.mp4,layout=vertical - Top and bottom",
        ],
        tags=["comparison", "side_by_side", "dual"],
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
