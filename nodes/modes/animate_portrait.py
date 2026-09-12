# coding: utf-8
"""No-LLM mode: animate portrait.

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


async def process_animate_portrait_only(
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
    driving_video: str = "",
    driving_multiplier: float = 1.0,
    relative_motion: bool = True,
    # Expression controls
    lp_rotate_pitch: float = 0.0,
    lp_rotate_yaw: float = 0.0,
    lp_rotate_roll: float = 0.0,
    lp_blink: float = 0.0,
    lp_eyebrow: float = 0.0,
    lp_wink: float = 0.0,
    lp_pupil_x: float = 0.0,
    lp_pupil_y: float = 0.0,
    lp_aaa: float = 0.0,
    lp_eee: float = 0.0,
    lp_woo: float = 0.0,
    lp_smile: float = 0.0,
    # Retargeting
    lp_retargeting_eyes: float = 1.0,
    lp_retargeting_mouth: float = 1.0,
    # Crop
    lp_crop_factor: float = 1.6,
    # Expression transfer
    lp_sample_image: str = "",
    lp_sample_ratio: float = 1.0,
    lp_sample_parts: str = "all",
    temp_video_from_images: Optional[str] = None,
    temp_video_with_audio: Optional[str] = None,
    **kwargs,
) -> tuple[torch.Tensor, dict, str, str, str, str]:
    """Run LivePortrait face animation directly without any LLM involvement.

    Animates the face in the source video/image using motion from a
    driving video, or using expression sliders alone (no driving video).
    The source is ``effective_video_path`` (from ``video_path`` or
    ``images_a``) and the driving video comes from ``video_a``.

    Returns the standard 6-tuple:
        (images_tensor, audio, output_path, command_log, analysis, mask_overlay_path)
    """
    logger.info("Animate portrait mode: starting LivePortrait")

    # Build expression kwargs dict (strip lp_ prefix)
    _expr_kwargs = dict(
        rotate_pitch=lp_rotate_pitch, rotate_yaw=lp_rotate_yaw,
        rotate_roll=lp_rotate_roll, blink=lp_blink, eyebrow=lp_eyebrow,
        wink=lp_wink, pupil_x=lp_pupil_x, pupil_y=lp_pupil_y,
        aaa=lp_aaa, eee=lp_eee, woo=lp_woo, smile=lp_smile,
    )
    _has_expr = any(v != 0.0 for v in _expr_kwargs.values())
    _has_driving = driving_video and os.path.isfile(driving_video)
    _has_sample = lp_sample_image and os.path.isfile(lp_sample_image)

    if not _has_driving and not _has_expr and not _has_sample:
        raise RuntimeError(
            "Animate portrait mode requires a driving video "
            "or at least one expression control to be set. "
            "Connect a driving video to the video_a input, "
            "or adjust the expression sliders."
        )

    # --- Import LivePortrait ---
    try:
        try:
            from ...core.liveportrait_synthesizer import (
                animate_portrait, animate_portrait_static,
            )
        except ImportError:
            from core.liveportrait_synthesizer import (  # type: ignore
                animate_portrait, animate_portrait_static,
            )
    except ImportError:
        raise RuntimeError(
            "LivePortrait is not available. "
            "Ensure all dependencies are installed and "
            "core/liveportrait_synthesizer.py exists."
        )

    # --- Build output path ---
    output_path, temp_render_dir = build_output_path(
        effective_video_path=effective_video_path,
        save_output=save_output,
        output_path=output_path,
        preview_mode=preview_mode,
    )

    # --- Run LivePortrait (in-process with offloading) ---
    animated_video = None
    try:
        if _has_driving:
            animated_video = animate_portrait(
                source_path=effective_video_path,
                driving_path=driving_video,
                driving_multiplier=driving_multiplier,
                relative_motion=relative_motion,
                retargeting_eyes=lp_retargeting_eyes,
                retargeting_mouth=lp_retargeting_mouth,
                crop_factor=lp_crop_factor,
                sample_image=lp_sample_image if _has_sample else None,
                sample_ratio=lp_sample_ratio,
                sample_parts=lp_sample_parts,
                **_expr_kwargs,
            )
        else:
            animated_video = animate_portrait_static(
                source_path=effective_video_path,
                crop_factor=lp_crop_factor,
                **_expr_kwargs,
            )
    except Exception as e:
        logger.error("Animate portrait mode: LivePortrait failed: %s", e)
        # Free VRAM on failure
        try:
            try:
                from ...core.liveportrait_synthesizer import cleanup as _lp_cleanup
            except ImportError:
                from core.liveportrait_synthesizer import cleanup as _lp_cleanup  # type: ignore
            _lp_cleanup()
        except Exception:
            pass
        raise RuntimeError(f"LivePortrait animation failed: {e}") from e

    # --- Re-encode to output path ---
    _ffmpeg = _get_ffmpeg_bin()
    effective_crf = crf if crf >= 0 else _CRF_MAP.get(quality_preset, 23)
    effective_preset = encoding_preset if encoding_preset != "auto" else _PRESET_MAP.get(quality_preset, "medium")

    ffmpeg_cmd = [
        _ffmpeg, "-y",
        "-i", animated_video,
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

    logger.debug("Animate portrait ffmpeg command: %s", " ".join(ffmpeg_cmd))
    try:
        proc = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(
                f"Animate portrait mode: ffmpeg encoding failed:\n"
                f"{proc.stderr[-500:]}"
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
            f"Animate Portrait Mode (no LLM)\n"
            f"Source: {effective_video_path}\n"
            f"Driving video: {driving_video}\n"
            f"Motion multiplier: {driving_multiplier}\n"
            f"Relative motion: {relative_motion}\n\n"
            f"Animated video: {animated_video}\n"
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
        # Clean up LivePortrait temp output
        if animated_video and os.path.exists(animated_video):
            try:
                os.remove(animated_video)
            except OSError:
                pass
        if not save_output and temp_render_dir and os.path.isdir(temp_render_dir):
            if not os.listdir(temp_render_dir):
                shutil.rmtree(temp_render_dir, ignore_errors=True)
