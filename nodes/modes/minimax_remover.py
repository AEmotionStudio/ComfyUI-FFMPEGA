# coding: utf-8
"""No-LLM mode: minimax remover.

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


async def process_minimax_remover_only(
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
    temp_video_from_images: Optional[str] = None,
    temp_video_with_audio: Optional[str] = None,
    **kwargs,
) -> tuple[torch.Tensor, dict, str, str, str, str]:
    """Run MiniMax-Remover directly without any LLM involvement.

    Auto-detects whether the input is a single image or a video and
    performs full-frame object removal.  The prompt is used as the SAM3
    text target to generate a mask, then MiniMax-Remover inpaints the
    masked region.

    When no prompt is provided, performs full-frame removal using the
    entire frame as a mask (useful for background replacement).

    Returns the standard 6-tuple:
        (images_tensor, audio, output_path, command_log, analysis, mask_overlay_path)
    """
    logger.info("MiniMax-Remover mode: prompt=%r", prompt)

    # --- Import MiniMax-Remover ---
    try:
        try:
            from ...core.minimax_remover import (
                remove_object as minimax_remove,
                cleanup as _mm_cleanup,
            )
        except ImportError:
            from core.minimax_remover import (  # type: ignore
                remove_object as minimax_remove,
                cleanup as _mm_cleanup,
            )
    except ImportError:
        raise RuntimeError(
            "MiniMax-Remover is not available. "
            "Ensure diffusers >= 0.33.0 is installed and "
            "core/minimax_remover.py exists."
        )

    # --- Build output path ---
    output_path, temp_render_dir = build_output_path(
        effective_video_path=effective_video_path,
        save_output=save_output,
        output_path=output_path,
        preview_mode=preview_mode,
    )

    # NOTE: VRAM is freed internally by minimax_remover.load_pipeline()
    # via _vram_utils.free_for_module() — no manual clearing needed here.

    # --- Generate mask with SAM3 (if prompt provided) ---
    mask_video_path = None
    mask_tmpdir = None  # track fallback mask temp dir for cleanup
    if prompt and prompt.strip():
        try:
            try:
                from ...core.sam3_masker import mask_video_subprocess as sam3_mask
            except ImportError:
                from core.sam3_masker import mask_video_subprocess as sam3_mask  # type: ignore
            logger.info("MiniMax-Remover: generating SAM3 mask for '%s'", prompt)
            mask_video_path = sam3_mask(
                video_path=effective_video_path,
                prompt=prompt,
            )
        except ImportError:
            logger.warning(
                "SAM3 not available — performing full-frame removal"
            )
        except Exception as e:
            logger.warning("SAM3 masking failed: %s — performing full-frame removal", e)

    # --- If no mask, create a full-white mask (full-frame removal) ---
    if mask_video_path is None or not os.path.isfile(mask_video_path):
        if not prompt or not prompt.strip():
            logger.warning(
                "MiniMax-Remover: no prompt provided — creating full-white mask. "
                "This will attempt to inpaint the ENTIRE frame, which may produce "
                "artifacts. Consider providing a text prompt to target specific objects."
            )
        import cv2
        import numpy as np

        cap = cv2.VideoCapture(effective_video_path)
        fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        n_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        cap.release()

        # Pad dimensions to even values so the mask matches the
        # pad=ceil(iw/2)*2:ceil(ih/2)*2 encoding used downstream,
        # preventing pixel misalignment with the source video.
        w = int(np.ceil(w / 2) * 2)
        h = int(np.ceil(h / 2) * 2)

        mask_tmpdir = tempfile.mkdtemp(prefix="ffmpega_mm_mask_")
        mask_video_path = os.path.join(mask_tmpdir, "mask.mp4")
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(mask_video_path, fourcc, fps, (w, h))
        white = np.full((h, w, 3), 255, dtype=np.uint8)
        for _ in range(max(1, n_frames)):
            writer.write(white)
        writer.release()

        # Re-encode with ffmpeg for proper MP4 container (mp4v can
        # produce files that ffmpeg/PIL decoders struggle with).
        _ffmpeg = _get_ffmpeg_bin()
        reencoded = mask_video_path + ".tmp.mp4"
        _re = subprocess.run(
            [_ffmpeg, "-y", "-i", mask_video_path,
             "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p",
             reencoded],
            capture_output=True,
        )
        if _re.returncode == 0 and os.path.isfile(reencoded):
            os.replace(reencoded, mask_video_path)
        else:
            # Clean up failed re-encode attempt
            try:
                os.remove(reencoded)
            except OSError:
                pass
            logger.warning("Mask re-encode failed (rc=%d), using mp4v original", _re.returncode)

        logger.info("MiniMax-Remover: created full-white mask (%dx%d, %d frames)", w, h, n_frames)

    removed_path = None
    try:
        removed_path = minimax_remove(
            video_path=effective_video_path,
            mask_video_path=mask_video_path,
            output_path=output_path,
        )
        output_path = removed_path

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
                    "MiniMax-Remover preview downscale failed: %s",
                    proc.stderr[-300:],
                )

        cmd_log = f"minimax_remover remove_object → {output_path}"

    except Exception as e:
        logger.error("MiniMax-Remover mode failed: %s", e)
        try:
            _mm_cleanup()
        except Exception:
            pass
        raise RuntimeError(f"MiniMax-Remover removal failed: {e}") from e

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
            f"MiniMax-Remover Mode (no LLM)\n"
            f"Target: {prompt or '(full-frame removal)'}\n"
            f"Mask: {mask_video_path}\n\n"
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
        # Clean up the fallback white-mask temp directory
        if mask_tmpdir and os.path.isdir(mask_tmpdir):
            shutil.rmtree(mask_tmpdir, ignore_errors=True)
        if not save_output and temp_render_dir and os.path.isdir(temp_render_dir):
            if not os.listdir(temp_render_dir):
                shutil.rmtree(temp_render_dir, ignore_errors=True)
