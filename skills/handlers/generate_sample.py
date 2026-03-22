"""FFMPEGA Foundation-1 skill handler.

Uses Foundation-1 to generate production-ready music samples/loops
from text prompts. Runs in-process with GPU↔CPU offloading.

License note:
    Foundation-1 model weights are under the Stability AI Community
    License (non-commercial or <$1M annual revenue).
    The code that loads/runs them is GPL-3.0 (this project).
    Users download model weights on first use and accept that license
    themselves.  See https://huggingface.co/RoyalCities/Foundation-1
"""

import logging
import os

try:
    from ..handler_contract import make_result
except ImportError:
    from skills.handler_contract import make_result

log = logging.getLogger("ffmpega")


def _f_generate_sample(p):
    """Generate a music sample or loop using Foundation-1 AI.

    Produces tempo-synced, key-aware musical loops with fine-grained
    control over instrument identity, timbre, FX, and musical structure.

    Params:
        prompt (str):           Text description of desired sound/loop.
        negative_prompt (str):  What to avoid in the generated audio.
        preset (str):           Preset name (warm_pad, synth_lead, bass_loop, etc.).
        mode (str):             "replace" or "mix" — how to combine with existing audio.
        seed (int):             Random seed for reproducibility (-1 = random).
        cfg_scale (float):      Guidance scale (higher = more prompt adherence).
        duration (float):       Override duration in seconds.
        steps (int):            Number of diffusion steps (default 100).
        bpm (int):              Beats per minute (0 = auto).
        bars (int):             Number of bars (0 = auto).
        key (str):              Musical key (e.g. "C major", "A minor").
    """
    prompt = str(p.get("prompt", ""))
    negative_prompt = str(p.get("negative_prompt", ""))
    preset = str(p.get("preset", ""))
    mode = str(p.get("_audio_output_mode", p.get("mode", "replace"))).lower()
    seed = int(p.get("seed", -1))
    cfg_scale = float(p.get("cfg_scale", 7.0))
    duration = p.get("duration")
    if duration is not None:
        duration = float(duration)
    steps = int(p.get("steps", 100))
    bpm = int(p.get("bpm", 0))
    bars = int(p.get("bars", 0))
    key = str(p.get("key", ""))

    if mode not in ("replace", "mix", "save_only"):
        mode = "replace"

    log.info(
        "⚠️  generate_sample uses Foundation-1 model weights licensed under "
        "the Stability AI Community License. "
        "See: https://huggingface.co/RoyalCities/Foundation-1"
    )

    # Try to import Foundation-1 synthesizer
    try:
        try:
            from ...core.foundation1_synthesizer import generate_sample
        except ImportError:
            from core.foundation1_synthesizer import generate_sample
        _has_foundation1 = True
    except ImportError:
        _has_foundation1 = False

    if not _has_foundation1:
        log.warning(
            "Foundation-1 not available for generate_sample — install with: "
            "pip install --no-deps stable-audio-tools"
        )
        _metadata_ref = p.get("_metadata_ref")
        if _metadata_ref is not None and isinstance(_metadata_ref, dict):
            _metadata_ref["_skill_degraded"] = True
        return make_result()

    if not prompt and not preset:
        log.warning(
            "generate_sample requires a text prompt or preset. "
            "No prompt or preset provided."
        )
        return make_result()

    # Generate sample in-process
    try:
        audio_path = generate_sample(
            prompt=prompt,
            negative_prompt=negative_prompt,
            preset=preset,
            bpm=bpm,
            bars=bars,
            key=key,
            duration=duration,
            seed=seed,
            cfg_scale=cfg_scale,
            steps=steps,
        )
    except Exception as e:
        log.error("Foundation-1 sample generation failed: %s", e)
        _metadata_ref = p.get("_metadata_ref")
        if _metadata_ref is not None and isinstance(_metadata_ref, dict):
            _metadata_ref["_skill_degraded"] = True
        return make_result()

    # Store path in metadata
    _metadata_ref = p.get("_metadata_ref")
    if _metadata_ref is not None and isinstance(_metadata_ref, dict):
        _metadata_ref["_generated_audio_path"] = audio_path

    # Build ffmpeg command based on mode
    return _build_audio_filter(audio_path, mode, p)


def _build_audio_filter(audio_path, mode, p):
    """Build the FFmpeg filter_complex for replacing or mixing audio."""
    escaped = audio_path.replace("'", "'\\''").replace(":", "\\:")

    if mode == "save_only":
        log.info("generate_sample save_only: %s", audio_path)
        return make_result()

    if mode == "replace":
        fc = (
            f"amovie={escaped}[_gen_sample];"
            f"[0:v]null[_vpass]"
        )
        return make_result(
            fc=fc,
            opts=["-map", "[_vpass]", "-map", "[_gen_sample]"],
        )
    elif mode == "mix":
        if not p.get("_has_embedded_audio"):
            fc = (
                f"amovie={escaped}[_gen_sample];"
                f"[0:v]null[_vpass]"
            )
            return make_result(
                fc=fc,
                opts=["-map", "[_vpass]", "-map", "[_gen_sample]"],
            )
        else:
            fc = (
                f"amovie={escaped}[_gen_sample];"
                f"[0:a][_gen_sample]amix=inputs=2:duration=shortest[_aout];"
                f"[0:v]null[_vpass]"
            )
            return make_result(
                fc=fc,
                opts=["-map", "[_vpass]", "-map", "[_aout]"],
            )

    return make_result()
