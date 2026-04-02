# coding: utf-8
"""Vendored from Pulse-of-Motion (Apache 2.0) — src/models/autoencoder2plus1d_1dcnn.py

2+1D VAE with temporal 1D-CNN. Imports rewritten to sibling modules.
Training methods stripped. pl.LightningModule → torch.nn.Module.
"""

import math
import torch
import torch.nn as nn
from einops import rearrange, repeat
from typing import Optional, Any

from .autoencoder import AutoencoderKL
from .ae_modules import Normalize, nonlinearity
from .attention_temporal import (
    exists, default, CrossAttention as CA_Temporal,
    QKVAttention, RelativePosition,
)
from .nn_utils import normalization, conv_nd, zero_module
from .distributions import DiagonalGaussianDistribution
from .autoencoder_temporal import EncoderTemporal1DCNN, DecoderTemporal1DCNN

try:
    import xformers
    import xformers.ops as xops
    XFORMERS_IS_AVAILBLE = True
except Exception:
    XFORMERS_IS_AVAILBLE = False


# ---------------------------------------------------------------------------
# 3D helper blocks
# ---------------------------------------------------------------------------

class TemporalConvLayer(nn.Module):
    def __init__(self, in_channels, out_channels):
        super().__init__()
        self.norm = Normalize(in_channels)
        self.conv = torch.nn.Conv3d(
            in_channels, out_channels,
            kernel_size=(3, 3, 3), stride=1, padding=(1, 1, 1),
        )
        nn.init.constant_(self.conv.weight, 0)
        nn.init.constant_(self.conv.bias, 0)

    def forward(self, x):
        h = self.norm(x)
        h = nonlinearity(h)
        h = self.conv(h)
        return h


class ResnetBlock2plus1D(nn.Module):
    def __init__(self, *, in_channels, out_channels=None, conv_shortcut=False,
                 dropout, temb_channels=512, kernel_size_t=3, padding_t=1, stride_t=1):
        super().__init__()
        self.in_channels = in_channels
        out_channels = in_channels if out_channels is None else out_channels
        self.out_channels = out_channels
        self.use_conv_shortcut = conv_shortcut

        self.norm1 = Normalize(in_channels)
        self.conv1 = torch.nn.Conv3d(in_channels, out_channels, kernel_size=(1, 3, 3), stride=1, padding=(0, 1, 1))
        self.conv1_tmp = TemporalConvLayer(out_channels, out_channels)

        if temb_channels > 0:
            self.temb_proj = torch.nn.Linear(temb_channels, out_channels)

        self.norm2 = Normalize(out_channels)
        self.dropout = torch.nn.Dropout(dropout)
        self.conv2 = torch.nn.Conv3d(out_channels, out_channels, kernel_size=(1, 3, 3), stride=1, padding=(0, 1, 1))
        self.conv2_tmp = TemporalConvLayer(out_channels, out_channels)

        if self.in_channels != self.out_channels:
            if self.use_conv_shortcut:
                self.conv_shortcut = torch.nn.Conv3d(in_channels, out_channels, kernel_size=(1, 3, 3), stride=1, padding=(0, 1, 1))
            else:
                self.nin_shortcut = torch.nn.Conv3d(in_channels, out_channels, kernel_size=(1, 1, 1), stride=1, padding=(0, 0, 0))
        self.conv3_tmp = TemporalConvLayer(out_channels, out_channels)

    def forward(self, x, temb, mask_temporal=False):
        h = x
        h = self.norm1(h)
        h = nonlinearity(h)
        h = self.conv1(h)
        if not mask_temporal:
            h = self.conv1_tmp(h) + h

        if temb is not None:
            h = h + self.temb_proj(nonlinearity(temb))[:, :, None, None]

        h = self.norm2(h)
        h = nonlinearity(h)
        h = self.dropout(h)
        h = self.conv2(h)
        if not mask_temporal:
            h = self.conv2_tmp(h) + h

        if self.in_channels != self.out_channels:
            if self.use_conv_shortcut:
                x = self.conv_shortcut(x)
            else:
                x = self.nin_shortcut(x)
            if not mask_temporal:
                x = self.conv3_tmp(x) + x

        return x + h


