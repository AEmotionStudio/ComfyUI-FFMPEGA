# coding: utf-8
"""Sapiens2 model loading + checkpoint resolution.

Three loaders, one for each kind of task:
- :func:`load_dense_model` for ``seg``/``normal``/``pointmap``/``matting``
- :func:`load_pose_model`  for ``pose``
- :func:`load_pretrain_backbone` for ``pretrain`` (no config)

A single-slot cache keeps the most recently loaded ``(task, size)``
warm.  Switching ``(task, size)`` evicts the previous model and frees
VRAM before loading the new one.
"""

from __future__ import annotations

import gc
import importlib
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import torch

from . import _fp8, _registry as reg

log = logging.getLogger("ffmpega")

#: Sizes for which "auto" precision prefers fp8 (the only one that doesn't
#: fit in fp16 on a typical 12 GB card).
_FP8_AUTO_SIZES: frozenset[str] = frozenset({"5b"})


# ---------------------------------------------------------------------------
# Cache state
# ---------------------------------------------------------------------------

@dataclass
class LoadedModel:
    """Container for whatever each loader returns + metadata for cache hits."""

    task: str
    size: str
    model: Any  # nn.Module — type varies per task family
    # Optional input resolution hint (for pretrain).
    input_resolution: Optional[tuple[int, int]] = None
    # Effective precision the model was loaded at (dense tasks only).
    precision: Optional[str] = None


_loaded: Optional[LoadedModel] = None


def get_cached(task: str, size: str) -> Optional[LoadedModel]:
    """Return the cached model iff it matches ``(task, size)``."""
    if _loaded is not None and _loaded.task == task and _loaded.size == size:
        return _loaded
    return None


def evict() -> None:
    """Free the cached model + run gc/empty_cache.

    Safe to call repeatedly.  Idempotent.
    """
    global _loaded
    if _loaded is None:
        return
    log.info("[Sapiens2] Unloading %s/%s", _loaded.task, _loaded.size)
    try:
        _loaded.model.to("cpu")
    except Exception:
        pass
    del _loaded.model
    _loaded = None
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


def _store(loaded: LoadedModel) -> None:
    global _loaded
    _loaded = loaded


# ---------------------------------------------------------------------------
# Sapiens package discovery (config + standalone backbone)
# ---------------------------------------------------------------------------

def _sapiens_package_root() -> Path:
    """Return the filesystem path to the installed ``sapiens`` package.

    Raises:
        ImportError: if ``sapiens`` is not importable.
    """
    try:
        import sapiens
    except ImportError as exc:
        raise ImportError(
            "Sapiens2 is not installed.  Run "
            "`pip install --no-deps git+https://github.com/facebookresearch/sapiens2.git` "
            "inside the ComfyUI venv (or run install.py)."
        ) from exc
    pkg_file = getattr(sapiens, "__file__", None)
    if not pkg_file:
        raise ImportError("Sapiens2: cannot locate sapiens package file")
    return Path(pkg_file).resolve().parent


def _resolve_config(task: str, size: str) -> str:
    """Resolve the on-disk path to the upstream sapiens config file."""
    rel = reg.config_relpath(task, size)
    if rel is None:
        raise ValueError(
            f"Sapiens2: task '{task}' has no config (uses raw backbone)"
        )
    cfg_path = _sapiens_package_root() / rel
    if not cfg_path.is_file():
        raise FileNotFoundError(
            f"Sapiens2: config not found at {cfg_path}.  Expected the "
            f"sapiens package layout to include "
            f"'{rel}'.  Reinstall sapiens or check that the install is "
            f"complete."
        )
    return str(cfg_path)


# ---------------------------------------------------------------------------
# Checkpoint download
# ---------------------------------------------------------------------------

def _require_downloads_allowed(task: str) -> None:
    """Defer to ``core.model_manager``'s global download guard."""
    try:
        from ..model_manager import require_downloads_allowed
    except ImportError:
        from core.model_manager import require_downloads_allowed  # type: ignore
    key = reg.MODEL_MANAGER_KEY.get(task)
    if key is None:
        # Defensive — registry should always cover every TASKS entry.
        raise RuntimeError(
            f"Sapiens2: no model_manager key registered for task '{task}'"
        )
    require_downloads_allowed(key)


