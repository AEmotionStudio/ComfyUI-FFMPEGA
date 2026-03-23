# coding: utf-8
# Copyright 2024-2025 The Alibaba Wan Team Authors. All rights reserved.
# Vendored and adapted for ComfyUI-FFMPEGA.
"""SCAIL model configurations."""

import torch
from easydict import EasyDict

# ── Shared Wan config ──────────────────────────────────────────────

_shared = EasyDict()
_shared.t5_model = "umt5_xxl"
_shared.t5_dtype = torch.bfloat16
_shared.text_len = 512
_shared.param_dtype = torch.bfloat16
_shared.num_train_timesteps = 1000
_shared.sample_fps = 16
_shared.sample_neg_prompt = ""

# ── SCAIL-14B ──────────────────────────────────────────────────────

scail_14B = EasyDict(__name__="Config: SCAIL 14B")
scail_14B.update(_shared)
scail_14B.sample_neg_prompt = ""

# T5 text encoder (safetensors from Kijai)
scail_14B.t5_checkpoint = "umt5-xxl-enc.safetensors"
scail_14B.t5_tokenizer = "umt5-xxl"  # fallback to HF if dir not present

# CLIP image encoder (safetensors from Kijai)
scail_14B.clip_model = "clip_xlm_roberta_vit_h_14"
scail_14B.clip_dtype = torch.float16
scail_14B.clip_checkpoint = "clip_visual.safetensors"
scail_14B.clip_tokenizer = "xlm-roberta-large"

# VAE (safetensors from Kijai)
scail_14B.vae_checkpoint = "wan2_1_vae.safetensors"
scail_14B.vae_stride = (4, 8, 8)

# Transformer (DiT)
scail_14B.patch_size = (1, 2, 2)
scail_14B.dim = 5120
scail_14B.ffn_dim = 13824
scail_14B.freq_dim = 256
scail_14B.num_heads = 40
scail_14B.num_layers = 40
scail_14B.window_size = (-1, -1)
scail_14B.qk_norm = True
scail_14B.cross_attn_norm = True
scail_14B.eps = 1e-6

# ── SCAIL-1.3B (placeholder — same architecture, smaller) ─────────

scail_1_3B = EasyDict(__name__="Config: SCAIL 1.3B")
scail_1_3B.update(_shared)
scail_1_3B.sample_neg_prompt = ""

scail_1_3B.t5_checkpoint = "umt5-xxl-enc.safetensors"
scail_1_3B.t5_tokenizer = "umt5-xxl"

scail_1_3B.clip_model = "clip_xlm_roberta_vit_h_14"
scail_1_3B.clip_dtype = torch.float16
scail_1_3B.clip_checkpoint = "clip_visual.safetensors"
scail_1_3B.clip_tokenizer = "xlm-roberta-large"

scail_1_3B.vae_checkpoint = "wan2_1_vae.safetensors"
scail_1_3B.vae_stride = (4, 8, 8)

scail_1_3B.patch_size = (1, 2, 2)
scail_1_3B.dim = 1536
scail_1_3B.ffn_dim = 8960
scail_1_3B.freq_dim = 256
scail_1_3B.num_heads = 12
scail_1_3B.num_layers = 30
scail_1_3B.window_size = (-1, -1)
scail_1_3B.qk_norm = True
scail_1_3B.cross_attn_norm = True
scail_1_3B.eps = 1e-6

# ── Lookup dicts ───────────────────────────────────────────────────

SCAIL_CONFIGS = {
    "SCAIL-14B": scail_14B,
    "SCAIL-1.3B": scail_1_3B,
}
