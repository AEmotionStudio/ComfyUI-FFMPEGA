"""Shared encoding options: colour policy, output formats, arg construction.

Every FFMPEGA encoder routes through this module so the repo has exactly one
colour convention instead of the five it accumulated.

Why the colour handling looks the way it does (measured on FFmpeg n8.1.2):

* ``-color_primaries`` and ``-color_trc`` passed as *output* options are
  silently dropped — the stream ends up tagged ``unknown`` for both.  Only
  ``-colorspace`` / ``-color_range`` survive, and only because they feed
  filter-graph negotiation.  The ``setparams`` filter is the reliable route
  and does write all four values, so tagging happens exclusively there.
* An untagged encode (what ComfyUI's native ``CreateVideo``/``SaveVideo``
  produces) is not merely untagged: swscale falls back to the BT.601 matrix,
  so the *pixel data itself* differs from a BT.709 encode.  Pure green goes to
  Y=144 instead of Y=173.  ``native`` reproduces that byte for byte.
* ComfyUI IMAGE tensors are generic RGB, which in practice means sRGB.  The
  default ``srgb`` policy therefore converts with the BT.709 matrix (sRGB and
  BT.709 share primaries) and tags the transfer honestly as IEC 61966-2-1.
  VideoHelperSuite instead lies (``fake_trc: bt709``); on FFmpeg 8 that lie is
  a no-op anyway, so it is not reproduced here.
"""

from __future__ import annotations

import functools
import subprocess
from dataclasses import dataclass, field

import numpy as np
import torch

try:
    from ..bin_paths import get_ffmpeg_bin
except ImportError:  # pragma: no cover - direct-import fallback
    from core.bin_paths import get_ffmpeg_bin  # type: ignore


# --------------------------------------------------------------------------
# Colour policies
# --------------------------------------------------------------------------

#: Filter fragment applied to *raw RGB tensor* input, after any loop/pad
#: filters.  Never apply these to a file→file re-encode: the source is already
#: YUV with its own tags and ``out_color_matrix`` would double-convert it.
COLOR_POLICIES: dict[str, str] = {
    # Truthful sRGB: BT.709 matrix + primaries, limited range, sRGB transfer.
    "srgb": (
        "scale=out_color_matrix=bt709,"
        "setparams=colorspace=bt709:color_primaries=bt709"
        ":color_trc=iec61966-2-1:range=tv"
    ),
    # Broadcast BT.709: same pixels, transfer tagged bt709 (VHS's intent).
    "bt709": (
        "scale=out_color_matrix=bt709,"
        "setparams=colorspace=bt709:color_primaries=bt709"
        ":color_trc=bt709:range=tv"
    ),
    # Byte-identical to ComfyUI native: swscale default BT.601, untagged.
    "native": "",
    # Full-range archival.  Tag and samples agree, unlike the old pc/tv mixes.
    "full": (
        "scale=out_color_matrix=bt709:out_range=pc,"
        "setparams=colorspace=bt709:color_primaries=bt709"
        ":color_trc=iec61966-2-1:range=pc"
    ),
}

DEFAULT_COLOR_POLICY = "srgb"

#: UI label → policy key.  Labels are what the node widget stores.
COLOR_POLICY_LABELS: dict[str, str] = {
    "sRGB (recommended)": "srgb",
    "BT.709 broadcast": "bt709",
    "ComfyUI native match": "native",
    "full range (pc)": "full",
}


def resolve_color_policy(value: str | None) -> str:
    """Map a widget label (or bare key) to a policy key, defaulting to sRGB."""
    if not value:
        return DEFAULT_COLOR_POLICY
    key = str(value).strip()
    if key in COLOR_POLICIES:
        return key
    if key in COLOR_POLICY_LABELS:
        return COLOR_POLICY_LABELS[key]
    # Tolerate partial matches from renamed labels ("sRGB", "native", ...).
    lowered = key.lower()
    for label, policy in COLOR_POLICY_LABELS.items():
        if lowered == label.lower() or lowered.startswith(policy):
            return policy
    return DEFAULT_COLOR_POLICY


