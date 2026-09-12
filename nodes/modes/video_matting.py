# coding: utf-8
"""No-LLM mode: video matting.

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
    tempfile,
    torch,
)


async def process_video_matting_only(
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
    matting_output: str = "foreground",
    matting_background: str = "green",
    matting_max_size: int = 0,
    mask_output_type: str = "black_white",
    sam3_device: str = "gpu",
    sam3_max_objects: int = 5,
    sam3_det_threshold: float = 0.7,
    mask_points: str = "",
    temp_video_from_images: Optional[str] = None,
    temp_video_with_audio: Optional[str] = None,
    **kwargs,
) -> tuple[torch.Tensor, dict, str, str, str, str]:
    """Run MatAnyone2 video matting directly without any LLM involvement.

    If no manual mask is provided (via image_a tensor or image_path_a file path),
    generates a first-frame mask from SAM3 using the prompt text. Then runs
    MatAnyone2 for production-quality alpha matting with temporal coherence.

    Returns the standard 6-tuple:
        (images_tensor, audio, output_path, command_log, analysis, mask_overlay_path)
    """
    import asyncio

    logger.info("Video Matting mode: prompt='%s', output_type=%s", prompt, matting_output)

    # If effective_video_path is a temp video created from IMAGE tensors,
    # prefer the original video_path for matting (full frame count).
    # IMAGE tensors are often a subset of frames (e.g. 25 out of 192).
    if temp_video_from_images and effective_video_path == temp_video_from_images:
        original_video = kwargs.get("video_path", "")
        if original_video and isinstance(original_video, str) and os.path.isfile(original_video.strip()):
            logger.info(
                "Video Matting: using original video '%s' instead of IMAGE-derived temp '%s'",
                original_video.strip(), effective_video_path,
            )
            effective_video_path = original_video.strip()

    # --- Build output path ---
    output_path, temp_render_dir = build_output_path(
        effective_video_path=effective_video_path,
        save_output=save_output,
        output_path=output_path,
        preview_mode=preview_mode,
    )
    output_dir = os.path.dirname(output_path)

    # --- Generate or locate the first-frame mask ---
    mask_path = None
    mask_source = "auto (SAM3)"

    # Check if a manual mask was provided via image_a
    image_a = kwargs.get("image_a")
    if image_a is not None:
        # image_a is a torch tensor (B, H, W, C) — save first frame as grayscale PNG
        try:
            import numpy as np
            from PIL import Image as PILImage

            if hasattr(image_a, "cpu"):
                mask_np = image_a[0].cpu().numpy()
            else:
                mask_np = np.array(image_a[0])

            # Convert to grayscale if needed
            if mask_np.ndim == 3 and mask_np.shape[-1] >= 3:
                mask_np = np.mean(mask_np[:, :, :3], axis=-1)

            # Normalize to 0-255
            if mask_np.max() <= 1.0:
                mask_np = (mask_np * 255).astype(np.uint8)
            else:
                mask_np = mask_np.astype(np.uint8)

            mask_tmp = tempfile.NamedTemporaryFile(suffix="_matting_mask.png", delete=False)
            PILImage.fromarray(mask_np, mode="L").save(mask_tmp.name)
            mask_path = mask_tmp.name
            mask_source = "manual (image_a)"
            logger.info("Video Matting: using manual mask from image_a → %s", mask_path)
        except Exception as e:
            logger.warning("Video Matting: failed to extract mask from image_a: %s — falling back to SAM3", e)
            mask_path = None

    # Check if a mask file path was provided via image_path_a
    if mask_path is None:
        image_path_a = kwargs.get("image_path_a", "")
        if image_path_a and isinstance(image_path_a, str) and image_path_a.strip() and os.path.isfile(image_path_a.strip()):
            mask_path = image_path_a.strip()
            mask_source = "manual (image_path_a)"
            logger.info("Video Matting: using mask from image_path_a → %s", mask_path)

    # Auto-generate mask from SAM3 if no manual mask
    if mask_path is None:
        # Parse point prompts from the JS point selector
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
                        logger.info("Video Matting: using %d point prompt(s) (src %dx%d)",
                                    len(point_coords), point_src_w, point_src_h)
            except (ValueError, TypeError) as exc:
                logger.warning("Video Matting: failed to parse mask_points JSON: %s", exc)

        has_points = bool(point_coords and point_labels)
        has_prompt = bool(prompt and prompt.strip())

        if not has_points and not has_prompt:
            raise RuntimeError(
                "Video Matting: no mask provided and no prompt text or point prompts "
                "for SAM3 auto-masking. Either connect a mask to image_a, provide a "
                "text prompt, or use the point selector to click on the subject."
            )

        # Extract first frame from video
        import cv2
        import numpy as np
        from PIL import Image as PILImage

        cap = cv2.VideoCapture(effective_video_path)
        ret, first_frame = cap.read()
        cap.release()
        if not ret:
            raise RuntimeError(f"Video Matting: failed to read first frame from {effective_video_path}")

        first_frame_rgb = cv2.cvtColor(first_frame, cv2.COLOR_BGR2RGB)

        # Save first frame to temp file (both APIs expect a file path)
        first_frame_tmp = tempfile.NamedTemporaryFile(suffix="_first_frame.png", delete=False)
        PILImage.fromarray(first_frame_rgb).save(first_frame_tmp.name)

        try:
            if has_points:
                # Point-based masking (click-to-select)
                logger.info("Video Matting: generating mask via SAM3 point prompts (%d points)",
                            len(point_coords))
                try:
                    try:
                        from ...core.sam3_masker import mask_image_with_points as sam3_mask_points
                    except ImportError:
                        from core.sam3_masker import mask_image_with_points as sam3_mask_points  # type: ignore
                except ImportError:
                    raise RuntimeError(
                        "Video Matting: SAM3 not available for point-based masking. "
                        "Either install SAM3 or connect a manual mask to image_a."
                    )

                sam3_result = await asyncio.to_thread(
                    sam3_mask_points,
                    first_frame_tmp.name,
                    point_coords,
                    point_labels,
                    point_src_w,
                    point_src_h,
                    sam3_device,
                )
            else:
                # Text-based masking (prompt)
                logger.info("Video Matting: generating first-frame mask via SAM3 for '%s'", prompt.strip())
                try:
                    try:
                        from ...core.sam3_masker import mask_image_with_text as sam3_mask_image
                    except ImportError:
                        from core.sam3_masker import mask_image_with_text as sam3_mask_image  # type: ignore
                except ImportError:
                    raise RuntimeError(
                        "Video Matting: SAM3 not available for auto-masking. "
                        "Either install SAM3 or connect a manual mask to image_a."
                    )

                sam3_result = await asyncio.to_thread(
                    sam3_mask_image,
                    first_frame_tmp.name,
                    prompt.strip(),
                    sam3_device,
                )

            # sam3 result → numpy array (H, W) with 255=masked, 0=unmasked
            if isinstance(sam3_result, PILImage.Image):
                mask_np = np.array(sam3_result.convert("L"))
            else:
                mask_np = np.array(sam3_result)
                if mask_np.ndim == 3:
                    mask_np = mask_np[:, :, 0]

            mask_tmp = tempfile.NamedTemporaryFile(suffix="_sam3_mask.png", delete=False)
            PILImage.fromarray(mask_np, mode="L").save(mask_tmp.name)
            mask_path = mask_tmp.name
            logger.info("Video Matting: SAM3 mask generated → %s", mask_path)
        except Exception as e:
            raise RuntimeError(
                f"Video Matting: SAM3 mask generation failed: {e}. "
                "Try providing a manual mask via image_a instead."
            ) from e
        finally:
            # Clean up temp first frame
            try:
                os.unlink(first_frame_tmp.name)
            except OSError:
                pass

    # --- Run MatAnyone2 matting ---
    try:
        try:
            from ...core.matanyone2_synthesizer import process_video as matanyone2_process
        except ImportError:
            from core.matanyone2_synthesizer import process_video as matanyone2_process  # type: ignore

        max_size = matting_max_size if matting_max_size > 0 else -1

        matting_results = await asyncio.to_thread(
            matanyone2_process,
            video_path=effective_video_path,
            mask_path=mask_path,
            output_dir=output_dir,
            output_type=matting_output,
            background_color=matting_background,
            max_size=max_size,
        )
    except Exception as e:
        raise RuntimeError(f"Video Matting: MatAnyone2 processing failed: {e}") from e

    # --- Determine the primary output video ---
    if "foreground" in matting_results:
        matted_video = matting_results["foreground"]
    elif "alpha" in matting_results:
        matted_video = matting_results["alpha"]
    else:
        raise RuntimeError("Video Matting: no output produced")

    # Copy the matted video to the expected output path
    if matted_video != output_path:
        _ffmpeg = _get_ffmpeg_bin()
        effective_crf = crf if crf >= 0 else _CRF_MAP.get(quality_preset, 23)
        effective_preset = encoding_preset if encoding_preset != "auto" else _PRESET_MAP.get(quality_preset, "medium")

        ffmpeg_cmd = [
            _ffmpeg, "-y",
            "-i", matted_video,
            "-c:v", "libx264",
            "-crf", str(effective_crf),
            "-preset", effective_preset,
            "-pix_fmt", "yuv420p",
            output_path,
        ]

        if preview_mode:
            ffmpeg_cmd = [
                _ffmpeg, "-y",
                "-i", matted_video,
                "-vf", "scale=480:trunc(ow/a/2)*2",
                "-t", "10",
                "-c:v", "libx264",
                "-crf", str(effective_crf),
                "-preset", effective_preset,
                "-pix_fmt", "yuv420p",
                output_path,
            ]

        proc = await asyncio.to_thread(
            subprocess.run, ffmpeg_cmd, capture_output=True, text=True
        )
        if proc.returncode != 0:
            raise RuntimeError(
                f"Video Matting: FFmpeg re-encode failed:\n{proc.stderr[-500:]}"
            )

    # --- Collect frame/audio output ---
    unique_id = str(kwargs.get("unique_id", ""))
    hidden_prompt = kwargs.get("hidden_prompt") or {}
    images_tensor, audio_out = collect_frame_output(
        media_converter=media_converter,
        output_path=output_path,
        unique_id=unique_id,
        hidden_prompt=hidden_prompt,
        removes_audio=True,  # matting removes audio
    )

    # --- Output the mask image so the user can see what was generated ---
    # Always return the SAM3/manual mask PNG; fall back to alpha video if available
    mask_overlay_path = mask_path or ""
    if not mask_overlay_path and "alpha" in matting_results:
        mask_overlay_path = matting_results["alpha"]

    # Generate colored overlay if requested
    if mask_overlay_path and mask_output_type == "colored_overlay" and os.path.isfile(mask_overlay_path):
        try:
            import cv2
            import numpy as np
            from PIL import Image as PILImage

            # Read the mask
            mask_img = np.array(PILImage.open(mask_overlay_path).convert("L"))

            # Read the first frame from the video
            cap = cv2.VideoCapture(effective_video_path)
            ret, first_frame = cap.read()
            cap.release()

            if ret:
                first_frame_rgb = cv2.cvtColor(first_frame, cv2.COLOR_BGR2RGB)

                # Resize mask to match frame if needed
                if mask_img.shape[:2] != first_frame_rgb.shape[:2]:
                    mask_img = cv2.resize(mask_img, (first_frame_rgb.shape[1], first_frame_rgb.shape[0]), interpolation=cv2.INTER_NEAREST)

                # Create colored overlay (SAM3-style blue-green)
                overlay_color = np.array([30, 180, 230], dtype=np.uint8)  # teal
                binary = (mask_img > 127).astype(np.uint8)
                overlay = first_frame_rgb.copy()
                mask_region = binary.astype(bool)
                overlay[mask_region] = (
                    overlay[mask_region].astype(np.float32) * 0.5
                    + overlay_color.astype(np.float32) * 0.5
                ).astype(np.uint8)

                # Draw contour
                contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                overlay_bgr = cv2.cvtColor(overlay, cv2.COLOR_RGB2BGR)
                cv2.drawContours(overlay_bgr, contours, -1, (0, 255, 255), 2)
                overlay = cv2.cvtColor(overlay_bgr, cv2.COLOR_BGR2RGB)

                # Save colored overlay
                overlay_tmp = tempfile.NamedTemporaryFile(suffix="_mask_overlay.png", delete=False)
                PILImage.fromarray(overlay).save(overlay_tmp.name)
                mask_overlay_path = overlay_tmp.name
                logger.info("Video Matting: colored mask overlay → %s", mask_overlay_path)
        except Exception as e:
            logger.warning("Video Matting: colored overlay generation failed: %s — using raw mask", e)

    # --- Build analysis string ---
    cmd_log = f"matanyone2 process_video → {matted_video}"
    analysis = (
        f"Video Matting Mode (MatAnyone2, no LLM)\n"
        f"Mask source: {mask_source}\n"
        f"Output type: {matting_output}\n"
        f"Background: {matting_background}\n"
        f"Max size: {matting_max_size or 'unlimited'}\n"
        f"Output: {output_path}\n"
        f"Alpha: {matting_results.get('alpha', 'not generated')}"
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
