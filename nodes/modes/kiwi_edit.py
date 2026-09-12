# coding: utf-8
"""No-LLM mode: kiwi edit.

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


async def process_kiwi_edit_only(
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
    image_a=None,
    _all_image_paths=None,
    temp_video_from_images: Optional[str] = None,
    temp_video_with_audio: Optional[str] = None,
    **kwargs,
) -> tuple[torch.Tensor, dict, str, str, str, str]:
    """Run Kiwi-Edit video editing directly without any LLM involvement.

    Auto-detects model variant based on available inputs:
    - Prompt only → instruct-only
    - Reference image only → reference-only
    - Both → instruct-reference

    The prompt is sent directly to Kiwi-Edit as the edit instruction.
    Reference images come from image_a input or image_path_a/b/c.

    Returns the standard 6-tuple:
        (images_tensor, audio, output_path, command_log, analysis, mask_overlay_path)
    """
    logger.info("Kiwi-Edit mode: prompt=%r", prompt)

    kiwi_model = kwargs.get("kiwi_model", "auto")
    kiwi_precision = kwargs.get("kiwi_precision", "auto")
    kiwi_resolution = kwargs.get("kiwi_resolution", "640")
    kiwi_width = kwargs.get("kiwi_width", 640)
    kiwi_height = kwargs.get("kiwi_height", 640)
    kiwi_max_frames = kwargs.get("kiwi_max_frames", 0)
    if int(kiwi_max_frames) <= 0:
        # Auto: match input video frame count
        input_frames = None
        if video_metadata and video_metadata.primary_video:
            input_frames = video_metadata.primary_video.nb_frames
        if input_frames and input_frames > 0:
            kiwi_max_frames = min(input_frames, 161)  # Cap at model max
            logger.info("Kiwi-Edit auto max_frames=%d (from input video)", kiwi_max_frames)
        else:
            kiwi_max_frames = 81  # Fallback default
            logger.info("Kiwi-Edit auto max_frames=%d (fallback, no frame count in metadata)", kiwi_max_frames)
    kiwi_steps = kwargs.get("kiwi_steps", 50)
    kiwi_guidance = kwargs.get("kiwi_guidance", 5.0)
    kiwi_block_swap = kwargs.get("kiwi_block_swap", 0)
    kiwi_long_video = kwargs.get("kiwi_long_video", False)
    kiwi_seed = kwargs.get("kiwi_seed", 0)
    kiwi_flow_shift = kwargs.get("kiwi_flow_shift", 5.0)
    kiwi_task_type = kwargs.get("kiwi_task_type", "auto")
    kiwi_scheduler = kwargs.get("kiwi_scheduler", "unipc")


    # --- Import Kiwi-Edit synthesizer ---
    try:
        try:
            from ...core.kiwi_edit_synthesizer import (
                edit_video as _kiwi_edit,
                cleanup as _kiwi_cleanup,
                auto_select_variant,
            )
        except ImportError:
            from core.kiwi_edit_synthesizer import (  # type: ignore
                edit_video as _kiwi_edit,
                cleanup as _kiwi_cleanup,
                auto_select_variant,
            )
    except ImportError:
        raise RuntimeError(
            "Kiwi-Edit is not available. "
            "Ensure diffusers >= 0.32.0 is installed and "
            "core/kiwi_edit_synthesizer.py exists."
        )

    # --- Build output path ---
    output_path, temp_render_dir = build_output_path(
        effective_video_path=effective_video_path,
        save_output=save_output,
        output_path=output_path,
        preview_mode=preview_mode,
    )

    if not effective_video_path or not os.path.isfile(effective_video_path):
        raise RuntimeError("No valid video provided for Kiwi-Edit")

    # --- Convert image_a tensor → PIL reference images ---
    reference_images = None
    if image_a is not None:
        from PIL import Image as _PILImage
        import numpy as _np
        reference_images = []
        if hasattr(image_a, 'shape') and len(image_a.shape) == 4:
            for idx in range(image_a.shape[0]):
                arr = (image_a[idx].cpu().numpy() * 255).clip(0, 255).astype(_np.uint8)
                reference_images.append(_PILImage.fromarray(arr))
        elif hasattr(image_a, 'shape') and len(image_a.shape) == 3:
            arr = (image_a.cpu().numpy() * 255).clip(0, 255).astype(_np.uint8)
            reference_images.append(_PILImage.fromarray(arr))
        if not reference_images:
            reference_images = None
        else:
            logger.info("Kiwi-Edit: using %d reference image(s) from image_a", len(reference_images))

    # --- Load image_path_a / image_path_b / ... as PIL references ---
    ref_image_paths = None
    if _all_image_paths:
        ref_image_paths = [p for p in _all_image_paths if os.path.isfile(p)]
        if ref_image_paths:
            logger.info("Kiwi-Edit: %d reference image path(s)", len(ref_image_paths))

    # --- Determine variant for analysis ---
    variant = auto_select_variant(prompt, reference_images or [], kiwi_model)

    edited_path = None
    try:
        edited_path = _kiwi_edit(
            video_path=effective_video_path,
            prompt=prompt if prompt and prompt.strip() else None,
            ref_image_paths=ref_image_paths,
            ref_images_pil=reference_images,
            output_path=output_path,
            model_variant=kiwi_model,
            resolution_preset=kiwi_resolution,
            custom_width=int(kiwi_width),
            custom_height=int(kiwi_height),
            max_frames=int(kiwi_max_frames),
            steps=int(kiwi_steps),
            guidance_scale=float(kiwi_guidance),
            seed=int(kiwi_seed),
            precision=kiwi_precision,
            long_video=bool(kiwi_long_video),
            block_swap_blocks=int(kiwi_block_swap),
            flow_shift=float(kiwi_flow_shift),
            task_type=str(kiwi_task_type),
            scheduler=str(kiwi_scheduler),
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
                    "Kiwi-Edit preview downscale failed: %s",
                    proc.stderr[-300:],
                )

        cmd_log = f"kiwi_edit edit_video ({variant}) → {output_path}"

    except Exception as e:
        logger.error("Kiwi-Edit mode failed: %s", e)
        try:
            _kiwi_cleanup()
        except Exception:
            pass
        raise RuntimeError(f"Kiwi-Edit editing failed: {e}") from e

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
        has_prompt = bool(prompt and prompt.strip())
        has_ref = bool(reference_images or ref_image_paths)
        analysis = (
            f"Kiwi-Edit Mode (no LLM)\n"
            f"Model variant: {variant}\n"
            f"Precision: {kiwi_precision}\n"
            f"Resolution: {kiwi_resolution}\n"
            f"Max frames: {kiwi_max_frames}\n"
            f"Steps: {kiwi_steps}\n"
            f"Guidance: {kiwi_guidance}\n"
            f"Seed: {kiwi_seed}\n"
            f"Flow shift: {kiwi_flow_shift}\n"
            f"Task type: {kiwi_task_type}\n"
            f"Scheduler: {kiwi_scheduler}\n"

            f"Long video: {kiwi_long_video}\n"
            f"Prompt: {prompt or '(none)'}\n"
            f"Reference images: {'yes' if has_ref else 'no'}\n\n"
            f"Source: {effective_video_path}\n"
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
        if not save_output and temp_render_dir and os.path.isdir(temp_render_dir):
            if not os.listdir(temp_render_dir):
                shutil.rmtree(temp_render_dir, ignore_errors=True)
