# coding: utf-8
"""No-LLM mode: sam3.

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
    json,
    logger,
    os,
    shutil,
    subprocess,
    torch,
)


async def process_sam3_only(
    # dependencies
    media_converter,
    # parameters
    prompt: str,
    effective_video_path: str,
    video_metadata,
    save_output: bool,
    output_path: str,
    preview_mode: bool,
    quality_preset: str,
    crf: int,
    encoding_preset: str,
    sam3_device: str,
    sam3_max_objects: int,
    sam3_det_threshold: float,
    mask_points: str,
    temp_video_from_images: Optional[str],
    temp_video_with_audio: Optional[str],
    **kwargs,
) -> tuple[torch.Tensor, dict, str, str, str, str]:
    """Run SAM3 masking directly without any LLM involvement.

    Calls ``mask_video_subprocess`` directly — the main video output is
    a clean copy of the source (no effects applied).  The SAM3 mask is
    output via the ``mask_overlay_path`` (colored overlay or raw B&W).

    Returns the standard 6-tuple:
        (images_tensor, audio, output_path, command_log, analysis, mask_overlay_path)
    """
    logger.info("SAM3-only mode: using prompt as text target → '%s'", prompt)

    # --- Build output path ---
    output_path, temp_render_dir = build_output_path(
        effective_video_path=effective_video_path,
        save_output=save_output,
        output_path=output_path,
        preview_mode=preview_mode,
    )

    # --- Parse point prompts (from the JS point selector) ---
    point_coords = None
    point_labels = None
    point_src_w = 0
    point_src_h = 0
    if mask_points and mask_points.strip():
        try:
            pt_data = json.loads(mask_points)
            if isinstance(pt_data, dict):
                point_coords = pt_data.get("points")
                point_labels = pt_data.get("labels")
                point_src_w = int(pt_data.get("image_width", 0))
                point_src_h = int(pt_data.get("image_height", 0))
                if point_coords and point_labels:
                    logger.info("SAM3-only: using %d point prompt(s) (src %dx%d)",
                                len(point_coords), point_src_w, point_src_h)
        except (ValueError, TypeError) as exc:
            logger.warning("SAM3-only: failed to parse mask_points JSON: %s", exc)

    # --- Run SAM3 directly (no auto_mask handler, no effects) ---
    try:
        from ...core.sam3_masker import mask_video_subprocess as sam3_mask_video
    except ImportError:
        from core.sam3_masker import mask_video_subprocess as sam3_mask_video  # type: ignore

    try:
        mask_video_path = sam3_mask_video(
            video_path=effective_video_path,
            prompt=prompt,
            device=sam3_device,
            max_objects=sam3_max_objects,
            det_threshold=sam3_det_threshold,
            points=point_coords,
            labels=point_labels,
            point_src_width=point_src_w,
            point_src_height=point_src_h,
        )
    except Exception as e:
        logger.error("SAM3-only: mask generation failed: %s", e)
        raise RuntimeError(f"SAM3 mask generation failed: {e}") from e

    # --- Copy source video through as the main output (no effects) ---
    effective_crf = crf if crf >= 0 else _CRF_MAP.get(quality_preset, 23)
    effective_preset = encoding_preset if encoding_preset != "auto" else _PRESET_MAP.get(quality_preset, "medium")

    _ffmpeg = _get_ffmpeg_bin()
    ffmpeg_cmd = [
        _ffmpeg, "-y",
        "-i", effective_video_path,
        "-c:v", "libx264",
        "-crf", str(effective_crf),
        "-preset", effective_preset,
        "-pix_fmt", "yuv420p",
        "-c:a", "copy",
        output_path,
    ]

    if preview_mode:
        # Insert scale + duration limit before output path
        ffmpeg_cmd = [
            _ffmpeg, "-y",
            "-i", effective_video_path,
            "-vf", "scale=480:trunc(ow/a/2)*2",
            "-t", "10",
            "-c:v", "libx264",
            "-crf", str(effective_crf),
            "-preset", effective_preset,
            "-pix_fmt", "yuv420p",
            "-c:a", "copy",
            output_path,
        ]

    logger.debug("SAM3-only passthrough command: %s", " ".join(ffmpeg_cmd))
    proc = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"SAM3-only mode: video passthrough failed:\n{proc.stderr[-500:]}"
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

    # --- Generate mask overlay ---
    mask_overlay_path = ""
    if mask_video_path and os.path.isfile(mask_video_path):
        mask_type = kwargs.get("mask_output_type", "colored_overlay")
        if mask_type == "black_white":
            mask_overlay_path = mask_video_path
            logger.info("SAM3-only: B&W mask video → %s", mask_overlay_path)
        else:
            try:
                try:
                    from ...core.sam3_masker import generate_mask_overlay
                except ImportError:
                    from core.sam3_masker import generate_mask_overlay  # type: ignore
                mask_overlay_path = generate_mask_overlay(
                    video_path=effective_video_path,
                    mask_video_path=mask_video_path,
                )
                logger.info("SAM3-only: colored overlay → %s", mask_overlay_path)
            except Exception as e:
                logger.warning("SAM3-only: mask overlay generation failed: %s", e)

    # --- Build analysis string ---
    cmd_log = " ".join(ffmpeg_cmd)
    analysis = (
        f"SAM3-Only Mode (no LLM)\n"
        f"Text target: {prompt}\n"
        f"Device: {sam3_device}\n"
        f"Max objects: {sam3_max_objects}\n"
        f"Detection threshold: {sam3_det_threshold}\n"
        f"Point prompts: {'yes' if mask_points else 'no'}\n\n"
        f"Main output: clean passthrough (no effects)\n"
        f"Mask output: {mask_overlay_path or mask_video_path or 'none'}"
    )

    # --- Cleanup temp files ---
    for tmp_path in [temp_video_from_images, temp_video_with_audio]:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
    if not save_output and temp_render_dir and os.path.isdir(temp_render_dir):
        if not os.listdir(temp_render_dir):
            shutil.rmtree(temp_render_dir, ignore_errors=True)

    return (images_tensor, audio_out, output_path, cmd_log, analysis, mask_overlay_path)
