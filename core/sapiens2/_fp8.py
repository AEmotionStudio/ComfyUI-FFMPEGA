# coding: utf-8
"""Native FP8 matmul for the Sapiens2 dense backbone.

The 5B "normal" checkpoint is ~20 GB in fp32 — too large for a 12 GB
card.  We keep the ViT backbone's attention / MLP ``nn.Linear`` weights
in ``float8_e4m3fn`` (~5 GB total) and run them through
``torch._scaled_mm`` so the matmuls execute natively in FP8 instead of
being dequantized back to bf16.

The quantization format is produced offline by :mod:`._convert_fp8`:
each quantized weight is stored as ``<name>.weight`` (fp8) plus a
per-output-channel scale ``<name>.weight.scale`` (fp32, shape ``(out,)``),
where ``weight_fp8 = (W / scale[:, None]).to(float8_e4m3fn)``.

This mirrors the proven pattern in ``core/fish_speech_synthesizer.py``
(itself based on ComfyUI-WanVideoWrapper's ``fp8_optimization``), kept
local here to avoid coupling the two synthesizers.  Native FP8 matmul
requires CUDA compute capability >= 8.9 (RTX 40-series / Ada and up).
"""

from __future__ import annotations

import logging

import torch
import torch.nn as nn
import torch.nn.functional as F

log = logging.getLogger("ffmpega")

_FP8_DTYPES = (torch.float8_e4m3fn, torch.float8_e5m2)


def supports_fp8_matmul() -> bool:
    """True iff the current CUDA device supports native FP8 matmul (CC >= 8.9)."""
    if not torch.cuda.is_available():
        return False
    cap = torch.cuda.get_device_capability()
    return cap[0] > 8 or (cap[0] == 8 and cap[1] >= 9)


def _dequantize_weight(cls, base_dtype: torch.dtype) -> torch.Tensor:
    """Reconstruct ``W ~= weight_fp8 * scale`` in ``base_dtype``.

    Used for the non-3D fallback path (e.g. a Linear that receives a 2D
    input), where ``torch._scaled_mm`` does not apply.
    """
    w = cls.weight.to(base_dtype)
    scale_weight = getattr(cls, "scale_weight", None)
    if scale_weight is not None:
        sw = scale_weight.to(device=w.device, dtype=base_dtype)
        if sw.numel() == 1:
            w = w * sw
        else:
            # Per-output-channel scale → broadcast over input dim.
            w = w * sw.reshape(-1, 1)
    return w


def _fp8_linear_forward(cls, base_dtype: torch.dtype, input: torch.Tensor):
    """FP8 ``nn.Linear.forward`` replacement using ``torch._scaled_mm``.

    Keeps the weight in FP8, casts the input to FP8, and runs a
    hardware-accelerated scaled matmul.  Output is in ``base_dtype``
    (bf16).  Non-FP8 weights and non-3D inputs fall back to a correct
    (dequantized) path.
    """
    weight_dtype = cls.weight.dtype
    if weight_dtype not in _FP8_DTYPES:
        return cls.original_forward(input)

    if input.dim() == 3:
        B, L, C = input.shape

        scale_weight = getattr(cls, "scale_weight", None)
        if scale_weight is None:
            scale_weight = torch.ones(
                (cls.weight.shape[0],), device=input.device, dtype=torch.float32
            )
        else:
            scale_weight = scale_weight.to(input.device)

        x2d = input.reshape(-1, C).float()

        # Dynamic per-row (per-token) activation scaling — quantize each
        # row by its own absmax so small-magnitude rows keep precision.
        # Far more accurate than a flat input scale; matmul accumulates the
        # row scale (scale_a) and per-channel weight scale (scale_b).
        scale_input = (x2d.abs().amax(dim=1, keepdim=True) / 448.0).clamp(min=1e-12)
        inn = (x2d / scale_input).clamp(-448, 448).to(torch.float8_e4m3fn).contiguous()

        bias = cls.bias.to(base_dtype) if cls.bias is not None else None

        out = torch._scaled_mm(
            inn,
            cls.weight.t(),
            out_dtype=base_dtype,
            bias=bias,
            scale_a=scale_input,
            scale_b=scale_weight.reshape(1, -1).contiguous(),
        )
        return out.reshape(B, L, cls.weight.shape[0])

    # Fallback for non-3D inputs: dequantize and run a plain linear.
    w = _dequantize_weight(cls, base_dtype)
    bias = cls.bias.to(base_dtype) if cls.bias is not None else None
    return F.linear(input.to(base_dtype), w, bias)


def convert_fp8_linear(module: nn.Module, base_dtype: torch.dtype) -> int:
    """Patch every FP8-weight ``nn.Linear`` in *module* for native FP8 matmul.

    Only layers whose weight is already FP8 are patched (the offline
    converter leaves heads / norms / conv in bf16).  Returns the number
    of patched layers so callers can sanity-check the count.
    """
    patched = 0
    for _name, sub in module.named_modules():
        if isinstance(sub, nn.Linear) and sub.weight.dtype in _FP8_DTYPES:
            original_forward = sub.forward
            sub.original_forward = original_forward
            sub.forward = (
                lambda inp, m=sub: _fp8_linear_forward(m, base_dtype, inp)
            )
            patched += 1
    log.info("[Sapiens2] Patched %d Linear layers for native FP8 matmul", patched)
    return patched


def extract_scale_weights(state_dict: dict) -> dict:
    """Pop ``<name>.weight.scale`` keys and attach them to their modules.

    Returns a mapping ``{module_name: scale_tensor}``.  The scale keys
    are removed from *state_dict* in place so ``load_state_dict`` does
    not complain about unexpected keys.
    """
    scales: dict[str, torch.Tensor] = {}
    for key in [k for k in state_dict if k.endswith(".weight.scale")]:
        module_name = key[: -len(".weight.scale")]
        scales[module_name] = state_dict.pop(key)
    return scales


def attach_scale_weights(model: nn.Module, scales: dict) -> None:
    """Set ``module.scale_weight`` for every quantized Linear from *scales*.

    Scales are placed on the same device as the module's weight so the
    hot ``_scaled_mm`` path doesn't move them every call.
    """
    modules = dict(model.named_modules())
    for module_name, scale in scales.items():
        mod = modules.get(module_name)
        if mod is not None:
            mod.scale_weight = scale.float().to(mod.weight.device)
