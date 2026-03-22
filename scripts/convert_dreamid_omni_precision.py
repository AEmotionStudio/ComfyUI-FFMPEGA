#!/usr/bin/env python3
"""Convert DreamID-Omni fusion checkpoint to BF16 and/or FP8.

Streaming/chunked converter — processes one tensor at a time so the full
46.6 GB FP32 state dict never resides in RAM.  Safe for systems with
32 GB RAM.

Usage:
    # Convert from local FP32 checkpoint
    python scripts/convert_dreamid_omni_precision.py \\
        --input /path/to/dreamid_omni.safetensors \\
        --output-dir /path/to/output \\
        --format bf16 fp8

    # Download from HuggingFace and convert
    python scripts/convert_dreamid_omni_precision.py \\
        --download \\
        --output-dir ~/ComfyUI/models/dreamid_omni/DreamID_Omni \\
        --format bf16 fp8

Output files:
    dreamid_omni_bf16.safetensors   (~23 GB)
    dreamid_omni_fp8.safetensors    (~12 GB)
"""

from __future__ import annotations

import argparse
import gc
import os
import sys
import time
from pathlib import Path

import torch


def _stream_convert_safetensors(
    input_path: str,
    output_path: str,
    target_dtype: torch.dtype,
    *,
    chunk_size: int = 50,
    skip_non_float: bool = True,
    max_shard_bytes: int = 6 * 1024**3,  # 6 GB per shard
) -> dict[str, str]:
    """Convert a safetensors file to a target dtype, streaming key-by-key.

    When the converted output exceeds ``max_shard_bytes``, saves as
    sharded files (e.g. ``dreamid_omni_bf16-00001-of-00003.safetensors``).
    This keeps peak RAM well under 32 GB even for BF16 (~23 GB total).

    For smaller outputs (e.g. FP8 ~12 GB), saves as a single file.

    Args:
        input_path: Path to source .safetensors file.
        output_path: Path for the converted .safetensors output.
        target_dtype: Target dtype (e.g. torch.bfloat16, torch.float8_e4m3fn).
        chunk_size: Number of tensors to read at a time from source.
        skip_non_float: If True, keep non-float tensors (int, bool) as-is.
        max_shard_bytes: Max bytes per output shard (default 6 GB).

    Returns:
        Dict with conversion stats.
    """
    from safetensors import safe_open
    from safetensors.torch import save_file

    print(f"\n{'='*60}")
    print(f"Converting: {input_path}")
    print(f"Target:     {output_path}")
    print(f"Dtype:      {target_dtype}")
    print(f"{'='*60}\n")

    t0 = time.time()

    # Phase 1: Scan keys and estimate output size
    with safe_open(input_path, framework="pt", device="cpu") as f:
        all_keys = list(f.keys())
        metadata = f.metadata()

    total_keys = len(all_keys)
    print(f"Total tensors: {total_keys}")

    # Estimate total output size to decide single vs sharded
    with safe_open(input_path, framework="pt", device="cpu") as f:
        sample_key = all_keys[0]
        sample_tensor = f.get_tensor(sample_key)
        in_elem_size = sample_tensor.element_size()
        out_elem_size = torch.tensor(0, dtype=target_dtype).element_size()
        del sample_tensor

    # Rough estimate based on element size ratio
    input_size = os.path.getsize(input_path)
    est_output_size = int(input_size * out_elem_size / in_elem_size)
    use_sharding = est_output_size > max_shard_bytes * 1.2  # 20% headroom

    if use_sharding:
        print(f"Estimated output: {est_output_size / (1024**3):.1f} GB → using sharded save "
              f"(~{max_shard_bytes / (1024**3):.0f} GB per shard)")
        return _sharded_convert(
            input_path, output_path, target_dtype, all_keys, metadata,
            chunk_size=chunk_size, skip_non_float=skip_non_float,
            max_shard_bytes=max_shard_bytes, t0=t0,
        )
    else:
        print(f"Estimated output: {est_output_size / (1024**3):.1f} GB → single file save")
        return _single_file_convert(
            input_path, output_path, target_dtype, all_keys, metadata,
            chunk_size=chunk_size, skip_non_float=skip_non_float, t0=t0,
        )