class AttnBlock3D(nn.Module):
    def __init__(self, in_channels):
        super().__init__()
        self.in_channels = in_channels
        self.norm = Normalize(in_channels)
        self.q = torch.nn.Conv3d(in_channels, in_channels, kernel_size=1, stride=1, padding=0)
        self.k = torch.nn.Conv3d(in_channels, in_channels, kernel_size=1, stride=1, padding=0)
        self.v = torch.nn.Conv3d(in_channels, in_channels, kernel_size=1, stride=1, padding=0)
        self.proj_out = torch.nn.Conv3d(in_channels, in_channels, kernel_size=1, stride=1, padding=0)

    def forward(self, x):
        h_ = self.norm(x)
        q = self.q(h_)
        k = self.k(h_)
        v = self.v(h_)

        b, c, t, h, w = q.shape
        q = rearrange(q, "b c t h w -> (b t) (h w) c")
        k = rearrange(k, "b c t h w -> (b t) c (h w)")

        w_ = torch.bmm(q, k)
        w_ = w_ * (int(c) ** (-0.5))
        w_ = torch.nn.functional.softmax(w_, dim=2)

        v = rearrange(v, "b c t h w -> (b t) c (h w)")
        w_ = w_.permute(0, 2, 1)
        h_ = torch.bmm(v, w_)
        h_ = rearrange(h_, "(b t) c (h w) -> b c t h w", b=b, h=h)
        h_ = self.proj_out(h_)

        return x + h_


class CrossAttention3D(nn.Module):
    """Cross attention used in the 2+1D encoder/decoder."""
    def __init__(self, query_dim, patch_size=1, context_dim=None, heads=8, dim_head=64, dropout=0.0):
        super().__init__()
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

        self.to_out = nn.Sequential(nn.Linear(inner_dim, patch_dim), nn.Dropout(dropout))

    def forward(self, x, context=None, mask=None):
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

        q, k, v = map(lambda t: rearrange(t, "b n (h d) -> (b h) n d", h=self.heads), (q, k, v))

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


class TemporalAttention(nn.Module):
    def __init__(self, channels, num_heads=1, num_head_channels=-1, max_temporal_length=64):
        super().__init__()
        if num_head_channels == -1:
            self.num_heads = num_heads
        else:
            assert channels % num_head_channels == 0
            self.num_heads = channels // num_head_channels

        self.norm = normalization(channels)
        self.qkv = zero_module(conv_nd(1, channels, channels * 3, 1))
        self.attention = QKVAttention(self.num_heads)
        self.relative_position_k = RelativePosition(
            num_units=channels // self.num_heads, max_relative_position=max_temporal_length,
        )
        self.relative_position_v = RelativePosition(
            num_units=channels // self.num_heads, max_relative_position=max_temporal_length,
        )
        self.proj_out = zero_module(conv_nd(1, channels, channels, 1))

    def forward(self, x, mask=None):
        b, c, t, h, w = x.shape
        out = rearrange(x, "b c t h w -> (b h w) c t")
        qkv = self.qkv(self.norm(out))
        len_q = qkv.size()[-1]
        k_rp = self.relative_position_k(len_q, len_q)
        v_rp = self.relative_position_v(len_q, len_q)
        out = self.attention(qkv, rp=(k_rp, v_rp))
        out = self.proj_out(out)
        out = rearrange(out, "(b h w) c t -> b c t h w", b=b, h=h, w=w)
        return x + out


# ---------------------------------------------------------------------------
# 2+1D Encoder / Decoder
# ---------------------------------------------------------------------------

class Downsample2plus1D(nn.Module):
    def __init__(self, in_channels, with_conv, temp_down):
        super().__init__()
        self.with_conv = with_conv
        self.temp_down = temp_down
        if self.with_conv:
            self.conv = torch.nn.Conv3d(
                in_channels, in_channels,
                kernel_size=(1, 3, 3), stride=(1, 2, 2), padding=0,
            )

    def forward(self, x, mask_temporal):
        if self.with_conv:
            pad = (0, 1, 0, 1, 0, 0)
            x = torch.nn.functional.pad(x, pad, mode="constant", value=0)
            x = self.conv(x)
        else:
            raise NotImplementedError
        return x


