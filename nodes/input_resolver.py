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
        or len(_all_image_paths) > 0
    )

    if images_a is not None:
        _images_a_shape = images_a.shape
        temp_video_from_images = media_converter.images_to_video(images_a)
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
