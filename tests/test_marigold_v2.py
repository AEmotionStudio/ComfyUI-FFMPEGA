"""Tests for the Marigold V2 backend and its integration surfaces.

Marigold V2 shares the ``marigold`` skill and no-LLM mode with v1.1 — the
version rides on a suffix in ``output_type`` rather than a separate widget, so
most of what is worth testing is that the suffix routes to the right backend.

Everything here must import and pass without torch, diffusers or a GPU: CI
installs none of them.
"""

import sys

import pytest
from unittest.mock import patch, MagicMock

from skills.registry import get_registry

try:
    import torch  # noqa: F401
    _has_torch = True
except (ImportError, RuntimeError):
    _has_torch = False


# ── Model registry ─────────────────────────────────────────────────


class TestMarigoldV2Registry:
    """The task table is the contract against the HuggingFace repo layout."""

    def test_three_tasks(self):
        from core import marigold_v2_synthesizer as mg2

        assert set(mg2.task_names()) == {"depth", "normals", "albedo"}

    def test_filenames_match_upstream_repo(self):
        """Filenames are asymmetric upstream — depth carries a _log_stage2
        suffix on its LoRA and VAE but not on its conditioning. Pin them so a
        well-meaning f-string refactor can't quietly break the depth task."""
        from core import marigold_v2_synthesizer as mg2

        expected = {
            "depth": (
                "marigold_v2_depth_log_stage2.safetensors",
                "marigold_v2_depth_log_stage2_vae.safetensors",
                "marigold_v2_depth_conditioning.safetensors",
            ),
            "normals": (
                "marigold_v2_normals.safetensors",
                "marigold_v2_normals_vae.safetensors",
                "marigold_v2_normals_conditioning.safetensors",
            ),
            "albedo": (
                "marigold_v2_albedo.safetensors",
                "marigold_v2_albedo_vae.safetensors",
                "marigold_v2_albedo_conditioning.safetensors",
            ),
        }
        for task, (lora, vae, cond) in expected.items():
            cfg = mg2._TASKS[task]
            assert cfg["lora"] == lora
            assert cfg["vae"] == vae
            assert cfg["conditioning"] == cond

    def test_folders_match_comfyui_model_dirs(self):
        from core import marigold_v2_synthesizer as mg2

        assert mg2._FOLDERS == {
            "unet": "diffusion_models",
            "lora": "loras",
            "vae": "vae",
            "conditioning": "embeddings",
        }

    def test_required_files_include_shared_base(self):
        from core import marigold_v2_synthesizer as mg2

        files = mg2._required_files("normals")
        assert files["unet"] == mg2.BASE_UNET
        assert len(files) == 4

    def test_sigma_is_half(self):
        """The reference's bf16 499.0 rounds ties-to-even to 500.0, so its
        effective timestep is exactly 0.5. Guard against a 0.499 'fix'."""
        from core import marigold_v2_synthesizer as mg2

        assert mg2.SIGMA == 0.5

    def test_invalid_task_rejected(self):
        from core import marigold_v2_synthesizer as mg2

        with pytest.raises(ValueError, match="output_type"):
            mg2._required_files  # touch module
            mg2.run_marigold_v2("/tmp/nope.png", output_type="lighting")


# ── Version routing ────────────────────────────────────────────────


class TestVersionRouting:
    """`depth (v2)` must reach the V2 backend; bare `depth` must not."""

    @pytest.mark.parametrize("value,version,task", [
        ("depth", "v1.1", "depth"),
        ("normals", "v1.1", "normals"),
        ("appearance", "v1.1", "appearance"),
        ("lighting", "v1.1", "lighting"),
        ("depth (v2)", "v2", "depth"),
        ("normals (v2)", "v2", "normals"),
        ("albedo (v2)", "v2", "albedo"),
    ])
    def test_split_version(self, value, version, task):
        pytest.importorskip("torch")
        from nodes.modes.marigold import _split_version

        assert _split_version(value) == (version, task)

    def test_widget_offers_every_valid_combination(self):
        """7 states, not 8 — albedo is v2-only, appearance/lighting are v1.1-only."""
        from nodes.agent_widgets.vision import marigold

        options = marigold()["marigold_output_type"][0]
        assert options == [
            "depth", "normals", "appearance", "lighting",
            "depth (v2)", "normals (v2)", "albedo (v2)",
        ]

    def test_v2_is_the_default(self):
        from nodes.agent_widgets.vision import marigold

        assert marigold()["marigold_output_type"][1]["default"] == "depth (v2)"

    def test_v1_options_come_first(self):
        """Existing saved workflows restore combo values as strings, so the
        v1.1 names must survive verbatim."""
        from nodes.agent_widgets.vision import marigold

        options = marigold()["marigold_output_type"][0]
        for legacy in ("depth", "normals", "appearance", "lighting"):
            assert legacy in options


