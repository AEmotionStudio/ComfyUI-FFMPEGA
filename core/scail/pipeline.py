# coding: utf-8
# Copyright 2024-2025 The Alibaba Wan Team Authors. All rights reserved.
# Vendored and adapted for ComfyUI-FFMPEGA.
# MODIFIED: Removed distributed/FSDP/USP. Replaced custom T5/CLIP/VAE
#           modules with HuggingFace transformers + safetensors loading.
#           Added FFMPEGA VRAM management integration.
"""SCAIL inference pipeline — the main orchestration class.

**⚠️ WIP**: Memory optimization incomplete — block-level offloading works
but activation memory still causes OOM on GPUs with <24 GiB VRAM.
See SCAIL_Memory_Report.md for details.

This pipeline takes a reference image, pose video, and text prompt,
then generates an animated video using the SCAIL DiT model.

Lifecycle::

    pipeline = SCAILPipeline(config, model_dir, device)
    video = pipeline.generate(prompt, img, pose_video, ...)
    pipeline.cleanup()
"""

import gc
import logging
import math
import os
import random
import sys
from contextlib import contextmanager

import numpy as np
import torch
import torch.nn.functional as F
import torchvision.transforms.functional as TF
from einops import rearrange
from safetensors.torch import load_file
from tqdm import tqdm

from .fm_solvers import (
    FlowDPMSolverMultistepScheduler,
    FlowUniPCMultistepScheduler,
    get_sampling_sigmas,
    retrieve_timesteps,
)
from .lora import fuse_lora_with_diff_b
from .model_scail import SCAILModel

log = logging.getLogger("ffmpega")

__all__ = ["SCAILPipeline"]


