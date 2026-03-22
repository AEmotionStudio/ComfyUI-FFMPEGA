"""Model download guard for FFMPEGA.

When the user sets allow_model_downloads=False on the FFMPEG Agent node,
calling require_downloads_allowed() raises a RuntimeError before any model
auto-download can occur. Call this at the top of any model loading function
that may trigger a download.
"""

from __future__ import annotations

import logging

log = logging.getLogger("ffmpega")

# ---------------------------------------------------------------------------
#  Global flag (set by agent_node.py before each skill run)
# ---------------------------------------------------------------------------

_downloads_allowed: bool = True


def set_downloads_allowed(allowed: bool) -> None:
    """Set the global model-download permission flag.

    Called by agent_node.py at the start of each run, before skill
    handlers are invoked.
    """
    global _downloads_allowed
    _downloads_allowed = allowed


def downloads_allowed() -> bool:
    """Return the current model-download permission flag."""
    return _downloads_allowed


# ---------------------------------------------------------------------------
#  Model registry — info shown in the error message when blocked
# ---------------------------------------------------------------------------

_MODEL_INFO: dict[str, dict] = {
    "sam3": {
        "name": "SAM3 (Segment Anything Model 3)",
        "size": "~300 MB",
        "url": "https://huggingface.co/AEmotionStudio/sam3",
        "mirror_repo": "AEmotionStudio/sam3",
        "manual": "Download sam3.safetensors and place it in ComfyUI/models/SAM3/",
    },
    "lama": {
        "name": "LaMa (Large Mask Inpainting)",
        "size": "~200 MB",
        "url": "https://huggingface.co/AEmotionStudio/lama-inpainting",
        "mirror_repo": "AEmotionStudio/lama-inpainting",
        "mirror_filename": "big-lama.safetensors",
        "manual": "Download big-lama.safetensors from "
                  "https://huggingface.co/AEmotionStudio/lama-inpainting "
                  "and place it in ~/.cache/torch/hub/checkpoints/",
    },
    "whisper": {
        "name": "OpenAI Whisper",
        "size": "75 MB (tiny) – 3 GB (large-v3)",
        "url": "https://huggingface.co/AEmotionStudio/whisper-models",
        "mirror_repo": "AEmotionStudio/whisper-models",
        "manual": "Download the model .pt file from "
                  "https://huggingface.co/AEmotionStudio/whisper-models "
                  "and place it in ComfyUI/models/whisper/",
    },
    "mmaudio": {
        "name": "MMAudio (Video-to-Audio Synthesis)",
        "size": "~5.5 GB total (3 core + CLIP + BigVGAN)",
        "url": "https://huggingface.co/hkchengrex/MMAudio",
        "mirror_repo": "AEmotionStudio/mmaudio-models",
        "license": "CC-BY-NC 4.0 (non-commercial use only)",
        "manual": "Download model files from "
                  "https://huggingface.co/AEmotionStudio/mmaudio-models "
                  "and place them in ComfyUI/models/mmaudio/. "
                  "⚠️ Model weights are CC-BY-NC 4.0 (non-commercial).",
    },
    "audiox": {
        "name": "AudioX (Unified Audio/Music Generation)",
        "size": "~5 GB (model + VAE + Synchformer)",
        "url": "https://huggingface.co/HKUSTAudio/AudioX-MAF",
        "mirror_repo": "AEmotionStudio/audiox-models",
        "license": "CC-BY-NC (non-commercial use only)",
        "manual": "Download model.ckpt, config.json, VAE.ckpt, and "
                  "synchformer_state_dict.pth from "
                  "https://huggingface.co/HKUSTAudio/AudioX-MAF "
                  "and place them in ComfyUI/models/audiox/. "
                  "⚠️ Model weights are CC-BY-NC (non-commercial).",
    },
    "musetalk": {
        "name": "MuseTalk (Lip Sync)",
        "size": "~3.2 GB (UNet) + ~335 MB (VAE, Whisper – separate downloads)",
        "url": "https://huggingface.co/TMElyralab/MuseTalk",
        "mirror_repo": "AEmotionStudio/musetalk-models",
        "license": "MIT (code), CreativeML Open RAIL-M (SD-VAE)",
        "manual": "Download model files from "
                  "https://huggingface.co/AEmotionStudio/musetalk-models "
                  "and place them in ComfyUI/models/musetalk/.",
    },
    "flux_klein": {
        "name": "FLUX Klein 4B (Image Editing)",
        "size": "~15 GB (bf16)",
        "url": "https://huggingface.co/AEmotionStudio/flux-klein",
        "mirror_repo": "AEmotionStudio/flux-klein",
        "license": "Apache 2.0",
        "manual": "Download model files from "
                  "https://huggingface.co/AEmotionStudio/flux-klein "
                  "and place them in ComfyUI/models/flux_klein/.",
    },
    "minimax_remover": {
        "name": "MiniMax-Remover (Video Object Removal)",
        "size": "~2.5 GB (transformer + VAE + scheduler)",
        "url": "https://huggingface.co/AEmotionStudio/minimax-remover",
        "mirror_repo": "AEmotionStudio/minimax-remover",
        "license": "CC-BY-NC-4.0",
        "manual": "⚠️ NON-COMMERCIAL LICENSE: MiniMax-Remover model weights are CC-BY-NC-4.0. "
                  "Download from "
                  "https://huggingface.co/AEmotionStudio/minimax-remover "
                  "— place vae/, transformer/, scheduler/ subdirs in "
                  "ComfyUI/models/minimax_remover/.",
    },
    "liveportrait": {
        "name": "LivePortrait (Portrait Animation)",
        "size": "~497 MB (5 model components)",
        "url": "https://huggingface.co/AEmotionStudio/liveportrait-models",
        "mirror_repo": "AEmotionStudio/liveportrait-models",
        "license": "MIT (code), see upstream for weights",
        "manual": "Download model files from "
                  "https://huggingface.co/AEmotionStudio/liveportrait-models "
                  "and place them in ComfyUI/models/liveportrait/.",
    },
    "marigold": {
        "name": "Marigold (Dense Vision Analysis)",
        "size": "~2.5 GB per mode (depth/normals/appearance/lighting)",
        "url": "https://huggingface.co/AEmotionStudio",
        "mirror_repo": "AEmotionStudio/marigold-depth-v1-1",
        "license": "CreativeML Open RAIL++-M",
        "manual": "Models are auto-downloaded by diffusers via from_pretrained(). "
                  "See https://huggingface.co/prs-eth for upstream checkpoints.",
    },
    "video_depth": {
        "name": "Video Depth Anything (Temporal Video Depth)",
        "size": "~102 MB (Small), ~390 MB (Base), ~670 MB (Large)",
        "url": "https://huggingface.co/depth-anything",
        "mirror_repo": "AEmotionStudio/Video-Depth-Anything-Small",
        "license": "Apache 2.0",
        "manual": "Checkpoints are auto-downloaded from HuggingFace. "
                  "See https://github.com/DepthAnything/Video-Depth-Anything for details.",
    },
    "ai_upscale": {
        "name": "AI Upscaler (Real-ESRGAN / HAT / DAT / SwinIR)",
        "size": "~17-170 MB per model",
        "url": "https://huggingface.co/AEmotionStudio/ai-upscale-models",
        "mirror_repo": "AEmotionStudio/ai-upscale-models",
        "license": "BSD-3-Clause (Real-ESRGAN) / Apache 2.0 (SwinIR)",
        "manual": "Models are auto-downloaded from HuggingFace on first use. "
                  "See https://huggingface.co/AEmotionStudio/ai-upscale-models",
    },
    "acestep": {
        "name": "ACE-Step 1.5 (Music Generation)",
        "size": "~6 GB (DiT turbo + 1.7B LM + VAE + text encoder)",
        "url": "https://huggingface.co/ACE-Step/Ace-Step1.5",
        "mirror_repo": "AEmotionStudio/acestep-models",
        "license": "MIT",
        "manual": "Download model files from "
                  "https://huggingface.co/ACE-Step/Ace-Step1.5 "
                  "and place them in ComfyUI/models/acestep/checkpoints/.",
    },
    "normalcrafter": {
        "name": "NormalCrafter (Video Normal Maps)",
        "size": "~4.5 GB (UNet + VAE + SVD base)",
        "url": "https://huggingface.co/AEmotionStudio/NormalCrafter",
        "mirror_repo": "AEmotionStudio/NormalCrafter",
        "license": "Apache-2.0",
        "manual": "Models are auto-downloaded from HuggingFace via from_pretrained(). "
                  "See https://github.com/Binyr/NormalCrafter for upstream.",
    },
    "seedvr2": {
        "name": "SeedVR2 (Diffusion Video/Image Upscaler)",
        "size": "~3-4 GB (DiT) + ~300 MB (VAE)",
        "url": "https://huggingface.co/AEmotionStudio/SeedVR2-models",
        "mirror_repo": "AEmotionStudio/SeedVR2-models",
        "license": "Apache-2.0",
        "manual": "Download DiT model (e.g. seedvr2_ema_3b_fp8_e4m3fn.safetensors) "
                  "and ema_vae_fp16.safetensors from "
                  "https://huggingface.co/AEmotionStudio/SeedVR2-models "
                  "and place them in the SeedVR2 cache directory.",
    },
    "kiwi_edit_instruct": {
        "name": "Kiwi-Edit 5B (Instruct Only)",
        "size": "~10 GB",
        "url": "https://huggingface.co/linyq/kiwi-edit-5b-instruct-only-diffusers",
        "mirror_repo": "AEmotionStudio/kiwi-edit-instruct",
        "license": "MIT",
        "manual": "Download model files from "
                  "https://huggingface.co/linyq/kiwi-edit-5b-instruct-only-diffusers "
                  "and place them in ComfyUI/models/kiwi_edit_instruct/.",
    },
    "kiwi_edit_reference": {
        "name": "Kiwi-Edit 5B (Reference Only)",
        "size": "~10 GB",
        "url": "https://huggingface.co/linyq/kiwi-edit-5b-reference-only-diffusers",
        "mirror_repo": "AEmotionStudio/kiwi-edit-reference",
        "license": "MIT",
        "manual": "Download model files from "
                  "https://huggingface.co/linyq/kiwi-edit-5b-reference-only-diffusers "
                  "and place them in ComfyUI/models/kiwi_edit_reference/.",
    },
    "kiwi_edit_instruct_reference": {
        "name": "Kiwi-Edit 5B (Instruct + Reference)",
        "size": "~10 GB",
        "url": "https://huggingface.co/linyq/kiwi-edit-5b-instruct-reference-diffusers",
        "mirror_repo": "AEmotionStudio/kiwi-edit-instruct-reference",
        "license": "MIT",
        "manual": "Download model files from "
                  "https://huggingface.co/linyq/kiwi-edit-5b-instruct-reference-diffusers "
                  "and place them in ComfyUI/models/kiwi_edit_instruct_reference/.",
    },
    # Kiwi-Edit FP8 variants (auto-downloaded by default)
    "kiwi_edit_instruct_fp8": {
        "name": "Kiwi-Edit 5B FP8 (Instruct Only)",
        "size": "~5 GB",
        "url": "https://huggingface.co/AEmotionStudio/kiwi-edit-instruct-fp8",
        "mirror_repo": "AEmotionStudio/kiwi-edit-instruct-fp8",
        "license": "MIT",
        "manual": "Downloaded automatically when Kiwi-Edit is used.",
    },
    "kiwi_edit_reference_fp8": {
        "name": "Kiwi-Edit 5B FP8 (Reference Only)",
        "size": "~5 GB",
        "url": "https://huggingface.co/AEmotionStudio/kiwi-edit-reference-fp8",
        "mirror_repo": "AEmotionStudio/kiwi-edit-reference-fp8",
        "license": "MIT",
        "manual": "Downloaded automatically when Kiwi-Edit is used.",
    },
    "kiwi_edit_instruct_reference_fp8": {
        "name": "Kiwi-Edit 5B FP8 (Instruct + Reference)",
        "size": "~5 GB",
        "url": "https://huggingface.co/AEmotionStudio/kiwi-edit-instruct-reference-fp8",
        "mirror_repo": "AEmotionStudio/kiwi-edit-instruct-reference-fp8",
        "license": "MIT",
        "manual": "Downloaded automatically when Kiwi-Edit is used.",
    },
    "dreamid_omni": {
        "name": "DreamID-Omni (Fusion DiT)",
        "size": "~5 GB",
        "url": "https://github.com/Guoxu1233/DreamID-Omni",
        "mirror_repo": "AEmotionStudio/dreamid-omni",
        "license": "Apache-2.0",
        "manual": "Download dreamid_omni.safetensors from "
                  "https://github.com/Guoxu1233/DreamID-Omni "
                  "and place it in ComfyUI/models/dreamid_omni/DreamID_Omni/.",
    },
    "dreamid_omni_wan": {
        "name": "DreamID-Omni Wan2.2 (T5 + VAE)",
        "size": "~10.5 GB",
        "url": "https://huggingface.co/Wan-AI/Wan2.2-TI2V-5B",
        "mirror_repo": "AEmotionStudio/dreamid-omni-wan",
        "license": "Apache-2.0",
        "manual": "Download Wan2.2_VAE.pth, models_t5_umt5-xxl-enc-bf16.pth, and "
                  "google/umt5-xxl/ from https://huggingface.co/Wan-AI/Wan2.2-TI2V-5B "
                  "and place them in ComfyUI/models/dreamid_omni/Wan2.2-TI2V-5B/.",
    },
    "dreamid_omni_mmaudio": {
        "name": "DreamID-Omni MMAudio (Audio VAE)",
        "size": "~350 MB",
        "url": "https://huggingface.co/hkchengrex/MMAudio",
        "mirror_repo": "AEmotionStudio/dreamid-omni-mmaudio",
        "license": "CC-BY-NC 4.0",
        "manual": "Download ext_weights/v1-16.pth and ext_weights/best_netG.pt from "
                  "https://huggingface.co/hkchengrex/MMAudio "
                  "and place them in ComfyUI/models/dreamid_omni/MMAudio/ext_weights/.",
    },
    "facecam": {
        "name": "FaceCam (Portrait Camera Control)",
        "size": "~16.8 GB (high+low bf16) + ~44 MB (gaussians.ply)",
        "url": "https://huggingface.co/wlyu/FaceCam",
        "license": "Apache-2.0",
        "manual": "Run: python scripts/merge_facecam_shards.py to download "
                  "and merge FaceCam bf16 checkpoints into "
                  "ComfyUI/models/diffusion_models/.",
    },
}


