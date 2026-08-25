"""
INT8 ConvRot Quantization Operations Module for SeedVR2

Runtime support for checkpoints saved in ComfyUI's ``int8_tensorwise`` layout
with the block-Hadamard ("ConvRot") rotation applied.

Layout, per quantized ``nn.Linear``:
    <layer>.weight        int8    [out, in]  pre-rotated round((W @ H_blk^T) / s)
    <layer>.weight_scale  float32 [out, 1]   per-output-row scale
    <layer>.comfy_quant   uint8   [72]       UTF-8 JSON describing the format

Everything else (biases, norms, ada modulation, RoPE freqs) stays floating point.

The rotation smears per-channel outliers across each group of ``convrot_groupsize``
input features so INT8 survives them. Because the regular Hadamard is symmetric and
orthogonal it cancels in the product: (x @ H)(W @ H^T)^T == x @ W^T. The weight is
rotated offline (already baked into the file); the activation is rotated online
inside the kernel, which is why the weight is never dequantized at runtime.
"""

import json
import torch
import torch.nn as nn
from typing import Any, Dict, Optional, Tuple

COMFY_QUANT_SUFFIX = ".comfy_quant"
WEIGHT_SCALE_SUFFIX = ".weight_scale"
SUPPORTED_QUANT_FORMAT = "int8_tensorwise"
DEFAULT_CONVROT_GROUPSIZE = 256

# comfy_kitchen's TensorWiseINT8Layout.MIN_SM_VERSION — below this there is no
# IMMA path and the kernel has no reason to be faster than plain fp16.
MIN_SM_VERSION = (7, 5)

try:
    import comfy_kitchen as _comfy_kitchen
    INT8_AVAILABLE = True
except ImportError:
    _comfy_kitchen = None
    INT8_AVAILABLE = False


def validate_int8_availability() -> None:
    """Raise a clear error if the INT8 runtime is unusable on this machine."""
    if not INT8_AVAILABLE:
        raise RuntimeError(
            "SeedVR2 int8_convrot models require the 'comfy_kitchen' package, "
            "which is not installed in this environment. Install it, or use an "
            "fp8/gguf SeedVR2 variant instead."
        )
    if not torch.cuda.is_available():
        raise RuntimeError(
            "SeedVR2 int8_convrot models require CUDA — the INT8 kernels have no "
            "CPU implementation. Use an fp8/gguf SeedVR2 variant instead."
        )
    capability = torch.cuda.get_device_capability()
    if capability < MIN_SM_VERSION:
        raise RuntimeError(
            f"SeedVR2 int8_convrot models require a GPU of compute capability "
            f"{MIN_SM_VERSION[0]}.{MIN_SM_VERSION[1]} or newer for the INT8 tensor-core "
            f"path; this GPU reports {capability[0]}.{capability[1]}. "
            f"Use an fp8/gguf SeedVR2 variant instead."
        )


class Int8ConvRotLinear(nn.Module):
    """Linear layer backed by INT8 ConvRot weights.

    Weights are held as **buffers**, not parameters, for two reasons:

    1. ``load_state_dict(..., assign=True)`` wraps assigned parameters in
       ``nn.Parameter(t, requires_grad=<meta param's flag>)``, which rejects an
       int8 tensor. Buffers are assigned as-is.
    2. BlockSwap moves whole blocks with ``self.to(device)`` and sizes them with
       ``get_module_memory_mb``; both cover buffers.

    Unlike the GGUF layers these deliberately carry no ``tensor_type``/``tensor_shape``
    markers — those mean "keep me on CPU and dequantize per layer", and INT8 wants
    the opposite. The packed weight lives on the compute device like a normal one.
    """

    def __init__(self, in_features: int, out_features: int, bias: bool = True,
                 convrot: bool = True, convrot_groupsize: int = DEFAULT_CONVROT_GROUPSIZE,
                 device=None, dtype=None) -> None:
        super().__init__()
        self.in_features = in_features
        self.out_features = out_features
        self.convrot = convrot
        self.convrot_groupsize = convrot_groupsize

        # Empty placeholders; real values arrive via load_state_dict(assign=True).
        self.register_buffer(
            "weight", torch.empty(out_features, in_features, dtype=torch.int8, device=device))
        self.register_buffer(
            "weight_scale", torch.empty(out_features, 1, dtype=torch.float32, device=device))
        if bias:
            self.register_buffer(
                "bias", torch.empty(out_features, dtype=dtype or torch.float16, device=device))
        else:
            self.register_buffer("bias", None)

    def forward(self, input: torch.Tensor) -> torch.Tensor:
        bias = self.bias
        if bias is not None and (bias.dtype != input.dtype or bias.device != input.device):
            bias = bias.to(device=input.device, dtype=input.dtype)

        return _comfy_kitchen.int8_linear(
            input,
            self.weight,
            self.weight_scale,
            bias,
            input.dtype,
            convrot=self.convrot,
            convrot_groupsize=self.convrot_groupsize,
        )

    def extra_repr(self) -> str:
        return (f"in_features={self.in_features}, out_features={self.out_features}, "
                f"bias={self.bias is not None}, convrot={self.convrot}, "
                f"groupsize={self.convrot_groupsize}")


def is_int8_convrot_state(state: Dict[str, torch.Tensor]) -> bool:
    """Check whether a state dict carries ComfyUI per-layer quantization tags."""
    return any(key.endswith(COMFY_QUANT_SUFFIX) for key in state)


