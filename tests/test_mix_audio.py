"""Tests for mix_audio skill and PiP audio_mix parameter."""

import sys
import os
import pytest

# Ensure the project root is on sys.path
_project_root = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..")
)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from skills.handlers.audio import _f_mix_audio
from skills.handlers.multi_input import _f_pip
from skills.registry import get_registry


# ── _f_mix_audio handler tests ──────────────────────────────────── #

class TestMixAudioHandler:
    """Tests for the standalone _f_mix_audio handler."""

    def test_default_params(self):
        """Default call should use amix with duration=longest."""
        vf, af, opts, fc = _f_mix_audio({})
        assert vf == []
        assert af == []
        assert opts == []
        assert "[0:a][1:a]amix=inputs=2" in fc
        assert "duration=longest" in fc
        assert "dropout_transition=2" in fc
        assert "weights=1 1" in fc

    def test_duration_shortest(self):
        """Should respect duration=shortest."""
        _, _, _, fc = _f_mix_audio({"duration": "shortest"})
        assert "duration=shortest" in fc

    def test_duration_first(self):
        """Should respect duration=first."""
        _, _, _, fc = _f_mix_audio({"duration": "first"})
        assert "duration=first" in fc

    def test_invalid_duration_defaults_to_longest(self):
        """Invalid duration should fall back to longest."""
        _, _, _, fc = _f_mix_audio({"duration": "invalid"})
        assert "duration=longest" in fc

    def test_custom_weights(self):
        """Should use custom weights for volume balance."""
        _, _, _, fc = _f_mix_audio({"weights": "1 0.3"})
        assert "weights=1 0.3" in fc

    def test_custom_dropout(self):
        """Should use custom dropout_transition."""
        _, _, _, fc = _f_mix_audio({"dropout_transition": 5})
        assert "dropout_transition=5" in fc


# ── PiP audio_mix tests ─────────────────────────────────────────── #

class TestPipAudioMix:
    """Tests for PiP audio_mix parameter support."""

    def test_pip_default_no_audio(self):
        """Default PiP should NOT include amix."""
        _, _, opts, fc = _f_pip({"scale": 0.25})
        assert "amix" not in fc
        assert "-map" not in opts

    def test_pip_audio_mix_false(self):
        """audio_mix=False should NOT include amix."""
        _, _, opts, fc = _f_pip({"scale": 0.25, "audio_mix": False})
        assert "amix" not in fc

    def test_pip_audio_mix_true(self):
        """audio_mix=True should append amix filter and -map."""
        _, _, opts, fc = _f_pip({"scale": 0.25, "audio_mix": True})
        assert "[0:a][1:a]amix=inputs=2" in fc
        assert "duration=longest" in fc
        assert "[_aout]" in fc
        assert "-map" in opts
        assert "[_aout]" in opts

    def test_pip_audio_mix_string_true(self):
        """audio_mix='true' (string) should work like True."""
        _, _, opts, fc = _f_pip({"audio_mix": "true"})
        assert "amix" in fc
        assert "-map" in opts

    def test_pip_audio_mix_string_yes(self):
        """audio_mix='yes' (string) should work like True."""
        _, _, opts, fc = _f_pip({"audio_mix": "yes"})
        assert "amix" in fc

    def test_pip_video_overlay_still_present_with_audio(self):
        """Video overlay should still be generated when audio_mix is True."""
        _, _, _, fc = _f_pip({
            "position": "top_left",
            "scale": 0.3,
            "audio_mix": True,
        })
        assert "overlay=" in fc
        assert "[0:v][pip]overlay=" in fc

    def test_pip_border_with_audio(self):
        """Border + audio_mix should produce both pad and amix."""
        _, _, opts, fc = _f_pip({
            "border": 5,
            "border_color": "white",
            "audio_mix": True,
        })
        assert "pad=" in fc
        assert "amix" in fc
        assert "-map" in opts


# ── Skill registration tests ──────────────────────────────────── #

class TestMixAudioSkillRegistration:
    """Tests for the mix_audio skill registration."""

    def test_mix_audio_in_registry(self):
        """mix_audio should be registered in the skill registry."""
        registry = get_registry()
        skill = registry.get("mix_audio")
        assert skill is not None
        assert skill.name == "mix_audio"

    def test_mix_audio_has_duration_param(self):
        """mix_audio should have a duration parameter."""
        registry = get_registry()
        skill = registry.get("mix_audio")
        param_names = [p.name for p in skill.parameters]
        assert "duration" in param_names

    def test_mix_audio_has_weights_param(self):
        """mix_audio should have a weights parameter."""
        registry = get_registry()
        skill = registry.get("mix_audio")
        param_names = [p.name for p in skill.parameters]
        assert "weights" in param_names

    def test_pip_has_audio_mix_param(self):
        """picture_in_picture should have an audio_mix parameter."""
        registry = get_registry()
        skill = registry.get("picture_in_picture")
        param_names = [p.name for p in skill.parameters]
        assert "audio_mix" in param_names

    def test_mix_audio_tags(self):
        """mix_audio should have relevant tags for LLM discovery."""
        registry = get_registry()
        skill = registry.get("mix_audio")
        assert "mix" in skill.tags
        assert "amix" in skill.tags
        assert "audio" in skill.tags
"""
TargetFile: /home/tealdisk/ComfyUI/custom_nodes/ComfyUI-FFMPEGA/tests/test_mix_audio.py
Overwrite: False
EmptyFile: false
Description: Unit tests for the mix_audio handler, PiP audio_mix parameter, and skill registration.
Complexity: 5
IsArtifact: false
"""