@functools.lru_cache(maxsize=1)
def has_setparams() -> bool:
    """Whether this ffmpeg build provides the ``setparams`` filter (>= 4.3).

    Without it there is no reliable way to tag primaries/transfer, so callers
    fall back to the legacy ``-color_*`` output flags: partially ignored on
    FFmpeg 8, but better than emitting a filter chain ffmpeg cannot parse.

    Fails *open*.  If the probe cannot run (patched subprocess under test, a
    sandbox that blocks exec) we assume a modern build rather than silently
    downgrading to the flags that do not work — a real absence surfaces as a
    loud ffmpeg error instead of a quietly mistagged file.
    """
    try:
        res = subprocess.run(
            [get_ffmpeg_bin(), "-hide_banner", "-filters"],
            capture_output=True, timeout=15,
        )
        stdout = res.stdout
        if not isinstance(stdout, (bytes, bytearray)):
            return True
    except Exception:
        return True
    return b" setparams " in stdout


def color_filter(policy: str | None) -> str:
    """Colour filter fragment for raw-RGB input under ``policy``.

    Returns an empty string for the ``native`` policy and whenever
    ``setparams`` is unavailable (see :func:`legacy_color_args`).
    """
    key = resolve_color_policy(policy)
    fragment = COLOR_POLICIES[key]
    if not fragment:
        return ""
    if not has_setparams():
        # Keep the matrix conversion, drop the tagging half.
        return fragment.split(",setparams=", 1)[0]
    return fragment


def legacy_color_args(policy: str | None) -> list[str]:
    """Output-side colour flags, only for builds without ``setparams``.

    Returns ``[]`` on a modern build because those flags are unreliable there.
    """
    key = resolve_color_policy(policy)
    if key == "native" or has_setparams():
        return []
    rng = "pc" if key == "full" else "tv"
    trc = "bt709" if key == "bt709" else "iec61966-2-1"
    return [
        "-color_range", rng,
        "-colorspace", "bt709",
        "-color_primaries", "bt709",
        "-color_trc", trc,
    ]


# --------------------------------------------------------------------------
# Output formats
# --------------------------------------------------------------------------

SOURCE_FORMAT = "source (no re-encode)"


@dataclass(frozen=True)
class FormatDef:
    """Static description of an output format."""

    ext: str
    codec: str | None                      # None = let the container decide
    pix_fmt_8: str | None
    pix_fmt_10: str | None                 # None = 10-bit not supported
    audio_codec: str | None                # None = format carries no audio
    quality_flag: str = "-crf"             # -crf, -qp, -q:v, or "" for none
    preset_flag: str = "-preset"           # -preset, -deadline, -cpu-used, ""
    default_preset: str = "medium"
    extra: tuple[str, ...] = ()
    supports_faststart: bool = False
    #: Output stays in an RGB/palette space, so no RGB→YUV matrix is applied
    #: and the colour policy has nothing to act on.
    rgb_output: bool = False
    #: Formats needing a branching graph (palettegen) instead of a plain -vf.
    filter_complex: str = ""
    #: ffprobe's name for this codec, used to spot an already-matching source.
    probe_name: str = ""


