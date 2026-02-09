"""FFMPEG command builder for constructing complex filter chains."""

from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path


@dataclass
class Filter:
    """Represents a single FFMPEG filter."""
    name: str
    params: dict[str, str | int | float] = field(default_factory=dict)
    inputs: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)

    def to_string(self) -> str:
        """Convert filter to FFMPEG filter string."""
        parts = []

        # Input labels
        for inp in self.inputs:
            parts.append(f"[{inp}]")

        # Filter name and parameters
        if self.params:
            param_str = ":".join(
                f"{k}={v}" if v is not None else k
                for k, v in self.params.items()
            )
            parts.append(f"{self.name}={param_str}")
        else:
            parts.append(self.name)

        # Output labels
        for out in self.outputs:
            parts.append(f"[{out}]")

        return "".join(parts)


@dataclass
class FilterChain:
    """A chain of filters connected in sequence."""
    filters: list[Filter] = field(default_factory=list)

    def add(self, filter_obj: Filter) -> "FilterChain":
        """Add a filter to the chain."""
        self.filters.append(filter_obj)
        return self

    def add_filter(
        self,
        name: str,
        params: Optional[dict] = None,
        inputs: Optional[list[str]] = None,
        outputs: Optional[list[str]] = None,
    ) -> "FilterChain":
        """Add a filter by parameters."""
        self.filters.append(Filter(
            name=name,
            params=params or {},
            inputs=inputs or [],
            outputs=outputs or [],
        ))
        return self

    def to_string(self) -> str:
        """Convert filter chain to FFMPEG filter string."""
        if not self.filters:
            return ""
        return ",".join(f.to_string() for f in self.filters)


@dataclass
class FFMPEGCommand:
    """Represents a complete FFMPEG command."""
    inputs: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)
    input_options: dict[str, list[str]] = field(default_factory=dict)
    output_options: list[str] = field(default_factory=list)
    video_filters: FilterChain = field(default_factory=FilterChain)
    audio_filters: FilterChain = field(default_factory=FilterChain)
    complex_filter: Optional[str] = None
    global_options: list[str] = field(default_factory=list)
    overwrite: bool = True

    def to_args(self) -> list[str]:
        """Convert command to list of arguments for subprocess."""
        args = ["ffmpeg"]

        # Global options
        if self.overwrite:
            args.append("-y")
        args.extend(self.global_options)

        # Inputs with their options
        for input_path in self.inputs:
            if input_path in self.input_options:
                args.extend(self.input_options[input_path])
            args.extend(["-i", input_path])

        # Filters
        if self.complex_filter:
            args.extend(["-filter_complex", self.complex_filter])
        else:
            vf = self.video_filters.to_string()
            if vf:
                args.extend(["-vf", vf])

        # Audio filters are always applied via -af (independent of filter_complex)
        af = self.audio_filters.to_string()
        if af:
            args.extend(["-af", af])

        # Output options
        args.extend(self.output_options)

        # Outputs
        args.extend(self.outputs)

        return args

    def to_string(self) -> str:
        """Convert command to shell string."""
        import shlex
        return " ".join(shlex.quote(arg) for arg in self.to_args())


