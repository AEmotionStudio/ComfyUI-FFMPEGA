"""Tests for the shared encode-options module.

The ffmpeg integration tests pin down behaviour that was measured rather than
assumed, and that differs between FFmpeg builds:

* ``-color_primaries`` / ``-color_trc`` as *output* options are silently
  dropped by FFmpeg 8, so tagging has to go through ``setparams``.
* An untagged encode uses swscale's BT.601 matrix, which changes the pixel
  data, not just the metadata.
"""

import shutil
import subprocess

import pytest

torch = pytest.importorskip("torch")
import numpy as np  # noqa: E402

from core.video import encode_opts as eo  # noqa: E402
from core.video import metadata as md  # noqa: E402

FFMPEG = shutil.which("ffmpeg")
FFPROBE = shutil.which("ffprobe")
needs_ffmpeg = pytest.mark.skipif(
    not FFMPEG or not FFPROBE, reason="ffmpeg/ffprobe not installed"
)

# Pure green through each matrix, limited range.
GREEN_601 = 145
GREEN_709 = 173
TOLERANCE = 2  # swscale rounds slightly differently across builds


class TestColorPolicies:
    def test_labels_resolve(self):
        assert eo.resolve_color_policy("sRGB (recommended)") == "srgb"
        assert eo.resolve_color_policy("ComfyUI native match") == "native"
        assert eo.resolve_color_policy("BT.709 broadcast") == "bt709"
        assert eo.resolve_color_policy("full range (pc)") == "full"

    def test_unknown_falls_back_to_srgb(self):
        assert eo.resolve_color_policy(None) == "srgb"
        assert eo.resolve_color_policy("") == "srgb"
        assert eo.resolve_color_policy("nonsense") == "srgb"

    def test_bare_keys_pass_through(self):
        for key in eo.COLOR_POLICIES:
            assert eo.resolve_color_policy(key) == key

    def test_native_emits_no_filter(self):
        assert eo.color_filter("ComfyUI native match") == ""

    def test_srgb_tags_transfer_honestly(self):
        f = eo.color_filter("srgb")
        assert "out_color_matrix=bt709" in f
        assert "color_trc=iec61966-2-1" in f
        assert "range=tv" in f

    def test_bt709_tags_transfer_as_bt709(self):
        assert "color_trc=bt709" in eo.color_filter("bt709")

    def test_full_range_agrees_with_its_tag(self):
        # The old code tagged pc while writing tv samples; both halves must match.
        f = eo.color_filter("full")
        assert "out_range=pc" in f and "range=pc" in f


class TestOutputArgs:
    """Output args must never carry the flags FFmpeg 8 ignores."""

    @pytest.mark.parametrize("fmt", sorted(eo.FORMATS))
    @pytest.mark.parametrize("policy", sorted(eo.COLOR_POLICIES))
    def test_no_dropped_color_flags(self, fmt, policy):
        spec = eo.EncodeSpec(format=fmt, color=policy)
        args = eo.video_output_args(spec)
        for flag in ("-color_primaries", "-color_trc", "-colorspace"):
            assert flag not in args, f"{flag} is ignored by FFmpeg 8; use setparams"

    @pytest.mark.parametrize("fmt", sorted(eo.FORMATS))
    def test_format_produces_an_extension(self, fmt):
        assert eo.FORMATS[fmt].ext.startswith(".")

    def test_h264_defaults(self):
        args = eo.video_output_args(eo.EncodeSpec(format="h264-mp4", crf=19))
        assert args[:2] == ["-c:v", "libx264"]
        assert "-crf" in args and args[args.index("-crf") + 1] == "19"
        assert args[args.index("-pix_fmt") + 1] == "yuv420p"

    def test_ten_bit_switches_pix_fmt(self):
        args = eo.video_output_args(eo.EncodeSpec(format="h264-mp4", bit_depth=10))
        assert args[args.index("-pix_fmt") + 1] == "yuv420p10le"

    def test_ffv1_ten_bit_uses_a_supported_pix_fmt(self):
        # ffv1 has no yuv444p10le; it must land on the 16-bit variant.
        args = eo.video_output_args(eo.EncodeSpec(format="ffv1-mkv", bit_depth=10))
        assert args[args.index("-pix_fmt") + 1] == "yuv444p16le"

    def test_x264_preset_is_sanitized(self):
        # "good" is a VP9 deadline, not an x264 preset.
        args = eo.video_output_args(eo.EncodeSpec(format="h264-mp4", preset="good"))
        assert args[args.index("-preset") + 1] == "medium"

    def test_vp9_uses_deadline_not_preset(self):
        args = eo.video_output_args(eo.EncodeSpec(format="vp9-webm", preset="medium"))
        assert "-deadline" in args
        assert "-preset" not in args
        assert args[args.index("-b:v") + 1] == "0"

    def test_svtav1_preset_must_be_numeric(self):
        args = eo.video_output_args(eo.EncodeSpec(format="av1-webm", preset="medium"))
        assert args[args.index("-preset") + 1].isdigit()

    def test_webp_quality_scale_is_inverted(self):
        args = eo.video_output_args(eo.EncodeSpec(format="webp", crf=19))
        assert args[args.index("-q:v") + 1] == "81"

    def test_rgb_formats_skip_color_work(self):
        for fmt in ("gif", "webp"):
            spec = eo.EncodeSpec(format=fmt, color="srgb")
            assert spec.wants_color is False
            assert "setparams" not in eo.video_filter(spec)


