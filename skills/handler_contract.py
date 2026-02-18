"""Formal contract for FFMPEGA skill handler functions.

Defines ``HandlerResult`` (what handlers return) and ``HandlerContext``
(what injected ``_``-prefixed parameters handlers may receive).  These
types make the previously-implicit coupling between ``composer.py`` and
the handler modules explicit and documented.

``HandlerResult`` supports tuple unpacking via ``__iter__`` so existing
``vf, af, opts, fc, io = handler(params)`` destructuring keeps working.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterator, TypedDict


@dataclass(slots=True)
class HandlerResult:
    """Structured return value from any ``_f_*`` handler function.

    Fields
    ------
    video_filters : list[str]
        Video filter expressions for ``-vf`` (e.g. ``["scale=1280:720"]``).
    audio_filters : list[str]
        Audio filter expressions for ``-af`` (e.g. ``["volume=0.5"]``).
    output_options : list[str]
        Raw output CLI flags (e.g. ``["-c:v", "libx264"]``).
    filter_complex : str
        Full ``-filter_complex`` graph string, or ``""`` if not needed.
    input_options : list[str]
        Raw input CLI flags placed *before* ``-i`` (e.g. ``["-ss", "5"]``).
    """

    video_filters: list[str] = field(default_factory=list)
    audio_filters: list[str] = field(default_factory=list)
    output_options: list[str] = field(default_factory=list)
    filter_complex: str = ""
    input_options: list[str] = field(default_factory=list)

    # ── Backward compatibility ────────────────────────────────────

    def __iter__(self) -> Iterator:
        """Allow ``vf, af, opts, fc, io = result`` destructuring."""
        return iter((
            self.video_filters,
            self.audio_filters,
            self.output_options,
            self.filter_complex,
            self.input_options,
        ))

    def __len__(self) -> int:
        """Always 5 — matches the canonical 5-tuple contract."""
        return 5

    def __getitem__(self, index: int):
        """Allow ``result[0]`` subscript access for backward compatibility."""
        return (
            self.video_filters,
            self.audio_filters,
            self.output_options,
            self.filter_complex,
            self.input_options,
        )[index]

    def __add__(self, other: tuple) -> tuple:
        """Allow ``result + ([],)`` concatenation for backward compatibility."""
        return tuple(self) + other


class HandlerContext(TypedDict, total=False):
    """Documented schema for ``_``-prefixed params injected by ``compose()``.

    Handlers may receive any subset of these keys in their ``params`` dict.
    All keys are optional — handlers should use ``.get()`` with defaults.
    """

    # ── Multi-input context ───────────────────────────────────────
    _extra_input_count: int
    """Number of extra inputs beyond the primary video (0 = single-input)."""

    _extra_input_paths: list[str]
    """File paths of extra inputs (images or videos)."""

    _image_input_indices: list[int]
    """FFmpeg input indices for image_path_a/b/c connections."""

    _image_input_paths: list[str]
    """File paths of image_path connections."""

    _exclude_inputs: set[int]
    """FFmpeg input indices reserved by other skills (e.g. overlay)."""

    _has_embedded_audio: bool
    """Whether the primary video has an audio stream."""

    # ── Duration / timing context ─────────────────────────────────
    _video_duration: float
    """Duration of the primary video in seconds."""

    _input_fps: float
    """Frame rate of the primary video."""

    _input_width: int
    """Width of the primary video in pixels."""

    _input_height: int
    """Height of the primary video in pixels."""

    _xfade_duration: float
    """Transition duration used by xfade (for offset calculation)."""

    _still_duration: float
    """Duration to display still images in multi-clip pipelines."""

    # ── Text context ──────────────────────────────────────────────
    _text_inputs: list[str]
    """Raw text strings from connected text_a/text_b inputs."""


def make_result(
    vf: list[str] | None = None,
    af: list[str] | None = None,
    opts: list[str] | None = None,
    fc: str = "",
    io: list[str] | None = None,
) -> HandlerResult:
    """Convenience constructor — avoids ``field(default_factory=...)`` noise.

    Usage::

        return make_result(vf=["scale=1280:720"])
        return make_result(af=["loudnorm"])
        return make_result(fc="[0:v][1:v]xfade=...")
    """
    return HandlerResult(
        video_filters=vf or [],
        audio_filters=af or [],
        output_options=opts or [],
        filter_complex=fc,
        input_options=io or [],
    )
