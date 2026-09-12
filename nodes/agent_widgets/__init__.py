# coding: utf-8
"""Widget schema for the FFMPEG Agent node, split by mode.

INPUT_TYPES' `optional` block used to be a single 1,670-line dict literal.
It is now assembled from these modules in the order SECTIONS declares, which
must stay identical to the original: ComfyUI restores saved workflows by
widget *position*, so reordering silently loads values into the wrong
widgets. tests/test_widget_order.py pins that order against a snapshot.

To add a mode: write a function returning its widget dict, then append it to
SECTIONS — appending is safe, inserting is not.
"""

from __future__ import annotations

from . import (
    audio,
    basics,
    character_animation,
    compositing,
    editing,
    execution,
    masking,
    portrait,
    retiming,
    talking_head,
    transcription,
    upscaling,
    video_generation,
    view_synthesis,
    vision,
)

# (label, builder) in the exact order INPUT_TYPES must emit.
SECTIONS = [
    ('Connection inputs (always visible, forceInput)', basics.connection_inputs),
    ('Basic options (always visible)', basics.basic_options),
    ('LLM Behavior (always visible)', basics.llm_behavior),
    ('Advanced toggle', basics.advanced_toggle),
    ('Advanced: Rendering', basics.rendering),
    ('Advanced: Whisper', transcription.whisper),
    ('Advanced: SAM3', masking.sam3),
    ('Advanced: SAM3 Pre-Masking for No-LLM Modes', masking.sam3_premask),
    ('Advanced: FLUX Klein', editing.flux_klein),
    ('Advanced: Kiwi-Edit', editing.kiwi_edit),
    ('Advanced: MiniMax-Remover', editing.minimax_remover),
    ('Advanced: DreamID-Omni (WIP)', talking_head.dreamid_omni),
    ('Advanced: SCAIL-2 (native pose-driven character animation)', character_animation.scail2),
    ('Advanced: SAM-Audio', audio.sam_audio),
    ('Advanced: Marigold', vision.marigold),
    ('Advanced: NormalCrafter', vision.normalcrafter),
    ('Advanced: Video Depth Anything', vision.video_depth),
    ('Advanced: Sapiens2', vision.sapiens2),
    ('Advanced: AI Upscale', upscaling.ai_upscale),
    ('Advanced: Rembg Background Removal', masking.rembg),
    ('Advanced: MatAnyone2 Video Matting', masking.matanyone2),
    ('Advanced: Audio Output Mode', audio.output_mode),
    ('Advanced: Audio Resample Rate', audio.resample_rate),
    ('Advanced: Onion Skin', compositing.onion_skin),
    ('Advanced: Comparison', compositing.comparison),
    ('Advanced: PhyFPS (Visual Chronometer)', retiming.phyfps),
    ('Advanced: SHARP (3D Gaussian View Synthesis)', view_synthesis.sharp),
    ('Advanced: Wan-Animate', character_animation.wan_animate),
    ('Advanced: SVI 2.0 Pro', video_generation.svi),
    ('Advanced: Foundation-1 controls', audio.foundation1),
    ('Advanced: Fish Speech TTS controls', audio.fish_speech),
    ('Advanced: LivePortrait expression controls', portrait.expression_controls),
    ('Advanced: LivePortrait expression transfer', portrait.expression_transfer),
    ('Advanced: Batch processing', execution.batch_processing),
    ('Advanced: Usage tracking & downloads', execution.usage_tracking),
]


def build_optional() -> dict:
    """Assemble the `optional` widget dict in declaration order."""
    out: dict = {}
    for label, build in SECTIONS:
        for name, spec in build().items():
            if name in out:
                raise ValueError(
                    f"duplicate widget {name!r} declared twice "
                    f"(second time in {label!r})"
                )
            out[name] = spec
    return out
