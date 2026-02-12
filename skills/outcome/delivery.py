"""Export and delivery skills (thumbnail, frame extraction, sprite sheets, etc.)."""

from ..registry import SkillRegistry, Skill, SkillParameter, SkillCategory, ParameterType


def register_skills(registry: SkillRegistry) -> None:
    """Register export and delivery skills with the registry."""

    # Thumbnail — extract best representative frame as image
    registry.register(Skill(
        name="thumbnail",
        category=SkillCategory.OUTCOME,
        description="Extract the best representative frame from the video as an image",
        parameters=[
            SkillParameter(
                name="time",
                type=ParameterType.FLOAT,
                description="Time in seconds to extract frame (0 = auto-detect best frame)",
                required=False,
                default=0,
                min_value=0,
                max_value=36000,
            ),
            SkillParameter(
                name="width",
                type=ParameterType.INT,
                description="Output thumbnail width in pixels (0 = original)",
                required=False,
                default=0,
                min_value=0,
                max_value=7680,
            ),
        ],
        # Handler in composer.py provides vf + output opts
        examples=[
            "thumbnail - Auto-detect best frame as thumbnail",
            "thumbnail:time=30 - Extract frame at 30 seconds",
            "thumbnail:width=1280 - 720p-width thumbnail",
        ],
        tags=["thumbnail", "frame", "image", "screenshot", "poster", "cover"],
    ))

    # Extract frames — export as image sequence
    registry.register(Skill(
        name="extract_frames",
        category=SkillCategory.OUTCOME,
        description="Export video frames as an image sequence (PNG/JPG)",
        parameters=[
            SkillParameter(
                name="rate",
                type=ParameterType.FLOAT,
                description="Frames per second to extract (1 = one per second, 0.1 = one every 10s)",
                required=False,
                default=1.0,
                min_value=0.01,
                max_value=60.0,
            ),
            SkillParameter(
                name="format",
                type=ParameterType.CHOICE,
                description="Output image format",
                required=False,
                default="png",
                choices=["png", "jpg", "bmp"],
            ),
            SkillParameter(
                name="quality",
                type=ParameterType.INT,
                description="JPEG quality (1-31, lower=better, only for jpg)",
                required=False,
                default=2,
                min_value=1,
                max_value=31,
            ),
        ],
        # Handler in composer.py provides vf + output opts
        examples=[
            "extract_frames - Extract 1 frame per second as PNG",
            "extract_frames:rate=0.5,format=jpg - One frame every 2 seconds as JPEG",
            "extract_frames:rate=24 - Extract every frame at 24fps",
        ],
        tags=["frames", "extract", "image", "sequence", "png", "jpg", "export"],
    ))

    # Sprite sheet — video preview sheet
    registry.register(Skill(
        name="sprite_sheet",
        category=SkillCategory.OUTCOME,
        description="Create a sprite sheet / contact sheet preview of the video (grid of thumbnails)",
        parameters=[
            SkillParameter(
                name="columns",
                type=ParameterType.INT,
                description="Number of columns in the grid",
                required=False,
                default=5,
                min_value=1,
                max_value=20,
            ),
            SkillParameter(
                name="rows",
                type=ParameterType.INT,
                description="Number of rows in the grid",
                required=False,
                default=5,
                min_value=1,
                max_value=20,
            ),
            SkillParameter(
                name="tile_width",
                type=ParameterType.INT,
                description="Width of each tile in pixels",
                required=False,
                default=320,
                min_value=64,
                max_value=1920,
            ),
            SkillParameter(
                name="interval",
                type=ParameterType.INT,
                description="Select every Nth frame (e.g. 30 = one frame per second at 30fps)",
                required=False,
                default=30,
                min_value=1,
                max_value=1000,
            ),
        ],
        ffmpeg_template="select='not(mod(n,{interval}))',scale={tile_width}:-1,tile={columns}x{rows}",
        examples=[
            "sprite_sheet - 5x5 thumbnail grid",
            "sprite_sheet:columns=10,rows=4 - 10x4 wide grid",
            "sprite_sheet:tile_width=160 - Smaller tiles",
        ],
        tags=["sprite", "sheet", "grid", "contact", "preview", "thumbnail", "overview"],
    ))

    # Preview strip — horizontal filmstrip
    registry.register(Skill(
        name="preview_strip",
        category=SkillCategory.OUTCOME,
        description="Create a horizontal filmstrip preview (evenly sampled frames side-by-side)",
        parameters=[
            SkillParameter(
                name="frames",
                type=ParameterType.INT,
                description="Number of frames to sample",
                required=False,
                default=10,
                min_value=2,
                max_value=50,
            ),
            SkillParameter(
                name="height",
                type=ParameterType.INT,
                description="Height of each frame in pixels",
                required=False,
                default=180,
                min_value=60,
                max_value=720,
            ),
            SkillParameter(
                name="interval",
                type=ParameterType.INT,
                description="Select every Nth frame (e.g. 30 = one frame per second at 30fps)",
                required=False,
                default=30,
                min_value=1,
                max_value=1000,
            ),
        ],
        ffmpeg_template="select='not(mod(n,{interval}))',scale=-1:{height},tile={frames}x1",
        examples=[
            "preview_strip - 10-frame horizontal filmstrip",
            "preview_strip:frames=20,height=120 - 20-frame compact strip",
        ],
        tags=["filmstrip", "preview", "strip", "overview", "summary"],
    ))

    # HLS packaging — segment for streaming
    registry.register(Skill(
        name="hls_package",
        category=SkillCategory.ENCODING,
        description="Package video for HTTP Live Streaming (HLS) with segmented output",
        parameters=[
            SkillParameter(
                name="segment_duration",
                type=ParameterType.INT,
                description="Segment duration in seconds",
                required=False,
                default=6,
                min_value=1,
                max_value=30,
            ),
            SkillParameter(
                name="playlist_type",
                type=ParameterType.CHOICE,
                description="Playlist type",
                required=False,
                default="vod",
                choices=["vod", "event"],
            ),
        ],
        ffmpeg_template="-hls_time {segment_duration} -hls_playlist_type {playlist_type} -hls_segment_filename segment_%03d.ts",
        examples=[
            "hls_package - Standard HLS packaging (6s segments)",
            "hls_package:segment_duration=10 - 10 second segments",
        ],
        tags=["hls", "streaming", "segment", "adaptive", "m3u8", "delivery", "web"],
    ))

    # Extract subtitles — pull subtitle track from container
    registry.register(Skill(
        name="extract_subtitles",
        category=SkillCategory.OUTCOME,
        description="Extract subtitle track from video container to a separate .srt file",
        parameters=[
            SkillParameter(
                name="track",
                type=ParameterType.INT,
                description="Subtitle track index (0 = first subtitle track)",
                required=False,
                default=0,
                min_value=0,
                max_value=10,
            ),
        ],
        ffmpeg_template="-map 0:s:{track} -c:s srt",
        examples=[
            "extract_subtitles - Extract first subtitle track as SRT",
            "extract_subtitles:track=1 - Extract second subtitle track",
        ],
        tags=["subtitle", "extract", "srt", "caption", "text", "closed_caption"],
    ))
