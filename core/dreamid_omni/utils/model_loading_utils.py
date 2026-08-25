import gc
import logging
import torch
import torch.nn as nn
import os
import json
from pathlib import Path
from safetensors.torch import load_file

log = logging.getLogger("ffmpega")


# ---------------------------------------------------------------------------
#  Native FP8 forward pass (adapted from Fish Speech _fp8_linear_forward)
# ---------------------------------------------------------------------------
# Keeps model weights in FP8 and uses torch._scaled_mm for hardware-
# accelerated FP8 matmul (CUDA compute >= 8.9, RTX 4000+).
# This halves VRAM usage vs upcasting FP8→BF16 during autocast.


def _supports_fp8_matmul() -> bool:
    """Check if the GPU supports native FP8 matmul (compute capability >= 8.9)."""
    if not torch.cuda.is_available():
        return False
    cap = torch.cuda.get_device_capability()
    return cap[0] > 8 or (cap[0] == 8 and cap[1] >= 9)


def _fp8_linear_forward(cls, base_dtype, input):
    """FP8 linear forward using torch._scaled_mm.

    Keeps weights in FP8, casts input to FP8, uses hardware-accelerated
    scaled matmul.  Output is in *base_dtype* (BF16).
    Handles inputs of any dimensionality by reshaping to 2D for matmul.
    """
    weight_dtype = cls.weight.dtype
    if weight_dtype not in [torch.float8_e4m3fn, torch.float8_e5m2]:
        return cls.original_forward(input)

    # torch._scaled_mm requires dimensions divisible by 16
    in_features = cls.weight.shape[1]
    out_features = cls.weight.shape[0]
    if in_features % 16 != 0 or out_features % 16 != 0:
        # Fall back to BF16 matmul for non-aligned layers (e.g. audio Head out_dim=20)
        # Must explicitly cast weight since original_forward can't handle FP8 weights
        w = cls.weight.to(base_dtype)
        b = cls.bias.to(base_dtype) if cls.bias is not None else None
        return torch.nn.functional.linear(input.to(base_dtype), w, b)

    input_shape = input.shape
    # Flatten all dims except last for matmul: (*batch, features) → (N, features)
    flat_input = input.reshape(-1, input_shape[-1])

    scale_weight = getattr(cls, "scale_weight", None)
    if scale_weight is None:
        scale_weight = torch.ones((), device=input.device, dtype=torch.float32)
    else:
        scale_weight = scale_weight.to(input.device)

    # Clamp + cast input to FP8
    flat_input = torch.clamp(flat_input, min=-448, max=448)
    inn = flat_input.to(torch.float8_e4m3fn).contiguous()

    bias = cls.bias.to(base_dtype) if cls.bias is not None else None

    # TensorWise scaling (no per-channel scales in this checkpoint)
    if scale_weight.dim() == 0 or scale_weight.numel() == 1:
        scale_input = torch.ones((), device=input.device, dtype=torch.float32)
        scale_b = scale_weight.reshape(())
    else:
        scale_input = torch.ones(
            (inn.shape[0], 1), device=input.device, dtype=torch.float32
        )
        scale_b = scale_weight.reshape(1, -1).contiguous()

    o = torch._scaled_mm(
        inn,
        cls.weight.t(),
        out_dtype=base_dtype,
        bias=bias,
        scale_a=scale_input,
        scale_b=scale_b,
    )
    # Restore original shape: (N, out_features) → (*batch, out_features)
    out_shape = input_shape[:-1] + (cls.weight.shape[0],)
    return o.reshape(out_shape)


def _convert_fp8_linear(module, base_dtype):
    """Patch all nn.Linear in *module* to use native FP8 matmul.

    Monkey-patches forward() on every Linear layer whose weight is FP8.
    """
    patched = 0
    for name, submodule in module.named_modules():
        if isinstance(submodule, nn.Linear):
            if submodule.weight.dtype in [torch.float8_e4m3fn, torch.float8_e5m2]:
                original_forward = submodule.forward
                setattr(submodule, "original_forward", original_forward)
                setattr(
                    submodule,
                    "forward",
                    lambda input, m=submodule: _fp8_linear_forward(
                        m, base_dtype, input
                    ),
                )
                patched += 1

    log.info("DreamID-Omni: patched %d Linear layers for native FP8 matmul", patched)
    return patched


def _dequantize_fp8_model(module):
    """Fallback: dequantize FP8 weights → BF16 in-place (for GPUs without FP8 matmul)."""
    count = 0
    for name, submodule in module.named_modules():
        if isinstance(submodule, nn.Linear):
            if submodule.weight.dtype in [torch.float8_e4m3fn, torch.float8_e5m2]:
                submodule.weight.data = submodule.weight.data.to(torch.bfloat16)
                if submodule.bias is not None and submodule.bias.dtype in [torch.float8_e4m3fn, torch.float8_e5m2]:
                    submodule.bias.data = submodule.bias.data.to(torch.bfloat16)
                count += 1
    log.info("DreamID-Omni: dequantized %d FP8 Linear layers → BF16 (no FP8 matmul support)", count)
    gc.collect()

from ..modules.fusion import FusionModel
from ..modules.t5 import T5EncoderModel
from ..modules.vae2_2 import Wan2_2_VAE
from ..modules.mmaudio.features_utils import FeaturesUtils

# Resolve config paths relative to the package root (core/dreamid_omni/)
_PACKAGE_DIR = Path(__file__).resolve().parent.parent
    
