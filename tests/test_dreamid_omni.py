# coding: utf-8
"""Unit tests for DreamID-Omni integration.

Tests run WITHOUT GPU or model downloads — they validate constants,
registration, function signatures, cleanup behaviour, UI wiring, and
no-LLM mode dispatch.

Follows the test_kiwi_edit.py pattern.
"""

from __future__ import annotations

import importlib
import os
import sys
import types
from typing import TYPE_CHECKING
from unittest import mock

import pytest

if TYPE_CHECKING:
    import torch
else:
    torch = pytest.importorskip("torch")

# ---------------------------------------------------------------------------
# Ensure project root is importable (mirrors conftest.py setup)
# ---------------------------------------------------------------------------
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# Mock ComfyUI modules that won't be available in CI
for mod_name in ("folder_paths", "comfy", "comfy.model_management"):
    if mod_name not in sys.modules:
        sys.modules[mod_name] = types.ModuleType(mod_name)

# Give folder_paths the minimum attributes the synthesizer expects
_fp = sys.modules["folder_paths"]
_fp.models_dir = "/tmp/comfyui_test_models"  # type: ignore[attr-defined]

# ---------------------------------------------------------------------------
# Import modules under test
# ---------------------------------------------------------------------------
from core import dreamid_omni_synthesizer as synth


# ======================================================================
# Constants
# ======================================================================

class TestConstants:
    """Verify synthesizer constants are set correctly."""

    def test_hf_repos_defined(self):
        assert synth.HF_REPO_WAN
        assert synth.HF_REPO_DREAMID
        assert synth.HF_MIRROR_DREAMID

    def test_default_params(self):
        assert synth.DEFAULT_STEPS == 50
        assert synth.DEFAULT_SOLVER == "unipc"
        assert synth.DEFAULT_SEED == 100
        assert synth.DEFAULT_SHIFT == 5.0
        assert synth.DEFAULT_VIDEO_CFG == 3.0
        assert synth.DEFAULT_VIDEO_REF_CFG == 1.5
        assert synth.DEFAULT_AUDIO_CFG == 4.0
        assert synth.DEFAULT_AUDIO_REF_CFG == 2.0

    def test_resolution_presets_defined(self):
        assert "992x512" in synth.RESOLUTION_PRESETS
        assert "1280x704" in synth.RESOLUTION_PRESETS
        # Values are (H, W) tuples
        for name, (h, w) in synth.RESOLUTION_PRESETS.items():
            assert h > 0 and w > 0
            assert h % 16 == 0, f"{name} height {h} not divisible by 16"
            assert w % 16 == 0, f"{name} width {w} not divisible by 16"

    def test_negative_prompts_defined(self):
        assert isinstance(synth.DEFAULT_VIDEO_NEG, str) and synth.DEFAULT_VIDEO_NEG
        assert isinstance(synth.DEFAULT_AUDIO_NEG, str) and synth.DEFAULT_AUDIO_NEG


# ======================================================================
# Resolution helpers
# ======================================================================

class TestResolution:
    """Test resolution selection logic."""

    def test_resolve_known_preset(self):
        h, w = synth.resolve_resolution("992x512")
        assert (h, w) == (512, 992)

    def test_resolve_known_preset_high(self):
        h, w = synth.resolve_resolution("1280x704")
        assert (h, w) == (704, 1280)

    def test_resolve_unknown_falls_back(self):
        h, w = synth.resolve_resolution("unknown_res")
        assert (h, w) == synth.RESOLUTION_PRESETS["992x512"]

    def test_resolve_auto_calls_auto_select(self):
        with mock.patch.object(synth, "auto_select_resolution", return_value=(512, 992)) as m:
            h, w = synth.resolve_resolution("auto")
            m.assert_called_once()
            assert (h, w) == (512, 992)


# ======================================================================
# Engine lifecycle
# ======================================================================