# ── Skill handler ──────────────────────────────────────────────────


class TestMarigoldV2Handler:
    """_f_marigold routes on the suffix and validates the widened enum."""

    @patch("skills.handlers.marigold.os.path.isfile", return_value=True)
    def test_v2_output_types_accepted(self, mock_isfile):
        from skills.handlers.marigold import _f_marigold

        for output_type in ("depth (v2)", "normals (v2)", "albedo (v2)"):
            mock_run = MagicMock(return_value="/tmp/out.png")
            mock_mod = MagicMock(run_marigold_v2=mock_run)
            with patch.dict(sys.modules, {"core.marigold_v2_synthesizer": mock_mod}):
                result = _f_marigold({
                    "_input_path": "/tmp/test.png",
                    "output_type": output_type,
                })
            assert "error" not in result, result
            assert result["movie"] == "/tmp/out.png"
            # The suffix must be stripped before it reaches the backend.
            assert mock_run.call_args.kwargs["output_type"] == output_type[:-5]

    @patch("skills.handlers.marigold.os.path.isfile", return_value=True)
    def test_v2_does_not_call_v1_backend(self, mock_isfile):
        from skills.handlers.marigold import _f_marigold

        v1 = MagicMock(run_marigold=MagicMock(return_value="/tmp/v1.mp4"))
        v2 = MagicMock(run_marigold_v2=MagicMock(return_value="/tmp/v2.png"))
        with patch.dict(sys.modules, {
            "core.marigold_synthesizer": v1,
            "core.marigold_v2_synthesizer": v2,
        }):
            _f_marigold({"_input_path": "/tmp/t.png", "output_type": "depth (v2)"})

        v2.run_marigold_v2.assert_called_once()
        v1.run_marigold.assert_not_called()

    @patch("skills.handlers.marigold.os.path.isfile", return_value=True)
    def test_v1_does_not_call_v2_backend(self, mock_isfile):
        from skills.handlers.marigold import _f_marigold

        v1 = MagicMock(run_marigold=MagicMock(return_value="/tmp/v1.mp4"))
        v2 = MagicMock(run_marigold_v2=MagicMock(return_value="/tmp/v2.png"))
        with patch.dict(sys.modules, {
            "core.marigold_synthesizer": v1,
            "core.marigold_v2_synthesizer": v2,
        }):
            _f_marigold({"_input_path": "/tmp/t.mp4", "output_type": "depth"})

        v1.run_marigold.assert_called_once()
        v2.run_marigold_v2.assert_not_called()

    @patch("skills.handlers.marigold.os.path.isfile", return_value=True)
    def test_albedo_without_suffix_is_rejected(self, mock_isfile):
        """Bare 'albedo' is not a v1.1 modality — it must not silently pass."""
        from skills.handlers.marigold import _f_marigold

        result = _f_marigold({"_input_path": "/tmp/t.png", "output_type": "albedo"})
        assert "error" in result

    def test_skill_documents_both_versions(self):
        registry = get_registry()
        param = registry.get("marigold").get_param("output_type")
        assert "(v2)" in param.description


# ── Registration in shared infrastructure ──────────────────────────