class Upsample2plus1D(nn.Module):
    def __init__(self, in_channels, with_conv, temp_up):
        super().__init__()
        self.with_conv = with_conv
        self.temp_up = temp_up
        if self.with_conv:
            self.conv = torch.nn.Conv3d(
                in_channels, in_channels,
                kernel_size=(1, 3, 3), stride=1, padding=(0, 1, 1),
            )

    def forward(self, x, mask_temporal):
        if self.temp_up and not mask_temporal:
            x = torch.nn.functional.interpolate(x, scale_factor=(2.0, 2.0, 2.0), mode="nearest")
        else:
            t = x.shape[2]
            x = rearrange(x, "b c t h w -> b (c t) h w")
            x = torch.nn.functional.interpolate(x, scale_factor=(2.0, 2.0), mode="nearest")
            x = rearrange(x, "b (c t) h w -> b c t h w", t=t)
        if self.with_conv:
            x = self.conv(x)
        return x


class Encoder2plus1D(nn.Module):
    def __init__(self, *, ch, out_ch, temporal_down_factor, ch_mult=(1, 2, 4, 8),
                 num_res_blocks, attn_resolutions, dropout=0.0, resamp_with_conv=True,
                 in_channels, resolution, z_channels, double_z=True,
                 use_linear_attn=False, attn_type="vanilla", mask_temporal=False, **ignore_kwargs):
        super().__init__()
        self.ch = ch
        self.temb_ch = 0
        self.num_resolutions = len(ch_mult)
        self.n_temporal_down = int(math.log2(temporal_down_factor))
        self.num_res_blocks = num_res_blocks
        self.resolution = resolution

        self.conv_in = torch.nn.Conv3d(in_channels, self.ch, kernel_size=(1, 3, 3), stride=1, padding=(0, 1, 1))

        curr_res = resolution
        in_ch_mult = (1,) + tuple(ch_mult)
        self.down = nn.ModuleList()
        cur_patch_size = 8

        for i_level in range(self.num_resolutions):
            block = nn.ModuleList()
            attn = nn.ModuleList()
            block_in = ch * in_ch_mult[i_level]
            block_out = ch * ch_mult[i_level]
            for i_block in range(self.num_res_blocks):
                block.append(ResnetBlock2plus1D(
                    in_channels=block_in, out_channels=block_out,
                    temb_channels=self.temb_ch, dropout=dropout,
                ))
                block_in = block_out
                if curr_res in attn_resolutions:
                    attn.append(CrossAttention3D(query_dim=block_in, patch_size=cur_patch_size, context_dim=1024))
            down = nn.Module()
            down.block = block
            down.attn = attn
            if i_level != self.num_resolutions - 1:
                temp_down = i_level <= self.n_temporal_down - 1
                down.downsample = Downsample2plus1D(block_in, resamp_with_conv, temp_down)
                curr_res = curr_res // 2
                cur_patch_size //= 2
            self.down.append(down)

        self.mid = nn.Module()
        self.mid.block_1 = ResnetBlock2plus1D(in_channels=block_in, out_channels=block_in, temb_channels=self.temb_ch, dropout=dropout)
        self.mid.attn_1 = AttnBlock3D(block_in)
        self.mid.attn_1_tmp = TemporalAttention(block_in, num_heads=1)
        self.mid.block_2 = ResnetBlock2plus1D(in_channels=block_in, out_channels=block_in, temb_channels=self.temb_ch, dropout=dropout)

        self.norm_out = Normalize(block_in)
        self.conv_out = torch.nn.Conv3d(
            block_in, 2 * z_channels if double_z else z_channels,
            kernel_size=(1, 3, 3), stride=1, padding=(0, 1, 1),
        )

    def forward(self, x, text_embeddings=None, text_attn_mask=None, mask_temporal=False):
        temb = None
        hs = [self.conv_in(x)]
        for i_level in range(self.num_resolutions):
            for i_block in range(self.num_res_blocks):
                h = self.down[i_level].block[i_block](hs[-1], temb, mask_temporal)
                if len(self.down[i_level].attn) > 0:
                    h = h + self.down[i_level].attn[i_block](h, context=text_embeddings, mask=text_attn_mask)
                hs.append(h)
            if i_level != self.num_resolutions - 1:
                hs.append(self.down[i_level].downsample(hs[-1], mask_temporal))

        h = hs[-1]
        h = self.mid.block_1(h, temb, mask_temporal)
        h = self.mid.attn_1(h)
        if not mask_temporal:
            h = self.mid.attn_1_tmp(h)
        h = self.mid.block_2(h, temb, mask_temporal)

        h = self.norm_out(h)
        h = nonlinearity(h)
        h = self.conv_out(h)
        return h


