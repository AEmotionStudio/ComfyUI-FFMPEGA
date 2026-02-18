"""Tests for skill combinations and extracted orchestration helpers.

Part 1: Parametrized integration tests for known-fragile multi-skill pipelines.
Part 2: Unit tests for the 5 extracted orchestration methods in SkillComposer.
"""

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from skills.composer import SkillComposer, Pipeline


# ══════════════════════════════════════════════════════════════════════ #
#  Part 1: Skill combination integration tests                         #
# ══════════════════════════════════════════════════════════════════════ #


class TestSingleSkillBaselines:
    """Verify that individual skills produce valid commands on their own."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        self.composer = SkillComposer()

    def _cmd(self, skill_name, params=None, extra_inputs=None, metadata=None):
        pipeline = Pipeline(
            input_path="/in.mp4",
            output_path="/out.mp4",
            extra_inputs=extra_inputs or [],
        )
        if metadata:
            pipeline.metadata.update(metadata)
        pipeline.add_step(skill_name, params or {})
        cmd = self.composer.compose(pipeline)
        return cmd.to_string()

    def test_resize(self):
        cmd = self._cmd("resize", {"width": 1280, "height": 720})
        assert "scale=" in cmd

    def test_brightness(self):
        cmd = self._cmd("brightness", {"value": 0.1})
        assert "eq=" in cmd

    def test_volume(self):
        cmd = self._cmd("volume", {"level": 2.0})
        assert "volume=" in cmd

    def test_concat_audio(self):
        cmd = self._cmd(
            "concat", {},
            extra_inputs=["/b.mp4"],
            metadata={"_has_embedded_audio": True},
        )
        assert "concat=" in cmd
        assert "a=1" in cmd

    def test_xfade(self):
        cmd = self._cmd(
            "xfade", {"transition": "fade"},
            extra_inputs=["/b.mp4"],
            metadata={"_has_embedded_audio": True},
        )
        assert "xfade" in cmd


class TestAudioVideoCombinations:
    """Test combinations of audio + video skills in a single pipeline."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        self.composer = SkillComposer()

    def _cmd(self, steps, extra_inputs=None, metadata=None):
        pipeline = Pipeline(
            input_path="/in.mp4",
            output_path="/out.mp4",
            extra_inputs=extra_inputs or [],
        )
        if metadata:
            pipeline.metadata.update(metadata)
        for name, params in steps:
            pipeline.add_step(name, params)
        cmd = self.composer.compose(pipeline)
        return cmd.to_string()

    def test_brightness_plus_volume(self):
        """brightness (video) + volume (audio) should produce both -vf and -af."""
        cmd = self._cmd([
            ("brightness", {"value": 0.1}),
            ("volume", {"level": 1.5}),
        ])
        assert "eq=" in cmd
        assert "volume=" in cmd

    def test_resize_plus_normalize(self):
        """resize + normalize should coexist."""
        cmd = self._cmd([
            ("resize", {"width": 1920, "height": 1080}),
            ("normalize", {}),
        ])
        assert "scale=" in cmd
        assert "loudnorm" in cmd

    def test_speed_plus_volume(self):
        """Speed change + volume should both apply."""
        cmd = self._cmd([
            ("speed", {"factor": 2.0}),
            ("volume", {"level": 0.5}),
        ])
        assert "setpts=" in cmd
        assert "volume=" in cmd


