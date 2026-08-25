"""Input resolution helpers extracted from FFMPEGAgentNode.

Provides ``resolve_inputs()`` and ``build_connected_inputs_summary()``
which were formerly ``_resolve_inputs`` and ``_build_connected_inputs_summary``
on the agent node class.
"""

import gc
import json
import logging
import os
import tempfile
from typing import Optional

logger = logging.getLogger("ffmpega")

# Used when frames arrive with no source video to take a rate from. An IMAGE
# batch genuinely has no frame rate, so this is a display convention, not a
# measurement — the downstream Save Video node's fps widget is what decides
# the rate of anything the user actually keeps.
DEFAULT_IMAGE_SEQUENCE_FPS = 24.0


def _source_fps(video_path: str, extra_video_paths: list) -> float:
    """Frame rate of the first readable source video, or the default.

    Frames connected alongside a source video (the usual Load Video Path →
    Agent wiring) should keep that video's rate rather than silently becoming
    24 fps.
    """
    candidates = []
    if video_path and str(video_path).strip():
        candidates.append(str(video_path).strip())
    candidates.extend(extra_video_paths or [])

    try:
        from ..core.last_frame import probe_video_stats
    except ImportError:
        from core.last_frame import probe_video_stats  # type: ignore

    for candidate in candidates:
        if not candidate or not os.path.isfile(candidate):
            continue
        try:
            fps, _duration, _frames = probe_video_stats(candidate)
        except Exception:
            continue
        if fps and fps > 0:
            logger.info(
                "resolve_inputs: images have no frame rate; using %.3f fps "
                "from %s", fps, os.path.basename(candidate),
            )
            return float(fps)

    return DEFAULT_IMAGE_SEQUENCE_FPS


