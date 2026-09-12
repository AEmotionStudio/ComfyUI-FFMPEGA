# coding: utf-8
"""No-LLM mode: flux klein.

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


async def process_flux_klein_only(
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
    flux_smoothing: str = "none",
    image_a=None,
    _all_image_paths=None,
    temp_video_from_images: Optional[str] = None,
    temp_video_with_audio: Optional[str] = None,
    **kwargs,
) -> tuple[torch.Tensor, dict, str, str, str, str]:
    """Run FLUX Klein editing directly without any LLM involvement.

    Auto-detects whether the input is a single image or a video:
    - **Image**: calls ``edit_single_image()`` for a one-shot edit
    - **Video**: calls ``edit_video()`` in maskless (full-frame) mode,
      applying the prompt to every frame via Klein's reference conditioning

    The prompt is sent directly to FLUX Klein as the edit instruction.

    Returns the standard 6-tuple:
        (images_tensor, audio, output_path, command_log, analysis, mask_overlay_path)
    """
    logger.info("FLUX Klein mode: prompt=%r", prompt)

    flux_image_source = kwargs.get("flux_image_source", False)
    flux_klein_steps = kwargs.get("flux_klein_steps", 4)
    flux_klein_guidance = kwargs.get("flux_klein_guidance", 1.0)
    flux_klein_seed = kwargs.get("flux_klein_seed", 42)
    flux_klein_width = kwargs.get("flux_klein_width", 1024)
    flux_klein_height = kwargs.get("flux_klein_height", 1024)
    flux_klein_model = kwargs.get("flux_klein_model", "4b")

    if not prompt or not prompt.strip():
        raise RuntimeError(
            "FLUX Klein mode requires a prompt describing the desired edit. "
            "Enter your edit instruction in the prompt field (e.g. "
            "'a person wearing a chrome bodysuit')."
        )

    # --- Image-source mode: use first image input as source ---
    # When flux_image_source is on, the first connected image becomes
    # effective_video_path and the rest become references.
    _temp_source_image = None  # track for cleanup
    if flux_image_source:
        if image_a is not None:
            # Convert image_a tensor → temp PNG for use as source
            from PIL import Image as _PILImage
            import numpy as _np

            if hasattr(image_a, 'shape') and len(image_a.shape) == 4:
                arr = (image_a[0].cpu().numpy() * 255).clip(0, 255).astype(_np.uint8)
            elif hasattr(image_a, 'shape') and len(image_a.shape) == 3:
                arr = (image_a.cpu().numpy() * 255).clip(0, 255).astype(_np.uint8)
            else:
                arr = None

            if arr is not None:
                _temp_source_image = os.path.join(
                    tempfile.mkdtemp(prefix="fk_src_"), "source.png"
                )
                _PILImage.fromarray(arr).save(_temp_source_image)
                effective_video_path = _temp_source_image
                image_a = None  # consumed — don't also use as reference
                logger.info("FLUX Klein image-source mode: using image_a tensor as source → %s", _temp_source_image)
            else:
                logger.warning("FLUX Klein image-source mode: image_a has unexpected shape, falling back to video_path")
        elif _all_image_paths and os.path.isfile(_all_image_paths[0]):
            # Use image_path_a as source, rest as references
            effective_video_path = _all_image_paths[0]
            _all_image_paths = _all_image_paths[1:]
            logger.info("FLUX Klein image-source mode: using image_path_a as source → %s", effective_video_path)
        else:
            logger.warning(
                "FLUX Klein image-source mode is on but no image inputs connected. "
                "Falling back to video_path as source."
            )

    # --- Import FLUX Klein editor ---
    try:
        try:
            from ...core.flux_klein_editor import (
                edit_single_image,
                edit_video,
                cleanup as _fk_cleanup,
            )
        except ImportError:
            from core.flux_klein_editor import (  # type: ignore
                edit_single_image,
                edit_video,
                cleanup as _fk_cleanup,
            )
    except ImportError:
        raise RuntimeError(
            "FLUX Klein is not available. "
            "Ensure diffusers >= 0.32.0 is installed and "
            "core/flux_klein_editor.py exists."
        )

    # --- Build output path ---
    output_path, temp_render_dir = build_output_path(
        effective_video_path=effective_video_path,
        save_output=save_output,
        output_path=output_path,
        preview_mode=preview_mode,
    )

    # --- Detect image vs video ---
    ext = os.path.splitext(effective_video_path)[1].lower()
    is_image = ext in (".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".webp")

    # NOTE: VRAM is freed internally by flux_klein_editor when loading
    # the pipeline via _vram_utils.free_for_module() — no manual clearing
    # needed here.

    # --- Convert image_a tensor → PIL reference images ---
    reference_images = None
    if image_a is not None:
        from PIL import Image as _PILImage
        import numpy as _np
        reference_images = []
        if hasattr(image_a, 'shape') and len(image_a.shape) == 4:
            # Batch of images (B, H, W, C) — ComfyUI IMAGE tensor
            for idx in range(image_a.shape[0]):
                arr = (image_a[idx].cpu().numpy() * 255).clip(0, 255).astype(_np.uint8)
                reference_images.append(_PILImage.fromarray(arr))
        elif hasattr(image_a, 'shape') and len(image_a.shape) == 3:
            # Single image (H, W, C)
            arr = (image_a.cpu().numpy() * 255).clip(0, 255).astype(_np.uint8)
            reference_images.append(_PILImage.fromarray(arr))
        if not reference_images:
            reference_images = None
        else:
            logger.info("FLUX Klein: using %d reference image(s) from image_a", len(reference_images))

    # --- Load image_path_a / image_path_b / ... as PIL references ---
    if _all_image_paths:
        from PIL import Image as _PILImage
        if reference_images is None:
            reference_images = []
        for img_path in _all_image_paths:
            if os.path.isfile(img_path):
                reference_images.append(_PILImage.open(img_path).convert("RGB"))
                logger.info("FLUX Klein: loaded reference image from %s", img_path)
        if not reference_images:
            reference_images = None

    edited_path = None
    try:
        if is_image:
            # Single-image edit
            logger.info("FLUX Klein: single-image mode")
            img_output = os.path.splitext(output_path)[0] + ".png"
            edited_path = edit_single_image(
                image_path=effective_video_path,
                prompt=prompt,
                output_path=img_output,
                seed=flux_klein_seed,
                reference_images=reference_images,
                num_steps=flux_klein_steps,
                guidance_scale=flux_klein_guidance,
                width=flux_klein_width,
                height=flux_klein_height,
                model=flux_klein_model,
            )
            output_path = edited_path
            cmd_log = f"flux_klein edit_single_image → {output_path}"
        else:
            # Video edit — full-frame (no mask)
            logger.info("FLUX Klein: full-frame video mode (no mask)")
            edited_path = edit_video(
                video_path=effective_video_path,
                mask_video_path=None,
                prompt=prompt,
                output_path=output_path,
                mode="edit",
                smoothing=flux_smoothing,
                reference_images=reference_images,
                seed=flux_klein_seed,
                num_steps=flux_klein_steps,
                guidance_scale=flux_klein_guidance,
                width=flux_klein_width,
                height=flux_klein_height,
                model=flux_klein_model,
            )
            output_path = edited_path

            # Re-encode for preview if needed
            if preview_mode:
                _ffmpeg = _get_ffmpeg_bin()
                effective_crf = crf if crf >= 0 else _CRF_MAP.get(quality_preset, 23)
                effective_preset = (
                    encoding_preset if encoding_preset != "auto"
                    else _PRESET_MAP.get(quality_preset, "medium")
                )
                preview_path = output_path + ".preview.mp4"
                ffmpeg_cmd = [
                    _ffmpeg, "-y",
                    "-i", output_path,
                    "-vf", "scale=480:trunc(ow/a/2)*2",
                    "-t", "10",
                    "-c:v", "libx264",
                    "-crf", str(effective_crf),
                    "-preset", effective_preset,
                    "-pix_fmt", "yuv420p",
                    "-an",
                    preview_path,
                ]
                proc = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
                if proc.returncode == 0:
                    os.replace(preview_path, output_path)
                else:
                    logger.warning(
                        "FLUX Klein preview downscale failed: %s",
                        proc.stderr[-300:],
                    )

            cmd_log = f"flux_klein edit_video (maskless) → {output_path}"

    except Exception as e:
        logger.error("FLUX Klein mode failed: %s", e)
        try:
            _fk_cleanup()
        except Exception:
            pass
        raise RuntimeError(f"FLUX Klein editing failed: {e}") from e

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
        input_type = "Image" if is_image else "Video"
        analysis = (
            f"FLUX Klein Mode (no LLM)\n"
            f"Input type: {input_type}\n"
            f"Prompt: {prompt}\n"
            f"Mask: none (full-frame edit)\n"
            f"Smoothing: {flux_smoothing}\n\n"
            f"Source: {effective_video_path}\n"
            f"Output: {output_path}"
        )

        return (images_tensor, audio_out, output_path, cmd_log, analysis, "")
    finally:
        # --- Cleanup temp files (always runs, even on error) ---
        for tmp_path in [temp_video_from_images, temp_video_with_audio, _temp_source_image]:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
        # Clean up temp source image directory
        if _temp_source_image:
            _src_dir = os.path.dirname(_temp_source_image)
            if _src_dir and os.path.isdir(_src_dir):
                shutil.rmtree(_src_dir, ignore_errors=True)
        if not save_output and temp_render_dir and os.path.isdir(temp_render_dir):
            if not os.listdir(temp_render_dir):
                shutil.rmtree(temp_render_dir, ignore_errors=True)
