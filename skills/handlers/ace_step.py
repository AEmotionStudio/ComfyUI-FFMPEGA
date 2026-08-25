"""FFMPEGA ACE-Step skill handler.

Uses ACE-Step 1.5 for music generation, cover creation, audio repaint,
track separation, and accompaniment generation.

Runs in-process with GPU↔CPU offloading via AceStepHandler.

License note:
    ACE-Step 1.5 is MIT-licensed (code and model weights).
"""

import logging
import os

try:
    from ..handler_contract import make_result
except ImportError:
    from skills.handler_contract import make_result

log = logging.getLogger("ffmpega")


def _f_ace_step(p):
    """Generate or improve music using ACE-Step 1.5 AI.

    Supports multiple modes:
    - ``generate``: Text-to-music generation with optional lyrics
    - ``cover``: Cover/improve existing audio (e.g. AudioX output)
    - ``repaint``: Selective regeneration of an audio region
    - ``audiox_repaint``: Two-stage AudioX → ACE-Step pipeline

    Params:
        prompt (str):           Text description of desired music.
        lyrics (str):           Lyrics with section markers ([verse], [chorus], etc.).
        mode (str):             Operation mode — generate/cover/repaint/audiox_repaint.
        audio_mode (str):       How to combine: replace/mix/save_only.
        reference_audio (str):  Path to reference audio for style guidance.
        mask_start (float):     Repaint region start (0-100%).
        mask_end (float):       Repaint region end (0-100%).
        duration (float):       Audio duration in seconds (10-600).
        seed (int):             Random seed (-1 = random).
        cfg_scale (float):      Guidance scale.
        steps (int):            Diffusion steps (turbo default = 8).
        lm_model (str):         LM tier — 0.6B or 1.7B.
        cover_strength (float): How closely cover follows source (0-1).
    """
    prompt = str(p.get("prompt", ""))
    lyrics = str(p.get("lyrics", ""))
    mode = str(p.get("mode", "generate")).lower()
    audio_mode = str(p.get("_audio_output_mode", p.get("audio_mode", "replace"))).lower()
    reference_audio = str(p.get("reference_audio", ""))
    mask_start = float(p.get("mask_start", 0.0))
    mask_end = float(p.get("mask_end", 100.0))
    duration = float(p.get("duration", 60.0))
    seed = int(p.get("seed", -1))
    cfg_scale = float(p.get("cfg_scale", 7.0))
    steps = int(p.get("steps", 8))
    lm_model = str(p.get("lm_model", "1.7B"))
    cover_strength = float(p.get("cover_strength", 0.8))
    video_path = p.get("_input_path", "")

    if audio_mode not in ("replace", "mix", "save_only"):
        audio_mode = "replace"
    if mode not in ("generate", "cover", "repaint", "audiox_repaint"):
        mode = "generate"

    # Try to import ACE-Step synthesizer
    try:
        try:
            from ...core.acestep_synthesizer import (
                generate_music_acestep,
                cover_audio,
                repaint_audio,
                audiox_to_acestep_repaint,
                is_available,
            )
        except ImportError:
            from core.acestep_synthesizer import (
                generate_music_acestep,
                cover_audio,
                repaint_audio,
                audiox_to_acestep_repaint,
                is_available,
            )
        _has_acestep = is_available()
    except ImportError:
        _has_acestep = False

    if not _has_acestep:
        log.warning(
            "ACE-Step not available — install with: "
            "pip install --no-deps git+https://github.com/ace-step/ACE-Step-1.5.git"
        )
        _metadata_ref = p.get("_metadata_ref")
        if _metadata_ref is not None and isinstance(_metadata_ref, dict):
            _metadata_ref["_skill_degraded"] = True
        return make_result()

    # Run the appropriate mode
    try:
        if mode == "audiox_repaint":
            # Two-stage: AudioX → ACE-Step pipeline
            if not video_path or not os.path.isfile(video_path):
                log.warning("audiox_repaint mode requires video input")
                return make_result()
            audio_path = audiox_to_acestep_repaint(
                video_path=video_path,
                prompt=prompt,
                lyrics=lyrics,
                cover_strength=cover_strength,
                seed=seed,
                lm_model=lm_model,
            )
        elif mode == "cover":
            # Cover existing audio
            src = reference_audio if reference_audio and os.path.isfile(reference_audio) else None
            if src is None:
                # Try to extract audio from video
                if video_path and os.path.isfile(video_path):
                    src = _extract_audio_from_video(video_path)
                if not src:
                    log.warning("cover mode requires reference_audio or video with audio")
                    return make_result()
            audio_path = cover_audio(
                audio_path=src,
                prompt=prompt,
                lyrics=lyrics,
                seed=seed,
                cover_strength=cover_strength,
                lm_model=lm_model,
            )
        elif mode == "repaint":
            # Selective repaint of audio region
            src = reference_audio if reference_audio and os.path.isfile(reference_audio) else None
            if src is None and video_path and os.path.isfile(video_path):
                src = _extract_audio_from_video(video_path)
            if not src:
                log.warning("repaint mode requires reference_audio or video with audio")
                return make_result()
            audio_path = repaint_audio(
                audio_path=src,
                prompt=prompt,
                mask_start=mask_start,
                mask_end=mask_end,
                seed=seed,
                lm_model=lm_model,
            )
        else:
            # Default: generate music from text
            audio_path = generate_music_acestep(
                prompt=prompt,
                lyrics=lyrics,
                duration=duration,
                seed=seed,
                cfg_scale=cfg_scale,
                steps=steps,
                reference_audio=reference_audio if reference_audio and os.path.isfile(reference_audio) else None,
                lm_model=lm_model,
            )
    except Exception as e:
        log.error("ACE-Step generation failed: %s", e)
        _metadata_ref = p.get("_metadata_ref")
        if _metadata_ref is not None and isinstance(_metadata_ref, dict):
            _metadata_ref["_skill_degraded"] = True
        return make_result()

    # Store generated path in metadata
    _metadata_ref = p.get("_metadata_ref")
    if _metadata_ref is not None and isinstance(_metadata_ref, dict):
        _metadata_ref["_generated_audio_path"] = audio_path

    if audio_mode == "save_only":
        # Just report the path, don't modify the video
        log.info("ACE-Step save_only: %s", audio_path)
        return make_result()

    # Build ffmpeg filter to mux audio into the video
    return _build_audio_filter(audio_path, audio_mode, p)


