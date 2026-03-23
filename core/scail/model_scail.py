# coding: utf-8
# Copyright 2024-2025 The Alibaba Wan Team Authors. All rights reserved.
# Vendored and adapted for ComfyUI-FFMPEGA.
"""SCAIL DiT (Diffusion Transformer) model.

This is the main backbone for SCAIL's image-to-video generation with
pose-conditioned denoising. Extends the Wan i2v architecture with a
dedicated pose patch embedding and SCAIL-specific RoPE.
"""

import math
from functools import partial, reduce
from operator import mul

import torch
import torch.nn as nn
import torch.nn.functional as F
from diffusers.configuration_utils import ConfigMixin, register_to_config
from diffusers.models.modeling_utils import ModelMixin
from einops import rearrange

from .attention import flash_attention

__all__ = ["SCAILModel"]

T5_CONTEXT_TOKEN_NUMBER = 512
FIRST_LAST_FRAME_CONTEXT_TOKEN_NUMBER = 257 * 2


# ── Positional Embeddings ──────────────────────────────────────────


def sinusoidal_embedding_1d(dim, position):
    assert dim % 2 == 0
    half = dim // 2
    position = position.type(torch.float64)
    sinusoid = torch.outer(
        position,
        torch.pow(10000, -torch.arange(half).to(position).div(half)),
    )
    return torch.cat([torch.cos(sinusoid), torch.sin(sinusoid)], dim=1)


@torch.amp.autocast('cuda', enabled=False)
def rope_params(max_seq_len, dim, theta=10000):
    assert dim % 2 == 0
    freqs = torch.outer(
        torch.arange(max_seq_len),
        1.0 / torch.pow(
            theta, torch.arange(0, dim, 2).to(torch.float64).div(dim)
        ),
    )
    return torch.polar(torch.ones_like(freqs), freqs)


