# coding: utf-8
"""No-LLM mode: normalcrafter.

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


async def process_normalcrafter_only(
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
    normalcrafter_max_res: str = "auto",
    normalcrafter_window_size: int = 14,
    normalcrafter_process_length: int = -1,
    normalcrafter_target_fps: int = -1,
    normalcrafter_seed: int = 42,
    temp_video_from_images: Optional[str] = None,
    temp_video_with_audio: Optional[str] = None,
    **kwargs,
) -> tuple[torch.Tensor, dict, str, str, str, str]:
    """Run NormalCrafter video normal map generation without LLM involvement.

    Produces temporally consistent surface normal map videos using video
    diffusion priors (NormalCrafter).

    Args:
        normalcrafter_max_res: Maximum processing resolution. One of
            'auto', '1024', '768', '512'.  'auto' detects GPU VRAM and
            picks a safe resolution.
        normalcrafter_window_size: Temporal window size for sliding inference.
        normalcrafter_process_length: Max frames to process (-1 = all).
        normalcrafter_target_fps: Target FPS (-1 = use original).
        normalcrafter_seed: Random seed for reproducibility.

    Returns the standard 6-tuple:
        (images_tensor, audio, output_path, command_log, analysis, mask_overlay_path)
    """
    logger.info(
        "NormalCrafter mode: max_res=%s, window=%d, seed=%d",
        normalcrafter_max_res, normalcrafter_window_size, normalcrafter_seed,
    )

    # --- Import NormalCrafter synthesizer ---
    try:
        try:
            from ...core.normalcrafter_synthesizer import run_normalcrafter, cleanup as _nc_cleanup
        except ImportError:
            from core.normalcrafter_synthesizer import run_normalcrafter, cleanup as _nc_cleanup  # type: ignore
    except ImportError:
        raise RuntimeError(
            "NormalCrafter is not available. "
            "Install with: pip install --no-deps "
            "git+https://github.com/Binyr/NormalCrafter.git"
        )

    # --- Build output path ---
    output_path, temp_render_dir = build_output_path(
        effective_video_path=effective_video_path,
        save_output=save_output,
        output_path=output_path,
        preview_mode=preview_mode,
    )

    # --- Run NormalCrafter (in-process with GPU offloading) ---
    nc_output = None
    try:
        nc_output = run_normalcrafter(
            video_path=effective_video_path,
            max_res=normalcrafter_max_res,
            window_size=normalcrafter_window_size,
            process_length=normalcrafter_process_length,
            target_fps=normalcrafter_target_fps,
            seed=normalcrafter_seed,
        )
    except Exception as e:
        logger.error("NormalCrafter mode: inference failed: %s", e)
        try:
            _nc_cleanup()
        except Exception:
            pass
        raise RuntimeError(f"NormalCrafter inference failed: {e}") from e

    # --- Re-encode to output path ---
    _ffmpeg = _get_ffmpeg_bin()
    effective_crf = crf if crf >= 0 else _CRF_MAP.get(quality_preset, 23)
    effective_preset = encoding_preset if encoding_preset != "auto" else _PRESET_MAP.get(quality_preset, "medium")

    ffmpeg_cmd = [
        _ffmpeg, "-y",
        "-i", nc_output,
        "-c:v", "libx264",
        "-crf", str(effective_crf),
        "-preset", effective_preset,
        "-pix_fmt", "yuv420p",
        "-an",  # NormalCrafter output has no audio
    ]

    if preview_mode:
        ffmpeg_cmd.extend(["-vf", "scale=480:trunc(ow/a/2)*2", "-t", "10"])

    ffmpeg_cmd.append(output_path)

    logger.debug("NormalCrafter ffmpeg command: %s", " ".join(ffmpeg_cmd))
    proc = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"NormalCrafter mode: ffmpeg encoding failed:\n{proc.stderr[-500:]}"
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
        analysis = (
            f"NormalCrafter Mode (no LLM)\n"
            f"Temporally consistent video surface normals\n"
            f"Max resolution: {normalcrafter_max_res}\n"
            f"Window size: {normalcrafter_window_size}\n"
            f"Seed: {normalcrafter_seed}\n\n"
            f"Source: {effective_video_path}\n"
            f"NormalCrafter output: {nc_output}\n"
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
        # Clean up NormalCrafter temp output
        if nc_output and os.path.exists(nc_output):
            try:
                os.remove(nc_output)
            except OSError:
                pass
        if not save_output and temp_render_dir and os.path.isdir(temp_render_dir):
            if not os.listdir(temp_render_dir):
                shutil.rmtree(temp_render_dir, ignore_errors=True)
