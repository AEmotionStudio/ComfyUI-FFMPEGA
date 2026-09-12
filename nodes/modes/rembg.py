# coding: utf-8
"""No-LLM mode: rembg.

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


async def process_rembg_only(
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
    rembg_model: str = "bria-rmbg",
    rembg_background: str = "transparent",
    temp_video_from_images: Optional[str] = None,
    temp_video_with_audio: Optional[str] = None,
    _all_image_paths: Optional[list] = None,
    **kwargs,
) -> tuple[torch.Tensor, dict, str, str, str, str]:
    """Remove background from video/image using rembg without any LLM.

    For single images (detected by file extension or via ``_all_image_paths``),
    processes the single frame directly — outputting a PNG with alpha
    (transparent) or a composited PNG (solid background).

    For videos, uses the existing ``_f_remove_background`` skill handler to
    generate per-frame alpha masks and composite via FFmpeg filter_complex.

    Returns:
        Standard 6-tuple: (images_tensor, audio_dict, output_path,
                          ffmpeg_log, analysis_text, mask_overlay_path)
    """
    import asyncio

    logger.info("Rembg mode: model=%s, background=%s", rembg_model, rembg_background)

    is_transparent = rembg_background == "transparent"

    # --- Detect single-image input ---
    # Priority: _all_image_paths (from LoadImagePath) > file extension check
    _IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tiff", ".tif", ".gif"}
    source_image_paths: list[str] = []

    if _all_image_paths:
        source_image_paths = [p for p in _all_image_paths if os.path.isfile(p)]
    else:
        ext = os.path.splitext(effective_video_path)[1].lower()
        if ext in _IMAGE_EXTS and os.path.isfile(effective_video_path):
            source_image_paths = [effective_video_path]

    # ================================================================== #
    #  Image fast path — process N images directly, output PNGs           #
    # ================================================================== #
    if source_image_paths:
        n_images = len(source_image_paths)
        logger.info(
            "Rembg: image mode — processing %d image(s) (model=%s)",
            n_images, rembg_model,
        )

        # --- Build output path (based on first image) ---
        output_path, temp_render_dir = build_output_path(
            effective_video_path=source_image_paths[0],
            save_output=save_output,
            output_path=output_path,
            preview_mode=preview_mode,
        )
        # Force PNG output for images
        base, _ = os.path.splitext(output_path)
        output_path = base + ".png"

        try:
            from rembg import remove as rembg_remove, new_session
        except ImportError:
            raise RuntimeError(
                "rembg is not installed. Install with: "
                "pip install 'comfyui-ffmpega[masking]'"
            )

        try:
            from PIL import Image as PILImage
            import numpy as np

            # Create session once — reuse for all images
            session = new_session(rembg_model)

            bg_color_map = {
                "white": (255, 255, 255),
                "black": (0, 0, 0),
                "green": (0, 177, 64),
                "blue": (0, 0, 255),
                "red": (255, 0, 0),
                "gray": (128, 128, 128),
                "grey": (128, 128, 128),
            }

            image_tensors = []
            output_paths = []
            for idx, src_path in enumerate(source_image_paths):
                pil_img = PILImage.open(src_path).convert("RGB")

                # Run rembg — returns RGBA PIL image
                result_rgba = await asyncio.to_thread(
                    rembg_remove, pil_img, session=session,
                )

                # Build per-image output path
                if idx == 0:
                    img_output = output_path
                else:
                    img_output = f"{base}_{idx}.png"

                if is_transparent:
                    result_rgba.save(img_output, "PNG")
                else:
                    bg_rgb = bg_color_map.get(rembg_background, (0, 0, 0))
                    bg = PILImage.new("RGBA", result_rgba.size, bg_rgb + (255,))
                    composited = PILImage.alpha_composite(bg, result_rgba)
                    composited.convert("RGB").save(img_output, "PNG")

                output_paths.append(img_output)
                logger.info(
                    "Rembg: image %d/%d complete: %s", idx + 1, n_images, img_output,
                )

                # Build per-image tensor — for transparent PNGs,
                # composite onto white so the IMAGE preview looks correct.
                # (ComfyUI IMAGE type is RGB-only, alpha is always lost.)
                if is_transparent and result_rgba.mode == "RGBA":
                    white_bg = PILImage.new("RGBA", result_rgba.size, (255, 255, 255, 255))
                    preview = PILImage.alpha_composite(white_bg, result_rgba)
                    result_np = np.array(preview.convert("RGB"))
                else:
                    result_np = np.array(PILImage.open(img_output).convert("RGB"))
                image_tensors.append(
                    torch.from_numpy(result_np.astype(np.float32) / 255.0)
                )

            # Stack into batched IMAGE tensor (N, H, W, 3)
            if len(image_tensors) == 1:
                images_tensor = image_tensors[0].unsqueeze(0)
            else:
                # Resize all images to match the first image's dimensions
                target_h, target_w = image_tensors[0].shape[:2]
                resized = [image_tensors[0]]
                for t in image_tensors[1:]:
                    if t.shape[0] != target_h or t.shape[1] != target_w:
                        # Resize via PIL for quality (Lanczos)
                        t_np = (t.numpy() * 255).astype(np.uint8)
                        t_pil = PILImage.fromarray(t_np)
                        t_pil = t_pil.resize((target_w, target_h), PILImage.LANCZOS)
                        t_arr = np.array(t_pil).astype(np.float32) / 255.0
                        resized.append(torch.from_numpy(t_arr))
                    else:
                        resized.append(t)
                images_tensor = torch.stack(resized, dim=0)

            cmd_log = f"rembg {rembg_model} → {', '.join(output_paths)}"
            audio_out = {"waveform": torch.zeros(1, 1, 0), "sample_rate": 44100}

            input_list = "\n".join(f"  {p}" for p in source_image_paths)
            output_list = "\n".join(f"  {p}" for p in output_paths)
            analysis = (
                f"Rembg Background Removal ({n_images} Image{'s' if n_images > 1 else ''})\n"
                f"Model: {rembg_model}\n"
                f"Background: {rembg_background}\n"
                f"Inputs:\n{input_list}\n"
                f"Outputs:\n{output_list}"
            )

            return (images_tensor, audio_out, output_path, cmd_log, analysis, "")

        finally:
            # Cleanup temp files
            for tmp_path in [temp_video_from_images, temp_video_with_audio]:
                if tmp_path and os.path.exists(tmp_path):
                    try:
                        os.remove(tmp_path)
                    except OSError:
                        pass
            if not save_output and temp_render_dir and os.path.isdir(temp_render_dir):
                if not os.listdir(temp_render_dir):
                    shutil.rmtree(temp_render_dir, ignore_errors=True)

    # ================================================================== #
    #  Video path — per-frame mask + FFmpeg composite (existing logic)     #
    # ================================================================== #

    # --- Build output path ---
    output_path, temp_render_dir = build_output_path(
        effective_video_path=effective_video_path,
        save_output=save_output,
        output_path=output_path,
        preview_mode=preview_mode,
    )

    if is_transparent:
        base, _ = os.path.splitext(output_path)
        output_path = base + ".webm"

    mask_video_path = None
    try:
        # --- Import and call the remove_background handler ---
        try:
            from ...skills.handlers.visual import _f_remove_background
        except ImportError:
            from skills.handlers.visual import _f_remove_background  # type: ignore

        # Use a dedicated dict so we can read the mask path back reliably
        # without re-extracting from handler_params (reduces coupling).
        metadata_ref: dict = {}
        handler_params = {
            "model": rembg_model,
            "background": rembg_background,
            "_input_path": effective_video_path,
            "_metadata_ref": metadata_ref,
        }

        # Per-frame rembg inference is CPU/GPU-heavy — run in a thread
        # so the event loop stays responsive.
        result = await asyncio.to_thread(_f_remove_background, handler_params)

        # Extract mask path for cleanup (written by the handler into
        # our metadata_ref dict under "_mask_video_path").
        mask_video_path = metadata_ref.get("_mask_video_path")

        # HandlerResult is a dataclass, not a dict
        fc = result.filter_complex
        extra_opts = result.output_options

        if not fc:
            raise RuntimeError(
                "rembg handler returned no filter_complex — "
                "is rembg installed? (pip install 'comfyui-ffmpega[masking]')"
            )

        # --- Build FFmpeg command ---
        ffmpeg_bin = _get_ffmpeg_bin()

        effective_crf = crf if crf >= 0 else _CRF_MAP.get(quality_preset, 23)
        effective_preset = (
            encoding_preset if encoding_preset != "auto"
            else _PRESET_MAP.get(quality_preset, "medium")
        )

        cmd = [ffmpeg_bin, "-y", "-i", effective_video_path]

        if is_transparent:
            # VP9 with alpha — opts from handler already include codec flags
            cmd += ["-filter_complex", fc]
            cmd += extra_opts
            cmd += [output_path]
        else:
            # Solid background — standard H.264
            cmd += ["-filter_complex", fc]
            cmd += [
                "-c:v", "libx264",
                "-crf", str(effective_crf),
                "-preset", effective_preset,
                "-pix_fmt", "yuv420p",
            ]
            # Preserve audio if present
            has_audio = bool(
                video_metadata and video_metadata.get("audio_codec")
            )
            if has_audio:
                cmd += ["-c:a", "aac", "-b:a", "192k"]
            else:
                cmd += ["-an"]
            cmd += [output_path]

        logger.info("Rembg FFmpeg cmd: %s", " ".join(cmd))
        # Run FFmpeg in a thread to avoid blocking the event loop
        proc = await asyncio.to_thread(
            subprocess.run, cmd, capture_output=True, text=True,
        )
        cmd_log = proc.stdout + proc.stderr

        if proc.returncode != 0:
            raise RuntimeError(
                f"FFmpeg rembg render failed (exit {proc.returncode}):\n"
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
            removes_audio=is_transparent,
        )

        analysis = (
            f"Rembg Background Removal\n"
            f"Model: {rembg_model}\n"
            f"Background: {rembg_background}\n"
            f"Input: {effective_video_path}\n"
            f"Output: {output_path}"
        )

        return (images_tensor, audio_out, output_path, cmd_log, analysis, "")

    finally:
        # Cleanup temp files
        for tmp_path in [temp_video_from_images, temp_video_with_audio]:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
        if mask_video_path and os.path.exists(mask_video_path):
            try:
                os.remove(mask_video_path)
            except OSError:
                pass
        if not save_output and temp_render_dir and os.path.isdir(temp_render_dir):
            if not os.listdir(temp_render_dir):
                shutil.rmtree(temp_render_dir, ignore_errors=True)