@torch.amp.autocast('cuda', enabled=False)
def rope_apply_ref(x, freqs, **kwargs):
    f, h, w = 1, kwargs["rope_H"], kwargs["rope_W"]
    shift_f, shift_h, shift_w = 0, kwargs["rope_H_shift"], kwargs["rope_W_shift"]
    n, c = x.size(2), x.size(3) // 2
    freqs = freqs.split([c - 2 * (c // 3), c // 3, c // 3], dim=1)

    output = []
    for i in range(x.size(0)):
        seq_len = f * h * w
        assert seq_len == x.size(1)
        x_i = torch.view_as_complex(
            x[i, :seq_len].to(torch.float64).reshape(seq_len, n, -1, 2)
        )
        freqs_i = torch.cat([
            freqs[0][shift_f:shift_f + f].view(f, 1, 1, -1).expand(f, h, w, -1),
            freqs[1][shift_h:shift_h + h].view(1, h, 1, -1).expand(f, h, w, -1),
            freqs[2][shift_w:shift_w + w].view(1, 1, w, -1).expand(f, h, w, -1),
        ], dim=-1).reshape(seq_len, 1, -1)
        x_i = torch.view_as_real(x_i * freqs_i).flatten(2)
        x_i = torch.cat([x_i, x[i, seq_len:]])
        output.append(x_i)
    return torch.stack(output).float()


@torch.amp.autocast('cuda', enabled=False)
def rope_apply_video(x, freqs, **kwargs):
    f, h, w = kwargs["rope_T"], kwargs["rope_H"], kwargs["rope_W"]
    shift_f, shift_h, shift_w = 1, kwargs["rope_H_shift"], kwargs["rope_W_shift"]
    n, c = x.size(2), x.size(3) // 2
    freqs = freqs.split([c - 2 * (c // 3), c // 3, c // 3], dim=1)

    output = []
    for i in range(x.size(0)):
        seq_len = f * h * w
        assert seq_len == x.size(1)
        x_i = torch.view_as_complex(
            x[i, :seq_len].to(torch.float64).reshape(seq_len, n, -1, 2)
        )
        freqs_i = torch.cat([
            freqs[0][shift_f:shift_f + f].view(f, 1, 1, -1).expand(f, h, w, -1),
            freqs[1][shift_h:shift_h + h].view(1, h, 1, -1).expand(f, h, w, -1),
            freqs[2][shift_w:shift_w + w].view(1, 1, w, -1).expand(f, h, w, -1),
        ], dim=-1).reshape(seq_len, 1, -1)
        x_i = torch.view_as_real(x_i * freqs_i).flatten(2)
        x_i = torch.cat([x_i, x[i, seq_len:]])
        output.append(x_i)
    return torch.stack(output).float()


@torch.amp.autocast('cuda', enabled=False)
def rope_apply_pose(x, freqs, **kwargs):
    f, h, w = kwargs["rope_T"], kwargs["rope_H"], kwargs["rope_W"]
    shift_f = 1
    shift_h = kwargs["rope_H_shift"] + kwargs["global_rope_H"]
    shift_w = kwargs["rope_W_shift"] + kwargs["global_rope_W"]
    n, c = x.size(2), x.size(3) // 2
    freqs = freqs.split([c - 2 * (c // 3), c // 3, c // 3], dim=1)

    output = []
    for i in range(x.size(0)):
        seq_len = f * (h // 2) * (w // 2)
        assert seq_len == x.size(1)
        x_i = torch.view_as_complex(
            x[i, :seq_len].to(torch.float64).reshape(seq_len, n, -1, 2)
        )
        freqs_i = torch.cat([
            freqs[0][shift_f:shift_f + f].view(f, 1, 1, -1).expand(f, h, w, -1),
            freqs[1][shift_h:shift_h + h].view(1, h, 1, -1).expand(f, h, w, -1),
            freqs[2][shift_w:shift_w + w].view(1, 1, w, -1).expand(f, h, w, -1),
        ], dim=-1)

        # Downsample RoPE for pose (half resolution)
        freqs_i_real = F.avg_pool2d(
            freqs_i.real.permute(0, 3, 1, 2), kernel_size=2, stride=2,
        ).permute(0, 2, 3, 1)
        freqs_i_imag = F.avg_pool2d(
            freqs_i.imag.permute(0, 3, 1, 2), kernel_size=2, stride=2,
        ).permute(0, 2, 3, 1)
        freqs_i = torch.complex(freqs_i_real, freqs_i_imag)
        freqs_i = freqs_i.reshape(seq_len, 1, -1)

        x_i = torch.view_as_real(x_i * freqs_i).flatten(2)
        x_i = torch.cat([x_i, x[i, seq_len:]])
        output.append(x_i)
    return torch.stack(output).float()


def rope_apply_scail(x, **kwargs):
    """Apply RoPE to concatenated [ref, video, pose] sequences."""
    ref_len = kwargs["ref_length"]
    vid_len = kwargs["seq_length"]
    pose_len = kwargs["pose_length"]
    return torch.cat([
        rope_apply_ref(x[:, :ref_len], **kwargs),
        rope_apply_video(x[:, ref_len:ref_len + vid_len], **kwargs),
        rope_apply_pose(x[:, -pose_len:], **kwargs),
    ], dim=1)


# ── Normalisation layers ───────────────────────────────────────────


class WanRMSNorm(nn.Module):
    def __init__(self, dim, eps=1e-5):
        super().__init__()
        self.eps = eps
        self.weight = nn.Parameter(torch.ones(dim))

    def forward(self, x):
        return self._norm(x.float()).type_as(x) * self.weight

    def _norm(self, x):
        return x * torch.rsqrt(x.pow(2).mean(dim=-1, keepdim=True) + self.eps)


class WanLayerNorm(nn.LayerNorm):
    def __init__(self, dim, eps=1e-6, elementwise_affine=False):
        super().__init__(dim, elementwise_affine=elementwise_affine, eps=eps)

    def forward(self, x):
        return super().forward(x.float()).type_as(x)


# ── Attention blocks ───────────────────────────────────────────────


class WanSelfAttention(nn.Module):
    def __init__(self, dim, num_heads, window_size=(-1, -1), qk_norm=True, eps=1e-6):
        assert dim % num_heads == 0
        super().__init__()
        self.dim = dim
        self.num_heads = num_heads
        self.head_dim = dim // num_heads
        self.window_size = window_size

        self.q = nn.Linear(dim, dim)
        self.k = nn.Linear(dim, dim)
        self.v = nn.Linear(dim, dim)
        self.o = nn.Linear(dim, dim)
        self.norm_q = WanRMSNorm(dim, eps=eps) if qk_norm else nn.Identity()
        self.norm_k = WanRMSNorm(dim, eps=eps) if qk_norm else nn.Identity()

    def forward(self, x, seq_lens, rope_apply_func, **kwargs):
        b, s, n, d = *x.shape[:2], self.num_heads, self.head_dim
        q = self.norm_q(self.q(x)).view(b, s, n, d)
        k = self.norm_k(self.k(x)).view(b, s, n, d)
        v = self.v(x).view(b, s, n, d)
        x = flash_attention(
            q=rope_apply_func(q), k=rope_apply_func(k), v=v,
            k_lens=seq_lens, window_size=self.window_size,
        )
        return self.o(x.flatten(2))


class WanT2VCrossAttention(WanSelfAttention):
    def forward(self, x, context, context_lens):
        b, n, d = x.size(0), self.num_heads, self.head_dim
        q = self.norm_q(self.q(x)).view(b, -1, n, d)
        k = self.norm_k(self.k(context)).view(b, -1, n, d)
        v = self.v(context).view(b, -1, n, d)
        x = flash_attention(q, k, v, k_lens=context_lens)
        return self.o(x.flatten(2))


class WanI2VCrossAttention(WanSelfAttention):
    def __init__(self, dim, num_heads, window_size=(-1, -1), qk_norm=True, eps=1e-6):
        super().__init__(dim, num_heads, window_size, qk_norm, eps)
        self.k_img = nn.Linear(dim, dim)
        self.v_img = nn.Linear(dim, dim)
        self.norm_k_img = WanRMSNorm(dim, eps=eps) if qk_norm else nn.Identity()

    def forward(self, x, context, context_lens):
        img_ctx_len = context.shape[1] - T5_CONTEXT_TOKEN_NUMBER
        context_img = context[:, :img_ctx_len]
        context = context[:, img_ctx_len:]
        b, n, d = x.size(0), self.num_heads, self.head_dim

        q = self.norm_q(self.q(x)).view(b, -1, n, d)
        k = self.norm_k(self.k(context)).view(b, -1, n, d)
        v = self.v(context).view(b, -1, n, d)
        k_img = self.norm_k_img(self.k_img(context_img)).view(b, -1, n, d)
        v_img = self.v_img(context_img).view(b, -1, n, d)

        img_x = flash_attention(q, k_img, v_img, k_lens=None)
        x = flash_attention(q, k, v, k_lens=context_lens)
        return self.o((x + img_x).flatten(2))


_CROSS_ATTN = {
    "t2v_cross_attn": WanT2VCrossAttention,
    "i2v_cross_attn": WanI2VCrossAttention,
}


class WanAttentionBlock(nn.Module):
    def __init__(
        self, cross_attn_type, dim, ffn_dim, num_heads,
        window_size=(-1, -1), qk_norm=True, cross_attn_norm=False, eps=1e-6,
    ):
        super().__init__()
        self.norm1 = WanLayerNorm(dim, eps)
        self.self_attn = WanSelfAttention(dim, num_heads, window_size, qk_norm, eps)
        self.norm3 = (
            WanLayerNorm(dim, eps, elementwise_affine=True)
            if cross_attn_norm else nn.Identity()
        )
        self.cross_attn = _CROSS_ATTN[cross_attn_type](
            dim, num_heads, (-1, -1), qk_norm, eps,
        )
        self.norm2 = WanLayerNorm(dim, eps)
        self.ffn = nn.Sequential(
            nn.Linear(dim, ffn_dim),
            nn.GELU(approximate="tanh"),
            nn.Linear(ffn_dim, dim),
        )
        self.modulation = nn.Parameter(torch.randn(1, 6, dim) / dim ** 0.5)

    def forward(self, x, e, seq_lens, context, context_lens, **kwargs):
        assert e.dtype == torch.float32
        with torch.amp.autocast('cuda', dtype=torch.float32):
            e = (self.modulation + e).chunk(6, dim=1)

        y = self.self_attn(
            self.norm1(x).float() * (1 + e[1]) + e[0],
            seq_lens, **kwargs,
        )
        with torch.amp.autocast('cuda', dtype=torch.float32):
            x = x + y * e[2]

        x = x + self.cross_attn(self.norm3(x), context, context_lens)
        y = self.ffn(self.norm2(x).float() * (1 + e[4]) + e[3])
        with torch.amp.autocast('cuda', dtype=torch.float32):
            x = x + y * e[5]
        return x


# ── Output head ────────────────────────────────────────────────────


class Head(nn.Module):
    def __init__(self, dim, out_dim, patch_size, eps=1e-6):
        super().__init__()
        self.patch_size = patch_size
        out_channels = math.prod(patch_size) * out_dim
        self.norm = WanLayerNorm(dim, eps)
        self.head = nn.Linear(dim, out_channels)
        self.modulation = nn.Parameter(torch.randn(1, 2, dim) / dim ** 0.5)

    def forward(self, x, e):
        assert e.dtype == torch.float32
        with torch.amp.autocast('cuda', dtype=torch.float32):
            e = (self.modulation + e.unsqueeze(1)).chunk(2, dim=1)
            return self.head(self.norm(x) * (1 + e[1]) + e[0])


class MLPProj(nn.Module):
    def __init__(self, in_dim, out_dim, flf_pos_emb=False):
        super().__init__()
        self.proj = nn.Sequential(
            nn.LayerNorm(in_dim), nn.Linear(in_dim, in_dim),
            nn.GELU(), nn.Linear(in_dim, out_dim),
            nn.LayerNorm(out_dim),
        )
        if flf_pos_emb:
            self.emb_pos = nn.Parameter(
                torch.zeros(1, FIRST_LAST_FRAME_CONTEXT_TOKEN_NUMBER, 1280)
            )

    def forward(self, image_embeds):
        if hasattr(self, "emb_pos"):
            bs, n, d = image_embeds.shape
            image_embeds = image_embeds.view(-1, 2 * n, d) + self.emb_pos
        return self.proj(image_embeds)


# ── Main SCAIL DiT Model ──────────────────────────────────────────


class SCAILModel(ModelMixin, ConfigMixin):
    """SCAIL diffusion transformer backbone.

    Extends Wan I2V with pose-conditioned denoising via a dedicated
    pose patch embedding and SCAIL-specific RoPE offsets.
    """

    ignore_for_config = [
        "patch_size", "cross_attn_norm", "qk_norm", "text_dim", "window_size",
    ]
    _no_split_modules = ["WanAttentionBlock"]

    @register_to_config
    def __init__(
        self,
        model_type="t2v",
        patch_size=(1, 2, 2),
        text_len=512,
        in_dim=16,
        dim=2048,
        ffn_dim=8192,
        freq_dim=256,
        text_dim=4096,
        out_dim=16,
        num_heads=16,
        num_layers=32,
        window_size=(-1, -1),
        qk_norm=True,
        cross_attn_norm=True,
        pose_rope_shift=(0, 0, 120),
        eps=1e-6,
    ):
        super().__init__()
        assert model_type in ("t2v", "i2v", "flf2v", "vace")
        self.model_type = model_type
        self.patch_size = patch_size
        self.text_len = text_len
        self.in_dim = in_dim
        self.dim = dim
        self.ffn_dim = ffn_dim
        self.freq_dim = freq_dim
        self.out_dim = out_dim
        self.num_heads = num_heads
        self.num_layers = num_layers
        self.pose_rope_shift = pose_rope_shift

        # Embeddings
        self.patch_embedding = nn.Conv3d(
            in_dim, dim, kernel_size=patch_size, stride=patch_size,
        )
        self.patch_embedding_pose = nn.Conv3d(
            in_dim, dim, kernel_size=patch_size, stride=patch_size,
        )
        self.text_embedding = nn.Sequential(
            nn.Linear(text_dim, dim), nn.GELU(approximate="tanh"),
            nn.Linear(dim, dim),
        )
        self.time_embedding = nn.Sequential(
            nn.Linear(freq_dim, dim), nn.SiLU(), nn.Linear(dim, dim),
        )
        self.time_projection = nn.Sequential(
            nn.SiLU(), nn.Linear(dim, dim * 6),
        )

        # Transformer blocks
        cross_attn_type = "t2v_cross_attn" if model_type == "t2v" else "i2v_cross_attn"
        self.blocks = nn.ModuleList([
            WanAttentionBlock(
                cross_attn_type, dim, ffn_dim, num_heads,
                window_size, qk_norm, cross_attn_norm, eps,
            )
            for _ in range(num_layers)
        ])

        # Output head
        self.head = Head(dim, out_dim, patch_size, eps)

        # RoPE frequency buffer
        assert (dim % num_heads) == 0 and (dim // num_heads) % 2 == 0
        d = dim // num_heads
        self.freqs = torch.cat([
            rope_params(8192, d - 4 * (d // 6)),
            rope_params(8192, 2 * (d // 6)),
            rope_params(8192, 2 * (d // 6)),
        ], dim=1)
        self.hidden_size_head = d

        # CLIP image projection (for i2v / flf2v)
        if model_type in ("i2v", "flf2v"):
            self.img_emb = MLPProj(1280, dim, flf_pos_emb=(model_type == "flf2v"))

        self.init_weights()

    def init_weights(self):
        for m in self.modules():
            if isinstance(m, nn.Linear):
                nn.init.xavier_uniform_(m.weight)
                if m.bias is not None:
                    nn.init.zeros_(m.bias)
        nn.init.xavier_uniform_(self.patch_embedding.weight.flatten(1))
        for m in self.text_embedding.modules():
            if isinstance(m, nn.Linear):
                nn.init.normal_(m.weight, std=0.02)
        for m in self.time_embedding.modules():
            if isinstance(m, nn.Linear):
                nn.init.normal_(m.weight, std=0.02)
        nn.init.zeros_(self.head.head.weight)

    def forward(
        self,
        x: list[torch.Tensor],
        pose_latents: list[torch.Tensor],
        ref_latents: list[torch.Tensor],
        t: torch.Tensor,
        context: list[torch.Tensor],
        seq_len: float,
        clip_fea: torch.Tensor | None = None,
    ) -> list[torch.Tensor]:
        """Forward pass through the SCAIL DiT.

        Args:
            x: List of noisy video latents [C, F, H, W].
            pose_latents: List of pose latents [C, F, H/2, W/2].
            ref_latents: List of reference image latents [C, 1, H, W].
            t: Diffusion timesteps [B].
            context: List of text embeddings.
            seq_len: Max sequence length.
            clip_fea: CLIP image features.
        """
        assert clip_fea is not None
        device = self.patch_embedding.weight.device
        if self.freqs.device != device:
            self.freqs = self.freqs.to(device)

        # Merge to batch (stay on CPU to save GPU memory)
        x = torch.cat([u.unsqueeze(0) for u in x], dim=0)
        ref_latents = torch.cat([u.unsqueeze(0) for u in ref_latents], dim=0)
        pose_latents = torch.cat([u.unsqueeze(0) for u in pose_latents], dim=0)

        # Apply masks (on CPU — these are zero/one fills, lightweight)
        def _zeros_mask(inp, mask_dim=4):
            b, d, t_, h, w = inp.shape
            return torch.cat([
                inp,
                torch.zeros(b, mask_dim, t_, h, w, device=inp.device, dtype=inp.dtype),
            ], dim=1)

        def _ones_mask(inp, mask_dim=4):
            b, d, t_, h, w = inp.shape
            return torch.cat([
                inp,
                torch.ones(b, mask_dim, t_, h, w, device=inp.device, dtype=inp.dtype),
            ], dim=1)

        x = _zeros_mask(x)
        ref_latents = _ones_mask(ref_latents)
        pose_latents = _ones_mask(pose_latents)

        B, D, T, H, W = x.shape
        ref_length = 1 * H * W // reduce(mul, self.patch_size)
        seq_length = T * ref_length
        pose_length = T * (H // 2) * (W // 2) // reduce(mul, self.patch_size)

        # ── Patch embeddings (move to GPU just-in-time, delete raw inputs) ──
        # Concatenate ref + noise, move to GPU, embed, then free the raw tensor
        x_combined = torch.cat([ref_latents, x], dim=2)
        del x, ref_latents  # free CPU copies

        x_emb = self.patch_embedding(x_combined.to(device).float()).to(self.patch_embedding.weight.dtype)
        del x_combined  # free GPU copy of raw input

        # Pose embedding: move to GPU, embed, free
        pose_emb = self.patch_embedding_pose(pose_latents.to(device).float()).to(self.patch_embedding.weight.dtype)
        del pose_latents  # free CPU copy (GPU copy freed by autograd)

        x = torch.cat([
            rearrange(x_emb, "b c t h w -> b (t h w) c"),
            rearrange(pose_emb, "b c t h w -> b (t h w) c"),
        ], dim=1)
        del x_emb, pose_emb  # free intermediate GPU tensors

        seq_lens = torch.tensor([u.size(0) for u in x], dtype=torch.long)

        # Time embedding (small — stays on GPU)
        with torch.amp.autocast('cuda', dtype=torch.float32):
            e = self.time_embedding(
                sinusoidal_embedding_1d(self.freq_dim, t.to(device)).float()
            )
            e0 = self.time_projection(e).unflatten(1, (6, self.dim))

        # Text context (move to GPU for text_embedding, small)
        context = self.text_embedding(torch.stack([
            torch.cat([u, u.new_zeros(self.text_len - u.size(0), u.size(1))])
            for u in context
        ]).to(device))

        if clip_fea is not None:
            context_clip = self.img_emb(clip_fea.to(device))
            context = torch.cat([context_clip, context], dim=1)
            del context_clip

        rope_t = T // self.patch_size[0]
        rope_h = H // self.patch_size[1]
        rope_w = W // self.patch_size[2]
        grid_sizes = torch.stack([
            torch.tensor((rope_t, rope_h, rope_w), dtype=torch.long)
            for _ in range(B)
        ])

        kwargs = dict(
            e=e0, seq_lens=seq_lens, grid_sizes=grid_sizes,
            freqs=self.freqs, context=context, context_lens=None,
            ref_length=ref_length, seq_length=seq_length,
            pose_length=pose_length,
            rope_T=rope_t, rope_H=rope_h, rope_W=rope_w,
            hidden_size_head=self.hidden_size_head,
            global_rope_H=self.pose_rope_shift[1],
            global_rope_W=self.pose_rope_shift[2],
            rope_H_shift=0, rope_W_shift=0,
        )
        kwargs["rope_apply_func"] = partial(rope_apply_scail, **kwargs)

        for block in self.blocks:
            x = block(x, **kwargs)

        x = self.head(x, e)
        return self._unpatchify(x, grid_sizes, offset=ref_length)

    def _unpatchify(self, x, grid_sizes, offset=0):
        c = self.out_dim
        out = []
        for u, v in zip(x, grid_sizes.tolist()):
            u = u[offset:offset + math.prod(v)].view(*v, *self.patch_size, c)
            u = torch.einsum("fhwpqrc->cfphqwr", u)
            u = u.reshape(c, *[i * j for i, j in zip(v, self.patch_size)])
            out.append(u)
        return out
