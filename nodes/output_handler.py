"""Output handling helpers extracted from FFMPEGAgentNode.

Provides functions for output path determination, audio muxing,
frame collection, thumbnail extraction, workflow PNG saving,
API-key stripping, duration probing, and audio-dict conversion.
"""

import json
import logging
import os
import shutil
import tempfile
from pathlib import Path
from typing import Optional

import torch  # type: ignore[import-not-found]

logger = logging.getLogger("ffmpega")


def build_output_path(
    effective_video_path: str,
    save_output: bool,
    output_path: str,
    preview_mode: bool,
) -> tuple[str, Optional[str]]:
    """Determine output path and optional temp render directory.

    Returns
    -------
    (output_path, temp_render_dir)
    """
    try:
        from ..core.sanitize import (  # type: ignore[import-not-found]
            validate_output_file_path,
            validate_output_path as _validate_output_path,
        )
    except ImportError:
        from core.sanitize import (  # type: ignore
            validate_output_file_path,
            validate_output_path as _validate_output_path,
        )

    import folder_paths  # type: ignore[import-not-found]

    stem = Path(effective_video_path).stem
    suffix = "_preview" if preview_mode else "_edited"
    temp_render_dir = None

    if save_output:
        if not output_path:
            output_dir = folder_paths.get_output_directory()
            output_path = str(Path(output_dir) / f"{stem}{suffix}.mp4")
        elif Path(output_path).is_dir() or output_path.endswith(os.sep):
            output_dir = _validate_output_path(output_path.rstrip(os.sep))
            output_path = str(Path(output_dir) / f"{stem}{suffix}.mp4")
        elif not Path(output_path).suffix:
            output_dir = _validate_output_path(output_path)
            os.makedirs(output_dir, exist_ok=True)
            output_path = str(Path(output_dir) / f"{stem}{suffix}.mp4")
        else:
            output_path = validate_output_file_path(output_path)
    else:
        temp_render_dir = tempfile.mkdtemp(prefix="ffmpega_")
        output_path = str(Path(temp_render_dir) / f"{stem}{suffix}.mp4")

    os.makedirs(Path(output_path).parent, exist_ok=True)
    return output_path, temp_render_dir


def handle_audio_output(
    command,
    pipeline,
    media_converter,
    audio_a,
    audio_source: str,
    audio_mode: str,
    output_path: str,
    **kwargs,
) -> None:
    """Mux or replace audio in the output file as directed by the LLM spec."""
    removes_audio = "-an" in command.output_options
    has_audio_processing = removes_audio or bool(command.audio_filters.to_string())
    audio_already_embedded = pipeline.metadata.get("_has_embedded_audio", False)

    audio_inputs = {}
    if audio_a is not None:
        audio_inputs["audio_a"] = audio_a
    for k in sorted(kwargs):
        if k.startswith("audio_") and k != "audio_a" and kwargs[k] is not None:
            audio_inputs[k] = kwargs[k]

    if audio_source == "mix":
        for step in pipeline.steps:
            step_audio = step.params.get("audio_source")
            if step_audio and step_audio != "mix":
                audio_source = step_audio
                break

    logger.debug(
        "Audio decision: removes=%s, has_processing=%s, "
        "already_embedded=%s, audio_source=%s, available=%s",
        removes_audio, has_audio_processing,
        audio_already_embedded, audio_source, list(audio_inputs.keys()),
    )

    if audio_inputs and not removes_audio and not has_audio_processing and not audio_already_embedded:
        if audio_source and audio_source != "mix" and audio_source in audio_inputs:
            logger.debug("Using specific audio: %s", audio_source)
            media_converter.mux_audio(output_path, audio_inputs[audio_source], audio_mode=audio_mode)
        elif len(audio_inputs) == 1:
            name = list(audio_inputs.keys())[0]
            logger.debug("Using only available audio: %s", name)
            media_converter.mux_audio(output_path, audio_inputs[name], audio_mode=audio_mode)
        else:
            logger.debug("Mixing %d audio tracks: %s", len(audio_inputs), list(audio_inputs.keys()))
            media_converter.mux_audio_mix(output_path, list(audio_inputs.values()), audio_mode=audio_mode)
    elif audio_inputs and audio_already_embedded and not removes_audio:
        if audio_source and audio_source != "mix" and audio_source in audio_inputs:
            logger.info("Replacing concat audio with explicit audio source: %s", audio_source)
            media_converter.mux_audio(output_path, audio_inputs[audio_source], audio_mode="replace")
        elif len(audio_inputs) == 1:
            name = list(audio_inputs.keys())[0]
            logger.info("Replacing concat audio with connected %s", name)
            media_converter.mux_audio(output_path, audio_inputs[name], audio_mode="replace")
        else:
            logger.debug(
                "Multiple audio inputs with embedded audio — skipping "
                "replacement (ambiguous intent)"
            )


def collect_frame_output(
    media_converter,
    output_path: str,
    unique_id: str,
    hidden_prompt: dict,
    removes_audio: bool,
) -> tuple[torch.Tensor, dict]:
    """Extract output frames and audio. Returns (images_tensor, audio_out)."""
    images_connected = False
    if unique_id and hidden_prompt:
        for node_id, node_data in hidden_prompt.items():
            if str(node_id) == unique_id:
                continue
            for inp_val in (node_data.get("inputs") or {}).values():
                if (
                    isinstance(inp_val, list)
                    and len(inp_val) == 2
                    and str(inp_val[0]) == unique_id
                    and inp_val[1] == 0
                ):
                    images_connected = True
                    break
            if images_connected:
                break

    if images_connected:
        logger.info("images output is connected — loading all frames from output video")
        images_tensor = media_converter.frames_to_tensor(output_path)
        logger.debug("Output full frames shape: %s", images_tensor.shape)
    else:
        images_tensor = extract_thumbnail_frame(output_path)
        logger.debug("Output thumbnail shape: %s", images_tensor.shape)

    if removes_audio:
        audio_out = {"waveform": torch.zeros(1, 1, 1, dtype=torch.float32), "sample_rate": 44100}
    else:
        audio_out = media_converter.extract_audio(output_path)

    return images_tensor, audio_out


