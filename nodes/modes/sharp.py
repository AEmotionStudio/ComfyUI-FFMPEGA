# coding: utf-8
"""No-LLM mode: sharp.

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


async def process_sharp_only(
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
    image_a=None,
    temp_video_from_images: Optional[str] = None,
    temp_video_with_audio: Optional[str] = None,
    **kwargs,
) -> tuple[torch.Tensor, dict, str, str, str, str]:
    """Run Apple SHARP 3D Gaussian view synthesis without any LLM involvement.

    Takes a single image from ``image_a`` (ComfyUI IMAGE tensor) and:
    1. Predicts 3D Gaussian splat parameters (<1s)
    2. Renders a camera trajectory video via gsplat (CUDA only)
    3. Optionally exports the .ply file

    ⚠️ Model weights are Apple ML Research License (non-commercial/research only).

    Returns the standard 6-tuple:
        (images_tensor, audio, output_path, command_log, analysis, mask_overlay_path)
    """
    # --- Extract SHARP parameters from kwargs ---
    sharp_trajectory = str(kwargs.pop("sharp_trajectory", "rotate_forward"))
    sharp_num_frames = int(kwargs.pop("sharp_num_frames", 60))
    sharp_max_disparity = float(kwargs.pop("sharp_max_disparity", 0.08))
    sharp_max_zoom = float(kwargs.pop("sharp_max_zoom", 0.15))
    sharp_save_ply = str(kwargs.pop("sharp_save_ply", "false")).lower() in ("true", "1", "yes")
    sharp_device = str(kwargs.pop("sharp_device", "auto"))

    logger.info(
        "SHARP mode: trajectory=%s, frames=%d, disparity=%.3f, zoom=%.3f, ply=%s, device=%s",
        sharp_trajectory, sharp_num_frames, sharp_max_disparity, sharp_max_zoom,
        sharp_save_ply, sharp_device,
    )

    # --- Extract input image from image_a tensor or image_path_a ---
    # Accept from tensor (image_a) or file path (image_path_a from LoadImagePath)
    image_path_a = kwargs.pop("image_path_a", "")
    if image_a is None or (hasattr(image_a, "shape") and image_a.shape[0] == 0):
        if image_path_a and isinstance(image_path_a, str) and image_path_a.strip() and os.path.isfile(image_path_a.strip()):
            from PIL import Image as _PILImage
            import numpy as np
            pil_img = _PILImage.open(image_path_a.strip()).convert("RGB")
            image_a = np.array(pil_img)
            logger.info("SHARP: loaded image from image_path_a → %s", image_path_a.strip())
        else:
            raise RuntimeError(
                "SHARP mode requires an image connected to the image_a or image_path_a input. "
                "Connect an image source (Load Image, LoadImagePath, etc.)."
            )

    # Convert ComfyUI IMAGE tensor (B, H, W, C) float32 [0,1] → numpy HWC uint8
    if isinstance(image_a, torch.Tensor):
        if image_a.dim() == 4:
            image_np = (image_a[0].cpu().numpy() * 255.0).clip(0, 255).astype(np.uint8)
        elif image_a.dim() == 3:
            image_np = (image_a.cpu().numpy() * 255.0).clip(0, 255).astype(np.uint8)
        else:
            raise RuntimeError(f"Unexpected image_a tensor shape: {image_a.shape}")
    elif isinstance(image_a, np.ndarray):
        if image_a.max() <= 1.0:
            image_np = (image_a * 255.0).clip(0, 255).astype(np.uint8)
        else:
            image_np = image_a.astype(np.uint8)
    else:
        raise RuntimeError(f"Unsupported image_a type: {type(image_a)}")

    # Ensure RGB (3 channels)
    if image_np.ndim == 2:
        image_np = np.stack([image_np] * 3, axis=-1)
    elif image_np.shape[-1] == 4:
        image_np = image_np[..., :3]

    logger.info("SHARP: input image shape: %s", image_np.shape)

    # --- Import SHARP synthesizer ---
    try:
        try:
            from ...core.sharp_synthesizer import run_sharp_pipeline, TRAJECTORY_TYPES
        except ImportError:
            from core.sharp_synthesizer import run_sharp_pipeline, TRAJECTORY_TYPES  # type: ignore
    except ImportError:
        raise RuntimeError(
            "SHARP is not available. Install with:\n"
            "  pip install --no-deps git+https://github.com/apple/ml-sharp.git\n"
            "See requirements-optional.txt for details."
        )

    if sharp_trajectory not in TRAJECTORY_TYPES:
        logger.warning(
            "SHARP: unknown trajectory '%s', falling back to 'rotate_forward'",
            sharp_trajectory,
        )
        sharp_trajectory = "rotate_forward"

    # --- Build output path ---
    output_path, temp_render_dir = build_output_path(
        effective_video_path=effective_video_path,
        save_output=save_output,
        output_path=output_path,
        preview_mode=preview_mode,
    )

    # --- Resolve PLY output path ---
    ply_output_path = None
    if sharp_save_ply:
        try:
            import folder_paths  # type: ignore[import-not-found]
            out_dir = folder_paths.get_output_directory()
        except ImportError:
            out_dir = os.path.dirname(output_path)
        ply_basename = os.path.splitext(os.path.basename(output_path))[0] + ".ply"
        ply_output_path = os.path.join(out_dir, ply_basename)

    # --- Run SHARP pipeline (in-process with GPU) ---
    frames_dir = None
    ply_path = None
    try:
        frames_dir, ply_path = run_sharp_pipeline(
            image_np=image_np,
            output_video_path=output_path,
            trajectory_type=sharp_trajectory,
            num_frames=sharp_num_frames,
            max_disparity=sharp_max_disparity,
            max_zoom=sharp_max_zoom,
            device=sharp_device,
            export_ply=sharp_save_ply,
            ply_output_path=ply_output_path,
        )
    except Exception as e:
        logger.error("SHARP mode: inference failed: %s", e)
        raise RuntimeError(f"SHARP inference failed: {e}") from e

    if not frames_dir:
        # CPU/MPS mode — only PLY was exported, no video rendered
        raise RuntimeError(
            "SHARP video rendering requires a CUDA GPU (gsplat limitation). "
            f"PLY file exported to: {ply_path}" if ply_path else
            "SHARP requires CUDA for video rendering. Enable sharp_save_ply for PLY-only mode on CPU."
        )

    # --- Encode frames through FFmpeg with user quality settings ---
    _ffmpeg = _get_ffmpeg_bin()
    effective_crf = crf if crf >= 0 else _CRF_MAP.get(quality_preset, 23)
    effective_preset = encoding_preset if encoding_preset != "auto" else _PRESET_MAP.get(quality_preset, "medium")

    # Detect FPS: use 30 fps for rendered trajectories
    render_fps = 30

    try:
        from ...core.video import encode_opts as _eo
    except (ImportError, Exception):
        from core.video import encode_opts as _eo  # type: ignore

    # PNG frames are RGB, so this is the same conversion the tensor encoders
    # do.  The old `-color_range pc` tag disagreed with the limited-range
    # samples swscale actually wrote.
    _colour = _eo.color_filter(_eo.DEFAULT_COLOR_POLICY)
    ffmpeg_cmd = [
        _ffmpeg, "-y",
        "-framerate", str(render_fps),
        "-i", os.path.join(frames_dir, "frame_%05d.png"),
        "-c:v", "libx264",
        "-crf", str(effective_crf),
        "-preset", effective_preset,
        "-pix_fmt", "yuv420p",
        "-an",  # No audio for rendered trajectories
    ]

    _vf = [f for f in (
        "scale=480:trunc(ow/a/2)*2" if preview_mode else "", _colour,
    ) if f]
    if _vf:
        ffmpeg_cmd.extend(["-vf", ",".join(_vf)])
    if preview_mode:
        ffmpeg_cmd.extend(["-t", "10"])

    ffmpeg_cmd.append(output_path)

    logger.debug("SHARP ffmpeg command: %s", " ".join(ffmpeg_cmd))
    proc = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"SHARP mode: ffmpeg encoding failed:\n{proc.stderr[-500:]}"
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
            f"SHARP Mode (no LLM) — 3D Gaussian View Synthesis\n"
            f"⚠️ Model weights: Apple ML Research License (research/non-commercial only)\n\n"
            f"Trajectory: {sharp_trajectory}\n"
            f"Frames: {sharp_num_frames}\n"
            f"Max disparity: {sharp_max_disparity}\n"
            f"Max zoom: {sharp_max_zoom}\n"
            f"Device: {sharp_device}\n"
            f"Image size: {image_np.shape[1]}×{image_np.shape[0]}\n\n"
            f"Output: {output_path}"
        )
        if ply_path:
            analysis += f"\nPLY export: {ply_path}"

        return (images_tensor, audio_out, output_path, cmd_log, analysis, "")
    finally:
        # --- Cleanup temp files ---
        import shutil as _shutil
        for tmp_path in [temp_video_from_images, temp_video_with_audio]:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
        # Clean up rendered PNG frames (no longer needed after FFmpeg encode)
        if frames_dir and os.path.isdir(frames_dir):
            try:
                _shutil.rmtree(frames_dir, ignore_errors=True)
            except OSError:
                pass
