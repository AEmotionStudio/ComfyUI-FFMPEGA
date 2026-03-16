"""Unit tests for the Kiwi-Edit synthesizer module.

Tests cover:
- Module constants (HF repos, mirror repos, model dir names)
- Resolution presets
- Auto-variant selection logic
- Enhanced prompt builder
- Pipeline cleanup
- Model manager integration
- No-LLM dropdown inclusion
"""

import pytest

import os

# PyTorch import can fail on Python 3.14 — guard torch-dependent tests
try:
    import torch  # noqa: F401
    _has_torch = True
except (ImportError, RuntimeError):
    _has_torch = False


# --- Constants Tests ----------------------------------------------------------

class TestKiwiEditConstants:
    """Test that module constants are correctly defined."""

    def test_hf_repos_all_variants(self):
        """_HF_REPOS should contain all three model variants."""
        from core.kiwi_edit_synthesizer import _HF_REPOS
        assert "instruct" in _HF_REPOS
        assert "reference" in _HF_REPOS
        assert "instruct_reference" in _HF_REPOS

    def test_hf_repos_point_to_linyq(self):
        """All HF repos should point to linyq/ namespace."""
        from core.kiwi_edit_synthesizer import _HF_REPOS
        for variant, repo in _HF_REPOS.items():
            assert repo.startswith("linyq/"), f"{variant}: {repo}"

    def test_mirror_repos_all_variants(self):
        """_MIRROR_REPOS should contain all three model variants."""
        from core.kiwi_edit_synthesizer import _MIRROR_REPOS
        assert "instruct" in _MIRROR_REPOS
        assert "reference" in _MIRROR_REPOS
        assert "instruct_reference" in _MIRROR_REPOS

    def test_mirror_repos_point_to_aemotion(self):
        """All mirror repos should point to AEmotionStudio/ namespace."""
        from core.kiwi_edit_synthesizer import _MIRROR_REPOS
        for variant, repo in _MIRROR_REPOS.items():
            assert repo.startswith("AEmotionStudio/"), f"{variant}: {repo}"

    def test_model_dir_names_all_variants(self):
        """_MODEL_DIR_NAMES should contain all three variants."""
        from core.kiwi_edit_synthesizer import _MODEL_DIR_NAMES
        assert "instruct" in _MODEL_DIR_NAMES
        assert "reference" in _MODEL_DIR_NAMES
        assert "instruct_reference" in _MODEL_DIR_NAMES

    def test_pipeline_defaults(self):
        """Pipeline defaults should be reasonable values."""
        from core.kiwi_edit_synthesizer import (
            _DEFAULT_STEPS, _DEFAULT_GUIDANCE, _DEFAULT_MAX_FRAMES, _DEFAULT_FPS,
        )
        assert _DEFAULT_STEPS == 30
        assert _DEFAULT_GUIDANCE == 5.0
        assert _DEFAULT_MAX_FRAMES == 81
        assert _DEFAULT_FPS == 15


# --- Resolution Preset Tests -------------------------------------------------

class TestResolutionPresets:
    """Test resolution preset mapping."""

    def test_all_presets_exist(self):
        """All expected resolution presets should be defined."""
        from core.kiwi_edit_synthesizer import RESOLUTION_PRESETS
        expected = {"auto", "480p", "512", "640", "720p", "custom"}
        assert set(RESOLUTION_PRESETS.keys()) == expected

    def test_480p_resolution(self):
        """480p should map to (480, 640)."""
        from core.kiwi_edit_synthesizer import RESOLUTION_PRESETS
        assert RESOLUTION_PRESETS["480p"] == (480, 640)

    def test_512_resolution(self):
        """512 should map to (512, 512)."""
        from core.kiwi_edit_synthesizer import RESOLUTION_PRESETS
        assert RESOLUTION_PRESETS["512"] == (512, 512)

    def test_640_resolution(self):
        """640 should map to (640, 640)."""
        from core.kiwi_edit_synthesizer import RESOLUTION_PRESETS
        assert RESOLUTION_PRESETS["640"] == (640, 640)

    def test_720p_resolution(self):
        """720p should map to (720, 1280)."""
        from core.kiwi_edit_synthesizer import RESOLUTION_PRESETS
        assert RESOLUTION_PRESETS["720p"] == (720, 1280)

    def test_auto_is_none(self):
        """auto should map to None (derive from input)."""
        from core.kiwi_edit_synthesizer import RESOLUTION_PRESETS
        assert RESOLUTION_PRESETS["auto"] is None

    def test_custom_is_none(self):
        """custom should map to None (use manual width/height)."""
        from core.kiwi_edit_synthesizer import RESOLUTION_PRESETS
        assert RESOLUTION_PRESETS["custom"] is None


