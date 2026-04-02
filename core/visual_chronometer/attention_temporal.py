# coding: utf-8
"""Vendored from Pulse-of-Motion (Apache 2.0) — src/modules/attention_temporal_videoae.py

Temporal attention modules for the 2+1D VAE.
Imports are rewritten to use sibling vendored modules.
"""

from inspect import isfunction
import math
import torch
import torch.nn.functional as F
from torch import nn, einsum
from einops import rearrange, repeat
from typing import Optional, Any

try:
    import xformers
    import xformers.ops
    XFORMERS_IS_AVAILBLE = True
except Exception:
    XFORMERS_IS_AVAILBLE = False

from .nn_utils import (
    checkpoint,
    conv_nd,
    zero_module,
    normalization,
)


def exists(val):
    return val is not None


def default(val, d):
    if exists(val):
        return val
    return d() if isfunction(d) else d


class RelativePosition(nn.Module):
    def __init__(self, num_units, max_relative_position):
        super().__init__()
        self.num_units = num_units
        self.max_relative_position = max_relative_position
        self.embeddings_table = nn.Parameter(
            torch.Tensor(max_relative_position * 2 + 1, num_units)
        )
        nn.init.xavier_uniform_(self.embeddings_table)

    def forward(self, length_q, length_k):
        device = self.embeddings_table.device
        range_vec_q = torch.arange(length_q, device=device)
        range_vec_k = torch.arange(length_k, device=device)
        distance_mat = range_vec_k[None, :] - range_vec_q[:, None]
        distance_mat_clipped = torch.clamp(
            distance_mat, -self.max_relative_position, self.max_relative_position
        )
        final_mat = distance_mat_clipped + self.max_relative_position
        final_mat = final_mat.long()
        embeddings = self.embeddings_table[final_mat]
        return embeddings


class QKVAttention(nn.Module):
    """QKV attention with relative position bias."""

    def __init__(self, n_heads):
        super().__init__()
        self.n_heads = n_heads

    def forward(self, qkv, rp=None):
        bs, width, length = qkv.shape
        assert width % (3 * self.n_heads) == 0
        ch = width // (3 * self.n_heads)
        q, k, v = qkv.chunk(3, dim=1)
        scale = 1 / math.sqrt(math.sqrt(ch))
        weight = torch.einsum(
            "bct,bcs->bts",
            (q * scale).view(bs * self.n_heads, ch, length),
            (k * scale).view(bs * self.n_heads, ch, length),
        )

        if rp is not None:
            k_rp, v_rp = rp
            weight2 = torch.einsum(
                "bct,tsc->bts",
                (q * scale).view(bs * self.n_heads, ch, length),
                k_rp,
            )
            weight = weight + weight2

        weight = torch.softmax(weight.float(), dim=-1).type(weight.dtype)
        a = torch.einsum(
            "bts,bcs->bct",
            weight,
            v.reshape(bs * self.n_heads, ch, length),
        )

        if rp is not None:
            a2 = torch.einsum("bts,tsd->btd", weight, v_rp)
            a2 = rearrange(a2, "(b h) t d -> b (h d) t", h=self.n_heads)
            a = a + a2

        return a.reshape(bs, -1, length)