def resolve_inputs(
    media_converter,
    video_path: str,
    images_a,
    image_a,
    image_path_a: str,
    video_a: str,
    text_a: str,
    subtitle_path: str,
    audio_a,
    **kwargs,
):
    """Resolve all input types and return effective_video_path plus
    collected extras.

    Parameters
    ----------
    media_converter : MediaConverter
        Instance used for images→video conversion and audio checks.

    Returns
    -------
    tuple of:
        effective_video_path (str),
        temp_video_from_images (str | None),
        temp_video_with_audio (str | None),
        _all_video_paths (list[str]),
        _all_image_paths (list[str]),
        _all_text_inputs (list[str]),
        _images_a_shape (tuple | None),  -- shape before tensor was freed
    """
    temp_video_from_images = None
    temp_video_with_audio = None
    _images_a_shape = None

    # Collect all video_* path inputs
    _all_video_paths = []
    if video_a and video_a.strip() and os.path.isfile(video_a.strip()):
        _all_video_paths.append(video_a.strip())
    for k in sorted(kwargs):
        if k.startswith("video_") and k not in ("video_folder", "video_path") and kwargs[k]:
            vp = str(kwargs[k]).strip()
            if vp and os.path.isfile(vp):
                _all_video_paths.append(vp)

    # Collect all image_path_* inputs
    _all_image_paths = []
    if image_path_a and image_path_a.strip() and os.path.isfile(image_path_a.strip()):
        _all_image_paths.append(image_path_a.strip())
    for k in sorted(kwargs):
        if k.startswith("image_path_") and kwargs[k]:
            ip = str(kwargs[k]).strip()
            if ip and os.path.isfile(ip):
                _all_image_paths.append(ip)

    # Collect all text_* inputs
    _all_text_inputs = []
    if text_a and text_a.strip():
        _all_text_inputs.append(text_a.strip())
    for k in sorted(kwargs):
        if k.startswith("text_") and kwargs[k]:
            tv = str(kwargs[k]).strip()
            if tv:
                _all_text_inputs.append(tv)
    if subtitle_path and subtitle_path.strip():
        sp = subtitle_path.strip()
        if os.path.isfile(sp):
            _all_text_inputs.insert(0, json.dumps({
                "text": "",
                "mode": "subtitle",
                "path": sp,
                "position": "bottom_center",
                "font_size": 24,
                "font_color": "white",
                "start_time": 0.0,
                "end_time": -1.0,
                "auto_mode": True,
            }))

    has_extra_images = (
        image_a is not None
        or any(k.startswith("image_") and not k.startswith("image_path_") and kwargs.get(k) is not None for k in kwargs)
        or len(_all_video_paths) > 0
        # NOTE: _all_image_paths intentionally excluded — image_path_a/b/c
        # are reference images or masks for specific modes, not video content.
        # Including them here incorrectly triggers dummy video creation when
        # the only connection is e.g. a mask path for video matting.
    )

    if images_a is not None:
        _images_a_shape = images_a.shape
        # Frames alone carry no frame rate, so the intermediate would be
        # stamped with images_to_video's 24 fps default. Frame *count* is
        # preserved either way, but the agent's video_path output inherits
        # this rate — wrong for 30/60 fps footage. Take the real rate from a
        # connected source video when there is one.
        _src_fps = _source_fps(video_path, _all_video_paths)
        temp_video_from_images = media_converter.images_to_video(
            images_a, fps=_src_fps,
        )
        effective_video_path = temp_video_from_images
        del images_a
        gc.collect()
        try:
            import torch as _torch
            if _torch.cuda.is_available():
                _torch.cuda.empty_cache()
        except Exception:
            pass
    elif video_path and video_path.strip():
        effective_video_path = video_path
    elif _all_video_paths:
        effective_video_path = _all_video_paths.pop(0)
    elif _all_image_paths:
        # No video / images tensor connected — a still image is the primary
        # source (e.g. image_path_a -> ai_upscale / rembg / image edit). Pop it
        # so it is not also re-used as a reference/overlay downstream.
        effective_video_path = _all_image_paths.pop(0)
        logger.info("No video input — using image_path as primary source: %s", effective_video_path)
    elif has_extra_images:
        dummy = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
        dummy.close()
        import subprocess
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i",
             "color=c=black:s=1920x1080:d=1:r=25",
             "-c:v", "libx264", "-t", "1", dummy.name],
            capture_output=True,
        )
        temp_video_from_images = dummy.name
        effective_video_path = dummy.name
    else:
        # No video, images, or extra media — generate a minimal black video
        # so audio-only modes (generate_sample, ace_step, etc.) still work.
        if not video_path or not video_path.strip():
            # Calculate duration from audio_a if available, otherwise default to 1s
            dummy_dur = 1
            if audio_a is not None and isinstance(audio_a, dict):
                try:
                    wf = audio_a.get("waveform")
                    sr = audio_a.get("sample_rate", 44100)
                    if wf is not None and sr:
                        # Audio duration + 10s safety buffer for effects that
                        # lengthen audio (e.g. reverb tails, loudnorm padding)
                        dummy_dur = max(1, int(wf.shape[-1] / sr) + 10)
                except Exception:
                    pass
            dummy = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
            dummy.close()
            import subprocess
            subprocess.run(
                ["ffmpeg", "-y", "-f", "lavfi", "-i",
                 f"color=c=black:s=1920x1080:d={dummy_dur}:r=25",
                 "-c:v", "libx264", "-t", str(dummy_dur), dummy.name],
                capture_output=True,
            )
            temp_video_from_images = dummy.name
            effective_video_path = dummy.name
            logger.info("No video input — created dummy black video for audio-only mode (%ds)", dummy_dur)
        else:
            effective_video_path = video_path

    try:
        from ..core.sanitize import validate_video_path  # type: ignore[import-not-found]
    except ImportError:
        from core.sanitize import validate_video_path  # type: ignore
    effective_video_path = validate_video_path(effective_video_path)

    # Pre-mux audio into the video if it has no audio stream
    if audio_a is not None and not media_converter.has_audio_stream(effective_video_path):
        tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
        tmp.close()
        import shutil as _shmod
        _shmod.copy2(effective_video_path, tmp.name)
        media_converter.mux_audio(tmp.name, audio_a)
        temp_video_with_audio = tmp.name
        effective_video_path = tmp.name

    return (
        effective_video_path,
        temp_video_from_images,
        temp_video_with_audio,
        _all_video_paths,
        _all_image_paths,
        _all_text_inputs,
        _images_a_shape,
    )


