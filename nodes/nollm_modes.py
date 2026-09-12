# coding: utf-8
"""Backwards-compatible facade for the no-LLM mode implementations.

The implementations moved to nodes/modes/ (one module per mode); this module
re-exports them so existing call sites keep working unchanged — including the
underscore-prefixed helpers that tests patch, which `import *` would not carry
across.

New code should import from nodes.modes directly.
"""

from __future__ import annotations

from .modes._shared import (  # noqa: F401
    Optional,
    Path,
    _CRF_MAP,
    _PRESET_MAP,
    _SAM3_PASSTHROUGH_SKILLS,
    _SKILL_TO_AUTOMASK_EFFECT,
    _encode_frames_to_video,
    _get_ffmpeg_bin,
    build_output_path,
    collect_frame_output,
    inject_effects_hints,
    json,
    logger,
    logging,
    merge_sam3_into_effects_pipeline,
    os,
    sam3_composite,
    sam3_premask,
    shutil,
    subprocess,
    tempfile,
    torch,
)

from .modes.ace_step import process_ace_step_only  # noqa: F401
from .modes.ai_upscale import process_ai_upscale_only  # noqa: F401
from .modes.animate_portrait import process_animate_portrait_only  # noqa: F401
from .modes.audiox_inpaint import process_audiox_inpaint_only  # noqa: F401
from .modes.audiox_music import process_audiox_music_only  # noqa: F401
from .modes.comparison import process_comparison_only  # noqa: F401
from .modes.dreamid_omni import process_dreamid_omni_only  # noqa: F401
from .modes.effects_pipeline import process_effects_pipeline  # noqa: F401
from .modes.fish_speech import process_fish_speech_only  # noqa: F401
from .modes.flux_klein import process_flux_klein_only  # noqa: F401
from .modes.foundation1 import process_foundation1_only  # noqa: F401
from .modes.kiwi_edit import process_kiwi_edit_only  # noqa: F401
from .modes.lip_sync import process_lip_sync_only  # noqa: F401
from .modes.marigold import process_marigold_only  # noqa: F401
from .modes.minimax_remover import process_minimax_remover_only  # noqa: F401
from .modes.mmaudio import process_mmaudio_only  # noqa: F401
from .modes.normalcrafter import process_normalcrafter_only  # noqa: F401
from .modes.onion_skin import process_onion_skin_only  # noqa: F401
from .modes.phyfps import process_phyfps_only  # noqa: F401
from .modes.rembg import process_rembg_only  # noqa: F401
from .modes.sam3 import process_sam3_only  # noqa: F401
from .modes.sam_audio_separate import process_sam_audio_separate  # noqa: F401
from .modes.sapiens2 import process_sapiens2_only  # noqa: F401
from .modes.scail2 import process_scail2_only  # noqa: F401
from .modes.sharp import process_sharp_only  # noqa: F401
from .modes.svi import process_svi_only  # noqa: F401
from .modes.video_depth import process_video_depth_only  # noqa: F401
from .modes.video_matting import process_video_matting_only  # noqa: F401
from .modes.wan_animate import process_wan_animate_only  # noqa: F401
from .modes.whisper import process_whisper_only  # noqa: F401

__all__ = ['Optional', 'Path', '_CRF_MAP', '_PRESET_MAP', '_SAM3_PASSTHROUGH_SKILLS', '_SKILL_TO_AUTOMASK_EFFECT', '_encode_frames_to_video', '_get_ffmpeg_bin', 'build_output_path', 'collect_frame_output', 'inject_effects_hints', 'json', 'logger', 'logging', 'merge_sam3_into_effects_pipeline', 'os', 'process_ace_step_only', 'process_ai_upscale_only', 'process_animate_portrait_only', 'process_audiox_inpaint_only', 'process_audiox_music_only', 'process_comparison_only', 'process_dreamid_omni_only', 'process_effects_pipeline', 'process_fish_speech_only', 'process_flux_klein_only', 'process_foundation1_only', 'process_kiwi_edit_only', 'process_lip_sync_only', 'process_marigold_only', 'process_minimax_remover_only', 'process_mmaudio_only', 'process_normalcrafter_only', 'process_onion_skin_only', 'process_phyfps_only', 'process_rembg_only', 'process_sam3_only', 'process_sam_audio_separate', 'process_sapiens2_only', 'process_scail2_only', 'process_sharp_only', 'process_svi_only', 'process_video_depth_only', 'process_video_matting_only', 'process_wan_animate_only', 'process_whisper_only', 'sam3_composite', 'sam3_premask', 'shutil', 'subprocess', 'tempfile', 'torch']