class TestCleanup:
    """Test engine cleanup resets module-level state."""

    def test_cleanup_resets_engine_to_none(self):
        # Set up mock engine
        synth._engine = mock.MagicMock()
        synth._engine_ckpt_dir = "/fake/dir"

        synth.cleanup()

        assert synth._engine is None
        assert synth._engine_ckpt_dir is None

    def test_cleanup_noop_when_no_engine(self):
        synth._engine = None
        synth._engine_ckpt_dir = None
        # Should not raise
        synth.cleanup()
        assert synth._engine is None


# ======================================================================
# Audio / image conversion helpers
# ======================================================================

class TestAudioConversion:
    """Test ComfyUI AUDIO dict → WAV conversion."""

    def test_audio_dict_to_wav_mono(self, tmp_path):
        wav_path = str(tmp_path / "test.wav")
        audio_dict = {
            "waveform": torch.randn(1, 1, 16000),  # 1 second mono
            "sample_rate": 16000,
        }
        result = synth._audio_dict_to_wav(audio_dict, wav_path)
        assert result == wav_path
        assert os.path.isfile(wav_path)
        assert os.path.getsize(wav_path) > 0

    def test_audio_dict_to_wav_stereo(self, tmp_path):
        wav_path = str(tmp_path / "test_stereo.wav")
        audio_dict = {
            "waveform": torch.randn(1, 2, 16000),  # 1 second stereo
            "sample_rate": 16000,
        }
        result = synth._audio_dict_to_wav(audio_dict, wav_path)
        assert os.path.isfile(wav_path)


class TestImageConversion:
    """Test ComfyUI IMAGE tensor → PNG conversion."""

    def test_tensor_to_image(self, tmp_path):
        png_path = str(tmp_path / "test.png")
        # ComfyUI IMAGE: [H, W, C] in [0, 1]
        tensor = torch.rand(64, 64, 3)
        result = synth._tensor_to_image(tensor, png_path)
        assert result == png_path
        assert os.path.isfile(png_path)
        assert os.path.getsize(png_path) > 0


# ======================================================================
# Model directory helpers
# ======================================================================

class TestModelDirectory:
    """Test model directory resolution."""

    def test_get_model_dir_uses_folder_paths(self):
        # folder_paths.models_dir is set to /tmp/comfyui_test_models
        result = synth._get_model_dir()
        assert "dreamid_omni" in result

    def test_get_model_dir_without_folder_paths(self):
        saved = sys.modules.get("folder_paths")
        try:
            sys.modules["folder_paths"] = types.ModuleType("folder_paths")
            # No models_dir attr → should fall back to ~/.cache
            importlib.reload(synth)
            result = synth._get_model_dir()
            assert "dreamid_omni" in result
        finally:
            if saved:
                sys.modules["folder_paths"] = saved
            importlib.reload(synth)


# ======================================================================
# generate_video validation
# ======================================================================

class TestGenerateVideoValidation:
    """Test input validation in generate_video."""

    def test_no_face_images_raises(self):
        with pytest.raises(ValueError, match="face reference image"):
            synth.generate_video(
                prompt="test",
                face_image_paths=None,
                audio_paths=["/fake/audio.wav"],
            )

    def test_empty_face_images_raises(self):
        with pytest.raises(ValueError, match="face reference image"):
            synth.generate_video(
                prompt="test",
                face_image_paths=[],
                audio_paths=["/fake/audio.wav"],
            )

    def test_no_audio_raises(self):
        with pytest.raises(ValueError, match="audio reference"):
            synth.generate_video(
                prompt="test",
                face_image_paths=["/fake/face.png"],
                audio_paths=None,
            )

    def test_empty_audio_raises(self):
        with pytest.raises(ValueError, match="audio reference"):
            synth.generate_video(
                prompt="test",
                face_image_paths=["/fake/face.png"],
                audio_paths=[],
            )


# ======================================================================
# VRAM utils registration
# ======================================================================

