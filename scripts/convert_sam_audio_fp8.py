#!/usr/bin/env python3
"""Convert SAM-Audio BF16 safetensors to FP8 scaled safetensors.

FP8 scaled format stores each tensor as:
  - `{key}` → float8_e4m3fn weights
  - `{key}._scale` → float32 per-tensor scale factor

At load time: actual_weight = fp8_weight.to(bf16) * scale

Usage:
    python scripts/convert_sam_audio_fp8.py
    python scripts/convert_sam_audio_fp8.py --variant base
    python scripts/convert_sam_audio_fp8.py --variant large
"""

import argparse
import gc
import os
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


def main():
    parser = argparse.ArgumentParser(
        description="Convert SAM-Audio BF16 to FP8 scaled safetensors"
    )
    parser.add_argument(
        "--variant", default="large", choices=["base", "large"],
        help="Model variant to convert (default: large)",
    )
    parser.add_argument(
        "--input-dir", default=None,
        help="Input directory (default: ComfyUI/models/sam_audio/)",
    )
    parser.add_argument(
        "--output-dir", default=None,
        help="Output directory (default: same as input)",
    )
    args = parser.parse_args()

    import torch

    # Resolve paths
    if args.input_dir:
        input_dir = args.input_dir
    else:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        comfyui_root = os.path.abspath(os.path.join(script_dir, "..", "..", ".."))
        input_dir = os.path.join(comfyui_root, "models", "sam_audio")

    output_dir = args.output_dir or input_dir

    input_file = f"sam-audio-{args.variant}-tv-bf16.safetensors"
    output_file = f"sam-audio-{args.variant}-tv-fp8-scaled.safetensors"

    input_path = os.path.join(input_dir, input_file)
    output_path = os.path.join(output_dir, output_file)

    if not os.path.isfile(input_path):
        print(f"ERROR: Input file not found: {input_path}")
        print(f"  Run convert_sam_audio.py first to create the BF16 model.")
        sys.exit(1)

    input_size = os.path.getsize(input_path) / 1024**3
    print(f"[FP8 Convert] Input:  {input_path} ({input_size:.2f} GiB)")
    print(f"[FP8 Convert] Output: {output_path}")

    # Load BF16 weights
    print("\n[1/3] Loading BF16 weights...")
    from safetensors.torch import load_file, save_file

    state_dict = load_file(input_path)
    print(f"  Loaded {len(state_dict)} tensors")

    # Quantize to FP8 scaled
    print("\n[2/3] Quantizing to FP8 scaled...")
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
            # Keep small or non-float tensors as-is
            fp8_dict[key] = tensor
            total_new += tensor.nbytes
            skipped += 1

    del state_dict
    gc.collect()

    print(f"  Converted: {converted} tensors")
    print(f"  Kept as-is: {skipped} tensors")
    print(f"  Original: {total_orig / 1024**3:.2f} GiB")
    print(f"  FP8 scaled: {total_new / 1024**3:.2f} GiB")
    print(f"  Reduction: {(1 - total_new / total_orig) * 100:.1f}%")

    # Save
    print(f"\n[3/3] Saving {output_path}...")
    os.makedirs(output_dir, exist_ok=True)
    save_file(fp8_dict, output_path)
    del fp8_dict
    gc.collect()

    file_size = os.path.getsize(output_path) / 1024**3
    print(f"  File size: {file_size:.2f} GiB")
    print(f"\n✅ Done! {input_file} ({input_size:.2f} GiB) → {output_file} ({file_size:.2f} GiB)")


if __name__ == "__main__":
    main()
