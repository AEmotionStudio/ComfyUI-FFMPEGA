# coding: utf-8
# Copyright 2024-2025 The Alibaba Wan Team Authors. All rights reserved.
# Vendored and adapted for ComfyUI-FFMPEGA.
"""Attention utilities — flash attention with SDPA fallback.

Supports flash_attn 2/3 if installed, otherwise falls back to
``torch.nn.functional.scaled_dot_product_attention`` (always available).
"""

import warnings

import torch

__all__ = ["flash_attention", "attention"]

try:
    import flash_attn_interface  # type: ignore[import-not-found]
    FLASH_ATTN_3_AVAILABLE = True
except ModuleNotFoundError:
    FLASH_ATTN_3_AVAILABLE = False

try:
    import flash_attn  # type: ignore[import-not-found]
    FLASH_ATTN_2_AVAILABLE = True
except ModuleNotFoundError:
    FLASH_ATTN_2_AVAILABLE = False


def flash_attention(
    q, k, v,
    q_lens=None, k_lens=None,
    dropout_p=0.0, softmax_scale=None, q_scale=None,
    causal=False, window_size=(-1, -1),
    deterministic=False, dtype=torch.bfloat16, version=None,
):
    """Multi-backend attention with flash_attn 2/3 or SDPA fallback.

    Args:
        q: [B, Lq, Nq, C1]
        k: [B, Lk, Nk, C1]
        v: [B, Lk, Nk, C2]
        q_lens/k_lens: [B] sequence lengths
    """
    half_dtypes = (torch.float16, torch.bfloat16)
    assert dtype in half_dtypes

    b, lq, lk, out_dtype = q.size(0), q.size(1), k.size(1), q.dtype

    def half(x):
        return x if x.dtype in half_dtypes else x.to(dtype)

    # Check if we can use flash attention
    use_flash = (
        q.device.type == "cuda"
        and q.size(-1) <= 256
        and (FLASH_ATTN_2_AVAILABLE or FLASH_ATTN_3_AVAILABLE)
    )

    if not use_flash:
        # SDPA fallback — always available
        return _sdpa_attention(
            q, k, v, q_lens=q_lens, k_lens=k_lens,
            dropout_p=dropout_p, causal=causal, dtype=dtype,
        )

    # --- Flash Attention path ---
    if q_lens is None:
        q = half(q.flatten(0, 1))
        q_lens = torch.tensor(
            [lq] * b, dtype=torch.int32
        ).to(device=q.device, non_blocking=True)
    else:
        q = half(torch.cat([u[:v] for u, v in zip(q, q_lens)]))

    if k_lens is None:
        k = half(k.flatten(0, 1))
        v = half(v.flatten(0, 1))
        k_lens = torch.tensor(
            [lk] * b, dtype=torch.int32
        ).to(device=k.device, non_blocking=True)
    else:
        k = half(torch.cat([u[:vv] for u, vv in zip(k, k_lens)]))
        v = half(torch.cat([u[:vv] for u, vv in zip(v, k_lens)]))

    q = q.to(v.dtype)
    k = k.to(v.dtype)

    if q_scale is not None:
        q = q * q_scale

    if version is not None and version == 3 and not FLASH_ATTN_3_AVAILABLE:
        warnings.warn(
            "Flash attention 3 not available, using flash attention 2."
        )

    cu_q = torch.cat([q_lens.new_zeros([1]), q_lens]).cumsum(
        0, dtype=torch.int32
    ).to(q.device, non_blocking=True)
    cu_k = torch.cat([k_lens.new_zeros([1]), k_lens]).cumsum(
        0, dtype=torch.int32
    ).to(q.device, non_blocking=True)

    if (version is None or version == 3) and FLASH_ATTN_3_AVAILABLE:
        x = flash_attn_interface.flash_attn_varlen_func(
            q=q, k=k, v=v,
            cu_seqlens_q=cu_q, cu_seqlens_k=cu_k,
            seqused_q=None, seqused_k=None,
            max_seqlen_q=lq, max_seqlen_k=lk,
            softmax_scale=softmax_scale,
            causal=causal,
            deterministic=deterministic,
        )[0].unflatten(0, (b, lq))
    else:
        x = flash_attn.flash_attn_varlen_func(
            q=q, k=k, v=v,
            cu_seqlens_q=cu_q, cu_seqlens_k=cu_k,
            max_seqlen_q=lq, max_seqlen_k=lk,
            dropout_p=dropout_p,
            softmax_scale=softmax_scale,
            causal=causal,
            window_size=window_size,
            deterministic=deterministic,
        ).unflatten(0, (b, lq))

    return x.type(out_dtype)


def _sdpa_attention(
    q, k, v,
    q_lens=None, k_lens=None,
    dropout_p=0.0, causal=False, dtype=torch.bfloat16,
):
    """Fallback attention using PyTorch's scaled_dot_product_attention."""
    if q_lens is not None or k_lens is not None:
        warnings.warn(
            "Padding mask disabled with SDPA fallback. "
            "May impact performance with variable-length sequences."
        )

    q = q.transpose(1, 2).to(dtype)
    k = k.transpose(1, 2).to(dtype)
    v = v.transpose(1, 2).to(dtype)

    out = torch.nn.functional.scaled_dot_product_attention(
        q, k, v, attn_mask=None, is_causal=causal, dropout_p=dropout_p,
    )
    return out.transpose(1, 2).contiguous()


def attention(q, k, v, **kwargs):
    """Unified entry — routes to flash or SDPA."""
    fa_version = kwargs.pop("fa_version", None)
    if FLASH_ATTN_2_AVAILABLE or FLASH_ATTN_3_AVAILABLE:
        return flash_attention(q, k, v, version=fa_version, **kwargs)
    return _sdpa_attention(
        q, k, v,
        q_lens=kwargs.get("q_lens"),
        k_lens=kwargs.get("k_lens"),
        dropout_p=kwargs.get("dropout_p", 0.0),
        causal=kwargs.get("causal", False),
        dtype=kwargs.get("dtype", torch.bfloat16),
    )
