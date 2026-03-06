"""Batch video processing extracted from FFMPEGAgentNode.

Provides ``process_batch()`` which was formerly ``_process_batch``
on the agent node class.
"""

import glob
import logging
import os
import shutil
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

import torch  # type: ignore[import-not-found]

logger = logging.getLogger("ffmpega")


async def process_batch(
    # dependencies (injected from agent node)
    analyzer,
    composer,
    process_manager,
    pipeline_generator,
    media_converter,
    # parameters
    video_folder: str,
    file_pattern: str,
    prompt: str,
    llm_model: str,
    quality_preset: str,
    ollama_url: str,
    api_key: str,
    custom_model: str,
    crf: int,
    encoding_preset: str,
    max_concurrent: int,
    save_output: bool,
    output_path: str,
    use_vision: bool = False,
    verify_output: bool = False,
    ptc_mode: str = "off",
    sam3_max_objects: int = 5,
    sam3_det_threshold: float = 0.7,
    mask_points: str = "",
    pipeline_json: str = "",
    use_flux_klein: bool = False,
    flux_smoothing: str = "none",
) -> tuple[torch.Tensor, dict, str, str, str, str]:
    """Process all matching videos in a folder with the same pipeline.

    Uses one LLM call to generate the pipeline, then applies it to
    every video concurrently via ThreadPoolExecutor.
    """
    import json

    try:
        from ..skills.composer import Pipeline  # type: ignore[import-not-found]
        from ..core.sanitize import validate_video_path as _validate, validate_output_path as _validate_out
    except ImportError:
        from skills.composer import Pipeline  # type: ignore
        from core.sanitize import validate_video_path as _validate, validate_output_path as _validate_out  # type: ignore

    import folder_paths  # type: ignore[import-not-found]

    # --- Validate folder ---
    folder = Path(video_folder)
    if not folder.exists() or not folder.is_dir():
        raise ValueError(f"Batch mode: video_folder not found or not a directory: {video_folder}")

    if not prompt.strip():
        raise ValueError("Prompt cannot be empty")

    # --- Discover videos ---
    patterns = file_pattern.split()
    video_files = []
    for pat in patterns:
        video_files.extend(glob.glob(str(folder / pat)))
    video_files = sorted(set(video_files))

    valid_files = []
    for vf in video_files:
        try:
            _validate(vf)
            valid_files.append(vf)
        except ValueError:
            pass

    if not valid_files:
        raise ValueError(
            f"Batch mode: no valid video files matching '{file_pattern}' in {video_folder}"
        )

    # --- Output folder ---
    if save_output and output_path:
        out_dir = Path(_validate_out(output_path))
    elif save_output:
        out_dir = Path(folder_paths.get_output_directory()) / "ffmpega_batch"
    else:
        out_dir = Path(tempfile.mkdtemp(prefix="ffmpega_batch_"))
    out_dir.mkdir(parents=True, exist_ok=True)

    # --- Generate pipeline via LLM (once from sample) ---
    sample_video = valid_files[0]
    video_metadata = analyzer.analyze(sample_video)
    metadata_str = video_metadata.to_analysis_string()

    if not ollama_url or not ollama_url.startswith(("http://", "https://")):
        ollama_url = "http://localhost:11434"
    effective_model = llm_model
    if llm_model == "custom":
        if not custom_model or not custom_model.strip():
            raise ValueError(
                "Please enter a model name in the 'custom_model' field "
                "when using 'custom' mode."
            )
        effective_model = custom_model.strip()

    connected_inputs_str = f"Batch mode: {len(valid_files)} videos in {video_folder}"
    connector = pipeline_generator.create_connector(effective_model, ollama_url, api_key)
    try:
        spec = await pipeline_generator.generate(
            connector, prompt, metadata_str,
            connected_inputs=connected_inputs_str,
            video_path=valid_files[0] if valid_files else "",
            use_vision=use_vision,
            ptc_mode=ptc_mode,
        )
    finally:
        if hasattr(connector, 'close'):
            await connector.close()

    pipeline_steps = spec.get("pipeline", [])
    interpretation = spec.get("interpretation", "")

    # --- Quality preset ---
    crf_map = {"draft": 28, "standard": 23, "high": 18, "lossless": 0}
    preset_map = {"draft": "ultrafast", "standard": "medium", "high": "slow", "lossless": "veryslow"}
    effective_crf = crf if crf >= 0 else crf_map.get(quality_preset, 23)
    effective_preset = encoding_preset if encoding_preset != "auto" else preset_map.get(quality_preset, "medium")

    # --- Process each video ---
    output_paths = []
    errors = []
    command_logs = []

    def process_single(vpath: str) -> tuple[str, str | None, str]:
        """Process one video file."""
        try:
            stem = Path(vpath).stem
            out_file = str(out_dir / f"{stem}_edited.mp4")

            pipeline = Pipeline(input_path=vpath, output_path=out_file)
            pipeline.metadata["_sam3_max_objects"] = sam3_max_objects
            pipeline.metadata["_sam3_det_threshold"] = sam3_det_threshold
            if mask_points and mask_points.strip():
                pipeline.metadata["_mask_points"] = mask_points.strip()
            pipeline.metadata["_enable_flux_klein"] = use_flux_klein
            if flux_smoothing and flux_smoothing != "none":
                pipeline.metadata["_flux_smoothing"] = flux_smoothing
            for step in pipeline_steps:
                skill_name = step.get("skill")
                params = step.get("params", {})
                if skill_name:
                    pipeline.add_step(skill_name, params)

            pipeline.add_step("quality", {
                "crf": effective_crf,
                "preset": effective_preset,
            })

            command = composer.compose(pipeline)
            result = process_manager.execute(command, timeout=600)

            if result.success:
                return (out_file, None, command.to_string())
            else:
                return (out_file, result.error_message, command.to_string())
        except Exception as e:
            return (vpath, str(e), "")

    with ThreadPoolExecutor(max_workers=max_concurrent) as executor:
        futures = {
            executor.submit(process_single, vf): vf
            for vf in valid_files
        }
        for future in as_completed(futures):
            vf = futures[future]
            try:
                out_file, error, cmd_log = future.result()
                if error:
                    errors.append(f"{Path(vf).name}: {error}")
                else:
                    output_paths.append(out_file)
                if cmd_log:
                    command_logs.append(f"[{Path(vf).name}] {cmd_log}")
            except Exception as e:
                errors.append(f"{Path(vf).name}: {str(e)}")

    # --- Build results ---
    processed = len(output_paths)
    failed = len(errors)
    total = len(valid_files)

    # Return the last successful video as frames, or a placeholder
    last_path = output_paths[-1] if output_paths else valid_files[0]
    frames_tensor = media_converter.frames_to_tensor(last_path)
    audio_dict = media_converter.extract_audio(last_path)

    paths_json = json.dumps(output_paths, indent=2)

    # Per-file status table
    status_lines = [
        f"Batch complete: {processed}/{total} succeeded, {failed} failed.",
        f"Output folder: {out_dir}",
        "",
        "File results:",
    ]
    # Map each source filename stem -> actual output path for reporting
    _stem_to_out: dict[str, str] = {Path(p).stem.replace("_edited", ""): p
                                     for p in output_paths}
    for vf in valid_files:
        stem = Path(vf).stem
        actual_out = _stem_to_out.get(stem)
        if actual_out is not None:
            # Successful — show output size if available
            try:
                size_kb = Path(actual_out).stat().st_size // 1024
                status_lines.append(f"  ✓ {Path(vf).name} → {Path(actual_out).name} ({size_kb:,} KB)")
            except OSError:
                status_lines.append(f"  ✓ {Path(vf).name} → {Path(actual_out).name}")
        else:
            # Find the error message for this file (default if no match)
            err_msg = next(
                ((e.split(": ", 1)[1] if ": " in e else e)
                 for e in errors
                 if e.startswith(Path(vf).name)),
                "unknown error",
            )
            status_lines.append(f"  ✗ {Path(vf).name}: {err_msg}")

    analysis = (
        f"Batch Mode — {interpretation}\n\n"
        + "\n".join(status_lines)
    )

    command_log = "\n\n".join(command_logs) if command_logs else "No commands executed"

    # --- Cleanup batch temp directory ---
    if not save_output and out_dir and out_dir.exists():
        try:
            shutil.rmtree(str(out_dir), ignore_errors=True)
        except OSError:
            pass

    return (frames_tensor, audio_dict, paths_json, command_log, analysis, "")