class SCAILPipeline:
    """SCAIL character-animation pipeline.

    Orchestrates:
    1. T5 text encoding  (then → CPU)
    2. CLIP image encoding (then → CPU)
    3. VAE encode ref + pose (on GPU)
    4. DiT denoising loop (on GPU, then → CPU)
    5. VAE decode (on GPU, then → CPU)
    """

    def __init__(
        self,
        config,
        checkpoint_dir: str,
        scail_safetensors_path: str,
        scail_config_path: str | None = None,
        device: torch.device | None = None,
        lora_path: str | None = None,
        lora_alpha: float | None = None,
    ):
        """Initialize the SCAIL pipeline.

        Args:
            config: SCAIL configuration (from configs.py).
            checkpoint_dir: Directory containing T5/CLIP/VAE checkpoints.
            scail_safetensors_path: Path to SCAIL model weights.
            scail_config_path: Path to model config JSON (or None for default).
            device: Target CUDA device.
            lora_path: Optional LoRA weights path.
            lora_alpha: LoRA strength (default 1.0).
        """
        self.device = device or torch.device("cuda")
        self.config = config
        self.param_dtype = config.param_dtype
        self.num_train_timesteps = config.num_train_timesteps
        self.vae_stride = config.vae_stride
        self.patch_size = config.patch_size

        # ── T5 Text Encoder ──
        self._t5_model = None
        self._t5_tokenizer = None
        self._t5_checkpoint_path = os.path.join(
            checkpoint_dir, config.t5_checkpoint
        )
        self._t5_tokenizer_path = os.path.join(
            checkpoint_dir, config.t5_tokenizer
        )
        self._t5_dtype = config.t5_dtype

        # ── CLIP Image Encoder ──
        self._clip_model = None
        self._clip_checkpoint_path = os.path.join(
            checkpoint_dir, config.clip_checkpoint
        )
        self._clip_dtype = config.clip_dtype

        # ── VAE ──
        self._vae = None
        self._vae_checkpoint_path = os.path.join(
            checkpoint_dir, config.vae_checkpoint
        )

        # ── DiT Model (construct on meta device → zero RAM, then assign weights) ──
        log.info("Loading SCAILModel from %s", scail_safetensors_path)
        with torch.device("meta"):
            if scail_config_path and os.path.exists(scail_config_path):
                self.model = SCAILModel.from_config(scail_config_path)
            else:
                self.model = SCAILModel(
                    model_type="i2v",
                    patch_size=config.patch_size,
                    text_len=config.text_len,
                    in_dim=20,  # 16 latent + 4 pose conditioning channels
                    dim=config.dim,
                    ffn_dim=config.ffn_dim,
                    freq_dim=config.freq_dim,
                    text_dim=4096,
                    out_dim=16,
                    num_heads=config.num_heads,
                    num_layers=config.num_layers,
                    window_size=config.window_size,
                    qk_norm=config.qk_norm,
                    cross_attn_norm=config.cross_attn_norm,
                    eps=config.eps,
                )

        # assign=True replaces meta tensors in-place — only ~16 GB RAM needed
        state_dict = load_file(scail_safetensors_path, device="cpu")
        self.model.load_state_dict(state_dict, strict=False, assign=True)
        del state_dict
        gc.collect()

        # Recompute non-parameter attributes that are meta tensors after meta device load
        from .model_scail import rope_params
        dim = config.dim
        num_heads = config.num_heads
        d = dim // num_heads
        self.model.freqs = torch.cat([
            rope_params(8192, d - 4 * (d // 6)),
            rope_params(8192, 2 * (d // 6)),
            rope_params(8192, 2 * (d // 6)),
        ], dim=1)
        self.model.hidden_size_head = d

        if lora_path is not None:
            alpha = lora_alpha if lora_alpha is not None else 1.0
            log.info("Fusing LoRA from %s, alpha=%.2f", lora_path, alpha)
            lora_sd = load_file(lora_path, device="cpu")
            fuse_lora_with_diff_b(self.model, lora_sd, alpha=alpha)
            del lora_sd

        # Keep on CPU — moved to GPU only during sampling
        self.model.eval().requires_grad_(False)
        self.sample_neg_prompt = config.sample_neg_prompt
        log.info("SCAILModel loaded to CPU (%.1f GB params)",
                 sum(p.numel() * p.element_size() for p in self.model.parameters()) / (1024**3))

    # ── Lazy-loaded sub-models ────────────────────────────────────

    def _get_t5(self, target_device=None):
        """Load T5 text encoder on demand (always to CPU first)."""
        if self._t5_model is None:
            from transformers import AutoTokenizer, T5EncoderModel as HF_T5

            log.info("Loading T5 encoder to CPU...")

            if os.path.isfile(self._t5_checkpoint_path):
                # Custom checkpoint — load to CPU first
                self._t5_model = HF_T5.from_pretrained(
                    "google/umt5-xxl",
                    torch_dtype=self._t5_dtype,
                ).cpu()
                sd = load_file(self._t5_checkpoint_path, device="cpu")
                self._t5_model.load_state_dict(sd, strict=False)
                del sd
                gc.collect()
            else:
                # Fallback to HuggingFace — load to CPU
                self._t5_model = HF_T5.from_pretrained(
                    "google/umt5-xxl",
                    torch_dtype=self._t5_dtype,
                ).cpu()

            self._t5_model.eval()

            if os.path.isdir(self._t5_tokenizer_path):
                self._t5_tokenizer = AutoTokenizer.from_pretrained(
                    self._t5_tokenizer_path
                )
            else:
                self._t5_tokenizer = AutoTokenizer.from_pretrained(
                    "google/umt5-xxl"
                )

        return self._t5_model, self._t5_tokenizer

    def _encode_text(self, prompts: list[str], device: torch.device = None):
        """Encode text prompts using T5 (always on CPU — too large for GPU)."""
        model, tokenizer = self._get_t5()
        # T5-XXL BF16 is ~10 GB — must stay on CPU for <24 GB GPUs
        cpu = torch.device("cpu")
        model.to(cpu)

        tokens = tokenizer(
            prompts, padding="max_length", truncation=True,
            max_length=self.config.text_len, return_tensors="pt",
        ).to(cpu)

        with torch.no_grad():
            outputs = model(**tokens)

        # Return list of embeddings (one per prompt) on CPU
        return [outputs.last_hidden_state[i].cpu() for i in range(len(prompts))]

    def _get_clip(self, device=None):
        """Load CLIP visual encoder on demand (always to CPU first)."""
        if self._clip_model is None:
            from transformers import CLIPVisionModel, CLIPVisionConfig

            log.info("Loading CLIP vision model to CPU...")

            # SCAIL uses ViT-H/14 (1280 hidden dim), NOT ViT-L (1024)
            vit_h_model_id = "laion/CLIP-ViT-H-14-laion2B-s32B-b79K"

            if os.path.isfile(self._clip_checkpoint_path):
                # Build ViT-H config and load custom safetensors weights
                try:
                    config = CLIPVisionConfig.from_pretrained(vit_h_model_id)
                except Exception:
                    # Fallback: manually specify ViT-H/14 config
                    config = CLIPVisionConfig(
                        hidden_size=1280,
                        intermediate_size=5120,
                        num_hidden_layers=32,
                        num_attention_heads=16,
                        image_size=224,
                        patch_size=14,
                        projection_dim=1024,
                    )
                self._clip_model = CLIPVisionModel(config).to(dtype=self._clip_dtype).cpu()
                sd = load_file(self._clip_checkpoint_path, device="cpu")
                self._clip_model.load_state_dict(sd, strict=False)
                del sd
                gc.collect()
            else:
                # Fallback to HuggingFace ViT-H model
                self._clip_model = CLIPVisionModel.from_pretrained(
                    vit_h_model_id,
                    torch_dtype=self._clip_dtype,
                ).cpu()

            self._clip_model.eval()

        return self._clip_model

    def _encode_image_clip(self, img: torch.Tensor, device: torch.device = None):
        """Encode reference image using CLIP visual encoder (on CPU).

        Args:
            img: [3, H, W] tensor in [-1, 1].

        Returns:
            CLIP features [1, 257, 1280] on CPU.
        """
        cpu = torch.device("cpu")
        model = self._get_clip()
        model.to(cpu)

        # Resize for CLIP (224x224) — the model handles it internally
        # but we pass the full-res image for the visual features
        img_input = img.unsqueeze(0).unsqueeze(1).to(cpu)  # [1, 1, 3, H, W]
        img_input = img_input.to(self._clip_dtype)

        with torch.no_grad():
            # CLIP expects [B, C, H, W]
            clip_input = F.interpolate(
                img_input.squeeze(1), size=(224, 224),
                mode="bicubic", align_corners=False,
            )
            outputs = model(pixel_values=clip_input)
            # Get the last hidden state [B, 257, 1280]
            clip_fea = outputs.last_hidden_state

        return clip_fea.cpu()

    def _get_vae(self, device=None):
        """Load WanVAE on demand (to CPU first for memory staging)."""
        if self._vae is None:
            # Import WanVAE — try our vendored version first
            try:
                from .vae import WanVAE
                log.info("Loading WanVAE to CPU...")
                self._vae = WanVAE(
                    vae_pth=self._vae_checkpoint_path,
                    device="cpu",
                )
            except ImportError:
                raise ImportError(
                    "WanVAE module not found. Please ensure the VAE "
                    "module is properly vendored."
                )
        return self._vae

    # ── Main Generation ──────────────────────────────────────────────

    def generate(
        self,
        input_prompt: str,
        img: torch.Tensor,
        pose_video: torch.Tensor,
        shift: float = 5.0,
        sample_solver: str = "unipc",
        sampling_steps: int = 40,
        guide_scale: float = 5.0,
        n_prompt: str | None = None,
        seed: int = -1,
        offload_model: bool = True,
        progress_callback=None,
    ) -> torch.Tensor:
        """Generate animated video from reference image + pose video.

        Args:
            input_prompt: Text describing the character/scene.
            img: Reference image [3, H, W] in [-1, 1].
            pose_video: Rendered pose skeleton [T, C, H, W] in [0, 1].
            shift: Noise schedule shift (3.0 for 480p, 5.0 for higher res).
            sample_solver: "unipc" or "dpm++".
            sampling_steps: Number of denoising steps (default 40).
            guide_scale: CFG scale (default 5.0).
            n_prompt: Negative prompt (default "").
            seed: Random seed (-1 for random).
            offload_model: Move models to CPU between uses.
            progress_callback: Optional callable(step, total) for progress.

        Returns:
            Video tensor [C, T, H, W] in [0, 1].
        """
        device = self.device

        if not isinstance(img, torch.Tensor):
            img = TF.to_tensor(img).sub_(0.5).div_(0.5)
        # Keep tensors on CPU until needed by each sub-model
        img = img.cpu()
        pose_video = pose_video.cpu()

        ori_img = img.unsqueeze(0)  # [1, 3, H, W]

        # Downsample pose for latent space (on CPU — small op)
        smpl_render_video = F.interpolate(
            pose_video, scale_factor=0.5, mode="bilinear", align_corners=False,
        )  # [T, C, H/2, W/2]

        # ── VAE encode (move VAE to GPU, encode, offload to CPU) ──
        log.info("VAE encoding (GPU)...")
        vae = self._get_vae()
        vae.model.to(device)
        vae.device = device
        vae.mean = vae.mean.to(device)
        vae.std = vae.std.to(device)
        vae.scale = [vae.mean, 1.0 / vae.std]

        smpl_render_latent = vae.encode(
            [rearrange(smpl_render_video.to(device), "t c h w -> c t h w")]
        )[0]
        pose_latent = smpl_render_latent.cpu()
        ref_latent = vae.encode(
            [rearrange(ori_img.to(device), "t c h w -> c t h w")]
        )[0].cpu()
        del smpl_render_video, smpl_render_latent, ori_img

        # Fully offload VAE from GPU — clear internal cache too
        vae.model.clear_cache()
        vae.model.cpu()
        vae.device = "cpu"
        vae.mean = vae.mean.cpu()
        vae.std = vae.std.cpu()
        vae.scale = [vae.mean, 1.0 / vae.std]
        gc.collect()
        torch.cuda.empty_cache()
        free_gb = torch.cuda.mem_get_info()[0] / (1024**3)
        log.info("VAE encoded & offloaded to CPU (GPU free: %.2f GiB)", free_gb)

        lat_t = pose_latent.shape[1]
        lat_c, _, lat_h, lat_w = ref_latent.shape
        max_seq_len = 1e10

        # Random seed
        seed = seed if seed >= 0 else random.randint(0, sys.maxsize)
        seed_g = torch.Generator(device="cpu")
        seed_g.manual_seed(seed)

        noise = torch.randn(
            lat_c, lat_t, lat_h, lat_w,
            dtype=torch.float32, generator=seed_g, device="cpu",
        )

        n_prompt = n_prompt or ""

        # ── T5 text encoding (on CPU — T5-XXL BF16 is too large for GPU) ──
        log.info("T5 encoding (CPU)...")
        context = self._encode_text([input_prompt])
        context_null = self._encode_text([n_prompt])
        log.info("T5 encoded")

        # ── CLIP image encoding (on CPU) ──
        log.info("CLIP encoding (CPU)...")
        clip_context = self._encode_image_clip(img)
        log.info("CLIP encoded")

        # ── Diffusion sampling (DiT on GPU) ──
        log.info("Moving DiT to GPU for sampling (%d steps)...", sampling_steps)
        with torch.amp.autocast('cuda', dtype=self.param_dtype), torch.no_grad():
            if sample_solver == "unipc":
                scheduler = FlowUniPCMultistepScheduler(
                    num_train_timesteps=self.num_train_timesteps,
                    shift=1, use_dynamic_shifting=False,
                )
                scheduler.set_timesteps(
                    sampling_steps, device=device, shift=shift,
                )
                timesteps = scheduler.timesteps
            elif sample_solver == "dpm++":
                scheduler = FlowDPMSolverMultistepScheduler(
                    num_train_timesteps=self.num_train_timesteps,
                    shift=1, use_dynamic_shifting=False,
                )
                sigmas = get_sampling_sigmas(sampling_steps, shift)
                timesteps, _ = retrieve_timesteps(
                    scheduler, device=device, sigmas=sigmas,
                )
            else:
                raise ValueError(f"Unknown solver: {sample_solver}")

            latent = noise
            # Move embeddings/latents to device for sampling
            # Keep conditioning tensors on CPU — forward() moves them to GPU
            # just-in-time for each embedding step, then frees them
            arg_c = {
                "context": [context[0]],
                "clip_fea": clip_context,
                "seq_len": max_seq_len,
                "ref_latents": [ref_latent],
                "pose_latents": [pose_latent],
            }
            arg_null = {
                "context": [c for c in context_null],
                "clip_fea": clip_context,
                "seq_len": max_seq_len,
                "ref_latents": [ref_latent],
                "pose_latents": [pose_latent],
            }
            del context, context_null, clip_context, ref_latent, pose_latent
            gc.collect()

            torch.cuda.empty_cache()

            # ── Block-level offloading ──
            # The DiT (15.3 GB) is too large for the GPU (11.6 GiB).
            # Move only small components to GPU; offload blocks one at a time.
            log.info("Setting up block-level offloading for DiT (%d blocks)...", len(self.model.blocks))

            # Move small components to GPU (~500 MB total)
            self.model.patch_embedding.to(device)
            self.model.patch_embedding_pose.to(device)
            self.model.text_embedding.to(device)
            self.model.time_embedding.to(device)
            self.model.time_projection.to(device)
            self.model.head.to(device)
            if hasattr(self.model, 'img_emb') and self.model.img_emb is not None:
                self.model.img_emb.to(device)
            self.model.freqs = self.model.freqs.to(device)

            # Install hooks on each block: move to GPU before forward, back to CPU after
            hooks = []
            for block in self.model.blocks:
                def pre_hook(module, args, _dev=device):
                    module.to(_dev)
                def post_hook(module, args, output, _dev=torch.device("cpu")):
                    module.to(_dev)
                hooks.append(block.register_forward_pre_hook(pre_hook))
                hooks.append(block.register_forward_hook(post_hook))

            total_steps = len(timesteps)

            for step_idx, t in enumerate(tqdm(timesteps, desc="SCAIL")):
                latent_input = [latent]  # stays on CPU; forward() moves to GPU
                ts = torch.stack([t])

                noise_pred_cond = self.model(
                    latent_input, t=ts, **arg_c,
                )[0]

                if guide_scale <= 1.0:
                    noise_pred = noise_pred_cond
                else:
                    noise_pred_uncond = self.model(
                        latent_input, t=ts, **arg_null,
                    )[0]

                    noise_pred = noise_pred_uncond + guide_scale * (
                        noise_pred_cond - noise_pred_uncond
                    )

                temp_x0 = scheduler.step(
                    noise_pred.unsqueeze(0), t,
                    latent.unsqueeze(0).to(device), return_dict=False,
                )[0]
                latent = temp_x0.squeeze(0).cpu()

                if progress_callback:
                    progress_callback(step_idx + 1, total_steps)

                del latent_input, ts, noise_pred_cond
                if guide_scale > 1.0:
                    del noise_pred_uncond
                del noise_pred, temp_x0

            # Remove hooks and offload DiT back to CPU
            log.info("Offloading DiT to CPU...")
            for h in hooks:
                h.remove()
            self.model.cpu()
            del arg_c, arg_null
            gc.collect()
            torch.cuda.empty_cache()

            # ── VAE decode (move VAE back to GPU) ──
            log.info("VAE decoding (GPU)...")
            vae.model.to(device)
            vae.device = device
            vae.mean = vae.mean.to(device)
            vae.std = vae.std.to(device)
            vae.scale = [vae.mean, 1.0 / vae.std]

            x0 = [latent.to(device)]
            videos = vae.decode(x0)

            # Offload VAE after decode
            vae.model.cpu()
            vae.device = "cpu"

        del noise, latent, scheduler
        gc.collect()
        torch.cuda.empty_cache()
        log.info("SCAIL generation complete")

        return videos[0]

    def cleanup(self):
        """Free all GPU memory and models."""
        for attr in ("_t5_model", "_clip_model", "_vae", "model"):
            obj = getattr(self, attr, None)
            if obj is not None and hasattr(obj, "cpu"):
                try:
                    obj.cpu()
                except Exception:
                    pass
            setattr(self, attr, None)

        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.synchronize()
