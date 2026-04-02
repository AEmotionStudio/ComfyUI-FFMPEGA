# coding: utf-8
"""Vendored from Pulse-of-Motion (Apache 2.0) — src/models/autoencoder_temporal.py

Temporal 1D-CNN encoder/decoder for the 2+1D VAE.
Imports rewritten to use sibling vendored modules.
"""

import math
import torch
import torch.nn as nn
import torch.nn.functional as F
from einops import rearrange, repeat

from .attention_temporal import (
    exists, default, CrossAttention as SpatialCrossAttention_Attn,
)

try:
    import xformers
    import xformers.ops as xops
    XFORMERS_IS_AVAILBLE = True
except Exception:
    XFORMERS_IS_AVAILBLE = False


def silu(x):
    return x * torch.sigmoid(x)


class SiLU(nn.Module):
    def forward(self, x):
        return silu(x)


def Normalize(in_channels, norm_type="group"):
    assert norm_type in ["group", "batch"]
    if norm_type == "group":
        return torch.nn.GroupNorm(
            num_groups=32, num_channels=in_channels, eps=1e-6, affine=True
        )
    elif norm_type == "batch":
        return torch.nn.SyncBatchNorm(in_channels)


class SamePadConv3d(nn.Module):
    def __init__(self, in_channels, out_channels, kernel_size, stride=1, bias=True, padding_type="replicate"):
        super().__init__()
        if isinstance(kernel_size, int):
            kernel_size = (kernel_size,) * 3
        if isinstance(stride, int):
            stride = (stride,) * 3

        total_pad = tuple([k - s for k, s in zip(kernel_size, stride)])
        pad_input = []
        for p in total_pad[::-1]:
            pad_input.append((p // 2 + p % 2, p // 2))
        pad_input = sum(pad_input, tuple())
        self.pad_input = pad_input
        self.padding_type = padding_type

        self.conv = nn.Conv3d(
            in_channels, out_channels, kernel_size, stride=stride, padding=0, bias=bias
        )

    def forward(self, x):
        return self.conv(F.pad(x, self.pad_input, mode=self.padding_type))


class ResBlock(nn.Module):
    def __init__(self, in_channels, out_channels=None, conv_shortcut=False, dropout=0.0, norm_type="group", padding_type="replicate"):
        super().__init__()
        self.in_channels = in_channels
        out_channels = in_channels if out_channels is None else out_channels
        self.out_channels = out_channels
        self.use_conv_shortcut = conv_shortcut

        self.norm1 = Normalize(in_channels, norm_type)
        self.conv1 = SamePadConv3d(in_channels, out_channels, kernel_size=3, padding_type=padding_type)
        self.dropout = torch.nn.Dropout(dropout)
        self.norm2 = Normalize(in_channels, norm_type)
        self.conv2 = SamePadConv3d(out_channels, out_channels, kernel_size=3, padding_type=padding_type)
        if self.in_channels != self.out_channels:
            self.conv_shortcut = SamePadConv3d(in_channels, out_channels, kernel_size=3, padding_type=padding_type)

    def forward(self, x):
        h = x
        h = self.norm1(h)
        h = silu(h)
        h = self.conv1(h)
        h = self.norm2(h)
        h = silu(h)
        h = self.conv2(h)

        if self.in_channels != self.out_channels:
            x = self.conv_shortcut(x)
        return x + h


class SpatialCrossAttention(nn.Module):
    def __init__(self, query_dim, patch_size=1, context_dim=None, heads=8, dim_head=64, dropout=0.0):
        super().__init__()
        from .attention_temporal import exists, default
        inner_dim = dim_head * heads
        context_dim = default(context_dim, query_dim)

        self.scale = dim_head**-0.5
        self.heads = heads
        self.dim_head = dim_head

        self.patch_size = patch_size
        patch_dim = query_dim * patch_size * patch_size
        self.norm = nn.LayerNorm(patch_dim)

        self.to_q = nn.Linear(patch_dim, inner_dim, bias=False)
        self.to_k = nn.Linear(context_dim, inner_dim, bias=False)
        self.to_v = nn.Linear(context_dim, inner_dim, bias=False)

        self.to_out = nn.Sequential(
            nn.Linear(inner_dim, patch_dim), nn.Dropout(dropout)
        )

    def forward(self, x, context=None, mask=None):
        from .attention_temporal import exists, default
        from einops import rearrange, repeat, einsum as _  # einsum from torch

        b, c, t, height, width = x.shape

        divide_factor_height = height // self.patch_size
        divide_factor_width = width // self.patch_size
        x = rearrange(
            x, "b c t (df1 ph) (df2 pw) -> (b t) (df1 df2) (ph pw c)",
            df1=divide_factor_height, df2=divide_factor_width,
            ph=self.patch_size, pw=self.patch_size,
        )
        x = self.norm(x)

        context = default(context, x)
        context = repeat(context, "b n d -> (b t) n d", b=b, t=t)

        q = self.to_q(x)
        k = self.to_k(context)
        v = self.to_v(context)

        q, k, v = map(
            lambda t: rearrange(t, "b n (h d) -> (b h) n d", h=self.heads), (q, k, v)
        )

        if XFORMERS_IS_AVAILBLE:
            out = xops.memory_efficient_attention(q, k, v, scale=self.scale)
        else:
            from torch import einsum
            sim = einsum("b i d, b j d -> b i j", q, k) * self.scale
            attn = sim.softmax(dim=-1)
            out = einsum("b i j, b j d -> b i d", attn, v)

        out = rearrange(out, "(b h) n d -> b n (h d)", h=self.heads)

        ret = self.to_out(out)
        ret = rearrange(
            ret, "(b t) (df1 df2) (ph pw c) -> b c t (df1 ph) (df2 pw)",
            b=b, t=t, df1=divide_factor_height, df2=divide_factor_width,
            ph=self.patch_size, pw=self.patch_size,
        )
        return ret


class EncoderTemporal1DCNN(nn.Module):
    def __init__(self, *, ch, out_ch, attn_temporal_factor=[], temporal_scale_factor=4, hidden_channel=128, **ignore_kwargs):
        super().__init__()
        self.ch = ch
        self.temb_ch = 0
        self.temporal_scale_factor = temporal_scale_factor

        self.conv_in = SamePadConv3d(ch, hidden_channel, kernel_size=3, padding_type="replicate")

        self.mid_blocks = nn.ModuleList()
        num_ds = int(math.log2(temporal_scale_factor))
        norm_type = "group"

        curr_temporal_factor = 1
        for i in range(num_ds):
            block = nn.Module()
            in_channels = hidden_channel * 2**i
            out_channels = hidden_channel * 2**(i + 1)
            temporal_stride = 2
            curr_temporal_factor = curr_temporal_factor * 2

            block.down = SamePadConv3d(
                in_channels, out_channels, kernel_size=3,
                stride=(temporal_stride, 1, 1), padding_type="replicate",
            )
            block.res = ResBlock(out_channels, out_channels, norm_type=norm_type)
            block.attn = nn.ModuleList()
            if curr_temporal_factor in attn_temporal_factor:
                block.attn.append(SpatialCrossAttention(query_dim=out_channels, context_dim=1024))

            self.mid_blocks.append(block)

        self.final_block = nn.Sequential(
            Normalize(out_channels, norm_type),
            SiLU(),
            SamePadConv3d(out_channels, out_ch * 2, kernel_size=3, padding_type="replicate"),
        )

        self.initialize_weights()

    def initialize_weights(self):
        def _basic_init(module):
            if isinstance(module, nn.Linear):
                if module.weight.requires_grad_:
                    torch.nn.init.xavier_uniform_(module.weight)
                    if module.bias is not None:
                        nn.init.constant_(module.bias, 0)
            if isinstance(module, nn.Conv3d):
                torch.nn.init.xavier_uniform_(module.weight)
                if module.bias is not None:
                    nn.init.constant_(module.bias, 0)
        self.apply(_basic_init)

    def forward(self, x, text_embeddings=None, text_attn_mask=None):
        h = self.conv_in(x)
        for block in self.mid_blocks:
            h = block.down(h)
            h = block.res(h)
            if len(block.attn) > 0:
                for attn in block.attn:
                    h = attn(h, context=text_embeddings, mask=text_attn_mask) + h
        h = self.final_block(h)
        return h


class DecoderTemporal1DCNN(nn.Module):
    def __init__(self, *, ch, out_ch, attn_temporal_factor=[], temporal_scale_factor=4, hidden_channel=128, **ignore_kwargs):
        super().__init__()
        self.ch = ch
        self.temb_ch = 0
        self.temporal_scale_factor = temporal_scale_factor

        num_us = int(math.log2(temporal_scale_factor))
        norm_type = "group"

        enc_out_channels = hidden_channel * 2**num_us
        self.conv_in = SamePadConv3d(ch, enc_out_channels, kernel_size=3, padding_type="replicate")

        self.mid_blocks = nn.ModuleList()
        curr_temporal_factor = self.temporal_scale_factor

        for i in range(num_us):
            block = nn.Module()
            in_channels = enc_out_channels if i == 0 else hidden_channel * 2**(num_us - i + 1)
            out_channels = hidden_channel * 2**(num_us - i)

            block.up = torch.nn.ConvTranspose3d(
                in_channels, out_channels,
                kernel_size=(3, 3, 3), stride=(2, 1, 1),
                padding=(1, 1, 1), output_padding=(1, 0, 0),
            )
            block.res1 = ResBlock(out_channels, out_channels, norm_type=norm_type)
            block.attn1 = nn.ModuleList()
            if curr_temporal_factor in attn_temporal_factor:
                block.attn1.append(SpatialCrossAttention(query_dim=out_channels, context_dim=1024))

            block.res2 = ResBlock(out_channels, out_channels, norm_type=norm_type)
            block.attn2 = nn.ModuleList()
            if curr_temporal_factor in attn_temporal_factor:
                block.attn2.append(SpatialCrossAttention(query_dim=out_channels, context_dim=1024))

            curr_temporal_factor = curr_temporal_factor / 2
            self.mid_blocks.append(block)

        self.conv_last = SamePadConv3d(out_channels, out_ch, kernel_size=3)
        self.initialize_weights()

    def initialize_weights(self):
        def _basic_init(module):
            if isinstance(module, nn.Linear):
                if module.weight.requires_grad_:
                    torch.nn.init.xavier_uniform_(module.weight)
                    if module.bias is not None:
                        nn.init.constant_(module.bias, 0)
            if isinstance(module, (nn.Conv3d, nn.ConvTranspose3d)):
                torch.nn.init.xavier_uniform_(module.weight)
                if module.bias is not None:
                    nn.init.constant_(module.bias, 0)
        self.apply(_basic_init)

    def forward(self, x, text_embeddings=None, text_attn_mask=None):
        h = self.conv_in(x)
        for block in self.mid_blocks:
            h = block.up(h)
            h = block.res1(h)
            if len(block.attn1) > 0:
                for attn in block.attn1:
                    h = attn(h, context=text_embeddings, mask=text_attn_mask) + h
            h = block.res2(h)
            if len(block.attn2) > 0:
                for attn in block.attn2:
                    h = attn(h, context=text_embeddings, mask=text_attn_mask) + h
        h = self.conv_last(h)
        return h
