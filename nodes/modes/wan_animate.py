# coding: utf-8
"""No-LLM mode: wan animate.

Moved verbatim from nodes/nollm_modes.py, which is now a re-export facade.
"""

from __future__ import annotations

from ._shared import (
    Optional,
    _encode_frames_to_video,
    build_output_path,
    collect_frame_output,
    os,
    tempfile,
    torch,
)


async def process_wan_animate_only(
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
    image_a=None,
    image_path_a: str = "",
    temp_video_from_images: Optional[str] = None,
    temp_video_with_audio: Optional[str] = None,
    **kwargs,
) -> tuple:
    """Run Wan-Animate video-driven character animation without any LLM involvement.

    Workflow:
    1. Extract driving frames from video_a (effective_video_path).
    2. Load reference character image from image_a or image_path_a.
    3. Run YOLO+ViTPose preprocessing to extract pose, face, bg, masks.
    4. Generate debug overlay video (skeleton + face bbox).
    5. Run WanAnimatePipeline inference.
    6. Encode output video.

    Returns:
        Standard 6-tuple: (images_tensor, audio_out, output_path, cmd_log, analysis, mask_overlay_path)
    """
    import asyncio
    import tempfile

    import numpy as np

    cmd_log = "🎭 Wan-Animate Mode\n"

    # ── Validate inputs ──────────────────────────────────────────────────
    driving_video = effective_video_path
    if not driving_video or not os.path.isfile(driving_video):
        raise ValueError(
            "Wan-Animate requires a driving video. Connect a video to video_a "
            "or provide a valid video path."
        )

    # Resolve reference image
    ref_image = None
    if image_a is not None:
        if isinstance(image_a, torch.Tensor):
            if image_a.dim() == 4:
                img_np = (image_a[0].cpu().numpy() * 255).astype(np.uint8)
            else:
                img_np = (image_a.cpu().numpy() * 255).astype(np.uint8)
            ref_image = img_np
        elif isinstance(image_a, np.ndarray):
            ref_image = image_a if image_a.max() > 1 else (image_a * 255).astype(np.uint8)

    if ref_image is None and image_path_a and os.path.isfile(image_path_a):
        import cv2
        ref_image = cv2.imread(image_path_a)
        if ref_image is not None:
            ref_image = cv2.cvtColor(ref_image, cv2.COLOR_BGR2RGB)

    if ref_image is None:
        raise ValueError(
            "Wan-Animate requires a reference character image. "
            "Connect an image to image_a or provide image_path_a."
        )

    cmd_log += f"Driving video: {driving_video}\n"
    cmd_log += f"Reference image shape: {ref_image.shape}\n"

    # ── Extract driving frames ───────────────────────────────────────────
    import cv2
    cap = cv2.VideoCapture(driving_video)
    frames = []
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        frames.append(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    cap.release()

    if not frames:
        raise ValueError("Could not read any frames from driving video.")

    cmd_log += f"Driving frames: {len(frames)}, FPS: {fps:.1f}\n"

    # ── Preprocessing ────────────────────────────────────────────────────
    from ...core.wan_animate_preprocess import WanAnimatePreprocessor

    preprocessor = WanAnimatePreprocessor(device="cuda")
    mode = kwargs.get("wan_animate_mode", "animate")
    cmd_log += f"Mode: {mode}\n"

    try:
        preprocess_result = preprocessor.preprocess(
            frames=frames,
            refer_image=ref_image,
            mode=mode,
        )
    except FileNotFoundError as e:
        raise RuntimeError(
            f"Wan-Animate model files missing: {e}\n"
            "Download the ONNX models to models/wan_animate/det/ and models/wan_animate/pose2d/"
        ) from e

    pose_frames = preprocess_result["pose_frames"]
    face_frames = preprocess_result["face_frames"]
    debug_frames = preprocess_result["debug_frames"]
    ref_processed = preprocess_result["ref_image"]

    cmd_log += f"Preprocessed: {len(pose_frames)} pose, {len(face_frames)} face frames\n"

    # ── Debug overlay video ──────────────────────────────────────────────
    debug_video_path = ""
    if debug_frames:
        debug_dir = tempfile.mkdtemp(prefix="wan_animate_debug_")
        debug_video_path = os.path.join(debug_dir, "debug_overlay.mp4")
        _encode_frames_to_video(debug_frames, debug_video_path, fps=fps)
        cmd_log += f"Debug overlay: {debug_video_path}\n"

    # ── Inference ────────────────────────────────────────────────────────
    from ...core.wan_animate_synthesizer import animate as wan_animate_infer, cleanup as wan_cleanup

    num_steps = int(kwargs.get("wan_animate_steps", 20))
    guidance = float(kwargs.get("wan_animate_guidance", 1.0))
    seed = int(kwargs.get("wan_animate_seed", 42))
    num_frames = int(kwargs.get("wan_animate_num_frames", min(len(pose_frames), 81)))
    target_h = int(kwargs.get("wan_animate_height", 480))
    target_w = int(kwargs.get("wan_animate_width", 832))
    pose_strength = float(kwargs.get("wan_animate_pose_strength", 1.0))
    face_strength = float(kwargs.get("wan_animate_face_strength", 1.0))
    prompt = str(kwargs.get("prompt", ""))

    # Collect LoRA entries from dynamic slots (a → d)
    lora_entries = []  # list of (path, strength) tuples
    for slot in ("a", "b", "c", "d"):
        lora_name = str(kwargs.get(f"wan_animate_lora_{slot}", "none"))
        if not lora_name or lora_name == "none":
            break  # stop at first empty slot
        lora_strength = float(kwargs.get(f"wan_animate_lora_strength_{slot}", 1.0))
        lora_path = None
        try:
            import folder_paths  # type: ignore
            lora_path = folder_paths.get_full_path("loras", lora_name)
        except Exception:
            for search_dir in [
                os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
                    os.path.dirname(os.path.abspath(__file__))))), "models", "loras"),
            ]:
                candidate = os.path.join(search_dir, lora_name)
                if os.path.isfile(candidate):
                    lora_path = candidate
                    break
        if lora_path:
            lora_entries.append((lora_path, lora_strength))
            cmd_log += f"LoRA {slot.upper()}: {lora_name} (strength={lora_strength})\n"
        else:
            cmd_log += f"⚠️ LoRA {slot.upper()} not found: {lora_name} — skipping\n"

    h, w = target_h, target_w

    cmd_log += f"Inference: {num_frames} frames, {w}x{h}, steps={num_steps}, cfg={guidance}\n"
    if prompt:
        cmd_log += f"Prompt: {prompt[:80]}{'...' if len(prompt) > 80 else ''}\n"

    try:
        output_frames = wan_animate_infer(
            ref_image=ref_processed,
            pose_frames=pose_frames,
            face_frames=face_frames,
            bg_frames=preprocess_result.get("bg_frames"),
            mask_frames=preprocess_result.get("mask_frames"),
            mode=mode,
            prompt=prompt,
            num_inference_steps=num_steps,
            guidance_scale=guidance,
            seed=seed,
            width=w,
            height=h,
            num_frames=num_frames,
            pose_strength=pose_strength,
            face_strength=face_strength,
            lora_entries=lora_entries,
        )
    finally:
        preprocessor.cleanup()
        wan_cleanup()

    cmd_log += f"Generated {len(output_frames)} output frames\n"

    # ── Encode output ────────────────────────────────────────────────────
    # Build the output path if not provided (common in no-LLM modes)
    if not output_path:
        output_path, _temp_render_dir = build_output_path(
            effective_video_path=effective_video_path,
            video_metadata=video_metadata,
            output_path=output_path,
            save_output=save_output,
        )
    _encode_frames_to_video(output_frames, output_path, fps=fps)
    cmd_log += f"Output: {output_path}\n"

    # ── Collect output tensor/audio ──────────────────────────────────────
    try:
        from ...ffmpega_media_converter import MediaConverter
        mc = MediaConverter()
    except ImportError:
        try:
            from ffmpega_media_converter import MediaConverter  # type: ignore
            mc = MediaConverter()
        except Exception:
            mc = None

    unique_id = str(kwargs.get("unique_id", ""))
    hidden_prompt = kwargs.get("hidden_prompt") or {}
    images_tensor, audio_out = collect_frame_output(
        media_converter=mc,
        output_path=output_path,
        unique_id=unique_id,
        hidden_prompt=hidden_prompt,
        removes_audio=False,
    )

    # ── Analysis string ──────────────────────────────────────────────────
    analysis = (
        f"🎭 Wan-Animate — Video-Driven Character Animation\n"
        f"Mode: {mode}\n"
        f"Driving frames: {len(frames)}\n"
        f"Output frames: {len(output_frames)}\n"
        f"Resolution: {w}×{h}\n"
        f"Steps: {num_steps}, CFG: {guidance}\n"
        f"Seed: {seed}\n"
    )
    if debug_video_path:
        analysis += f"\nDebug overlay: {debug_video_path}"

    return (images_tensor, audio_out, output_path, cmd_log, analysis, debug_video_path)
