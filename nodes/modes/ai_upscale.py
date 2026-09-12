# coding: utf-8
"""No-LLM mode: ai upscale.

Moved verbatim from nodes/nollm_modes.py, which is now a re-export facade.
"""

from __future__ import annotations

from ._shared import (
    Optional,
    build_output_path,
    collect_frame_output,
    logger,
    os,
    shutil,
    torch,
)


async def process_ai_upscale_only(
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
    upscale_model: str = "realesrgan_x4plus",
    upscale_scale: int = 4,
    tile_size: int = 512,
    blockswap_blocks: int = 0,
    seedvr_resolution: int = 1080,
    rtx_quality: str = "ULTRA",
    vae_tiling: bool = True,
    vae_tile_preset: str = "auto",
    vae_tile_size: int = 512,
    vae_tile_overlap: int = 64,
    flashvsr_processing: str = "whole",
    flashvsr_frame_window: int = 0,
    flashvsr_color_fix: bool = True,
    flashvsr_decode_tile: int = 512,
    temp_video_from_images: Optional[str] = None,
    temp_video_with_audio: Optional[str] = None,
    **kwargs,
) -> tuple[torch.Tensor, dict, str, str, str, str]:
    """Run AI upscaling directly without any LLM involvement.

    Upscales images and videos using Real-ESRGAN, HAT, DAT, or SwinIR
    via spandrel.

    Returns:
        Standard 6-tuple: (images_tensor, audio_dict, output_path,
                          ffmpeg_log, analysis_text, error_text)
    """
    import shutil

    upscale_output = None
    temp_render_dir = None
    _SEEDVR_MODELS = {"seedvr2_3b_int8", "seedvr2_7b_int8", "seedvr2_3b_fp8", "seedvr2_3b_gguf", "seedvr2_7b_fp8", "seedvr2_7b_fp8_mixed", "seedvr2_7b_gguf"}
    _FLASHVSR_MODELS = {"flashvsr_full", "flashvsr_tiny", "flashvsr_tiny_long"}

    # --- Build output path (same pattern as flux_klein and other no-LLM modes) ---
    output_path, temp_render_dir = build_output_path(
        effective_video_path=effective_video_path,
        save_output=save_output,
        output_path=output_path,
        preview_mode=preview_mode,
    )

    try:
        if not effective_video_path or not os.path.isfile(effective_video_path):
            raise RuntimeError("No valid input provided for AI upscaling")

        # Determine if input is video or image
        ext = os.path.splitext(effective_video_path)[1].lower()
        _video_exts = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".flv", ".wmv"}
        is_video = ext in _video_exts

        # Image source -> image output: switch the output extension so the file
        # is saved as an image and the Agent's image_path output (which only
        # forwards image-extension paths) picks it up. (build_output_path always
        # emits .mp4.)
        if not is_video:
            _img_out_ext = ext if ext in (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff", ".tif") else ".png"
            output_path = os.path.splitext(output_path)[0] + _img_out_ext

        # Normalize VAE tiling request for diffusion upscalers (SeedVR2 / FlashVSR).
        # _tile_sz / _tile_ov are None for "auto" (let the model decide its own defaults).
        if not vae_tiling:
            _tile_on, _tile_sz, _tile_ov = False, None, None
        elif vae_tile_preset == "auto":
            _tile_on, _tile_sz, _tile_ov = True, None, None
        elif vae_tile_preset == "custom":
            _tile_on, _tile_sz, _tile_ov = True, int(vae_tile_size), int(vae_tile_overlap)
        else:  # numeric preset, e.g. "512"
            _tile_sz = int(vae_tile_preset)
            _tile_on, _tile_ov = True, max(0, _tile_sz // 8)

        # Import the appropriate synthesizer
        if upscale_model in _FLASHVSR_MODELS:
            try:
                from ...core.flashvsr_synthesizer import upscale_image, upscale_video
            except ImportError:
                from core.flashvsr_synthesizer import upscale_image, upscale_video  # type: ignore

            logger.info("[AIUpscale] FlashVSR upscaling with model=%s, is_video=%s",
                        upscale_model, is_video)

            if is_video:
                # processing selects how activation/decode memory is bounded:
                #   whole    → one whole-frame pass (best quality; tiny_long streams
                #              over time internally).
                #   temporal → sliding frame-window (no spatial tiling); manual
                #              frame_window bounds memory for full/tiny.
                #   spatial  → per-tile (opt-in; lowest quality). Uses the chosen
                #              VAE tile size when set.
                _fv_proc = str(flashvsr_processing or "whole").lower()
                _flashvsr_kwargs = {
                    "processing": _fv_proc,
                    "frame_window": int(flashvsr_frame_window),
                    "block_swap_blocks": blockswap_blocks,
                    "color_fix": bool(flashvsr_color_fix),
                    "decode_tile": int(flashvsr_decode_tile),
                }
                if _fv_proc == "spatial" and _tile_sz is not None:
                    _flashvsr_kwargs["tile_size"] = _tile_sz
                    _flashvsr_kwargs["tile_overlap"] = _tile_ov
                upscale_output = upscale_video(
                    input_path=effective_video_path,
                    model_name=upscale_model,
                    scale=upscale_scale,
                    **_flashvsr_kwargs,
                )
            else:
                upscale_output = upscale_image(
                    input_path=effective_video_path,
                    model_name=upscale_model,
                    scale=upscale_scale,
                    block_swap_blocks=blockswap_blocks,
                    color_fix=bool(flashvsr_color_fix),
                    decode_tile=int(flashvsr_decode_tile),
                )
        elif upscale_model in _SEEDVR_MODELS:
            try:
                from ...core.seedvr_synthesizer import upscale_image, upscale_video
            except ImportError:
                from core.seedvr_synthesizer import upscale_image, upscale_video  # type: ignore

            logger.info("[AIUpscale] SeedVR2 upscaling with model=%s, is_video=%s",
                        upscale_model, is_video)

            if is_video:
                upscale_output = upscale_video(
                    input_path=effective_video_path,
                    model_name=upscale_model,
                    resolution=seedvr_resolution,
                    blockswap_blocks=blockswap_blocks,
                    vae_tiling=_tile_on,
                    vae_tile_size=_tile_sz,
                    vae_tile_overlap=_tile_ov,
                )
            else:
                upscale_output = upscale_image(
                    input_path=effective_video_path,
                    model_name=upscale_model,
                    resolution=seedvr_resolution,
                    blockswap_blocks=blockswap_blocks,
                    vae_tiling=_tile_on,
                    vae_tile_size=_tile_sz,
                    vae_tile_overlap=_tile_ov,
                )
        elif upscale_model == "rtx_vsr":
            try:
                from ...core.rtx_vsr_synthesizer import upscale_image, upscale_video
            except ImportError:
                from core.rtx_vsr_synthesizer import upscale_image, upscale_video  # type: ignore

            logger.info("[AIUpscale] RTX VSR upscaling (quality=%s, scale=%dx, is_video=%s)",
                        rtx_quality, upscale_scale, is_video)

            if is_video:
                upscale_output = upscale_video(
                    input_path=effective_video_path,
                    scale=upscale_scale,
                    quality=rtx_quality,
                )
            else:
                upscale_output = upscale_image(
                    input_path=effective_video_path,
                    scale=upscale_scale,
                    quality=rtx_quality,
                )
        else:
            try:
                from ...core.upscaler import upscale_image, upscale_video
            except ImportError:
                from core.upscaler import upscale_image, upscale_video  # type: ignore

            logger.info("[AIUpscale] Upscaling with model=%s, scale=%dx, is_video=%s",
                        upscale_model, upscale_scale, is_video)

            if is_video:
                upscale_output = upscale_video(
                    input_path=effective_video_path,
                    model_name=upscale_model,
                    scale_factor=upscale_scale,
                    tile_size=tile_size,
                )
            else:
                upscale_output = upscale_image(
                    input_path=effective_video_path,
                    model_name=upscale_model,
                    scale_factor=upscale_scale,
                    tile_size=tile_size,
                )

        if not upscale_output or not os.path.isfile(upscale_output):
            raise RuntimeError("AI upscaler produced no output")

        logger.info("[AIUpscale] Upscale output: %s", upscale_output)

        # Always save upscale output to the ComfyUI output folder.
        # Upscaling is expensive — the result should always be persisted.
        if not save_output or not output_path:
            # Force an output path even if save_output was False
            import folder_paths  # type: ignore[import-not-found]
            out_dir = folder_paths.get_output_directory()
            stem = os.path.splitext(os.path.basename(effective_video_path))[0]
            _forced_ext = ".mp4" if is_video else (os.path.splitext(output_path)[1] or ".png")
            output_path = os.path.join(out_dir, f"{stem}_upscaled{_forced_ext}")
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        shutil.copy2(upscale_output, output_path)
        cmd_log = f"ai_upscale → {output_path}"
        logger.info("[AIUpscale] Saved to: %s", output_path)

        # --- Collect frame/audio output ---
        unique_id = str(kwargs.get("unique_id", ""))
        hidden_prompt = kwargs.get("hidden_prompt") or {}
        images_tensor, audio_out = collect_frame_output(
            media_converter=media_converter,
            output_path=output_path,
            unique_id=unique_id,
            hidden_prompt=hidden_prompt,
            removes_audio=not is_video,
        )

        analysis = (
            f"AI Upscale — Super-Resolution\n"
            f"Model: {upscale_model}\n"
            f"Scale: {upscale_scale}×\n"
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
        if upscale_output and os.path.exists(upscale_output):
            try:
                os.remove(upscale_output)
            except OSError:
                pass