class TestMultiStreamCombinations:
    """Test multi-stream skills combined with simple skills."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        self.composer = SkillComposer()

    def _cmd(self, steps, extra_inputs=None, metadata=None):
        pipeline = Pipeline(
            input_path="/in.mp4",
            output_path="/out.mp4",
            extra_inputs=extra_inputs or [],
        )
        if metadata:
            pipeline.metadata.update(metadata)
        for name, params in steps:
            pipeline.add_step(name, params)
        cmd = self.composer.compose(pipeline)
        return cmd.to_string()

    def test_concat_plus_volume(self):
        """concat + volume: audio filters should be folded into filter_complex."""
        cmd = self._cmd(
            [("concat", {}), ("volume", {"level": 2.0})],
            extra_inputs=["/b.mp4"],
            metadata={"_has_embedded_audio": True},
        )
        assert "concat=" in cmd
        assert "volume=" in cmd
        # -af should NOT be present when filter_complex handles audio
        assert " -af " not in cmd

    def test_concat_plus_fade(self):
        """concat + fade: fade should apply post-concat, not to first clip."""
        cmd = self._cmd(
            [("concat", {}), ("fade", {"type": "out", "duration": 2})],
            extra_inputs=["/b.mp4"],
            metadata={"_has_embedded_audio": True},
        )
        assert "concat=" in cmd
        assert "fade=" in cmd
        assert "filter_complex" in cmd

    def test_xfade_plus_fade(self):
        """xfade + fade: both should coexist in filter_complex."""
        cmd = self._cmd(
            [
                ("xfade", {"transition": "fade", "duration": 1}),
                ("fade", {"type": "out", "duration": 2}),
            ],
            extra_inputs=["/b.mp4"],
            metadata={"_has_embedded_audio": True},
        )
        assert "xfade" in cmd
        assert "fade=" in cmd

    def test_xfade_plus_volume(self):
        """xfade + volume: volume should be folded into filter_complex audio."""
        cmd = self._cmd(
            [
                ("xfade", {"transition": "dissolve", "duration": 1}),
                ("volume", {"level": 0.5}),
            ],
            extra_inputs=["/b.mp4"],
            metadata={"_has_embedded_audio": True},
        )
        assert "xfade" in cmd
        assert "volume=" in cmd
        assert " -af " not in cmd


class TestConflictResolution:
    """Test scenarios with conflicting skills."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        self.composer = SkillComposer()

    def _cmd(self, steps, extra_inputs=None, metadata=None):
        pipeline = Pipeline(
            input_path="/in.mp4",
            output_path="/out.mp4",
            extra_inputs=extra_inputs or [],
        )
        if metadata:
            pipeline.metadata.update(metadata)
        for name, params in steps:
            pipeline.add_step(name, params)
        cmd = self.composer.compose(pipeline)
        return cmd.to_string()

    def test_remove_audio_plus_volume(self):
        """remove_audio + volume: -an wins, volume should be dropped."""
        cmd = self._cmd([
            ("remove_audio", {}),
            ("volume", {"level": 2.0}),
        ])
        assert "-an" in cmd
        # Volume filter should NOT be present
        assert "volume=" not in cmd

    def test_jump_cut_plus_volume(self):
        """jump_cut + volume: jump_cut's defensive -an should be dropped."""
        cmd = self._cmd([
            ("jump_cut", {"threshold": 0.4}),
            ("volume", {"level": 2.0}),
        ])
        assert "volume=" in cmd
        # Should NOT have -an since volume is explicit audio intent
        assert "-an" not in cmd

    def test_duplicate_quality_settings(self):
        """Two quality skills should deduplicate (last-writer-wins)."""
        cmd = self._cmd([
            ("quality", {"crf": 18, "preset": "slow"}),
            ("quality", {"crf": 23, "preset": "fast"}),
        ])
        # Last CRF should win
        assert "-crf" in cmd
        parts = cmd.split()
        crf_indices = [i for i, p in enumerate(parts) if p == "-crf"]
        # Should only appear once (dedup)
        assert len(crf_indices) == 1
        assert parts[crf_indices[0] + 1] == "23"


# ══════════════════════════════════════════════════════════════════════ #
#  Part 2: Unit tests for extracted orchestration helpers               #
# ══════════════════════════════════════════════════════════════════════ #


class TestResolveAudioConflicts:
    """Unit tests for SkillComposer._resolve_audio_conflicts."""

    def test_no_an_flag_passthrough(self):
        """When -an is not present, return inputs unchanged."""
        opts, af = SkillComposer._resolve_audio_conflicts(
            ["-c:v", "libx264"], ["volume=2"], {"resize"},
        )
        assert opts == ["-c:v", "libx264"]
        assert af == ["volume=2"]

    def test_remove_audio_clears_filters(self):
        """-an + remove_audio: keep -an, clear audio filters."""
        opts, af = SkillComposer._resolve_audio_conflicts(
            ["-an", "-c:v", "libx264"], ["volume=2"], {"remove_audio"},
        )
        assert "-an" in opts
        assert af == []

    def test_defensive_an_dropped_when_audio_filters(self):
        """-an from beat_sync + audio filters: drop -an."""
        opts, af = SkillComposer._resolve_audio_conflicts(
            ["-an", "-c:v", "libx264"], ["volume=2"], {"beat_sync"},
        )
        assert "-an" not in opts
        assert af == ["volume=2"]

    def test_an_no_audio_filters_strips_audio(self):
        """-an with no audio filters: keep -an, clear filters."""
        opts, af = SkillComposer._resolve_audio_conflicts(
            ["-an"], [], {"beat_sync"},
        )
        assert "-an" in opts
        assert af == []


