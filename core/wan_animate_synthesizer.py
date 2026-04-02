# Copyright 2024-2025 The Alibaba Wan Team Authors. All rights reserved.
# Adapted for ComfyUI-FFMPEGA.
"""
Wan-Animate inference synthesizer — ComfyUI-native model loading.

Uses the same pattern as the SVI synthesizer: loads the Wan 2.2 Animate
transformer via ``comfy.sd.load_diffusion_model()``, VAE via ``comfy.sd.VAE``,
and text encoder via ``comfy.sd.load_clip()``.  LoRAs are applied with
``comfy.sd.load_lora_for_models()``.

The Animate-specific conditioning (pose latents, face pixels, ref latent)
is injected via ComfyUI's ``transformer_options`` dict, matching the format
expected by Kijai's WanVideoWrapper model implementation.
"""
from __future__ import annotations

import gc
import logging
import math
import os
from typing import List, Optional, Tuple

import numpy as np
import torch

logger = logging.getLogger("ComfyUI-FFMPEGA.wan_animate")

# Cached state
_model = None
_vae_model = None
_clip_model = None


# ---------------------------------------------------------------------------
#  Model discovery — reuse SVI helpers where possible
# ---------------------------------------------------------------------------

def _find_wan_animate_model() -> Optional[str]:
    """Find Wan 2.2 Animate model in ComfyUI model directories."""
    try:
        import folder_paths  # type: ignore[import-not-found]
    except ImportError:
        return None

    search_dirs = []
    for folder_name in ["diffusion_models", "unet"]:
        try:
            paths = folder_paths.get_folder_paths(folder_name)
            search_dirs.extend(paths)
        except Exception:
            pass

    for search_dir in search_dirs:
        if not os.path.isdir(search_dir):
            continue
        for root, _dirs, files in os.walk(search_dir):
            for f in files:
                f_lower = f.lower()
                if not f.endswith((".safetensors", ".ckpt", ".gguf")):
                    continue
                if "animate" in f_lower and ("wan" in f_lower or "14b" in f_lower):
                    return os.path.join(root, f)
    return None


def _import_svi_helpers():
    """Import model discovery helpers from the SVI synthesizer."""
    try:
        from .svi_synthesizer import (
            _find_wan_vae,
            _find_wan_text_encoder,
            _apply_lora_to_model,
        )
        return _find_wan_vae, _find_wan_text_encoder, _apply_lora_to_model
    except ImportError:
        from core.svi_synthesizer import (  # type: ignore
            _find_wan_vae,
            _find_wan_text_encoder,
            _apply_lora_to_model,
        )
        return _find_wan_vae, _find_wan_text_encoder, _apply_lora_to_model


def _load_gguf_text_encoder(te_path: str, comfy_module):
    """Load a GGUF text encoder using ComfyUI-GGUF extension.

    Mirrors the SVI synthesizer's GGUF loading logic.
    """
    import sys as _sys

    gguf_loader_mod = gguf_ops_mod = gguf_nodes_mod = None
    for _key, _mod in _sys.modules.items():
        if _mod is None:
            continue
        _mf = getattr(_mod, "__file__", "") or ""
        if os.path.join("ComfyUI-GGUF", "loader.py") in _mf:
            gguf_loader_mod = _mod
        elif os.path.join("ComfyUI-GGUF", "ops.py") in _mf:
            gguf_ops_mod = _mod
        elif os.path.join("ComfyUI-GGUF", "nodes.py") in _mf:
            gguf_nodes_mod = _mod

    if not (gguf_loader_mod and gguf_ops_mod and gguf_nodes_mod):
        raise RuntimeError(
            "GGUF text encoder requires ComfyUI-GGUF extension. "
            "Install from: https://github.com/city96/ComfyUI-GGUF"
        )

    clip_sd = gguf_loader_mod.gguf_clip_loader(te_path)

    import folder_paths  # type: ignore[import-not-found]
    clip_model = comfy_module.sd.load_text_encoder_state_dicts(
        clip_type=comfy_module.sd.CLIPType.WAN,
        state_dicts=[clip_sd],
        model_options={
            "custom_operations": gguf_ops_mod.GGMLOps,
            "initial_device": comfy_module.model_management.text_encoder_offload_device(),
        },
        embedding_directory=folder_paths.get_folder_paths("embeddings"),
    )
    clip_model.patcher = gguf_nodes_mod.GGUFModelPatcher.clone(clip_model.patcher)
    logger.info("WanAnimate: GGUF text encoder loaded successfully")
    return clip_model


# ---------------------------------------------------------------------------
#  Pipeline loading (ComfyUI-native)
# ---------------------------------------------------------------------------