def _hf_download(repo: str, filename: str, dest_dir: Path) -> Optional[str]:
    """Try to download ``filename`` from HuggingFace repo ``repo``.

    Returns the local path on success, ``None`` on failure (so the caller
    can fall back to the upstream repo).  We catch broadly because
    huggingface_hub raises a variety of exception types depending on
    whether the repo is missing, the file is missing, or auth fails.
    """
    try:
        from huggingface_hub import hf_hub_download
    except ImportError as exc:
        raise ImportError(
            "Sapiens2: huggingface_hub is required to download "
            "checkpoints.  It should already be present in the ComfyUI "
            "venv — try `pip install huggingface_hub`."
        ) from exc

    try:
        path = hf_hub_download(
            repo_id=repo,
            filename=filename,
            local_dir=str(dest_dir),
        )
        return path
    except Exception as exc:
        log.warning(
            "[Sapiens2] HF download from %s/%s failed: %s",
            repo, filename, exc,
        )
        return None


def resolve_checkpoint(task: str, size: str, *, fp8: bool = False) -> str:
    """Return a local path to the safetensors checkpoint for ``(task, size)``.

    With ``fp8=True`` the pre-quantized ``*_fp8.safetensors`` variant is
    resolved instead of the fp32 file (the upstream ``facebook`` repo has
    no fp8 file, so only the mirror is tried for it).

    Lookup order:
        1. ``ComfyUI/models/sapiens2/<task>/<filename>`` if it already exists.
        2. AEmotionStudio mirror.
        3. Upstream ``facebook/sapiens2-<task>`` repo (fp32 only).

    Raises:
        FileNotFoundError: if no source yields the checkpoint.
        RuntimeError: if downloads are disabled via the model_manager
            guard and no local copy exists.
    """
    spec = reg.get_task_spec(task)
    filename = (
        reg.fp8_checkpoint_filename(task, size) if fp8
        else reg.checkpoint_filename(task, size)
    )
    local_dir = reg.cache_dir(task)
    local_path = local_dir / filename

    if local_path.is_file():
        log.info("[Sapiens2] Using local checkpoint: %s", local_path)
        return str(local_path)

    _require_downloads_allowed(task)

    # The fp8 variant only exists on our mirror; upstream has fp32 only.
    repos = (spec.mirror_repo,) if fp8 else (spec.mirror_repo, spec.upstream_repo)
    for repo in repos:
        log.info("[Sapiens2] Trying HF repo %s for %s", repo, filename)
        path = _hf_download(repo, filename, local_dir)
        if path is not None and os.path.isfile(path):
            log.info("[Sapiens2] Downloaded %s → %s", filename, path)
            return path

    raise FileNotFoundError(
        f"Sapiens2: could not obtain checkpoint '{filename}' from "
        f"{', '.join(repos)!r}.  Place the file under {local_dir}/ "
        f"manually" + (
            " (or run `python -m core.sapiens2._convert_fp8` to create it "
            "from the fp32 checkpoint)" if fp8 else ""
        ) + " or check your HuggingFace auth."
    )


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

def _get_device() -> torch.device:
    try:
        import comfy.model_management as mm  # type: ignore[import-not-found]
        return mm.get_torch_device()
    except (ImportError, AttributeError):
        if torch.cuda.is_available():
            return torch.device("cuda")
        return torch.device("cpu")


def _free_other_synthesizers() -> None:
    """Ask other synthesizers to release VRAM, then run gc/empty_cache."""
    try:
        from .._vram_utils import free_for_module
    except ImportError:
        from core._vram_utils import free_for_module  # type: ignore
    free_for_module(exclude="sapiens2_synthesizer")