class TestAudioArgs:
    def test_auto_uses_the_format_default(self):
        assert eo.audio_output_args(eo.EncodeSpec(format="vp9-webm"))[:2] == [
            "-c:a", "libopus",
        ]

    def test_none_disables_audio(self):
        assert eo.audio_output_args(
            eo.EncodeSpec(format="h264-mp4", audio_codec="none")
        ) == ["-an"]

    def test_silent_formats_force_an(self):
        assert eo.audio_output_args(eo.EncodeSpec(format="gif")) == ["-an"]

    def test_lossless_codecs_get_no_bitrate(self):
        args = eo.audio_output_args(
            eo.EncodeSpec(format="ffv1-mkv", audio_codec="flac")
        )
        assert "-b:a" not in args


class TestMovflags:
    def test_faststart_and_metadata_share_one_flag(self):
        # A repeated -movflags would silently drop the earlier value.
        spec = eo.EncodeSpec(format="h264-mp4", faststart=True)
        args = eo.movflags(spec, extra=("use_metadata_tags",))
        assert args.count("-movflags") == 1
        value = args[1]
        assert "faststart" in value and "use_metadata_tags" in value
        assert "+" in value

    def test_non_mov_containers_get_nothing(self):
        assert eo.movflags(eo.EncodeSpec(format="vp9-webm")) == []
        assert eo.movflags(eo.EncodeSpec(format="ffv1-mkv")) == []

    def test_source_format_needs_an_explicit_ext(self):
        spec = eo.EncodeSpec(format=eo.SOURCE_FORMAT)
        assert eo.movflags(spec, ext=".webm") == []
        assert eo.movflags(spec, ext=".mp4")[0] == "-movflags"


class TestFilters:
    def test_only_one_vf_string_is_produced(self):
        spec = eo.EncodeSpec(format="h264-mp4", loop_count=3)
        vf = eo.video_filter(spec, n_frames=16, prefix="pad=iw:ih")
        assert vf.startswith("pad=iw:ih,")
        assert "loop=loop=3:size=16" in vf
        assert "setparams" in vf

    def test_loop_needs_a_frame_count(self):
        spec = eo.EncodeSpec(format="h264-mp4", loop_count=3)
        assert "loop=" not in eo.video_filter(spec, n_frames=None)

    def test_file_path_never_applies_color(self):
        spec = eo.EncodeSpec(format="h264-mp4")
        assert eo.video_filter(spec, apply_color=False) == ""

    def test_gif_appends_the_palette_graph(self):
        vf = eo.video_filter(eo.EncodeSpec(format="gif"))
        assert "palettegen" in vf and "paletteuse" in vf


