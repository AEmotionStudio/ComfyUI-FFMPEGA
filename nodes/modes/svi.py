# coding: utf-8
"""No-LLM mode: svi.

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
    subprocess,
    tempfile,
    torch,
)


async def process_svi_only(
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
    image_path_a: Optional[str] = None,
    temp_video_from_images: Optional[str] = None,
    temp_video_with_audio: Optional[str] = None,
    **kwargs,
) -> tuple[torch.Tensor, dict, str, str, str, str]:
    """Run SVI 2.0 Pro infinite video generation without any LLM involvement.

    The reference image comes from ``image_a`` (ComfyUI IMAGE tensor).
    Per-clip prompts are newline-separated in the ``prompt`` field.

    Returns the standard 6-tuple:
        (images_tensor, audio, output_path, command_log, analysis, mask_overlay_path)
    """
    logger.info("SVI mode: prompt=%r", prompt)

    # --- Extract SVI parameters from kwargs ---
    svi_num_clips = int(kwargs.pop("svi_num_clips", 10))
    svi_height = int(kwargs.pop("svi_height", 480))
    svi_width = int(kwargs.pop("svi_width", 832))
    svi_fps = int(kwargs.pop("svi_fps", 15))
    svi_cfg_scale = float(kwargs.pop("svi_cfg_scale", 4.0))
    svi_overlap_frames = int(kwargs.pop("svi_overlap_frames", 5))
    svi_seed_multiplier = int(kwargs.pop("svi_seed_multiplier", 42))
    svi_steps = int(kwargs.pop("svi_steps", 30))
    svi_high_model_ratio = float(kwargs.pop("svi_high_model_ratio", 0.875))
    svi_frames_per_clip = int(kwargs.pop("svi_frames_per_clip", 81))
    svi_variant = str(kwargs.pop("svi_variant", "pro"))
    svi_model_high = str(kwargs.pop("svi_model_high", "auto"))
    svi_model_low = str(kwargs.pop("svi_model_low", "auto"))
    svi_lora_high = str(kwargs.pop("svi_lora_high", "SVI_Wan2.2-I2V-A14B_high_noise_lora_v2.0_pro.safetensors"))
    svi_lora_low = str(kwargs.pop("svi_lora_low", "SVI_Wan2.2-I2V-A14B_low_noise_lora_v2.0_pro.safetensors"))
    svi_extra_lora_high = str(kwargs.pop("svi_extra_lora_high", "none"))
    svi_extra_lora_low = str(kwargs.pop("svi_extra_lora_low", "none"))
    svi_vae = str(kwargs.pop("svi_vae", "auto"))
    svi_text_encoder = str(kwargs.pop("svi_text_encoder", "auto"))
    svi_sampler = str(kwargs.pop("svi_sampler", "euler"))
    svi_scheduler = str(kwargs.pop("svi_scheduler", "normal"))
    svi_blockswap_blocks = int(kwargs.pop("svi_blockswap_blocks", 0))
    svi_tiled_vae = bool(kwargs.pop("svi_tiled_vae", False))

    # Derive variant from the selected LoRA filenames
    if "_pro" in svi_lora_high.lower():
        svi_variant = "pro"
    else:
        svi_variant = "standard"

    # --- Import SVI synthesizer ---
    try:
        try:
            from ...core.svi_synthesizer import (
                generate_infinite_video,
                cleanup as _svi_cleanup,
            )
        except ImportError:
            from core.svi_synthesizer import (  # type: ignore
                generate_infinite_video,
                cleanup as _svi_cleanup,
            )
    except ImportError:
        raise RuntimeError(
            "SVI synthesizer is not available. "
            "Ensure core/svi_synthesizer.py exists."
        )

    # --- Convert image_a tensor → saved reference image ---
    ref_image_path = None
    if image_a is not None:
        from PIL import Image as _PILImage
        import numpy as _np
        if hasattr(image_a, 'shape') and len(image_a.shape) >= 3:
            if len(image_a.shape) == 4:
                arr = (image_a[0].cpu().numpy() * 255).clip(0, 255).astype(_np.uint8)
            else:
                arr = (image_a.cpu().numpy() * 255).clip(0, 255).astype(_np.uint8)
            import tempfile as _tmp
            ref_dir = _tmp.mkdtemp(prefix="svi_ref_")
            ref_image_path = os.path.join(ref_dir, "reference.png")
            _PILImage.fromarray(arr).save(ref_image_path)
            logger.info("SVI: saved reference image from image_a → %s", ref_image_path)

    # Fall back to image_path_a (string path from LoadImagePath)
    if ref_image_path is None and image_path_a:
        path_a = str(image_path_a)
        if os.path.isfile(path_a):
            ext_a = os.path.splitext(path_a)[1].lower()
            if ext_a in (".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".webp"):
                ref_image_path = path_a
                logger.info("SVI: using image_path_a as reference → %s", ref_image_path)

    # Fall back to effective_video_path (or video_path from kwargs) if it's an image/video
    if ref_image_path is None:
        # Try multiple sources for a video/image path
        candidate_paths = [
            effective_video_path,
            str(kwargs.get("video_path", "")),
        ]
        video_candidate = None
        for cand in candidate_paths:
            if cand and os.path.isfile(cand):
                video_candidate = cand
                break

        if video_candidate:
            ext = os.path.splitext(video_candidate)[1].lower()
            if ext in (".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".webp"):
                ref_image_path = video_candidate
            elif ext in (".mp4", ".mov", ".avi", ".mkv", ".webm", ".flv"):
                # Extract last frame from previous video for continuation chaining
                import subprocess, tempfile as _tmp
                ref_dir = _tmp.mkdtemp(prefix="svi_ref_")
                last_frame_path = os.path.join(ref_dir, "last_frame.png")
                try:
                    subprocess.run(
                        [
                            "ffmpeg", "-y", "-sseof", "-0.1",
                            "-i", video_candidate,
                            "-frames:v", "1", "-update", "1",
                            last_frame_path,
                        ],
                        capture_output=True, timeout=30,
                    )
                    if os.path.isfile(last_frame_path):
                        ref_image_path = last_frame_path
                        logger.info(
                            "SVI: extracted last frame from video for continuation → %s",
                            ref_image_path,
                        )
                    else:
                        raise RuntimeError("ffmpeg did not produce last frame")
                except Exception as e:
                    raise RuntimeError(
                        f"SVI mode: could not extract last frame from video "
                        f"'{video_candidate}': {e}. "
                        "Connect an image to image_a instead."
                    )

        if ref_image_path is None:
            raise RuntimeError(
                "SVI mode requires a reference image. "
                "Connect an image to image_a, provide an image_path_a, "
                "or connect a previous SVI video output to auto-extract "
                f"its last frame for continuation. "
                f"(effective_video_path='{effective_video_path}')"
            )

    # --- Parse prompts (newline-separated) ---
    prompts = [line.strip() for line in prompt.strip().split("\n") if line.strip()]
    if not prompts:
        prompts = ["A beautiful cinematic scene with natural motion"]

    # --- Build output path ---
    output_path, temp_render_dir = build_output_path(
        effective_video_path=effective_video_path,
        save_output=save_output,
        output_path=output_path,
        preview_mode=preview_mode,
    )

    cmd_log = ""
    try:
        result_path = generate_infinite_video(
            ref_image_path=ref_image_path,
            prompts=prompts,
            output_path=output_path,
            num_clips=svi_num_clips,
            height=svi_height,
            width=svi_width,
            fps=svi_fps,
            cfg_scale=svi_cfg_scale,
            num_overlap_frame=svi_overlap_frames,
            seed_multiplier=svi_seed_multiplier,
            num_inference_steps=svi_steps,
            switch_boundary=svi_high_model_ratio,
            frames_per_clip=svi_frames_per_clip,
            variant=svi_variant,
            model_path_high=svi_model_high,
            model_path_low=svi_model_low,
            lora_high=svi_lora_high,
            lora_low=svi_lora_low,
            extra_lora_high=svi_extra_lora_high if svi_extra_lora_high != "none" else None,
            extra_lora_low=svi_extra_lora_low if svi_extra_lora_low != "none" else None,
            vae_path=svi_vae,
            text_encoder_path=svi_text_encoder,
            sampler_name=svi_sampler,
            scheduler=svi_scheduler,
            blockswap_blocks=svi_blockswap_blocks,
            tiled_vae=svi_tiled_vae,
        )
        output_path = result_path
        cmd_log = f"svi generate_infinite_video → {output_path}"

    except Exception as e:
        logger.error("SVI mode failed: %s", e)
        try:
            _svi_cleanup()
        except Exception:
            pass
        raise RuntimeError(f"SVI generation failed: {e}") from e

    try:
        # --- Collect frame/audio output ---
        try:
            from ...ffmpega_media_converter import MediaConverter
            media_converter = MediaConverter()
        except ImportError:
            try:
                from ffmpega_media_converter import MediaConverter  # type: ignore
                media_converter = MediaConverter()
            except Exception:
                media_converter = None

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
        analysis = (
            f"🎬 SVI 2.0 Pro — Infinite Video Generation\n"
            f"Clips: {svi_num_clips}\n"
            f"Resolution: {svi_width}×{svi_height}\n"
            f"FPS: {svi_fps}\n"
            f"CFG Scale: {svi_cfg_scale}\n"
            f"Overlap Frames: {svi_overlap_frames}\n"
            f"Variant: {svi_variant}\n"
            f"Prompts:\n" + "\n".join(f"  {i+1}. {p}" for i, p in enumerate(prompts[:svi_num_clips]))
            + f"\n\nOutput: {output_path}"
        )

        return (images_tensor, audio_out, output_path, cmd_log, analysis, "")

    finally:
        if not save_output and temp_render_dir and os.path.isdir(temp_render_dir):
            if not os.listdir(temp_render_dir):
                shutil.rmtree(temp_render_dir, ignore_errors=True)
