"""FFMPEGA Audio Inpaint skill handler.

Uses AudioX to fill gaps or extend existing audio using AI.
Runs in-process with GPU↔CPU offloading (cached models).

License note:
    AudioX model weights are CC-BY-NC (non-commercial use only).
    The code that loads/runs them is GPL-3.0 (this project).
    Users download model weights on first use and accept the CC-BY-NC
    license themselves.  See https://huggingface.co/HKUSTAudio/AudioX-MAF
"""

import logging
import os
import tempfile

try:
    from ..handler_contract import make_result
except ImportError:
    from skills.handler_contract import make_result

log = logging.getLogger("ffmpega")


def _f_audio_inpaint(p):
    """Inpaint or extend audio using AudioX AI.

    Fills a masked region of the audio track with AI-generated content
    guided by the text prompt.

    Params:
        prompt (str):           Text description to guide inpainted audio.
        negative_prompt (str):  What to avoid in the generated audio.
        mask_start (float):     Start of mask region as percentage (0-100).
        mask_end (float):       End of mask region as percentage (0-100).
        seed (int):             Random seed for reproducibility (-1 = random).
        cfg_scale (float):      Guidance scale (higher = more prompt adherence).
        steps (int):            Number of diffusion steps (default 250).
    """
    prompt = str(p.get("prompt", ""))
    negative_prompt = str(p.get("negative_prompt", ""))
    mask_start = float(p.get("mask_start", 0.0))
    mask_end = float(p.get("mask_end", 100.0))
    seed = int(p.get("seed", -1))
    cfg_scale = float(p.get("cfg_scale", 7.0))
    steps = int(p.get("steps", 250))
    video_path = p.get("_input_path", "")

    log.info(
        "⚠️  audio_inpaint uses AudioX model weights licensed CC-BY-NC "
        "(non-commercial). See: https://huggingface.co/HKUSTAudio/AudioX-MAF"
    )

    # Try to import AudioX synthesizer
    try:
        try:
            from ...core.audiox_synthesizer import inpaint_audio
        except ImportError:
            from core.audiox_synthesizer import inpaint_audio
        _has_audiox = True
    except ImportError:
        _has_audiox = False

    if not _has_audiox:
        log.warning(
            "AudioX not available for audio_inpaint — install with: "
            "pip install --no-deps stable-audio-tools"
        )
        _metadata_ref = p.get("_metadata_ref")
        if _metadata_ref is not None and isinstance(_metadata_ref, dict):
            _metadata_ref["_skill_degraded"] = True
        return make_result()

    if not video_path or not os.path.isfile(video_path):
        log.warning(
            "audio_inpaint requires an input video/audio file."
        )
        return make_result()

    # Extract audio from the video first
    audio_path = _extract_audio(video_path)
    if not audio_path:
        log.warning("audio_inpaint: no audio track found in input")
        _metadata_ref = p.get("_metadata_ref")
        if _metadata_ref is not None and isinstance(_metadata_ref, dict):
            _metadata_ref["_skill_degraded"] = True
        return make_result()

    # Inpaint audio
    try:
        result_path = inpaint_audio(
            audio_path=audio_path,
            prompt=prompt,
            negative_prompt=negative_prompt,
            mask_start=mask_start,
            mask_end=mask_end,
            seed=seed,
            cfg_scale=cfg_scale,
            steps=steps,
        )
    except Exception as e:
        log.error("AudioX audio inpainting failed: %s", e)
        _metadata_ref = p.get("_metadata_ref")
        if _metadata_ref is not None and isinstance(_metadata_ref, dict):
            _metadata_ref["_skill_degraded"] = True
        return make_result()

    # Store path in metadata
    _metadata_ref = p.get("_metadata_ref")
    if _metadata_ref is not None and isinstance(_metadata_ref, dict):
        _metadata_ref["_generated_audio_path"] = result_path

    # Determine audio output mode
    audio_mode = str(p.get("_audio_output_mode", p.get("mode", "replace"))).lower()
    if audio_mode not in ("replace", "mix", "save_only"):
        audio_mode = "replace"

    # save_only: just store the path, don't mux
    if audio_mode == "save_only":
        log.info("audio_inpaint save_only: %s", result_path)
        return make_result()

    escaped = result_path.replace("'", "'\\''").replace(":", "\\:")

    if audio_mode == "mix" and p.get("_has_embedded_audio"):
        # Mix inpainted audio with original
        fc = (
            f"amovie={escaped}[_inpaint_audio];"
            f"[0:a][_inpaint_audio]amix=inputs=2:duration=shortest[_aout];"
            f"[0:v]null[_vpass]"
        )
        return make_result(
            fc=fc,
            opts=["-map", "[_vpass]", "-map", "[_aout]"],
        )

    # Replace (default) or mix with no existing audio
    fc = (
        f"amovie={escaped}[_inpaint_audio];"
        f"[0:v]null[_vpass]"
    )
    return make_result(
        fc=fc,
        opts=["-map", "[_vpass]", "-map", "[_inpaint_audio]"],
    )


def _extract_audio(video_path: str) -> str | None:
    """Extract audio from video to a temp WAV file."""
    import subprocess

    try:
        from core.bin_paths import get_ffmpeg_bin
        ffmpeg = get_ffmpeg_bin()
    except ImportError:
        ffmpeg = "ffmpeg"

    tmp = tempfile.NamedTemporaryFile(
        suffix=".wav", delete=False, prefix="ffmpega_extract_"
    )
    tmp_path = tmp.name
    tmp.close()

    try:
        result = subprocess.run(
            [ffmpeg, "-y", "-i", video_path,
             "-vn", "-acodec", "pcm_f32le",
             "-ar", "44100", "-ac", "2",
             tmp_path],
            capture_output=True, timeout=60,
        )
        if result.returncode == 0 and os.path.isfile(tmp_path):
            return tmp_path
    except Exception:
        pass

    # Clean up on failure
    try:
        os.unlink(tmp_path)
    except OSError:
        pass
    return None