def _resolve_precision(size: str, precision: str) -> str:
    """Map the user's precision choice to a concrete mode.

    ``"auto"`` → ``"fp8"`` for the 5B model on an fp8-capable GPU (the
    only size that doesn't fit in fp16 on a 12 GB card), otherwise the
    upstream ``"fp32"`` path.  ``"fp8"`` always tries fp8 but transparently
    falls back to ``"bf16"`` if the GPU lacks native fp8 matmul.
    """
    precision = (precision or "auto").lower()
    if precision not in ("auto", "fp32", "bf16", "fp8"):
        raise ValueError(
            f"Sapiens2: unknown precision {precision!r} "
            "(expected auto/fp32/bf16/fp8)"
        )
    if precision == "auto":
        if size in _FP8_AUTO_SIZES and _fp8.supports_fp8_matmul():
            return "fp8"
        return "fp32"
    if precision == "fp8" and not _fp8.supports_fp8_matmul():
        log.warning(
            "[Sapiens2] fp8 requested but GPU lacks native fp8 matmul "
            "(needs compute capability >= 8.9); falling back to bf16."
        )
        return "bf16"
    return precision


def _build_dense_skeleton(config_path: str):
    """Build a dense model architecture on the meta device (no weights).

    Mirrors the front half of upstream ``init_model`` but under
    ``accelerate.init_empty_weights()`` so no 20 GB fp32 allocation
    happens.  Returns ``(model, config, data_preprocessor)``.
    """
    from accelerate import init_empty_weights
    from sapiens.engine.config import Config
    from sapiens.engine.datasets import Compose
    from sapiens.registry import MODELS

    config = Config.fromfile(config_path)
    if "init_cfg" in config.model["backbone"]:
        config.model["backbone"].pop("init_cfg")

    with init_empty_weights():
        model = MODELS.build(config.model)

    data_preprocessor = MODELS.build(config.data_preprocessor)
    model.cfg = config
    model.data_preprocessor = data_preprocessor
    model.pipeline = Compose(config.test_pipeline)
    return model


def _init_model_fp8(config_path: str, fp8_ckpt_path: str, device: torch.device):
    """Load a dense model from a pre-quantized fp8 checkpoint.

    The backbone Linear weights stay in ``float8_e4m3fn`` and run through
    ``torch._scaled_mm`` (see :mod:`._fp8`); everything else is bf16.  Peak
    GPU memory is ~5 GB instead of ~20 GB.
    """
    from safetensors.torch import load_file

    model = _build_dense_skeleton(config_path)

    state = load_file(fp8_ckpt_path, device="cpu")
    scales = _fp8.extract_scale_weights(state)  # pops "<name>.weight.scale"

    incompat = model.load_state_dict(state, strict=False, assign=True)
    if incompat.missing_keys:
        log.warning(
            "[Sapiens2] fp8 load: %d missing keys (e.g. %s)",
            len(incompat.missing_keys), incompat.missing_keys[:3],
        )
    if incompat.unexpected_keys:
        log.warning(
            "[Sapiens2] fp8 load: %d unexpected keys (e.g. %s)",
            len(incompat.unexpected_keys), incompat.unexpected_keys[:3],
        )

    # Safety net: any param/buffer still on meta (not covered by the
    # checkpoint) would crash .to(device) — materialize as zeros + warn.
    _materialize_leftover_meta(model)

    model.to(device)
    model.eval()

    _fp8.attach_scale_weights(model, scales)
    _fp8.convert_fp8_linear(model, torch.bfloat16)
    return model


def _materialize_leftover_meta(model) -> None:
    """Replace any remaining meta params/buffers with real zeros (defensive)."""
    n = 0
    for mod in model.modules():
        for name, p in list(mod.named_parameters(recurse=False)):
            if p.is_meta:
                mod.register_parameter(
                    name,
                    torch.nn.Parameter(
                        torch.zeros(p.shape, dtype=torch.bfloat16),
                        requires_grad=False,
                    ),
                )
                n += 1
        for name, b in list(mod.named_buffers(recurse=False)):
            if b is not None and b.is_meta:
                mod.register_buffer(
                    name, torch.zeros(b.shape, dtype=torch.bfloat16)
                )
                n += 1
    if n:
        log.warning(
            "[Sapiens2] fp8 load: materialized %d meta tensor(s) as zeros — "
            "checkpoint may be incomplete", n,
        )