FORMATS: dict[str, FormatDef] = {
    "h264-mp4": FormatDef(
        ext=".mp4", codec="libx264",
        probe_name="h264",
        pix_fmt_8="yuv420p", pix_fmt_10="yuv420p10le",
        audio_codec="aac", supports_faststart=True,
    ),
    "h265-mp4": FormatDef(
        ext=".mp4", codec="libx265",
        probe_name="hevc",
        pix_fmt_8="yuv420p", pix_fmt_10="yuv420p10le",
        audio_codec="aac", supports_faststart=True,
        # hvc1 tag keeps QuickTime/Safari happy; quiet the x265 banner.
        extra=("-vtag", "hvc1", "-x265-params", "log-level=quiet"),
    ),
    "vp9-webm": FormatDef(
        ext=".webm", codec="libvpx-vp9",
        probe_name="vp9",
        pix_fmt_8="yuv420p", pix_fmt_10="yuv420p10le",
        audio_codec="libopus",
        preset_flag="-deadline", default_preset="good",
        # -b:v 0 puts VP9 into constant-quality (CRF-only) mode.
        extra=("-b:v", "0", "-row-mt", "1"),
    ),
    "av1-webm": FormatDef(
        ext=".webm", codec="libsvtav1",
        probe_name="av1",
        pix_fmt_8="yuv420p", pix_fmt_10="yuv420p10le",
        audio_codec="libopus",
        quality_flag="-crf", preset_flag="-preset", default_preset="8",
        extra=("-svtav1-params", "tune=0"),
    ),
    "prores-mov": FormatDef(
        probe_name="prores",
        # prores_ks only accepts 10-bit 4:2:2/4:4:4, so both depths map there.
        ext=".mov", codec="prores_ks",
        pix_fmt_8="yuv422p10le", pix_fmt_10="yuv422p10le",
        audio_codec="pcm_s16le",
        quality_flag="", preset_flag="",
        extra=("-profile:v", "3"),
    ),
    "ffv1-mkv": FormatDef(
        ext=".mkv", codec="ffv1",
        probe_name="ffv1",
        pix_fmt_8="yuv444p", pix_fmt_10="yuv444p16le",
        audio_codec="flac",
        quality_flag="", preset_flag="",
        extra=("-level", "3", "-coder", "1", "-context", "1", "-g", "1"),
    ),
    "gif": FormatDef(
        ext=".gif", codec=None,
        pix_fmt_8=None, pix_fmt_10=None,
        audio_codec=None, quality_flag="", preset_flag="",
        rgb_output=True,
        # palettegen needs two branches, so gif cannot use a plain -vf.
        filter_complex=(
            "split[pga][pgb];[pga]palettegen=stats_mode=diff[pgp];"
            "[pgb][pgp]paletteuse=dither=sierra2_4a:diff_mode=rectangle"
        ),
    ),
    "webp": FormatDef(
        ext=".webp", codec="libwebp_anim",
        # bgra keeps the animation in RGB — no matrix conversion to get wrong.
        pix_fmt_8="bgra", pix_fmt_10=None,
        audio_codec=None, quality_flag="-q:v", preset_flag="",
        extra=("-loop", "0"),
        rgb_output=True,
    ),
}

#: Presets accepted by libx264/libx265.  VP9 and AV1 use their own scales.
X264_PRESETS = [
    "ultrafast", "superfast", "veryfast", "faster", "fast",
    "medium", "slow", "slower", "veryslow",
]

#: Codecs that can be stream-copied into each container without re-encoding.
_REMUXABLE: dict[str, frozenset[str]] = {
    ".mp4": frozenset({"h264", "hevc", "av1", "mpeg4"}),
    ".mov": frozenset({"h264", "hevc", "prores", "mpeg4"}),
    ".mkv": frozenset({"h264", "hevc", "av1", "vp9", "vp8", "ffv1", "mpeg4"}),
    ".webm": frozenset({"vp9", "vp8", "av1"}),
}


def can_remux(source_codec: str | None, target_ext: str) -> bool:
    """Whether ``source_codec`` can be stream-copied into ``target_ext``."""
    if not source_codec:
        return False
    return source_codec.lower() in _REMUXABLE.get(target_ext.lower(), frozenset())


#: Audio encoder each container accepts.  Muxing aac into webm fails outright.
_AUDIO_BY_EXT: dict[str, str] = {
    ".mp4": "aac",
    ".mov": "aac",
    ".m4v": "aac",
    ".mkv": "aac",
    ".webm": "libopus",
}


