# coding: utf-8
"""No-LLM mode: ace step.

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


async def process_ace_step_only(
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
    """Run ACE-Step music generation directly without any LLM involvement.

    Generates high-quality music from a text prompt (and optional lyrics) using
    ACE-Step 1.5, then muxes the result into the output video. If the source
    video has existing audio and the prompt is empty, ACE-Step will attempt
    to cover/repaint the existing audio for higher quality.

    Args:
        prompt: Text description to guide music generation.
        audio_output_mode: "auto"/"replace" to discard original audio,
                           "mix" to blend, "save_only" to skip muxing.

    Returns the standard 6-tuple:
        (images_tensor, audio, output_path, command_log, analysis, mask_overlay_path)
    """
    # Treat "auto" as "replace" in no-LLM context
    if audio_output_mode == "auto":
        audio_output_mode = "replace"
    logger.info(
        "ACE-Step music-only mode: prompt=%r, mode=%s", prompt, audio_output_mode,
    )

    # --- Import ACE-Step ---
    try:
        try:
            from ...core.acestep_synthesizer import (
                generate_music_acestep,
                cover_audio,
                generate_lyrics as _ace_generate_lyrics,
                cleanup as _ace_cleanup,
            )
        except ImportError:
            from core.acestep_synthesizer import (  # type: ignore
                generate_music_acestep,
                cover_audio,
                generate_lyrics as _ace_generate_lyrics,
                cleanup as _ace_cleanup,
            )
    except ImportError:
        raise RuntimeError(
            "ACE-Step is not installed. Install with: "
            "pip install --no-deps git+https://github.com/ace-step/ACE-Step-1.5.git"
        )

    # --- Build output path ---
    output_path, temp_render_dir = build_output_path(
        effective_video_path=effective_video_path,
        save_output=save_output,
        output_path=output_path,
        preview_mode=preview_mode,
    )

    # --- Resolve lyrics: text_a = manual lyrics, auto-generate if empty ---
    text_a = kwargs.get("text_a", "") or ""
    lyrics = text_a.strip()

    # --- Extract ACE-Step advanced params ---
    ace_cover_strength = float(kwargs.get("ace_cover_strength", 0.5))
    ace_steps = int(kwargs.get("ace_steps", 8))
    ace_cfg_scale = float(kwargs.get("ace_cfg_scale", 7.0))
    ace_bpm = (kwargs.get("ace_bpm", "") or "").strip()
    ace_key = (kwargs.get("ace_key", "") or "").strip()
    ace_time_sig = (kwargs.get("ace_time_sig", "") or "").strip()

    # --- Resolve reference audio from audio_a ---
    reference_audio_path = None
    audio_a = kwargs.get("audio_a")
    if audio_a and isinstance(audio_a, dict):
        try:
            import torchaudio
            import tempfile as _tf
            waveform = audio_a.get("waveform")
            sample_rate = audio_a.get("sample_rate", 48000)
            if waveform is not None:
                fd, ref_wav = _tf.mkstemp(suffix=".wav", prefix="ace_ref_")
                os.close(fd)
                if waveform.dim() == 3:
                    waveform = waveform.squeeze(0)  # (batch, channels, samples) → (channels, samples)
                torchaudio.save(ref_wav, waveform.cpu(), sample_rate)
                reference_audio_path = ref_wav
                logger.info("ACE-Step: Using audio_a as reference audio")
        except Exception as e:
            logger.warning("ACE-Step: Could not extract reference audio from audio_a: %s", e)

    # --- Build user metadata for LM (BPM/Key/TimeSig) ---
    user_metadata = {}
    if ace_bpm:
        user_metadata["bpm"] = ace_bpm
    if ace_key:
        user_metadata["keyscale"] = ace_key
    if ace_time_sig:
        user_metadata["timesignature"] = ace_time_sig

    # --- Determine mode: repaint existing audio or generate fresh ---
    has_audio = bool(video_metadata.primary_audio)
    audio_file = None
    duration = float(video_metadata.duration) if video_metadata.duration else 60.0

    try:
        if has_audio and not prompt.strip():
            # Repaint existing audio: extract → cover with ACE-Step
            logger.info("ACE-Step: No prompt + video has audio → repaint mode (strength=%.2f)", ace_cover_strength)
            import tempfile as _tf
            fd, src_wav = _tf.mkstemp(suffix=".wav", prefix="ace_src_")
            os.close(fd)
            _ffmpeg = _get_ffmpeg_bin()
            subprocess.run(
                [_ffmpeg, "-y", "-i", effective_video_path,
                 "-vn", "-acodec", "pcm_s16le", "-ar", "48000", "-ac", "2",
                 src_wav],
                capture_output=True, timeout=60,
            )
            if os.path.isfile(src_wav) and os.path.getsize(src_wav) > 100:
                audio_file = cover_audio(
                    audio_path=src_wav,
                    prompt="high quality music",
                    lyrics=lyrics,
                    cover_strength=ace_cover_strength,
                )
            try:
                os.unlink(src_wav)
            except OSError:
                pass
            if not audio_file:
                raise RuntimeError("ACE-Step repaint failed — no output generated")
        else:
            # Auto-generate lyrics if none provided and we have a prompt
            if not lyrics and prompt.strip():
                logger.info("ACE-Step: No manual lyrics — auto-generating from prompt")
                lyrics = _ace_generate_lyrics(
                    prompt=prompt,
                    duration=duration,
                    user_metadata=user_metadata if user_metadata else None,
                )
                if lyrics:
                    logger.info("ACE-Step: Auto-generated lyrics: %r", lyrics[:120])
                else:
                    logger.info("ACE-Step: No lyrics generated — proceeding instrumental")

            # Generate fresh music from prompt
            audio_file = generate_music_acestep(
                prompt=prompt or "background music",
                lyrics=lyrics,
                duration=duration,
                steps=ace_steps,
                cfg_scale=ace_cfg_scale,
                reference_audio=reference_audio_path,
            )
    except Exception as e:
        logger.error("ACE-Step music-only: generation failed: %s", e)
        try:
            _ace_cleanup()
        except Exception:
            pass
        raise RuntimeError(f"ACE-Step music generation failed: {e}") from e

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
        lyrics_section = ""
        if lyrics:
            lyrics_source = "manual (text_a)" if text_a.strip() else "auto-generated"
            lyrics_section = f"\nLyrics ({lyrics_source}):\n{lyrics}\n"
        analysis = (
            f"ACE-Step Music-Only Mode (no LLM) — save_only\n"
            f"Prompt: {prompt or '(repaint mode — improving existing audio)'}\n"
            f"{lyrics_section}\n"
            f"Generated music saved to: {audio_file}\n"
            f"(Audio was NOT muxed into the video)"
        )
        return (images_tensor, audio_out, output_path, "", analysis, "")

    # --- Build ffmpeg command to mux generated audio ---
    _ffmpeg = _get_ffmpeg_bin()
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

    logger.debug("ACE-Step music-only ffmpeg command: %s", " ".join(ffmpeg_cmd))
    try:
        proc = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(
                f"ACE-Step music-only mode: ffmpeg mux failed:\n{proc.stderr[-500:]}"
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
        lyrics_section = ""
        if lyrics:
            lyrics_source = "manual (text_a)" if text_a.strip() else "auto-generated"
            lyrics_section = f"\nLyrics ({lyrics_source}):\n{lyrics}\n"
        analysis = (
            f"ACE-Step Music-Only Mode (no LLM)\n"
            f"Prompt: {prompt or '(repaint mode — improving existing audio)'}\n"
            f"Audio mode: {audio_output_mode}\n"
            f"Source had audio: {has_audio}\n"
            f"{lyrics_section}\n"
            f"Generated music: {audio_file}\n"
            f"Output: {output_path}"
        )

        return (images_tensor, audio_out, output_path, cmd_log, analysis, "")
    finally:
        for tmp_path in [temp_video_from_images, temp_video_with_audio]:
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
