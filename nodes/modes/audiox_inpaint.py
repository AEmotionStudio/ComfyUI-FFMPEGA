# coding: utf-8
"""No-LLM mode: audiox inpaint.

Moved verbatim from nodes/nollm_modes.py, which is now a re-export facade.
"""

from __future__ import annotations

from ._shared import (
    Optional,
    _CRF_MAP,
    _PRESET_MAP,
    _get_ffmpeg_bin,
    build_output_path,
    collect_frame_output,
    logger,
    os,
    shutil,
    subprocess,
    tempfile,
    torch,
)


async def process_audiox_inpaint_only(
    # dependencies
    media_converter,
    # parameters
    prompt: str,
    audio_output_mode: str,
    effective_video_path: str,
    video_metadata,
    save_output: bool,
    output_path: str,
    preview_mode: bool,
    quality_preset: str,
    crf: int,
    encoding_preset: str,
    temp_video_from_images: Optional[str] = None,
    temp_video_with_audio: Optional[str] = None,
    **kwargs,
) -> tuple[torch.Tensor, dict, str, str, str, str]:
    """Run AudioX audio inpainting directly without any LLM involvement.

    Extracts audio from the video, inpaints the second half (for completion),
    then muxes the result back.

    Args:
        prompt: Text description to guide inpainted audio.
        audio_output_mode: "auto"/"replace" to discard original audio,
                           "mix" to blend, "save_only" to skip muxing.

    Returns the standard 6-tuple:
        (images_tensor, audio, output_path, command_log, analysis, mask_overlay_path)
    """
    # Treat "auto" as "replace" in no-LLM context
    if audio_output_mode == "auto":
        audio_output_mode = "replace"
    logger.info("AudioX inpaint-only mode: prompt=%r, mode=%s", prompt, audio_output_mode)

    # --- Import AudioX ---
    try:
        try:
            from ...core.audiox_synthesizer import inpaint_audio
        except ImportError:
            from core.audiox_synthesizer import inpaint_audio  # type: ignore
    except ImportError:
        raise RuntimeError(
            "AudioX is not installed. Install with: "
            "pip install --no-deps stable-audio-tools && "
            "pip install alias-free-torch x-transformers einops-exts k-diffusion"
        )

    # --- Extract audio for inpainting ---
    _ffmpeg = _get_ffmpeg_bin()
    tmp_wav = tempfile.NamedTemporaryFile(
        suffix=".wav", delete=False, prefix="ffmpega_ax_"
    )
    tmp_wav_path = tmp_wav.name
    tmp_wav.close()

    extract_result = subprocess.run(
        [_ffmpeg, "-y", "-i", effective_video_path,
         "-vn", "-acodec", "pcm_f32le", "-ar", "44100", "-ac", "2",
         tmp_wav_path],
        capture_output=True, timeout=60,
    )
    if extract_result.returncode != 0:
        raise RuntimeError(
            "AudioX inpaint-only: failed to extract audio from video. "
            "Ensure the input video has an audio track."
        )

    # --- Build output path ---
    output_path, temp_render_dir = build_output_path(
        effective_video_path=effective_video_path,
        save_output=save_output,
        output_path=output_path,
        preview_mode=preview_mode,
    )

    # --- Inpaint audio via AudioX ---
    audio_file = None
    try:
        audio_file = inpaint_audio(
            audio_path=tmp_wav_path,
            prompt=prompt,
            mask_start=50.0,  # Default: inpaint second half (audio completion)
            mask_end=100.0,
        )
    except Exception as e:
        logger.error("AudioX inpaint-only: generation failed: %s", e)
        try:
            try:
                from ...core.audiox_synthesizer import cleanup as _ax_cleanup
            except ImportError:
                from core.audiox_synthesizer import cleanup as _ax_cleanup  # type: ignore
            _ax_cleanup()
        except Exception:
            pass
        raise RuntimeError(f"AudioX audio inpainting failed: {e}") from e

    # --- Detect if source has audio (for mix mode) ---
    has_audio = bool(video_metadata.primary_audio)

    # --- save_only: skip muxing, just return the audio file path ---
    if audio_output_mode == "save_only":
        shutil.copy2(effective_video_path, output_path)
        unique_id = str(kwargs.get("unique_id", ""))
        hidden_prompt = kwargs.get("hidden_prompt") or {}
        images_tensor, audio_out = collect_frame_output(
            media_converter=media_converter,
            output_path=output_path,
            unique_id=unique_id,
            hidden_prompt=hidden_prompt,
            removes_audio=False,
        )
        analysis = (
            f"AudioX Inpaint-Only Mode (no LLM) — save_only\n"
            f"Prompt: {prompt or '(no text prompt)'}\n"
            f"Inpainted audio saved to: {audio_file}\n"
            f"(Audio was NOT muxed into the video)"
        )
        return (images_tensor, audio_out, output_path, "", analysis, "")

    # --- Mux inpainted audio back into video ---
    effective_crf = crf if crf >= 0 else _CRF_MAP.get(quality_preset, 23)
    effective_preset = encoding_preset if encoding_preset != "auto" else _PRESET_MAP.get(quality_preset, "medium")

    if audio_output_mode == "mix" and has_audio:
        ffmpeg_cmd = [
            _ffmpeg, "-y",
            "-i", effective_video_path,
            "-i", audio_file,
            "-filter_complex",
            "[0:a][1:a]amix=inputs=2:duration=shortest[aout]",
            "-map", "0:v",
            "-map", "[aout]",
            "-c:v", "libx264",
            "-crf", str(effective_crf),
            "-preset", effective_preset,
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "192k",
        ]
    else:
        ffmpeg_cmd = [
            _ffmpeg, "-y",
            "-i", effective_video_path,
            "-i", audio_file,
            "-map", "0:v",
            "-map", "1:a",
            "-c:v", "copy",
            "-c:a", "aac",
            "-b:a", "192k",
            "-shortest",
        ]

    if preview_mode:
        if audio_output_mode == "mix" and has_audio:
            ffmpeg_cmd.extend(["-vf", "scale=480:trunc(ow/a/2)*2", "-t", "10"])
        else:
            ffmpeg_cmd = [
                _ffmpeg, "-y",
                "-i", effective_video_path,
                "-i", audio_file,
                "-map", "0:v",
                "-map", "1:a",
                "-vf", "scale=480:trunc(ow/a/2)*2",
                "-t", "10",
                "-c:v", "libx264",
                "-crf", str(effective_crf),
                "-preset", effective_preset,
                "-pix_fmt", "yuv420p",
                "-c:a", "aac",
                "-b:a", "192k",
                "-shortest",
            ]

    ffmpeg_cmd.append(output_path)

    logger.debug("AudioX inpaint-only ffmpeg command: %s", " ".join(ffmpeg_cmd))
    try:
        proc = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(
                f"AudioX inpaint-only mode: ffmpeg mux failed:\n{proc.stderr[-500:]}"
            )

        unique_id = str(kwargs.get("unique_id", ""))
        hidden_prompt = kwargs.get("hidden_prompt") or {}
        images_tensor, audio_out = collect_frame_output(
            media_converter=media_converter,
            output_path=output_path,
            unique_id=unique_id,
            hidden_prompt=hidden_prompt,
            removes_audio=False,
        )

        cmd_log = " ".join(ffmpeg_cmd)
        analysis = (
            f"AudioX Inpaint-Only Mode (no LLM)\n"
            f"Prompt: {prompt or '(no text prompt)'}\n"
            f"Audio mode: {audio_output_mode}\n"
            f"Mask: 50-100% (audio completion)\n\n"
            f"Inpainted audio: {audio_file}\n"
            f"Output: {output_path}"
        )

        return (images_tensor, audio_out, output_path, cmd_log, analysis, "")
    finally:
        for tmp_path in [temp_video_from_images, temp_video_with_audio, tmp_wav_path]:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
        if audio_file and os.path.exists(audio_file):
            try:
                os.remove(audio_file)
            except OSError:
                pass
        if not save_output and temp_render_dir and os.path.isdir(temp_render_dir):
            if not os.listdir(temp_render_dir):
                shutil.rmtree(temp_render_dir, ignore_errors=True)
