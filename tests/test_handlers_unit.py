"""Unit tests for individual handler functions.

These tests call _f_* handlers directly with plain dicts, bypassing
compose() entirely.  This isolates handler logic from orchestration
so regressions are caught at the right layer.

All handlers now return ``HandlerResult`` (always 5 fields via __iter__).
"""

import pytest

from skills.handler_contract import HandlerResult

# ── Spatial handlers ───────────────────────────────────────────────

from skills.handlers.spatial import (
    _f_resize, _f_crop, _f_pad, _f_rotate, _f_flip, _f_zoom, _f_ken_burns,
)


class TestSpatialHandlers:

    def test_resize_basic(self):
        r = _f_resize({"width": 1280, "height": 720})
        assert isinstance(r, HandlerResult)
        assert r.video_filters == ["scale=1280:720"]
        assert r.audio_filters == []
        assert r.output_options == []

    def test_resize_auto_height(self):
        """When only width is set, height defaults to -2 (even dims)."""
        r = _f_resize({"width": 1280})
        assert "scale=1280:-2" in r.video_filters[0]

    def test_resize_minus_one_corrected(self):
        """scale=-1 should be auto-corrected to -2 for even dimensions."""
        r = _f_resize({"width": -1, "height": 720})
        assert "-2" in r.video_filters[0]
        assert "-1" not in r.video_filters[0]

    def test_crop_defaults(self):
        r = _f_crop({})
        assert len(r.video_filters) == 1
        assert r.video_filters[0].startswith("crop=")

    def test_pad_with_color(self):
        r = _f_pad({"width": 1920, "height": 1080, "color": "red"})
        assert "red" in r.video_filters[0]
        assert r.video_filters[0].startswith("pad=")

    def test_rotate_90(self):
        r = _f_rotate({"angle": 90})
        assert r.video_filters == ["transpose=1"]

    def test_rotate_180(self):
        r = _f_rotate({"angle": 180})
        assert "transpose" in r.video_filters[0]

    def test_rotate_arbitrary(self):
        r = _f_rotate({"angle": 45})
        assert "rotate=" in r.video_filters[0]

    def test_flip_horizontal(self):
        r = _f_flip({"direction": "horizontal"})
        assert r.video_filters == ["hflip"]

    def test_flip_vertical(self):
        r = _f_flip({"direction": "vertical"})
        assert r.video_filters == ["vflip"]

    def test_zoom_default(self):
        r = _f_zoom({})
        assert len(r.video_filters) == 1
        assert "crop=" in r.video_filters[0]
        assert "scale=" in r.video_filters[0]

    def test_ken_burns_zoom_in(self):
        r = _f_ken_burns({"direction": "zoom_in"})
        assert len(r.video_filters) == 1
        assert "zoompan" in r.video_filters[0]

    def test_iter_unpacking(self):
        """HandlerResult supports 5-tuple unpacking for backward compat."""
        vf, af, opts, fc, io = _f_resize({"width": 640, "height": 480})
        assert vf == ["scale=640:480"]
        assert af == []
        assert opts == []
        assert fc == ""
        assert io == []


# ── Temporal handlers ──────────────────────────────────────────────

from skills.handlers.temporal import (
    _f_trim, _f_speed, _f_reverse, _f_loop, _f_boomerang, _f_jump_cut,
)


class TestTemporalHandlers:

    def test_trim_start_duration(self):
        r = _f_trim({"start": 5, "duration": 30})
        assert isinstance(r, HandlerResult)
        assert "-ss" in r.input_options or "-ss" in r.output_options
        assert "-t" in r.output_options

    def test_trim_start_end(self):
        r = _f_trim({"start": 10, "end": 20})
        assert "-t" in r.output_options
        t_idx = r.output_options.index("-t")
        assert float(r.output_options[t_idx + 1]) == 10.0

    def test_speed_normal(self):
        r = _f_speed({"factor": 2.0})
        assert len(r.video_filters) == 1
        assert "setpts=" in r.video_filters[0]
        assert len(r.audio_filters) >= 1
        assert "atempo=" in r.audio_filters[0]

    def test_speed_very_slow(self):
        """Factor < 0.5 should chain multiple atempo filters."""
        r = _f_speed({"factor": 0.25})
        assert len(r.audio_filters) >= 2  # Multiple atempo needed for < 0.5

    def test_reverse(self):
        r = _f_reverse({})
        assert "reverse" in r.video_filters
        assert "areverse" in r.audio_filters

    def test_loop(self):
        r = _f_loop({"count": 3})
        assert isinstance(r, HandlerResult)
        assert "-stream_loop" in r.input_options
        assert "3" in r.input_options

    def test_boomerang(self):
        r = _f_boomerang({"loops": 3})
        assert len(r.video_filters) == 1
        assert "reverse" in r.video_filters[0]
        assert "concat" in r.video_filters[0]

    def test_jump_cut(self):
        r = _f_jump_cut({"threshold": 0.03})
        assert len(r.video_filters) == 1
        assert "select=" in r.video_filters[0]
        assert "-an" in r.output_options  # Audio must be dropped