def extract_thumbnail_frame(video_path: str) -> torch.Tensor:
    """Extract only the first frame from a video as a (1, H, W, 3) tensor.

    This is vastly cheaper than loading all frames (~6 MB vs ~13 GB for
    a typical 74s 1080p video).  The single frame is used for:
     - The IMAGE output (thumbnail preview)
     - The workflow PNG embed
    """
    try:
        import av  # type: ignore[import-not-found]
        container = av.open(video_path)
        for frame in container.decode(video=0):
            arr = frame.to_ndarray(format="rgb24")
            container.close()
            return (
                torch.from_numpy(arr)
                .float()
                .div_(255.0)
                .unsqueeze(0)  # (H,W,3) → (1,H,W,3)
            )
        container.close()
    except Exception:
        pass
    return torch.zeros(1, 64, 64, 3, dtype=torch.float32)


def save_workflow_png(
    first_frame: torch.Tensor,
    png_path: str,
    prompt: Optional[dict],
    extra_pnginfo: Optional[dict],
    extra_info: Optional[dict] = None,
) -> None:
    """Save a first-frame PNG with embedded ComfyUI workflow metadata.

    This allows the PNG to be dragged into ComfyUI to reload the
    workflow, matching the behavior of ComfyUI's SaveImage node.
    """
    from PIL import Image  # type: ignore[import-untyped]
    from PIL.PngImagePlugin import PngInfo
    import numpy as np

    # Convert tensor (H, W, C) float [0,1] -> uint8 PIL Image
    frame_np = (255.0 * first_frame.cpu().numpy()).clip(0, 255).astype(np.uint8)
    img = Image.fromarray(frame_np)

    metadata = PngInfo()
    if prompt is not None:
        metadata.add_text("prompt", json.dumps(prompt))
    if extra_pnginfo is not None:
        for key in extra_pnginfo:
            metadata.add_text(key, json.dumps(extra_pnginfo[key]))
    if extra_info is not None:
        for key, value in extra_info.items():
            metadata.add_text(key, value if isinstance(value, str) else json.dumps(value))

    img.save(png_path, pnginfo=metadata, compress_level=4)


def strip_api_key_from_metadata(
    api_key: str,
    prompt: Optional[dict],
    extra_pnginfo: Optional[dict],
) -> None:
    """Remove api_key values from workflow metadata in-place.

    This prevents API keys from being embedded in output files
    when downstream Save Image/Video nodes serialize the workflow.
    """
    # Strip from the prompt graph (api format — keyed by node id)
    if prompt:
        for node_id, node_data in prompt.items():
            inputs = node_data.get("inputs", {})
            if "api_key" in inputs:
                inputs["api_key"] = ""

    # Strip from the workflow JSON (drag-drop format)
    if extra_pnginfo and "workflow" in extra_pnginfo:
        workflow = extra_pnginfo["workflow"]
        for node in workflow.get("nodes", []):
            # widgets_values is a positional array — scan for the
            # actual key value and replace it
            widgets = node.get("widgets_values", [])
            if isinstance(widgets, list):
                for i, val in enumerate(widgets):
                    if val == api_key:
                        widgets[i] = ""


def audio_dict_to_wav(audio: dict) -> Optional[str]:
    """Convert a ComfyUI AUDIO dict to a temporary WAV file.

    Args:
        audio: ComfyUI AUDIO dict with 'waveform' and 'sample_rate'.

    Returns:
        Path to the created temporary WAV file, or None on failure.
    """
    import subprocess

    try:
        waveform = audio["waveform"]       # (1, channels, samples)
        sample_rate = audio["sample_rate"]
    except (KeyError, TypeError):
        return None

    channels = waveform.size(1)
    audio_data = waveform.squeeze(0).transpose(0, 1).contiguous()  # (samples, channels)
    audio_bytes = (audio_data * 32767.0).clamp(-32768, 32767).to(torch.int16).numpy().tobytes()

    tmp_wav = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp_wav.close()

    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        return None

    result = subprocess.run(
        [
            ffmpeg_bin, "-y",
            "-f", "s16le",
            "-ar", str(sample_rate),
            "-ac", str(channels),
            "-i", "-",
            tmp_wav.name,
        ],
        input=audio_bytes,
        capture_output=True,
    )
    if result.returncode != 0:
        if os.path.exists(tmp_wav.name):
            os.remove(tmp_wav.name)
        return None

    return tmp_wav.name


def probe_duration(video_path: str) -> float:
    """Probe the duration of a video file using ffprobe.

    Returns:
        Duration in seconds, or 0.0 if probing fails.
    """
    import subprocess
    ffprobe_bin = shutil.which("ffprobe")
    if not ffprobe_bin:
        return 0.0
    try:
        try:
            from ..core.sanitize import validate_video_path
        except ImportError:
            from core.sanitize import validate_video_path  # type: ignore
        video_path = validate_video_path(str(video_path))
        result = subprocess.run(
            [ffprobe_bin, "-v", "error", "-show_entries",
             "format=duration", "-of", "default=noprint_wrappers=1:nokey=1",
             video_path],
            capture_output=True, text=True, check=True,
        )
        return float(result.stdout.strip())
    except Exception:
        return 0.0
