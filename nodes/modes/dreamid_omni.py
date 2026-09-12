# coding: utf-8
"""No-LLM mode: dreamid omni.

Moved verbatim from nodes/nollm_modes.py, which is now a re-export facade.
"""

from __future__ import annotations

from ._shared import (
    Optional,
    build_output_path,
    collect_frame_output,
    logger,
    os,
    shutil,
    tempfile,
    torch,
)


async def process_dreamid_omni_only(
    # parameters
    prompt: str,
    effective_video_path: str,
    video_metadata,
    save_output: bool,
    output_path: str,
    preview_mode: bool,
    quality_preset: str,
    crf: int,
    encoding_preset: str,
    image_a=None,
    audio_a=None,
    temp_video_from_images: Optional[str] = None,
    temp_video_with_audio: Optional[str] = None,
    **kwargs,
) -> tuple[torch.Tensor, dict, str, str, str, str]:
    """Run DreamID-Omni identity-preserving talking-head video generation without LLM.

    Requires face image(s) on image_a and reference audio on audio_a.
    The prompt describes the scene/action for the generated video.

    Returns the standard 6-tuple:
        (images_tensor, audio, output_path, command_log, analysis, mask_overlay_path)
    """
    logger.info("DreamID-Omni mode: prompt=%r", prompt)

    # --- Extract DreamID parameters from kwargs ---
    dreamid_resolution = kwargs.get("dreamid_resolution", "auto")
    dreamid_precision = kwargs.get("dreamid_precision", "auto")
    dreamid_steps = int(kwargs.get("dreamid_steps", 50))
    dreamid_seed = int(kwargs.get("dreamid_seed", 100))
    dreamid_solver = kwargs.get("dreamid_solver", "unipc")
    dreamid_video_cfg = float(kwargs.get("dreamid_video_cfg", 3.0))
    dreamid_video_ref_cfg = float(kwargs.get("dreamid_video_ref_cfg", 1.5))
    dreamid_audio_cfg = float(kwargs.get("dreamid_audio_cfg", 4.0))
    dreamid_audio_ref_cfg = float(kwargs.get("dreamid_audio_ref_cfg", 2.0))

    # --- Import DreamID-Omni synthesizer ---
    try:
        try:
            from ...core.dreamid_omni_synthesizer import (
                generate_video as _dreamid_generate,
                cleanup as _dreamid_cleanup,
                _audio_dict_to_wav,
                _tensor_to_image,
            )
        except ImportError:
            from core.dreamid_omni_synthesizer import (  # type: ignore
                generate_video as _dreamid_generate,
                cleanup as _dreamid_cleanup,
                _audio_dict_to_wav,
                _tensor_to_image,
            )
    except ImportError:
        raise RuntimeError(
            "DreamID-Omni is not available. "
            "Ensure core/dreamid_omni_synthesizer.py "
            "and core/dreamid_omni/ exist."
        )

    # --- Validate inputs ---
    if image_a is None:
        raise RuntimeError(
            "DreamID-Omni requires at least one face reference image. "
            "Connect a face image to image_a."
        )
    if audio_a is None:
        raise RuntimeError(
            "DreamID-Omni requires reference audio. "
            "Connect an audio clip to audio_a."
        )

    # --- Build output path ---
    output_path, temp_render_dir = build_output_path(
        effective_video_path=effective_video_path,
        save_output=save_output,
        output_path=output_path,
        preview_mode=preview_mode,
    )

    # --- Convert image_a tensor → temp PNG files ---
    import numpy as _np
    face_image_paths = []
    temp_files = []
    try:
        if hasattr(image_a, 'shape') and len(image_a.shape) == 4:
            # Batch: [B, H, W, C]
            for idx in range(min(image_a.shape[0], 2)):  # Max 2 faces
                tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
                tmp.close()
                _tensor_to_image(image_a[idx], tmp.name)
                face_image_paths.append(tmp.name)
                temp_files.append(tmp.name)
        elif hasattr(image_a, 'shape') and len(image_a.shape) == 3:
            # Single: [H, W, C]
            tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
            tmp.close()
            _tensor_to_image(image_a, tmp.name)
            face_image_paths.append(tmp.name)
            temp_files.append(tmp.name)

        if not face_image_paths:
            raise RuntimeError("Could not extract face images from image_a tensor")

        logger.info("DreamID-Omni: %d face image(s) extracted", len(face_image_paths))

        # --- Convert audio_a AUDIO dict → temp WAV ---
        audio_wav = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        audio_wav.close()
        _audio_dict_to_wav(audio_a, audio_wav.name)
        audio_paths = [audio_wav.name]
        temp_files.append(audio_wav.name)
        logger.info("DreamID-Omni: audio extracted to %s", audio_wav.name)

        # --- Generate ---
        generated_path = _dreamid_generate(
            prompt=prompt or "",
            face_image_paths=face_image_paths,
            audio_paths=audio_paths,
            output_path=output_path,
            resolution_preset=dreamid_resolution,
            seed=dreamid_seed,
            steps=dreamid_steps,
            solver_name=dreamid_solver,
            shift=5.0,
            video_cfg_scale=dreamid_video_cfg,
            video_ref_cfg_scale=dreamid_video_ref_cfg,
            audio_cfg_scale=dreamid_audio_cfg,
            audio_ref_cfg_scale=dreamid_audio_ref_cfg,
            precision=dreamid_precision,
        )
        output_path = generated_path

        cmd_log = f"dreamid_omni generate_video → {output_path}"

    except Exception as e:
        logger.error("DreamID-Omni mode failed: %s", e)
        try:
            _dreamid_cleanup()
        except Exception:
            pass
        raise RuntimeError(f"DreamID-Omni generation failed: {e}") from e

    finally:
        # Clean up temp face/audio files
        for fp in temp_files:
            try:
                if os.path.exists(fp):
                    os.remove(fp)
            except OSError:
                pass

    try:
        # --- Collect frame/audio output ---
        try:
            try:
                from ...core.media_converter import MediaConverter
            except ImportError:
                from core.media_converter import MediaConverter  # type: ignore
            media_converter = MediaConverter()
        except Exception:
            media_converter = None

        unique_id = str(kwargs.get("unique_id", ""))
        hidden_prompt = kwargs.get("hidden_prompt") or {}
        images_tensor, audio_out = collect_frame_output(
            media_converter=media_converter,
            output_path=output_path,
            unique_id=unique_id,
            hidden_prompt=hidden_prompt,
            removes_audio=False,
        )

        # --- Build analysis string ---
        analysis = (
            f"⚠️ DreamID-Omni Mode (WIP / Experimental)\n"
            f"Resolution: {dreamid_resolution}\n"
            f"Steps: {dreamid_steps}\n"
            f"Seed: {dreamid_seed}\n"
            f"Solver: {dreamid_solver}\n"
            f"Video CFG: {dreamid_video_cfg}\n"
            f"Video Ref CFG: {dreamid_video_ref_cfg}\n"
            f"Audio CFG: {dreamid_audio_cfg}\n"
            f"Audio Ref CFG: {dreamid_audio_ref_cfg}\n"
            f"Faces: {len(face_image_paths)}\n"
            f"Prompt: {prompt or '(none)'}\n\n"
            f"Output: {output_path}"
        )

        return (images_tensor, audio_out, output_path, cmd_log, analysis, "")
    finally:
        # --- Cleanup temp files (always runs, even on error) ---
        for tmp_path in [temp_video_from_images, temp_video_with_audio]:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
        if not save_output and temp_render_dir and os.path.isdir(temp_render_dir):
            if not os.listdir(temp_render_dir):
                shutil.rmtree(temp_render_dir, ignore_errors=True)
