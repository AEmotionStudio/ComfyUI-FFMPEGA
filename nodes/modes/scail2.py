# coding: utf-8
"""No-LLM mode: scail2.

Moved verbatim from nodes/nollm_modes.py, which is now a re-export facade.
"""

from __future__ import annotations

from ._shared import (
    build_output_path,
    collect_frame_output,
    json,
    logger,
    os,
    shutil,
    tempfile,
    torch,
)


async def process_scail2_only(
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
    **kwargs,
) -> tuple[torch.Tensor, dict, str, str, str, str]:
    """Run native SCAIL-2 pose-driven character animation without an LLM.

    Requires:
    - Reference character image on ``image_a`` (or ``image_path_a``)
    - Driving/pose video on ``effective_video_path``

    SAM 3.1 tracks the subject(s) (driven by ``prompt``/``mask_points``) in both
    the driving video and the reference image; the colored masks feed the native
    ``WanSCAILToVideo`` conditioning. Returns the standard 6-tuple with the
    colored pose-video mask in the ``mask_overlay_path`` slot so a second Save
    Video node can save it:
        (images_tensor, audio, output_path, command_log, analysis, mask_video_path)
    """
    logger.info("SCAIL2 mode: prompt=%r", prompt)

    # --- Parameters from advanced widgets ---
    scail2_steps = int(kwargs.get("scail2_steps", 6))
    scail2_cfg = float(kwargs.get("scail2_cfg", 1.0))
    scail2_shift = float(kwargs.get("scail2_shift", 5.0))
    scail2_length = int(kwargs.get("scail2_length", 81))
    scail2_width = int(kwargs.get("scail2_width", 512))
    scail2_height = int(kwargs.get("scail2_height", 896))
    scail2_seed = int(kwargs.get("scail2_seed", kwargs.get("seed", 0)))
    scail2_sampler = str(kwargs.get("scail2_sampler", "euler"))
    scail2_scheduler = str(kwargs.get("scail2_scheduler", "simple"))
    scail2_denoise = float(kwargs.get("scail2_denoise", 1.0))
    scail2_replacement = bool(kwargs.get("scail2_replacement_mode", False))
    scail2_sort_by = str(kwargs.get("scail2_sort_by", "left_to_right"))
    scail2_object_indices = str(kwargs.get("scail2_object_indices", ""))
    scail2_subject = str(kwargs.get("scail2_subject", "person")).strip()
    scail2_max_objects = int(kwargs.get("scail2_max_objects", 1))
    scail2_det_threshold = float(kwargs.get("scail2_detection_threshold", 0.5))
    scail2_detect_interval = int(kwargs.get("scail2_detect_interval", 2))
    scail2_point_src_w = int(kwargs.get("scail2_point_src_width", 0))
    scail2_point_src_h = int(kwargs.get("scail2_point_src_height", 0))
    scail2_composite_direction = str(kwargs.get("scail2_composite_direction", "horizontal"))
    scail2_main_reference = str(kwargs.get("scail2_main_reference", "last"))
    scail2_color_match = bool(kwargs.get("scail2_color_match", False))
    scail2_pose_extend = str(kwargs.get("scail2_pose_extend", "pingpong"))
    scail2_blockswap = int(kwargs.get("scail2_blockswap_blocks", 0))
    scail2_tiled_vae = bool(kwargs.get("scail2_tiled_vae", False))

    # --- Import SCAIL-2 synthesizer ---
    try:
        from ...core.scail2_synthesizer import (
            generate_video as _scail2_generate, cleanup as _scail2_cleanup,
        )
    except ImportError:
        try:
            from core.scail2_synthesizer import (  # type: ignore
                generate_video as _scail2_generate, cleanup as _scail2_cleanup,
            )
        except ImportError as exc:
            raise RuntimeError(
                "SCAIL-2 is not available. Ensure core/scail2_synthesizer.py "
                "exists and ComfyUI ships comfy_extras/nodes_scail.py."
            ) from exc

    # --- Validate inputs (image_a tensor or image_path_a file) ---
    image_path_a = kwargs.get("image_path_a", "")
    if image_a is None and image_path_a and os.path.isfile(image_path_a.strip()):
        image_a = image_path_a.strip()
        logger.info("SCAIL2: using image_path_a as reference: %s", image_a)
    if image_a is None:
        raise RuntimeError(
            "SCAIL-2 requires a reference character image. "
            "Connect an image to image_a or image_path_a.")
    if not effective_video_path or not os.path.isfile(effective_video_path):
        raise RuntimeError(
            "SCAIL-2 requires a driving/pose video. Connect a video input.")

    # --- Parse point prompts (from the JS point selector) ---
    sam_points = sam_labels = None
    point_src_w = point_src_h = 0
    mask_points = kwargs.get("mask_points", "")
    if mask_points and str(mask_points).strip():
        try:
            pt_data = json.loads(mask_points)
            if isinstance(pt_data, dict):
                sam_points = pt_data.get("points")
                sam_labels = pt_data.get("labels")
                point_src_w = int(pt_data.get("image_width", 0))
                point_src_h = int(pt_data.get("image_height", 0))
        except (ValueError, TypeError) as exc:
            logger.warning("SCAIL2: failed to parse mask_points JSON: %s", exc)
    # Manual point-source overrides (0 = keep the value from the point selector).
    if scail2_point_src_w > 0:
        point_src_w = scail2_point_src_w
    if scail2_point_src_h > 0:
        point_src_h = scail2_point_src_h

    # --- Collect LoRA entries from dynamic slots (a → d) ---
    lora_entries = []  # list of (path, strength)
    lora_log = ""
    for slot in ("a", "b", "c", "d"):
        lora_name = str(kwargs.get(f"scail2_lora_{slot}", "none"))
        if not lora_name or lora_name == "none":
            break
        lora_strength = float(kwargs.get(f"scail2_lora_strength_{slot}", 1.0))
        lora_path = None
        try:
            import folder_paths  # type: ignore
            lora_path = folder_paths.get_full_path("loras", lora_name)
        except Exception:
            lora_path = None
        if lora_path:
            lora_entries.append((lora_path, lora_strength))
            lora_log += f"LoRA {slot.upper()}: {lora_name} (strength={lora_strength})\n"
        else:
            lora_log += f"⚠️ LoRA {slot.upper()} not found: {lora_name} — skipping\n"

    # --- Build output path ---
    output_path, temp_render_dir = build_output_path(
        effective_video_path=effective_video_path,
        save_output=save_output,
        output_path=output_path,
        preview_mode=preview_mode,
    )

    # --- Convert image_a tensor → temp PNG file ---
    import numpy as _np
    ref_image_path = None
    temp_files = []
    try:
        if hasattr(image_a, "shape") and len(image_a.shape) == 4:
            tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
            tmp.close()
            from PIL import Image
            arr = (image_a[0].cpu().numpy() * 255).clip(0, 255).astype(_np.uint8)
            Image.fromarray(arr).save(tmp.name)
            ref_image_path = tmp.name
            temp_files.append(tmp.name)
        elif hasattr(image_a, "shape") and len(image_a.shape) == 3:
            tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
            tmp.close()
            from PIL import Image
            arr = (image_a.cpu().numpy() * 255).clip(0, 255).astype(_np.uint8)
            Image.fromarray(arr).save(tmp.name)
            ref_image_path = tmp.name
            temp_files.append(tmp.name)
        elif isinstance(image_a, str) and os.path.isfile(image_a):
            ref_image_path = image_a
        else:
            raise RuntimeError(
                f"Unexpected image_a type: {type(image_a)}. "
                "Expected ComfyUI IMAGE tensor or file path.")

        logger.info("SCAIL2: ref=%s driving=%s", ref_image_path, effective_video_path)

        # --- Collect extra reference images (image_b/image_path_b, c, d …) ---
        # Multiple references are composited onto one image so SAM gives each
        # subject its own color (2nd subject → red). Reuses the same temp_files
        # cleanup list as the primary reference.
        extra_ref_paths = []
        for suffix in ("b", "c", "d", "e"):
            img_t = kwargs.get(f"image_{suffix}")
            img_p = kwargs.get(f"image_path_{suffix}", "")
            extra_path = None
            if img_t is not None and hasattr(img_t, "shape"):
                frame = img_t[0] if len(img_t.shape) == 4 else img_t
                tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
                tmp.close()
                from PIL import Image
                arr = (frame.cpu().numpy() * 255).clip(0, 255).astype(_np.uint8)
                Image.fromarray(arr).save(tmp.name)
                extra_path = tmp.name
                temp_files.append(tmp.name)
            elif isinstance(img_p, str) and img_p.strip() and os.path.isfile(img_p.strip()):
                extra_path = img_p.strip()
            if extra_path:
                extra_ref_paths.append(extra_path)
        if extra_ref_paths:
            logger.info("SCAIL2: %d extra reference image(s) → composited",
                        len(extra_ref_paths))

        cmd_log = (
            f"scail2 generate --ref {ref_image_path} "
            f"--driving {effective_video_path}\n{lora_log}"
        )

        # --- Generate (returns animation + colored mask video paths) ---
        # SAM 3.1 detection target is the dedicated subject noun, NOT the
        # animation prompt — a full sentence makes SAM over-detect and produces
        # splotchy multi-colored masks. mask_points (if supplied) override it.
        sam_prompt = scail2_subject or "person"
        try:
            animation_path, mask_video_path = _scail2_generate(
                prompt=prompt,
                reference_image_path=ref_image_path,
                driving_video_path=effective_video_path,
                output_path=output_path,
                width=scail2_width,
                height=scail2_height,
                length=scail2_length,
                steps=scail2_steps,
                cfg=scail2_cfg,
                shift=scail2_shift,
                seed=scail2_seed,
                sampler_name=scail2_sampler,
                scheduler=scail2_scheduler,
                denoise=scail2_denoise,
                replacement_mode=scail2_replacement,
                sort_by=scail2_sort_by,
                object_indices=scail2_object_indices,
                sam_prompt=sam_prompt,
                sam_points=sam_points,
                sam_labels=sam_labels,
                sam_max_objects=scail2_max_objects,
                sam_det_threshold=scail2_det_threshold,
                sam_detect_interval=scail2_detect_interval,
                extra_reference_paths=extra_ref_paths,
                composite_direction=scail2_composite_direction,
                main_reference=scail2_main_reference,
                color_match=scail2_color_match,
                pose_extend=scail2_pose_extend,
                point_src_width=point_src_w,
                point_src_height=point_src_h,
                lora_entries=lora_entries,
                blockswap_blocks=scail2_blockswap,
                tiled_vae=scail2_tiled_vae,
            )
        finally:
            _scail2_cleanup()

        output_path = animation_path

        # --- Collect output frames/audio ---
        try:
            from ...ffmpega_media_converter import MediaConverter
            media_converter = MediaConverter()
        except ImportError:
            try:
                from ffmpega_media_converter import MediaConverter  # type: ignore
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

        analysis = (
            f"🎭 SCAIL-2 Character Animation\n"
            f"Mode: {'replacement' if scail2_replacement else 'animation'}\n"
            f"Resolution: {scail2_width}x{scail2_height}, frames={scail2_length} "
            f"(extend pose: {scail2_pose_extend})\n"
            f"Steps: {scail2_steps}, CFG: {scail2_cfg}, Shift: {scail2_shift}\n"
            f"Sampler: {scail2_sampler}/{scail2_scheduler}, Denoise: {scail2_denoise}\n"
            f"Seed: {scail2_seed}\n"
            f"SAM3 subject: {sam_prompt} (max {scail2_max_objects}, "
            f"det {scail2_det_threshold}, interval {scail2_detect_interval})"
            f"{' (point prompts)' if sam_points else ''}\n"
            f"References: {1 + len(extra_ref_paths)}"
            f"{f' ({scail2_composite_direction}, main={scail2_main_reference})' if extra_ref_paths else ''}\n"
            f"Mask sort: {scail2_sort_by}, object_indices: "
            f"{scail2_object_indices or '(all)'}\n"
            f"{lora_log}"
            f"Output: {output_path}\n"
            f"Mask video: {mask_video_path}"
        )

        return (images_tensor, audio_out, output_path, cmd_log, analysis, mask_video_path)
    finally:
        for tmp_path in temp_files:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
        if not save_output and temp_render_dir and os.path.isdir(temp_render_dir):
            if not os.listdir(temp_render_dir):
                shutil.rmtree(temp_render_dir, ignore_errors=True)