# --- VRAM-Aware Auto Resolution Tests ----------------------------------------

class TestAutoDetectResolution:
    """Test VRAM-aware auto resolution selection."""

    def test_vram_tier_tables_exist(self):
        """Both BF16 and FP8 tier tables should be defined."""
        from core.kiwi_edit_synthesizer import (
            _VRAM_RESOLUTION_TIERS_BF16, _VRAM_RESOLUTION_TIERS_FP8,
        )
        assert len(_VRAM_RESOLUTION_TIERS_BF16) >= 4
        assert len(_VRAM_RESOLUTION_TIERS_FP8) >= 4

    def test_vram_tiers_are_sorted_descending(self):
        """Tier tables should be sorted by descending VRAM threshold."""
        from core.kiwi_edit_synthesizer import (
            _VRAM_RESOLUTION_TIERS_BF16, _VRAM_RESOLUTION_TIERS_FP8,
        )
        for tiers in (_VRAM_RESOLUTION_TIERS_BF16, _VRAM_RESOLUTION_TIERS_FP8):
            thresholds = [t[0] for t in tiers]
            assert thresholds == sorted(thresholds, reverse=True)

    def test_lowest_tier_is_zero(self):
        """The lowest tier threshold should be 0.0 GiB (catch-all)."""
        from core.kiwi_edit_synthesizer import (
            _VRAM_RESOLUTION_TIERS_BF16, _VRAM_RESOLUTION_TIERS_FP8,
        )
        assert _VRAM_RESOLUTION_TIERS_BF16[-1][0] == 0.0
        assert _VRAM_RESOLUTION_TIERS_FP8[-1][0] == 0.0

    def test_fp8_thresholds_are_lower(self):
        """FP8 tiers should have equal or lower VRAM thresholds than BF16."""
        from core.kiwi_edit_synthesizer import (
            _VRAM_RESOLUTION_TIERS_BF16, _VRAM_RESOLUTION_TIERS_FP8,
        )
        for bf16_tier, fp8_tier in zip(
            _VRAM_RESOLUTION_TIERS_BF16, _VRAM_RESOLUTION_TIERS_FP8
        ):
            assert fp8_tier[0] <= bf16_tier[0], (
                f"FP8 threshold {fp8_tier[0]} > BF16 threshold {bf16_tier[0]}"
            )

    def test_block_swap_savings_constant(self):
        """Block swap VRAM savings constant should be reasonable."""
        from core.kiwi_edit_synthesizer import _BLOCK_SWAP_VRAM_SAVINGS_MB
        assert 100 <= _BLOCK_SWAP_VRAM_SAVINGS_MB <= 500

    def test_auto_detect_callable(self):
        """_auto_detect_resolution should be callable."""
        from core.kiwi_edit_synthesizer import _auto_detect_resolution
        assert callable(_auto_detect_resolution)

    def test_auto_detect_returns_tuple(self):
        """_auto_detect_resolution should return (preset_name, (h, w))."""
        from core.kiwi_edit_synthesizer import _auto_detect_resolution
        result = _auto_detect_resolution(precision="bf16")
        assert isinstance(result, tuple)
        assert len(result) == 2
        preset_name, resolution = result
        assert isinstance(preset_name, str)
        assert isinstance(resolution, tuple)
        assert len(resolution) == 2

    def test_resolve_resolution_accepts_precision(self):
        """_resolve_resolution should accept precision and block_swap_blocks."""
        from core.kiwi_edit_synthesizer import _resolve_resolution
        # Test with an explicit preset (should ignore VRAM)
        h, w = _resolve_resolution([], "640", precision="bf16", block_swap_blocks=0)
        assert (h, w) == (640, 640)

    def test_resolve_resolution_auto_returns_valid(self):
        """Auto preset should return a valid (h, w) tuple from VRAM detection."""
        from core.kiwi_edit_synthesizer import _resolve_resolution, RESOLUTION_PRESETS
        h, w = _resolve_resolution([], "auto", precision="bf16", block_swap_blocks=0)
        # Should be one of the known resolution sizes
        valid_sizes = {v for v in RESOLUTION_PRESETS.values() if v is not None}
        assert (h, w) in valid_sizes


# --- Auto-Variant Selection Tests ---------------------------------------------