def build_connected_inputs_summary(
    images_a,
    _images_a_shape,
    video_path: str,
    audio_a,
    image_a,
    _all_video_paths: list,
    _all_image_paths: list,
    _all_text_inputs: list,
    video_metadata,
    **kwargs,
) -> str:
    """Build the connected-inputs context string sent to the LLM."""
    input_lines = []

    if images_a is not None:
        dur = (video_metadata.primary_video.duration
               if video_metadata.primary_video and video_metadata.primary_video.duration else "unknown")
        fps = (video_metadata.primary_video.frame_rate
               if video_metadata.primary_video and video_metadata.primary_video.frame_rate else "unknown")
        input_lines.append(
            f"- images_a (video): connected — primary video input, "
            f"{images_a.shape[0]} frames, {dur}s, {fps}fps"
        )
    elif _images_a_shape is not None:
        dur = (video_metadata.primary_video.duration
               if video_metadata.primary_video and video_metadata.primary_video.duration else "unknown")
        fps = (video_metadata.primary_video.frame_rate
               if video_metadata.primary_video and video_metadata.primary_video.frame_rate else "unknown")
        input_lines.append(
            f"- images_a (video): connected — primary video input, "
            f"{_images_a_shape[0]} frames, {dur}s, {fps}fps"
        )
    elif video_path and video_path.strip():
        input_lines.append("- video_path: connected — file input")

    for k in sorted(kwargs):
        if k.startswith("images_") and k != "images_a" and kwargs[k] is not None:
            tensor = kwargs[k]
            input_lines.append(f"- {k} (video): connected — {tensor.shape[0]} frames")

    for vi, vp in enumerate(_all_video_paths):
        letter = chr(ord('a') + vi)
        input_lines.append(f"- video_{letter} (video file): connected — {vp}")

    if audio_a is not None:
        sr = audio_a.get("sample_rate", "unknown")
        wf = audio_a.get("waveform")
        dur_str = "unknown"
        if wf is not None and sr and sr != "unknown":
            dur_str = f"{wf.shape[-1] / sr:.1f}s"
        input_lines.append(f"- audio_a: connected — {dur_str}, {sr}Hz")
    for k in sorted(kwargs):
        if k.startswith("audio_") and k != "audio_a" and kwargs[k] is not None:
            ad = kwargs[k]
            sr = ad.get("sample_rate", "unknown")
            wf = ad.get("waveform")
            dur_str = "unknown"
            if wf is not None and sr and sr != "unknown":
                dur_str = f"{wf.shape[-1] / sr:.1f}s"
            input_lines.append(f"- {k}: connected — {dur_str}, {sr}Hz")

    if image_a is not None:
        input_lines.append(
            f"- image_a: connected — single image "
            f"{image_a.shape[2]}x{image_a.shape[1]}"
        )
    for k in sorted(kwargs):
        if (k.startswith("image_") and k != "image_a"
                and not k.startswith("images_")
                and not k.startswith("image_path_")
                and kwargs[k] is not None):
            img = kwargs[k]
            input_lines.append(
                f"- {k}: connected — single image {img.shape[2]}x{img.shape[1]}"
            )

    for ii, ip in enumerate(_all_image_paths):
        letter = chr(ord('a') + ii)
        input_lines.append(f"- image_path_{letter} (image file): connected — {ip}")

    for ti, raw_text in enumerate(_all_text_inputs):
        letter = chr(ord('a') + ti)
        try:
            meta = json.loads(raw_text)
            if isinstance(meta, dict) and "mode" in meta:
                mode = meta.get("mode", "raw")
                text_preview = meta.get("text", "")[:60]
                path = meta.get("path", "")
                if path:
                    input_lines.append(
                        f"- text_{letter} ({mode}): connected — subtitle file: {path}"
                    )
                else:
                    input_lines.append(
                        f"- text_{letter} ({mode}): connected — "
                        f"\"{text_preview}{'...' if len(meta.get('text', '')) > 60 else ''}\" "
                        f"({len(meta.get('text', ''))} chars)"
                    )
                continue
        except (json.JSONDecodeError, TypeError):
            pass
        preview = raw_text[:60]
        input_lines.append(
            f"- text_{letter} (raw text): connected — "
            f"\"{preview}{'...' if len(raw_text) > 60 else ''}\" "
            f"({len(raw_text)} chars)"
        )

    return "\n".join(input_lines) if input_lines else "No extra inputs connected"