def _load_models():
    """Load Wan 2.2 Animate transformer, VAE, and text encoder.

    Returns (model_patcher, vae, clip_model).
    """
    global _model, _vae_model, _clip_model

    if _model is not None and _vae_model is not None:
        return _model, _vae_model, _clip_model

    import comfy.sd  # type: ignore[import-not-found]
    import comfy.utils  # type: ignore[import-not-found]
    import comfy.model_management as mm  # type: ignore[import-not-found]

    _find_wan_vae, _find_wan_text_encoder, _ = _import_svi_helpers()

    # Free VRAM
    mm.unload_all_models()
    mm.soft_empty_cache()
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    # 1. Find and load the Animate transformer
    model_path = _find_wan_animate_model()
    if model_path is None:
        raise FileNotFoundError(
            "Wan 2.2 Animate model not found in ComfyUI model directories.\n"
            "Expected: Wan2_2-Animate-14B_*.safetensors in "
            "ComfyUI/models/diffusion_models/\n"
            "Download from: https://huggingface.co/Kijai/WanVideo_comfy_fp8_scaled"
        )
    logger.info("WanAnimate: Loading transformer from %s", model_path)
    _model = comfy.sd.load_diffusion_model(model_path)

    # 2. Find and load VAE
    vae_path = _find_wan_vae()
    if vae_path is None:
        raise FileNotFoundError(
            "Wan VAE not found. Expected: wan*.safetensors in ComfyUI/models/vae/"
        )
    logger.info("WanAnimate: Loading VAE from %s", vae_path)
    _vae_model = comfy.sd.VAE(sd=comfy.utils.load_torch_file(vae_path))

    # 3. Find and load text encoder (optional, used for prompt guidance)
    te_path = _find_wan_text_encoder()
    if te_path:
        logger.info("WanAnimate: Loading text encoder from %s", te_path)
        try:
            if te_path.lower().endswith(".gguf"):
                _clip_model = _load_gguf_text_encoder(te_path, comfy)
            else:
                _clip_model = comfy.sd.load_clip(
                    ckpt_paths=[te_path],
                    embedding_directory=None,
                    clip_type=comfy.sd.CLIPType.WAN,
                )
        except Exception as e:
            logger.warning("WanAnimate: Text encoder load failed: %s", e)
            _clip_model = None
    else:
        logger.warning("WanAnimate: No text encoder found — prompt guidance disabled")
        _clip_model = None


    logger.info("WanAnimate: All models loaded successfully")
    return _model, _vae_model, _clip_model


# ---------------------------------------------------------------------------
#  Main inference function
# ---------------------------------------------------------------------------

