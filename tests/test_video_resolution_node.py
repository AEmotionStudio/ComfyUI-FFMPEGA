"""Tests for the FFMPEGA Video Resolution node.

Pure-math: no torch, no ComfyUI runtime.  The module falls back to local
implementations of the MiniMax H3 helpers when comfy_extras is unavailable,
which is exactly the path exercised here.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

# Load the module directly to avoid ComfyUI deps in nodes/__init__.py
_path = Path(__file__).resolve().parent.parent / "nodes" / "video_resolution_node.py"
_spec = importlib.util.spec_from_file_location("video_resolution_node", _path)
_mod = importlib.util.module_from_spec(_spec)
sys.modules["video_resolution_node"] = _mod
_spec.loader.exec_module(_mod)

VideoResolutionNode = _mod.VideoResolutionNode
MODEL_SPECS = _mod.MODEL_SPECS
ASPECT_RATIOS = _mod.ASPECT_RATIOS
BUCKETS = _mod.BUCKETS
snap_frames = _mod.snap_frames
latent_tokens = _mod.latent_tokens
resolve_dimensions = _mod.resolve_dimensions

ALL_MODELS = list(MODEL_SPECS.keys())


class TestGridAlignment:
    """Every produced dimension must land on the model's pixel grid."""

    @pytest.mark.parametrize("model_type", ALL_MODELS)
    @pytest.mark.parametrize("bucket", BUCKETS)
    @pytest.mark.parametrize("aspect_ratio", list(ASPECT_RATIOS.keys()))
    def test_bucket_dims_on_grid(self, model_type, bucket, aspect_ratio):
        mult = MODEL_SPECS[model_type]["multiple"]
        w, h = resolve_dimensions(model_type, "bucket", bucket, aspect_ratio, 0.4)
        assert w % mult == 0, f"{w} not divisible by {mult}"
        assert h % mult == 0, f"{h} not divisible by {mult}"

    @pytest.mark.parametrize("model_type", ALL_MODELS)
    @pytest.mark.parametrize("mp", [0.2, 0.4, 0.5, 0.75, 1.0, 1.5, 2.0])
    def test_megapixel_dims_on_grid(self, model_type, mp):
        """The core-node bug: 0.2/0.4/0.5/0.75 MP all land off-grid at multiple=8."""
        mult = MODEL_SPECS[model_type]["multiple"]
        w, h = resolve_dimensions(model_type, "megapixels", "480p", "16:9 (Widescreen)", mp)
        assert w % mult == 0
        assert h % mult == 0

    def test_declared_buckets_are_themselves_on_grid(self):
        for model_type, spec in MODEL_SPECS.items():
            for name, (w, h) in spec["buckets"].items():
                assert w % spec["multiple"] == 0, f"{model_type}/{name} width {w}"
                assert h % spec["multiple"] == 0, f"{model_type}/{name} height {h}"

    def test_720_only_valid_on_the_16_grid(self):
        """720 = 16*45, so A14B can use it; the 32-grid models must use 704."""
        assert 720 % 16 == 0
        assert 720 % 32 != 0
        assert MODEL_SPECS["wan22_a14b"]["buckets"]["720p"] == (1280, 720)
        assert MODEL_SPECS["wan22_ti2v_5b"]["buckets"]["720p"] == (1280, 704)

    def test_bucket_dimensions_survive_verbatim(self):
        """A matching aspect ratio must return the hand-picked bucket untouched."""
        w, h = resolve_dimensions("wan22_a14b", "bucket", "480p", "16:9 (Widescreen)", 0.4)
        assert (w, h) == (832, 480)

    def test_portrait_mirrors_the_bucket(self):
        w, h = resolve_dimensions("wan22_a14b", "bucket", "480p", "9:16 (Portrait)", 0.4)
        assert (w, h) == (480, 832)