class TestAutoVariantSelection:
    """Test that auto_select_variant picks the right model."""

    def test_prompt_only_selects_instruct(self):
        """Prompt without ref images should select instruct."""
        from core.kiwi_edit_synthesizer import auto_select_variant
        assert auto_select_variant("Remove the cat", None) == "instruct"

    def test_ref_only_selects_reference(self):
        """Ref images without prompt should select reference."""
        from core.kiwi_edit_synthesizer import auto_select_variant
        assert auto_select_variant(None, ["ref.jpg"]) == "reference"

    def test_both_selects_instruct_reference(self):
        """Prompt + ref images should select instruct_reference."""
        from core.kiwi_edit_synthesizer import auto_select_variant
        assert auto_select_variant("Replace sofa", ["ref.jpg"]) == "instruct_reference"

    def test_empty_prompt_with_ref_selects_reference(self):
        """Empty string prompt with ref images should select reference."""
        from core.kiwi_edit_synthesizer import auto_select_variant
        assert auto_select_variant("", ["ref.jpg"]) == "reference"

    def test_whitespace_prompt_selects_reference(self):
        """Whitespace-only prompt with ref images should select reference."""
        from core.kiwi_edit_synthesizer import auto_select_variant
        assert auto_select_variant("   ", ["ref.jpg"]) == "reference"

    def test_manual_override_respected(self):
        """Manual variant override should be respected."""
        from core.kiwi_edit_synthesizer import auto_select_variant
        result = auto_select_variant("test", ["ref.jpg"], "instruct")
        assert result == "instruct"

    def test_no_inputs_defaults_to_instruct(self):
        """No prompt and no ref images should default to instruct."""
        from core.kiwi_edit_synthesizer import auto_select_variant
        assert auto_select_variant(None, None) == "instruct"


# --- Enhanced Prompt Tests ----------------------------------------------------

class TestEnhancedPrompt:
    """Test automatic prompt enhancement for temporal stability."""

    def test_remove_prompt_enhanced(self):
        """Remove prompts should get local_remove enhancements."""
        from core.kiwi_edit_synthesizer import _enhance_prompt
        result = _enhance_prompt("Remove the monkey")
        assert len(result) > len("Remove the monkey")

    def test_add_prompt_enhanced(self):
        """Add prompts should get local_add enhancements."""
        from core.kiwi_edit_synthesizer import _enhance_prompt
        result = _enhance_prompt("Add a hat to the person")
        assert len(result) > len("Add a hat to the person")

    def test_background_prompt_enhanced(self):
        """Background prompts should get background_change enhancements."""
        from core.kiwi_edit_synthesizer import _enhance_prompt
        result = _enhance_prompt("Change the background to winter")
        assert len(result) > len("Change the background to winter")

    def test_style_prompt_enhanced(self):
        """Style prompts should get global_style enhancements."""
        from core.kiwi_edit_synthesizer import _enhance_prompt
        result = _enhance_prompt("Make it look like a painting")
        assert len(result) > len("Make it look like a painting")

    def test_generic_prompt_enhanced(self):
        """Generic prompts should get local_change enhancements."""
        from core.kiwi_edit_synthesizer import _enhance_prompt
        result = _enhance_prompt("Turn the shirt red")
        assert len(result) > len("Turn the shirt red")


# --- Cleanup Tests ------------------------------------------------------------

class TestKiwiEditCleanup:
    """Test pipeline cleanup."""

    @pytest.mark.skipif(not _has_torch, reason="PyTorch not available")
    def test_cleanup_resets_pipeline(self):
        """Cleanup should reset the cached pipeline to None."""
        import core.kiwi_edit_synthesizer as ke
        ke._pipeline = "fake"
        ke._pipeline_variant = "instruct"
        ke._pipeline_precision = "bf16"
        ke.cleanup()
        assert ke._pipeline is None
        assert ke._pipeline_variant == ""
        assert ke._pipeline_precision == ""


# --- Model Manager Integration ------------------------------------------------

