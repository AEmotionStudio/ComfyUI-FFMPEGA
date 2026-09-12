# coding: utf-8
"""No-LLM mode: sapiens2.

Moved verbatim from nodes/nollm_modes.py, which is now a re-export facade.
"""

from __future__ import annotations

from ._shared import (
    Optional,
    Path,
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


async def process_sapiens2_only(
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
    sapiens2_task: str = "pose",
    sapiens2_size: str = "1b",
    sapiens2_precision: str = "auto",
    sapiens2_seg_alpha: float = 0.5,
    sapiens2_pose_kpt_thr: float = 0.3,
    sapiens2_pose_radius: int = 6,
    sapiens2_pose_thickness: int = 4,
    temp_video_from_images: Optional[str] = None,
    temp_video_with_audio: Optional[str] = None,
    **kwargs,
) -> tuple[torch.Tensor, dict, str, str, str, str]:
    """Run Meta Sapiens2 human-centric vision without LLM involvement.

    Produces per-frame visualizations for one of six tasks: 308-keypoint
    pose, 29-class body-part segmentation, surface normals, 3D pointmap,
    human matting, or raw backbone features.

    Returns the standard 6-tuple:
        (images_tensor, audio, output_path, command_log, analysis, mask_overlay_path)

    License:
        Sapiens2 / Meta Proprietary.  Not for surveillance, biometric
        identification, deepfake generation, or weapons / critical-
        infrastructure use.  Attribution required on publications.
    """
    # The size dropdown folds the fp8 model choice into its value (e.g.
    # "5b (fp8)"); split it back out so a trailing precision suffix wins over
    # the (default "auto") sapiens2_precision value.
    try:
        from ...core.sapiens2 import _registry as _sap_reg
    except ImportError:
        from core.sapiens2 import _registry as _sap_reg  # type: ignore
    parsed_size, prec_override = _sap_reg.parse_size_selector(sapiens2_size)
    effective_precision = prec_override or sapiens2_precision

    logger.info(
        "Sapiens2 mode: task=%s size=%s precision=%s",
        sapiens2_task, parsed_size, effective_precision,
    )

    # --- Import synthesizer ---
    try:
        try:
            from ...core.sapiens2_synthesizer import (
                run_sapiens2,
                cleanup as _sap_cleanup,
            )
        except ImportError:
            from core.sapiens2_synthesizer import (  # type: ignore
                run_sapiens2,
                cleanup as _sap_cleanup,
            )
    except ImportError as exc:
        raise RuntimeError(
            "Sapiens2 is not available — "
            f"{exc}. Run install.py inside the ComfyUI venv or "
            "`pip install --no-deps git+https://github.com/facebookresearch/sapiens2.git`."
        )

    # --- Build output path ---
    output_path, temp_render_dir = build_output_path(
        effective_video_path=effective_video_path,
        save_output=save_output,
        output_path=output_path,
        preview_mode=preview_mode,
    )

    # --- Validate-and-coerce numeric params (the UI sends strings/floats) ---
    try:
        seg_alpha = float(sapiens2_seg_alpha)
        pose_kpt_thr = float(sapiens2_pose_kpt_thr)
        pose_radius = max(1, int(sapiens2_pose_radius))
        pose_thickness = max(1, int(sapiens2_pose_thickness))
    except (TypeError, ValueError) as exc:
        raise RuntimeError(
            f"Sapiens2 mode: invalid numeric parameter — {exc}"
        ) from exc

    effective_crf = crf if crf >= 0 else _CRF_MAP.get(quality_preset, 23)
    effective_preset = (
        encoding_preset if encoding_preset != "auto"
        else _PRESET_MAP.get(quality_preset, "medium")
    )

    # --- Run inference ---
    sapiens_output: Optional[str] = None
    try:
        sapiens_output = run_sapiens2(
            effective_video_path,
            task=sapiens2_task,
            size=parsed_size,
            precision=effective_precision,
            seg_alpha=seg_alpha,
            pose_kpt_thr=pose_kpt_thr,
            pose_radius=pose_radius,
            pose_thickness=pose_thickness,
            crf=effective_crf,
            preset=effective_preset,
        )
    except Exception as exc:
        logger.error("Sapiens2 mode: inference failed: %s", exc)
        try:
            _sap_cleanup()
        except Exception:
            pass
        raise RuntimeError(f"Sapiens2 inference failed: {exc}") from exc

    # --- Re-encode preview / move to output path ---
    ext = os.path.splitext(sapiens_output)[1].lower()
    is_image = ext in (".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".webp")
    if is_image:
        import shutil as _shutil
        output_path = str(Path(output_path).with_suffix(ext))
        _shutil.copy2(sapiens_output, output_path)
        cmd_log = f"cp {sapiens_output} {output_path}"
    else:
        ffmpeg = _get_ffmpeg_bin()
        ffmpeg_cmd = [
            ffmpeg, "-y",
            "-i", sapiens_output,
            "-c:v", "libx264",
            "-crf", str(effective_crf),
            "-preset", effective_preset,
            "-pix_fmt", "yuv420p",
            "-an",
        ]
        if preview_mode:
            ffmpeg_cmd.extend(["-vf", "scale=480:trunc(ow/a/2)*2", "-t", "10"])
        ffmpeg_cmd.append(output_path)

        logger.debug("Sapiens2 ffmpeg command: %s", " ".join(ffmpeg_cmd))
        proc = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(
                f"Sapiens2 mode: ffmpeg encoding failed:\n{proc.stderr[-500:]}"
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

        _task_desc = {
            "pose": "308-keypoint top-down pose (body + face + hands + feet)",
            "seg": "29-class human body-part segmentation overlay",
            "normal": "per-pixel surface normals",
            "pointmap": "3D pointmap (z-channel turbo colormap)",
            "matting": "human matting (alpha composited on green)",
            "pretrain": "raw backbone features (PCA-visualized RGB)",
        }
        analysis = (
            f"Sapiens2 Mode (no LLM)\n"
            f"Task: {sapiens2_task} — {_task_desc.get(sapiens2_task, sapiens2_task)}\n"
            f"Size: {sapiens2_size} (precision: {sapiens2_precision})\n"
            f"Source: {effective_video_path}\n"
            f"Sapiens2 output: {sapiens_output}\n"
            f"Output: {output_path}\n"
            f"License: Sapiens2/Meta Proprietary — no surveillance, biometric "
            f"identification, or deepfake use; attribution required."
        )

        return (images_tensor, audio_out, output_path, cmd_log, analysis, "")
    finally:
        # --- Cleanup temp files (always runs) ---
        for tmp_path in [temp_video_from_images, temp_video_with_audio]:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
        if sapiens_output and os.path.exists(sapiens_output):
            try:
                os.remove(sapiens_output)
            except OSError:
                pass
        if not save_output and temp_render_dir and os.path.isdir(temp_render_dir):
            if not os.listdir(temp_render_dir):
                shutil.rmtree(temp_render_dir, ignore_errors=True)