class TestRemux:
    def test_h264_can_remux_into_mp4_but_not_webm(self):
        assert eo.can_remux("h264", ".mp4") is True
        assert eo.can_remux("h264", ".webm") is False

    def test_vp9_can_remux_into_webm(self):
        assert eo.can_remux("vp9", ".webm") is True

    def test_unknown_codec_is_not_remuxable(self):
        assert eo.can_remux(None, ".mp4") is False

    def test_stream_copy_command_has_no_encoder_args(self):
        cmd = eo.build_file_command(
            eo.EncodeSpec(format="h264-mp4"), "in.mp4", "out.mp4", stream_copy=True,
        )
        assert "-c" in cmd and cmd[cmd.index("-c") + 1] == "copy"
        assert "-c:v" not in cmd

    def test_loop_uses_stream_loop_on_files(self):
        cmd = eo.build_file_command(
            eo.EncodeSpec(format="h264-mp4", loop_count=2),
            "in.mp4", "out.mp4", stream_copy=True,
        )
        assert cmd[cmd.index("-stream_loop") + 1] == "2"
        # -stream_loop must precede -i to apply to the input.
        assert cmd.index("-stream_loop") < cmd.index("-i")


class TestSpecFromWidgets:
    def test_defaults_to_source(self):
        assert eo.spec_from_widgets().is_source

    def test_unknown_format_falls_back(self):
        assert eo.spec_from_widgets(output_format="h266-mp4").format == "h264-mp4"

    def test_string_widget_values_are_coerced(self):
        spec = eo.spec_from_widgets(
            output_format="h265-mp4", crf="28", bit_depth="10", loop_count="4",
        )
        assert spec.crf == 28 and spec.bit_depth == 10 and spec.loop_count == 4

    def test_garbage_values_do_not_raise(self):
        spec = eo.spec_from_widgets(crf="abc", loop_count=None)
        assert spec.crf == 19 and spec.loop_count == 0

    def test_crf_is_clamped(self):
        assert eo.spec_from_widgets(crf=999).crf == 63


class TestTensorHelpers:
    def test_rounding_is_half_up(self):
        # A truncating cast sends 0.999 to 254, darkening every frame.
        t = torch.tensor([[[[0.999, 0.5, 0.0]]]], dtype=torch.float32)
        out = eo.frames_to_bytes(t, 8)
        assert out.dtype == np.uint8
        assert out.reshape(-1).tolist() == [255, 128, 0]

    def test_out_of_gamut_values_are_clamped_not_wrapped(self):
        # Wan latents decode slightly outside [0, 1]; an unclamped cast wraps.
        t = torch.tensor([[[[1.4, -0.3, 0.5]]]], dtype=torch.float32)
        assert eo.frames_to_bytes(t, 8).reshape(-1).tolist() == [255, 0, 128]

    def test_sixteen_bit_path(self):
        t = torch.tensor([[[[1.0, 0.5, 0.0]]]], dtype=torch.float32)
        out = eo.frames_to_bytes(t, 10)
        assert out.dtype == np.uint16
        assert out.reshape(-1).tolist() == [65535, 32768, 0]

    def test_alpha_is_dropped(self):
        t = torch.rand(2, 4, 4, 4)
        assert eo.frames_to_bytes(t, 8).shape[-1] == 3

    def test_padding_aligns_dimensions(self):
        padded = eo.pad_to_alignment(torch.rand(1, 33, 15, 3), 2)
        assert padded.shape[1] == 34 and padded.shape[2] == 16

    def test_padding_is_a_noop_when_aligned(self):
        t = torch.rand(1, 32, 16, 3)
        assert eo.pad_to_alignment(t, 2) is t

    def test_pingpong_drops_duplicate_endpoints(self):
        t = torch.arange(5, dtype=torch.float32).reshape(5, 1, 1, 1).repeat(1, 1, 1, 3)
        out = eo.apply_pingpong(t)
        assert out.shape[0] == 8
        assert [int(v) for v in out[:, 0, 0, 0]] == [0, 1, 2, 3, 4, 3, 2, 1]

    def test_pingpong_ignores_tiny_batches(self):
        t = torch.rand(2, 4, 4, 3)
        assert eo.apply_pingpong(t).shape[0] == 2

    def test_raw_input_pix_fmt_follows_bit_depth(self):
        assert "rgb24" in eo.raw_input_args(16, 16, 24, 8)
        assert "rgb48le" in eo.raw_input_args(16, 16, 24, 10)