class TestMarigoldV2Registration:
    """Omissions here fail silently at runtime, so assert them explicitly."""

    def test_registered_for_vram_eviction(self):
        """Missing from ALL_SYNTHESIZER_MODULES means it never gets evicted
        when another model needs VRAM — a silent OOM, not an error."""
        from core._vram_utils import ALL_SYNTHESIZER_MODULES

        assert "marigold_v2_synthesizer" in ALL_SYNTHESIZER_MODULES

    def test_registered_in_model_manager(self):
        from core.model_manager import _MODEL_INFO

        assert "marigold_v2" in _MODEL_INFO
        assert _MODEL_INFO["marigold_v2"]["mirror_repo"] == "Comfy-Org/marigold-v2-0"

    def test_hf_repo_is_pinned(self):
        """Comfy-Org is third-party, so repo policy says pin it to a SHA."""
        from core.hf_pins import PINNED_REVISIONS
        from core import marigold_v2_synthesizer as mg2

        assert PINNED_REVISIONS.get("Comfy-Org/marigold-v2-0") == mg2.HF_REVISION
        assert len(mg2.HF_REVISION) == 40

    def test_albedo_alias_dispatches_to_marigold(self):
        from skills.composer import SkillComposer

        assert SkillComposer.SKILL_ALIASES.get("albedo") == "marigold"


# ── Shader bridge integration ──────────────────────────────────────


class TestDepthShaderBridge:
    def test_backends_advertised(self):
        from core.depth_shader_bridge import DEPTH_BACKENDS, NORMAL_BACKENDS

        assert "marigold-v2" in DEPTH_BACKENDS
        assert "marigold-v2" in NORMAL_BACKENDS

    def test_depth_map_matches_vda_polarity(self):
        """VDA's ReLU head emits disparity, i.e. near=white. Marigold V2's raw
        log depth is the opposite, so the bridge must invert it — otherwise
        swapping backend silently flips every focus mask."""
        from core import depth_shader_bridge as bridge

        mock_run = MagicMock(return_value="/tmp/depth.mp4")
        with patch.dict(sys.modules, {
            "core.marigold_v2_synthesizer": MagicMock(run_marigold_v2=mock_run),
        }), patch.object(bridge.os.path, "isfile", return_value=True):
            bridge.generate_depth_map("/tmp/in.mp4", backend="marigold-v2")

        assert mock_run.call_args.kwargs["depth_polarity"] == "near_bright"

    def test_normals_do_not_set_depth_polarity(self):
        from core import depth_shader_bridge as bridge

        mock_run = MagicMock(return_value="/tmp/n.mp4")
        with patch.dict(sys.modules, {
            "core.marigold_v2_synthesizer": MagicMock(run_marigold_v2=mock_run),
        }), patch.object(bridge.os.path, "isfile", return_value=True):
            bridge.generate_normal_map("/tmp/in.mp4", backend="marigold-v2")

        assert mock_run.call_args.kwargs["output_type"] == "normals"

    def test_default_backend_still_vda(self):
        """Marigold V2 is ~100x slower per frame — it must stay opt-in."""
        import inspect
        from core.depth_shader_bridge import generate_depth_map, generate_normal_map

        assert inspect.signature(generate_depth_map).parameters["backend"].default == "vda"
        assert inspect.signature(
            generate_normal_map).parameters["backend"].default == "normalcrafter"


# ── Block swap ─────────────────────────────────────────────────────


class TestBlockSwapDiscovery:
    """Qwen-Image names its stack `transformer_blocks`, not `blocks`."""

    def _patcher(self, **attrs):
        diffusion_model = type("DM", (), attrs)()
        model = type("M", (), {"diffusion_model": diffusion_model})()
        return type("P", (), {"model": model})()

    def test_finds_wan_style_blocks(self):
        from core.blockswap import find_transformer_blocks

        p = self._patcher(blocks=[1, 2, 3])
        assert find_transformer_blocks(p) == [1, 2, 3]

    def test_finds_qwen_image_transformer_blocks(self):
        from core.blockswap import find_transformer_blocks

        p = self._patcher(transformer_blocks=list(range(60)))
        assert len(find_transformer_blocks(p)) == 60

    def test_prefers_blocks_over_transformer_blocks(self):
        """Wan-family callers must keep their existing arithmetic."""
        from core.blockswap import find_transformer_blocks

        p = self._patcher(blocks=[1], transformer_blocks=[1, 2, 3])
        assert find_transformer_blocks(p) == [1]

    def test_ignores_empty_stacks(self):
        from core.blockswap import find_transformer_blocks

        p = self._patcher(blocks=[], transformer_blocks=[1, 2])
        assert find_transformer_blocks(p) == [1, 2]

    def test_returns_none_when_absent(self):
        from core.blockswap import find_transformer_blocks

        assert find_transformer_blocks(self._patcher()) is None

    def test_returns_none_without_diffusion_model(self):
        from core.blockswap import find_transformer_blocks

        assert find_transformer_blocks(object()) is None


