# coding: utf-8
# Copyright 2024-2025 The Alibaba Wan Team Authors. All rights reserved.
# Vendored and adapted for ComfyUI-FFMPEGA.
"""LoRA fusion utilities for SCAIL models."""

import torch


def fuse_lora_with_diff_b(
    model: torch.nn.Module,
    lora_state_dict: dict[str, torch.Tensor],
    alpha: float = 1.0,
):
    """Fuse LoRA weights into a model in-place.

    Supports ``lora_down``/``lora_up`` weight pairs with optional
    ``diff_b`` bias terms.
    """
    model_state = model.state_dict()
    lora_keys = [
        k for k in lora_state_dict if k.endswith(".lora_down.weight")
    ]

    for lora_key in lora_keys:
        prefix = lora_key[: -len(".lora_down.weight")]
        lora_up_key = prefix + ".lora_up.weight"
        lora_diff_b_key = prefix + ".diff_b"

        if lora_up_key not in lora_state_dict:
            continue

        weight_key = prefix + ".weight"
        bias_key = prefix + ".bias"

        # Strip diffusion_model prefix if present
        if weight_key.startswith("diffusion_model."):
            weight_key = weight_key[len("diffusion_model."):]
        if bias_key.startswith("diffusion_model."):
            bias_key = bias_key[len("diffusion_model."):]

        if weight_key not in model_state:
            continue

        W = model_state[weight_key]
        W_down = lora_state_dict[lora_key]
        W_up = lora_state_dict[lora_up_key]

        delta_W = torch.matmul(W_up, W_down).to(W.dtype).to(W.device)
        model_state[weight_key] = W + alpha * delta_W

        if bias_key in model_state and lora_diff_b_key in lora_state_dict:
            diff_b = lora_state_dict[lora_diff_b_key]
            model_state[bias_key] = (
                model_state[bias_key]
                + alpha * diff_b.to(model_state[bias_key].dtype).to(
                    model_state[bias_key].device
                )
            )

    model.load_state_dict(model_state)