#: How an existing file should reach the output directory.
COPY = "copy"        # shutil.copy2 — no ffmpeg, no quality loss, no cost
REMUX = "remux"      # ffmpeg -c copy — repackage only, still lossless
ENCODE = "encode"    # full re-encode — the only lossy option


def plan_output(
    spec: EncodeSpec,
    source_codec: str | None,
    source_ext: str,
    needs_metadata: bool = False,
    already_final: bool = False,
) -> tuple[str, str]:
    """Decide how to get an existing file into its final form.

    Args:
        spec: The user's encoding choices.
        source_codec: ffprobe codec name of the input, if known.
        source_ext: Extension of the input file.
        needs_metadata: Whether the workflow has to be written into the
            container, which a plain copy cannot do.
        already_final: True when this process just encoded the file to
            ``spec`` (the images path), so re-encoding would only lose quality.

    Returns:
        ``(action, target_ext)`` where action is :data:`COPY`, :data:`REMUX`
        or :data:`ENCODE`.
    """
    source_ext = source_ext or ".mp4"
    target_ext = source_ext if spec.is_source else spec.ext

    # Loops on an existing file need -stream_loop, which a copy cannot do.
    needs_ffmpeg = needs_metadata or (spec.loop_count > 0 and not already_final)

    if already_final or spec.is_source:
        # Nothing to convert; touch the file only if something demands it.
        if not needs_ffmpeg:
            return COPY, target_ext
        return REMUX, target_ext

    # An explicit format was chosen.  Repackaging is lossless and near-free
    # when the source already holds exactly the codec that format produces.
    fmt = spec.definition
    if (
        fmt.probe_name
        and source_codec
        and source_codec.lower() == fmt.probe_name
        and can_remux(source_codec, target_ext)
    ):
        return REMUX, target_ext

    return ENCODE, target_ext


def audio_codec_for(ext: str, requested: str = "auto") -> str:
    """Pick an audio encoder valid for ``ext``.

    ``requested`` wins unless it is ``auto``; callers that let a user choose
    still need this for the pass-through case, where the container is only
    known from the source file's extension.
    """
    choice = (requested or "auto").lower()
    if choice not in ("auto", "", "none"):
        return choice
    return _AUDIO_BY_EXT.get((ext or "").lower(), "aac")


# --------------------------------------------------------------------------
# Encode spec
# --------------------------------------------------------------------------


@dataclass
class EncodeSpec:
    """User-facing encoding choices for one output."""

    format: str = "h264-mp4"
    crf: int = 19
    preset: str = "medium"
    bit_depth: int = 8
    color: str | None = DEFAULT_COLOR_POLICY
    audio_codec: str = "auto"
    audio_bitrate: str = "192k"
    faststart: bool = True
    loop_count: int = 0
    trim_to_audio: bool = False
    dim_alignment: int = 2
    extra_movflags: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        self.color = resolve_color_policy(self.color)
        self.bit_depth = 10 if int(self.bit_depth) >= 10 else 8
        self.dim_alignment = max(1, int(self.dim_alignment))

    @property
    def is_source(self) -> bool:
        """True when the user asked for no re-encode."""
        return self.format == SOURCE_FORMAT

    @property
    def definition(self) -> FormatDef:
        return FORMATS[self.format]

    @property
    def ext(self) -> str:
        return SOURCE_FORMAT if self.is_source else self.definition.ext

    @property
    def wants_color(self) -> bool:
        """Whether a colour policy is meaningful for this format.

        Palette/RGB outputs never run an RGB→YUV matrix, so there is nothing
        for the policy to correct and nothing worth tagging.
        """
        if self.is_source:
            return True
        return not self.definition.rgb_output


