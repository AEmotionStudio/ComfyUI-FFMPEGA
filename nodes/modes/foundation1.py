# coding: utf-8
"""No-LLM mode: foundation1.

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


async def process_foundation1_only(
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
    """Run Foundation-1 sample generation directly without any LLM involvement.

    Generates a music sample/loop from a text prompt using Foundation-1,
    then muxes the result into the output video.

    Args:
        prompt: Text description to guide sample generation (or preset name).
        audio_output_mode: "auto"/"replace" to discard original audio,
                           "mix" to blend, "save_only" to skip muxing.

    Returns the standard 6-tuple:
        (images_tensor, audio, output_path, command_log, analysis, mask_overlay_path)
    """
    # Treat "auto" as "replace" in no-LLM context
    if audio_output_mode == "auto":
        audio_output_mode = "replace"
    logger.info(
        "Foundation-1 sample-only mode: prompt=%r, mode=%s", prompt, audio_output_mode,
    )

    # --- Import Foundation-1 ---
    try:
        try:
            from ...core.foundation1_synthesizer import generate_sample
        except ImportError:
            from core.foundation1_synthesizer import generate_sample  # type: ignore
    except ImportError:
        raise RuntimeError(
            "Foundation-1 is not available. Install with: "
            "pip install --no-deps stable-audio-tools"
        )

    # --- Build output path ---
    output_path, temp_render_dir = build_output_path(
        effective_video_path=effective_video_path,
        save_output=save_output,
        output_path=output_path,
        preview_mode=preview_mode,
    )

    # --- Extract Foundation-1 widget params ---
    f1_preset = kwargs.pop("f1_preset", "none")
    f1_instrument = kwargs.pop("f1_instrument", "none")
    f1_fx = kwargs.pop("f1_fx", "none")
    f1_structure = kwargs.pop("f1_structure", "none")
    f1_negative_prompt = kwargs.pop("f1_negative_prompt", "")
    f1_bpm_str = kwargs.pop("f1_bpm", "auto")
    f1_bars_str = kwargs.pop("f1_bars", "auto")
    f1_key = kwargs.pop("f1_key", "")
    f1_duration = kwargs.pop("f1_duration", 0.0)
    f1_steps = kwargs.pop("f1_steps", 100)
    f1_cfg_scale = kwargs.pop("f1_cfg_scale", 7.0)
    f1_style_transfer = kwargs.pop("f1_style_transfer", False)
    f1_noise_level = kwargs.pop("f1_noise_level", 0.7)
    audio_a = kwargs.pop("audio_a", None)

    # Convert string dropdowns to ints
    f1_bpm = int(f1_bpm_str) if f1_bpm_str != "auto" else 0
    f1_bars = int(f1_bars_str) if f1_bars_str != "auto" else 0

    # Build enhanced prompt from instrument/FX/structure dropdowns
    prompt_parts = []
    if f1_instrument and f1_instrument != "none":
        # Capitalize for Foundation-1's tag format
        prompt_parts.append(f1_instrument.replace("_", " ").title())
    if f1_fx and f1_fx != "none":
        # Convert underscored names to Foundation-1 tag format
        prompt_parts.append(f1_fx.replace("_", " ").title())
    if f1_structure and f1_structure != "none":
        prompt_parts.append(f1_structure.replace("_", " ").title())
    if prompt_parts:
        # Prepend instrument/FX/structure tags to user prompt
        tags = ", ".join(prompt_parts)
        prompt = f"{tags}, {prompt}" if prompt.strip() else tags

    logger.info(
        "Foundation-1 params: preset=%s, instrument=%s, fx=%s, structure=%s, "
        "bpm=%s, bars=%s, key=%r, duration=%.1f, steps=%d, cfg=%.1f, "
        "style_transfer=%s, noise_level=%.2f",
        f1_preset, f1_instrument, f1_fx, f1_structure,
        f1_bpm, f1_bars, f1_key, f1_duration, f1_steps, f1_cfg_scale,
        f1_style_transfer, f1_noise_level,
    )

    # --- Generate audio via Foundation-1 ---
    audio_file = None
    try:
        if f1_style_transfer and audio_a is not None:
            # Style transfer mode: restyle connected audio_a
            try:
                try:
                    from ...core.foundation1_synthesizer import style_transfer_audio
                except ImportError:
                    from core.foundation1_synthesizer import style_transfer_audio  # type: ignore
            except ImportError:
                raise RuntimeError(
                    "Foundation-1 style_transfer_audio not available. "
                    "Ensure foundation1_synthesizer.py is up-to-date."
                )

            # Extract audio_a waveform to a temp wav file for the synthesizer
            import tempfile as _tf
            import numpy as _np
            from scipy.io import wavfile as _wavfile

            waveform = audio_a.get("waveform")  # shape: [batch, channels, samples]
            sr = audio_a.get("sample_rate", 44100)
            if waveform is None:
                raise RuntimeError("audio_a has no waveform — connect an audio source")

            # Write to temp file
            tmp_audio = _tf.NamedTemporaryFile(suffix=".wav", delete=False)
            tmp_audio.close()
            audio_np = waveform.squeeze(0).cpu().numpy()  # [channels, samples]
            if audio_np.ndim == 2:
                audio_np = audio_np.T  # → [samples, channels]
            audio_np = _np.clip(audio_np, -1.0, 1.0).astype(_np.float32)
            _wavfile.write(tmp_audio.name, int(sr), audio_np)

            audio_file = style_transfer_audio(
                input_audio_path=tmp_audio.name,
                prompt=prompt,
                negative_prompt=f1_negative_prompt,
                preset=f1_preset if f1_preset != "none" else "",
                bpm=f1_bpm,
                bars=f1_bars,
                key=f1_key,
                init_noise_level=f1_noise_level,
                steps=f1_steps,
                cfg_scale=f1_cfg_scale,
            )

            # Clean up temp input
            try:
                os.remove(tmp_audio.name)
            except OSError:
                pass
        else:
            # Standard generation mode
            audio_file = generate_sample(
                prompt=prompt,
                negative_prompt=f1_negative_prompt,
                preset=f1_preset if f1_preset != "none" else "",
                bpm=f1_bpm,
                bars=f1_bars,
                key=f1_key,
                duration=f1_duration if f1_duration > 0 else None,
                steps=f1_steps,
                cfg_scale=f1_cfg_scale,
            )
    except Exception as e:
        logger.error("Foundation-1 sample-only: generation failed: %s", e)
        try:
            try:
                from ...core.foundation1_synthesizer import cleanup as _f1_cleanup
            except ImportError:
                from core.foundation1_synthesizer import cleanup as _f1_cleanup  # type: ignore
            _f1_cleanup()
        except Exception:
            pass
        raise RuntimeError(f"Foundation-1 sample generation failed: {e}") from e

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
            f"Foundation-1 Sample-Only Mode (no LLM) — {mode_label}\n"
            f"Prompt: {prompt or '(no text prompt)'}\n"
            f"Generated sample: {audio_file}\n"
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

    logger.debug("Foundation-1 sample-only ffmpeg command: %s", " ".join(ffmpeg_cmd))
    try:
        proc = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(
                f"Foundation-1 sample-only mode: ffmpeg mux failed:\n{proc.stderr[-500:]}"
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
            f"Foundation-1 Sample-Only Mode (no LLM)\n"
            f"Prompt: {prompt or '(no text prompt)'}\n"
            f"Audio mode: {audio_output_mode}\n"
            f"Source had audio: {has_audio}\n\n"
            f"Generated sample: {audio_file}\n"
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