def _init_model_bf16(config_path: str, ckpt_path: str, device: torch.device):
    """Load the fp32 checkpoint on CPU, cast to bf16, then move to GPU.

    ~10 GB on the GPU.  Staged through CPU so the 5B model never has to
    exist as 20 GB on the GPU.
    """
    init_module = importlib.import_module("sapiens.dense.models")
    init_model = getattr(init_module, "init_model")
    model = init_model(config_path, ckpt_path, device="cpu")
    model = model.to(torch.bfloat16)
    model.to(device)
    model.eval()
    return model


def load_dense_model(
    task: str, size: str, precision: str = "auto"
) -> LoadedModel:
    """Load a dense-task model via ``sapiens.dense.models.init_model``.

    ``precision`` is one of ``auto`` / ``fp32`` / ``bf16`` / ``fp8``.
    Reuses the cached model if ``(task, size, precision)`` matches.
    """
    reg.validate_task_size(task, size)
    if task not in reg.DENSE_TASKS:
        raise ValueError(f"Sapiens2: '{task}' is not a dense task")

    eff = _resolve_precision(size, precision)

    cached = get_cached(task, size)
    if cached is not None and getattr(cached, "precision", None) == eff:
        return cached

    evict()
    _free_other_synthesizers()

    config_path = _resolve_config(task, size)
    device = _get_device()

    log.info(
        "[Sapiens2] Loading dense model task=%s size=%s precision=%s on %s",
        task, size, eff, device,
    )

    if eff == "fp8":
        try:
            fp8_ckpt = resolve_checkpoint(task, size, fp8=True)
        except FileNotFoundError:
            if precision == "fp8":
                raise
            log.warning(
                "[Sapiens2] No fp8 checkpoint for %s/%s; falling back to bf16.",
                task, size,
            )
            eff = "bf16"
        else:
            model = _init_model_fp8(config_path, fp8_ckpt, device)

    if eff == "bf16":
        ckpt_path = resolve_checkpoint(task, size)
        model = _init_model_bf16(config_path, ckpt_path, device)
    elif eff == "fp32":
        ckpt_path = resolve_checkpoint(task, size)
        init_module = importlib.import_module("sapiens.dense.models")
        init_model = getattr(init_module, "init_model", None)
        if init_model is None:
            raise ImportError(
                "Sapiens2: 'sapiens.dense.models.init_model' missing — "
                "incompatible sapiens version?"
            )
        model = init_model(config_path, ckpt_path, device=str(device))
        model.eval()

    loaded = LoadedModel(task=task, size=size, model=model, precision=eff)
    _store(loaded)
    return loaded


