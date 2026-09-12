# coding: utf-8
"""No-LLM mode: marigold.

Moved verbatim from nodes/nollm_modes.py, which is now a re-export facade.
"""

from __future__ import annotations

from ._shared import (
    Optional,
    Path,
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


async def process_marigold_only(
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
    marigold_output_type: str = "depth",
    marigold_colormap: str = "Spectral",
    marigold_num_steps: int = 4,
    marigold_ensemble_size: int = 1,
    temp_video_from_images: Optional[str] = None,
    temp_video_with_audio: Optional[str] = None,
    **kwargs,
) -> tuple[torch.Tensor, dict, str, str, str, str]:
    """Run Marigold dense vision analysis directly without any LLM involvement.

    Produces depth maps, surface normals, or intrinsic image decomposition
    (appearance or lighting) from the input image or video.

    Args:
        marigold_output_type: One of 'depth', 'normals', 'appearance', 'lighting'.
        marigold_num_steps: Number of denoising steps (1-50).
        marigold_ensemble_size: Number of ensemble predictions (1-10).

    Returns the standard 6-tuple:
        (images_tensor, audio, output_path, command_log, analysis, mask_overlay_path)
    """
    logger.info(
        "Marigold mode: type=%s, steps=%d, ensemble=%d",
        marigold_output_type, marigold_num_steps, marigold_ensemble_size,
    )

    # --- Import Marigold synthesizer ---
    try:
        try:
            from ...core.marigold_synthesizer import run_marigold, cleanup as _mg_cleanup
        except ImportError:
            from core.marigold_synthesizer import run_marigold, cleanup as _mg_cleanup  # type: ignore
    except ImportError:
        raise RuntimeError(
            "Marigold is not available. "
            "Ensure diffusers >= 0.28.0 is installed and "
            "core/marigold_synthesizer.py exists."
        )

    # --- Build output path ---
    output_path, temp_render_dir = build_output_path(
        effective_video_path=effective_video_path,
        save_output=save_output,
        output_path=output_path,
        preview_mode=preview_mode,
    )

    # --- Run Marigold (in-process with GPU offloading) ---
    marigold_output = None
    try:
        marigold_output = run_marigold(
            input_path=effective_video_path,
            output_type=marigold_output_type,
            colormap=marigold_colormap,
            num_steps=marigold_num_steps,
            ensemble_size=marigold_ensemble_size,
        )
    except Exception as e:
        logger.error("Marigold mode: inference failed: %s", e)
        # Free VRAM on failure
        try:
            _mg_cleanup()
        except Exception:
            pass
        raise RuntimeError(f"Marigold inference failed: {e}") from e

    # --- Re-encode to output path ---
    _ffmpeg = _get_ffmpeg_bin()
    effective_crf = crf if crf >= 0 else _CRF_MAP.get(quality_preset, 23)
    effective_preset = encoding_preset if encoding_preset != "auto" else _PRESET_MAP.get(quality_preset, "medium")

    # Determine if output is image or video
    ext = os.path.splitext(marigold_output)[1].lower()
    is_image = ext in (".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".webp")

    if is_image:
        # For images, just copy to output path (change extension)
        import shutil as _shutil
        output_path = str(Path(output_path).with_suffix(ext))
        _shutil.copy2(marigold_output, output_path)
        cmd_log = f"cp {marigold_output} {output_path}"
    else:
        # For video, re-encode
        ffmpeg_cmd = [
            _ffmpeg, "-y",
            "-i", marigold_output,
            "-c:v", "libx264",
            "-crf", str(effective_crf),
            "-preset", effective_preset,
            "-pix_fmt", "yuv420p",
            "-an",  # Marigold output has no audio
        ]

        if preview_mode:
            ffmpeg_cmd.extend(["-vf", "scale=480:trunc(ow/a/2)*2", "-t", "10"])

        ffmpeg_cmd.append(output_path)

        logger.debug("Marigold ffmpeg command: %s", " ".join(ffmpeg_cmd))
        proc = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(
                f"Marigold mode: ffmpeg encoding failed:\n{proc.stderr[-500:]}"
            )
        cmd_log = " ".join(ffmpeg_cmd)

    try:
        # --- Collect frame/audio output ---
        unique_id = str(kwargs.get("unique_id", ""))
        hidden_prompt = kwargs.get("hidden_prompt") or {}
        images_tensor, audio_out = collect_frame_output(
            media_converter=media_converter,
            output_path=output_path,
            unique_id=unique_id,
            hidden_prompt=hidden_prompt,
            removes_audio=True,
        )

        # --- Build analysis string ---
        _type_desc = {
            "depth": "Monocular depth estimation",
            "normals": "Surface normals estimation",
            "appearance": "Intrinsic decomposition (albedo, roughness, metallicity)",
            "lighting": "Intrinsic decomposition (albedo, shading, residual)",
        }
        analysis = (
            f"Marigold Mode (no LLM)\n"
            f"Output type: {marigold_output_type} — "
            f"{_type_desc.get(marigold_output_type, marigold_output_type)}\n"
            f"Denoising steps: {marigold_num_steps}\n"
            f"Ensemble size: {marigold_ensemble_size}\n\n"
            f"Source: {effective_video_path}\n"
            f"Marigold output: {marigold_output}\n"
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
        # Clean up Marigold temp output
        if marigold_output and os.path.exists(marigold_output):
            try:
                os.remove(marigold_output)
            except OSError:
                pass
        if not save_output and temp_render_dir and os.path.isdir(temp_render_dir):
            if not os.listdir(temp_render_dir):
                shutil.rmtree(temp_render_dir, ignore_errors=True)
