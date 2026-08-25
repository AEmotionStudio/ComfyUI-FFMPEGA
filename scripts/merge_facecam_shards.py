#!/usr/bin/env python3
"""Download and merge FaceCam bf16 sharded checkpoints into single files.

Downloads from wlyu/FaceCam on HuggingFace, merges 2 shards per stage
into single safetensors files, and places them in ComfyUI/models/diffusion_models/.

Usage:
    python scripts/merge_facecam_shards.py

Output:
    ComfyUI/models/diffusion_models/facecam_wan2.2_14b_high_bf16.safetensors
    ComfyUI/models/diffusion_models/facecam_wan2.2_14b_low_bf16.safetensors

These can be loaded directly via ComfyUI's "Load Diffusion Model" node.
"""

import gc
import logging
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
log = logging.getLogger("facecam_shards")

HF_REPO = "wlyu/FaceCam"
STAGES = ("high", "low")
SHARD_TEMPLATE = "wan2.2_14b/{stage}/released_version/model-{shard}-of-00002.safetensors"


def get_comfyui_root() -> Path:
    """Find ComfyUI root directory."""
    p = Path(__file__).resolve()
    for parent in p.parents:
        if (parent / "comfy").is_dir() and (parent / "models").is_dir():
            return parent
    return Path.home() / "ComfyUI"


def main():
    import torch
    from safetensors.torch import save_file

    try:
        from huggingface_hub import hf_hub_download
    except ImportError:
        log.error("huggingface_hub not installed. Run: pip install huggingface_hub")
        sys.exit(1)

    try:
        from safetensors import safe_open
    except ImportError:
        log.error("safetensors not installed. Run: pip install safetensors")
        sys.exit(1)

    comfyui_root = get_comfyui_root()
    output_dir = comfyui_root / "models" / "diffusion_models"
    output_dir.mkdir(parents=True, exist_ok=True)

    cache_dir = comfyui_root / "models" / ".cache" / "facecam_download"
    cache_dir.mkdir(parents=True, exist_ok=True)

    log.info("ComfyUI root: %s", comfyui_root)
    log.info("Output dir: %s", output_dir)

    for stage in STAGES:
        output_path = output_dir / f"facecam_wan2.2_14b_{stage}_bf16.safetensors"

        if output_path.exists():
            sz = output_path.stat().st_size / (1024**3)
            log.info("Already exists (%.2f GB), skipping: %s", sz, output_path.name)
            continue

        log.info("=== Processing stage: %s ===", stage)

        # Download and merge shards
        state_dict = {}
        for shard_num in ("00001", "00002"):
            filename = SHARD_TEMPLATE.format(stage=stage, shard=shard_num)
            log.info("Downloading %s/%s ...", HF_REPO, filename)
            local_path = hf_hub_download(
                repo_id=HF_REPO,
                filename=filename,
                cache_dir=str(cache_dir),
            )
            log.info("Loading shard: %s", Path(local_path).name)
            with safe_open(local_path, framework="pt", device="cpu") as f:
                for key in f.keys():
                    state_dict[key] = f.get_tensor(key)

        log.info("Stage '%s': loaded %d tensors", stage, len(state_dict))

        # Save merged file (already bf16 from upstream)
        log.info("Saving merged model: %s ...", output_path.name)
        save_file(state_dict, str(output_path))
        sz = output_path.stat().st_size / (1024**3)
        log.info("Saved: %.2f GB", sz)

        del state_dict
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    # Also download gaussians.ply and face_landmarker
    facecam_dir = comfyui_root / "models" / "facecam"
    facecam_dir.mkdir(parents=True, exist_ok=True)

    ply_path = facecam_dir / "gaussians.ply"
    if not ply_path.exists():
        log.info("Downloading gaussians.ply (~44 MB)...")
        local = hf_hub_download(
            repo_id=HF_REPO,
            filename="gaussians.ply",
            cache_dir=str(cache_dir),
        )
        import shutil
        shutil.copy2(local, str(ply_path))
        log.info("Saved: %s", ply_path)

    landmarker_path = facecam_dir / "face_landmarker_v2_with_blendshapes.task"
    if not landmarker_path.exists():
        log.info("Downloading MediaPipe face landmarker (~5 MB)...")
        import urllib.request
        url = (
            "https://storage.googleapis.com/mediapipe-models/"
            "face_landmarker/face_landmarker/float16/latest/"
            "face_landmarker.task"
        )
        urllib.request.urlretrieve(url, str(landmarker_path))
        log.info("Saved: %s", landmarker_path)

    log.info("=== Done! ===")
    log.info("Load in ComfyUI via 'Load Diffusion Model' node:")
    for stage in STAGES:
        log.info("  - facecam_wan2.2_14b_%s_bf16.safetensors", stage)
    log.info("")
    log.info("You also need the Wan2.2 Q4_K_M GGUF as base model.")
    log.info("Connect both to the FaceCam node.")


if __name__ == "__main__":
    main()