def require_downloads_allowed(model_key: str) -> None:
    """Raise RuntimeError if model downloads are disabled.

    Call this at the start of any model loading function that may trigger
    an automatic download. When blocked, logs a clear console message with
    the model's download URL so the user knows where to get it manually.

    Args:
        model_key: A key from ``_MODEL_INFO`` (e.g. ``"sam3"``,
            ``"minimax_remover"``, ``"ai_upscale"``).

    Raises:
        RuntimeError: If allow_model_downloads is False on the node.
    """
    if _downloads_allowed:
        return

    info = _MODEL_INFO.get(model_key, {
        "name": model_key,
        "size": "unknown",
        "url": "https://github.com/AEmotionStudio/ComfyUI-FFMPEGA",
        "manual": "See project README for manual installation.",
    })

    msg = (
        f"\n"
        f"[FFMPEGA] ⛔ Model download blocked: {info['name']} ({info['size']})\n"
        f"[FFMPEGA]    The 'allow_model_downloads' toggle is OFF on the FFMPEG Agent node.\n"
        f"[FFMPEGA]    To download automatically: enable 'allow_model_downloads' and re-run.\n"
        f"[FFMPEGA]    To install manually:       {info['manual']}\n"
        f"[FFMPEGA]    Model page:                {info['url']}\n"
    )

    # Always print to console so it's visible even if logging is suppressed
    print(msg)
    log.error(
        "Model download blocked (%s). Enable allow_model_downloads or install manually. "
        "See: %s",
        info["name"], info["url"],
    )

    raise RuntimeError(
        f"{info['name']} requires a download (~{info['size']}) but "
        f"'allow_model_downloads' is disabled on the FFMPEG Agent node. "
        f"Enable it to auto-download, or download manually from: {info['url']}"
    )