def _extract_audio_from_video(video_path: str) -> str | None:
    """Extract audio track from video to a temp WAV file."""
    import subprocess
    import tempfile

    fd, wav_path = tempfile.mkstemp(suffix=".wav", prefix="acestep_src_")
    os.close(fd)

    try:
        subprocess.run(
            [
                "ffmpeg", "-y", "-i", video_path,
                "-vn", "-acodec", "pcm_s16le",
                "-ar", "48000", "-ac", "2",
                wav_path,
            ],
            capture_output=True,
            timeout=60,
        )
        if os.path.isfile(wav_path) and os.path.getsize(wav_path) > 100:
            return wav_path
    except Exception as e:
        log.debug("Failed to extract audio from %s: %s", video_path, e)

    try:
        os.unlink(wav_path)
    except OSError:
        pass
    return None


def _build_audio_filter(audio_path, audio_mode, p):
    """Build the FFmpeg filter_complex for replacing or mixing audio."""
    escaped = audio_path.replace("'", "'\\''").replace(":", "\\:")

    if audio_mode == "replace":
        fc = (
            f"amovie={escaped}[_gen_ace];"
            f"[0:v]null[_vpass]"
        )
        return make_result(
            fc=fc,
            opts=["-map", "[_vpass]", "-map", "[_gen_ace]"],
        )
    elif audio_mode == "mix":
        if not p.get("_has_embedded_audio"):
            fc = (
                f"amovie={escaped}[_gen_ace];"
                f"[0:v]null[_vpass]"
            )
            return make_result(
                fc=fc,
                opts=["-map", "[_vpass]", "-map", "[_gen_ace]"],
            )
        else:
            fc = (
                f"amovie={escaped}[_gen_ace];"
                f"[0:a][_gen_ace]amix=inputs=2:duration=shortest[_aout];"
                f"[0:v]null[_vpass]"
            )
            return make_result(
                fc=fc,
                opts=["-map", "[_vpass]", "-map", "[_aout]"],
            )

    return make_result()