def init_wan_vae_2_2(ckpt_dir, rank=0):
    vae_config = {}
    vae_config['device'] = rank
    vae_pth = os.path.join(ckpt_dir, "Wan2.2-TI2V-5B/Wan2.2_VAE.pth")
    vae_config['vae_pth'] = vae_pth
    vae_model = Wan2_2_VAE(**vae_config)

    return vae_model

def init_mmaudio_vae(ckpt_dir, rank=0):
    vae_config = {}
    vae_config['mode'] = '16k'
    vae_config['need_vae_encoder'] = True

    tod_vae_ckpt = os.path.join(ckpt_dir, "MMAudio/ext_weights/v1-16.pth")
    bigvgan_vocoder_ckpt = os.path.join(ckpt_dir, "MMAudio/ext_weights/best_netG.pt")

    vae_config['tod_vae_ckpt'] = tod_vae_ckpt
    vae_config['bigvgan_vocoder_ckpt'] = bigvgan_vocoder_ckpt

    vae = FeaturesUtils(**vae_config).to(rank)

    return vae

def init_fusion_score_model_ovi(rank: int = 0, meta_init=False):
    video_config = str(_PACKAGE_DIR / "configs" / "model" / "dit" / "video.json")
    audio_config = str(_PACKAGE_DIR / "configs" / "model" / "dit" / "audio.json")
    assert os.path.exists(video_config), f"{video_config} does not exist"
    assert os.path.exists(audio_config), f"{audio_config} does not exist"

    with open(video_config) as f:
        video_config = json.load(f)

    with open(audio_config) as f:
        audio_config = json.load(f)

    if meta_init:
        with torch.device("meta"):
            fusion_model = FusionModel(video_config, audio_config)
    else:
        fusion_model = FusionModel(video_config, audio_config)
    
    params_all = sum(p.numel() for p in fusion_model.parameters())
    
    if rank == 0:
        print(
            f"Score model (Fusion) all parameters:{params_all}"
        )

    return fusion_model, video_config, audio_config

def init_text_model(ckpt_dir, rank, cpu_offload=False):
    wan_dir = os.path.join(ckpt_dir, "Wan2.2-TI2V-5B")
    text_encoder_path = os.path.join(wan_dir, "models_t5_umt5-xxl-enc-bf16.pth")
    text_tokenizer_path = os.path.join(wan_dir, "google/umt5-xxl")

    text_encoder = T5EncoderModel(
        text_len=512,
        dtype=torch.bfloat16,
        device=rank,
        checkpoint_path=text_encoder_path,
        tokenizer_path=text_tokenizer_path,
        cpu_offload=cpu_offload,
        shard_fn=None)


    return text_encoder


def load_fusion_checkpoint(model, checkpoint_path, from_meta=False):
    import glob as _glob
    import re as _re

    if not checkpoint_path or not os.path.exists(checkpoint_path):
        raise RuntimeError(f"{checkpoint_path=} does not exist")

    # Detect sharded checkpoint: pattern _bf16-00001-of-00003.safetensors
    shard_match = _re.search(r'-(\d{5})-of-(\d{5})\.safetensors$', checkpoint_path)
    if shard_match:
        # Glob for all shards from the same base
        base = _re.sub(r'-\d{5}-of-\d{5}\.safetensors$', '', checkpoint_path)
        shard_files = sorted(_glob.glob(f"{base}-*-of-*.safetensors"))
        total = int(shard_match.group(2))
        if len(shard_files) != total:
            raise RuntimeError(
                f"Expected {total} shards but found {len(shard_files)} for {base}"
            )
        print(f"Loading {total} sharded fusion checkpoint files...")
        df = {}
        for shard_path in shard_files:
            print(f"  Loading shard: {os.path.basename(shard_path)}")
            shard_data = load_file(shard_path, device="cpu")
            df.update(shard_data)
            del shard_data
            gc.collect()
        print(f"  Merged {len(df)} tensors from {total} shards")
    elif checkpoint_path.endswith(".safetensors"):
        df = load_file(checkpoint_path, device="cpu")
    elif checkpoint_path.endswith(".pt"):
        try:
            df = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
            df = df['module'] if 'module' in df else df
        except Exception as e:
            df = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
            df = df['app']['model']
    else:
        raise RuntimeError("We only support .safetensors and .pt checkpoints")

    missing, unexpected = model.load_state_dict(df, strict=True, assign=from_meta)

    # Detect FP8 weights and apply native FP8 matmul patching
    has_fp8 = any(
        p.dtype in [torch.float8_e4m3fn, torch.float8_e5m2]
        for p in model.parameters()
    )
    if has_fp8:
        # Cast non-Linear FP8 params (LayerNorm, embeddings, etc.) to BF16
        # These don't support FP8 computation and need real precision
        non_linear_cast = 0
        for name, submodule in model.named_modules():
            if isinstance(submodule, nn.Linear):
                continue  # Handled by FP8 patching or dequant below
            for pname, param in submodule.named_parameters(recurse=False):
                if param.dtype in [torch.float8_e4m3fn, torch.float8_e5m2]:
                    param.data = param.data.to(torch.bfloat16)
                    non_linear_cast += 1

        if _supports_fp8_matmul():
            log.info("DreamID-Omni: FP8 weights detected — enabling native FP8 matmul")
            _convert_fp8_linear(model, torch.bfloat16)
            log.info("DreamID-Omni: cast %d non-Linear FP8 params → BF16", non_linear_cast)
        else:
            log.info("DreamID-Omni: FP8 weights detected but GPU lacks FP8 support — dequantizing to BF16")
            _dequantize_fp8_model(model)

    del df
    gc.collect()
    print(f"Successfully loaded fusion checkpoint from {checkpoint_path}")