class TemporalCrossAttention(nn.Module):
    def __init__(
        self,
        query_dim,
        context_dim=None,
        heads=8,
        dim_head=64,
        dropout=0.0,
        temporal_length=None,
        image_length=None,
        use_relative_position=False,
        img_video_joint_train=False,
        use_tempoal_causal_attn=False,
        bidirectional_causal_attn=False,
        tempoal_attn_type=None,
        joint_train_mode="same_batch",
        **kwargs,
    ):
        super().__init__()
        inner_dim = dim_head * heads
        context_dim = default(context_dim, query_dim)
        self.context_dim = context_dim
        self.scale = dim_head**-0.5
        self.heads = heads
        self.temporal_length = temporal_length
        self.use_relative_position = use_relative_position
        self.img_video_joint_train = img_video_joint_train
        self.bidirectional_causal_attn = bidirectional_causal_attn
        self.joint_train_mode = joint_train_mode
        self.tempoal_attn_type = tempoal_attn_type

        self.to_q = nn.Linear(query_dim, inner_dim, bias=False)
        self.to_k = nn.Linear(context_dim, inner_dim, bias=False)
        self.to_v = nn.Linear(context_dim, inner_dim, bias=False)

        self.mask = None  # Simplified — no training masks needed for inference

        if use_relative_position:
            assert temporal_length is not None
            self.relative_position_k = RelativePosition(
                num_units=dim_head, max_relative_position=temporal_length
            )
            self.relative_position_v = RelativePosition(
                num_units=dim_head, max_relative_position=temporal_length
            )

        self.to_out = nn.Sequential(
            nn.Linear(inner_dim, query_dim), nn.Dropout(dropout)
        )

        nn.init.constant_(self.to_q.weight, 0)
        nn.init.constant_(self.to_k.weight, 0)
        nn.init.constant_(self.to_v.weight, 0)
        nn.init.constant_(self.to_out[0].weight, 0)
        nn.init.constant_(self.to_out[0].bias, 0)

    def forward(self, x, context=None, mask=None):
        nh = self.heads
        out = x
        q = self.to_q(out)
        context = default(context, x)
        k = self.to_k(context)
        v = self.to_v(context)

        q, k, v = map(lambda t: rearrange(t, "b n (h d) -> (b h) n d", h=nh), (q, k, v))
        sim = einsum("b i d, b j d -> b i j", q, k) * self.scale

        if self.use_relative_position:
            len_q, len_k, len_v = q.shape[1], k.shape[1], v.shape[1]
            k2 = self.relative_position_k(len_q, len_k)
            sim2 = einsum("b t d, t s d -> b t s", q, k2) * self.scale
            sim += sim2

        if exists(self.mask):
            if mask is None:
                mask = self.mask.to(sim.device)
            else:
                mask = self.mask.to(sim.device).bool() & mask

        if mask is not None:
            max_neg_value = -1e9
            sim = sim + (1 - mask.float()) * max_neg_value

        attn = sim.softmax(dim=-1)
        out = einsum("b i j, b j d -> b i d", attn, v)

        if self.use_relative_position:
            v2 = self.relative_position_v(len_q, len_v)
            out2 = einsum("b t s, t s d -> b t d", attn, v2)
            out += out2

        out = rearrange(out, "(b h) n d -> b n (h d)", h=nh)
        return self.to_out(out)


