# coding: utf-8
"""No-LLM mode: video depth.

Moved verbatim from nodes/nollm_modes.py, which is now a re-export facade.
"""

from __future__ import annotations

from ._shared import (
    Optional,
    collect_frame_output,
    logger,
    os,
    shutil,
    tempfile,
    torch,
)


async def process_video_depth_only(
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
    video_depth_encoder: str = "vits",
    video_depth_colormap: str = "gray",
    temp_video_from_images: Optional[str] = None,
    temp_video_with_audio: Optional[str] = None,
    **kwargs,
) -> tuple[torch.Tensor, dict, str, str, str, str]:
    """Run Video Depth Anything directly without any LLM involvement.

    Produces temporally-consistent depth videos using native temporal
    attention layers.

    Returns:
        Standard 6-tuple: (images_tensor, audio_dict, output_path,
                          ffmpeg_log, analysis_text, error_text)
    """
    import shutil

    vda_output = None
    temp_render_dir = None
    try:
        if not effective_video_path or not os.path.isfile(effective_video_path):
            raise RuntimeError("No valid video provided for depth estimation")

        # Import synthesizer
        try:
            from ...core.vda_synthesizer import run_video_depth
        except ImportError:
            from core.vda_synthesizer import run_video_depth

        logger.info("[VideoDepth] Running depth estimation (encoder=%s)", video_depth_encoder)

        vda_output = run_video_depth(
            input_path=effective_video_path,
            encoder=video_depth_encoder,
            colormap=video_depth_colormap,
        )

        if not vda_output or not os.path.isfile(vda_output):
            raise RuntimeError("Video Depth Anything produced no output")

        logger.info("[VideoDepth] Depth output: %s", vda_output)

        # VDA synthesizer already produces a properly encoded mp4,
        # so just copy it — no re-encode needed.
        temp_render_dir = tempfile.mkdtemp(prefix="ffmpega_vda_")
        final_video = os.path.join(temp_render_dir, "vda_depth.mp4")
        shutil.copy2(vda_output, final_video)
        cmd_log = f"cp {vda_output} {final_video}"

        # Copy to output path if saving
        if save_output and output_path:
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            shutil.copy2(final_video, output_path)
        else:
            output_path = final_video

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

        analysis = (
            f"Video Depth Anything — Temporal Depth Estimation\n"
            f"Encoder: {video_depth_encoder}\n"
            f"Colormap: {video_depth_colormap}\n"
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
        if vda_output and os.path.exists(vda_output):
            try:
                os.remove(vda_output)
            except OSError:
                pass
        if not save_output and temp_render_dir and os.path.isdir(temp_render_dir):
            if not os.listdir(temp_render_dir):
                shutil.rmtree(temp_render_dir, ignore_errors=True)