class Decoder2plus1D(nn.Module):
    def __init__(self, *, ch, out_ch, temporal_down_factor, ch_mult=(1, 2, 4, 8),
                 num_res_blocks, attn_resolutions, dropout=0.0, resamp_with_conv=True,
                 in_channels, resolution, z_channels, give_pre_end=False, tanh_out=False,
                 use_linear_attn=False, attn_type="vanilla", mask_temporal=False, **ignorekwargs):
        super().__init__()
        self.ch = ch
        self.temb_ch = 0
        self.num_resolutions = len(ch_mult)
        self.n_temporal_up = int(math.log2(temporal_down_factor))
        self.n_spatial_up = self.num_resolutions - 1
        self.num_res_blocks = num_res_blocks
        self.resolution = resolution
        self.give_pre_end = give_pre_end
        self.tanh_out = tanh_out

        in_ch_mult = (1,) + tuple(ch_mult)
        block_in = ch * ch_mult[self.num_resolutions - 1]
        curr_res = resolution // 2 ** (self.num_resolutions - 1)

        self.conv_in = torch.nn.Conv3d(z_channels, block_in, kernel_size=(1, 3, 3), stride=1, padding=(0, 1, 1))

        self.mid = nn.Module()
        self.mid.block_1 = ResnetBlock2plus1D(in_channels=block_in, out_channels=block_in, temb_channels=self.temb_ch, dropout=dropout)
        self.mid.attn_1 = AttnBlock3D(block_in)
        self.mid.attn_1_tmp = TemporalAttention(block_in, num_heads=1)
        self.mid.block_2 = ResnetBlock2plus1D(in_channels=block_in, out_channels=block_in, temb_channels=self.temb_ch, dropout=dropout)

        self.up = nn.ModuleList()
        cur_patch_size = 1

        for i_level in reversed(range(self.num_resolutions)):
            block = nn.ModuleList()
            attn = nn.ModuleList()
            block_out = ch * ch_mult[i_level]
            for i_block in range(self.num_res_blocks + 1):
                block.append(ResnetBlock2plus1D(
                    in_channels=block_in, out_channels=block_out,
                    temb_channels=self.temb_ch, dropout=dropout,
                ))
                block_in = block_out
                if curr_res in attn_resolutions:
                    attn.append(CrossAttention3D(query_dim=block_in, patch_size=cur_patch_size, context_dim=1024))
            up = nn.Module()
            up.block = block
            up.attn = attn
            if i_level != 0:
                temp_up = i_level <= self.num_resolutions - 1 - (self.n_spatial_up - self.n_temporal_up)
                up.upsample = Upsample2plus1D(block_in, resamp_with_conv, temp_up)
                curr_res = curr_res * 2
                cur_patch_size *= 2
            self.up.insert(0, up)

        self.norm_out = Normalize(block_in)
        self.conv_out = torch.nn.Conv3d(block_in, out_ch, kernel_size=(1, 3, 3), stride=1, padding=(0, 1, 1))

    def forward(self, z, text_embeddings=None, text_attn_mask=None, mask_temporal=False):
        self.last_z_shape = z.shape
        temb = None
        h = self.conv_in(z)

        h = self.mid.block_1(h, temb, mask_temporal)
        h = self.mid.attn_1(h)
        if not mask_temporal:
            h = self.mid.attn_1_tmp(h)
        h = self.mid.block_2(h, temb, mask_temporal)

        for i_level in reversed(range(self.num_resolutions)):
            for i_block in range(self.num_res_blocks + 1):
                h = self.up[i_level].block[i_block](h, temb, mask_temporal)
                if len(self.up[i_level].attn) > 0:
                    h = h + self.up[i_level].attn[i_block](h, context=text_embeddings, mask=text_attn_mask)
            if i_level != 0:
                h = self.up[i_level].upsample(h, mask_temporal)

        if self.give_pre_end:
            return h
        h = self.norm_out(h)
        h = nonlinearity(h)
        h = self.conv_out(h)
        if self.tanh_out:
            h = torch.tanh(h)
        return h