class CrossAttention(nn.Module):
    """Cross attention used in both spatial and temporal blocks."""

    def __init__(
        self,
        query_dim,
        context_dim=None,
        heads=8,
        dim_head=64,
        dropout=0.0,
        sa_shared_kv=False,
        shared_type="only_first",
        **kwargs,
    ):
        super().__init__()
        inner_dim = dim_head * heads
        context_dim = default(context_dim, query_dim)
        self.sa_shared_kv = sa_shared_kv
        self.shared_type = shared_type

        self.scale = dim_head**-0.5
        self.heads = heads
        self.dim_head = dim_head

        self.to_q = nn.Linear(query_dim, inner_dim, bias=False)
        self.to_k = nn.Linear(context_dim, inner_dim, bias=False)
        self.to_v = nn.Linear(context_dim, inner_dim, bias=False)

        self.to_out = nn.Sequential(
            nn.Linear(inner_dim, query_dim), nn.Dropout(dropout)
        )
        self.attention_op: Optional[Any] = None

    def forward(self, x, context=None, mask=None):
        h = self.heads
        b = x.shape[0]

        q = self.to_q(x)
        context = default(context, x)
        k = self.to_k(context)
        v = self.to_v(context)

        q, k, v = map(lambda t: rearrange(t, "b n (h d) -> (b h) n d", h=h), (q, k, v))

        sim = einsum("b i d, b j d -> b i j", q, k) * self.scale

        if exists(mask):
            mask = rearrange(mask, "b ... -> b (...)")
            max_neg_value = -torch.finfo(sim.dtype).max
            mask = repeat(mask, "b j -> (b h) () j", h=h)
            sim.masked_fill_(~mask, max_neg_value)

        attn = sim.softmax(dim=-1)
        out = einsum("b i j, b j d -> b i d", attn, v)
        out = rearrange(out, "(b h) n d -> b n (h d)", h=h)
        return self.to_out(out)

    def efficient_forward(self, x, context=None, mask=None):
        q = self.to_q(x)
        context = default(context, x)
        k = self.to_k(context)
        v = self.to_v(context)

        b, _, _ = q.shape
        q, k, v = map(
            lambda t: t.unsqueeze(3)
            .reshape(b, t.shape[1], self.heads, self.dim_head)
            .permute(0, 2, 1, 3)
            .reshape(b * self.heads, t.shape[1], self.dim_head)
            .contiguous(),
            (q, k, v),
        )
        out = xformers.ops.memory_efficient_attention(
            q, k, v, attn_bias=None, op=self.attention_op
        )

        out = (
            out.unsqueeze(0)
            .reshape(b, self.heads, out.shape[1], self.dim_head)
            .permute(0, 2, 1, 3)
            .reshape(b, out.shape[1], self.heads * self.dim_head)
        )
        return self.to_out(out)


class FeedForward(nn.Module):
    def __init__(self, dim, dim_out=None, mult=4, glu=False, dropout=0.0):
        super().__init__()
        inner_dim = int(dim * mult)
        dim_out = default(dim_out, dim)
        project_in = nn.Sequential(nn.Linear(dim, inner_dim), nn.GELU())

        self.net = nn.Sequential(
            project_in, nn.Dropout(dropout), nn.Linear(inner_dim, dim_out)
        )

    def forward(self, x):
        return self.net(x)