def parse_comfy_quant(state: Dict[str, torch.Tensor]) -> Dict[str, Dict[str, Any]]:
    """Decode every ``*.comfy_quant`` tag into a per-module config.

    Args:
        state: Loaded state dict (tags are uint8 tensors holding UTF-8 JSON).

    Returns:
        Mapping of module path (the key without the ``.comfy_quant`` suffix) to
        the decoded config dict.

    Raises:
        ValueError: If a tag is undecodable or names an unsupported format.
    """
    quant_map: Dict[str, Dict[str, Any]] = {}

    for key, tensor in state.items():
        if not key.endswith(COMFY_QUANT_SUFFIX):
            continue
        module_path = key[: -len(COMFY_QUANT_SUFFIX)]

        try:
            payload = bytes(tensor.detach().cpu().to(torch.uint8).numpy().tobytes())
            config = json.loads(payload.decode("utf-8"))
        except Exception as exc:
            raise ValueError(f"Could not decode quantization tag '{key}': {exc}") from exc

        quant_format = config.get("format")
        if quant_format != SUPPORTED_QUANT_FORMAT:
            raise ValueError(
                f"Layer '{module_path}' uses quantization format '{quant_format}', but this "
                f"SeedVR2 loader only supports '{SUPPORTED_QUANT_FORMAT}'."
            )

        quant_map[module_path] = config

    return quant_map


def strip_quant_metadata(state: Dict[str, torch.Tensor]) -> int:
    """Drop the ``*.comfy_quant`` tags from a state dict in place.

    The tags are consumed by :func:`parse_comfy_quant`; leaving them in would make
    them unexpected keys at ``load_state_dict`` time.

    Returns:
        Number of keys removed.
    """
    tags = [key for key in state if key.endswith(COMFY_QUANT_SUFFIX)]
    for key in tags:
        del state[key]
    return len(tags)


def convert_state_to_compute_dtype(state: Dict[str, torch.Tensor],
                                   target_dtype: torch.dtype) -> int:
    """Cast the non-quantized floating-point tensors to the compute dtype.

    Skips the INT8 weights (not floating point) and the ``*.weight_scale`` tensors,
    which the kernel requires in float32. Without this the model's first parameter
    would be fp16 and ``CompatibleDiT`` would treat the whole DiT as an fp16 model.

    Returns:
        Number of tensors converted.
    """
    converted = 0
    for key, tensor in state.items():
        if key.endswith(WEIGHT_SCALE_SUFFIX):
            continue
        if not torch.is_tensor(tensor) or not tensor.is_floating_point():
            continue
        if tensor.dtype == target_dtype:
            continue
        state[key] = tensor.to(target_dtype)
        converted += 1
    return converted


def replace_linear_with_int8(model: nn.Module, quant_map: Dict[str, Dict[str, Any]],
                             debug: Optional['Debug'] = None) -> Tuple[int, Dict[str, int]]:
    """Swap every ``nn.Linear`` named in ``quant_map`` for an :class:`Int8ConvRotLinear`.

    Must run *before* ``load_state_dict`` so the replacement modules are the ones
    that receive the weights. Safe on a meta-device model — the placeholder buffers
    are created on whatever device the module currently lives on.

    Args:
        model: The DiT (typically still on meta).
        quant_map: Output of :func:`parse_comfy_quant`.
        debug: Optional Debug instance for logging.

    Returns:
        Tuple of (replacements_made, group_sizes) where group_sizes counts layers
        per ConvRot group size, for logging.

    Raises:
        ValueError: If a quantized key does not name an ``nn.Linear`` on this model.
    """
    modules = dict(model.named_modules())
    replacements_made = 0
    group_sizes: Dict[str, int] = {}

    for module_path, config in quant_map.items():
        target = modules.get(module_path)
        if target is None:
            raise ValueError(
                f"Checkpoint quantizes '{module_path}', which does not exist on this "
                f"SeedVR2 model. The checkpoint does not match the selected architecture."
            )
        if not isinstance(target, nn.Linear):
            raise ValueError(
                f"Checkpoint quantizes '{module_path}', which is a "
                f"{type(target).__name__} rather than nn.Linear."
            )

        convrot = bool(config.get("convrot", False))
        groupsize = int(config.get("convrot_groupsize", DEFAULT_CONVROT_GROUPSIZE))
        if convrot and target.in_features % groupsize != 0:
            raise ValueError(
                f"Layer '{module_path}' has in_features={target.in_features}, which is not "
                f"divisible by the ConvRot group size {groupsize}."
            )

        quantized = Int8ConvRotLinear(
            target.in_features,
            target.out_features,
            bias=target.bias is not None,
            convrot=convrot,
            convrot_groupsize=groupsize,
            device=target.weight.device,
            dtype=target.weight.dtype if target.bias is None else target.bias.dtype,
        )

        parent_path, _, attr_name = module_path.rpartition(".")
        parent = modules[parent_path] if parent_path else model
        setattr(parent, attr_name, quantized)

        replacements_made += 1
        label = f"convrot{groupsize}" if convrot else "plain"
        group_sizes[label] = group_sizes.get(label, 0) + 1

    if debug:
        debug.log(f"Replaced {replacements_made} Linear layers with INT8 ConvRot versions",
                  category="dit")

    return replacements_made, group_sizes