def _single_file_convert(
    input_path, output_path, target_dtype, all_keys, metadata,
    *, chunk_size, skip_non_float, t0,
) -> dict[str, str]:
    """Convert and save as a single safetensors file (for smaller outputs)."""
    from safetensors import safe_open
    from safetensors.torch import save_file

    total_keys = len(all_keys)
    converted_state = {}
    converted_count = 0
    skipped_count = 0
    total_bytes_in = 0
    total_bytes_out = 0

    for chunk_start in range(0, total_keys, chunk_size):
        chunk_keys = all_keys[chunk_start:chunk_start + chunk_size]
        with safe_open(input_path, framework="pt", device="cpu") as f:
            for key in chunk_keys:
                tensor = f.get_tensor(key)
                total_bytes_in += tensor.nelement() * tensor.element_size()
                if skip_non_float and not tensor.is_floating_point():
                    converted_state[key] = tensor
                    total_bytes_out += tensor.nelement() * tensor.element_size()
                    skipped_count += 1
                else:
                    converted = tensor.to(target_dtype)
                    converted_state[key] = converted
                    total_bytes_out += converted.nelement() * converted.element_size()
                    converted_count += 1
                    del tensor
        progress = min(chunk_start + chunk_size, total_keys)
        pct = progress / total_keys * 100
        ram_gb = sum(t.nelement() * t.element_size() for t in converted_state.values()) / (1024**3)
        print(f"  [{pct:5.1f}%] {progress}/{total_keys} tensors | "
              f"RAM: {ram_gb:.1f} GB | converted: {converted_count}, kept: {skipped_count}")
        gc.collect()

    print(f"\nSaving {len(converted_state)} tensors to {output_path}...")
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    save_metadata = dict(metadata) if metadata else {}
    save_metadata["converted_from"] = "fp32"
    save_metadata["converted_to"] = str(target_dtype)
    save_file(converted_state, output_path, metadata=save_metadata)
    del converted_state
    gc.collect()

    return _print_stats(input_path, output_path, total_bytes_in, total_bytes_out,
                        converted_count, skipped_count, t0)


def _sharded_convert(
    input_path, output_path, target_dtype, all_keys, metadata,
    *, chunk_size, skip_non_float, max_shard_bytes, t0,
) -> dict[str, str]:
    """Convert and save as multiple sharded safetensors files.

    Each shard holds ~max_shard_bytes of converted tensors, so peak RAM
    stays well under system limits.

    Output files: base-00001-of-NNNNN.safetensors, etc.
    """
    from safetensors import safe_open
    from safetensors.torch import save_file

    total_keys = len(all_keys)
    base_stem = output_path.replace(".safetensors", "")

    shard_state = {}
    shard_bytes = 0
    shard_idx = 0
    shard_files = []

    converted_count = 0
    skipped_count = 0
    total_bytes_in = 0
    total_bytes_out = 0

    save_metadata = dict(metadata) if metadata else {}
    save_metadata["converted_from"] = "fp32"
    save_metadata["converted_to"] = str(target_dtype)

    def flush_shard():
        nonlocal shard_state, shard_bytes, shard_idx
        if not shard_state:
            return
        shard_idx += 1
        # We'll rename later once we know total shard count
        tmp_path = f"{base_stem}-shard-{shard_idx:05d}.safetensors.tmp"
        shard_meta = dict(save_metadata)
        shard_meta["shard_index"] = str(shard_idx)
        print(f"    → Flushing shard {shard_idx} ({len(shard_state)} tensors, "
              f"{shard_bytes / (1024**3):.1f} GB)...")
        save_file(shard_state, tmp_path, metadata=shard_meta)
        shard_files.append(tmp_path)
        del shard_state
        gc.collect()
        shard_state = {}
        shard_bytes = 0

    for i, key in enumerate(all_keys):
        with safe_open(input_path, framework="pt", device="cpu") as f:
            tensor = f.get_tensor(key)

        total_bytes_in += tensor.nelement() * tensor.element_size()

        if skip_non_float and not tensor.is_floating_point():
            shard_state[key] = tensor
            out_bytes = tensor.nelement() * tensor.element_size()
            total_bytes_out += out_bytes
            shard_bytes += out_bytes
            skipped_count += 1
        else:
            converted = tensor.to(target_dtype)
            shard_state[key] = converted
            out_bytes = converted.nelement() * converted.element_size()
            total_bytes_out += out_bytes
            shard_bytes += out_bytes
            converted_count += 1
            del tensor

        # Flush when shard is full
        if shard_bytes >= max_shard_bytes:
            flush_shard()

        if (i + 1) % 100 == 0 or i == total_keys - 1:
            pct = (i + 1) / total_keys * 100
            print(f"  [{pct:5.1f}%] {i+1}/{total_keys} tensors | "
                  f"shard RAM: {shard_bytes / (1024**3):.1f} GB | "
                  f"shards written: {len(shard_files)}")

        if (i + 1) % 50 == 0:
            gc.collect()

    # Flush remaining
    flush_shard()

    # Rename temp files to final sharded names
    total_shards = len(shard_files)
    final_files = []
    for idx, tmp_path in enumerate(shard_files, 1):
        final_name = f"{base_stem}-{idx:05d}-of-{total_shards:05d}.safetensors"
        os.rename(tmp_path, final_name)
        final_files.append(final_name)
        print(f"  Renamed: {os.path.basename(final_name)}")

    print(f"\n✓ Saved {total_shards} shards")
    for fp in final_files:
        print(f"  {os.path.basename(fp)}: {os.path.getsize(fp) / (1024**3):.2f} GB")

    return _print_stats(input_path, None, total_bytes_in, total_bytes_out,
                        converted_count, skipped_count, t0, shard_count=total_shards)


