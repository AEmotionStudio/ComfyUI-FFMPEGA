# coding: utf-8
"""Shared VRAM-budgeting helpers for ComfyUI-native ModelPatcher paths.

Block swapping here is not a custom offload engine — it leans on ComfyUI's own
lowvram partial loader. Inflating ``EXTRA_RESERVED_VRAM`` for the duration of
``prepare_sampling`` shrinks the weight budget that loader computes, so it
leaves that many bytes on the offload device and casts them per-layer on
forward. LoRA is applied at cast time and GGUF weights keep working, which a
hand-rolled offload would break.
"""

from __future__ import annotations

import logging

log = logging.getLogger("ffmpega")

# Wan 2.1 / 2.2 14B transformer depth — used only to size a fallback estimate
# when the patcher doesn't expose its blocks.
WAN_NUM_BLOCKS = 40


def register_blockswap(
    model_patcher,
    blocks_to_swap: int,
    *,
    key: str,
    label: str,
    num_blocks: int = WAN_NUM_BLOCKS,
) -> None:
    """Keep ~``blocks_to_swap`` transformer blocks' worth of weights off-GPU.

    Args:
        model_patcher: ComfyUI ModelPatcher to attach the wrapper to.
        blocks_to_swap: Number of blocks to keep off-GPU. <= 0 is a no-op.
        key: Unique wrapper key, so two models can register independently.
        label: Human-readable name used in the log line.
        num_blocks: Transformer depth, for the fallback size estimate.
    """
    if blocks_to_swap <= 0:
        return

    import comfy.model_management as mm  # type: ignore[import-not-found]
    import comfy.patcher_extension as pe  # type: ignore[import-not-found]

    try:
        blocks = model_patcher.model.diffusion_model.blocks
        swap_bytes = min(blocks_to_swap, len(blocks)) * mm.module_size(blocks[0])  # type: ignore[attr-defined]
    except AttributeError:
        swap_bytes = int(
            model_patcher.model_size()
            * min(blocks_to_swap, num_blocks) / num_blocks
        )

    def _wrapper(executor, *args, **kwargs):
        prev = mm.EXTRA_RESERVED_VRAM  # type: ignore[attr-defined]
        mm.EXTRA_RESERVED_VRAM = prev + int(swap_bytes)  # type: ignore[attr-defined]
        try:
            return executor(*args, **kwargs)
        finally:
            mm.EXTRA_RESERVED_VRAM = prev  # type: ignore[attr-defined]

    model_patcher.add_wrapper_with_key(pe.WrappersMP.PREPARE_SAMPLING, key, _wrapper)
    log.info(
        "%s blockswap: keeping ~%.0f MB (%d blocks) off-GPU",
        label, swap_bytes / 1024**2, blocks_to_swap,
    )
