# coding: utf-8
"""Shared VRAM management utilities for FFMPEGA synthesizers.

Every synthesizer (FLUX Klein, LaMa, LivePortrait, MMAudio, MuseTalk,
SAM3, Marigold, VDA, Upscaler, MiniMax-Remover) needs to free GPU VRAM
before loading its own model.  The pattern is always the same:

1. Evict ComfyUI-managed models via ``comfy.model_management``
2. Call ``cleanup()`` on every *other* FFMPEGA synthesizer module
3. Empty CUDA cache + ``gc.collect()``

This module provides that logic once, with a re-entrancy guard
(``_freeing_vram``) to prevent infinite recursion when synthesizer A
frees synthesizer B, which in turn tries to free synthesizer A.
"""

import gc
import logging
import sys

import torch

log = logging.getLogger("ffmpega")

# Complete list of all synthesizer module names that have a ``cleanup()``
# function.  Order is irrelevant — all are iterated every time.
#
# IMPORTANT: When adding a new core/*.py synthesizer module that caches a
# GPU model and exposes a ``cleanup()`` function, you MUST add its base
# name here.  Otherwise it won't be freed when other modules need VRAM.
ALL_SYNTHESIZER_MODULES: tuple[str, ...] = (
    "liveportrait_synthesizer",
    "mmaudio_synthesizer",
    "musetalk_synthesizer",
    "sam3_masker",
    "flux_klein_editor",  # NB: not *_synthesizer — module is named flux_klein_editor
    "lama_inpainter",
    "marigold_synthesizer",
    "vda_synthesizer",
    "upscaler",
    "minimax_remover",
)

_freeing_vram = False


def free_for_module(exclude: str = "") -> None:
    """Free GPU VRAM on behalf of the calling synthesizer module.

    Args:
        exclude: Module base-name to skip (the caller itself),
                 e.g. ``"flux_klein_editor"``.  Pass ``""`` to clean
                 *all* synthesizers (e.g. from a top-level caller).

    The function is guarded against re-entrancy so that mutual
    ``cleanup()`` → ``_free_vram()`` → ``cleanup()`` chains terminate
    immediately.
    """
    global _freeing_vram
    if _freeing_vram:
        return
    _freeing_vram = True
    try:
        # Step 1: Evict all ComfyUI-managed models from VRAM
        try:
            import comfy.model_management as mm  # type: ignore[import-not-found]
            mm.unload_all_models()
            mm.soft_empty_cache()
        except (ImportError, AttributeError):
            pass

        try:
            from .platform import free_comfyui_vram
        except ImportError:
            try:
                from core.platform import free_comfyui_vram  # type: ignore
            except ImportError:
                free_comfyui_vram = None  # type: ignore[assignment]
        if free_comfyui_vram:
            free_comfyui_vram()

        # Step 2: Cleanup every other FFMPEGA synthesizer
        # Only clean modules already in sys.modules — a module that hasn't
        # been imported yet cannot have loaded a GPU model, so there's
        # nothing to free.  Using sys.modules avoids triggering a full
        # import (and loading heavy deps like torch/diffusers) for modules
        # the user never activated this session.
        for mod_name in ALL_SYNTHESIZER_MODULES:
            if mod_name == exclude:
                continue
            mod = sys.modules.get(f"core.{mod_name}") or sys.modules.get(mod_name)
            if mod is None:
                continue
            try:
                if hasattr(mod, "cleanup"):
                    mod.cleanup()
            except Exception:
                pass

        # Step 3: GC + CUDA cleanup
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

        if torch.cuda.is_available():
            free_mem = torch.cuda.mem_get_info()[0] / (1024**3)
            log.info("[VRAM] GPU free after cleanup: %.2f GiB", free_mem)
    finally:
        _freeing_vram = False