class TestFrameSnapping:
    def test_wan_snaps_to_4n_plus_1(self):
        assert snap_frames(80, "wan22_a14b") == 81
        assert snap_frames(81, "wan22_a14b") == 81
        assert snap_frames(48, "wan22_a14b") == 49
        assert snap_frames(50, "wan22_a14b") == 53

    @pytest.mark.parametrize("n", range(1, 200))
    def test_wan_result_always_on_grid(self, n):
        assert snap_frames(n, "wan22_a14b") % 4 == 1

    def test_h3_snaps_to_17k_plus_5(self):
        assert snap_frames(100, "minimax_h3") == 107
        assert snap_frames(124, "minimax_h3") == 124
        assert snap_frames(5, "minimax_h3") == 5

    @pytest.mark.parametrize("n", range(1, 400))
    def test_h3_result_always_on_grid(self, n):
        assert snap_frames(n, "minimax_h3") % 17 == 5

    def test_snapping_never_reduces(self):
        for model_type in ALL_MODELS:
            for n in range(1, 200):
                assert snap_frames(n, model_type) >= min(n, 5) or n < 5


class TestFloorEnforcement:
    """Hard error below the model's trained floor — the 0.1 MP case."""

    # H3 is canvas-locked, so it physically cannot be driven sub-native and has
    # nothing to reject; it is covered by test_canvas_locked_cannot_go_sub_native.
    @pytest.mark.parametrize(
        "model_type",
        [m for m in ALL_MODELS if not MODEL_SPECS[m].get("canvas_locked")],
    )
    def test_point_one_megapixels_rejected(self, model_type):
        result = VideoResolutionNode.VALIDATE_INPUTS(
            model_type=model_type,
            sizing="megapixels",
            megapixels=0.1,
            aspect_ratio="1:1 (Square)",
        )
        assert result is not True
        assert isinstance(result, str)
        assert "below" in result.lower()

    def test_canvas_locked_cannot_go_sub_native(self):
        """H3 clamps to its own canvas, so 0.1 MP is corrected rather than refused."""
        assert VideoResolutionNode.VALIDATE_INPUTS(
            model_type="minimax_h3", sizing="megapixels", megapixels=0.1
        ) is True
        w, h = resolve_dimensions(
            "minimax_h3", "megapixels", "480p", "16:9 (Widescreen)", 0.1
        )
        assert min(w, h) == 768

    def test_error_message_names_the_fix(self):
        result = VideoResolutionNode.VALIDATE_INPUTS(
            model_type="wan22_a14b", sizing="megapixels", megapixels=0.1
        )
        assert "832x480" in result
        assert "allow_below_native" in result

    @pytest.mark.parametrize(
        "model_type",
        [m for m in ALL_MODELS if not MODEL_SPECS[m].get("canvas_locked")],
    )
    def test_override_permits_it(self, model_type):
        result = VideoResolutionNode.VALIDATE_INPUTS(
            model_type=model_type,
            sizing="megapixels",
            megapixels=0.1,
            allow_below_native=True,
        )
        assert result is True

    @pytest.mark.parametrize("model_type", ALL_MODELS)
    def test_native_bucket_passes(self, model_type):
        native = MODEL_SPECS[model_type]["native_bucket"]
        assert VideoResolutionNode.VALIDATE_INPUTS(
            model_type=model_type, sizing="bucket", bucket=native
        ) is True

    def test_execute_raises_when_validation_bypassed(self):
        node = VideoResolutionNode()
        with pytest.raises(ValueError, match="below"):
            node.resolve(model_type="wan22_a14b", sizing="megapixels", megapixels=0.1)

    def test_rejects_unknown_model(self):
        assert VideoResolutionNode.VALIDATE_INPUTS(model_type="nope") != True  # noqa: E712


