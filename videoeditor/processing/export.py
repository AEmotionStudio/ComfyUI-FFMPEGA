"""Final render pipeline — chains all video edits into FFmpeg commands.

Orchestrates the full edit pipeline: trim → per-segment speed →
transitions → text overlays → crop → audio.  Uses ``core.bin_paths``
for FFmpeg binary resolution.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import tempfile
import threading

from ._bin import get_ffmpeg_bin, get_ffprobe_bin
from .audio import build_audio_filter, get_audio_args
from .color_grading import build_color_grading_filters, has_color_grading
from .crop import apply_crop
from .filters import build_filter_preset, has_filter_preset
from .shaders import has_shader, build_shader_filter as build_shader_preset
from .keyframes import has_keyframes, build_speed_keyframe_filter
from .relight import build_relight_filters, has_relight, needs_ai_normals, apply_ai_relight
from .export_settings import (
    parse_export_settings, build_video_codec_args, build_audio_codec_args,
    build_resolution_filter, has_export_settings, _DEFAULTS as _EXPORT_DEFAULTS,
)
from .compose import has_compose, build_compose_filters
from .ai_compose import has_ai_compose, parse_ai_compose
from .transform import has_transform, build_transform_filter, parse_transform
from .speed import build_speed_filters
from .text_overlay import build_drawtext_filters
from .transitions import apply_transitions, parse_transitions
from .trim import _parse_segments

log = logging.getLogger("ffmpega.videoeditor")


def render_edits(
    source_path: str,
    output_path: str,
    *,
    segments_json: str = "[]",
    crop_json: str = "",
    speed_map_json: str = "{}",
    volume: float = 1.0,
    text_overlays_json: str = "[]",
    transitions_json: str = "[]",
    audio_segments_json: str = "[]",
    color_grading_json: str = "{}",
    filter_preset_json: str = "{}",
    shader_preset_json: str = "{}",
    keyframes_json: str = "{}",
    relight_json: str = "{}",
    export_settings_json: str = "{}",
    compose_json: str = "{}",
    ai_compose_json: str = "{}",
    transform_json: str = "{}",
    cancel_event: threading.Event | None = None,
) -> dict:
    """Apply all edits and render to *output_path*.

    Parameters
    ----------
    source_path:
        Path to the source video file.
    output_path:
        Destination path for the rendered video.
    segments_json:
        JSON ``[[start, end], ...]`` segment list.
    crop_json:
        JSON ``{"x":N,"y":N,"w":N,"h":N}`` or empty.
    speed_map_json:
        JSON ``{"segIdx": speed}`` per-segment speed map.
    volume:
        Audio volume (0.0–2.0).
    text_overlays_json:
        JSON array of text overlay configs.
    transitions_json:
        JSON array of transition configs.
    audio_segments_json:
        JSON array of per-segment audio configs (volume, fade, EQ, mute).

    Returns
    -------
    dict
        ``{"success": bool, "output_path": str, "duration": float,
        "file_size": int, "error": str|None}``
    """
    if not os.path.isfile(source_path):
        return _error(f"Source file not found: {source_path}")

    tmp_dir = tempfile.mkdtemp(prefix="ffmpega_export_")

    try:
        # --- Step 1: Parse segments ---
        segments = _parse_segments(segments_json)
        has_edits = bool(segments)
        has_speed = has_speed_changes(speed_map_json)
        has_crop = bool(crop_json and crop_json.strip() and crop_json != "{}")
        has_text = bool(text_overlays_json and text_overlays_json.strip()
                        and text_overlays_json != "[]")
        transitions = parse_transitions(transitions_json)
        has_transitions = bool(transitions)
        has_grading = has_color_grading(color_grading_json)
        has_filters = has_filter_preset(filter_preset_json)
        has_shaders = has_shader(shader_preset_json)
        has_kf = has_keyframes(keyframes_json)
        has_relit = has_relight(relight_json)
        has_xform = has_transform(transform_json)
        has_comp = has_compose(compose_json)
        has_ai = has_ai_compose(ai_compose_json)
        has_exp = has_export_settings(export_settings_json)

        # Parse per-segment audio edits
        has_audio_segments = False
        try:
            if audio_segments_json and audio_segments_json.strip() and audio_segments_json != "[]":
                audio_segs = json.loads(audio_segments_json)
                if isinstance(audio_segs, list) and audio_segs:
                    has_audio_segments = any(
                        abs(s.get('volume', 1.0) - 1.0) > 0.01
                        or s.get('fadeIn', 0) > 0
                        or s.get('fadeOut', 0) > 0
                        or s.get('eq', 'flat') != 'flat'
                        or s.get('muted', False)
                        for s in audio_segs
                    )
        except (json.JSONDecodeError, TypeError):
            pass

        if has_audio_segments:
            log.info(
                "[VideoEditor] Per-segment audio edits detected "
                "(volume/fade/EQ/mute) — these are stored for the UI "
                "but per-segment FFmpeg rendering is not yet implemented. "
                "Master volume is still applied."
            )

        # AI compose (background removal, depth effects) requires GPU model
        # inference which is not part of the FFmpeg-only pipeline.  Log and
        # skip — these will be implemented via separate inference endpoints.
        if has_ai:
            ai_settings = parse_ai_compose(ai_compose_json)
            if ai_settings["bg_removal"].get("enabled"):
                log.info(
                    "[VideoEditor] AI background removal is configured but "
                    "requires model inference — not yet integrated into the "
                    "FFmpeg export pipeline.  Skipping."
                )
            if ai_settings["depth_effect"].get("enabled"):
                log.info(
                    "[VideoEditor] AI depth effects are configured but "
                    "require model inference — not yet integrated into the "
                    "FFmpeg export pipeline.  Skipping."
                )

        # Parse export settings (used for final encode codec/resolution)
        exp_settings = parse_export_settings(export_settings_json)

        # Adjust output extension to match user-selected format (e.g. .mkv, .webm)
        desired_ext = exp_settings.get("extension", ".mp4")
        base, current_ext = os.path.splitext(output_path)
        if current_ext != desired_ext:
            output_path = base + desired_ext

        # Fast path: no edits at all → copy source
        # Note: has_audio_segments is intentionally excluded here —
        # per-segment audio rendering is not yet implemented, so blocking
        # the fast-path would force a full re-encode without applying them.
        # has_ai is excluded — AI compose requires model inference.
        # has_exp is excluded — export settings only affect codec choice and
        # don't require re-encoding if nothing else triggers it.
        if (not has_edits and not has_speed and not has_crop
                and not has_text and not has_transitions
                and not has_grading and not has_filters
                and not has_kf and not has_relit
                and not has_xform and not has_comp):
            shutil.copy2(source_path, output_path)
            return _success(output_path)

        # --- Step 2: Extract segments (with per-segment speed) ---
        if has_edits:
            needs_reencode = has_speed
            seg_files = _extract_segments(
                source_path, segments, speed_map_json,
                tmp_dir,
                reencode=needs_reencode,
            )
        else:
            # No trim — treat entire video as one segment
            seg_files = [source_path]

        if not seg_files:
            return _error("All segments failed to extract")

        # --- Step 3: Apply transitions (or simple concat) ---
        if cancel_event and cancel_event.is_set():
            return _error("Export cancelled")

        used_transitions = has_transitions and len(seg_files) > 1
        if used_transitions:
            joined_path = os.path.join(tmp_dir, "joined.mp4")
            apply_transitions(seg_files, transitions, joined_path)
            current = joined_path
        elif len(seg_files) > 1:
            joined_path = os.path.join(tmp_dir, "joined.mp4")
            current = _concat_segments(seg_files, joined_path)
        else:
            current = seg_files[0]

        # ── Step 3b: filter_complex presets (can't merge into -vf) ────
        if cancel_event and cancel_event.is_set():
            return _error("Export cancelled")

        # Parse compose data once — reused for watermark fc and vf parts.
        compose_data: dict = {}
        if has_comp:
            compose_data = build_compose_filters(compose_json)

        # Complex / reduced-intensity filter preset → separate fc pass
        fc_applied = False
        if has_filters:
            _vf_f, _fc_f = build_filter_preset(filter_preset_json)
            if _fc_f:
                fc_path = os.path.join(tmp_dir, "fc_preset.mp4")
                current = _apply_filter_preset(
                    current, filter_preset_json, fc_path,
                )
                fc_applied = True

        # Complex / reduced-intensity shader → separate fc pass
        if has_shaders:
            _vf_s, _fc_s = build_shader_preset(shader_preset_json)
            if _fc_s:
                shader_fc_path = os.path.join(tmp_dir, "fc_shader.mp4")
                ffmpeg = get_ffmpeg_bin()
                shader_cmd = [
                    ffmpeg, "-y", "-i", current,
                    "-filter_complex", _fc_s,
                    "-c:v", "libx264", "-crf", "18", "-preset", "fast",
                    "-pix_fmt", "yuv420p", "-c:a", "copy",
                    shader_fc_path,
                ]
                log.info("[VideoEditor] Shader fc pass: %s", " ".join(shader_cmd))
                _run(shader_cmd, cancel_event=cancel_event)
                if os.path.isfile(shader_fc_path) and os.path.getsize(shader_fc_path) > 0:
                    current = shader_fc_path
                else:
                    log.warning("[VideoEditor] Shader fc pass produced no output, skipping")

        # Watermark uses movie= filter_complex → separate pass
        if compose_data.get("watermark_filter"):
            wm_fc = compose_data["watermark_filter"]
            ffmpeg = get_ffmpeg_bin()
            wm_out = os.path.join(tmp_dir, "wm_out.mp4")
            wm_cmd = [
                ffmpeg, "-y", "-i", current,
                "-filter_complex", wm_fc,
                "-c:v", "libx264", "-crf", "18", "-preset", "fast",
                "-pix_fmt", "yuv420p", "-c:a", "copy",
                "-v", "warning", wm_out,
            ]
            wm_result = subprocess.run(
                wm_cmd, capture_output=True, text=True, timeout=300,
            )
            if wm_result.returncode == 0:
                current = wm_out
            else:
                log.warning(
                    "[VideoEditor] Watermark failed: %s",
                    wm_result.stderr[:300],
                )

        # Log compose modes that need multi-input (not yet wired)
        if compose_data.get("pip_filter"):
            log.info(
                "[VideoEditor] PiP compositing requires a second video "
                "input — not yet integrated.  Skipping."
            )
        if compose_data.get("split_screen"):
            log.info(
                "[VideoEditor] Split screen requires multiple video "
                "inputs — not yet integrated.  Skipping."
            )
        if compose_data.get("blend"):
            log.info(
                "[VideoEditor] Blend mode requires a second video "
                "input — not yet integrated.  Skipping."
            )

        # ── Step 3c-pre: AI normals relight (NormalCrafter GPU pass) ──
        # When ai_normals is enabled, run NormalCrafter to get real surface
        # normals and composite per-pixel Lambertian shading.  This replaces
        # the FFmpeg-only relight approximation with physically-based normals.
        # Must run before the vf chain since it needs GPU model inference.
        if has_relit and needs_ai_normals(relight_json):
            if cancel_event and cancel_event.is_set():
                return _error("Export cancelled")
            ai_relit_path = os.path.join(tmp_dir, "ai_relit.mp4")
            try:
                current = apply_ai_relight(
                    video_path=current,
                    relight_json=relight_json,
                    output_path=ai_relit_path,
                )
                log.info("[VideoEditor] AI normals relight applied successfully")
            except Exception as exc:
                log.warning(
                    "[VideoEditor] AI normals relight failed, falling back "
                    "to FFmpeg approximation: %s", exc,
                )
                # Fall through — build_relight_filters will return FFmpeg
                # approximation filters since ai_normals check failed.

        # ── Step 3c: Collect simple -vf filters into one chain ─────
        if cancel_event and cancel_event.is_set():
            return _error("Export cancelled")

        vf_chain: list[str] = []
        strip_audio = False

        if has_grading:
            vf_chain.extend(build_color_grading_filters(color_grading_json))

        # Simple, full-intensity presets (fc handled above)
        if has_filters and not fc_applied:
            _vf_simple, _ = build_filter_preset(filter_preset_json)
            if _vf_simple:
                vf_chain.extend(_vf_simple)

        # Simple shader preset (full intensity, no fc needed)
        if has_shaders:
            _vf_shader, _fc_shader = build_shader_preset(shader_preset_json)
            if _vf_shader and not _fc_shader:
                vf_chain.extend(_vf_shader)

        if has_relit:
            vf_chain.extend(build_relight_filters(relight_json))

        if has_xform:
            vf_chain.extend(build_transform_filter(parse_transform(transform_json)))

        # Compose -vf parts (vignette, chromakey, mask, onion skin)
        if has_comp:
            vf_chain.extend(compose_data.get("vignette", []))
            vf_chain.extend(compose_data.get("chromakey", []))
            vf_chain.extend(compose_data.get("mask", []))
            vf_chain.extend(compose_data.get("onion_skin", []))

        # Speed keyframes (setpts changes timing → must strip audio)
        if has_kf:
            speed_filter = build_speed_keyframe_filter(keyframes_json)
            if speed_filter:
                vf_chain.append(speed_filter)
                strip_audio = True

        # Text overlays last so text renders on top of all effects
        if has_text:
            text_filters = build_drawtext_filters(text_overlays_json)
            if text_filters:
                vf_chain.extend(text_filters)

        # Resolution scale from export settings (if non-source)
        use_export_codec = has_exp and not _settings_match_intermediate(
            exp_settings
        )
        if use_export_codec:
            res_filter = build_resolution_filter(exp_settings)
            if res_filter:
                vf_chain.append(res_filter)

        # ── Step 3d: Apply collected filters in ONE encode pass ────
        # Save pre-combined path — if audio was stripped during this pass
        # we re-mux from this source in the audio step below.
        pre_combined = current
        export_applied = False

        if vf_chain:
            vf = ",".join(vf_chain)
            combined_path = os.path.join(tmp_dir, "combined.mp4")

            # Use export codec when non-default → avoids a redundant
            # re-encode in the step-5b export settings pass.
            if use_export_codec:
                vcodec = build_video_codec_args(exp_settings)
                acodec = (
                    ["-an"] if strip_audio
                    else build_audio_codec_args(exp_settings)
                )
                export_applied = True
            else:
                vcodec = [
                    "-c:v", "libx264", "-crf", "18",
                    "-preset", "fast", "-pix_fmt", "yuv420p",
                ]
                acodec = ["-an"] if strip_audio else ["-c:a", "copy"]

            ffmpeg = get_ffmpeg_bin()
            cmd = (
                [ffmpeg, "-y", "-i", current, "-vf", vf]
                + vcodec + acodec
                + ["-v", "warning", combined_path]
            )
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=600,
            )
            if result.returncode == 0:
                current = combined_path
            else:
                log.warning(
                    "[VideoEditor] Combined filter pass failed: %s",
                    result.stderr[:300],
                )

        # --- Step 4: Apply crop ---
        if cancel_event and cancel_event.is_set():
            return _error("Export cancelled")

        if has_crop:
            cropped_path = os.path.join(tmp_dir, "cropped.mp4")
            current = apply_crop(current, crop_json, cropped_path)

        # --- Step 5: Apply audio adjustments ---
        if cancel_event and cancel_event.is_set():
            return _error("Export cancelled")

        # Audio re-mux is needed when:
        #  - transitions stripped audio (-an)
        #  - keyframe setpts stripped audio (A/V timing mismatch)
        #  - volume != 1.0
        needs_audio_pass = (
            used_transitions
            or strip_audio
            or abs(volume - 1.0) > 0.01
            or volume < 0.001
        )
        if needs_audio_pass:
            audio_src = None
            video_duration = None
            if used_transitions:
                # Build a matching audio track from the segment files
                audio_concat = os.path.join(tmp_dir, "audio_concat.mp4")
                audio_src = _concat_segments(seg_files, audio_concat)
                # Probe xfade'd video duration so we can truncate audio to
                # match — xfade shortens the total by transition overlap.
                from .transitions import _get_duration
                video_duration = _get_duration(current) or None
            elif strip_audio:
                # Keyframe setpts altered video timing — re-mux audio
                # from the pre-combined source, truncated to the new
                # video duration.  Note: A/V may desync for large speed
                # changes since audio speed isn't adjusted.
                audio_src = pre_combined
                from .transitions import _get_duration
                video_duration = _get_duration(current) or None
            audio_path = os.path.join(tmp_dir, "audio_adj.mp4")
            current = _apply_audio(
                current, volume, audio_path, audio_src,
                match_duration=video_duration,
            )

        # --- Step 5b: Apply export settings (final re-encode) ---
        # Skip if already applied in the combined pass above.
        if cancel_event and cancel_event.is_set():
            return _error("Export cancelled")

        if (has_exp
                and not _settings_match_intermediate(exp_settings)
                and not export_applied):
            final_path = os.path.join(tmp_dir, "final_encode.mp4")
            current = _apply_export_settings(
                current, exp_settings, final_path,
            )

        # --- Step 6: Move final to output ---
        if current != output_path:
            if os.path.isfile(current):
                shutil.copy2(current, output_path)
            else:
                return _error("Final render file not found")

        return _success(output_path)

    except Exception as e:
        log.exception("[VideoEditor] Export failed")
        return _error(str(e))

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _extract_segments(
    source_path: str,
    segments: list[tuple[float, float]],
    speed_map_json: str,
    tmp_dir: str,
    *,
    reencode: bool = False,
) -> list[str]:
    """Extract individual segments, applying per-segment speed filters."""
    ffmpeg = get_ffmpeg_bin()
    seg_files: list[str] = []

    for idx, (start, end) in enumerate(segments):
        duration = end - start
        if duration <= 0:
            continue

        seg_out = os.path.join(tmp_dir, f"seg_{idx:04d}.mp4")
        vf, af_speed = build_speed_filters(speed_map_json, idx)

        needs_reencode = reencode or bool(vf) or bool(af_speed)

        cmd: list[str] = [
            ffmpeg, "-y",
            "-ss", f"{start:.6f}",
            "-i", source_path,
            "-t", f"{duration:.6f}",
        ]

        if needs_reencode:
            if vf:
                cmd += ["-vf", vf]
            cmd += [
                "-c:v", "libx264", "-crf", "18", "-preset", "fast",
                "-pix_fmt", "yuv420p",
            ]
            if af_speed:
                cmd += ["-af", af_speed, "-c:a", "aac", "-b:a", "192k"]
            else:
                cmd += ["-c:a", "aac", "-b:a", "192k"]
        else:
            cmd += ["-c", "copy", "-avoid_negative_ts", "make_zero"]

        cmd += ["-v", "warning", seg_out]

        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=300,
        )
        if result.returncode != 0:
            log.warning(
                "[VideoEditor] Segment %d extract failed: %s",
                idx, result.stderr[:300],
            )
            continue

        seg_files.append(seg_out)

    return seg_files


def _apply_text_overlays(
    source_path: str,
    text_overlays_json: str,
    output_path: str,
) -> str:
    """Apply text overlays to the concatenated video.

    Text overlay times are relative to the final output timeline,
    so this must run *after* concat/transitions.
    """
    text_filters = build_drawtext_filters(text_overlays_json)
    if not text_filters:
        return source_path

    ffmpeg = get_ffmpeg_bin()
    cmd = [
        ffmpeg, "-y",
        "-i", source_path,
        "-vf", ",".join(text_filters),
        "-c:v", "libx264", "-crf", "18", "-preset", "fast",
        "-pix_fmt", "yuv420p",
        "-c:a", "copy",
        "-v", "warning",
        output_path,
    ]
    result = subprocess.run(
        cmd, capture_output=True, text=True, timeout=300,
    )
    if result.returncode != 0:
        log.warning(
            "[VideoEditor] Text overlay failed: %s", result.stderr[:300],
        )
        return source_path  # graceful fallback

    return output_path


def _apply_color_grading(
    source_path: str,
    grading_json: str,
    output_path: str,
) -> str:
    """Apply color grading filters to the video.

    Runs after concat/transitions but before text overlays, so text
    renders on top of the graded footage.
    """
    grading_filters = build_color_grading_filters(grading_json)
    if not grading_filters:
        return source_path

    ffmpeg = get_ffmpeg_bin()
    vf = ",".join(grading_filters)

    cmd = [
        ffmpeg, "-y",
        "-i", source_path,
        "-vf", vf,
        "-c:v", "libx264", "-crf", "18", "-preset", "fast",
        "-pix_fmt", "yuv420p",
        "-c:a", "copy",
        "-v", "warning",
        output_path,
    ]
    result = subprocess.run(
        cmd, capture_output=True, text=True, timeout=300,
    )
    if result.returncode != 0:
        log.warning(
            "[VideoEditor] Color grading failed: %s", result.stderr[:300],
        )
        return source_path  # graceful fallback

    return output_path


def _apply_filter_preset(
    source_path: str,
    preset_json: str,
    output_path: str,
) -> str:
    """Apply a filter preset to the video.

    Handles both simple (-vf) and complex (-filter_complex) presets.
    Runs after color grading but before text overlays.
    """
    vf_filters, filter_complex = build_filter_preset(preset_json)

    if not vf_filters and not filter_complex:
        return source_path

    ffmpeg = get_ffmpeg_bin()

    if vf_filters:
        # Simple preset — use -vf
        vf = ",".join(vf_filters)
        cmd = [
            ffmpeg, "-y",
            "-i", source_path,
            "-vf", vf,
            "-c:v", "libx264", "-crf", "18", "-preset", "fast",
            "-pix_fmt", "yuv420p",
            "-c:a", "copy",
            "-v", "warning",
            output_path,
        ]
    else:
        # Complex preset — use -filter_complex
        cmd = [
            ffmpeg, "-y",
            "-i", source_path,
            "-filter_complex", filter_complex,
            "-map", "[out]",
            "-map", "0:a?",
            "-c:v", "libx264", "-crf", "18", "-preset", "fast",
            "-pix_fmt", "yuv420p",
            "-c:a", "copy",
            "-v", "warning",
            output_path,
        ]

    result = subprocess.run(
        cmd, capture_output=True, text=True, timeout=300,
    )
    if result.returncode != 0:
        log.warning(
            "[VideoEditor] Filter preset failed: %s", result.stderr[:300],
        )
        return source_path  # graceful fallback

    return output_path


def _apply_relight(
    source_path: str,
    relight_json: str,
    output_path: str,
) -> str:
    """Apply relighting to the video using FFmpeg filters."""
    filters = build_relight_filters(relight_json)
    if not filters:
        return source_path

    ffmpeg = get_ffmpeg_bin()
    vf = ",".join(filters)
    cmd = [
        ffmpeg, "-y",
        "-i", source_path,
        "-vf", vf,
        "-c:v", "libx264", "-crf", "18", "-preset", "fast",
        "-pix_fmt", "yuv420p",
        "-c:a", "copy",
        "-v", "warning",
        output_path,
    ]
    result = subprocess.run(
        cmd, capture_output=True, text=True, timeout=300,
    )
    if result.returncode != 0:
        log.warning(
            "[VideoEditor] Relight failed: %s", result.stderr[:300],
        )
        return source_path  # graceful fallback

    return output_path


def _apply_transform(
    source_path: str,
    transform_json: str,
    output_path: str,
) -> str:
    """Apply spatial transform filters (position, scale, rotation, flip, opacity)."""
    params = parse_transform(transform_json)
    filters = build_transform_filter(params)
    if not filters:
        return source_path

    ffmpeg = get_ffmpeg_bin()
    vf = ",".join(filters)
    cmd = [
        ffmpeg, "-y",
        "-i", source_path,
        "-vf", vf,
        "-c:v", "libx264", "-crf", "18", "-preset", "fast",
        "-pix_fmt", "yuv420p",
        "-c:a", "copy",
        "-v", "warning",
        output_path,
    ]
    result = subprocess.run(
        cmd, capture_output=True, text=True, timeout=300,
    )
    if result.returncode != 0:
        log.warning(
            "[VideoEditor] Transform failed: %s", result.stderr[:300],
        )
        return source_path  # graceful fallback

    return output_path


def _apply_compose(
    source_path: str,
    compose_json: str,
    output_path: str,
) -> str:
    """Apply compositing filters (vignette, chromakey, mask, etc.).

    PiP and watermark require multi-input or ``movie=`` filters and are
    handled separately.  This applies single-input ``-vf`` compose filters.
    """
    compose_data = build_compose_filters(compose_json)

    # Collect simple -vf filters (not filter_complex / multi-input ones)
    vf_parts: list[str] = []
    vf_parts.extend(compose_data.get("vignette", []))
    vf_parts.extend(compose_data.get("chromakey", []))
    vf_parts.extend(compose_data.get("mask", []))

    # Log PiP/watermark/split_screen as not yet wired (require multi-input)
    if compose_data.get("pip_filter"):
        log.info(
            "[VideoEditor] PiP compositing requires a second video input — "
            "not yet integrated into the single-input export pipeline.  Skipping."
        )
    if compose_data.get("watermark_filter"):
        # Watermark uses movie= filter which works as single-input filter_complex
        wm_fc = compose_data["watermark_filter"]
        ffmpeg = get_ffmpeg_bin()
        # Write to a temp location inside output_path's directory (guaranteed
        # to be tmp_dir) rather than source_path's directory, which may be
        # the user's original video location if no prior step ran.
        wm_out = os.path.join(os.path.dirname(output_path), "wm_out.mp4")
        cmd = [
            ffmpeg, "-y",
            "-i", source_path,
            "-filter_complex", wm_fc,
            "-c:v", "libx264", "-crf", "18", "-preset", "fast",
            "-pix_fmt", "yuv420p",
            "-c:a", "copy",
            "-v", "warning",
            wm_out,
        ]
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=300,
        )
        if result.returncode == 0:
            # Reassign local param so subsequent vf block reads the
            # watermarked file as its input.
            source_path = wm_out
        else:
            log.warning(
                "[VideoEditor] Watermark failed: %s", result.stderr[:300],
            )
    if compose_data.get("split_screen"):
        log.info(
            "[VideoEditor] Split screen requires multiple video inputs — "
            "not yet integrated.  Skipping."
        )
    if compose_data.get("blend"):
        log.info(
            "[VideoEditor] Blend mode requires a second video input — "
            "not yet integrated into the single-input export pipeline.  Skipping."
        )

    if not vf_parts:
        return source_path

    ffmpeg = get_ffmpeg_bin()
    vf = ",".join(vf_parts)
    cmd = [
        ffmpeg, "-y",
        "-i", source_path,
        "-vf", vf,
        "-c:v", "libx264", "-crf", "18", "-preset", "fast",
        "-pix_fmt", "yuv420p",
        "-c:a", "copy",
        "-v", "warning",
        output_path,
    ]
    result = subprocess.run(
        cmd, capture_output=True, text=True, timeout=300,
    )
    if result.returncode != 0:
        log.warning(
            "[VideoEditor] Compose filters failed: %s", result.stderr[:300],
        )
        return source_path  # graceful fallback

    return output_path


def _apply_keyframes(
    source_path: str,
    keyframes_json: str,
    output_path: str,
) -> str:
    """Apply speed keyframe ramps via ``setpts`` filter.

    Converts keyframe data into a nested ``if(between(t,...),...)``
    expression and applies it as a ``setpts`` video filter.  If volume
    keyframes are also present, an ``-af volume=...`` filter is added.

    Parameters
    ----------
    source_path:
        Path to the current intermediate video.
    keyframes_json:
        JSON string from the ``_keyframes`` hidden widget.
    output_path:
        Destination path for the keyframed video.

    Returns
    -------
    str
        *output_path* on success, *source_path* on failure (graceful fallback).
    """
    speed_filter = build_speed_keyframe_filter(keyframes_json)
    if not speed_filter:
        return source_path

    ffmpeg = get_ffmpeg_bin()
    # setpts only changes video timestamps — audio doesn't need re-encoding.
    # Use -c:a copy to avoid unnecessary lossy audio re-encode.
    cmd: list[str] = [
        ffmpeg, "-y",
        "-i", source_path,
        "-vf", speed_filter,
        "-c:v", "libx264", "-crf", "18", "-preset", "fast",
        "-pix_fmt", "yuv420p",
        "-c:a", "copy",
        "-v", "warning",
        output_path,
    ]
    result = subprocess.run(
        cmd, capture_output=True, text=True, timeout=600,
    )
    if result.returncode != 0:
        log.warning(
            "[VideoEditor] Keyframe speed ramp failed: %s",
            result.stderr[:300],
        )
        return source_path  # graceful fallback

    return output_path


def _apply_export_settings(
    source_path: str,
    settings: dict,
    output_path: str,
) -> str:
    """Apply user-selected export settings (codec, CRF, preset, resolution, audio).

    This runs as the final encode step, re-encoding the intermediate result
    with the user's chosen codec/CRF/preset instead of the default libx264.

    Parameters
    ----------
    source_path:
        Path to the current intermediate video.
    settings:
        Parsed export settings dict from ``parse_export_settings()``.
    output_path:
        Destination path for the re-encoded video.

    Returns
    -------
    str
        *output_path* on success, *source_path* on failure (graceful fallback).
    """
    ffmpeg = get_ffmpeg_bin()

    vcodec_args = build_video_codec_args(settings)
    acodec_args = build_audio_codec_args(settings)
    res_filter = build_resolution_filter(settings)

    cmd: list[str] = [ffmpeg, "-y", "-i", source_path]

    # Explicit stream selection for safety
    cmd += ["-map", "0:v", "-map", "0:a?"]

    # Video filter for resolution scaling (if needed)
    if res_filter:
        cmd += ["-vf", res_filter]

    cmd += vcodec_args

    # Audio: re-encode with chosen codec, or copy if defaults
    cmd += acodec_args

    cmd += ["-v", "warning", output_path]

    result = subprocess.run(
        cmd, capture_output=True, text=True, timeout=600,
    )
    if result.returncode != 0:
        log.warning(
            "[VideoEditor] Export settings re-encode failed: %s",
            result.stderr[:300],
        )
        return source_path  # graceful fallback

    return output_path


def _concat_segments(segment_files: list[str], output_path: str) -> str:
    """Concatenate segment files via concat demuxer."""
    from .concat import concat_segments
    return concat_segments(segment_files, output_path, raise_on_error=True)


def _apply_audio(
    source_path: str,
    volume: float,
    output_path: str,
    audio_source: str | None = None,
    match_duration: float | None = None,
) -> str:
    """Apply audio volume adjustment.

    Parameters
    ----------
    source_path:
        Video file to process (may lack audio after transitions).
    volume:
        Desired volume level (0.0–2.0).
    output_path:
        Destination path.
    audio_source:
        If provided, mux audio from this file instead of *source_path*.
        Used after ``apply_transitions`` which strips audio (``-an``).
    match_duration:
        If provided, truncate the audio to this duration (seconds) to
        prevent A/V desync after xfade shortens the video.
    """
    ffmpeg = get_ffmpeg_bin()
    filt, muted = build_audio_filter(volume)

    if audio_source:
        # Mux: take video from source_path, audio from audio_source.
        # Use filter_complex with explicit stream labels to avoid
        # ambiguous -af stream selection.
        audio_input_args = ["-i", audio_source]
        if match_duration is not None and match_duration > 0:
            # Truncate audio input to match the xfade'd video length
            audio_input_args = [
                "-t", f"{match_duration:.3f}",
            ] + audio_input_args

        if muted:
            cmd = [
                ffmpeg, "-y",
                "-i", source_path,
            ] + audio_input_args + [
                "-map", "0:v",
                "-c:v", "copy",
                "-an",
                "-v", "warning", output_path,
            ]
        elif filt:
            # Volume change — use filter_complex to target stream 1 audio
            cmd = [
                ffmpeg, "-y",
                "-i", source_path,
            ] + audio_input_args + [
                "-filter_complex", f"[1:a]{filt}[aout]",
                "-map", "0:v",
                "-map", "[aout]",
                "-c:v", "copy",
                "-c:a", "aac", "-b:a", "192k",
                "-v", "warning", output_path,
            ]
        else:
            # No volume change — just mux
            cmd = [
                ffmpeg, "-y",
                "-i", source_path,
            ] + audio_input_args + [
                "-map", "0:v",
                "-map", "1:a?",
                "-c:v", "copy",
                "-c:a", "copy",
                "-v", "warning", output_path,
            ]
    else:
        audio_args = get_audio_args(volume)
        cmd = [
            ffmpeg, "-y",
            "-i", source_path,
            "-c:v", "copy",
        ] + audio_args + ["-v", "warning", output_path]

    result = subprocess.run(
        cmd, capture_output=True, text=True, timeout=300,
    )
    if result.returncode != 0:
        log.warning("[VideoEditor] Audio adjust failed: %s", result.stderr[:300])
        raise RuntimeError(
            f"Audio adjust failed (rc={result.returncode}): {result.stderr[:300]}"
        )

    return output_path


def _settings_match_intermediate(settings: dict) -> bool:
    """Return True when *settings* match the intermediate pipeline defaults.

    Uses ``_EXPORT_DEFAULTS`` from ``export_settings`` as the single source
    of truth — avoids maintaining a duplicate defaults dict.

    When True, the final re-encode step is redundant and can be skipped.
    """
    # Skip "format" — container change doesn't require video re-encode
    # (it's handled by extension adjustment in render_edits).
    for key, default in _EXPORT_DEFAULTS.items():
        if key == "format":
            continue
        if str(settings.get(key, default)) != str(default):
            return False
    return True


def has_speed_changes(speed_map_json: str) -> bool:
    """Check if any segment has a non-1.0 speed."""
    if not speed_map_json or not speed_map_json.strip():
        return False
    try:
        data = json.loads(speed_map_json)
    except (json.JSONDecodeError, TypeError):
        return False
    if not isinstance(data, dict):
        return False
    return any(abs(float(v) - 1.0) > 0.01 for v in data.values())


def _success(output_path: str) -> dict:
    """Build a success result dict."""
    file_size = 0
    duration = 0.0
    try:
        file_size = os.path.getsize(output_path)
    except OSError:
        pass

    # Probe duration
    ffprobe = get_ffprobe_bin()
    try:
        cmd = [
            ffprobe, "-v", "error",
            "-show_entries", "format=duration",
            "-print_format", "csv=p=0",
            output_path,
        ]
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            duration = float(result.stdout.strip())
    except Exception:
        pass

    return {
        "success": True,
        "output_path": output_path,
        "duration": duration,
        "file_size": file_size,
        "error": None,
    }


def _error(message: str) -> dict:
    """Build an error result dict."""
    return {
        "success": False,
        "output_path": "",
        "duration": 0.0,
        "file_size": 0,
        "error": message,
    }