# ---------------------------------------------------------------------------
#  Mirror-first download helper
# ---------------------------------------------------------------------------


def try_mirror_download(
    model_key: str,
    filename: str,
    local_dir: str,
    *,
    convert_safetensors: bool = False,
    pt_metadata: dict | None = None,
) -> str | None:
    """Try downloading a model file from the AEmotionStudio HF mirror.

    Supports two modes:

    * **Direct** (``convert_safetensors=False``): downloads the file
      as-is (e.g. a TorchScript ``.pt`` for LaMa).
    * **Safetensors → .pt** (``convert_safetensors=True``): downloads
      the ``.safetensors`` version from the mirror and reconstructs a
      ``.pt`` file locally so downstream loaders work unchanged.

    Args:
        model_key: Registry key (e.g. ``"lama"``, ``"whisper"``).
        filename: Target filename that the caller expects locally.
        local_dir: Directory to save the downloaded/converted file.
        convert_safetensors: If ``True``, the mirror stores
            ``.safetensors`` and the helper will convert to ``.pt``.
        pt_metadata: Extra metadata to embed in the ``.pt`` file
            alongside ``model_state_dict`` (used by Whisper for
            ``dims``).  Only used when ``convert_safetensors=True``.

    Returns:
        Path to the local file, or ``None`` on any failure.
    """
    require_downloads_allowed(model_key)

    info = _MODEL_INFO.get(model_key, {})
    mirror_repo = info.get("mirror_repo")
    if not mirror_repo:
        return None

    try:
        from huggingface_hub import hf_hub_download
    except ImportError:
        return None

    import os
    os.makedirs(local_dir, exist_ok=True)

    if not convert_safetensors:
        # ── Direct download (.pt as-is) ──────────────────────────
        try:
            log.info(
                "Trying AEmotionStudio mirror for %s (%s)...",
                filename, mirror_repo,
            )
            path = hf_hub_download(
                repo_id=mirror_repo,
                filename=filename,
                local_dir=local_dir,
            )
            log.info("Mirror download succeeded: %s", path)
            return path
        except Exception as e:
            log.debug(
                "Mirror download failed for %s/%s: %s — falling back",
                mirror_repo, filename, e,
            )
            return None

    # ── Safetensors → .pt conversion ─────────────────────────────
    stem = filename.rsplit(".", 1)[0] if "." in filename else filename
    st_filename = f"{stem}.safetensors"
    pt_target = os.path.join(local_dir, filename)

    try:
        log.info(
            "Trying AEmotionStudio mirror for %s (%s)...",
            st_filename, mirror_repo,
        )
        st_path = hf_hub_download(
            repo_id=mirror_repo,
            filename=st_filename,
        )

        # Convert safetensors → .pt
        from safetensors.torch import load_file
        import torch
        import json as _json

        state_dict = load_file(st_path, device="cpu")

        # Read safetensors metadata (may contain dims for Whisper)
        st_meta = {}
        try:
            from safetensors import safe_open
            with safe_open(st_path, framework="pt") as f:
                st_meta = f.metadata() or {}
        except Exception:
            pass

        # Build the .pt payload
        pt_data: dict = {}
        if pt_metadata:
            pt_data.update(pt_metadata)

        # Restore metadata from safetensors header (e.g. Whisper dims)
        if "dims" in st_meta and "dims" not in pt_data:
            try:
                pt_data["dims"] = _json.loads(st_meta["dims"])
            except Exception:
                pass

        pt_data["model_state_dict"] = state_dict
        torch.save(pt_data, pt_target)

        log.info("Mirror download + conversion succeeded: %s", pt_target)
        return pt_target
    except Exception as e:
        log.debug(
            "Mirror download failed for %s/%s: %s — falling back",
            mirror_repo, st_filename, e,
        )
        return None