def spec_from_widgets(**widgets) -> EncodeSpec:
    """Build an :class:`EncodeSpec` from raw node widget values.

    Unknown formats fall back to ``h264-mp4`` rather than raising, so a
    workflow saved against a newer version still executes.
    """
    fmt = str(widgets.get("output_format") or SOURCE_FORMAT)
    if fmt != SOURCE_FORMAT and fmt not in FORMATS:
        fmt = "h264-mp4"
    try:
        crf = int(widgets.get("crf", 19))
    except (TypeError, ValueError):
        crf = 19
    try:
        loop_count = max(0, int(widgets.get("loop_count", 0)))
    except (TypeError, ValueError):
        loop_count = 0
    return EncodeSpec(
        format=fmt,
        crf=max(0, min(63, crf)),
        preset=str(widgets.get("encode_preset") or "medium"),
        bit_depth=int(str(widgets.get("bit_depth", 8)) or 8),
        color=widgets.get("color_policy"),
        audio_codec=str(widgets.get("audio_codec") or "auto"),
        audio_bitrate=str(widgets.get("audio_bitrate") or "192k"),
        faststart=bool(widgets.get("faststart", True)),
        loop_count=loop_count,
        trim_to_audio=bool(widgets.get("trim_to_audio", False)),
    )


# --------------------------------------------------------------------------
# Argument construction
# --------------------------------------------------------------------------


def raw_input_args(width: int, height: int, fps: float, bit_depth: int = 8) -> list[str]:
    """ffmpeg args describing a raw RGB frame stream arriving on stdin.

    No ``-color_*`` input flags: the policy is applied on the output side so
    there is a single place where colour is decided.
    """
    pix_fmt = "rgb48le" if int(bit_depth) >= 10 else "rgb24"
    return [
        "-f", "rawvideo",
        "-pix_fmt", pix_fmt,
        "-s", f"{int(width)}x{int(height)}",
        "-r", str(fps),
        "-i", "-",
    ]


def video_filter(
    spec: EncodeSpec,
    n_frames: int | None = None,
    prefix: str = "",
    apply_color: bool = True,
) -> str:
    """Build the single ``-vf`` string for a raw-RGB encode.

    ffmpeg keeps only the last ``-vf`` it sees, so every filter has to be
    joined here rather than appended as a second flag.

    Args:
        spec: Encoding choices.
        n_frames: Source frame count, required for ``loop_count``.
        prefix: Extra filters to run first (e.g. padding).
        apply_color: Set False for file→file work, where the source already
            carries its own colour tags.
    """
    parts: list[str] = []
    if prefix:
        parts.append(prefix)
    if spec.loop_count > 0 and n_frames:
        # size must cover the whole clip or loop repeats only a prefix of it.
        parts.append(f"loop=loop={spec.loop_count}:size={int(n_frames)}:start=0")
    if apply_color and spec.wants_color:
        fragment = color_filter(spec.color)
        if fragment:
            parts.append(fragment)
    if not spec.is_source and spec.definition.filter_complex:
        parts.append(spec.definition.filter_complex)
    return ",".join(p for p in parts if p)


def movflags(
    spec: EncodeSpec,
    extra: tuple[str, ...] = (),
    ext: str | None = None,
) -> list[str]:
    """Combined ``-movflags`` token, or ``[]`` when the container has none.

    Repeating ``-movflags`` makes ffmpeg keep only the last one, so every flag
    must be folded into a single ``+``-joined value.

    Args:
        ext: Target container extension.  Required when ``spec.is_source``,
            since the format table cannot answer for a pass-through file.
    """
    target = ext if ext is not None else (None if spec.is_source else spec.ext)
    if target is not None and target.lower() not in (".mp4", ".mov", ".m4v"):
        return []
    flags: list[str] = []
    if spec.faststart:
        flags.append("faststart")
    for f in (*spec.extra_movflags, *extra):
        if f not in flags:
            flags.append(f)
    if not flags:
        return []
    return ["-movflags", "+".join(flags)]


