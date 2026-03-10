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
            "face image or video using LivePortrait. Produces a video where "
            "the source face moves like the driver."
        ),
        parameters=[
            SkillParameter(
                name="driving_video",
                type=ParameterType.STRING,
                description="Path to the driving video whose motion will be transferred",
                required=True,
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
        ],
        examples=[
            "animate_portrait:driving_video=/path/to/driver.mp4 - Animate source with driver's expressions",
            "animate_portrait:driving_video=/path/to/driver.mp4,driving_multiplier=1.5 - Exaggerated motion",
            "animate_portrait:driving_video=/path/to/driver.mp4,relative_motion=false - Absolute pose transfer",
        ],
        tags=[
            "animate", "portrait", "liveportrait", "face", "expression",
            "pose", "reenactment", "puppet", "ai", "deepfake",
            "head", "motion",
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
            "and an anime-optimized variant. Uses tiled inference to stay "
            "within VRAM limits."
        ),
        parameters=[
            SkillParameter(
                name="model",
                type=ParameterType.STRING,
                description=(
                    "Upscaler model: 'realesrgan_x4plus' (fast general), "
                    "'realesrgan_x4_anime' (anime/cartoon), "
                    "'hat_x4' (SOTA quality), 'dat_x4' (balanced), "
                    "'swinir_x4' (classical SR)"
                ),
                required=False,
                default="realesrgan_x4plus",
                choices=[
                    "realesrgan_x4plus", "realesrgan_x4_anime",
                    "hat_x4", "dat_x4", "swinir_x4",
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
        ],
        tags=[
            "upscale", "super_resolution", "enhance", "4k", "hd",
            "ai_upscale", "esrgan", "swinir", "hat", "dat",
            "detail", "resolution", "enlarge", "ai",
        ],
    ))