class TestH3Canvas:
    def test_area_cap_respected(self):
        """H3 clamps to a 768*1344 canvas however many megapixels you ask for."""
        w, h = resolve_dimensions(
            "minimax_h3", "megapixels", "480p", "16:9 (Widescreen)", 8.0
        )
        assert w * h <= _mod._H3_MAX_PIXELS * 1.02

    def test_short_edge_is_768_for_landscape(self):
        w, h = resolve_dimensions(
            "minimax_h3", "bucket", "1080p", "16:9 (Widescreen)", 0.4
        )
        assert min(w, h) == 768


class TestOutputs:
    def test_returns_four_values(self):
        node = VideoResolutionNode()
        out = node.resolve(model_type="wan22_a14b", sizing="bucket", bucket="480p", frames=81)
        assert len(out) == 4
        w, h, length, info = out
        assert (w, h) == (832, 480)
        assert length == 81
        assert isinstance(info, str)

    def test_info_reports_snapping(self):
        node = VideoResolutionNode()
        _, _, length, info = node.resolve(
            model_type="wan22_a14b", sizing="bucket", bucket="480p", frames=80
        )
        assert length == 81
        assert "80 -> 81" in info

    def test_info_flags_below_native_when_overridden(self):
        node = VideoResolutionNode()
        *_, info = node.resolve(
            model_type="wan22_a14b",
            sizing="megapixels",
            megapixels=0.1,
            allow_below_native=True,
        )
        assert "BELOW NATIVE" in info

    def test_info_flags_frames_below_trained_range(self):
        """H3 at Wan's default 81 snaps to 90, which is under H3's trained 124."""
        node = VideoResolutionNode()
        _, _, length, info = node.resolve(model_type="minimax_h3", frames=81)
        assert length == 90
        assert "below this model's trained range" in info

    def test_info_quiet_inside_trained_range(self):
        node = VideoResolutionNode()
        *_, info = node.resolve(model_type="wan22_a14b", bucket="480p", frames=49)
        assert "trained range" not in info

    def test_info_flags_frames_above_trained_range(self):
        node = VideoResolutionNode()
        *_, info = node.resolve(model_type="wan22_a14b", bucket="480p", frames=201)
        assert "exceeds the trained range" in info

    def test_info_flags_canvas_lock(self):
        node = VideoResolutionNode()
        *_, info = node.resolve(model_type="minimax_h3", sizing="bucket", bucket="480p")
        assert "fixed 768-short-edge canvas" in info

    def test_return_metadata_matches_arity(self):
        assert len(VideoResolutionNode.RETURN_TYPES) == 4
        assert len(VideoResolutionNode.RETURN_NAMES) == 4
        assert len(VideoResolutionNode.OUTPUT_TOOLTIPS) == 4


class TestTokenBudget:
    """The VRAM argument: frames are the cheap lever, resolution is not."""

    def test_fewer_frames_cuts_tokens_proportionally(self):
        full = latent_tokens(832, 480, 81, "wan22_a14b")
        short = latent_tokens(832, 480, 49, "wan22_a14b")
        assert short < full
        assert 0.55 < short / full < 0.70

    def test_native_bucket_is_the_baseline(self):
        node = VideoResolutionNode()
        *_, info = node.resolve(
            model_type="wan22_a14b", sizing="bucket", bucket="480p", frames=81
        )
        assert "100% of native" in info


class TestInputSchema:
    def test_input_types_wellformed(self):
        it = VideoResolutionNode.INPUT_TYPES()
        assert "required" in it and "optional" in it
        for section in it.values():
            for name, spec in section.items():
                assert isinstance(spec, tuple) and len(spec) == 2, name
                assert "tooltip" in spec[1], f"{name} missing a tooltip"

    def test_every_model_has_a_complete_spec(self):
        required = {
            "label", "multiple", "vae_spatial", "temporal_rule", "default_frames",
            "buckets", "native_bucket", "floor_pixels", "frame_note", "trained_frames",
        }
        for model_type, spec in MODEL_SPECS.items():
            assert required <= set(spec), f"{model_type} missing {required - set(spec)}"
            assert spec["native_bucket"] in spec["buckets"]