def video_output_args(spec: EncodeSpec, apply_color: bool = True) -> list[str]:
    """Encoder args for the video stream (no ``-vf``, no output path).

    Never emits ``-colorspace`` / ``-color_primaries`` / ``-color_trc``: those
    are dropped by FFmpeg 8.  Tagging happens in :func:`color_filter`, except
    on ancient builds where :func:`legacy_color_args` takes over.
    """
    fmt = spec.definition
    args: list[str] = []
    if fmt.codec:
        args += ["-c:v", fmt.codec]

    if fmt.quality_flag == "-q:v":
        # libwebp's scale runs the other way: 0 worst, 100 best.
        args += ["-q:v", str(max(1, min(100, 100 - spec.crf)))]
    elif fmt.quality_flag:
        args += [fmt.quality_flag, str(spec.crf)]

    if fmt.preset_flag:
        preset = spec.preset
        if fmt.preset_flag == "-preset" and fmt.codec == "libsvtav1":
            # SVT-AV1 takes a numeric speed, not an x264 preset name.
            preset = preset if str(preset).isdigit() else fmt.default_preset
        elif fmt.preset_flag == "-preset" and preset not in X264_PRESETS:
            preset = fmt.default_preset
        elif fmt.preset_flag == "-deadline" and preset not in (
            "best", "good", "realtime",
        ):
            preset = fmt.default_preset
        args += [fmt.preset_flag, str(preset)]

    pix_fmt = fmt.pix_fmt_10 if spec.bit_depth >= 10 else fmt.pix_fmt_8
    if pix_fmt is None:
        pix_fmt = fmt.pix_fmt_8
    if pix_fmt:
        args += ["-pix_fmt", pix_fmt]

    args += list(fmt.extra)
    if apply_color and spec.wants_color:
        args += legacy_color_args(spec.color)
    return args


def audio_output_args(spec: EncodeSpec) -> list[str]:
    """Encoder args for the audio stream, or ``["-an"]`` when disabled."""
    fmt = spec.definition
    choice = (spec.audio_codec or "auto").lower()
    if choice == "none" or fmt.audio_codec is None:
        return ["-an"]
    if choice == "copy":
        return ["-c:a", "copy"]
    codec = fmt.audio_codec if choice == "auto" else choice
    args = ["-c:a", codec]
    # Lossless codecs reject a target bitrate.
    if codec not in ("flac", "pcm_s16le", "pcm_s24le", "copy"):
        args += ["-b:a", spec.audio_bitrate]
    return args