class CommandBuilder:
    """Builder for constructing FFMPEG commands."""

    def __init__(self):
        self._command = FFMPEGCommand()

    def reset(self) -> "CommandBuilder":
        """Reset the builder to initial state."""
        self._command = FFMPEGCommand()
        return self

    def input(
        self,
        path: str | Path,
        options: Optional[list[str]] = None,
    ) -> "CommandBuilder":
        """Add an input file."""
        path_str = str(path)
        self._command.inputs.append(path_str)
        if options:
            self._command.input_options[path_str] = options
        return self

    def add_input_options(
        self,
        path: str | Path,
        options: list[str],
    ) -> "CommandBuilder":
        """Add options to an existing input."""
        path_str = str(path)
        if path_str not in self._command.input_options:
            self._command.input_options[path_str] = []
        self._command.input_options[path_str].extend(options)
        return self

    def output(self, path: str | Path) -> "CommandBuilder":
        """Set output file."""
        self._command.outputs.append(str(path))
        return self

    def output_options(self, *options: str) -> "CommandBuilder":
        """Add output options."""
        self._command.output_options.extend(options)
        return self

    def global_options(self, *options: str) -> "CommandBuilder":
        """Add global options."""
        self._command.global_options.extend(options)
        return self

    def video_codec(self, codec: str, **params) -> "CommandBuilder":
        """Set video codec with optional parameters."""
        self._command.output_options.extend(["-c:v", codec])
        for key, value in params.items():
            if key == "crf":
                self._command.output_options.extend(["-crf", str(value)])
            elif key == "preset":
                self._command.output_options.extend(["-preset", value])
            elif key == "bitrate":
                self._command.output_options.extend(["-b:v", value])
        return self

    def audio_codec(self, codec: str, **params) -> "CommandBuilder":
        """Set audio codec with optional parameters."""
        self._command.output_options.extend(["-c:a", codec])
        for key, value in params.items():
            if key == "bitrate":
                self._command.output_options.extend(["-b:a", value])
            elif key == "sample_rate":
                self._command.output_options.extend(["-ar", str(value)])
            elif key == "channels":
                self._command.output_options.extend(["-ac", str(value)])
        return self

    def no_audio(self) -> "CommandBuilder":
        """Remove audio from output."""
        self._command.output_options.append("-an")
        return self

    def no_video(self) -> "CommandBuilder":
        """Remove video from output."""
        self._command.output_options.append("-vn")
        return self

    def vf(self, *filters: str | Filter) -> "CommandBuilder":
        """Add video filters."""
        for f in filters:
            if isinstance(f, str):
                # Parse simple filter string
                self._command.video_filters.add_filter(f)
            else:
                self._command.video_filters.add(f)
        return self

    def af(self, *filters: str | Filter) -> "CommandBuilder":
        """Add audio filters."""
        for f in filters:
            if isinstance(f, str):
                self._command.audio_filters.add_filter(f)
            else:
                self._command.audio_filters.add(f)
        return self

    def scale(self, width: int | str, height: int | str) -> "CommandBuilder":
        """Add scale filter."""
        self._command.video_filters.add_filter(
            "scale", {"w": width, "h": height}
        )
        return self

    def crop(
        self,
        width: int | str,
        height: int | str,
        x: int | str = 0,
        y: int | str = 0,
    ) -> "CommandBuilder":
        """Add crop filter."""
        self._command.video_filters.add_filter(
            "crop", {"w": width, "h": height, "x": x, "y": y}
        )
        return self

    def trim(
        self,
        start: Optional[float] = None,
        end: Optional[float] = None,
        duration: Optional[float] = None,
    ) -> "CommandBuilder":
        """Add trim/seek options."""
        if start is not None:
            self._command.output_options.extend(["-ss", str(start)])
        if end is not None:
            self._command.output_options.extend(["-to", str(end)])
        if duration is not None:
            self._command.output_options.extend(["-t", str(duration)])
        return self

    def speed(self, factor: float) -> "CommandBuilder":
        """Change playback speed."""
        # Video speed
        pts_factor = 1.0 / factor
        self._command.video_filters.add_filter(
            "setpts", {"": f"{pts_factor}*PTS"}
        )
        # Audio speed (atempo only supports 0.5-2.0)
        if 0.5 <= factor <= 2.0:
            self._command.audio_filters.add_filter(
                "atempo", {"": str(factor)}
            )
        elif factor < 0.5:
            # Chain multiple atempo filters
            remaining = factor
            while remaining < 0.5:
                self._command.audio_filters.add_filter("atempo", {"": "0.5"})
                remaining *= 2
            self._command.audio_filters.add_filter("atempo", {"": str(remaining)})
        else:
            # factor > 2.0
            remaining = factor
            while remaining > 2.0:
                self._command.audio_filters.add_filter("atempo", {"": "2.0"})
                remaining /= 2
            self._command.audio_filters.add_filter("atempo", {"": str(remaining)})
        return self

    def fps(self, rate: int | float) -> "CommandBuilder":
        """Set output frame rate."""
        self._command.video_filters.add_filter("fps", {"": str(rate)})
        return self

    def eq(
        self,
        brightness: Optional[float] = None,
        contrast: Optional[float] = None,
        saturation: Optional[float] = None,
        gamma: Optional[float] = None,
    ) -> "CommandBuilder":
        """Add eq (equalizer) filter for color adjustments."""
        params = {}
        if brightness is not None:
            params["brightness"] = brightness
        if contrast is not None:
            params["contrast"] = contrast
        if saturation is not None:
            params["saturation"] = saturation
        if gamma is not None:
            params["gamma"] = gamma
        if params:
            self._command.video_filters.add_filter("eq", params)
        return self

    def complex_filter(self, filter_graph: str) -> "CommandBuilder":
        """Set complex filtergraph."""
        self._command.complex_filter = filter_graph
        return self

    def format(self, fmt: str) -> "CommandBuilder":
        """Set output format."""
        self._command.output_options.extend(["-f", fmt])
        return self

    def quality(self, preset: str) -> "CommandBuilder":
        """Apply quality preset."""
        presets = {
            "draft": {"crf": 28, "preset": "ultrafast"},
            "standard": {"crf": 23, "preset": "medium"},
            "high": {"crf": 18, "preset": "slow"},
            "lossless": {"crf": 0, "preset": "veryslow"},
        }
        if preset in presets:
            self.video_codec("libx264", **presets[preset])
        return self

    def overwrite(self, value: bool = True) -> "CommandBuilder":
        """Set overwrite flag."""
        self._command.overwrite = value
        return self

    def build(self) -> FFMPEGCommand:
        """Build and return the command."""
        return self._command

    def build_args(self) -> list[str]:
        """Build and return command as argument list."""
        return self._command.to_args()

    def build_string(self) -> str:
        """Build and return command as shell string."""
        return self._command.to_string()