class TestVRAMRegistration:
    """Test that dreamid_omni_synthesizer is registered in VRAM utils."""

    def test_in_all_synthesizer_modules(self):
        from core._vram_utils import ALL_SYNTHESIZER_MODULES
        assert "dreamid_omni_synthesizer" in ALL_SYNTHESIZER_MODULES


# ======================================================================
# Model manager registration
# ======================================================================

class TestModelManagerRegistration:
    """Test _MODEL_INFO entries for DreamID-Omni."""

    def test_dreamid_omni_in_model_info(self):
        from core.model_manager import _MODEL_INFO
        assert "dreamid_omni" in _MODEL_INFO

    def test_dreamid_omni_wan_in_model_info(self):
        from core.model_manager import _MODEL_INFO
        assert "dreamid_omni_wan" in _MODEL_INFO

    def test_dreamid_omni_mmaudio_in_model_info(self):
        from core.model_manager import _MODEL_INFO
        assert "dreamid_omni_mmaudio" in _MODEL_INFO

    def test_model_info_has_required_fields(self):
        from core.model_manager import _MODEL_INFO
        for key in ("dreamid_omni", "dreamid_omni_wan", "dreamid_omni_mmaudio"):
            info = _MODEL_INFO[key]
            assert "name" in info, f"{key} missing 'name'"
            assert "size" in info, f"{key} missing 'size'"
            assert "url" in info, f"{key} missing 'url'"
            assert "license" in info, f"{key} missing 'license'"
            assert "manual" in info, f"{key} missing 'manual'"


# ======================================================================
# Agent node INPUT_TYPES
# ======================================================================

class TestAgentNodeInputTypes:
    """Test DreamID-Omni wiring in the FFMPEG Agent node."""

    @pytest.fixture(autouse=True)
    def _import_node(self):
        """Import agent_node, mocking heavy dependencies."""
        try:
            from nodes.agent_node import FFMPEGAgentNode
            self.node_cls = FFMPEGAgentNode
        except Exception:
            pytest.skip("agent_node could not be imported (missing deps)")

    def test_dreamid_omni_in_no_llm_mode(self):
        types = self.node_cls.INPUT_TYPES()
        no_llm_choices = types["required"]["no_llm_mode"][0]
        assert "dreamid_omni" in no_llm_choices

    def test_use_dreamid_omni_toggle_exists(self):
        types = self.node_cls.INPUT_TYPES()
        assert "use_dreamid_omni" in types["optional"]
        toggle = types["optional"]["use_dreamid_omni"]
        assert toggle[0] == "BOOLEAN"
        assert toggle[1]["default"] is False

    def test_dreamid_resolution_exists(self):
        types = self.node_cls.INPUT_TYPES()
        assert "dreamid_resolution" in types["optional"]
        choices = types["optional"]["dreamid_resolution"][0]
        assert "auto" in choices
        assert "992x512" in choices
        assert "1280x704" in choices

    def test_dreamid_steps_exists(self):
        types = self.node_cls.INPUT_TYPES()
        assert "dreamid_steps" in types["optional"]
        spec = types["optional"]["dreamid_steps"]
        assert spec[0] == "INT"
        assert spec[1]["default"] == 50

    def test_dreamid_seed_exists(self):
        types = self.node_cls.INPUT_TYPES()
        assert "dreamid_seed" in types["optional"]
        spec = types["optional"]["dreamid_seed"]
        assert spec[0] == "INT"
        assert spec[1]["default"] == 100

    def test_dreamid_solver_exists(self):
        types = self.node_cls.INPUT_TYPES()
        assert "dreamid_solver" in types["optional"]
        choices = types["optional"]["dreamid_solver"][0]
        assert "unipc" in choices
        assert "euler" in choices
        assert "dpm++" in choices

    def test_dreamid_cfg_scales_exist(self):
        types = self.node_cls.INPUT_TYPES()
        for param in ("dreamid_video_cfg", "dreamid_video_ref_cfg",
                      "dreamid_audio_cfg", "dreamid_audio_ref_cfg"):
            assert param in types["optional"], f"{param} missing"
            assert types["optional"][param][0] == "FLOAT"