def _print_stats(input_path, output_path, total_bytes_in, total_bytes_out,
                 converted_count, skipped_count, t0, shard_count=0):
    elapsed = time.time() - t0
    in_gb = total_bytes_in / (1024**3)
    out_gb = total_bytes_out / (1024**3)
    ratio = out_gb / in_gb * 100 if in_gb > 0 else 0

    print(f"\n✓ Conversion complete in {elapsed:.0f}s")
    print(f"  Input:  {in_gb:.2f} GB")
    print(f"  Output: {out_gb:.2f} GB ({ratio:.0f}% of original)")
    if output_path and os.path.isfile(output_path):
        print(f"  Saved:  {output_path}")
        print(f"  Size:   {os.path.getsize(output_path) / (1024**3):.2f} GB on disk")
    if shard_count:
        print(f"  Shards: {shard_count}")

    return {
        "input_gb": f"{in_gb:.2f}",
        "output_gb": f"{out_gb:.2f}",
        "ratio": f"{ratio:.0f}%",
        "converted": converted_count,
        "skipped": skipped_count,
        "elapsed_s": f"{elapsed:.0f}",
    }


def download_fp32(output_dir: str) -> str:
    """Download the FP32 fusion checkpoint from HuggingFace.

    Tries AEmotionStudio mirror first, falls back to official repo.

    Returns:
        Path to the downloaded .safetensors file.
    """
    try:
        from huggingface_hub import hf_hub_download
    except ImportError:
        print("ERROR: huggingface_hub required. Install with: pip install huggingface_hub")
        sys.exit(1)

    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "dreamid_omni.safetensors")

    if os.path.isfile(output_path):
        size_gb = os.path.getsize(output_path) / (1024**3)
        print(f"FP32 checkpoint already exists: {output_path} ({size_gb:.1f} GB)")
        return output_path

    print("Downloading FP32 fusion checkpoint from HuggingFace...")
    print("This is ~46.6 GB and may take a while.\n")

    # Try official repo
    try:
        hf_hub_download(
            repo_id="XuGuo699/DreamID-Omni",
            filename="dreamid_omni.safetensors",
            local_dir=output_dir,
        )
        print(f"✓ Downloaded to {output_path}")
        return output_path
    except Exception as e:
        print(f"Download failed: {e}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Convert DreamID-Omni fusion checkpoint to BF16/FP8"
    )
    parser.add_argument(
        "--input", "-i",
        help="Path to source FP32 dreamid_omni.safetensors",
    )
    parser.add_argument(
        "--download", "-d",
        action="store_true",
        help="Download FP32 checkpoint from HuggingFace first",
    )
    parser.add_argument(
        "--output-dir", "-o",
        default=".",
        help="Directory for converted output files (default: current dir)",
    )
    parser.add_argument(
        "--format", "-f",
        nargs="+",
        choices=["bf16", "fp8"],
        default=["bf16", "fp8"],
        help="Output format(s) to produce (default: both)",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=50,
        help="Tensors per chunk during conversion (lower = less RAM, default 50)",
    )

    args = parser.parse_args()

    if args.download:
        args.input = download_fp32(args.output_dir)
    elif not args.input:
        parser.error("Either --input or --download is required")

    if not os.path.isfile(args.input):
        print(f"ERROR: Input file not found: {args.input}")
        sys.exit(1)

    size_gb = os.path.getsize(args.input) / (1024**3)
    print(f"\nSource: {args.input} ({size_gb:.1f} GB)")

    dtype_map = {
        "bf16": (torch.bfloat16, "dreamid_omni_bf16.safetensors"),
        "fp8": (torch.float8_e4m3fn, "dreamid_omni_fp8.safetensors"),
    }

    results = {}
    for fmt in args.format:
        dtype, filename = dtype_map[fmt]
        output_path = os.path.join(args.output_dir, filename)

        if os.path.isfile(output_path):
            existing_gb = os.path.getsize(output_path) / (1024**3)
            print(f"\n⚠ {fmt.upper()} output already exists: {output_path} ({existing_gb:.1f} GB)")
            print("  Skipping (delete to re-convert)")
            continue

        stats = _stream_convert_safetensors(
            input_path=args.input,
            output_path=output_path,
            target_dtype=dtype,
            chunk_size=args.chunk_size,
        )
        results[fmt] = stats

    # Summary
    if results:
        print(f"\n{'='*60}")
        print("CONVERSION SUMMARY")
        print(f"{'='*60}")
        for fmt, stats in results.items():
            print(f"  {fmt.upper()}: {stats['input_gb']} GB → {stats['output_gb']} GB "
                  f"({stats['ratio']}) in {stats['elapsed_s']}s")
        print(f"\nOutput directory: {args.output_dir}")
        print("\nNext steps:")
        print("  1. Upload to HuggingFace: huggingface-cli upload AEmotionStudio/dreamid-omni <file>")
        print("  2. Delete the FP32 source if no longer needed")


if __name__ == "__main__":
    main()
