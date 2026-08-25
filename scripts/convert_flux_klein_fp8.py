#!/usr/bin/env python3
"""Convert Flux Klein BF16/FP16 safetensors to FP8 scaled safetensors.

FP8 scaled format stores each tensor as:
  - `{key}` → float8_e4m3fn weights
  - `{key}._scale` → float32 per-tensor scale factor

At load time: actual_weight = fp8_weight.to(bf16) * scale

Converts the transformer (~7.7 GB) and text encoder (~8 GB) to FP8 scaled,
producing a new `flux_klein_fp8/` directory that mirrors the original layout.
The VAE, scheduler, tokenizer, and config files are copied as-is.

Usage:
    python scripts/convert_flux_klein_fp8.py
    python scripts/convert_flux_klein_fp8.py --input-dir /path/to/flux_klein
    python scripts/convert_flux_klein_fp8.py --output-dir /path/to/flux_klein_fp8
"""

import argparse
import gc
import json
import os
import shutil
import sys


def quantize_to_fp8_scaled(tensor):
    """Quantize a BF16/FP16/FP32 tensor to FP8 e4m3fn with per-tensor scale.

    Returns (fp8_tensor, scale_tensor).
    """
    import torch

    if not tensor.is_floating_point():
        return tensor, None

    # Compute per-tensor scale: max_abs / max_fp8_representable
    # float8_e4m3fn max value is 448.0
    FP8_MAX = 448.0
    abs_max = tensor.abs().max().float().clamp(min=1e-12)
    scale = abs_max / FP8_MAX

    # Scale down, clamp, and cast to FP8
    scaled = (tensor.float() / scale).clamp(-FP8_MAX, FP8_MAX)
    fp8_tensor = scaled.to(torch.float8_e4m3fn)

    return fp8_tensor, scale.to(torch.float32)