# ── Audio handlers ─────────────────────────────────────────────────

from skills.handlers.audio import (
    _f_volume, _f_normalize, _f_fade_audio, _f_remove_audio,
    _f_replace_audio, _f_mix_audio, _f_audio_crossfade,
)


class TestAudioHandlers:

    def test_volume(self):
        r = _f_volume({"level": 0.5})
        assert r.video_filters == []
        assert r.audio_filters == ["volume=0.5"]
        assert r.output_options == []

    def test_normalize(self):
        r = _f_normalize({})
        assert r.audio_filters == ["loudnorm"]

    def test_fade_audio_in(self):
        r = _f_fade_audio({"type": "in", "start": 0, "duration": 2})
        assert len(r.audio_filters) == 1
        assert "afade=t=in" in r.audio_filters[0]
        assert "d=2" in r.audio_filters[0]

    def test_remove_audio(self):
        r = _f_remove_audio({})
        assert "-an" in r.output_options
        assert r.video_filters == []
        assert r.audio_filters == []

    def test_replace_audio(self):
        r = _f_replace_audio({})
        assert "-map" in r.output_options
        assert "0:v" in r.output_options
        assert "1:a" in r.output_options

    def test_audio_crossfade(self):
        r = _f_audio_crossfade({"duration": 2.0, "curve": "tri"})
        assert isinstance(r, HandlerResult)
        assert "acrossfade" in r.filter_complex
        assert "d=2.0" in r.filter_complex

    def test_mix_audio_defaults(self):
        r = _f_mix_audio({})
        assert isinstance(r, HandlerResult)
        assert "amix" in r.filter_complex
        assert "duration=longest" in r.filter_complex


# ── Visual handlers ────────────────────────────────────────────────

from skills.handlers.visual import (
    _f_brightness, _f_contrast, _f_saturation, _f_fade,
    _f_chromakey, _f_glow, _f_mask_blur, _f_vignette,
)


class TestVisualHandlers:

    def test_brightness(self):
        r = _f_brightness({"value": 0.1})
        assert r.video_filters == ["eq=brightness=0.1"]

    def test_contrast(self):
        r = _f_contrast({"value": 1.5})
        assert "eq=contrast=1.5" in r.video_filters[0]

    def test_saturation(self):
        r = _f_saturation({"value": 1.3})
        assert "eq=saturation=1.3" in r.video_filters[0]

    def test_fade_in(self):
        r = _f_fade({"type": "in", "duration": 2})
        assert len(r.video_filters) == 1
        assert "fade=t=in" in r.video_filters[0]

    def test_fade_both(self):
        r = _f_fade({"type": "both", "duration": 1, "start": 5})
        assert len(r.video_filters) == 2  # Both in and out
        assert any("fade=t=in" in f for f in r.video_filters)
        assert any("fade=t=out" in f for f in r.video_filters)

    def test_vignette(self):
        r = _f_vignette({"intensity": 0.5})
        assert len(r.video_filters) == 1
        assert "vignette=angle=" in r.video_filters[0]

    def test_chromakey_default(self):
        """Default chromakey produces filter_complex with colorkey + overlay."""
        r = _f_chromakey({"color": "green"})
        assert isinstance(r, HandlerResult)
        assert "colorkey=" in r.filter_complex
        assert "overlay" in r.filter_complex

    def test_chromakey_transparent(self):
        r = _f_chromakey({"color": "0x00FF00", "background": "transparent"})
        assert len(r.video_filters) == 1
        assert "colorkey=" in r.video_filters[0]

    def test_glow(self):
        r = _f_glow({"radius": 30, "strength": 0.4})
        assert isinstance(r, HandlerResult)
        assert "gblur" in r.filter_complex
        assert "blend" in r.filter_complex

    def test_mask_blur(self):
        r = _f_mask_blur({"x": 100, "y": 100, "w": 200, "h": 200})
        assert isinstance(r, HandlerResult)
        assert "boxblur" in r.filter_complex
        assert "overlay" in r.filter_complex


# ── Multi-input handlers ──────────────────────────────────────────

from skills.handlers.multi_input import (
    _f_concat, _f_xfade, _f_overlay_image, _f_grid, _f_split_screen, _f_pip,
)