class TestDedupOutputOptions:
    """Unit tests for SkillComposer._dedup_output_options."""

    def test_no_duplicates(self):
        result = SkillComposer._dedup_output_options(
            ["-c:v", "libx264", "-crf", "23"]
        )
        assert result == ["-c:v", "libx264", "-crf", "23"]

    def test_last_writer_wins(self):
        result = SkillComposer._dedup_output_options(
            ["-crf", "18", "-c:v", "libx264", "-crf", "23"]
        )
        # -crf should appear once with value "23"
        assert result.count("-crf") == 1
        idx = result.index("-crf")
        assert result[idx + 1] == "23"

    def test_map_allows_duplicates(self):
        result = SkillComposer._dedup_output_options(
            ["-map", "[_vout]", "-map", "[_aout]"]
        )
        assert result.count("-map") == 2

    def test_standalone_flags(self):
        result = SkillComposer._dedup_output_options(
            ["-an", "-y", "-an"]
        )
        assert result.count("-an") == 1


class TestChainFilterComplex:
    """Unit tests for SkillComposer._chain_filter_complex."""

    def test_single_block_no_audio(self):
        fc, label, opts = SkillComposer._chain_filter_complex(
            ["[0:v][1:v]overlay=0:0"], [], False,
        )
        assert fc == "[0:v][1:v]overlay=0:0"
        assert label is None

    def test_single_block_with_audio(self):
        fc, label, opts = SkillComposer._chain_filter_complex(
            ["[0:v][1:v]concat=n=2:v=1:a=1[_vout][_aout]"], [], True,
        )
        assert label == "[_aout]"

    def test_two_blocks_chained(self):
        fc, label, opts = SkillComposer._chain_filter_complex(
            [
                "[0:v][1:v]concat=n=2:v=1:a=0",
                "[0:v][2:v]overlay=W-w:H-h",
            ],
            [], False,
        )
        # First block should get pipe label, second should consume it
        assert "[_pipe_0]" in fc
        assert "[_pipe_0]" in fc.split(";")[1]  # consumed in block 2


class TestFoldAudioIntoFc:
    """Unit tests for SkillComposer._fold_audio_into_fc."""

    def test_folds_audio_filters(self):
        fc, af, opts = SkillComposer._fold_audio_into_fc(
            "[stuff][_vfinal]",
            ["volume=2"],
            [],
            "[_aout_pre]",
        )
        assert "volume=2" in fc
        assert af == []
        assert "-map" in opts

    def test_no_audio_label_passthrough(self):
        fc, af, opts = SkillComposer._fold_audio_into_fc(
            "[0:v]scale=1280:720",
            ["volume=2"],
            [],
            None,
        )
        assert af == ["volume=2"]
        assert fc == "[0:v]scale=1280:720"

    def test_vout_gets_mapped(self):
        fc, af, opts = SkillComposer._fold_audio_into_fc(
            "stuff[_vout]",
            [],
            [],
            None,
        )
        assert "-map" in opts
        assert "[_vout]" in opts

    def test_vfinal_with_audio_label_no_filters(self):
        fc, af, opts = SkillComposer._fold_audio_into_fc(
            "stuff[_vfinal]",
            [],
            [],
            "[_aout_pre]",
        )
        assert "-map" in opts
        assert "[_vfinal]" in opts
        assert "[_aout_pre]" in opts


class TestResolveOverlayInputs:
    """Unit tests for SkillComposer._resolve_overlay_inputs."""

    def test_non_concat_returns_empty(self):
        pipeline = Pipeline(input_path="/in.mp4", output_path="/out.mp4")
        result = SkillComposer._resolve_overlay_inputs(
            pipeline, "resize", [], 1, {},
        )
        assert result == set()

    def test_concat_with_image_paths_excludes(self):
        pipeline = Pipeline(
            input_path="/in.mp4",
            output_path="/out.mp4",
            extra_inputs=["/b.mp4"],
        )
        pipeline.add_step("overlay_image", {"image_source": "image_a"})
        result = SkillComposer._resolve_overlay_inputs(
            pipeline, "concat", ["/logo.png"], 2, {},
        )
        assert 2 in result  # image_a at _image_input_start

    def test_concat_no_images_returns_empty(self):
        pipeline = Pipeline(
            input_path="/in.mp4",
            output_path="/out.mp4",
            extra_inputs=["/b.mp4"],
        )
        result = SkillComposer._resolve_overlay_inputs(
            pipeline, "concat", [], 1, {},
        )
        assert result == set()
