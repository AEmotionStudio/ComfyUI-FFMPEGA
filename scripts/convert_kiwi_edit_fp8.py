#!/usr/bin/env python3
"""Convert Kiwi-Edit BF16 diffusers weights to FP8 scaled safetensors.

FP8 scaled format stores each tensor as:
  - `{key}` → float8_e4m3fn weights
  - `{key}._scale` → float32 per-tensor scale factor

At load time: actual_weight = fp8_weight.to(bf16) * scale

Converts the transformer (~5B Wan 2.2 DiT) and mllm_encoder (~3B Qwen2.5-VL)
to FP8 scaled, producing a new `kiwi_edit_<variant>_fp8/` directory that
mirrors the original layout.  The VAE, scheduler, processor, and
source_embedder are symlinked/copied as-is.

Usage:
    python scripts/convert_kiwi_edit_fp8.py
    python scripts/convert_kiwi_edit_fp8.py --variant instruct
    python scripts/convert_kiwi_edit_fp8.py --variant reference --input-dir /path/to/model
    python scripts/convert_kiwi_edit_fp8.py --variant instruct_reference
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

    for key, tensor in state_dict.items():
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


def convert_sharded_safetensors(input_dir: str, output_dir: str, label: str) -> dict:
    """Convert a sharded safetensors directory to FP8 (merged single shard).

    Handles both single-file and multi-shard layouts.
    Returns stats dict.
    """
    from safetensors.torch import load_file, save_file

    # Find all safetensors files (exclude index files)
    shards = sorted([
        f for f in os.listdir(input_dir)
        if f.endswith(".safetensors") and "index" not in f
    ])

    if not shards:
        print(f"  WARNING: No safetensors found in {input_dir}, skipping")
        return {"converted": 0, "skipped": 0, "orig_bytes": 0, "new_bytes": 0}

    if len(shards) == 1:
        # Single file — use simpler conversion
        return convert_safetensors_file(
            os.path.join(input_dir, shards[0]),
            os.path.join(output_dir, "model.safetensors"),
            label,
        )

    # Multi-shard: load all, merge, quantize, save as single shard
    print(f"\n  Loading {label}: {len(shards)} shard(s)")

    full_state_dict = {}
    for shard_name in shards:
        shard_path = os.path.join(input_dir, shard_name)
        print(f"    Loading shard: {shard_name}")
        shard_dict = load_file(shard_path)
        full_state_dict.update(shard_dict)
        del shard_dict
        gc.collect()

    print(f"    Total: {len(full_state_dict)} tensors")

    # Quantize
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

    print(f"    Converted: {converted}, kept as-is: {skipped}")
    print(f"    {total_orig / 1024**3:.2f} GiB → {total_new / 1024**3:.2f} GiB "
          f"({(1 - total_new / total_orig) * 100:.1f}% reduction)")

    # Save as single shard
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "model.safetensors")
    save_file(fp8_dict, output_path)
    file_size = os.path.getsize(output_path) / 1024**3
    print(f"    Saved: {output_path} ({file_size:.2f} GiB)")

    # Create index file pointing to single shard
    weight_map = {key: "model.safetensors" for key in fp8_dict.keys()}
    index_data = {
        "metadata": {"total_size": sum(t.nbytes for t in fp8_dict.values())},
        "weight_map": weight_map,
    }
    index_output = os.path.join(output_dir, "model.safetensors.index.json")
    with open(index_output, "w") as f:
        json.dump(index_data, f, indent=2)
    print(f"    Saved: {index_output}")

    del fp8_dict
    gc.collect()

    return {
        "converted": converted,
        "skipped": skipped,
        "orig_bytes": total_orig,
        "new_bytes": total_new,
    }


# Variant name → directory name mapping
VARIANT_DIR_NAMES = {
    "instruct": "kiwi_edit_instruct",
    "reference": "kiwi_edit_reference",
    "instruct_reference": "kiwi_edit_instruct_reference",
}

# Subdirectories that need FP8 quantization
QUANTIZE_SUBDIRS = ["transformer", "mllm_encoder"]

# Subdirectories to symlink/copy as-is (no quantization)
COPY_SUBDIRS = ["vae", "scheduler", "processor", "source_embedder"]


def main():
    parser = argparse.ArgumentParser(
        description="Convert Kiwi-Edit BF16 to FP8 scaled safetensors"
    )
    parser.add_argument(
        "--variant", default="instruct",
        choices=list(VARIANT_DIR_NAMES.keys()),
        help="Model variant to convert (default: instruct)",
    )
    parser.add_argument(
        "--input-dir", default=None,
        help="Input directory (default: ComfyUI/models/<variant>/)",
    )
    parser.add_argument(
        "--output-dir", default=None,
        help="Output directory (default: ComfyUI/models/<variant>_fp8/)",
    )
    args = parser.parse_args()

    import torch  # noqa: F401 — validates torch is available

    dir_name = VARIANT_DIR_NAMES[args.variant]

    # Resolve paths
    if args.input_dir:
        input_dir = args.input_dir
    else:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        comfyui_root = os.path.abspath(os.path.join(script_dir, "..", "..", ".."))
        input_dir = os.path.join(comfyui_root, "models", dir_name)

    if args.output_dir:
        output_dir = args.output_dir
    else:
        output_dir = os.path.join(os.path.dirname(input_dir), f"{dir_name}_fp8")

    # Validate input
    model_index = os.path.join(input_dir, "model_index.json")
    if not os.path.isfile(model_index):
        print(f"ERROR: model_index.json not found at {model_index}")
        print(f"  Expected Kiwi-Edit model at: {input_dir}")
        print(f"  Download first with: huggingface-cli download linyq/kiwi-edit-5b-{args.variant.replace('_', '-')}-only-diffusers --local-dir {input_dir}")
        sys.exit(1)

    print(f"[FP8 Convert] Kiwi-Edit 5B ({args.variant})")
    print(f"  Input:  {input_dir}")
    print(f"  Output: {output_dir}")

    os.makedirs(output_dir, exist_ok=True)

    # ------------------------------------------------------------------
    # Step 1: Copy model_index.json and symlink non-quantized components
    # ------------------------------------------------------------------
    total_steps = 2 + len(QUANTIZE_SUBDIRS)
    step = 1

    print(f"\n[{step}/{total_steps}] Setting up output directory structure...")

    # Copy model_index.json
    shutil.copy2(model_index, os.path.join(output_dir, "model_index.json"))
    print("  Copied model_index.json")

    # Copy top-level Python files (pipeline, VAE, embedder definitions)
    for py_file in ["pipeline_kiwi_edit.py", "wan_video_vae.py",
                     "conditional_embedder.py", "mllm_encoder.py", "__init__.py"]:
        src = os.path.join(input_dir, py_file)
        if os.path.isfile(src):
            shutil.copy2(src, os.path.join(output_dir, py_file))
            print(f"  Copied {py_file}")

    # Symlink directories that don't need quantization
    for subdir in COPY_SUBDIRS:
        src = os.path.join(input_dir, subdir)
        dst = os.path.join(output_dir, subdir)
        if os.path.isdir(src):
            if os.path.exists(dst):
                if os.path.islink(dst):
                    os.unlink(dst)
                else:
                    shutil.rmtree(dst)
            os.symlink(os.path.abspath(src), dst)
            print(f"  Symlinked {subdir}/")

    all_stats = {}

    # ------------------------------------------------------------------
    # Steps 2+: Convert each quantizable subdirectory to FP8
    # ------------------------------------------------------------------
    for subdir in QUANTIZE_SUBDIRS:
        step += 1
        src_dir = os.path.join(input_dir, subdir)
        dst_dir = os.path.join(output_dir, subdir)

        if not os.path.isdir(src_dir):
            print(f"\n[{step}/{total_steps}] Skipping {subdir}/ (not found)")
            all_stats[subdir] = {"converted": 0, "skipped": 0, "orig_bytes": 0, "new_bytes": 0}
            continue

        print(f"\n[{step}/{total_steps}] Converting {subdir} to FP8 scaled...")

        # Create output subdir
        os.makedirs(dst_dir, exist_ok=True)

        # Copy config files
        for cfg_file in os.listdir(src_dir):
            if cfg_file.endswith(".json") and "index" not in cfg_file:
                shutil.copy2(
                    os.path.join(src_dir, cfg_file),
                    os.path.join(dst_dir, cfg_file),
                )
                print(f"  Copied {subdir}/{cfg_file}")

        # Check for single safetensors or sharded
        safetensors_files = [
            f for f in os.listdir(src_dir)
            if f.endswith(".safetensors") and "index" not in f
        ]

        if len(safetensors_files) == 1:
            stats = convert_safetensors_file(
                os.path.join(src_dir, safetensors_files[0]),
                os.path.join(dst_dir, safetensors_files[0]),
                subdir,
            )
        else:
            stats = convert_sharded_safetensors(src_dir, dst_dir, subdir)

        all_stats[subdir] = stats

    # ------------------------------------------------------------------
    # Final summary
    # ------------------------------------------------------------------
    step += 1
    print(f"\n[{step}/{total_steps}] Summary")
    print("=" * 60)

    total_orig = sum(s["orig_bytes"] for s in all_stats.values())
    total_new = sum(s["new_bytes"] for s in all_stats.values())

    for name, stats in all_stats.items():
        if stats["orig_bytes"] > 0:
            print(f"  {name}: {stats['converted']} tensors converted, "
                  f"{stats['orig_bytes'] / 1024**3:.2f} → "
                  f"{stats['new_bytes'] / 1024**3:.2f} GiB")

    if total_orig > 0:
        print(f"  Total: {total_orig / 1024**3:.2f} → {total_new / 1024**3:.2f} GiB "
              f"({(1 - total_new / total_orig) * 100:.1f}% reduction)")

    print(f"\n✅ Done! FP8 model saved to: {output_dir}")


if __name__ == "__main__":
    main()
