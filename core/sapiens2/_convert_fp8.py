# coding: utf-8
"""Offline fp32 -> fp8 converter for Sapiens2 dense checkpoints.

The released ``sapiens2_5b_normal.safetensors`` is ~20 GB in fp32, which
does not fit on a 12 GB card.  This tool streams the checkpoint one
tensor at a time and writes a ~5 GB fp8 variant:

- Every 2D backbone Linear weight (``backbone.blocks.*.{attn,ffn}.*.weight``)
  is quantized to ``float8_e4m3fn`` with a per-output-channel scale
  stored alongside as ``<key>.weight.scale`` (fp32, shape ``(out,)``):

      scale[o]   = max(|W[o, :]|) / 448
      weight_fp8 = (W / scale[:, None]).clamp(-448, 448).to(float8_e4m3fn)

  These layers run natively through ``torch._scaled_mm`` at inference
  (see :mod:`._fp8`).
- Everything else (patch-embed conv, layer norms, layerscale, RoPE
  buffers, the entire Conv2d ``decode_head``, biases) is cast to bf16.

Streaming keeps peak RAM to roughly one tensor (~200 MB), so the
conversion runs comfortably even on machines that cannot hold the full
fp32 model in memory.

Usage (inside the ComfyUI venv)::

    python -m core.sapiens2._convert_fp8 \
        --task normal --size 5b [--input PATH] [--output PATH] \
        [--upload] [--repo AEmotionStudio/sapiens2-normal]

If ``--input`` is omitted, the fp32 checkpoint is resolved (and
downloaded if necessary) via the normal Sapiens2 checkpoint resolver.
``--upload`` pushes the produced file to the HuggingFace mirror (needs a
write token in the environment, e.g. ``HF_TOKEN`` or ``huggingface-cli
login``).
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import torch
from safetensors import safe_open
from safetensors.torch import save_file

from . import _registry as reg

log = logging.getLogger("ffmpega")

#: e4m3fn representable maximum magnitude (used for scaling).
_E4M3_MAX = 448.0


def fp8_filename(task: str, size: str) -> str:
    """Filename for the fp8 variant, e.g. ``sapiens2_5b_normal_fp8.safetensors``."""
    return reg.fp8_checkpoint_filename(task, size)


def _should_quantize(key: str, shape: tuple[int, ...]) -> bool:
    """True for the 2D backbone Linear weights we keep in fp8.

    The released dense checkpoints place *every* 2D tensor inside
    ``backbone.blocks.*`` (attention ``wq/wk/wv/proj`` and SwiGLU
    ``ffn.w12/w3``); the ``decode_head`` is entirely Conv2d (4D) and the
    norms / layerscale / biases are 1D.  We require both the 2D shape and
    the backbone-block prefix so a future checkpoint layout can't silently
    drag a head projection or embedding table into fp8.
    """
    return (
        len(shape) == 2
        and key.startswith("backbone.blocks.")
        and key.endswith(".weight")
    )


def _quantize_rowwise(w: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
    """Per-output-channel fp8 quantization of a 2D weight ``(out, in)``.

    Returns ``(weight_fp8, scale_fp32)`` where ``scale`` has shape
    ``(out,)`` and ``weight ~= weight_fp8.float() * scale[:, None]``.
    """
    w = w.float()
    scale = w.abs().amax(dim=1) / _E4M3_MAX          # (out,)
    scale = scale.clamp(min=1e-12)                   # avoid div-by-zero rows
    w_fp8 = (w / scale[:, None]).clamp(-_E4M3_MAX, _E4M3_MAX).to(torch.float8_e4m3fn)
    return w_fp8, scale.to(torch.float32)


def convert(input_path: Path, output_path: Path) -> dict:
    """Stream-convert *input_path* (fp32 safetensors) to fp8 at *output_path*.

    Returns a small stats dict.
    """
    out: dict[str, torch.Tensor] = {}
    n_quant = 0
    n_other = 0
    log.info("[Sapiens2] fp8 convert: %s -> %s", input_path, output_path)

    with safe_open(str(input_path), framework="pt", device="cpu") as f:
        keys = list(f.keys())
        for i, key in enumerate(keys):
            t = f.get_tensor(key)
            if _should_quantize(key, tuple(t.shape)):
                w_fp8, scale = _quantize_rowwise(t)
                out[key] = w_fp8
                out[f"{key}.scale"] = scale
                n_quant += 1
            else:
                out[key] = t.to(torch.bfloat16)
                n_other += 1
            del t
            if (i + 1) % 100 == 0:
                log.info("[Sapiens2]   %d/%d tensors", i + 1, len(keys))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    save_file(
        out,
        str(output_path),
        metadata={"format": "pt", "fp8_quant": "e4m3fn_rowwise"},
    )
    size_gb = output_path.stat().st_size / 1e9
    stats = {
        "quantized_linears": n_quant,
        "bf16_tensors": n_other,
        "output_size_gb": round(size_gb, 2),
    }
    log.info(
        "[Sapiens2] fp8 convert done: %d fp8 Linears, %d bf16 tensors, %.2f GB",
        n_quant, n_other, size_gb,
    )
    return stats


def upload(output_path: Path, repo_id: str) -> None:
    """Upload the produced fp8 file to a HuggingFace repo (needs write auth)."""
    from huggingface_hub import upload_file

    log.info("[Sapiens2] Uploading %s -> %s", output_path.name, repo_id)
    upload_file(
        path_or_fileobj=str(output_path),
        path_in_repo=output_path.name,
        repo_id=repo_id,
        commit_message=f"Add fp8 (e4m3fn, rowwise) variant: {output_path.name}",
    )
    log.info("[Sapiens2] Upload complete.")


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    p = argparse.ArgumentParser(description="Convert a Sapiens2 dense checkpoint to fp8.")
    p.add_argument("--task", default="normal")
    p.add_argument("--size", default="5b")
    p.add_argument("--input", default=None, help="fp32 .safetensors (default: resolve/download)")
    p.add_argument("--output", default=None, help="output fp8 .safetensors path")
    p.add_argument("--upload", action="store_true", help="upload result to the HF mirror")
    p.add_argument("--repo", default=None, help="override upload repo (default: task mirror)")
    args = p.parse_args(argv)

    if args.input is not None:
        input_path = Path(args.input)
        if not input_path.is_file():
            log.error("Input not found: %s", input_path)
            return 2
    else:
        # Defer import: _models pulls in torch-heavy deps only when needed.
        from . import _models
        input_path = Path(_models.resolve_checkpoint(args.task, args.size))

    if args.output is not None:
        output_path = Path(args.output)
    else:
        output_path = reg.cache_dir(args.task) / fp8_filename(args.task, args.size)

    convert(input_path, output_path)

    if args.upload:
        repo = args.repo or reg.get_task_spec(args.task).mirror_repo
        upload(output_path, repo)

    return 0


if __name__ == "__main__":
    sys.exit(main())
