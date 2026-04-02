# coding: utf-8
"""Vendored from Pulse-of-Motion (Apache 2.0) — src/models/fps_predictor.py

FPSPredictor — pytorch_lightning stripped → pure torch.nn.Module.
Training methods removed. Only __init__ and forward() remain.
"""

import torch
import torch.nn as nn
from einops import rearrange, repeat

from .autoencoder_2p1d import AutoencoderKL2plus1D_1dcnn
from .attention_temporal import CrossAttention


class FPSPredictor(nn.Module):
    def __init__(
        self,
        ddconfig,
        ppconfig,
        lossconfig,
        embed_dim,
        use_quant_conv=True,
        ckpt_path=None,
        freeze_encoder=True,
        hidden_dim=1024,
        input_key="video",
        monitor="val/loss",
        logdir=None,
        warmup_steps=2000,
        n_layers=4,
        *args,
        **kwargs,
    ):
        super().__init__()
        self.freeze_encoder = freeze_encoder
        self.n_layers = n_layers

        # Instantiate the VAE (with frozen pretrained encoder)
        self.vae = AutoencoderKL2plus1D_1dcnn(
            ddconfig=ddconfig,
            ppconfig=ppconfig,
            lossconfig=lossconfig,
            embed_dim=embed_dim,
            use_quant_conv=use_quant_conv,
            ckpt_path=ckpt_path,
        )

        if self.freeze_encoder:
            self.vae.eval()
            self.vae.freeze()

        self.feat_dim = 2 * ddconfig["z_channels"] if use_quant_conv else ddconfig["z_channels"]
        self.probe_token = nn.Parameter(torch.randn(1, 1, hidden_dim))

        # Project encoder output to hidden_dim
        self.proj_in = nn.Linear(self.feat_dim, hidden_dim)

        # Attention Pooling
        if n_layers == 1:
            self.attn_pool = CrossAttention(
                query_dim=hidden_dim,
                context_dim=hidden_dim,
                heads=8,
                dim_head=64,
                dropout=0.1,
            )
        else:
            self.attn_pool = nn.ModuleList([
                CrossAttention(
                    query_dim=hidden_dim,
                    context_dim=hidden_dim,
                    heads=8,
                    dim_head=64,
                    dropout=0.1,
                ) for _ in range(n_layers)
            ])

        # MLP for regression: outputs log(FPS)
        self.mlp = nn.Sequential(
            nn.LayerNorm(hidden_dim),
            nn.Linear(hidden_dim, hidden_dim),
            nn.GELU(),
            nn.Linear(hidden_dim, 1),
        )

    def forward(self, x):
        """
        Args:
            x: [B, C, T, H, W] video tensor (normalized to [-1, 1])
        Returns:
            pred_log_fps: [B, 1] predicted log(FPS)
        """
        # Encode
        if self.freeze_encoder:
            with torch.no_grad():
                latents = self.vae.encoder(x)
                if self.vae.use_quant_conv:
                    latents = self.vae.quant_conv(latents)
        else:
            latents = self.vae.encoder(x)
            if self.vae.use_quant_conv:
                latents = self.vae.quant_conv(latents)

        b, c, t, h, w = latents.shape

        # Flatten spatial+temporal → sequence
        latents = rearrange(latents, "b c t h w -> b (t h w) c")

        # Project to hidden_dim
        latents = self.proj_in(latents)

        # Probe token → cross-attention pooling
        probe = repeat(self.probe_token, "1 1 d -> b 1 d", b=b)

        if self.n_layers == 1:
            pooled = self.attn_pool(probe, context=latents)
        else:
            pooled = probe
            for attn in self.attn_pool:
                pooled = attn(pooled, context=latents)

        # MLP regression head
        pred_log_fps = self.mlp(pooled).squeeze(-1)

        return pred_log_fps
