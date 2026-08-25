# coding: utf-8
"""Shared VRAM management utilities for FFMPEGA synthesizers.

Every synthesizer (FLUX Klein, LaMa, LivePortrait, MMAudio, MuseTalk,
SAM3, Marigold, VDA, Upscaler, MiniMax-Remover, SAM-Audio) needs to
free GPU VRAM before loading its own model.  The pattern is always the
same — but now we leverage ComfyUI's *official* memory APIs for smarter,
budget-aware eviction instead of the nuclear `unload_all_models()`:

1. Evict ComfyUI-managed models via ``comfy.model_management.free_memory``
2. Call ``cleanup()`` on every *other* FFMPEGA synthesizer module
3. ``soft_empty_cache()`` + ``gc.collect()``

This module provides that logic once, with a re-entrancy guard
(``_freeing_vram``) to prevent infinite recursion when synthesizer A
frees synthesizer B, which in turn tries to free synthesizer A.
"""

import gc
import logging
import sys

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
    "sam_audio_synthesizer",
    "normalcrafter_synthesizer",
    "acestep_synthesizer",
    "seedvr_synthesizer",
    "kiwi_edit_synthesizer",
    "facecam_synthesizer",
    "dreamid_omni_synthesizer",
    "fish_speech_synthesizer",
    "matanyone2_synthesizer",
    "flashvsr_synthesizer",
    "scail2_synthesizer",
    "audiox_synthesizer",
    "rtx_vsr_synthesizer",
    "foundation1_synthesizer",
    "phyfps_synthesizer",
    "svi_synthesizer",
    "wan_animate_synthesizer",
    "sharp_synthesizer",
    "sapiens2_synthesizer",
)

_freeing_vram = False


# ---------------------------------------------------------------------- #
#  ComfyUI API helpers                                                     #
# ---------------------------------------------------------------------- #

def _get_mm():
    """Import comfy.model_management, returns None if unavailable."""
    try:
        import comfy.model_management as mm  # type: ignore[import-not-found]
        return mm
    except (ImportError, AttributeError):
        return None


def get_device():
    """Return the current GPU device via ComfyUI, fallback to cuda:0."""
    mm = _get_mm()
    if mm:
        return mm.get_torch_device()
    import torch
    if torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


def get_free_memory(device=None):
    """Return free GPU memory in bytes using ComfyUI's accurate method.

    ComfyUI's get_free_memory includes both free CUDA memory AND
    PyTorch's cached-but-unused allocations, giving a more accurate
    picture than raw `torch.cuda.mem_get_info()`.
    """
    mm = _get_mm()
    if mm:
        return mm.get_free_memory(device)
    import torch
    if torch.cuda.is_available():
        return torch.cuda.mem_get_info(device)[0]
    return 0


def soft_empty_cache():
    """Cross-platform cache cleanup via ComfyUI's soft_empty_cache.

    Better than raw `torch.cuda.empty_cache()` because it:
    - Handles CUDA, MPS, XPU, NPU, MLU
    - Calls torch.cuda.synchronize() first (avoids race conditions)
    - Calls torch.cuda.ipc_collect() (reclaims shared memory)
    """
    mm = _get_mm()
    if mm:
        mm.soft_empty_cache()
    else:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()


def is_oom(exception) -> bool:
    """Check if an exception is an OOM error using ComfyUI's detection.

    Handles torch.cuda.OutOfMemoryError, torch.AcceleratorError,
    and string-matching fallback for "out of memory".
    """
    mm = _get_mm()
    if mm:
        return mm.is_oom(exception)  # type: ignore[attr-defined]
    return "out of memory" in str(exception).lower()


# ---------------------------------------------------------------------- #
#  Main VRAM freeing logic                                                 #
# ---------------------------------------------------------------------- #

def free_for_module(exclude: str = "", memory_needed: int = 0) -> None:
    """Free GPU VRAM on behalf of the calling synthesizer module.

    Args:
        exclude: Module base-name to skip (the caller itself),
                 e.g. ``"flux_klein_editor"``.  Pass ``""`` to clean
                 *all* synthesizers (e.g. from a top-level caller).
        memory_needed: Bytes of VRAM the caller needs.  When > 0, uses
                 ComfyUI's budget-aware ``free_memory()`` to evict only
                 what's necessary instead of the nuclear
                 ``unload_all_models()``.  Pass 0 to evict everything.

    The function is guarded against re-entrancy so that mutual
    ``cleanup()`` → ``_free_vram()`` → ``cleanup()`` chains terminate
    immediately.
    """
    global _freeing_vram
    if _freeing_vram:
        return
    _freeing_vram = True
    try:
        mm = _get_mm()
        device = get_device()

        # Step 1: Evict ComfyUI-managed models from VRAM
        if mm:
            if memory_needed > 0:
                # Budget-aware: only evict enough to free memory_needed
                mm.free_memory(memory_needed, device)  # type: ignore[attr-defined]
            else:
                # Nuclear fallback: evict everything
                mm.unload_all_models()
            mm.soft_empty_cache()

        # Also call platform helper if available
        try:
            from .platform import free_comfyui_vram
        except ImportError:
            try:
                from core.platform import free_comfyui_vram  # type: ignore
            except ImportError:
                free_comfyui_vram = None  # type: ignore[assignment]
        if free_comfyui_vram:
            free_comfyui_vram(memory_needed=memory_needed)

        # Step 2: Cleanup every other FFMPEGA synthesizer
        # Only clean modules already in sys.modules — a module that hasn't
        # been imported yet cannot have loaded a GPU model, so there's
        # nothing to free.  Using sys.modules avoids triggering a full
        # import (and loading heavy deps like torch/diffusers) for modules
        # the user never activated this session.
        #
        # Derive the package prefix from this module's own __name__ so
        # the lookup works regardless of how ComfyUI registered the
        # package (e.g. "core._vram_utils" vs
        # "custom_nodes.ComfyUI-FFMPEGA.core._vram_utils").
        _pkg = __name__.rsplit(".", 1)[0]  # e.g. "core" or full package path
        for mod_name in ALL_SYNTHESIZER_MODULES:
            if mod_name == exclude:
                continue
            mod = (
                sys.modules.get(f"{_pkg}.{mod_name}")
                or sys.modules.get(f"core.{mod_name}")
                or sys.modules.get(mod_name)
            )
            if mod is None:
                continue
            try:
                if hasattr(mod, "cleanup"):
                    mod.cleanup()
            except Exception:
                pass

        # Step 3: GC + cross-platform cache cleanup
        gc.collect()
        soft_empty_cache()

        if log.isEnabledFor(logging.INFO):
            free_mem = get_free_memory(device)
            log.info("[VRAM] GPU free after cleanup: %.2f GiB", free_mem / (1024**3))
    finally:
        _freeing_vram = False
