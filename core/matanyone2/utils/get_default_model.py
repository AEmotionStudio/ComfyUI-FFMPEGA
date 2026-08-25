"""
A helper function to get a default model for quick testing.

Replaces the upstream hydra-based loader with direct OmegaConf YAML loading
to avoid the hydra-core dependency.
"""
from pathlib import Path

from omegaconf import OmegaConf

import torch
from ..model.matanyone2 import MatAnyone2


def get_matanyone2_model(ckpt_path, device=None) -> MatAnyone2:
    # Load config directly from YAML files (no hydra)
    config_dir = Path(__file__).resolve().parent.parent / "config"
    base_cfg = OmegaConf.load(config_dir / "eval_matanyone_config.yaml")
    model_cfg = OmegaConf.load(config_dir / "model" / "base.yaml")

    # Merge: model config goes under 'model' key
    cfg = OmegaConf.merge(base_cfg, {"model": model_cfg})

    # Override weights path
    cfg.weights = str(ckpt_path)

    # Load the network weights
    if device is not None:
        matanyone2 = MatAnyone2(cfg, single_object=True).to(device).eval()
    else:  # if device is not specified, `.cuda()` by default
        matanyone2 = MatAnyone2(cfg, single_object=True).cuda().eval()

    # Support both .safetensors and .pth formats
    ckpt_str = str(ckpt_path)
    if ckpt_str.endswith(".safetensors"):
        from safetensors.torch import load_file
        map_loc = str(device) if device is not None else "cuda"
        model_weights = load_file(ckpt_str, device=map_loc)
    else:
        if device is not None:
            model_weights = torch.load(ckpt_str, map_location=device, weights_only=True)
        else:
            model_weights = torch.load(ckpt_str, weights_only=True)

    matanyone2.load_weights(model_weights)

    return matanyone2

