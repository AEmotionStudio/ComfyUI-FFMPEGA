# coding: utf-8
"""Vendored from Pulse-of-Motion (Apache 2.0) — src/modules/utils.py

Core neural network utility functions used by the attention and encoder modules.
Stripped of distributed/training helpers not needed for inference.
"""

import math
from inspect import isfunction

import torch
import torch.nn as nn


def exists(val):
    return val is not None


def default(val, d):
    if exists(val):
        return val
    return d() if isfunction(d) else d


def checkpoint(func, inputs, params, flag):
    """Gradient checkpointing wrapper. Disabled during inference."""
    if flag:
        return torch.utils.checkpoint.checkpoint(func, *inputs)
    return func(*inputs)


def zero_module(module):
    """Zero out all parameters of a module and return it."""
    for p in module.parameters():
        p.detach().zero_()
    return module


def conv_nd(dims, *args, **kwargs):
    """Create a 1D, 2D, or 3D convolution module."""
    if dims == 1:
        return nn.Conv1d(*args, **kwargs)
    elif dims == 2:
        return nn.Conv2d(*args, **kwargs)
    elif dims == 3:
        return nn.Conv3d(*args, **kwargs)
    raise ValueError(f"unsupported dimensions: {dims}")


class GroupNormSpecific(nn.GroupNorm):
    def forward(self, x):
        if x.dtype == torch.float16 or x.dtype == torch.bfloat16:
            return super().forward(x).type(x.dtype)
        return super().forward(x.float()).type(x.dtype)


def normalization(channels, num_groups=32):
    """Standard GroupNorm normalization layer."""
    return GroupNormSpecific(num_groups, channels)