class TestMultiInputHandlers:

    def test_concat_basic(self):
        r = _f_concat({
            "_extra_input_count": 1,
            "_extra_input_paths": ["/extra.mp4"],
        })
        assert isinstance(r, HandlerResult)
        assert "concat=n=2:v=1:a=0" in r.filter_complex

    def test_concat_with_audio(self):
        r = _f_concat({
            "_extra_input_count": 1,
            "_extra_input_paths": ["/extra.mp4"],
            "_has_embedded_audio": True,
        })
        assert "concat=n=2:v=1:a=1" in r.filter_complex
        assert "[0:a]" in r.filter_complex
        assert "[1:a]" in r.filter_complex

    def test_concat_no_extras(self):
        """With no extra inputs, concat should return empty."""
        r = _f_concat({"_extra_input_count": 0})
        assert r.filter_complex == ""

    def test_concat_excludes_overlay_inputs(self):
        """Inputs marked in _exclude_inputs should be skipped."""
        r = _f_concat({
            "_extra_input_count": 2,
            "_extra_input_paths": ["/logo.png", "/extra.mp4"],
            "_exclude_inputs": {1},  # Skip logo.png at index 1
        })
        # Should only concat 2 segments (main + extra.mp4), not 3
        assert "concat=n=2" in r.filter_complex

    def test_xfade_basic(self):
        r = _f_xfade({
            "_extra_input_count": 1,
            "_extra_input_paths": ["/extra.mp4"],
            "_video_duration": 5.0,
        })
        assert "xfade=" in r.filter_complex
        assert "transition=fade" in r.filter_complex

    def test_xfade_with_audio(self):
        r = _f_xfade({
            "_extra_input_count": 1,
            "_extra_input_paths": ["/extra.mp4"],
            "_video_duration": 5.0,
            "_has_embedded_audio": True,
        })
        assert "xfade=" in r.filter_complex
        assert "acrossfade" in r.filter_complex
        assert "-map" in r.output_options

    def test_overlay_image_single(self):
        r = _f_overlay_image({
            "_extra_input_count": 1,
            "position": "bottom-right",
            "scale": 0.2,
        })
        assert "overlay=" in r.filter_complex
        assert "scale=" in r.filter_complex

    def test_overlay_image_no_extras(self):
        r = _f_overlay_image({"_extra_input_count": 0})
        assert r.filter_complex == ""

    def test_grid_basic(self):
        r = _f_grid({
            "_extra_input_count": 3,
            "_extra_input_paths": ["/a.jpg", "/b.jpg", "/c.jpg"],
            "columns": 2,
        })
        assert "xstack=" in r.filter_complex

    def test_grid_too_few_inputs(self):
        r = _f_grid({
            "_extra_input_count": 0,
            "include_video": "false",
        })
        assert r.filter_complex == ""

    def test_split_screen_horizontal(self):
        r = _f_split_screen({
            "_extra_input_count": 1,
            "_extra_input_paths": ["/extra.mp4"],
            "layout": "horizontal",
        })
        assert "hstack" in r.filter_complex

    def test_split_screen_vertical(self):
        r = _f_split_screen({
            "_extra_input_count": 1,
            "_extra_input_paths": ["/extra.mp4"],
            "layout": "vertical",
        })
        assert "vstack" in r.filter_complex

    def test_pip_basic(self):
        r = _f_pip({
            "position": "bottom_right",
            "scale": 0.25,
        })
        assert "overlay=" in r.filter_complex
        assert "[pip]" in r.filter_complex

    def test_pip_with_audio_mix(self):
        r = _f_pip({
            "position": "top_left",
            "scale": 0.3,
            "audio_mix": True,
        })
        assert "amix" in r.filter_complex
        assert "-map" in r.output_options


# ── Encoding handlers ─────────────────────────────────────────────

from skills.handlers.encoding import (
    _f_compress, _f_convert, _f_quality, _f_gif, _f_hwaccel,
)


class TestEncodingHandlers:

    def test_compress_medium(self):
        r = _f_compress({"preset": "medium"})
        assert "-c:v" in r.output_options
        assert "libx264" in r.output_options
        assert "-crf" in r.output_options
        assert "23" in r.output_options

    def test_compress_heavy(self):
        r = _f_compress({"preset": "heavy"})
        assert "28" in r.output_options  # Higher CRF for heavy compression

    def test_convert_h265(self):
        r = _f_convert({"codec": "h265"})
        assert "libx265" in r.output_options

    def test_quality(self):
        r = _f_quality({"crf": 18, "preset": "slow"})
        assert "18" in r.output_options
        assert "slow" in r.output_options

    def test_gif(self):
        r = _f_gif({"width": 320, "fps": 10})
        assert len(r.video_filters) == 1
        assert "palettegen" in r.video_filters[0]
        assert "fps=10" in r.video_filters[0]

    def test_hwaccel(self):
        r = _f_hwaccel({"type": "cuda"})
        assert isinstance(r, HandlerResult)
        assert "-hwaccel" in r.input_options
        assert "cuda" in r.input_options
