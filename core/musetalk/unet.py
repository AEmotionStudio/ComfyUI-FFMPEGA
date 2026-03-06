"""UNet wrapper for MuseTalk — audio-conditioned face inpainting.

Adapted from MuseTalk (MIT License).
Uses ``diffusers.UNet2DConditionModel`` (already installed in ComfyUI).
"""

import json
import math

import torch
import torch.nn as nn
from diffusers import UNet2DConditionModel


class PositionalEncoding(nn.Module):
    """Sinusoidal positional encoding for audio feature sequences."""

    def __init__(self, d_model: int = 384, max_len: int = 5000):
        super().__init__()
        pe = torch.zeros(max_len, d_model)
        position = torch.arange(0, max_len, dtype=torch.float).unsqueeze(1)
        div_term = torch.exp(
            torch.arange(0, d_model, 2).float()
            * (-math.log(10000.0) / d_model)
        )
        pe[:, 0::2] = torch.sin(position * div_term)
        pe[:, 1::2] = torch.cos(position * div_term)
        pe = pe.unsqueeze(0)
        self.register_buffer("pe", pe)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        _, seq_len, _ = x.size()
        pe = self.pe[:, :seq_len, :]
        return x + pe.to(x.device)


class UNet:
    """Wraps a ``UNet2DConditionModel`` for audio-conditioned face inpainting.

    The UNet takes concatenated [masked_face_latents, reference_latents]
    (8 channels) and produces inpainted face latents (4 channels),
    conditioned on Whisper audio features via cross-attention.
    """

    def __init__(
        self,
        unet_config: str,
        model_path: str,
        use_float16: bool = False,
        device: torch.device | None = None,
    ):
        with open(unet_config, "r") as f:
            config = json.load(f)

        self.model = UNet2DConditionModel(**config)

        self.device = device or torch.device(
            "cuda" if torch.cuda.is_available() else "cpu"
        )

        # Load weights — prefer comfy loader, fallback to torch
        try:
            import comfy.utils

            weights = comfy.utils.load_torch_file(model_path, safe_load=True)
        except (ImportError, Exception):
            from safetensors.torch import load_file

            if model_path.endswith(".safetensors"):
                weights = load_file(model_path, device="cpu")
            else:
                weights = torch.load(
                    model_path,
                    map_location="cpu",
                    weights_only=True,
                )

        self.model.load_state_dict(weights)

        if use_float16:
            self.model = self.model.half()

        self.model.to(self.device)
        self.model.eval()

    def to(self, device):
        """Move UNet model to a device and update internal device tracking."""
        device = torch.device(device) if isinstance(device, str) else device
        self.device = device
        self.model.to(device)
        return self