# ── Post-processing maths ──────────────────────────────────────────


@pytest.mark.skipif(not _has_torch, reason="PyTorch not available")
class TestPostProcess:
    def test_depth_near_bright_inverts(self):
        import torch
        from core.marigold_v2_synthesizer import postprocess

        # Raw log depth increases with distance.
        raw = torch.tensor([0.0, 1.0]).view(1, 1, 2, 1).repeat(1, 1, 1, 3)
        near = postprocess(raw, "depth", depth_polarity="near_bright")
        far = postprocess(raw, "depth", depth_polarity="far_bright")

        assert near[0, 0, 0, 0].item() == pytest.approx(1.0)   # near -> white
        assert near[0, 0, 1, 0].item() == pytest.approx(0.0)
        assert far[0, 0, 0, 0].item() == pytest.approx(0.0)    # near -> black
        assert far[0, 0, 1, 0].item() == pytest.approx(1.0)

    def test_global_range_keeps_frames_comparable(self):
        """Per-frame normalisation is the classic depth-video flicker."""
        import torch
        from core.marigold_v2_synthesizer import postprocess

        frame_a = torch.tensor([0.0, 1.0]).view(1, 1, 2, 1).repeat(1, 1, 1, 3)
        frame_b = torch.tensor([0.0, 2.0]).view(1, 1, 2, 1).repeat(1, 1, 1, 3)
        batch = torch.cat([frame_a, frame_b], dim=0)

        glob = postprocess(batch, "depth", depth_range="global")
        per = postprocess(batch, "depth", depth_range="per_frame")

        # Under a shared range the two frames' midpoints differ...
        assert glob[0, 0, 1, 0].item() != pytest.approx(glob[1, 0, 1, 0].item())
        # ...but per-frame normalisation crushes both to the same value.
        assert per[0, 0, 1, 0].item() == pytest.approx(per[1, 0, 1, 0].item())

    def test_normals_are_unit_length(self):
        import torch
        from core.marigold_v2_synthesizer import postprocess

        raw = torch.tensor([3.0, 0.0, 4.0]).view(1, 1, 1, 3)
        out = postprocess(raw, "normals")
        unit = out * 2.0 - 1.0
        assert unit.pow(2).sum().sqrt().item() == pytest.approx(1.0, abs=1e-5)

    def test_degenerate_normals_go_neutral_not_noisy(self):
        """F.normalize's eps=1e-12 would amplify this to unit length."""
        import torch
        from core.marigold_v2_synthesizer import postprocess

        raw = torch.zeros(1, 1, 1, 3)
        out = postprocess(raw, "normals")
        assert out.abs().max().item() == pytest.approx(0.5)

    def test_albedo_uses_gamma_22(self):
        """The reference labels this 'the Marigold V1 gamma-2.2 conversion';
        ComfyUI's node uses the piecewise sRGB curve instead."""
        import torch
        from core.marigold_v2_synthesizer import postprocess

        raw = torch.zeros(1, 1, 1, 3)  # -> linear 0.5
        out = postprocess(raw, "albedo")
        assert out[0, 0, 0, 0].item() == pytest.approx(0.5 ** (1 / 2.2), abs=1e-5)

    def test_outputs_are_three_channel_and_in_range(self):
        import torch
        from core.marigold_v2_synthesizer import postprocess

        raw = torch.randn(2, 4, 4, 3)
        for output_type in ("depth", "normals", "albedo"):
            out = postprocess(raw, output_type)
            assert out.shape == (2, 4, 4, 3)
            assert out.min().item() >= -1e-6
            assert out.max().item() <= 1.0 + 1e-6


# ── Grid rounding ──────────────────────────────────────────────────


class TestGridRounding:
    """Qwen-Image patchifies 2x2 over an 8x VAE downscale = 16px granularity."""

    @pytest.mark.parametrize("value,expected", [
        (1024, 1024), (1023, 1008), (1025, 1024), (17, 16), (16, 16), (1, 16), (0, 16),
    ])
    def test_rounds_down_to_multiple_of_16(self, value, expected):
        from core.marigold_v2_synthesizer import _round_to_grid

        assert _round_to_grid(value) == expected
