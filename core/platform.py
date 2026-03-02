"""Platform abstraction — isolates ComfyUI-specific APIs.

All ComfyUI imports live here.  The rest of ``core/`` imports only from
this module, making offline testing and standalone usage possible
without mocking ComfyUI internals.

Public API:
    get_models_dir(subdir)   — ``folder_paths.models_dir`` replacement
    free_comfyui_vram()      — unload ComfyUI models + empty CUDA cache
    load_torch_file(path)    — ``comfy.utils.load_torch_file`` wrapper
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

log = logging.getLogger("ffmpega")

# Extension root: …/ComfyUI/custom_nodes/ComfyUI-FFMPEGA
_EXT_ROOT = Path(__file__).resolve().parent.parent


# ------------------------------------------------------------------ #
#  Model directory                                                     #
# ------------------------------------------------------------------ #


def get_models_dir(subdir: str = "") -> str:
    """Return ComfyUI's models directory, with optional subdirectory.

    Resolution order:
        1. ``folder_paths.models_dir``  (ComfyUI runtime)
        2. ``<extension_root>/models/`` (standalone / testing fallback)

    The directory is created if it doesn't exist.

    Args:
        subdir: Optional subdirectory under models/ (e.g. ``"mmaudio"``).

    Returns:
        Absolute path to the (sub)directory.
    """
    try:
        import folder_paths  # type: ignore[import-not-found]

        base: str = folder_paths.models_dir
    except (ImportError, AttributeError):
        base = str(_EXT_ROOT / "models")

    path = os.path.join(base, subdir) if subdir else base
    os.makedirs(path, exist_ok=True)
    return path


# ------------------------------------------------------------------ #
#  VRAM management                                                     #
# ------------------------------------------------------------------ #


def free_comfyui_vram() -> None:
    """Ask ComfyUI to unload cached models and free GPU memory.

    Safe to call outside ComfyUI — silently does nothing if the
    ``comfy`` package is unavailable.
    """
    try:
        import comfy.model_management  # type: ignore[import-not-found]

        comfy.model_management.unload_all_models()
        comfy.model_management.soft_empty_cache()
        log.debug("Freed ComfyUI GPU VRAM via model_management")
    except (ImportError, AttributeError):
        pass


# ------------------------------------------------------------------ #
#  Checkpoint loading                                                  #
# ------------------------------------------------------------------ #


def load_torch_file(path: str, device: str = "cpu", safe_load: bool = True):
    """Load a model checkpoint, preferring comfy.utils when available.

    Comfy's ``load_torch_file`` handles ``.safetensors`` natively and
    is the safest option inside ComfyUI.  Falls back to
    ``safetensors.torch.load_file`` / ``torch.load`` for standalone usage.

    Args:
        path: Absolute path to ``.pt`` / ``.safetensors`` file.
        device: Target device for the loaded tensors (e.g. ``"cpu"``,
            ``"cuda:0"``).  Forwarded to the underlying loader.
        safe_load: If ``True``, use ``weights_only=True`` in the
            ``torch.load`` fallback for security.

    Returns:
        State dict (``dict[str, Tensor]``).
    """
    try:
        from comfy.utils import load_torch_file as _comfy_load  # type: ignore[import-not-found]

        return _comfy_load(path, safe_load=safe_load)  # type: ignore[call-arg]
    except ImportError:
        pass

    if path.endswith(".safetensors"):
        from safetensors.torch import load_file

        return load_file(path, device=device)

    import torch

    return torch.load(path, map_location=device, weights_only=safe_load)
