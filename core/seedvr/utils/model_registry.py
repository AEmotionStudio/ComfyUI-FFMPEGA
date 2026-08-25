"""
Model Registry for SeedVR2
Central registry for model definitions, repositories, and metadata
"""

import os
from typing import List, Optional
from dataclasses import dataclass
from .constants import get_all_model_files

# Model class imports using relative imports
from ..models.dit_3b.nadit import NaDiT as NaDiT3B
from ..models.dit_7b.nadit import NaDiT as NaDiT7B
from ..models.video_vae_v3.modules.attn_video_vae import VideoAutoencoderKLWrapper

# Model classes - simple registry with clear keys
MODEL_CLASSES = {
    "dit_3b.nadit": NaDiT3B,
    "dit_7b.nadit": NaDiT7B,
    "video_vae_v3.modules.attn_video_vae": VideoAutoencoderKLWrapper,
}

@dataclass
class ModelInfo:
    """Model metadata"""
    repo: str = "AEmotionStudio/SeedVR2-models"
    category: str = "dit" # 'model' or 'vae'
    precision: str = "fp16" # 'fp16', 'fp8_e4m3fn', 'Q4_K_M', etc.
    size: str = "3B" # '3B', '7B', etc.
    variant: Optional[str] = None # 'sharp', etc.
    sha256: Optional[str] = None # Cached hash
    local_only: bool = False # No mirror to download from; must already be on disk

# Model registry with metadata
MODEL_REGISTRY = {
    # 3B models
    "seedvr2_ema_3b-Q4_K_M.gguf": ModelInfo(size="3B", precision="Q4_K_M", sha256="7c357f46aedc49ca04bf41636df4795a04d1cb64bea0c568b72eef1da1127aaf"),
    "seedvr2_ema_3b_fp8_e4m3fn.safetensors": ModelInfo(size="3B", precision="fp8_e4m3fn", sha256="17c9abce2138136c7f9b29ac69b8791a8b34d2e785c7747b6fe3fd302439d342"),
    
    # 7B models
    "seedvr2_ema_7b-Q4_K_M.gguf": ModelInfo(size="7B", precision="Q4_K_M", sha256="94f72225bfa2b052a7e14618c9352d74a7f391d7c95249677fa2d526913c9fd7"),
    "seedvr2_ema_7b_fp8_e4m3fn.safetensors": ModelInfo(size="7B", precision="fp8_e4m3fn", sha256="1fdbf3877b7d1eb266038d3a165a977f17dbb4daa4a0f0d334d5461476963037"),
    # FP8 with the final transformer block (block 35) kept in FP16 — eliminates the
    # 7B-specific seam/grid artifacts of pure FP8 at the same VRAM footprint.
    # Mirrored to AEmotionStudio/SeedVR2-models (source: mekrod/...mixed_block35_fp16).
    "seedvr2_ema_7b_fp8_e4m3fn_mixed_block35_fp16.safetensors": ModelInfo(size="7B", precision="fp8_e4m3fn", variant="mixed_block35_fp16", sha256="3d68b5ec0b295ae28092e355c8cad870edd00b817b26587d0cb8f9dd2df19bb2"),

    # INT8 ConvRot models — ComfyUI's native int8_tensorwise layout with the
    # block-Hadamard rotation. Smaller and faster than FP8 on tensor cores.
    # Local-only: place them in ComfyUI/models/diffusion_models/ (where ComfyUI
    # downloads them) or ComfyUI/models/SEEDVR2/; both are searched.
    "seedvr2_3b_int8_convrot.safetensors": ModelInfo(size="3B", precision="int8_convrot", local_only=True),
    "seedvr2_7b_int8_convrot.safetensors": ModelInfo(size="7B", precision="int8_convrot", local_only=True),

    # VAE models
    "ema_vae_fp16.safetensors": ModelInfo(category="vae", precision="fp16", sha256="20678548f420d98d26f11442d3528f8b8c94e57ee046ef93dbb7633da8612ca1"),
}

# Configuration constants
DEFAULT_DIT = "seedvr2_ema_3b_fp8_e4m3fn.safetensors"
DEFAULT_VAE = "ema_vae_fp16.safetensors"

def get_default_models(category: str) -> List[str]:
    """Get list of default models"""
    return [name for name, info in MODEL_REGISTRY.items() if info.category == category]

def get_model_repo(model_name: str) -> str:
    """Get repository for a specific model"""
    return MODEL_REGISTRY.get(model_name, ModelInfo()).repo

def get_available_dit_models() -> List[str]:
    """Get all available DiT models including those discovered on disk"""
    model_list = get_default_models("dit")
    
    try:
        # Get all model files from all paths
        model_files = get_all_model_files()
        
        # Add files not in registry
        discovered_models = [
            filename for filename in model_files
            if filename not in MODEL_REGISTRY
        ]
        
        # Add discovered models to the list
        model_list.extend(sorted(discovered_models))
    except:
        pass
    
    return model_list

def get_available_vae_models() -> List[str]:
    """Get all available VAE models from the registry"""
    model_list = get_default_models("vae")
    return model_list