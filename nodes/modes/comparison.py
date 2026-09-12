# coding: utf-8
"""No-LLM mode: comparison.

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


async def process_comparison_only(
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
    comparison_style: str = "swipe",
    comparison_labels: bool = False,
    comparison_label_a: str = "Before",
    comparison_label_b: str = "After",
    _all_video_paths: Optional[list] = None,
    temp_video_from_images: Optional[str] = None,
    temp_video_with_audio: Optional[str] = None,
    **kwargs,
) -> tuple[torch.Tensor, dict, str, str, str, str]:
    """Run Comparison effect directly without any LLM involvement.

    Creates a comparison video from the main video and a connected extra video
    input. Supports styles: swipe, split, side_by_side, diagonal,
    circular_reveal, difference.

    Returns the standard 6-tuple:
        (images_tensor, audio, output_path, command_log, analysis, mask_overlay_path)
    """
    extra_videos = _all_video_paths or []
    if not extra_videos:
        raise RuntimeError(
            "Comparison mode requires a second video input. "
            "Connect a video to video_a (the 'after' input)."
        )

    video_b_path = extra_videos[0]
    logger.info(
        "Comparison mode: style=%s, labels=%s, video_a=%s, video_b=%s",
        comparison_style, comparison_labels, effective_video_path, video_b_path,
    )

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

    # --- Probe input dimensions ---
    try:
        from ...core.bin_paths import get_ffprobe_bin
    except ImportError:
        from core.bin_paths import get_ffprobe_bin  # type: ignore

    w, h, fps_val, dur = 1280, 720, 25, 10.0
    ffprobe = get_ffprobe_bin()
    if ffprobe:
        try:
            probe_result = subprocess.run(
                [ffprobe, "-v", "error", "-select_streams", "v:0",
                 "-show_entries", "stream=width,height,r_frame_rate",
                 "-show_entries", "format=duration",
                 "-of", "csv=p=0", effective_video_path],
                capture_output=True, text=True, timeout=10,
            )
            lines = probe_result.stdout.strip().split("\n")
            if lines and lines[0]:
                parts = lines[0].split(",")
                if len(parts) >= 2:
                    w = int(parts[0])
                    h = int(parts[1])
                if len(parts) >= 3 and "/" in parts[2]:
                    num, den = parts[2].split("/")
                    fps_val = int(num) // max(1, int(den))
            if len(lines) > 1 and lines[1]:
                try:
                    dur = float(lines[1])
                except ValueError:
                    pass
        except Exception:
            pass

    # Ensure even dimensions
    w = w // 2 * 2
    h = h // 2 * 2

    # --- Build filter_complex ---
    style = comparison_style.lower()

    prep_a = (f"[0:v]scale={w}:{h}:force_original_aspect_ratio=decrease,"
              f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:black,setsar=1,fps={fps_val}[_ca]")
    prep_b = (f"[1:v]scale={w}:{h}:force_original_aspect_ratio=decrease,"
              f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:black,setsar=1,fps={fps_val}[_cb]")

    fc_parts = [prep_a, prep_b]

    if style == "swipe":
        # Reveal B left→right over the clip duration. A time-animated crop width
        # can't be used here: crop evaluates w once at init, where t=0 yields a
        # zero-width frame and libx264 fails with "Could not open encoder before
        # EOF" (-22). blend evaluates the expression per-pixel/per-frame instead.
        fc_parts.append(
            f"[_ca][_cb]blend=all_expr='if(lt(X,{w}*T/{dur}),B,A)':shortest=1[_cmp]"
        )

    elif style == "split":
        half = (w // 2) // 2 * 2
        fc_parts.append(f"[_cb]crop=w={half}:h={h}:x=0:y=0[_cb_half]")
        fc_parts.append(f"[_ca][_cb_half]overlay=x=0:y=0:shortest=1[_cmp_raw]")
        fc_parts.append(f"[_cmp_raw]drawbox=x={half}:y=0:w=2:h={h}:color=white:t=fill[_cmp]")

    elif style == "side_by_side":
        fc_parts.append(f"[_ca][_cb]hstack=inputs=2:shortest=1[_cmp]")

    elif style == "diagonal":
        fc_parts.append(
            f"[_ca][_cb]blend=all_expr='if(lt(X/{w}+Y/{h},1),B,A)':shortest=1[_cmp]"
        )

    elif style == "circular_reveal":
        max_r = max(w, h)
        cx, cy = w // 2, h // 2
        fc_parts.append(
            f"[_ca][_cb]blend=all_expr='if(lte(hypot(X-{cx},Y-{cy}),{max_r}*T/{dur}),B,A)':shortest=1[_cmp]"
        )

    elif style == "difference":
        fc_parts.append(f"[_ca][_cb]blend=all_mode=difference:all_opacity=1.0:shortest=1[_cmp]")

    else:
        # Default to swipe (see swipe branch for why blend, not crop+overlay)
        fc_parts.append(
            f"[_ca][_cb]blend=all_expr='if(lt(X,{w}*T/{dur}),B,A)':shortest=1[_cmp]"
        )

    # --- Optional labels ---
    if comparison_labels:
        safe_a = comparison_label_a.replace(":", r"\:")
        safe_b = comparison_label_b.replace(":", r"\:")
        fc_parts.append(
            f"[_cmp]drawtext=text='{safe_a}':fontsize=36:"
            f"fontcolor=white:borderw=2:bordercolor=black:x=20:y=20,"
            f"drawtext=text='{safe_b}':fontsize=36:"
            f"fontcolor=white:borderw=2:bordercolor=black:x=w-text_w-20:y=20[vout]"
        )
        map_label = "[vout]"
    else:
        fc_parts.append("[_cmp]null[vout]")
        map_label = "[vout]"

    filter_complex = ";".join(fc_parts)

    # --- Build FFmpeg command ---
    ffmpeg_cmd = [
        _ffmpeg, "-y",
        "-i", effective_video_path,
        "-stream_loop", "-1", "-i", video_b_path,
        "-filter_complex", filter_complex,
        "-map", map_label,
    ]

    # Copy audio from main input if present
    if video_metadata.primary_audio:
        ffmpeg_cmd.extend(["-map", "0:a?", "-c:a", "aac", "-b:a", "192k"])

    ffmpeg_cmd.extend([
        "-c:v", "libx264",
        "-crf", str(effective_crf),
        "-preset", effective_preset,
        "-pix_fmt", "yuv420p",
        "-shortest",
    ])

    if preview_mode:
        ffmpeg_cmd.extend(["-s", "480x270", "-t", "10"])

    ffmpeg_cmd.append(output_path)
    cmd_log = " ".join(ffmpeg_cmd)

    logger.debug("Comparison command: %s", cmd_log)
    proc = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"Comparison mode: ffmpeg failed:\n{proc.stderr[-500:]}"
        )

    analysis = (
        f"Comparison Mode — {style} (no LLM)\n"
        f"Labels: {'Yes' if comparison_labels else 'No'}\n"
        f"Input A (before): {effective_video_path}\n"
        f"Input B (after): {video_b_path}\n"
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