# ---------------------------------------------------------------------------
# Main composite model
# ---------------------------------------------------------------------------

class AutoencoderKL2plus1D_1dcnn(AutoencoderKL):
    def __init__(
        self, ddconfig, ppconfig, lossconfig, embed_dim=0, use_quant_conv=True,
        test=False, ckpt_path=None, ckpt_path_2d=None, ckpt_path_4temporal=None,
        ignore_keys_3d=[], img_video_joint_train=False, video_key="",
        caption_guide=False, t5_model_max_length=120, *args, **kwargs,
    ):
        super().__init__(
            ddconfig, lossconfig, embed_dim, use_quant_conv,
            *args, test=False, **kwargs,
        )
        self.use_quant_conv = use_quant_conv

        self.encoder_temporal = EncoderTemporal1DCNN(**ppconfig)
        self.decoder_temporal = DecoderTemporal1DCNN(**ppconfig)

        # Override 2D encoder/decoder from parent with 2+1D versions
        self.encoder = Encoder2plus1D(**ddconfig)
        self.decoder = Decoder2plus1D(**ddconfig)

        if use_quant_conv:
            assert embed_dim
            self.embed_dim = embed_dim
            self.quant_conv = torch.nn.Conv3d(2 * ddconfig["z_channels"], 2 * embed_dim, 1)
            self.post_quant_conv = torch.nn.Conv3d(embed_dim, ddconfig["z_channels"], 1)

        if ckpt_path is not None:
            self.init_from_ckpt(ckpt_path, ignore_keys=ignore_keys_3d)

    def encode_temporal(self, x, text_embeddings=None, text_attn_mask=None):
        moments = self.encoder_temporal(x, text_embeddings, text_attn_mask)
        posterior = DiagonalGaussianDistribution(moments)
        return posterior

    def decode_temporal(self, z, text_embeddings=None, text_attn_mask=None):
        return self.decoder_temporal(z, text_embeddings, text_attn_mask)

    def encode_2plus1d(self, x, text_embeddings=None, text_attn_mask=None, mask_temporal=False):
        h = self.encoder(x, text_embeddings, text_attn_mask, mask_temporal=mask_temporal)
        if self.use_quant_conv:
            h = self.quant_conv(h)
        posterior = DiagonalGaussianDistribution(h)
        return posterior

    def decode_2plus1d(self, z, text_embeddings=None, text_attn_mask=None, mask_temporal=False):
        if self.use_quant_conv:
            z = self.post_quant_conv(z)
        return self.decoder(z, text_embeddings, text_attn_mask, mask_temporal=mask_temporal)

    def encode(self, x, text_embeddings=None, text_attn_mask=None, sample_posterior=True, mask_temporal=False):
        posterior = self.encode_2plus1d(x, text_embeddings, text_attn_mask, mask_temporal=mask_temporal)
        z = posterior.sample() if sample_posterior else posterior.mode()

        if not mask_temporal:
            posterior = self.encode_temporal(z, text_embeddings, text_attn_mask)
            z = posterior.sample() if sample_posterior else posterior.mode()

        return z, posterior

    def decode(self, z, text_embeddings=None, text_attn_mask=None, mask_temporal=False):
        if not mask_temporal:
            z = self.decode_temporal(z, text_embeddings, text_attn_mask)
        return self.decode_2plus1d(z, text_embeddings, text_attn_mask, mask_temporal=mask_temporal)

    def forward(self, inputs, text_embeddings=None, text_attn_mask=None, sample_posterior=True, mask_temporal=False):
        z, posterior = self.encode(inputs, text_embeddings, text_attn_mask, sample_posterior, mask_temporal=mask_temporal)
        dec = self.decode(z, text_embeddings, text_attn_mask, mask_temporal=mask_temporal)
        return dec, posterior

    def get_last_layer(self):
        return self.decoder.conv_out.weight