def probe_video_codec(path: str) -> str | None:
    """Return the video codec name of ``path``, or None if it cannot be read."""
    try:
        from ..bin_paths import get_ffprobe_bin
    except ImportError:  # pragma: no cover - direct-import fallback
        from core.bin_paths import get_ffprobe_bin  # type: ignore
    try:
        res = subprocess.run(
            [
                get_ffprobe_bin(), "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=codec_name",
                "-of", "default=nk=1:nw=1", path,
            ],
            capture_output=True, timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    name = res.stdout.decode("utf-8", "replace").strip().splitlines()
    return name[0] if name else None


def _metadata_block(
    spec: EncodeSpec,
    ext: str | None,
    prompt=None,
    extra_pnginfo: dict | None = None,
) -> list[str]:
    """``-movflags`` plus ``-metadata`` args as one already-merged block.

    Both the container metadata and ``faststart`` want a ``-movflags``, and a
    repeated flag makes ffmpeg keep only the last.  Merging here is the only
    place that has to know about the interaction.
    """
    try:
        from .metadata import metadata_args, required_movflags
    except ImportError:  # pragma: no cover - direct-import fallback
        from core.video.metadata import metadata_args, required_movflags  # type: ignore

    target = ext if ext is not None else (None if spec.is_source else spec.ext)
    meta = metadata_args(prompt, extra_pnginfo, target or ".mp4")
    extra = required_movflags(target or "", bool(meta))
    return movflags(spec, extra=extra, ext=target) + meta


def build_file_command(
    spec: EncodeSpec,
    input_path: str,
    output_path: str,
    stream_copy: bool,
    prompt=None,
    extra_pnginfo: dict | None = None,
    ext: str | None = None,
) -> list[str]:
    """ffmpeg command for remuxing or re-encoding an existing file.

    No colour filter is inserted: the source is already YUV and carries its
    own tags, so forcing ``out_color_matrix`` here would convert it twice.
    """
    target_ext = ext or (None if spec.is_source else spec.ext)
    cmd = [get_ffmpeg_bin(), "-y", "-v", "error"]
    if spec.loop_count > 0:
        # -stream_loop repeats the input container, which works under -c copy.
        cmd += ["-stream_loop", str(spec.loop_count)]
    cmd += ["-i", input_path]
    if stream_copy:
        cmd += ["-c", "copy"]
    else:
        cmd += video_output_args(spec, apply_color=False)
        cmd += audio_output_args(spec)
    cmd += _metadata_block(spec, target_ext, prompt, extra_pnginfo)
    cmd.append(output_path)
    return cmd


def build_raw_encode_command(
    spec: EncodeSpec,
    width: int,
    height: int,
    fps: float,
    output_path: str,
    n_frames: int | None = None,
    filter_prefix: str = "",
    prompt=None,
    extra_pnginfo: dict | None = None,
    extra_output_args: list[str] | None = None,
) -> list[str]:
    """Full ffmpeg command for encoding raw RGB frames piped on stdin.

    Pass ``prompt``/``extra_pnginfo`` to embed the workflow in the container;
    the ``-movflags`` it needs are merged with ``faststart`` automatically.
    """
    cmd = [get_ffmpeg_bin(), "-y", "-v", "error"]
    cmd += raw_input_args(width, height, fps, spec.bit_depth)
    vf = video_filter(spec, n_frames=n_frames, prefix=filter_prefix)
    if vf:
        cmd += ["-vf", vf]
    cmd += video_output_args(spec)
    cmd += _metadata_block(spec, None, prompt, extra_pnginfo)
    if extra_output_args:
        cmd += extra_output_args
    cmd.append(output_path)
    return cmd


# --------------------------------------------------------------------------
# Tensor helpers
# --------------------------------------------------------------------------


def frames_to_bytes(chunk: torch.Tensor, bit_depth: int = 8) -> np.ndarray:
    """Convert a float IMAGE chunk in [0, 1] to raw ``rgb24``/``rgb48le`` bytes.

    Rounds half-up rather than truncating.  A plain ``(x * 255).to(uint8)``
    cast sends 0.999 to 254, darkening every frame by up to 1/255.
    """
    scale = 65535.0 if int(bit_depth) >= 10 else 255.0
    if chunk.shape[-1] > 3:
        chunk = chunk[..., :3]
    scaled = chunk.detach().float().mul(scale).add_(0.5).clamp_(0, scale)
    if scale > 255.0:
        # torch has no complete uint16 support; go through numpy.
        return scaled.cpu().contiguous().numpy().astype(np.uint16)
    return scaled.to(torch.uint8).cpu().contiguous().numpy()


def pad_to_alignment(images: torch.Tensor, alignment: int = 2) -> torch.Tensor:
    """Replication-pad an IMAGE batch so W/H are multiples of ``alignment``.

    yuv420p requires even dimensions; edge replication avoids the black
    fringe a constant pad would leave.
    """
    alignment = max(1, int(alignment))
    if alignment == 1:
        return images
    h, w = images.shape[1], images.shape[2]
    pad_w = (-w) % alignment
    pad_h = (-h) % alignment
    if not pad_w and not pad_h:
        return images
    padfunc = torch.nn.ReplicationPad2d((0, pad_w, 0, pad_h))
    return (
        padfunc(images.permute(0, 3, 1, 2))
        .permute(0, 2, 3, 1)
        .contiguous()
    )


def apply_pingpong(images: torch.Tensor) -> torch.Tensor:
    """Append the reversed interior of a batch so playback boomerangs.

    Endpoints are dropped from the reversed half so they are not duplicated.
    """
    if images.shape[0] < 3:
        return images
    return torch.cat([images, images.flip(0)[1:-1]], dim=0)