class TestKiwiEditModelManager:
    """Test that Kiwi-Edit variants are registered in model_manager."""

    def test_instruct_in_model_info(self):
        """kiwi_edit_instruct should be in _MODEL_INFO."""
        from core.model_manager import _MODEL_INFO
        assert "kiwi_edit_instruct" in _MODEL_INFO

    def test_reference_in_model_info(self):
        """kiwi_edit_reference should be in _MODEL_INFO."""
        from core.model_manager import _MODEL_INFO
        assert "kiwi_edit_reference" in _MODEL_INFO

    def test_instruct_reference_in_model_info(self):
        """kiwi_edit_instruct_reference should be in _MODEL_INFO."""
        from core.model_manager import _MODEL_INFO
        assert "kiwi_edit_instruct_reference" in _MODEL_INFO



    def test_model_info_has_required_fields(self):
        """Each kiwi_edit entry should have all required fields."""
        from core.model_manager import _MODEL_INFO
        for key in ("kiwi_edit_instruct", "kiwi_edit_reference",
                     "kiwi_edit_instruct_reference"):
            info = _MODEL_INFO[key]
            assert "name" in info
            assert "size" in info
            assert "url" in info
            assert "mirror_repo" in info

    def test_mirror_repos_match(self):
        """Mirror repos in model_manager should match kiwi_edit_synthesizer."""
        from core.model_manager import _MODEL_INFO
        from core.kiwi_edit_synthesizer import _MIRROR_REPOS
        assert _MODEL_INFO["kiwi_edit_instruct"]["mirror_repo"] == _MIRROR_REPOS["instruct"]
        assert _MODEL_INFO["kiwi_edit_reference"]["mirror_repo"] == _MIRROR_REPOS["reference"]
        assert _MODEL_INFO["kiwi_edit_instruct_reference"]["mirror_repo"] == _MIRROR_REPOS["instruct_reference"]


    def test_license_is_mit(self):
        """All Kiwi-Edit models should be MIT licensed."""
        from core.model_manager import _MODEL_INFO
        for key in ("kiwi_edit_instruct", "kiwi_edit_reference",
                     "kiwi_edit_instruct_reference"):
            assert "MIT" in _MODEL_INFO[key].get("license", "")



# --- VRAM Utils Integration ---------------------------------------------------

class TestKiwiEditVRAMUtils:
    """Test that Kiwi-Edit is registered in the VRAM cleanup registry."""

    def test_in_synthesizer_modules(self):
        """kiwi_edit_synthesizer should be in ALL_SYNTHESIZER_MODULES."""
        from core._vram_utils import ALL_SYNTHESIZER_MODULES
        assert "kiwi_edit_synthesizer" in ALL_SYNTHESIZER_MODULES


# --- No-LLM Mode Tests -------------------------------------------------------

class TestKiwiEditNoLLMMode:
    """Test the kiwi_edit no_llm_mode integration."""

    def test_kiwi_edit_in_no_llm_dropdown(self):
        """'kiwi_edit' should be in the no_llm_mode dropdown choices."""
        pytest.importorskip("torch")
        from nodes.agent_node import FFMPEGAgentNode
        input_types = FFMPEGAgentNode.INPUT_TYPES()
        choices = input_types["required"]["no_llm_mode"][0]
        assert "kiwi_edit" in choices

    def test_process_kiwi_edit_only_exists(self):
        """process_kiwi_edit_only should be importable from nollm_modes."""
        pytest.importorskip("torch")
        from nodes.nollm_modes import process_kiwi_edit_only
        assert callable(process_kiwi_edit_only)

    def test_edit_video_exists(self):
        """edit_video should be importable from kiwi_edit_synthesizer."""
        from core.kiwi_edit_synthesizer import edit_video
        assert callable(edit_video)

    def test_cleanup_exists(self):
        """cleanup should be importable from kiwi_edit_synthesizer."""
        from core.kiwi_edit_synthesizer import cleanup
        assert callable(cleanup)


# --- Task Enhancement Templates -----------------------------------------------

class TestTaskPromptEnhancements:
    """Test that task prompt enhancement templates are complete."""

    def test_all_task_types_have_templates(self):
        """All expected task types should have prompt templates."""
        from core.kiwi_edit_synthesizer import TASK_PROMPT_ENHANCEMENTS
        expected = {"global_style", "local_change", "background_change",
                    "local_remove", "local_add"}
        assert set(TASK_PROMPT_ENHANCEMENTS.keys()) == expected

    def test_templates_are_non_empty(self):
        """Each task type's template list should be non-empty."""
        from core.kiwi_edit_synthesizer import TASK_PROMPT_ENHANCEMENTS
        for task, hints in TASK_PROMPT_ENHANCEMENTS.items():
            assert len(hints) >= 2, f"{task} has too few hints"

    def test_templates_are_strings(self):
        """Each template hint should be a non-empty string."""
        from core.kiwi_edit_synthesizer import TASK_PROMPT_ENHANCEMENTS
        for task, hints in TASK_PROMPT_ENHANCEMENTS.items():
            for hint in hints:
                assert isinstance(hint, str) and len(hint) > 10, \
                    f"{task}: hint too short: {hint!r}"


# --- Path Validation Tests ----------------------------------------------------

class TestKiwiEditPathValidation:
    """Test that path inputs are validated against traversal attacks."""

    def test_edit_video_rejects_traversal(self):
        """edit_video should reject path traversal in video_path."""
        from core.kiwi_edit_synthesizer import edit_video
        from core.errors import ValidationError
        with pytest.raises(ValidationError):
            edit_video("../../../../etc/passwd", prompt="test")