class BasicTransformerBlockST(nn.Module):
    """Spatial-Temporal transformer block used in the 2+1D encoder/decoder."""

    def __init__(
        self,
        dim,
        n_heads,
        d_head,
        dropout=0.0,
        context_dim=None,
        gated_ff=True,
        checkpoint=True,
        temporal_length=None,
        image_length=None,
        use_relative_position=True,
        img_video_joint_train=False,
        cross_attn_on_tempoal=False,
        temporal_crossattn_type="selfattn",
        order="stst",
        temporalcrossfirst=False,
        temporal_context_dim=None,
        split_stcontext=False,
        local_spatial_temporal_attn=False,
        window_size=2,
        random_t=False,
        **kwargs,
    ):
        super().__init__()
        self.attn1 = CrossAttention(
            query_dim=dim, heads=n_heads, dim_head=d_head, dropout=dropout, **kwargs,
        )
        self.attn2 = CrossAttention(
            query_dim=dim, context_dim=context_dim, heads=n_heads,
            dim_head=d_head, dropout=dropout, **kwargs,
        )
        if XFORMERS_IS_AVAILBLE:
            self.attn1.forward = self.attn1.efficient_forward
            self.attn2.forward = self.attn2.efficient_forward

        self.ff = FeedForward(dim, dropout=dropout, glu=gated_ff)

        self.norm1 = nn.LayerNorm(dim)
        self.norm2 = nn.LayerNorm(dim)
        self.norm3 = nn.LayerNorm(dim)
        self._checkpoint = checkpoint
        self.order = order
        self.temporalcrossfirst = temporalcrossfirst
        self.split_stcontext = split_stcontext
        self.random_t = random_t

        if not split_stcontext:
            temporal_context_dim = context_dim

        self.temporal_crossattn_type = temporal_crossattn_type
        self.attn1_tmp = TemporalCrossAttention(
            query_dim=dim, heads=n_heads, dim_head=d_head, dropout=dropout,
            temporal_length=temporal_length, image_length=image_length,
            use_relative_position=use_relative_position,
            img_video_joint_train=img_video_joint_train, **kwargs,
        )
        self.attn2_tmp = TemporalCrossAttention(
            query_dim=dim, heads=n_heads, dim_head=d_head, dropout=dropout,
            context_dim=(temporal_context_dim if temporal_crossattn_type == "crossattn" else None),
            temporal_length=temporal_length, image_length=image_length,
            use_relative_position=use_relative_position,
            img_video_joint_train=img_video_joint_train, **kwargs,
        )
        self.norm4 = nn.LayerNorm(dim)
        self.norm5 = nn.LayerNorm(dim)

    def forward(self, x, context=None, temporal_context=None, no_temporal_attn=None, attn_mask=None, **kwargs):
        if not self.split_stcontext:
            temporal_context = context.detach().clone() if context is not None else None

        if context is None and temporal_context is None:
            return self._forward_nocontext(x)
        else:
            if no_temporal_attn:
                return self._forward_no_temporal_attn(x, context, temporal_context)
            return self._forward(x, context, temporal_context)

    def _forward(self, x, context=None, temporal_context=None, mask=None, no_temporal_attn=None):
        assert x.dim() == 5
        b, c, t, h, w = x.shape
        x = self._st_cross_attn(x, context, temporal_context=temporal_context, order=self.order, mask=mask)
        x = self.ff(self.norm3(x)) + x
        x = rearrange(x, "(b h w) t c -> b c t h w", b=b, h=h, w=w)
        return x

    def _forward_no_temporal_attn(self, x, context=None, temporal_context=None):
        assert x.dim() == 5
        b, c, t, h, w = x.shape
        mask = torch.zeros([1, t, t], device=x.device).bool()
        x = self._st_cross_attn(x, context, temporal_context=temporal_context, order=self.order, mask=mask)
        x = self.ff(self.norm3(x)) + x
        x = rearrange(x, "(b h w) t c -> b c t h w", b=b, h=h, w=w)
        return x

    def _forward_nocontext(self, x, no_temporal_attn=None):
        assert x.dim() == 5
        b, c, t, h, w = x.shape
        x = self._st_cross_attn(x, order=self.order, no_temporal_attn=no_temporal_attn)
        x = self.ff(self.norm3(x)) + x
        x = rearrange(x, "(b h w) t c -> b c t h w", b=b, h=h, w=w)
        return x

    def _st_cross_attn(self, x, context=None, temporal_context=None, order="stst", mask=None, no_temporal_attn=None):
        b, c, t, h, w = x.shape

        # spatial self attention
        x = rearrange(x, "b c t h w -> (b t) (h w) c")
        x = self.attn1(self.norm1(x)) + x
        x = rearrange(x, "(b t) (h w) c -> b c t h w", b=b, h=h)

        # temporal self attention
        x = rearrange(x, "b c t h w -> (b h w) t c")
        x = self.attn1_tmp(self.norm4(x), mask=mask) + x

        x = rearrange(x, "(b h w) t c -> b c t h w", b=b, h=h, w=w)

        # spatial cross attention
        x = rearrange(x, "b c t h w -> (b t) (h w) c")
        if context is not None:
            if context.shape[0] == t:
                context_ = context
            else:
                context_ = []
                for i in range(context.shape[0]):
                    context_.append(context[i].unsqueeze(0).repeat(t, 1, 1))
                context_ = torch.cat(context_, dim=0)
        else:
            context_ = None
        x = self.attn2(self.norm2(x), context=context_) + x

        # temporal cross attention
        x = rearrange(x, "(b t) (h w) c -> b c t h w", b=b, h=h)
        x = rearrange(x, "b c t h w -> (b h w) t c")
        if temporal_context is not None:
            temporal_context = repeat(temporal_context, "b n d -> (b hw) n d", hw=h * w)
        x = self.attn2_tmp(self.norm5(x), context=temporal_context, mask=mask) + x

        return x