def convert_safetensors_file(input_path: str, output_path: str, label: str) -> dict:
    """Convert a single safetensors file to FP8 scaled format.

    Returns dict with stats: {converted, skipped, orig_bytes, new_bytes}.
    """
    from safetensors.torch import load_file, save_file

    print(f"\n  Loading {label}: {input_path}")
    state_dict = load_file(input_path)
    print(f"    {len(state_dict)} tensors loaded")

    fp8_dict = {}
    converted = 0
    skipped = 0
    total_orig = 0
    total_new = 0

    # Patterns that should NOT be quantized to FP8:
    # - Normalization weights (RMSNorm, LayerNorm) — used in elementwise mul
    # - Embedding weights — used in indexing ops
    # - Modulation/projection weights — small 1D tensors
    _SKIP_PATTERNS = (
        "layernorm", "norm.", "norm_q.", "norm_k.", "norm_added_q.",
        "norm_added_k.", "norm_out.", "embed_tokens", "modulation",
        "x_embedder", "context_embedder", "proj_out",
        "time_guidance_embed",
    )

    for key, tensor in state_dict.items():
        total_orig += tensor.nbytes

        # Skip small tensors and non-float tensors
        if not tensor.is_floating_point() or tensor.numel() <= 1:
            fp8_dict[key] = tensor
            total_new += tensor.nbytes
            skipped += 1
            continue

        # Skip norm/embedding/modulation weights — CUDA doesn't support
        # elementwise ops on FP8 and these are small anyway
        key_lower = key.lower()
        if any(pat in key_lower for pat in _SKIP_PATTERNS):
            fp8_dict[key] = tensor
            total_new += tensor.nbytes
            skipped += 1
            continue

        # Quantize large weight matrices to FP8
        fp8_tensor, scale = quantize_to_fp8_scaled(tensor)
        fp8_dict[key] = fp8_tensor
        if scale is not None:
            fp8_dict[f"{key}._scale"] = scale
        total_new += fp8_tensor.nbytes + (scale.nbytes if scale is not None else 0)
        converted += 1

    del state_dict
    gc.collect()

    print(f"    Converted: {converted}, kept as-is: {skipped}")
    print(f"    {total_orig / 1024**3:.2f} GiB → {total_new / 1024**3:.2f} GiB "
          f"({(1 - total_new / total_orig) * 100:.1f}% reduction)")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    save_file(fp8_dict, output_path)
    del fp8_dict
    gc.collect()

    file_size = os.path.getsize(output_path) / 1024**3
    print(f"    Saved: {output_path} ({file_size:.2f} GiB)")

    return {
        "converted": converted,
        "skipped": skipped,
        "orig_bytes": total_orig,
        "new_bytes": total_new,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Convert Flux Klein BF16/FP16 to FP8 scaled safetensors"
    )
    parser.add_argument(
        "--input-dir", default=None,
        help="Input directory (default: ComfyUI/models/flux_klein/)",
    )
    parser.add_argument(
        "--output-dir", default=None,
        help="Output directory (default: ComfyUI/models/flux_klein_fp8/)",
    )
    args = parser.parse_args()

    import torch  # noqa: F401 — validates torch is available

    # Resolve paths
    if args.input_dir:
        input_dir = args.input_dir
    else:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        comfyui_root = os.path.abspath(os.path.join(script_dir, "..", "..", ".."))
        input_dir = os.path.join(comfyui_root, "models", "flux_klein")

    if args.output_dir:
        output_dir = args.output_dir
    else:
        output_dir = os.path.join(os.path.dirname(input_dir), "flux_klein_fp8")

    # Validate input
    model_index = os.path.join(input_dir, "model_index.json")
    if not os.path.isfile(model_index):
        print(f"ERROR: model_index.json not found at {model_index}")
        print(f"  Expected Flux Klein model at: {input_dir}")
        sys.exit(1)

    transformer_file = os.path.join(input_dir, "transformer", "diffusion_pytorch_model.safetensors")
    if not os.path.isfile(transformer_file):
        print(f"ERROR: Transformer weights not found: {transformer_file}")
        sys.exit(1)

    print(f"[FP8 Convert] Flux Klein 4B")
    print(f"  Input:  {input_dir}")
    print(f"  Output: {output_dir}")

    os.makedirs(output_dir, exist_ok=True)

    # ------------------------------------------------------------------
    # Step 1: Copy/symlink non-quantized components
    # ------------------------------------------------------------------
    print("\n[1/4] Setting up output directory structure...")

    # Copy model_index.json
    shutil.copy2(model_index, os.path.join(output_dir, "model_index.json"))
    print("  Copied model_index.json")

    # Copy directories that don't need quantization (makes FP8 self-contained)
    for subdir in ("scheduler", "tokenizer", "vae"):
        src = os.path.join(input_dir, subdir)
        dst = os.path.join(output_dir, subdir)
        if os.path.isdir(src):
            if os.path.exists(dst) or os.path.islink(dst):
                if os.path.islink(dst):
                    os.unlink(dst)
                else:
                    shutil.rmtree(dst)
            shutil.copytree(src, dst)
            print(f"  Copied {subdir}/")

    # Copy transformer config
    transformer_out_dir = os.path.join(output_dir, "transformer")
    os.makedirs(transformer_out_dir, exist_ok=True)
    transformer_config = os.path.join(input_dir, "transformer", "config.json")
    if os.path.isfile(transformer_config):
        shutil.copy2(transformer_config, os.path.join(transformer_out_dir, "config.json"))
        print("  Copied transformer/config.json")

    # Copy text_encoder configs
    text_encoder_out_dir = os.path.join(output_dir, "text_encoder")
    os.makedirs(text_encoder_out_dir, exist_ok=True)
    for cfg_file in ("config.json", "generation_config.json"):
        src = os.path.join(input_dir, "text_encoder", cfg_file)
        if os.path.isfile(src):
            shutil.copy2(src, os.path.join(text_encoder_out_dir, cfg_file))
            print(f"  Copied text_encoder/{cfg_file}")

    # ------------------------------------------------------------------
    # Step 2: Convert transformer to FP8
    # ------------------------------------------------------------------
    print("\n[2/4] Converting transformer to FP8 scaled...")
    transformer_output = os.path.join(transformer_out_dir, "diffusion_pytorch_model.safetensors")
    t_stats = convert_safetensors_file(transformer_file, transformer_output, "transformer")

    # ------------------------------------------------------------------
    # Step 3: Convert text encoder to FP8 (merge shards into one file)
    # ------------------------------------------------------------------
    print("\n[3/4] Converting text encoder to FP8 scaled...")

    from safetensors.torch import load_file, save_file

    # Find all text encoder shards
    te_dir = os.path.join(input_dir, "text_encoder")
    te_index_file = os.path.join(te_dir, "model.safetensors.index.json")

    # Load all shards into one state dict
    te_shards = sorted([
        f for f in os.listdir(te_dir)
        if f.endswith(".safetensors") and "index" not in f
    ])

    if not te_shards:
        print("  WARNING: No text encoder safetensors found, skipping")
        te_stats = {"converted": 0, "skipped": 0, "orig_bytes": 0, "new_bytes": 0}
    else:
        print(f"  Found {len(te_shards)} shard(s): {', '.join(te_shards)}")

        # Load all shards
        full_state_dict = {}
        for shard_name in te_shards:
            shard_path = os.path.join(te_dir, shard_name)
            print(f"  Loading shard: {shard_name}")
            shard_dict = load_file(shard_path)
            full_state_dict.update(shard_dict)
            del shard_dict
            gc.collect()

        print(f"  Total: {len(full_state_dict)} tensors")

        # Quantize all tensors
        fp8_dict = {}
        converted = 0
        skipped = 0
        total_orig = 0
        total_new = 0

        for key, tensor in full_state_dict.items():
            total_orig += tensor.nbytes

            if tensor.is_floating_point() and tensor.numel() > 1:
                fp8_tensor, scale = quantize_to_fp8_scaled(tensor)
                fp8_dict[key] = fp8_tensor
                if scale is not None:
                    fp8_dict[f"{key}._scale"] = scale
                total_new += fp8_tensor.nbytes + (scale.nbytes if scale is not None else 0)
                converted += 1
            else:
                fp8_dict[key] = tensor
                total_new += tensor.nbytes
                skipped += 1

        del full_state_dict
        gc.collect()

        print(f"  Converted: {converted}, kept as-is: {skipped}")
        print(f"  {total_orig / 1024**3:.2f} GiB → {total_new / 1024**3:.2f} GiB "
              f"({(1 - total_new / total_orig) * 100:.1f}% reduction)")

        # Save as single shard
        te_output = os.path.join(text_encoder_out_dir, "model.safetensors")
        save_file(fp8_dict, te_output)
        file_size = os.path.getsize(te_output) / 1024**3
        print(f"  Saved: {te_output} ({file_size:.2f} GiB)")

        # Create new index file pointing to single shard
        weight_map = {key: "model.safetensors" for key in fp8_dict.keys()}
        index_data = {
            "metadata": {"total_size": sum(t.nbytes for t in fp8_dict.values())},
            "weight_map": weight_map,
        }
        index_output = os.path.join(text_encoder_out_dir, "model.safetensors.index.json")
        with open(index_output, "w") as f:
            json.dump(index_data, f, indent=2)
        print(f"  Saved: {index_output}")

        te_stats = {
            "converted": converted,
            "skipped": skipped,
            "orig_bytes": total_orig,
            "new_bytes": total_new,
        }

        del fp8_dict
        gc.collect()

    # ------------------------------------------------------------------
    # Step 4: Summary
    # ------------------------------------------------------------------
    print("\n[4/4] Summary")
    print("=" * 60)

    total_orig = t_stats["orig_bytes"] + te_stats["orig_bytes"]
    total_new = t_stats["new_bytes"] + te_stats["new_bytes"]

    print(f"  Transformer: {t_stats['converted']} tensors converted, "
          f"{t_stats['orig_bytes'] / 1024**3:.2f} → "
          f"{t_stats['new_bytes'] / 1024**3:.2f} GiB")
    print(f"  Text Encoder: {te_stats['converted']} tensors converted, "
          f"{te_stats['orig_bytes'] / 1024**3:.2f} → "
          f"{te_stats['new_bytes'] / 1024**3:.2f} GiB")
    print(f"  Total: {total_orig / 1024**3:.2f} → {total_new / 1024**3:.2f} GiB "
          f"({(1 - total_new / total_orig) * 100:.1f}% reduction)")
    print(f"\n✅ Done! FP8 model saved to: {output_dir}")


if __name__ == "__main__":
    main()