class TestMetadata:
    def test_prompt_and_workflow_are_embedded(self):
        args = md.metadata_args({"1": {"x": 2}}, {"workflow": {"nodes": []}}, ".mp4")
        joined = " ".join(args)
        assert "prompt=" in joined and "workflow=" in joined

    def test_mp4_requires_use_metadata_tags(self):
        assert md.required_movflags(".mp4", True) == ("use_metadata_tags",)
        assert md.required_movflags(".webm", True) == ()
        assert md.required_movflags(".mp4", False) == ()

    def test_matroska_also_gets_a_comment_tag(self):
        # mkv/webm uppercase custom keys, so readers may only find `comment`.
        args = md.metadata_args(None, {"workflow": {"nodes": []}}, ".mkv")
        assert any(a.startswith("comment=") for a in args)

    def test_mp4_gets_no_redundant_comment(self):
        args = md.metadata_args(None, {"workflow": {"nodes": []}}, ".mp4")
        assert not any(a.startswith("comment=") for a in args)

    def test_empty_input_produces_nothing(self):
        assert md.metadata_args(None, None, ".mp4") == []

    def test_oversized_values_are_skipped(self):
        big = {"workflow": {"nodes": ["x" * 5000]}}
        assert md.metadata_args(None, big, ".mp4", max_bytes=1024) == []

    def test_unserializable_values_do_not_raise(self):
        assert md.metadata_args(None, {"workflow": {1, 2, 3}}, ".mp4") == []


# --------------------------------------------------------------------------
# ffmpeg integration — reproduces the measurements the design rests on
# --------------------------------------------------------------------------


def _encode_green_y(vf: str) -> int:
    """Encode one pure-green frame through ``vf`` and return its first Y byte."""
    cmd = [
        FFMPEG, "-v", "error",
        "-f", "lavfi", "-i", "color=c=0x00FF00:s=16x16:d=1:r=1",
        "-frames:v", "1",
    ]
    cmd += ["-vf", f"format=rgb24,{vf}" if vf else "format=rgb24"]
    cmd += ["-pix_fmt", "yuv420p", "-f", "rawvideo", "pipe:1"]
    out = subprocess.run(cmd, capture_output=True, timeout=60).stdout
    assert out, "ffmpeg produced no frame data"
    return out[0]


def _probe_tags(vf: str) -> list[str]:
    """Encode a short h264 stream through ``vf`` and read back its colour tags."""
    enc = [
        FFMPEG, "-v", "error",
        "-f", "lavfi", "-i", "color=c=0x00FF00:s=64x64:d=1:r=10",
        "-frames:v", "5",
    ]
    enc += ["-vf", f"format=rgb24,{vf}" if vf else "format=rgb24"]
    enc += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-f", "h264", "pipe:1"]
    stream = subprocess.run(enc, capture_output=True, timeout=60).stdout
    probe = subprocess.run(
        [
            FFPROBE, "-v", "error", "-select_streams", "v:0",
            "-show_entries",
            "stream=color_range,color_space,color_transfer,color_primaries",
            "-of", "csv=p=0", "pipe:0",
        ],
        input=stream, capture_output=True, timeout=60,
    )
    return probe.stdout.decode().strip().split(",")


@needs_ffmpeg
class TestFFmpegColorBehaviour:
    def test_srgb_and_bt709_use_the_709_matrix(self):
        for policy in ("srgb", "bt709"):
            y = _encode_green_y(eo.color_filter(policy))
            assert abs(y - GREEN_709) <= TOLERANCE, f"{policy} drifted to Y={y}"

    def test_native_matches_comfyui_601_output(self):
        y = _encode_green_y(eo.color_filter("native"))
        assert abs(y - GREEN_601) <= TOLERANCE, f"native drifted to Y={y}"

    def test_the_two_matrices_really_differ(self):
        # If these ever converge, the whole policy switch is pointless.
        assert _encode_green_y(eo.color_filter("srgb")) != _encode_green_y(
            eo.color_filter("native")
        )

    def test_srgb_writes_all_four_tags(self):
        rng, space, transfer, primaries = _probe_tags(eo.color_filter("srgb"))
        assert rng == "tv"
        assert space == "bt709"
        assert transfer == "iec61966-2-1"
        assert primaries == "bt709"

    def test_bt709_policy_tags_the_transfer_as_bt709(self):
        assert _probe_tags(eo.color_filter("bt709"))[2] == "bt709"

    def test_native_writes_no_tags(self):
        assert set(_probe_tags(eo.color_filter("native"))) == {"unknown"}

    def test_legacy_output_flags_are_indeed_dropped(self):
        """The regression this whole module exists to prevent.

        Passing the tags as output options looks correct and does nothing:
        transfer and primaries come back unknown.
        """
        enc = [
            FFMPEG, "-v", "error",
            "-f", "lavfi", "-i", "color=c=0x00FF00:s=64x64:d=1:r=10",
            "-frames:v", "5",
            "-vf", "format=rgb24,scale=out_color_matrix=bt709",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-color_range", "tv", "-colorspace", "bt709",
            "-color_primaries", "bt709", "-color_trc", "bt709",
            "-f", "h264", "pipe:1",
        ]
        stream = subprocess.run(enc, capture_output=True, timeout=60).stdout
        probe = subprocess.run(
            [
                FFPROBE, "-v", "error", "-select_streams", "v:0",
                "-show_entries", "stream=color_transfer,color_primaries",
                "-of", "csv=p=0", "pipe:0",
            ],
            input=stream, capture_output=True, timeout=60,
        )
        transfer, primaries = probe.stdout.decode().strip().split(",")
        if eo.has_setparams():
            assert transfer == "unknown" and primaries == "unknown"


