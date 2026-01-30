"""Preview generation for quick video previews."""

import tempfile
from pathlib import Path
from typing import Optional
from .command_builder import CommandBuilder
from .process_manager import ProcessManager


class PreviewGenerator:
    """Generates low-resolution video previews quickly."""

    # Preview resolution presets
    RESOLUTIONS = {
        "360p": (640, 360),
        "480p": (854, 480),
        "720p": (1280, 720),
    }

    def __init__(self, process_manager: Optional[ProcessManager] = None):
        """Initialize preview generator.

        Args:
            process_manager: ProcessManager to use. Creates one if not provided.
        """
        self.process_manager = process_manager or ProcessManager()

    def generate_preview(
        self,
        input_path: str | Path,
        output_path: Optional[str | Path] = None,
        resolution: str = "480p",
        frame_skip: int = 2,
        duration: Optional[float] = None,
    ) -> Path:
        """Generate a low-resolution preview of a video.

        Args:
            input_path: Path to input video.
            output_path: Path for output. If None, creates temp file.
            resolution: Target resolution preset (360p, 480p, 720p).
            frame_skip: Process every Nth frame (higher = faster, lower quality).
            duration: Limit preview duration in seconds.

        Returns:
            Path to the generated preview file.
        """
        input_path = Path(input_path)
        if not input_path.exists():
            raise FileNotFoundError(f"Input file not found: {input_path}")

        if output_path is None:
            output_path = Path(tempfile.mktemp(suffix=".mp4"))
        else:
            output_path = Path(output_path)

        width, height = self.RESOLUTIONS.get(resolution, self.RESOLUTIONS["480p"])

        builder = CommandBuilder()
        builder.input(input_path)

        # Scale to target resolution while maintaining aspect ratio
        builder.vf(f"scale={width}:{height}:force_original_aspect_ratio=decrease")
        builder.vf(f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2")

        # Frame skip for faster processing
        if frame_skip > 1:
            builder.vf(f"select='not(mod(n,{frame_skip}))'")
            builder.vf("setpts=N/FRAME_RATE/TB")

        # Fast encoding preset
        builder.video_codec("libx264", crf=28, preset="ultrafast")
        builder.audio_codec("aac", bitrate="64k")

        # Duration limit
        if duration:
            builder.trim(duration=duration)

        builder.output(output_path)

        result = self.process_manager.execute(builder.build())
        if not result.success:
            raise RuntimeError(f"Preview generation failed: {result.error_message}")

        return output_path

    def generate_thumbnail(
        self,
        input_path: str | Path,
        output_path: Optional[str | Path] = None,
        timestamp: float = 0,
        width: int = 320,
    ) -> Path:
        """Generate a thumbnail image from a video.

        Args:
            input_path: Path to input video.
            output_path: Path for output. If None, creates temp file.
            timestamp: Time in seconds to capture frame.
            width: Thumbnail width (height auto-calculated).

        Returns:
            Path to the generated thumbnail file.
        """
        input_path = Path(input_path)
        if not input_path.exists():
            raise FileNotFoundError(f"Input file not found: {input_path}")

        if output_path is None:
            output_path = Path(tempfile.mktemp(suffix=".png"))
        else:
            output_path = Path(output_path)

        builder = CommandBuilder()
        builder.input(input_path, ["-ss", str(timestamp)])
        builder.vf(f"scale={width}:-1")
        builder.output_options("-vframes", "1")
        builder.output(output_path)

        result = self.process_manager.execute(builder.build())
        if not result.success:
            raise RuntimeError(f"Thumbnail generation failed: {result.error_message}")

        return output_path

    def generate_gif(
        self,
        input_path: str | Path,
        output_path: Optional[str | Path] = None,
        start: float = 0,
        duration: float = 5,
        width: int = 320,
        fps: int = 10,
    ) -> Path:
        """Generate an animated GIF from a video segment.

        Args:
            input_path: Path to input video.
            output_path: Path for output. If None, creates temp file.
            start: Start time in seconds.
            duration: Duration in seconds.
            width: GIF width (height auto-calculated).
            fps: Frames per second in output GIF.

        Returns:
            Path to the generated GIF file.
        """
        input_path = Path(input_path)
        if not input_path.exists():
            raise FileNotFoundError(f"Input file not found: {input_path}")

        if output_path is None:
            output_path = Path(tempfile.mktemp(suffix=".gif"))
        else:
            output_path = Path(output_path)

        # Two-pass for better GIF quality
        palette_path = Path(tempfile.mktemp(suffix=".png"))

        try:
            # Generate palette
            palette_builder = CommandBuilder()
            palette_builder.input(input_path, ["-ss", str(start), "-t", str(duration)])
            palette_builder.vf(f"fps={fps},scale={width}:-1:flags=lanczos,palettegen")
            palette_builder.output(palette_path)

            result = self.process_manager.execute(palette_builder.build())
            if not result.success:
                raise RuntimeError(f"Palette generation failed: {result.error_message}")

            # Generate GIF using palette
            gif_builder = CommandBuilder()
            gif_builder.input(input_path, ["-ss", str(start), "-t", str(duration)])
            gif_builder.input(palette_path)
            gif_builder.complex_filter(
                f"[0:v]fps={fps},scale={width}:-1:flags=lanczos[x];[x][1:v]paletteuse"
            )
            gif_builder.output(output_path)

            result = self.process_manager.execute(gif_builder.build())
            if not result.success:
                raise RuntimeError(f"GIF generation failed: {result.error_message}")

            return output_path

        finally:
            if palette_path.exists():
                palette_path.unlink()

    def extract_frames(
        self,
        input_path: str | Path,
        output_dir: Optional[str | Path] = None,
        fps: float = 1,
        format: str = "png",
        start: Optional[float] = None,
        duration: Optional[float] = None,
    ) -> list[Path]:
        """Extract frames from a video.

        Args:
            input_path: Path to input video.
            output_dir: Directory for output frames. If None, creates temp dir.
            fps: Frames per second to extract.
            format: Output image format (png, jpg).
            start: Start time in seconds.
            duration: Duration in seconds.

        Returns:
            List of paths to extracted frame files.
        """
        input_path = Path(input_path)
        if not input_path.exists():
            raise FileNotFoundError(f"Input file not found: {input_path}")

        if output_dir is None:
            output_dir = Path(tempfile.mkdtemp())
        else:
            output_dir = Path(output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)

        output_pattern = output_dir / f"frame_%04d.{format}"

        builder = CommandBuilder()

        input_opts = []
        if start is not None:
            input_opts.extend(["-ss", str(start)])
        builder.input(input_path, input_opts if input_opts else None)

        if duration is not None:
            builder.trim(duration=duration)

        builder.vf(f"fps={fps}")
        builder.output(output_pattern)

        result = self.process_manager.execute(builder.build())
        if not result.success:
            raise RuntimeError(f"Frame extraction failed: {result.error_message}")

        # Return list of extracted files
        frames = sorted(output_dir.glob(f"frame_*.{format}"))
        return frames