def load_pose_model(task: str, size: str) -> LoadedModel:
    """Load a pose-task model via ``sapiens.pose.models.init_model``."""
    cached = get_cached(task, size)
    if cached is not None:
        return cached

    if task != "pose":
        raise ValueError(f"Sapiens2: load_pose_model called with task={task!r}")
    reg.validate_task_size(task, size)

    evict()
    _free_other_synthesizers()

    config_path = _resolve_config(task, size)
    ckpt_path = resolve_checkpoint(task, size)
    device = _get_device()

    try:
        init_module = importlib.import_module("sapiens.pose.models")
    except ImportError as exc:
        raise ImportError(
            "Sapiens2: 'sapiens.pose.models' is unavailable.  Reinstall "
            "the sapiens package."
        ) from exc

    init_model = getattr(init_module, "init_model", None)
    if init_model is None:
        raise ImportError(
            "Sapiens2: 'sapiens.pose.models.init_model' missing — "
            "incompatible sapiens version?"
        )

    log.info(
        "[Sapiens2] Loading pose model task=%s size=%s on %s",
        task, size, device,
    )
    model = init_model(config_path, ckpt_path, device=str(device))
    model.eval()

    # Attach pose metadata + codec (matches sapiens vis_pose.py).
    try:
        from sapiens.pose.datasets import parse_pose_metainfo, UDPHeatmap
    except ImportError as exc:
        raise ImportError(
            "Sapiens2: 'sapiens.pose.datasets' is unavailable."
        ) from exc

    num_keypoints = getattr(model.cfg, "num_keypoints", 308)
    if num_keypoints == 308:
        kp_cfg = _sapiens_package_root() / "pose" / "configs" / "_base_" / "keypoints308.py"
        model.pose_metainfo = parse_pose_metainfo(dict(from_file=str(kp_cfg)))
    else:
        # Defensive — should never trigger with the released checkpoints.
        log.warning(
            "[Sapiens2] Unexpected num_keypoints=%s; skeleton overlay may be blank",
            num_keypoints,
        )
        model.pose_metainfo = {
            "skeleton_links": [],
            "keypoint_colors": (255, 0, 0),
            "skeleton_link_colors": (0, 255, 0),
        }

    codec_cfg = dict(model.cfg.codec)  # copy so we don't mutate the cfg
    codec_type = codec_cfg.pop("type")
    if codec_type != "UDPHeatmap":
        raise RuntimeError(
            f"Sapiens2: unexpected pose codec '{codec_type}', expected "
            f"'UDPHeatmap'"
        )
    model.codec = UDPHeatmap(**codec_cfg)

    loaded = LoadedModel(task=task, size=size, model=model)
    _store(loaded)
    return loaded


def load_pretrain_backbone(size: str) -> LoadedModel:
    """Load the standalone Sapiens2 backbone for the ``pretrain`` task."""
    cached = get_cached("pretrain", size)
    if cached is not None:
        return cached

    reg.validate_task_size("pretrain", size)

    evict()
    _free_other_synthesizers()

    try:
        from sapiens.backbones.standalone.sapiens2 import Sapiens2
    except ImportError as exc:
        raise ImportError(
            "Sapiens2: standalone backbone import failed.  Reinstall the "
            "sapiens package."
        ) from exc
    try:
        from safetensors.torch import load_file
    except ImportError as exc:
        raise ImportError(
            "Sapiens2: 'safetensors' is required.  It should be present "
            "in the ComfyUI venv."
        ) from exc

    arch = reg.get_arch(size)
    H, W = reg.get_resolution(size)
    device = _get_device()

    log.info(
        "[Sapiens2] Loading pretrain backbone arch=%s img=%dx%d on %s",
        arch, H, W, device,
    )

    # ``out_type="featmap"`` makes the backbone return ``(B, C, h, w)``
    # directly — it strips the CLS + register tokens (defaults: 1 + 8 = 9
    # extra non-spatial tokens) so callers don't have to.
    model = Sapiens2(
        arch=arch, img_size=(H, W), patch_size=16, out_type="featmap",
    ).eval()
    ckpt_path = resolve_checkpoint("pretrain", size)
    state = load_file(ckpt_path, device="cpu")
    incompat = model.load_state_dict(state, strict=False)
    if incompat.missing_keys:
        log.warning(
            "[Sapiens2] pretrain backbone missing %d keys (first 5: %s)",
            len(incompat.missing_keys), incompat.missing_keys[:5],
        )
    if incompat.unexpected_keys:
        log.warning(
            "[Sapiens2] pretrain backbone unexpected %d keys (first 5: %s)",
            len(incompat.unexpected_keys), incompat.unexpected_keys[:5],
        )

    # Move to device.  Use fp16 for >=1B sizes on CUDA to fit comfortably
    # in 6–8 GB cards; smaller models stay fp32 for accuracy.
    if device.type == "cuda" and size not in {"0.1b", "0.4b"}:
        model = model.half()
    model = model.to(device)

    loaded = LoadedModel(
        task="pretrain",
        size=size,
        model=model,
        input_resolution=(H, W),
    )
    _store(loaded)
    return loaded