# ======================================================================
# No-LLM mode function
# ======================================================================

class TestNoLLMMode:
    """Test process_dreamid_omni_only is callable."""

    def test_function_exists(self):
        from nodes.nollm_modes import process_dreamid_omni_only
        assert callable(process_dreamid_omni_only)

    def test_function_is_async(self):
        import asyncio
        from nodes.nollm_modes import process_dreamid_omni_only
        assert asyncio.iscoroutinefunction(process_dreamid_omni_only)


# ======================================================================
# Composer metadata propagation
# ======================================================================

class TestComposerPropagation:
    """Test that _enable_dreamid_omni is propagated through the composer."""

    def test_enable_flag_propagated(self):
        """Verify composer.py propagates _enable_dreamid_omni from metadata to step params."""
        import ast
        composer_path = os.path.join(_PROJECT_ROOT, "skills", "composer.py")
        with open(composer_path, "r") as f:
            source = f.read()
        assert "_enable_dreamid_omni" in source, \
            "composer.py should propagate _enable_dreamid_omni metadata"


# ======================================================================
# Visual handler flag
# ======================================================================

class TestVisualHandler:
    """Test that _enable_dreamid_omni is read in the visual handler."""

    def test_flag_read_in_visual(self):
        visual_path = os.path.join(_PROJECT_ROOT, "skills", "handlers", "visual.py")
        with open(visual_path, "r") as f:
            source = f.read()
        assert "_enable_dreamid_omni" in source, \
            "visual.py should read _enable_dreamid_omni flag"


# ======================================================================
# Vendored package structure
# ======================================================================

class TestVendoredPackage:
    """Test the vendored dreamid_omni package structure."""

    _vendor_dir = os.path.join(_PROJECT_ROOT, "core", "dreamid_omni")

    def test_init_exists(self):
        assert os.path.isfile(os.path.join(self._vendor_dir, "__init__.py"))

    def test_engine_exists(self):
        assert os.path.isfile(os.path.join(self._vendor_dir, "dreamid_omni_engine.py"))

    def test_configs_exist(self):
        yaml_path = os.path.join(self._vendor_dir, "configs", "inference", "inference_r2av.yaml")
        assert os.path.isfile(yaml_path), f"Missing config: {yaml_path}"

    def test_dit_configs_exist(self):
        for name in ("video.json", "audio.json"):
            path = os.path.join(self._vendor_dir, "configs", "model", "dit", name)
            assert os.path.isfile(path), f"Missing DIT config: {path}"

    def test_attention_module_exists(self):
        assert os.path.isfile(os.path.join(self._vendor_dir, "modules", "attention.py"))

    def test_no_absolute_imports(self):
        """Ensure no files still use absolute 'from dreamid_omni.' imports."""
        import subprocess
        result = subprocess.run(
            ["grep", "-rn", "from dreamid_omni\\.", self._vendor_dir,
             "--include=*.py"],
            capture_output=True, text=True
        )
        matches = result.stdout.strip()
        assert not matches, (
            f"Found absolute imports that should be relative:\n{matches}"
        )

    def test_attention_has_sdpa_fallback(self):
        """Verify attention.py has an SDPA fallback path."""
        attn_path = os.path.join(self._vendor_dir, "modules", "attention.py")
        with open(attn_path, "r") as f:
            source = f.read()
        assert "scaled_dot_product_attention" in source, \
            "attention.py should have SDPA fallback"

    def test_engine_uses_pathlib(self):
        """Verify engine resolves config via Path(__file__), not CWD."""
        engine_path = os.path.join(self._vendor_dir, "dreamid_omni_engine.py")
        with open(engine_path, "r") as f:
            source = f.read()
        assert "_PACKAGE_DIR" in source, \
            "Engine should use _PACKAGE_DIR for config resolution"
        assert "Path(__file__)" in source
