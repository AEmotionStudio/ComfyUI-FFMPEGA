#!/usr/bin/env python3
"""Download LivePortrait .pth weights from upstream and convert to .safetensors.

Usage:
    python scripts/convert_liveportrait_weights.py [--output-dir DIR]

Downloads models from KlingTeam/LivePortrait on HuggingFace, converts each
.pth checkpoint to .safetensors, and saves to the output directory.

The converted files are ready to upload to AEmotionStudio/liveportrait-models.
"""

import argparse
import os
import sys
from pathlib import Path

# Upstream model locations on KlingTeam/LivePortrait
UPSTREAM_REPO = "KlingTeam/LivePortrait"

MODEL_MAP = {
    "appearance_feature_extractor": "liveportrait/base_models/appearance_feature_extractor.pth",
    "motion_extractor": "liveportrait/base_models/motion_extractor.pth",
    "spade_generator": "liveportrait/base_models/spade_generator.pth",
    "warping_module": "liveportrait/base_models/warping_module.pth",
    "stitching_retargeting_module": "liveportrait/retargeting_models/stitching_retargeting_module.pth",
}


def download_model(model_key: str, hf_path: str, cache_dir: str) -> str:
    """Download a single model file from HuggingFace."""
    from huggingface_hub import hf_hub_download

    print(f"  Downloading {model_key} from {UPSTREAM_REPO}/{hf_path}...")
    local = hf_hub_download(
        repo_id=UPSTREAM_REPO,
        filename=hf_path,
        local_dir=cache_dir,
        local_dir_use_symlinks=False,
    )
    print(f"  → {local}")
    return local


def convert_pth_to_safetensors(pth_path: str, output_path: str, model_key: str) -> None:
    """Convert a .pth checkpoint to .safetensors format."""
    import torch
    from safetensors.torch import save_file
    from collections import OrderedDict

    print(f"  Loading {pth_path}...")
    checkpoint = torch.load(pth_path, map_location="cpu", weights_only=False)

    # Handle nested checkpoint formats
    if isinstance(checkpoint, dict):
        if "model" in checkpoint:
            state_dict = checkpoint["model"]
        elif "state_dict" in checkpoint:
            state_dict = checkpoint["state_dict"]
        else:
            state_dict = checkpoint
    else:
        state_dict = checkpoint

    # Remove 'module.' prefix (DDP artifacts)
    cleaned = OrderedDict()
    for k, v in state_dict.items():
        clean_key = k.replace("module.", "")
        if isinstance(v, torch.Tensor):
            cleaned[clean_key] = v
        else:
            print(f"    Skipping non-tensor key: {clean_key} ({type(v).__name__})")

    print(f"  Converting {len(cleaned)} tensors...")

    # Special handling for stitching_retargeting_module:
    # Upstream checkpoint has sub-dicts: retarget_shoulder (=stitching),
    # retarget_mouth (=lip), retarget_eye (=eye)
    # Each sub-dict has keys like 'module.mlp.0.weight'
    # We flatten to: stitching.mlp.0.weight, retarget_lip.mlp.0.weight, etc.
    if model_key == "stitching_retargeting_module":
        # Map upstream sub-dict names → our prefix names
        MAPPING = {
            "retarget_shoulder": "stitching",
            "retarget_mouth": "retarget_lip",
            "retarget_eye": "retarget_eye",
        }
        flat = OrderedDict()
        for upstream_name, our_prefix in MAPPING.items():
            sub_dict = state_dict.get(upstream_name)
            if sub_dict is None:
                print(f"    WARNING: Missing sub-dict '{upstream_name}'")
                continue
            if not isinstance(sub_dict, dict):
                print(f"    WARNING: '{upstream_name}' is {type(sub_dict).__name__}, not dict")
                continue
            for sk, sv in sub_dict.items():
                if isinstance(sv, torch.Tensor):
                    # Strip 'module.' prefix from DDP
                    clean_key = sk.replace("module.", "")
                    flat[f"{our_prefix}.{clean_key}"] = sv
        if flat:
            cleaned = flat
            print(f"  Flattened {len(flat)} tensors from {len(MAPPING)} sub-networks")

    # Validate all values are tensors
    for k, v in list(cleaned.items()):
        if not isinstance(v, torch.Tensor):
            print(f"    Removing non-tensor: {k}")
            del cleaned[k]

    # Convert to float32 for maximum compatibility (safetensors doesn't support all dtypes)
    for k in cleaned:
        if cleaned[k].dtype == torch.float64:
            cleaned[k] = cleaned[k].float()

    save_file(cleaned, output_path)
    size_mb = os.path.getsize(output_path) / (1024 * 1024)
    print(f"  → Saved {output_path} ({size_mb:.1f} MB, {len(cleaned)} tensors)")


def main():
    parser = argparse.ArgumentParser(
        description="Convert LivePortrait .pth weights to .safetensors"
    )
    parser.add_argument(
        "--output-dir", "-o",
        default="./liveportrait_safetensors",
        help="Output directory for converted files (default: ./liveportrait_safetensors)",
    )
    parser.add_argument(
        "--cache-dir", "-c",
        default="/tmp/liveportrait_pth_cache",
        help="Cache directory for downloaded .pth files (default: /tmp/liveportrait_pth_cache)",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    cache_dir = args.cache_dir

    print(f"Output directory: {output_dir}")
    print(f"Cache directory: {cache_dir}")
    print()

    total_size = 0

    for model_key, hf_path in MODEL_MAP.items():
        print(f"[{model_key}]")

        # Download
        pth_path = download_model(model_key, hf_path, cache_dir)

        # Convert
        out_name = f"{model_key}.safetensors"
        out_path = str(output_dir / out_name)
        convert_pth_to_safetensors(pth_path, out_path, model_key)

        total_size += os.path.getsize(out_path)
        print()

    total_mb = total_size / (1024 * 1024)
    print(f"Done! Total: {total_mb:.1f} MB in {output_dir}")
    print()
    print("To upload to HuggingFace mirror:")
    print(f"  huggingface-cli upload AEmotionStudio/liveportrait-models {output_dir} .")


if __name__ == "__main__":
    main()
