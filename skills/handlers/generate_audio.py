"""FFMPEGA Generate Audio skill handler.

Uses MMAudio to synthesize audio from video content and/or text prompts.
Runs in-process with GPU↔CPU offloading (cached models).

License note:
    MMAudio model weights are CC-BY-NC 4.0 (non-commercial use only).
    The code that loads/runs them is GPL-3.0 (this project).
    Users download model weights on first use and accept the CC-BY-NC
    license themselves.  See https://creativecommons.org/licenses/by-nc/4.0/
"""

import logging
import os

try:
    from ..handler_contract import make_result
except ImportError:
    from skills.handler_contract import make_result

log = logging.getLogger("ffmpega")


def _f_generate_audio(p):
    """Generate audio from video and/or text using MMAudio AI.

    Synthesizes matching audio for the input video, then either replaces
    or mixes with the existing audio track based on the ``mode`` parameter.

    Params:
        prompt (str):           Text description to guide audio generation.
        negative_prompt (str):  What to avoid in the generated audio.
        mode (str):             "replace" or "mix" — how to combine with existing audio.
        seed (int):             Random seed for reproducibility.
        cfg_strength (float):   Guidance strength (higher = more prompt adherence).
    """
    prompt = str(p.get("prompt", ""))
    negative_prompt = str(p.get("negative_prompt", ""))
    mode = str(p.get("_mmaudio_mode", p.get("mode", "replace"))).lower()
    seed = int(p.get("seed", 42))
    cfg_strength = float(p.get("cfg_strength", 4.5))
    video_path = p.get("_input_path", "")

    if mode not in ("replace", "mix"):
        mode = "replace"

    log.info(
        "⚠️  generate_audio uses MMAudio model weights licensed CC-BY-NC 4.0 "
        "(non-commercial). See: https://creativecommons.org/licenses/by-nc/4.0/"
    )

    # Try to import MMAudio
    try:
        try:
            from ...core.mmaudio_synthesizer import generate_audio
        except ImportError:
            from core.mmaudio_synthesizer import generate_audio
        _has_mmaudio = True
    except ImportError:
        _has_mmaudio = False

    if not _has_mmaudio:
        log.warning(
            "MMAudio not available for generate_audio — install with: "
            "pip install --no-deps mmaudio"
        )
        _metadata_ref = p.get("_metadata_ref")
        if _metadata_ref is not None and isinstance(_metadata_ref, dict):
            _metadata_ref["_skill_degraded"] = True
        return make_result()

    if not video_path or not os.path.isfile(video_path):
        if not prompt:
            log.warning(
                "generate_audio requires a video input or a text prompt. "
                "No video path available and no prompt provided."
            )
            return make_result()
        # Text-to-audio mode — no video, just prompt
        video_path = None

    # Generate audio in-process (with GPU↔CPU offloading)
    try:
        audio_path = generate_audio(
            video_path=video_path,
            prompt=prompt,
            negative_prompt=negative_prompt,
            seed=seed,
            cfg_strength=cfg_strength,
        )
    except Exception as e:
        log.error("MMAudio audio generation failed: %s", e)
        _metadata_ref = p.get("_metadata_ref")
        if _metadata_ref is not None and isinstance(_metadata_ref, dict):
            _metadata_ref["_skill_degraded"] = True
        return make_result()

    # Store generated audio path in metadata for potential downstream use
    _metadata_ref = p.get("_metadata_ref")
    if _metadata_ref is not None and isinstance(_metadata_ref, dict):
        _metadata_ref["_generated_audio_path"] = audio_path

    # Build ffmpeg command based on mode
    if mode == "replace":
        # The generated audio file needs to be added as an extra input
        # by the composer. We use output options to map it.
        # Since the handler can't add inputs dynamically, we use a
        # filter_complex with movie source to load the audio file.
        from ..handler_contract import make_result as _mr

        escaped = audio_path.replace("'", "'\\''").replace(":", "\\:")
        fc = (
            f"amovie={escaped}[_gen_audio];"
            f"[0:v]null[_vpass]"
        )
        return _mr(
            fc=fc,
            opts=["-map", "[_vpass]", "-map", "[_gen_audio]"],
        )

    elif mode == "mix":
        # Mix generated audio with original
        if not p.get("_has_embedded_audio"):
            # No existing audio — just use the generated audio
            escaped = audio_path.replace("'", "'\\''").replace(":", "\\:")
            fc = (
                f"amovie={escaped}[_gen_audio];"
                f"[0:v]null[_vpass]"
            )
            return make_result(
                fc=fc,
                opts=["-map", "[_vpass]", "-map", "[_gen_audio]"],
            )
        else:
            escaped = audio_path.replace("'", "'\\''").replace(":", "\\:")
            fc = (
                f"amovie={escaped}[_gen_audio];"
                f"[0:a][_gen_audio]amix=inputs=2:duration=shortest[_aout];"
                f"[0:v]null[_vpass]"
            )
            return make_result(
                fc=fc,
                opts=["-map", "[_vpass]", "-map", "[_aout]"],
            )

    return make_result()
