"""FFMPEGA Generate Music skill handler.

Uses AudioX to generate music from text and/or video.
Runs in-process with GPU↔CPU offloading (cached models).

License note:
    AudioX model weights are CC-BY-NC (non-commercial use only).
    The code that loads/runs them is GPL-3.0 (this project).
    Users download model weights on first use and accept the CC-BY-NC
    license themselves.  See https://huggingface.co/HKUSTAudio/AudioX-MAF
"""

import logging
import os

try:
    from ..handler_contract import make_result
except ImportError:
    from skills.handler_contract import make_result

log = logging.getLogger("ffmpega")


def _f_generate_music(p):
    """Generate music from text and/or video using AudioX AI.

    Synthesizes music for the input, then either replaces or mixes
    with the existing audio track based on the ``mode`` parameter.

    Params:
        prompt (str):           Text description to guide music generation.
        negative_prompt (str):  What to avoid in the generated music.
        mode (str):             "replace" or "mix" — how to combine with existing audio.
        seed (int):             Random seed for reproducibility (-1 = random).
        cfg_scale (float):      Guidance scale (higher = more prompt adherence).
        duration (float):       Override duration in seconds (max 10s).
        steps (int):            Number of diffusion steps (default 250).
    """
    prompt = str(p.get("prompt", ""))
    negative_prompt = str(p.get("negative_prompt", ""))
    mode = str(p.get("_audio_output_mode", p.get("mode", "replace"))).lower()
    seed = int(p.get("seed", -1))
    cfg_scale = float(p.get("cfg_scale", 7.0))
    duration = p.get("duration")
    if duration is not None:
        duration = float(duration)
    steps = int(p.get("steps", 250))
    video_path = p.get("_input_path", "")

    if mode not in ("replace", "mix", "save_only"):
        mode = "replace"

    log.info(
        "⚠️  generate_music uses AudioX model weights licensed CC-BY-NC "
        "(non-commercial). See: https://huggingface.co/HKUSTAudio/AudioX-MAF"
    )

    # Try to import AudioX synthesizer
    try:
        try:
            from ...core.audiox_synthesizer import generate_music
        except ImportError:
            from core.audiox_synthesizer import generate_music
        _has_audiox = True
    except ImportError:
        _has_audiox = False

    if not _has_audiox:
        log.warning(
            "AudioX not available for generate_music — install with: "
            "pip install --no-deps stable-audio-tools"
        )
        _metadata_ref = p.get("_metadata_ref")
        if _metadata_ref is not None and isinstance(_metadata_ref, dict):
            _metadata_ref["_skill_degraded"] = True
        return make_result()

    if not video_path or not os.path.isfile(video_path):
        if not prompt:
            log.warning(
                "generate_music requires a video input or a text prompt. "
                "No video path available and no prompt provided."
            )
            return make_result()
        video_path = None

    # Generate music in-process
    try:
        audio_path = generate_music(
            video_path=video_path,
            prompt=prompt,
            negative_prompt=negative_prompt,
            duration=duration,
            seed=seed,
            cfg_scale=cfg_scale,
            steps=steps,
        )
    except Exception as e:
        log.error("AudioX music generation failed: %s", e)
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
        log.info("generate_music save_only: %s", audio_path)
        return make_result()

    if mode == "replace":
        fc = (
            f"amovie={escaped}[_gen_music];"
            f"[0:v]null[_vpass]"
        )
        return make_result(
            fc=fc,
            opts=["-map", "[_vpass]", "-map", "[_gen_music]"],
        )
    elif mode == "mix":
        if not p.get("_has_embedded_audio"):
            fc = (
                f"amovie={escaped}[_gen_music];"
                f"[0:v]null[_vpass]"
            )
            return make_result(
                fc=fc,
                opts=["-map", "[_vpass]", "-map", "[_gen_music]"],
            )
        else:
            fc = (
                f"amovie={escaped}[_gen_music];"
                f"[0:a][_gen_music]amix=inputs=2:duration=shortest[_aout];"
                f"[0:v]null[_vpass]"
            )
            return make_result(
                fc=fc,
                opts=["-map", "[_vpass]", "-map", "[_aout]"],
            )

    return make_result()