# ---------------------------------------------------------------------------
#  Download progress helpers
# ---------------------------------------------------------------------------

def log_download_start(model_key: str, extra: str = "") -> None:
    """Print a clear console banner when a model download starts.

    Args:
        model_key: Registry key (e.g. "sam3", "lama", "whisper").
        extra: Optional extra info (e.g. model size variant).
    """
    info = _MODEL_INFO.get(model_key, {"name": model_key, "size": "unknown"})
    name = info["name"]
    size = info["size"]
    suffix = f" ({extra})" if extra else ""
    msg = (
        f"\n"
        f"[FFMPEGA] ⬇️  Downloading {name}{suffix} (~{size})...\n"
        f"[FFMPEGA]    This is a one-time download. "
        f"Progress may appear below.\n"
    )
    print(msg, flush=True)
    log.info("Downloading %s%s (~%s)...", name, suffix, size)


def log_download_complete(model_key: str, path: str = "") -> None:
    """Print a console banner when a model download finishes.

    Args:
        model_key: Registry key.
        path: Path where the model was saved (optional).
    """
    info = _MODEL_INFO.get(model_key, {"name": model_key})
    name = info["name"]
    path_str = f" → {path}" if path else ""
    msg = f"[FFMPEGA] ✅ {name} downloaded successfully{path_str}\n"
    print(msg, flush=True)
    log.info("%s download complete%s", name, path_str)


def download_with_progress(model_key: str, download_fn, extra: str = ""):
    """Wrap a download callable with start/complete console logging.

    Usage::

        path = download_with_progress(
            "sam3",
            lambda: hf_hub_download(repo_id=..., filename=...),
        )

    Args:
        model_key: Registry key for log messages.
        download_fn: Callable that performs the download and returns a result.
        extra: Optional extra label (e.g. "large-v3").

    Returns:
        Whatever download_fn returns.
    """
    import time
    log_download_start(model_key, extra)
    t0 = time.time()
    try:
        result = download_fn()
    except Exception:
        elapsed = time.time() - t0
        info = _MODEL_INFO.get(model_key, {"name": model_key})
        print(
            f"[FFMPEGA] ❌ {info['name']} download failed after {elapsed:.1f}s\n",
            flush=True,
        )
        raise
    elapsed = time.time() - t0
    path_str = str(result) if result else ""
    info = _MODEL_INFO.get(model_key, {"name": model_key})
    msg = f"[FFMPEGA] ✅ {info['name']} downloaded in {elapsed:.1f}s"
    if path_str:
        msg += f" → {path_str}"
    print(msg + "\n", flush=True)
    log.info("%s download complete in %.1fs", info["name"], elapsed)
    return result
