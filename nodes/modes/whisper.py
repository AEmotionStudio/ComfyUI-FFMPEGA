# coding: utf-8
"""No-LLM mode: whisper.

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


async def process_whisper_only(
    # dependencies
    media_converter,
    # parameters
    mode: str,
    effective_video_path: str,
    video_metadata,
    save_output: bool,
    output_path: str,
    preview_mode: bool,
    quality_preset: str,
    crf: int,
    encoding_preset: str,
    whisper_device: str = "cpu",
    whisper_model: str = "large-v3",
    temp_video_from_images: Optional[str] = None,
    temp_video_with_audio: Optional[str] = None,
    **kwargs,
) -> tuple[torch.Tensor, dict, str, str, str, str]:
    """Run Whisper transcription directly without any LLM involvement.

    Transcribes the video audio using Whisper and burns subtitles
    (SRT or karaoke ASS) into the output video.  The full transcription
    text is included in the ``analysis`` return field.

    Args:
        mode: "transcribe" for SRT subtitles, "karaoke_subtitles" for
              word-by-word karaoke ASS subtitles.

    Returns the standard 6-tuple:
        (images_tensor, audio, output_path, command_log, analysis, mask_overlay_path)
    """
    try:
        from ...core.whisper_transcriber import (
            transcribe_audio,
            segments_to_srt,
            words_to_karaoke_ass,
        )
    except ImportError:
        from core.whisper_transcriber import (  # type: ignore
            transcribe_audio,
            segments_to_srt,
            words_to_karaoke_ass,
        )

    logger.info(
        "Whisper-only mode (%s): device=%s, model=%s",
        mode, whisper_device, whisper_model,
    )

    # --- Build output path ---
    output_path, temp_render_dir = build_output_path(
        effective_video_path=effective_video_path,
        save_output=save_output,
        output_path=output_path,
        preview_mode=preview_mode,
    )

    # --- Transcribe ---
    result = transcribe_audio(
        effective_video_path,
        model_size=whisper_model,
        device=whisper_device,
    )

    # --- Generate subtitle file ---
    sub_tmp_path = None  # track for cleanup after ffmpeg
    if mode == "karaoke_subtitles":
        if not result.words:
            logger.warning("Whisper found no words — producing clean passthrough")
            sub_filter = None
        else:
            ass_content = words_to_karaoke_ass(result.words)
            tmp = tempfile.NamedTemporaryFile(
                mode="w", suffix=".ass", delete=False, encoding="utf-8",
            )
            tmp.write(ass_content)
            tmp.close()
            sub_tmp_path = tmp.name

            try:
                from ...core.sanitize import ffmpeg_escape_path
            except ImportError:
                from core.sanitize import ffmpeg_escape_path  # type: ignore
            escaped_path = ffmpeg_escape_path(tmp.name)
            sub_filter = f"ass={escaped_path}"
    else:
        # mode == "transcribe"
        if not result.segments:
            logger.warning("Whisper found no speech — producing clean passthrough")
            sub_filter = None
        else:
            srt_content = segments_to_srt(result.segments)
            tmp = tempfile.NamedTemporaryFile(
                mode="w", suffix=".srt", delete=False, encoding="utf-8",
            )
            tmp.write(srt_content)
            tmp.close()
            sub_tmp_path = tmp.name

            try:
                from ...core.sanitize import ffmpeg_escape_path
            except ImportError:
                from core.sanitize import ffmpeg_escape_path  # type: ignore
            escaped_path = ffmpeg_escape_path(tmp.name)
            sub_filter = f"subtitles={escaped_path}"

    # --- Build ffmpeg command ---
    effective_crf = crf if crf >= 0 else _CRF_MAP.get(quality_preset, 23)
    effective_preset = encoding_preset if encoding_preset != "auto" else _PRESET_MAP.get(quality_preset, "medium")

    _ffmpeg = _get_ffmpeg_bin()
    ffmpeg_cmd = [_ffmpeg, "-y", "-i", effective_video_path]

    if sub_filter:
        ffmpeg_cmd.extend(["-vf", sub_filter])

    ffmpeg_cmd.extend([
        "-c:v", "libx264",
        "-crf", str(effective_crf),
        "-preset", effective_preset,
        "-pix_fmt", "yuv420p",
        "-c:a", "copy",
    ])

    if preview_mode:
        # Insert scale + duration limit
        if sub_filter:
            # Append scale to existing vf
            vf_idx = ffmpeg_cmd.index("-vf")
            ffmpeg_cmd[vf_idx + 1] += ",scale=480:trunc(ow/a/2)*2"
        else:
            ffmpeg_cmd.extend(["-vf", "scale=480:trunc(ow/a/2)*2"])
        ffmpeg_cmd.extend(["-t", "10"])

    ffmpeg_cmd.append(output_path)

    logger.debug("Whisper-only command: %s", " ".join(ffmpeg_cmd))
    proc = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"Whisper-only mode: ffmpeg failed:\n{proc.stderr[-500:]}"
        )

    # --- Collect frame/audio output ---
    unique_id = str(kwargs.get("unique_id", ""))
    hidden_prompt = kwargs.get("hidden_prompt") or {}
    images_tensor, audio_out = collect_frame_output(
        media_converter=media_converter,
        output_path=output_path,
        unique_id=unique_id,
        hidden_prompt=hidden_prompt,
        removes_audio=False,
    )

    # --- Build analysis string (includes full transcription) ---
    cmd_log = " ".join(ffmpeg_cmd)
    mode_label = "Karaoke Subtitles" if mode == "karaoke_subtitles" else "SRT Subtitles"
    analysis = (
        f"Whisper-Only Mode (no LLM)\n"
        f"Mode: {mode_label}\n"
        f"Model: {whisper_model}\n"
        f"Device: {whisper_device}\n"
        f"Language: {result.language or 'auto-detected'}\n"
        f"Segments: {len(result.segments)}\n"
        f"Words: {len(result.words)}\n\n"
        f"--- Transcription ---\n"
        f"{result.full_text or '(no speech detected)'}"
    )

    # --- Cleanup temp files ---
    for tmp_path in [temp_video_from_images, temp_video_with_audio, sub_tmp_path]:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
    if not save_output and temp_render_dir and os.path.isdir(temp_render_dir):
        if not os.listdir(temp_render_dir):
            shutil.rmtree(temp_render_dir, ignore_errors=True)

    return (images_tensor, audio_out, output_path, cmd_log, analysis, "")
