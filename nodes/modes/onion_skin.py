# coding: utf-8
"""No-LLM mode: onion skin.

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


async def process_onion_skin_only(
    # dependencies (injected from agent node)
    composer,
    process_manager,
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
    onion_blend_mode: str = "screen",
    onion_opacity: float = 0.5,
    onion_decay: float = 0.97,
    _all_video_paths: Optional[list] = None,
    temp_video_from_images: Optional[str] = None,
    temp_video_with_audio: Optional[str] = None,
    **kwargs,
) -> tuple[torch.Tensor, dict, str, str, str, str]:
    """Run Onion Skin effect directly without any LLM involvement.

    Auto-detects connected extra video inputs:
    - **Composite mode** (extra inputs): Blends extra videos onto the main
      video using ``filter_complex`` with FFmpeg ``blend`` filters.
    - **Temporal mode** (no extra inputs): Applies ghost-trail self-blend
      using the ``lagfun`` filter on a single video.

    Returns the standard 6-tuple:
        (images_tensor, audio, output_path, command_log, analysis, mask_overlay_path)
    """
    extra_videos = _all_video_paths or []
    has_extra = len(extra_videos) > 0
    mode_label = "composite" if has_extra else "temporal"

    logger.info(
        "Onion Skin mode: %s, blend_mode=%s, opacity=%.2f, decay=%.3f, extra_inputs=%d",
        mode_label, onion_blend_mode, onion_opacity, onion_decay, len(extra_videos),
    )

    # --- Validate blend mode ---
    _valid_modes = {
        "normal", "screen", "addition", "difference",
        "multiply", "overlay", "softlight",
    }
    if onion_blend_mode not in _valid_modes:
        onion_blend_mode = "screen"

    # --- Build output path ---
    output_path, temp_render_dir = build_output_path(
        effective_video_path=effective_video_path,
        save_output=save_output,
        output_path=output_path,
        preview_mode=preview_mode,
    )

    _ffmpeg = _get_ffmpeg_bin()
    effective_crf = crf if crf >= 0 else _CRF_MAP.get(quality_preset, 23)
    effective_preset = (
        encoding_preset if encoding_preset != "auto"
        else _PRESET_MAP.get(quality_preset, "medium")
    )

    if has_extra:
        # ── Composite mode: blend extra videos onto main ─────────────
        ffmpeg_cmd = [_ffmpeg, "-y", "-i", effective_video_path]
        for vp in extra_videos:
            ffmpeg_cmd.extend(["-i", vp])

        # Build filter_complex chain
        n_layers = len(extra_videos)
        fc_parts = []

        # Scale and prepare each overlay input to match main video
        for i in range(n_layers):
            idx = i + 1  # ffmpeg input index (0 = main)
            fc_parts.append(
                f"[{idx}:v]scale=iw:ih:force_original_aspect_ratio=decrease,"
                f"pad=iw:ih:(ow-iw)/2:(oh-ih)/2:black,setsar=1[_os{i}]"
            )

        # Chain blend operations with decaying opacity per layer
        prev = "[0:v]"
        for i in range(n_layers):
            layer_opacity = onion_opacity * (0.5 ** i) if n_layers > 1 else onion_opacity
            layer_opacity = max(0.01, min(1.0, layer_opacity))

            if i < n_layers - 1:
                out_label = f"[_osm{i}]"
                fc_parts.append(
                    f"{prev}[_os{i}]blend=all_mode={onion_blend_mode}"
                    f":all_opacity={layer_opacity:.3f}{out_label}"
                )
                prev = out_label
            else:
                fc_parts.append(
                    f"{prev}[_os{i}]blend=all_mode={onion_blend_mode}"
                    f":all_opacity={layer_opacity:.3f}[vout]"
                )

        filter_complex = ";".join(fc_parts)
        ffmpeg_cmd.extend(["-filter_complex", filter_complex])
        ffmpeg_cmd.extend(["-map", "[vout]"])

        # Copy audio from main input if present
        if video_metadata.primary_audio:
            ffmpeg_cmd.extend(["-map", "0:a?", "-c:a", "aac", "-b:a", "192k"])

        ffmpeg_cmd.extend([
            "-c:v", "libx264",
            "-crf", str(effective_crf),
            "-preset", effective_preset,
            "-pix_fmt", "yuv420p",
        ])

        if preview_mode:
            ffmpeg_cmd.extend(["-s", "480x270", "-t", "10"])

        ffmpeg_cmd.append(output_path)
        cmd_log = " ".join(ffmpeg_cmd)

        logger.debug("Onion Skin composite command: %s", cmd_log)
        proc = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(
                f"Onion Skin composite mode: ffmpeg failed:\n{proc.stderr[-500:]}"
            )

        analysis = (
            f"Onion Skin Mode — Composite (no LLM)\n"
            f"Blend mode: {onion_blend_mode}\n"
            f"Opacity: {onion_opacity:.0%}\n"
            f"Extra inputs: {n_layers}\n"
            f"Layers blended with decay factor 0.5 per layer\n\n"
            f"Inputs:\n  Main: {effective_video_path}\n"
            + "\n".join(f"  Layer {i+1}: {v}" for i, v in enumerate(extra_videos))
        )

    else:
        # ── Temporal mode: single-video ghost trail ──────────────────
        decay = max(0.9, min(0.999, onion_decay))

        ffmpeg_cmd = [
            _ffmpeg, "-y",
            "-i", effective_video_path,
            "-vf", f"lagfun=decay={decay}",
            "-c:v", "libx264",
            "-crf", str(effective_crf),
            "-preset", effective_preset,
            "-pix_fmt", "yuv420p",
        ]

        # Preserve audio
        if video_metadata.primary_audio:
            ffmpeg_cmd.extend(["-c:a", "aac", "-b:a", "192k"])
        else:
            ffmpeg_cmd.append("-an")

        if preview_mode:
            # Insert scale filter before lagfun
            for i, arg in enumerate(ffmpeg_cmd):
                if arg == "-vf":
                    ffmpeg_cmd[i + 1] = f"scale=480:-1,{ffmpeg_cmd[i + 1]}"
                    break
            ffmpeg_cmd.extend(["-t", "10"])

        ffmpeg_cmd.append(output_path)
        cmd_log = " ".join(ffmpeg_cmd)

        logger.debug("Onion Skin temporal command: %s", cmd_log)
        proc = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(
                f"Onion Skin temporal mode: ffmpeg failed:\n{proc.stderr[-500:]}"
            )

        analysis = (
            f"Onion Skin Mode — Temporal (no LLM)\n"
            f"Decay: {decay:.3f}\n"
            f"Input: {effective_video_path}\n"
            f"Output: {output_path}"
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
