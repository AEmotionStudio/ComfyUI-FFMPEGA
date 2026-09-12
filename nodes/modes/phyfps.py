# coding: utf-8
"""No-LLM mode: phyfps.

Moved verbatim from nodes/nollm_modes.py, which is now a re-export facade.
"""

from __future__ import annotations

from ._shared import (
    Optional,
    _get_ffmpeg_bin,
    build_output_path,
    collect_frame_output,
    logger,
    os,
    shutil,
    subprocess,
    torch,
)


async def process_phyfps_only(
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
    phyfps_action: str = "analyze_only",
    temp_video_from_images: Optional[str] = None,
    temp_video_with_audio: Optional[str] = None,
    **kwargs,
) -> tuple[torch.Tensor, dict, str, str, str, str]:
    """Run Visual Chronometer PhyFPS analysis and optional re-timing correction.

    Returns the standard 6-tuple:
        (images_tensor, audio, output_path, command_log, analysis, mask_overlay_path)
    """
    try:
        from ...core import phyfps_synthesizer
    except ImportError:
        from core import phyfps_synthesizer  # type: ignore

    try:
        from ...core.bin_paths import get_ffprobe_bin
    except ImportError:
        from core.bin_paths import get_ffprobe_bin  # type: ignore

    logger.info("PhyFPS mode: action=%s, video=%s", phyfps_action, effective_video_path)

    # --- Build output path ---
    output_path, temp_render_dir = build_output_path(
        effective_video_path=effective_video_path,
        save_output=save_output,
        output_path=output_path,
        preview_mode=preview_mode,
    )

    # --- Get container FPS ---
    container_fps = 24.0
    ffprobe = get_ffprobe_bin()
    if ffprobe:
        try:
            probe_result = subprocess.run(
                [ffprobe, "-v", "error", "-select_streams", "v:0",
                 "-show_entries", "stream=r_frame_rate",
                 "-of", "csv=p=0", effective_video_path],
                capture_output=True, text=True, timeout=10,
            )
            fps_str = probe_result.stdout.strip().split("\n")[0].strip()
            if "/" in fps_str:
                num, den = fps_str.split("/")
                container_fps = float(num) / float(den) if float(den) > 0 else 24.0
            elif fps_str:
                container_fps = float(fps_str)
        except Exception as e:
            logger.warning("Failed to probe container FPS: %s", e)

    # --- Run PhyFPS prediction ---
    results, avg_phyfps, total_frames = phyfps_synthesizer.predict_phyfps(
        video_path=effective_video_path,
        clip_length=30,
        stride=4,
        resolution=216,
    )

    corrected = False
    cmd_log = ""

    if phyfps_action == "correct" and abs(avg_phyfps / container_fps - 1.0) >= 0.05:
        # Re-time the video
        phyfps_synthesizer.correct_video(
            video_path=effective_video_path,
            container_fps=container_fps,
            phyfps=avg_phyfps,
            output_path=output_path,
        )
        corrected = True
        cmd_log = f"PhyFPS correction: {container_fps:.1f} → {avg_phyfps:.1f} fps (factor={avg_phyfps/container_fps:.3f})"
    else:
        # Just copy the video through
        _ffmpeg = _get_ffmpeg_bin()
        copy_cmd = [_ffmpeg, "-y", "-i", effective_video_path, "-c", "copy", output_path]
        subprocess.run(copy_cmd, capture_output=True, check=True)
        cmd_log = " ".join(copy_cmd)

    # Offload model after inference
    phyfps_synthesizer.offload_to_cpu()

    # --- Build analysis string ---
    video_name = os.path.basename(effective_video_path)
    analysis = phyfps_synthesizer.build_analysis_string(
        video_name=video_name,
        results=results,
        avg_phyfps=avg_phyfps,
        container_fps=container_fps,
        total_frames=total_frames,
        corrected=corrected,
    )

    # --- Collect frame/audio output ---
    unique_id = str(kwargs.get("unique_id", ""))
    hidden_prompt = kwargs.get("hidden_prompt") or {}
    images_tensor, audio_out = collect_frame_output(
        media_converter=media_converter,
        output_path=output_path,
        unique_id=unique_id,
        hidden_prompt=hidden_prompt,
        removes_audio=not bool(video_metadata.primary_audio),
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

    return (images_tensor, audio_out, output_path, cmd_log, analysis, "")