@needs_ffmpeg
class TestFFmpegEncodeRoundTrip:
    @pytest.mark.parametrize(
        "fmt", ["h264-mp4", "h265-mp4", "vp9-webm", "av1-webm",
                "prores-mov", "ffv1-mkv", "gif", "webp"],
    )
    def test_every_format_encodes(self, fmt, tmp_path):
        spec = eo.EncodeSpec(format=fmt, crf=30, preset="ultrafast")
        out = tmp_path / f"out{spec.ext}"
        cmd = eo.build_raw_encode_command(
            spec, 64, 64, 10, str(out), n_frames=6,
        )
        frames = eo.frames_to_bytes(torch.rand(6, 64, 64, 3), spec.bit_depth)
        proc = subprocess.run(cmd, input=frames.tobytes(), capture_output=True,
                              timeout=180)
        assert proc.returncode == 0, proc.stderr.decode()[:800]
        assert out.exists() and out.stat().st_size > 0

    def test_ten_bit_keeps_the_tags(self, tmp_path):
        spec = eo.EncodeSpec(format="h264-mp4", bit_depth=10, crf=30,
                             preset="ultrafast")
        out = tmp_path / "out10.mp4"
        cmd = eo.build_raw_encode_command(spec, 64, 64, 10, str(out), n_frames=4)
        frames = eo.frames_to_bytes(torch.rand(4, 64, 64, 3), 10)
        proc = subprocess.run(cmd, input=frames.tobytes(), capture_output=True,
                              timeout=120)
        assert proc.returncode == 0, proc.stderr.decode()[:800]
        probe = subprocess.run(
            [
                FFPROBE, "-v", "error", "-select_streams", "v:0",
                "-show_entries", "stream=pix_fmt,color_transfer", "-of", "csv=p=0",
                str(out),
            ],
            capture_output=True, timeout=60,
        )
        pix_fmt, transfer = probe.stdout.decode().strip().split(",")
        assert pix_fmt == "yuv420p10le"
        assert transfer == "iec61966-2-1"

    def test_workflow_metadata_round_trips(self, tmp_path):
        spec = eo.EncodeSpec(format="h264-mp4", crf=30, preset="ultrafast")
        out = tmp_path / "meta.mp4"
        cmd = eo.build_raw_encode_command(
            spec, 32, 32, 10, str(out), n_frames=4,
            prompt={"1": {"class_type": "X"}},
            extra_pnginfo={"workflow": {"nodes": []}},
        )
        # faststart and use_metadata_tags must have been merged, or ffmpeg
        # would honour only the last -movflags and drop the custom keys.
        assert cmd.count("-movflags") == 1
        frames = eo.frames_to_bytes(torch.rand(4, 32, 32, 3), 8)
        proc = subprocess.run(cmd, input=frames.tobytes(), capture_output=True,
                              timeout=120)
        assert proc.returncode == 0, proc.stderr.decode()[:800]
        probe = subprocess.run(
            [FFPROBE, "-v", "error", "-show_entries", "format_tags",
             "-of", "default=nk=0", str(out)],
            capture_output=True, timeout=60,
        )
        text = probe.stdout.decode()
        assert "TAG:prompt=" in text
        assert "TAG:workflow=" in text
