# coding: utf-8
"""No-LLM mode: mmaudio.

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


async def process_mmaudio_only(
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
    """Run MMAudio audio generation directly without any LLM involvement.

    Generates audio from the video (and optional text prompt) using MMAudio,
    then muxes the result into the output video.

    Args:
        prompt: Text description to guide audio generation (can be empty
                for pure video-to-audio).
        audio_output_mode: "auto"/"replace" to discard original audio,
                           "mix" to blend, "save_only" to skip muxing.

    Returns the standard 6-tuple:
        (images_tensor, audio, output_path, command_log, analysis, mask_overlay_path)
    """
    # Treat "auto" as "replace" in no-LLM context
    if audio_output_mode == "auto":
        audio_output_mode = "replace"
    logger.info(
        "MMAudio-only mode: prompt=%r, mode=%s", prompt, audio_output_mode,
    )

    # --- Import MMAudio ---
    try:
        try:
            from ...core.mmaudio_synthesizer import generate_audio
        except ImportError:
            from core.mmaudio_synthesizer import generate_audio  # type: ignore
    except ImportError:
        raise RuntimeError(
            "MMAudio is not installed. Install with: "
            "pip install --no-deps git+https://github.com/hkchengrex/MMAudio.git && "
            "pip install torchdiffeq"
        )

    # --- Build output path ---
    output_path, temp_render_dir = build_output_path(
        effective_video_path=effective_video_path,
        save_output=save_output,
        output_path=output_path,
        preview_mode=preview_mode,
    )

    # --- Generate audio via MMAudio (in-process with offloading) ---
    audio_file = None  # ensure defined for finally block
    try:
        audio_file = generate_audio(
            video_path=effective_video_path,
            prompt=prompt,
        )
    except Exception as e:
        logger.error("MMAudio-only: audio generation failed: %s", e)
        # Free VRAM from loaded MMAudio models on failure
        try:
            try:
                from ...core.mmaudio_synthesizer import cleanup as _mm_cleanup
            except ImportError:
                from core.mmaudio_synthesizer import cleanup as _mm_cleanup  # type: ignore
            _mm_cleanup()
        except Exception:
            pass
        raise RuntimeError(f"MMAudio audio generation failed: {e}") from e

    # --- Detect if source video has audio ---
    has_audio = False
    if video_metadata.primary_audio:
        has_audio = True

    # --- save_only: skip muxing, just return the audio file path ---
    if audio_output_mode == "save_only":
        output_path, temp_render_dir = build_output_path(
            effective_video_path=effective_video_path,
            save_output=save_output,
            output_path=output_path,
            preview_mode=preview_mode,
        )
        # Copy original video to output (no audio changes)
        _ffmpeg = _get_ffmpeg_bin()
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
            f"MMAudio-Only Mode (no LLM) — save_only\n"
            f"Prompt: {prompt or '(video-to-audio, no text prompt)'}\n"
            f"Generated audio saved to: {audio_file}\n"
            f"(Audio was NOT muxed into the video)"
        )
        return (images_tensor, audio_out, output_path, "", analysis, "")

    # --- Build ffmpeg command to mux generated audio ---
    _ffmpeg = _get_ffmpeg_bin()
    effective_crf = crf if crf >= 0 else _CRF_MAP.get(quality_preset, 23)
    effective_preset = encoding_preset if encoding_preset != "auto" else _PRESET_MAP.get(quality_preset, "medium")

    if audio_output_mode == "mix" and has_audio:
        # Mix generated audio with original audio
        logger.info(
            "MMAudio-only: 'mix' mode requires video re-encoding (slower than 'replace')"
        )
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
        # Replace mode (or mix with no existing audio) — pass through
        # the video codec since only the audio track is changing.
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
            # Mix mode already re-encodes — just add scale + time limit
            ffmpeg_cmd.extend(["-vf", "scale=480:trunc(ow/a/2)*2", "-t", "10"])
        else:
            # Replace mode uses -c:v copy — rebuild with re-encode for scaling
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

    logger.debug("MMAudio-only ffmpeg command: %s", " ".join(ffmpeg_cmd))
    try:
        proc = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(
                f"MMAudio-only mode: ffmpeg mux failed:\n{proc.stderr[-500:]}"
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

        # --- Build analysis string ---
        cmd_log = " ".join(ffmpeg_cmd)
        analysis = (
            f"MMAudio-Only Mode (no LLM)\n"
            f"Prompt: {prompt or '(video-to-audio, no text prompt)'}\n"
            f"Audio mode: {audio_output_mode}\n"
            f"Source had audio: {has_audio}\n\n"
            f"Generated audio: {audio_file}\n"
            f"Output: {output_path}"
        )

        return (images_tensor, audio_out, output_path, cmd_log, analysis, "")
    finally:
        # --- Cleanup temp files (always runs, even on error) ---
        for tmp_path in [temp_video_from_images, temp_video_with_audio]:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
        # Clean up generated audio file
        if audio_file and os.path.exists(audio_file):
            try:
                os.remove(audio_file)
            except OSError:
                pass
        if not save_output and temp_render_dir and os.path.isdir(temp_render_dir):
            if not os.listdir(temp_render_dir):
                shutil.rmtree(temp_render_dir, ignore_errors=True)
