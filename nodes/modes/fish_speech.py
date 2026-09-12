# coding: utf-8
"""No-LLM mode: fish speech.

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
    torch,
)


async def process_fish_speech_only(
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
    """Run Fish Speech TTS directly without any LLM involvement.

    Generates speech audio from text using Fish Speech S2 Pro,
    then muxes the result into the output video.

    Args:
        prompt: Text to synthesize. Supports inline tags like ``[whisper]``,
                ``[excited]``, ``<|speaker:0|>``, etc.
        audio_output_mode: "auto"/"replace" to discard original audio,
                           "mix" to blend, "save_only" to skip muxing.

    Returns the standard 6-tuple:
        (images_tensor, audio, output_path, command_log, analysis, mask_overlay_path)
    """
    # Treat "auto" as "replace" in no-LLM context
    if audio_output_mode == "auto":
        audio_output_mode = "replace"
    logger.info(
        "Fish Speech TTS mode: prompt=%r, mode=%s", prompt[:80], audio_output_mode,
    )

    # --- Import Fish Speech synthesizer ---
    try:
        try:
            from ...core.fish_speech_synthesizer import generate_speech
        except ImportError:
            from core.fish_speech_synthesizer import generate_speech  # type: ignore
    except ImportError:
        raise RuntimeError(
            "Fish Speech is not available. Install with: "
            "pip install --no-deps fish-speech"
        )

    # --- Build output path ---
    output_path, temp_render_dir = build_output_path(
        effective_video_path=effective_video_path,
        save_output=save_output,
        output_path=output_path,
        preview_mode=preview_mode,
    )

    # --- Extract Fish Speech widget params ---
    fish_model_variant = kwargs.pop("fish_model_variant", "bf16")
    fish_voice = kwargs.pop("fish_voice", "")
    fish_emotion = kwargs.pop("fish_emotion", "(none)")
    fish_temperature = kwargs.pop("fish_temperature", 0.7)
    fish_top_p = kwargs.pop("fish_top_p", 0.7)
    fish_repetition_penalty = kwargs.pop("fish_repetition_penalty", 1.2)

    # Normalize emotion tag
    emotion_tag = ""
    if fish_emotion and fish_emotion != "(none)":
        emotion_tag = fish_emotion

    # Resolve voice references — priority: audio inputs > fish_voice library
    # Supports multi-speaker: audio_a → speaker:0, audio_b → speaker:1
    reference_audio = None
    reference_audios = None
    voice_name = None

    # 1. Check for connected audio inputs (direct reference audio)
    from ..output_handler import audio_dict_to_wav
    audio_a = kwargs.pop("audio_a", None)
    audio_b = kwargs.pop("audio_b", None)

    ref_paths = []  # list of (wav_path, label) tuples
    for label, audio_dict in [("speaker_0", audio_a), ("speaker_1", audio_b)]:
        if audio_dict is not None and isinstance(audio_dict, dict):
            try:
                wav_path = audio_dict_to_wav(audio_dict)
                if wav_path and os.path.isfile(wav_path):
                    ref_paths.append((wav_path, label))
                    logger.info(
                        "Fish Speech: %s reference voice → %s", label, wav_path,
                    )
            except Exception as e:
                logger.warning(
                    "Fish Speech: could not extract %s for voice cloning: %s",
                    label, e,
                )

    if len(ref_paths) >= 2:
        # Multi-speaker mode
        reference_audios = ref_paths
        logger.info("Fish Speech: multi-speaker mode with %d references", len(ref_paths))
    elif len(ref_paths) == 1:
        # Single speaker mode
        reference_audio = ref_paths[0][0]

    # 2. Fallback: voice library name or direct path
    if not reference_audio and not reference_audios and fish_voice and fish_voice.strip():
        voice_str = fish_voice.strip()
        if os.path.isfile(voice_str):
            reference_audio = voice_str
        else:
            voice_name = voice_str

    logger.info(
        "Fish Speech params: variant=%s, voice=%s, emotion=%s, "
        "temperature=%.2f, top_p=%.2f, rep_penalty=%.2f",
        fish_model_variant, fish_voice or "(default)",
        fish_emotion, fish_temperature, fish_top_p, fish_repetition_penalty,
    )

    # --- Generate speech ---
    audio_file = None
    try:
        audio_file = generate_speech(
            text=prompt,
            reference_audio=reference_audio,
            reference_audios=reference_audios,
            voice_name=voice_name,
            emotion_tag=emotion_tag,
            variant=fish_model_variant,
            temperature=fish_temperature,
            top_p=fish_top_p,
            repetition_penalty=fish_repetition_penalty,
        )
    except Exception as e:
        logger.error("Fish Speech TTS: generation failed: %s", e)
        try:
            try:
                from ...core.fish_speech_synthesizer import cleanup as _fs_cleanup
            except ImportError:
                from core.fish_speech_synthesizer import cleanup as _fs_cleanup  # type: ignore
            _fs_cleanup()
        except Exception:
            pass
        raise RuntimeError(f"Fish Speech generation failed: {e}") from e

    # --- Detect if source video has audio ---
    has_audio = False
    has_real_video = bool(effective_video_path and effective_video_path.strip()
                         and os.path.isfile(effective_video_path))
    if has_real_video and video_metadata and video_metadata.primary_audio:
        has_audio = True

    # --- Audio-only output (no video connected) or save_only ---
    if audio_output_mode == "save_only" or not has_real_video:
        # Just output the generated audio file directly
        shutil.copy2(audio_file, output_path)
        unique_id = str(kwargs.get("unique_id", ""))
        hidden_prompt = kwargs.get("hidden_prompt") or {}
        images_tensor, audio_out = collect_frame_output(
            media_converter=media_converter,
            output_path=output_path,
            unique_id=unique_id,
            hidden_prompt=hidden_prompt,
            removes_audio=False,
        )
        mode_label = "save_only" if audio_output_mode == "save_only" else "audio-only"
        analysis = (
            f"Fish Speech TTS Mode (no LLM) — {mode_label}\n"
            f"Text: {prompt[:100] or '(no text)'}{'...' if len(prompt) > 100 else ''}\n"
            f"Voice: {fish_voice or '(default)'}\n"
            f"Emotion: {fish_emotion}\n"
            f"Generated audio: {audio_file}\n"
            f"Output: {output_path}"
        )
        return (images_tensor, audio_out, output_path, "", analysis, "")

    # --- Build ffmpeg command to mux generated audio into real video ---
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

    logger.debug("Fish Speech TTS ffmpeg command: %s", " ".join(ffmpeg_cmd))
    try:
        proc = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(
                f"Fish Speech TTS mode: ffmpeg mux failed:\n{proc.stderr[-500:]}"
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
            f"Fish Speech TTS Mode (no LLM)\n"
            f"Text: {prompt[:100] or '(no text)'}{'...' if len(prompt) > 100 else ''}\n"
            f"Voice: {fish_voice or '(default)'}\n"
            f"Emotion: {fish_emotion}\n"
            f"Audio mode: {audio_output_mode}\n"
            f"Source had audio: {has_audio}\n\n"
            f"Generated audio: {audio_file}\n"
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