def animate(
    ref_image: np.ndarray,
    pose_frames: List[np.ndarray],
    face_frames: List[np.ndarray],
    bg_frames: Optional[List[np.ndarray]] = None,
    mask_frames: Optional[List[np.ndarray]] = None,
    mode: str = "animate",
    prompt: str = "",
    model_path: Optional[str] = None,
    num_inference_steps: int = 20,
    guidance_scale: float = 1.0,
    pose_strength: float = 1.0,
    face_strength: float = 1.0,
    seed: int = 42,
    width: int = 832,
    height: int = 480,
    num_frames: int = 81,
    lora_entries: Optional[List[Tuple[str, float]]] = None,
) -> List[np.ndarray]:
    """Run Wan-Animate inference using ComfyUI-native infrastructure.

    Args:
        ref_image: Reference character image (RGB, HWC uint8).
        pose_frames: Skeleton conditioning images (RGB, HWC uint8).
        face_frames: Face crops, 512×512 (RGB, HWC uint8).
        bg_frames: Background images for replacement mode.
        mask_frames: Body masks for replacement mode.
        mode: "animate" or "replace".
        prompt: Optional text prompt for supplementary guidance.
        model_path: Override model directory (unused in native mode).
        num_inference_steps: Denoising steps.
        guidance_scale: Classifier-free guidance scale.
        pose_strength: Pose conditioning strength multiplier.
        face_strength: Face conditioning strength multiplier.
        seed: Random seed.
        width: Output width.
        height: Output height.
        num_frames: Number of output frames.
        lora_entries: List of (lora_path, strength) tuples to load.

    Returns:
        List of output video frames (RGB, HWC uint8).
    """
    import comfy.model_management as mm  # type: ignore
    import comfy.samplers  # type: ignore
    import comfy.sample  # type: ignore
    import comfy.utils  # type: ignore
    from PIL import Image

    # Ensure 4n+1 frame count
    num_frames = ((num_frames - 1) // 4) * 4 + 1
    actual_frames = min(len(pose_frames), num_frames)

    # Align to 16px
    W = (width // 16) * 16
    H = (height // 16) * 16

    logger.info(
        "WanAnimate: Starting inference — %d frames, %dx%d, steps=%d, cfg=%.1f",
        actual_frames, W, H, num_inference_steps, guidance_scale,
    )

    # Load models
    model, vae, clip_model = _load_models()

    device = mm.get_torch_device()
    dtype = torch.bfloat16

    # Apply LoRAs
    _, _, _apply_lora = _import_svi_helpers()
    working_model = model
    if lora_entries:
        for i, (lora_path, lora_strength) in enumerate(lora_entries):
            if not lora_path or not os.path.isfile(lora_path):
                continue
            logger.info(
                "WanAnimate: Applying LoRA %d — %s (strength=%.2f)",
                i, os.path.basename(lora_path), lora_strength,
            )
            try:
                working_model = _apply_lora(working_model, lora_path, lora_strength)
            except Exception as e:
                logger.warning("WanAnimate: Failed to apply LoRA %s: %s", lora_path, e)

    # --- Encode text prompt ---
    prompt_cond = None
    neg_cond = None
    if clip_model and prompt:
        logger.info("WanAnimate: Encoding prompt: %s", prompt[:60])
        tokens = clip_model.tokenize(prompt)
        prompt_cond = clip_model.encode_from_tokens_scheduled(tokens)
        neg_tokens = clip_model.tokenize("")
        neg_cond = clip_model.encode_from_tokens_scheduled(neg_tokens)
    elif clip_model:
        tokens = clip_model.tokenize("")
        prompt_cond = clip_model.encode_from_tokens_scheduled(tokens)
        neg_cond = prompt_cond

    # --- VAE-encode conditioning images ---
    lat_h = H // 8
    lat_w = W // 8
    num_refs = 1  # single ref image

    # 1. VAE-encode pose images → pose_latents
    #    ComfyUI VAE.encode() expects [T, H, W, C] float [0,1]
    #    Internally reshapes to [1, C, T, H, W] for Wan video VAE
    pose_imgs = []
    for f in pose_frames[:actual_frames]:
        pf = Image.fromarray(f).resize((W, H), Image.LANCZOS)
        pose_imgs.append(np.array(pf))
    # [T, H, W, 3] float [0, 1]
    pose_tensor = torch.from_numpy(np.stack(pose_imgs)).float() / 255.0
    pose_latents = vae.encode(pose_tensor[:, :, :, :3])
    # pose_latents shape: [1, C=16, T_lat, H_lat, W_lat]
    logger.info("WanAnimate: pose_latents shape=%s", list(pose_latents.shape))

    # 2. Prepare face images → pixel values [-1, 1] at 512×512
    #    Face pixels are NOT VAE-encoded — passed as raw pixels to model
    face_imgs = []
    for f in face_frames[:actual_frames]:
        ff = Image.fromarray(f).resize((512, 512), Image.LANCZOS)
        face_imgs.append(np.array(ff))
    face_np = np.stack(face_imgs).astype(np.float32) / 255.0
    # Kijai format: [1, C, T, 512, 512] in [-1, 1]
    face_pixels = torch.from_numpy(face_np).permute(3, 0, 1, 2)  # [C, T, 512, 512]
    face_pixels = (face_pixels * 2 - 1).unsqueeze(0).to(dtype=dtype)  # [1, C, T, 512, 512]

    # 3. VAE-encode ref image — [1, H, W, 3] float [0, 1]
    ref_pil = Image.fromarray(ref_image).resize((W, H), Image.LANCZOS)
    ref_np = np.array(ref_pil).astype(np.float32) / 255.0
    ref_tensor = torch.from_numpy(ref_np).unsqueeze(0)  # [1, H, W, 3]
    ref_latent = vae.encode(ref_tensor[:, :, :, :3])
    # ref_latent: [1, C=16, T=1, H_lat, W_lat]
    ref_latent = ref_latent[0]  # [C, T=1, H_lat, W_lat]

    # Build ref latent with mask (4 mask channels + 16 latent channels)
    msk = torch.zeros(4, 1, lat_h, lat_w, device=ref_latent.device, dtype=ref_latent.dtype)
    msk[:, :num_refs] = 1
    ref_latent_masked = torch.cat([msk, ref_latent], dim=0)  # [20, 1, H_lat, W_lat]

    # 4. Background latents (encode zeros) — [T-1, H, W, 3] float [0, 1]
    total_latents = (actual_frames - 1) // 4 + 1
    bg_frame_count = actual_frames - num_refs
    bg_zero = torch.zeros(bg_frame_count, H, W, 3)  # [T, H, W, 3] float
    bg_latents = vae.encode(bg_zero)
    # bg_latents: [1, C=16, T_lat_bg, H_lat, W_lat]
    bg_latents = bg_latents[0]  # [C, T_lat_bg, H_lat, W_lat]
    bg_mask = torch.zeros(4, bg_latents.shape[1], lat_h, lat_w,
                          device=bg_latents.device, dtype=bg_latents.dtype)
    bg_latents_masked = torch.cat([bg_mask, bg_latents], dim=0)

    # Combine: [ref + bg] along temporal dim
    combined_ref_latent = torch.cat([ref_latent_masked, bg_latents_masked], dim=1)
    # Shape: [20, total_latents, H_lat, W_lat]


    # Offload VAE
    vae.first_stage_model.to("cpu")
    mm.soft_empty_cache()
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    # --- Build image_embeds dict (Kijai's WanAnimate format) ---
    target_shape = (16, total_latents + num_refs, lat_h, lat_w)
    seq_len = math.ceil((target_shape[2] * target_shape[3]) / 4 * target_shape[1])

    image_embeds = {
        "pose_latents": pose_latents.to("cpu"),
        "face_pixels": face_pixels.to("cpu"),
        "ref_latent": combined_ref_latent.to("cpu"),
        "ref_image": (torch.from_numpy(np.array(ref_pil)).float().permute(2, 0, 1) / 255.0 * 2 - 1).to("cpu"),
        "num_frames": actual_frames,
        "target_shape": target_shape,
        "frame_window_size": actual_frames,
        "lat_h": lat_h,
        "lat_w": lat_w,
        "looping": False,
        "pose_strength": pose_strength,
        "face_strength": face_strength,
        "max_seq_len": seq_len,
        "colormatch": "disabled",
        "clip_context": None,
        "negative_clip_context": None,
        "is_masked": False,
        "start_ref_image": None,
        "bg_images": None,
        "ref_masks": None,
        "pose_images": None,
    }

    # Inject image_embeds into model's transformer_options
    working_model.model_options.setdefault("transformer_options", {})
    working_model.model_options["transformer_options"]["wanvid_embeds"] = image_embeds

    # --- Sample ---
    logger.info("WanAnimate: Starting sampling...")
    latent_image = torch.zeros(
        1, 16, total_latents + num_refs, lat_h, lat_w,
        device=mm.intermediate_device(),
    )
    noise = torch.randn_like(latent_image)

    # Build positive/negative conditioning
    if prompt_cond is not None:
        positive = prompt_cond
        negative = neg_cond
    else:
        positive = [[torch.zeros(1, 512, 4096), {}]]
        negative = [[torch.zeros(1, 512, 4096), {}]]

    # Use ComfyUI's native sampler
    sampler = comfy.samplers.KSampler(
        working_model,
        steps=num_inference_steps,
        device=device,
        sampler="euler",
        scheduler="normal",
        denoise=1.0,
        model_options=working_model.model_options,
    )

    samples = comfy.sample.sample(
        working_model,
        noise,
        num_inference_steps,
        cfg=guidance_scale,
        sampler_name="euler",
        scheduler="normal",
        positive=positive,
        negative=negative,
        latent_image=latent_image,
        denoise=1.0,
        seed=seed,
    )
    logger.info("WanAnimate: Sampling complete, decoding frames...")

    # --- VAE decode ---
    vae.first_stage_model.to(device)
    # Remove ref latents from output (they were prepended)
    output_latents = samples[:, :, num_refs:]
    decoded = vae.decode(output_latents)
    # decoded: [B, T, H, W, C] float [0, 1]

    vae.first_stage_model.to("cpu")

    result = []
    for i in range(decoded.shape[1] if len(decoded.shape) == 5 else decoded.shape[0]):
        if len(decoded.shape) == 5:
            frame = decoded[0, i]
        else:
            frame = decoded[i]
        frame_np = (frame.clamp(0, 1).cpu().numpy() * 255).astype(np.uint8)
        result.append(frame_np)

    logger.info("WanAnimate: Generated %d frames", len(result))
    return result


def cleanup():
    """Release pipeline and free GPU memory."""
    global _model, _vae_model, _clip_model
    _model = None
    _vae_model = None
    _clip_model = None
    gc.collect()
    try:
        import comfy.model_management as mm  # type: ignore
        mm.unload_all_models()
        mm.soft_empty_cache()
    except (ImportError, Exception):
        pass
    try:
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        pass
    logger.info("WanAnimate: Cleaned up GPU memory.")
