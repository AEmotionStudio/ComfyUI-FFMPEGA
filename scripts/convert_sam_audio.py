#!/usr/bin/env python3
"""Convert facebook/sam-audio-large-tv to BF16 safetensors.

Ultra-low-memory version: the FP32 checkpoint is 13.84 GiB with 1345
tensors.  With only 30 GB RAM we cannot hold the full BF16 dict (~7 GiB)
alongside the mmap'd source.  Instead we:

  1. mmap-load the checkpoint
  2. Write a temporary per-tensor file for each BF16 tensor (disk is cheap)
  3. Build the final safetensors from the temp files in one pass

Usage:
    python scripts/convert_sam_audio.py
    python scripts/convert_sam_audio.py --output /path/to/output/
"""

import argparse
import gc
import os
import shutil
import sys
import tempfile


def main():
    parser = argparse.ArgumentParser(
        description="Convert SAM-Audio model to BF16 safetensors (low-memory)"
    )
    parser.add_argument(
        "--model", default="facebook/sam-audio-large-tv",
        help="HuggingFace model ID",
    )
    parser.add_argument(
        "--output", default=None,
        help="Output directory (default: ComfyUI/models/sam_audio/)",
    )
    parser.add_argument(
        "--dtype", default="bf16", choices=["bf16", "fp16", "fp32"],
        help="Target dtype (default: bf16)",
    )
    args = parser.parse_args()

    import torch

    if args.output:
        output_dir = args.output
    else:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        comfyui_root = os.path.abspath(os.path.join(script_dir, "..", "..", ".."))
        output_dir = os.path.join(comfyui_root, "models", "sam_audio")
    os.makedirs(output_dir, exist_ok=True)

    dtype_map = {"bf16": torch.bfloat16, "fp16": torch.float16, "fp32": torch.float32}
    target_dtype = dtype_map[args.dtype]
    dtype_label = args.dtype

    print(f"[SAM-Audio Convert] Model:  {args.model}")
    print(f"[SAM-Audio Convert] Output: {output_dir}")
    print(f"[SAM-Audio Convert] Dtype:  {dtype_label}")
    print(f"[SAM-Audio Convert] Mode:   ultra-low-memory (one tensor at a time)")

    # ── Step 1: Download ──────────────────────────────────────────────
    print("\n[1/5] Downloading model from HuggingFace...")
    from huggingface_hub import snapshot_download
    cached_dir = snapshot_download(repo_id=args.model, token=True)
    print(f"  Downloaded to: {cached_dir}")

    ckpt_path = os.path.join(cached_dir, "checkpoint.pt")
    if not os.path.isfile(ckpt_path):
        print(f"  ERROR: checkpoint.pt not found.  Files: {os.listdir(cached_dir)}")
        sys.exit(1)
    print(f"  Checkpoint size: {os.path.getsize(ckpt_path) / 1024**3:.2f} GiB")

    # ── Step 2: mmap-load & collect metadata ──────────────────────────
    print("\n[2/5] Memory-mapping checkpoint...")
    state_dict = torch.load(ckpt_path, map_location="cpu", weights_only=True, mmap=True)
    keys = list(state_dict.keys())
    print(f"  Found {len(keys)} tensors")

    # ── Step 3: Convert ONE tensor at a time, save to temp files ──────
    print(f"\n[3/5] Converting to {dtype_label} (one tensor at a time → temp files)...")
    tmp_dir = tempfile.mkdtemp(prefix="sa_conv_")
    tensor_metadata = {}  # key → (shape, dtype, tmp_path)
    total_orig = 0
    total_new = 0

    for i, key in enumerate(keys):
        tensor = state_dict[key]
        total_orig += tensor.nbytes

        if tensor.is_floating_point():
            converted = tensor.to(target_dtype).contiguous()
        else:
            converted = tensor.contiguous()

        total_new += converted.nbytes

        # Save this single tensor to a temp file
        safe_name = key.replace("/", "__").replace(".", "_") + ".pt"
        tmp_path = os.path.join(tmp_dir, safe_name)
        torch.save(converted, tmp_path)
        tensor_metadata[key] = (converted.shape, converted.dtype, tmp_path)

        # Aggressively free memory
        del converted, tensor
        if (i + 1) % 100 == 0:
            gc.collect()
            pct = int((i + 1) / len(keys) * 100)
            print(f"  [{pct:3d}%] {i+1}/{len(keys)} tensors converted")

    # Free the mmap'd state dict entirely
    del state_dict
    gc.collect()

    num_params = 0
    for key, (shape, dtype, _) in tensor_metadata.items():
        n = 1
        for s in shape:
            n *= s
        num_params += n

    print(f"  Original size: {total_orig / 1024**3:.2f} GiB")
    print(f"  Converted size: {total_new / 1024**3:.2f} GiB")
    print(f"  Reduction: {(1 - total_new / total_orig) * 100:.1f}%")
    print(f"  Parameters: {num_params:,}")

    # ── Step 4: Reassemble into safetensors ───────────────────────────
    # Load temp files in batches to build the safetensors dict
    # Each temp .pt file is tiny (~a few MB), so we can load them all
    # since the BF16 total is ~7 GiB which should fit now that the
    # 14 GiB mmap is freed.
    print(f"\n[4/5] Assembling safetensors from {len(keys)} temp files...")

    from safetensors.torch import save_file

    model_name = args.model.split("/")[-1]
    safetensors_name = f"{model_name}-{dtype_label}.safetensors"
    safetensors_path = os.path.join(output_dir, safetensors_name)

    # Reload in batches of 200 to keep memory bounded
    batch_size = 200
    final_dict = {}
    sorted_keys = list(tensor_metadata.keys())

    for batch_start in range(0, len(sorted_keys), batch_size):
        batch_keys = sorted_keys[batch_start:batch_start + batch_size]
        for key in batch_keys:
            _, _, tmp_path = tensor_metadata[key]
            final_dict[key] = torch.load(tmp_path, map_location="cpu", weights_only=True)
        pct = min(100, int((batch_start + len(batch_keys)) / len(sorted_keys) * 100))
        print(f"  [{pct:3d}%] Loaded {min(batch_start + batch_size, len(sorted_keys))}/{len(sorted_keys)} tensors")

    print(f"  Saving {safetensors_path}...")
    save_file(final_dict, safetensors_path)
    del final_dict
    gc.collect()

    file_size = os.path.getsize(safetensors_path)
    print(f"  File size: {file_size / 1024**3:.2f} GiB")

    # Clean up temp files
    shutil.rmtree(tmp_dir, ignore_errors=True)
    print("  Cleaned up temp files")

    # ── Step 5: Mirror files ──────────────────────────────────────────
    print(f"\n[5/5] Creating mirror files...")

    config_src = os.path.join(cached_dir, "config.json")
    if os.path.isfile(config_src):
        shutil.copy2(config_src, os.path.join(output_dir, "config.json"))
        print("  Copied config.json")

    license_src = os.path.join(cached_dir, "LICENSE")
    if os.path.isfile(license_src):
        shutil.copy2(license_src, os.path.join(output_dir, "LICENSE"))
        print("  Copied LICENSE (SAM License)")
    else:
        print("  Downloading LICENSE from GitHub...")
        try:
            import urllib.request
            urllib.request.urlretrieve(
                "https://raw.githubusercontent.com/facebookresearch/sam-audio/main/LICENSE",
                os.path.join(output_dir, "LICENSE"),
            )
            print("  Downloaded LICENSE")
        except Exception as e:
            print(f"  WARNING: Could not download LICENSE: {e}")

    orig_gib = total_orig / 1024**3
    file_gib = file_size / 1024**3
    readme_path = os.path.join(output_dir, "README.md")
    with open(readme_path, "w") as f:
        f.write(f"""---
license: other
license_name: sam-license
license_link: LICENSE
tags:
  - audio
  - audio-separation
  - sound-separation
  - sam-audio
  - meta
  - pytorch
  - safetensors
  - bf16
pipeline_tag: audio-to-audio
base_model: {args.model}
---

# SAM-Audio Large-TV ({dtype_label.upper()})

This is an **ungated mirror** of Meta's [SAM-Audio Large-TV](https://huggingface.co/{args.model}) model weights, converted to {dtype_label.upper()} safetensors format and redistributed under the [SAM License](LICENSE) for easier access.

## What is SAM-Audio?

SAM-Audio (Segment Anything Model for Audio) is Meta AI's foundation model for **isolating any sound in audio** using text, visual, or temporal prompts. It can separate specific sounds from complex audio mixtures.

- **Text prompts** — isolate sounds by describing them (e.g. *"drums"*, *"vocals"*, *"piano"*)
- **Visual prompts** — point at objects in video to extract their sound
- **Span prompts** — specify time ranges where the target sound occurs

The `-tv` variant is optimized for **target correctness** and **visual prompting**.

## Files

| File | Description |
|---|---|
| `{safetensors_name}` | Model weights ({dtype_label.upper()} safetensors format) |
| `config.json` | Model configuration |
| `LICENSE` | SAM License (required for redistribution) |

## Model Info

| Property | Value |
|---|---|
| Source | [`{args.model}`](https://huggingface.co/{args.model}) |
| Dtype | `{dtype_label}` (`{target_dtype}`) |
| Parameters | {num_params:,} |
| File size | {file_gib:.2f} GiB (original: {orig_gib:.2f} GiB) |
| Sample rate | 48,000 Hz |

## Usage

```python
# With ComfyUI-FFMPEGA (automatic download)
# Set no_llm_mode = "audio_separate" and prompt = "vocals"

# Or standalone:
from sam_audio import SAMAudio
model = SAMAudio.from_pretrained("path/to/this/repo")
```

## License

This model is distributed under the **SAM License** — see the [LICENSE](LICENSE) file. Key points:

- ✅ Commercial use permitted
- ✅ Redistribution permitted (with license included)
- ✅ Derivative works permitted
- ❌ No military/warfare, nuclear, or espionage use
- ❌ No reverse engineering

## Credits

- **Original model by**: [Meta AI (FAIR)](https://github.com/facebookresearch/sam-audio)
- **Original HuggingFace repo**: [{args.model}](https://huggingface.co/{args.model})
- **Paper**: *SAM-Audio: Segment Anything in Audio*
- **Redistributed by**: [Æmotion Studio](https://huggingface.co/AEmotionStudio) for use with [ComfyUI-FFMPEGA](https://github.com/AEmotionStudio/ComfyUI-FFMPEGA)
""")
    print("  Created README.md")

    print(f"\n✅ Done! Output directory: {output_dir}")
    for name in [safetensors_name, "config.json", "LICENSE", "README.md"]:
        print(f"   {name}")


if __name__ == "__main__":
    main()
