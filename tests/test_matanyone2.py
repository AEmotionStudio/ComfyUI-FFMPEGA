"""Tests for the video_matting no-LLM mode (MatAnyone2 integration).

Tests follow the same patterns as test_rembg.py:
  - Verify dropdown/widget registration
  - Verify handler exists and is callable
  - Verify VRAM cleanup registration
  - Verify synthesizer module structure
"""

from __future__ import annotations

import importlib
import sys
import unittest


class TestVideoMattingNoLLMMode(unittest.TestCase):
    """Check that video_matting is wired into the agent node correctly."""

    def test_video_matting_in_no_llm_dropdown(self):
        """'video_matting' should appear in the no_llm_mode dropdown choices."""
        from nodes.agent_node import FFMPEGAgentNode

        types = FFMPEGAgentNode.INPUT_TYPES()
        choices = types["required"]["no_llm_mode"][0]
        self.assertIn("video_matting", choices)

    def test_matting_output_dropdown_exists(self):
        """The matting_output dropdown should be in optional inputs."""
        from nodes.agent_node import FFMPEGAgentNode

        types = FFMPEGAgentNode.INPUT_TYPES()
        optional = types.get("optional", {})
        self.assertIn("matting_output", optional)
        choices = optional["matting_output"][0]
        self.assertIn("foreground", choices)
        self.assertIn("alpha", choices)
        self.assertIn("both", choices)
        self.assertIn("green_screen", choices)

    def test_matting_background_dropdown_exists(self):
        """The matting_background dropdown should be in optional inputs."""
        from nodes.agent_node import FFMPEGAgentNode

        types = FFMPEGAgentNode.INPUT_TYPES()
        optional = types.get("optional", {})
        self.assertIn("matting_background", optional)
        choices = optional["matting_background"][0]
        self.assertIn("green", choices)
        self.assertIn("black", choices)
        self.assertIn("white", choices)
        self.assertIn("blue", choices)

    def test_matting_max_size_input_exists(self):
        """The matting_max_size INT input should be in optional inputs."""
        from nodes.agent_node import FFMPEGAgentNode

        types = FFMPEGAgentNode.INPUT_TYPES()
        optional = types.get("optional", {})
        self.assertIn("matting_max_size", optional)
        spec = optional["matting_max_size"]
        self.assertEqual(spec[0], "INT")
        self.assertEqual(spec[1]["default"], 0)

    def test_process_video_matting_only_handler_exists(self):
        """The nollm_modes module should have a process_video_matting_only callable."""
        from nodes import nollm_modes

        self.assertTrue(
            hasattr(nollm_modes, "process_video_matting_only"),
            "nollm_modes.process_video_matting_only should exist",
        )
        self.assertTrue(
            callable(nollm_modes.process_video_matting_only),
            "nollm_modes.process_video_matting_only should be callable",
        )

    def test_agent_node_has_wrapper_method(self):
        """FFMPEGAgentNode should have _process_video_matting_only method."""
        from nodes.agent_node import FFMPEGAgentNode

        self.assertTrue(
            hasattr(FFMPEGAgentNode, "_process_video_matting_only"),
            "FFMPEGAgentNode._process_video_matting_only should exist",
        )


class TestMatAnyone2VRAMRegistration(unittest.TestCase):
    """Verify VRAM utils knows about the matanyone2 synthesizer."""

    def test_synthesizer_registered_in_vram_utils(self):
        """matanyone2_synthesizer should be in ALL_SYNTHESIZER_MODULES."""
        from core._vram_utils import ALL_SYNTHESIZER_MODULES

        self.assertIn(
            "matanyone2_synthesizer",
            ALL_SYNTHESIZER_MODULES,
            "matanyone2_synthesizer must be in ALL_SYNTHESIZER_MODULES",
        )


class TestMatAnyone2SynthesizerModule(unittest.TestCase):
    """Verify the synthesizer module has the expected public API."""

    def test_module_importable(self):
        """core.matanyone2_synthesizer should be importable."""
        try:
            mod = importlib.import_module("core.matanyone2_synthesizer")
            self.assertIsNotNone(mod)
        except ImportError as e:
            self.fail(f"Failed to import core.matanyone2_synthesizer: {e}")

    def test_public_api(self):
        """The synthesizer should expose process_video, load_model, cleanup."""
        mod = importlib.import_module("core.matanyone2_synthesizer")
        for fn_name in ("process_video", "load_model", "cleanup"):
            self.assertTrue(
                hasattr(mod, fn_name),
                f"core.matanyone2_synthesizer.{fn_name} should exist",
            )
            self.assertTrue(
                callable(getattr(mod, fn_name)),
                f"core.matanyone2_synthesizer.{fn_name} should be callable",
            )

    def test_bg_colors(self):
        """The _BG_COLORS dict should have the expected colors."""
        mod = importlib.import_module("core.matanyone2_synthesizer")
        for color in ("green", "black", "white", "blue"):
            bg = mod._get_bg_color(color)
            self.assertEqual(bg.shape, (1, 1, 3), f"Background color '{color}' should be (1,1,3)")

    def test_unknown_bg_defaults_to_green(self):
        """Unknown background color names should default to green."""
        mod = importlib.import_module("core.matanyone2_synthesizer")
        import numpy as np

        green = mod._get_bg_color("green")
        unknown = mod._get_bg_color("purple_polka_dot")
        np.testing.assert_array_equal(green, unknown)


class TestVendoredPackage(unittest.TestCase):
    """Verify the vendored matanyone2 package structure."""

    def test_config_yaml_exists(self):
        """The vendored config YAML files should exist."""
        from pathlib import Path

        base = Path(__file__).resolve().parent.parent / "core" / "matanyone2" / "config"
        self.assertTrue(
            (base / "eval_matanyone_config.yaml").exists(),
            "eval_matanyone_config.yaml should exist",
        )
        self.assertTrue(
            (base / "model" / "base.yaml").exists(),
            "model/base.yaml should exist",
        )

    def test_no_hydra_imports(self):
        """The vendored package should not import hydra anywhere."""
        from pathlib import Path

        base = Path(__file__).resolve().parent.parent / "core" / "matanyone2"
        for py_file in base.rglob("*.py"):
            content = py_file.read_text()
            self.assertNotIn(
                "from hydra",
                content,
                f"{py_file.relative_to(base)} still imports hydra",
            )
            self.assertNotIn(
                "import hydra",
                content,
                f"{py_file.relative_to(base)} still imports hydra",
            )


if __name__ == "__main__":
    unittest.main()
