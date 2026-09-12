# coding: utf-8
"""No-LLM mode: lip sync.

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


async def process_lip_sync_only(
    # dependencies
    media_converter,
    # parameters
    effective_video_path: str,
    video_metadata,
    save_output: bool,
    output_path: str,
    preview_mode: bool,
    quality_preset: str,
    crf: int,
    encoding_preset: str,
    audio_a=None,
    temp_video_from_images: Optional[str] = None,
    temp_video_with_audio: Optional[str] = None,
    **kwargs,
) -> tuple[torch.Tensor, dict, str, str, str, str]:
    """Run MuseTalk lip sync directly without any LLM involvement.

    Converts the connected audio_a input to a WAV file and runs
    MuseTalk lip_sync in-process to synchronize lip movements.

    Requires audio_a to be connected — raises RuntimeError if missing.

    Returns the standard 6-tuple:
        (images_tensor, audio, output_path, command_log, analysis, mask_overlay_path)
    """
    logger.info("Lip sync mode: starting MuseTalk lip sync")

    if audio_a is None:
        raise RuntimeError(
            "Lip sync mode requires an audio input. "
            "Connect an audio source to the audio_a input."
        )

    # --- Convert audio_a to WAV ---
    from ..output_handler import audio_dict_to_wav
    audio_wav_path = audio_dict_to_wav(audio_a)
    if not audio_wav_path:
        raise RuntimeError(
            "Lip sync mode: failed to convert audio_a to WAV. "
            "Check that the audio input is valid."
        )

    # --- Import MuseTalk ---
    try:
        try:
            from ...core.musetalk_synthesizer import lip_sync
        except ImportError:
            from core.musetalk_synthesizer import lip_sync  # type: ignore
    except ImportError:
        raise RuntimeError(
            "MuseTalk lip sync is not available. "
            "All dependencies should be built into ComfyUI — "
            "check that core/musetalk_synthesizer.py exists."
        )

    # --- Build output path ---
    output_path, temp_render_dir = build_output_path(
        effective_video_path=effective_video_path,
        save_output=save_output,
        output_path=output_path,
        preview_mode=preview_mode,
    )

    # --- Run MuseTalk lip sync (in-process) ---
    lip_synced_video = None
    try:
        lip_synced_video = lip_sync(
            video_path=effective_video_path,
            audio_path=audio_wav_path,
            batch_size=8,
            face_index=-1,
        )
    except Exception as e:
        logger.error("Lip sync mode: MuseTalk failed: %s", e)
        raise RuntimeError(f"MuseTalk lip sync failed: {e}") from e

    # --- Re-encode to output path ---
    _ffmpeg = _get_ffmpeg_bin()
    effective_crf = crf if crf >= 0 else _CRF_MAP.get(quality_preset, 23)
    effective_preset = encoding_preset if encoding_preset != "auto" else _PRESET_MAP.get(quality_preset, "medium")

    ffmpeg_cmd = [
        _ffmpeg, "-y",
        "-i", lip_synced_video,
        "-c:v", "libx264",
        "-crf", str(effective_crf),
        "-preset", effective_preset,
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "192k",
    ]

    if preview_mode:
        ffmpeg_cmd.extend(["-vf", "scale=480:trunc(ow/a/2)*2", "-t", "10"])

    ffmpeg_cmd.append(output_path)

    logger.debug("Lip sync ffmpeg command: %s", " ".join(ffmpeg_cmd))
    try:
        proc = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(
                f"Lip sync mode: ffmpeg encoding failed:\n{proc.stderr[-500:]}"
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
            f"Lip Sync Mode (no LLM)\n"
            f"Audio source: connected audio_a\n"
            f"Audio WAV: {audio_wav_path}\n"
            f"Lip-synced video: {lip_synced_video}\n\n"
            f"Output: {output_path}"
        )

        return (images_tensor, audio_out, output_path, cmd_log, analysis, "")
    finally:
        # --- Cleanup temp files (always runs, even on error) ---
        for tmp_path in [temp_video_from_images, temp_video_with_audio, audio_wav_path]:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
        # Clean up MuseTalk temp output
        if lip_synced_video and os.path.exists(lip_synced_video):
            try:
                os.remove(lip_synced_video)
            except OSError:
                pass
        if not save_output and temp_render_dir and os.path.isdir(temp_render_dir):
            if not os.listdir(temp_render_dir):
                shutil.rmtree(temp_render_dir, ignore_errors=True)
