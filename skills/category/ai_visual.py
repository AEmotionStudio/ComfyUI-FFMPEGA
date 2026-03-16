"""AI Visual skills registration — AI-powered visual transformations."""

from ..registry import (
    SkillRegistry,
    Skill,
    SkillCategory,
    SkillParameter,
    ParameterType,
)


def register_skills(registry: SkillRegistry) -> None:
    """Register AI visual transformation skills."""

    # Animate portrait — LivePortrait
    registry.register(Skill(
        name="animate_portrait",
        category=SkillCategory.AI_VISUAL,
        description=(
            "AI-animate a portrait: transfer head pose, facial expressions, "
            "eye gaze, and lip movements from a driving video to a source "
            "face image or video using LivePortrait. Can also animate using "
            "expression sliders alone (no driving video needed). Produces "
            "a video where the source face moves like the driver or per the "
            "specified expressions."
        ),
        parameters=[
            SkillParameter(
                name="driving_video",
                type=ParameterType.STRING,
                description="Path to the driving video whose motion will be transferred (optional if expression sliders are set)",
                required=False,
            ),
            SkillParameter(
                name="driving_multiplier",
                type=ParameterType.FLOAT,
                description="Scale factor for driving motion intensity (1.0 = normal)",
                required=False,
                default=1.0,
                min_value=0.1,
                max_value=3.0,
            ),
            SkillParameter(
                name="relative_motion",
                type=ParameterType.BOOL,
                description="Use relative motion transfer (recommended). If false, uses absolute pose.",
                required=False,
                default=True,
            ),
            # Expression controls
            SkillParameter(
                name="rotate_pitch",
                type=ParameterType.FLOAT,
                description="Head pitch rotation in degrees (nod up/down)",
                required=False, default=0.0, min_value=-20.0, max_value=20.0,
            ),
            SkillParameter(
                name="rotate_yaw",
                type=ParameterType.FLOAT,
                description="Head yaw rotation in degrees (turn left/right)",
                required=False, default=0.0, min_value=-20.0, max_value=20.0,
            ),
            SkillParameter(
                name="rotate_roll",
                type=ParameterType.FLOAT,
                description="Head roll rotation in degrees (tilt left/right)",
                required=False, default=0.0, min_value=-20.0, max_value=20.0,
            ),
            SkillParameter(
                name="blink",
                type=ParameterType.FLOAT,
                description="Eye blink intensity (-20 to 5, positive = open, negative = close)",
                required=False, default=0.0, min_value=-20.0, max_value=5.0,
            ),
            SkillParameter(
                name="eyebrow",
                type=ParameterType.FLOAT,
                description="Eyebrow raise/lower (-10 to 15, positive = raise)",
                required=False, default=0.0, min_value=-10.0, max_value=15.0,
            ),
            SkillParameter(
                name="wink",
                type=ParameterType.FLOAT,
                description="Wink intensity (0 to 25)",
                required=False, default=0.0, min_value=0.0, max_value=25.0,
            ),
            SkillParameter(
                name="pupil_x",
                type=ParameterType.FLOAT,
                description="Pupil horizontal position (-15 to 15, negative = left)",
                required=False, default=0.0, min_value=-15.0, max_value=15.0,
            ),
            SkillParameter(
                name="pupil_y",
                type=ParameterType.FLOAT,
                description="Pupil vertical position (-15 to 15, negative = up)",
                required=False, default=0.0, min_value=-15.0, max_value=15.0,
            ),
            SkillParameter(
                name="aaa",
                type=ParameterType.FLOAT,
                description="Mouth open (aaa shape, 0 to 50)",
                required=False, default=0.0, min_value=-30.0, max_value=120.0,
            ),
            SkillParameter(
                name="eee",
                type=ParameterType.FLOAT,
                description="Mouth eee shape (-20 to 15)",
                required=False, default=0.0, min_value=-20.0, max_value=15.0,
            ),
            SkillParameter(
                name="woo",
                type=ParameterType.FLOAT,
                description="Mouth woo/pucker shape (-20 to 15)",
                required=False, default=0.0, min_value=-20.0, max_value=15.0,
            ),
            SkillParameter(
                name="smile",
                type=ParameterType.FLOAT,
                description="Smile intensity (-0.3 to 1.3)",
                required=False, default=0.0, min_value=-0.3, max_value=1.3,
            ),
            # Retargeting
            SkillParameter(
                name="retargeting_eyes",
                type=ParameterType.FLOAT,
                description="Eye retargeting intensity (0 = ignore driver's eyes, 1 = full transfer)",
                required=False, default=1.0, min_value=0.0, max_value=1.0,
            ),
            SkillParameter(
                name="retargeting_mouth",
                type=ParameterType.FLOAT,
                description="Mouth retargeting intensity (0 = ignore driver's mouth, 1 = full transfer)",
                required=False, default=1.0, min_value=0.0, max_value=1.0,
            ),
            SkillParameter(
                name="crop_factor",
                type=ParameterType.FLOAT,
                description="Face crop expansion factor (larger = more context around face)",
                required=False, default=1.6, min_value=1.0, max_value=3.0,
            ),
        ],
        examples=[
            "animate_portrait:driving_video=/path/to/driver.mp4 - Animate source with driver's expressions",
            "animate_portrait:driving_video=/path/to/driver.mp4,driving_multiplier=1.5 - Exaggerated motion",
            "animate_portrait:smile=1.0,aaa=30 - Make the face smile with open mouth (no driving video)",
            "animate_portrait:driving_video=/path/to/driver.mp4,retargeting_mouth=0.5 - Halve mouth motion",
            "animate_portrait:rotate_yaw=10,smile=0.8,blink=-5 - Turn head right, smile, eyes half-closed",
        ],
        tags=[
            "animate", "portrait", "liveportrait", "face", "expression",
            "pose", "reenactment", "puppet", "ai", "deepfake",
            "head", "motion", "smile", "blink", "eyebrow",
        ],
    ))

    # Marigold — Dense vision analysis (depth, normals, intrinsics)
    registry.register(Skill(
        name="marigold",
        category=SkillCategory.AI_VISUAL,
        description=(
            "AI dense vision analysis: estimate depth maps, surface normals, "
            "or intrinsic image properties (albedo, roughness, metallicity, "
            "shading) from a single image or video using the Marigold "
            "diffusion pipeline. Select output_type to choose what to produce."
        ),
        parameters=[
            SkillParameter(
                name="output_type",
                type=ParameterType.STRING,
                description=(
                    "Type of output: 'depth' (depth map), 'normals' (surface "
                    "normals), 'appearance' (albedo+roughness+metallicity), "
                    "or 'lighting' (albedo+shading+residual)"
                ),
                required=True,
            ),
            SkillParameter(
                name="num_steps",
                type=ParameterType.INT,
                description="Number of denoising steps (more = slower but higher quality)",
                required=False,
                default=4,
                min_value=1,
                max_value=50,
            ),
            SkillParameter(
                name="ensemble_size",
                type=ParameterType.INT,
                description="Number of ensemble predictions to average (more = higher precision)",
                required=False,
                default=1,
                min_value=1,
                max_value=10,
            ),
        ],
        examples=[
            "marigold:output_type=depth - Generate a depth map",
            "marigold:output_type=normals - Estimate surface normals",
            "marigold:output_type=normals,num_steps=10,ensemble_size=5 - High-precision normals",
            "marigold:output_type=appearance - Decompose into albedo, roughness, metallicity",
            "marigold:output_type=lighting - Decompose into albedo, shading, residual",
        ],
        tags=[
            "marigold", "depth", "normal", "normals", "surface", "albedo",
            "material", "roughness", "metallicity", "intrinsic", "shading",
            "decomposition", "ai", "vision", "3d", "depth_map", "normal_map",
        ],
    ))

    # NormalCrafter — Temporally consistent video normal maps
    registry.register(Skill(
        name="normalcrafter",
        category=SkillCategory.AI_VISUAL,
        description=(
            "AI video normal map generation with native temporal consistency. "
            "Produces flicker-free surface normal videos using video diffusion "
            "priors (NormalCrafter, ICCV 2025). Unlike per-frame Marigold normals, "
            "NormalCrafter uses a sliding window approach over the SVD backbone "
            "to ensure smooth transitions between frames — ideal for video "
            "relighting and 3D reconstruction. For single-image normals, use "
            "the 'marigold' skill instead."
        ),
        parameters=[
            SkillParameter(
                name="max_res",
                type=ParameterType.INT,
                description=(
                    "Maximum processing resolution (longest side). "
                    "512 = ~6 GB VRAM, 1024 = ~12 GB VRAM"
                ),
                required=False,
                default=1024,
                min_value=256,
                max_value=1024,
            ),
            SkillParameter(
                name="window_size",
                type=ParameterType.INT,
                description="Temporal window size for sliding inference (frames)",
                required=False,
                default=14,
                min_value=2,
                max_value=60,
            ),
            SkillParameter(
                name="process_length",
                type=ParameterType.INT,
                description="Maximum number of frames to process (-1 = all)",
                required=False,
                default=-1,
                min_value=-1,
                max_value=1000,
            ),
            SkillParameter(
                name="target_fps",
                type=ParameterType.INT,
                description="Target FPS for processing (-1 = use original)",
                required=False,
                default=-1,
                min_value=-1,
                max_value=60,
            ),
            SkillParameter(
                name="seed",
                type=ParameterType.INT,
                description="Random seed for reproducibility",
                required=False,
                default=42,
            ),
        ],
        examples=[
            "normalcrafter - Generate temporally-consistent video normals",
            "normalcrafter:max_res=512 - Lower VRAM usage at 512p",
            "normalcrafter:window_size=28 - Longer temporal window for smoother normals",
            "normalcrafter:process_length=100 - Process only the first 100 frames",
        ],
        tags=[
            "normalcrafter", "normals", "normal_map", "video_normals",
            "temporal", "consistent", "video", "surface", "3d", "ai",
            "vision", "relight", "relighting", "svd",
        ],
    ))

    # Video Depth Anything — Temporally-consistent video depth
    registry.register(Skill(
        name="video_depth",
        category=SkillCategory.AI_VISUAL,
        description=(
            "AI video depth estimation with native temporal consistency. "
            "Produces flicker-free depth videos using Video Depth Anything "
            "(CVPR 2025). Uses temporal attention to ensure smooth depth "
            "transitions between frames — ideal for video unlike per-frame "
            "models."
        ),
        parameters=[
            SkillParameter(
                name="encoder",
                type=ParameterType.STRING,
                description=(
                    "Model size: 'vits' (Small ~7GB VRAM, fastest), "
                    "'vitb' (Base), 'vitl' (Large ~24GB, best quality)"
                ),
                required=False,
                default="vits",
            ),
            SkillParameter(
                name="input_size",
                type=ParameterType.INT,
                description="Model input resolution (default 518)",
                required=False,
                default=518,
                min_value=256,
                max_value=1024,
            ),
            SkillParameter(
                name="max_res",
                type=ParameterType.INT,
                description="Maximum video resolution (default 1280)",
                required=False,
                default=1280,
                min_value=256,
                max_value=2560,
            ),
        ],
        examples=[
            "video_depth - Generate temporally-consistent depth video",
            "video_depth:encoder=vitl - High-quality depth with large model",
            "video_depth:encoder=vits,max_res=720 - Fast depth at lower res",
        ],
        tags=[
            "video_depth", "depth", "temporal", "consistent", "video",
            "depth_map", "3d", "ai", "vision", "vda",
        ],
    ))

    # AI Upscale — Super-resolution (Real-ESRGAN, HAT, DAT, SwinIR)
    registry.register(Skill(
        name="ai_upscale",
        category=SkillCategory.AI_VISUAL,
        description=(
            "AI super-resolution upscaling: enhance image or video resolution "
            "using neural network models. Supports Real-ESRGAN (fast, general), "
            "Real-HAT-GAN (SOTA quality), DAT (balanced), SwinIR (classical), "
            "an anime-optimized variant, and SeedVR2 diffusion upscaler "
            "(highest quality, temporal consistency for video). GAN models "
            "use tiled inference; SeedVR2 uses one-step diffusion."
        ),
        parameters=[
            SkillParameter(
                name="model",
                type=ParameterType.STRING,
                description=(
                    "Upscaler model: 'realesrgan_x4plus' (fast general), "
                    "'realesrgan_x4_anime' (anime/cartoon), "
                    "'hat_x4' (SOTA quality), 'dat_x4' (balanced), "
                    "'swinir_x4' (classical SR), "
                    "'seedvr2_3b_fp8' (diffusion, great quality), "
                    "'seedvr2_7b_gguf' (diffusion, highest quality)"
                ),
                required=False,
                default="realesrgan_x4plus",
                choices=[
                    "realesrgan_x4plus", "realesrgan_x4_anime",
                    "hat_x4", "dat_x4", "swinir_x4",
                    "seedvr2_3b_fp8", "seedvr2_7b_gguf",
                ],
            ),
            SkillParameter(
                name="scale_factor",
                type=ParameterType.INT,
                description="Output scale factor: 2 (2x) or 4 (4x, default)",
                required=False,
                default=4,
                choices=[2, 4],
            ),
            SkillParameter(
                name="tile_size",
                type=ParameterType.INT,
                description="Tile size for processing (smaller = less VRAM)",
                required=False,
                default=512,
                min_value=256,
                max_value=1024,
            ),
        ],
        examples=[
            "ai_upscale - Upscale with Real-ESRGAN 4x (default)",
            "ai_upscale:model=hat_x4 - SOTA quality upscale with HAT",
            "ai_upscale:model=realesrgan_x4_anime - Anime-optimized upscale",
            "ai_upscale:model=dat_x4,scale_factor=2 - 2x upscale with DAT",
            "ai_upscale:tile_size=256 - Lower VRAM usage with smaller tiles",
            "ai_upscale:model=seedvr2_3b_fp8 - Diffusion upscale (great quality)",
            "ai_upscale:model=seedvr2_7b_gguf - Highest quality diffusion upscale",
        ],
        tags=[
            "upscale", "super_resolution", "enhance", "4k", "hd",
            "ai_upscale", "esrgan", "swinir", "hat", "dat",
            "seedvr2", "diffusion", "temporal",
            "detail", "resolution", "enlarge", "ai",
        ],
    ))
