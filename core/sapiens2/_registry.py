# coding: utf-8
"""Sapiens2 task/size registry — pure data + validation.

No torch / no heavy ML imports.  Other modules in this subpackage rely
on this module for:
- the set of valid task names and size names
- the per-task dataset slug used in the upstream config filename
- the AEmotionStudio mirror repo for each task
- the local cache directory under ``ComfyUI/models/sapiens2/``
- the input resolution per size (1024x768 for everything except 1B-4K)
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Task descriptors
# ---------------------------------------------------------------------------

#: All sapiens2 tasks exposed by this integration.
TASKS: tuple[str, ...] = (
    "pose",
    "seg",
    "normal",
    "pointmap",
    "matting",
    "pretrain",
)

#: Tasks that use the dense-prediction pipeline (sapiens.dense.models.init_model).
DENSE_TASKS: frozenset[str] = frozenset({"seg", "normal", "pointmap", "matting"})

#: Tasks that need the DETR person detector.
DETECTOR_TASKS: frozenset[str] = frozenset({"pose"})

#: Tasks that don't need a config (use the standalone backbone directly).
RAW_BACKBONE_TASKS: frozenset[str] = frozenset({"pretrain"})


@dataclass(frozen=True)
class TaskSpec:
    """Static metadata for one Sapiens2 task family."""

    name: str
    # Dataset slug embedded in the upstream config filename.
    dataset: str
    # Subdirectory of ``sapiens/<subpkg>/configs/<dataset>/`` and of the
    # local cache root.  Same as ``name`` for every task today, but split
    # out for clarity.
    subdir: str
    # Sub-package the config lives under: "dense" or "pose".
    config_subpkg: str
    # The slug used inside the upstream config tree.  Almost always equal
    # to ``name`` (the task identifier we expose), but pose is the odd
    # one out: the config lives under ``pose/configs/keypoints308/...``
    # and the filename embeds ``keypoints308`` rather than ``pose``.
    config_slug: str
    # HuggingFace repo (AEmotionStudio mirror).
    mirror_repo: str
    # Upstream HuggingFace repo, used as a fallback if the mirror is empty.
    upstream_repo: str
    # Sizes that have a released checkpoint.
    supported_sizes: tuple[str, ...]


_TASK_SPECS: dict[str, TaskSpec] = {
    "pose": TaskSpec(
        name="pose",
        dataset="shutterstock_goliath_3po",
        subdir="pose",
        config_subpkg="pose",
        config_slug="keypoints308",
        mirror_repo="AEmotionStudio/sapiens2-pose",
        upstream_repo="facebook/sapiens2-pose",
        supported_sizes=("0.4b", "0.8b", "1b", "5b"),
    ),
    "seg": TaskSpec(
        name="seg",
        dataset="shutterstock_goliath",
        subdir="seg",
        config_subpkg="dense",
        config_slug="seg",
        mirror_repo="AEmotionStudio/sapiens2-seg",
        upstream_repo="facebook/sapiens2-seg",
        supported_sizes=("0.4b", "0.8b", "1b", "5b"),
    ),
    "normal": TaskSpec(
        name="normal",
        dataset="metasim_render_people",
        subdir="normal",
        config_subpkg="dense",
        config_slug="normal",
        mirror_repo="AEmotionStudio/sapiens2-normal",
        upstream_repo="facebook/sapiens2-normal",
        supported_sizes=("0.4b", "0.8b", "1b", "5b"),
    ),
    "pointmap": TaskSpec(
        name="pointmap",
        dataset="render_people",
        subdir="pointmap",
        config_subpkg="dense",
        config_slug="pointmap",
        mirror_repo="AEmotionStudio/sapiens2-pointmap",
        upstream_repo="facebook/sapiens2-pointmap",
        supported_sizes=("0.4b", "0.8b", "1b", "5b"),
    ),
    "matting": TaskSpec(
        name="matting",
        dataset="gss_p3m_metasim",
        subdir="matting",
        config_subpkg="dense",
        config_slug="matting",
        mirror_repo="AEmotionStudio/sapiens2-matting",
        upstream_repo="facebook/sapiens2-matting",
        # Meta only released matting for 1B.
        supported_sizes=("1b",),
    ),
    "pretrain": TaskSpec(
        name="pretrain",
        dataset="",  # no dataset / config — raw backbone
        subdir="pretrain",
        config_subpkg="",
        config_slug="",
        mirror_repo="AEmotionStudio/sapiens2-pretrain",
        upstream_repo="facebook/sapiens2-pretrain",
        # 1b_4k is mentioned in the README but no checkpoint has been
        # released on HF as of the May 2026 model release.  Add it back
        # to this tuple (and to _SIZE_TO_ARCH / _SIZE_TO_RESOLUTION) once
        # Meta publishes the file.
        supported_sizes=("0.1b", "0.4b", "0.8b", "1b", "5b"),
    ),
}


def get_task_spec(task: str) -> TaskSpec:
    """Return the :class:`TaskSpec` for ``task`` or raise ValueError."""
    if task not in _TASK_SPECS:
        raise ValueError(
            f"Unknown Sapiens2 task '{task}'. "
            f"Valid tasks: {sorted(_TASK_SPECS)}"
        )
    return _TASK_SPECS[task]


# ---------------------------------------------------------------------------
# Sizes
# ---------------------------------------------------------------------------

#: All sizes that the standalone backbone supports.
ALL_SIZES: tuple[str, ...] = ("0.1b", "0.4b", "0.8b", "1b", "5b")

#: Arch name expected by ``sapiens.backbones.standalone.sapiens2.Sapiens2``.
_SIZE_TO_ARCH: dict[str, str] = {
    "0.1b": "sapiens2_0.1b",
    "0.4b": "sapiens2_0.4b",
    "0.8b": "sapiens2_0.8b",
    "1b": "sapiens2_1b",
    "5b": "sapiens2_5b",
}

#: (H, W) input resolution per size.  All released checkpoints are
#: trained at 1024×768.  (Sapiens2-1B-4K at 4096×3072 is mentioned in the
#: paper but its checkpoint is not yet on HuggingFace as of May 2026.)
_SIZE_TO_RESOLUTION: dict[str, tuple[int, int]] = {
    "0.1b": (1024, 768),
    "0.4b": (1024, 768),
    "0.8b": (1024, 768),
    "1b": (1024, 768),
    "5b": (1024, 768),
}


def get_arch(size: str) -> str:
    """Return the standalone-backbone arch string for ``size``."""
    if size not in _SIZE_TO_ARCH:
        raise ValueError(
            f"Unknown Sapiens2 size '{size}'. "
            f"Valid sizes: {sorted(_SIZE_TO_ARCH)}"
        )
    return _SIZE_TO_ARCH[size]


def get_resolution(size: str) -> tuple[int, int]:
    """Return ``(H, W)`` input resolution for ``size``."""
    if size not in _SIZE_TO_RESOLUTION:
        raise ValueError(
            f"Unknown Sapiens2 size '{size}'. "
            f"Valid sizes: {sorted(_SIZE_TO_RESOLUTION)}"
        )
    return _SIZE_TO_RESOLUTION[size]


def validate_task_size(task: str, size: str) -> None:
    """Raise ValueError if ``(task, size)`` has no released checkpoint."""
    spec = get_task_spec(task)
    if size not in spec.supported_sizes:
        raise ValueError(
            f"Sapiens2 task '{task}' has no released checkpoint for size "
            f"'{size}'. Supported sizes for this task: "
            f"{list(spec.supported_sizes)}"
        )


# ---------------------------------------------------------------------------
# File-name conventions (matches the upstream HuggingFace repo layout)
# ---------------------------------------------------------------------------

def checkpoint_filename(task: str, size: str) -> str:
    """Return the canonical safetensors filename for ``(task, size)``.

    Examples:
        ``("pose", "1b")    -> "sapiens2_1b_pose.safetensors"``
        ``("pretrain", "5b") -> "sapiens2_5b_pretrain.safetensors"``
        ``("pretrain", "1b_4k") -> "sapiens2_1b_4k_pretrain.safetensors"``
    """
    validate_task_size(task, size)
    # Pretrain uses "1b_4k" verbatim; other tasks don't have a 4K variant.
    return f"sapiens2_{size}_{task}.safetensors"


def fp8_checkpoint_filename(task: str, size: str) -> str:
    """Return the fp8 variant filename, e.g. ``sapiens2_5b_normal_fp8.safetensors``.

    Produced offline by :mod:`._convert_fp8` and hosted on the same
    AEmotionStudio mirror as the fp32 checkpoint.
    """
    return checkpoint_filename(task, size).replace(
        ".safetensors", "_fp8.safetensors"
    )


def parse_size_selector(value: str) -> tuple[str, Optional[str]]:
    """Split a UI size string like ``'5b (fp8)'`` into ``(size, precision)``.

    The node's ``sapiens2_size`` dropdown folds the fp8 model choice into the
    size value via a ``' (fp8)'`` suffix, so the precision selection rides
    along with the size.  Bare sizes return ``precision_override=None`` and the
    caller falls back to ``'auto'``.

    Examples:
        ``"5b (fp8)" -> ("5b", "fp8")``
        ``"1b"       -> ("1b", None)``
    """
    v = (value or "").strip()
    if v.endswith("(fp8)"):
        return v[: -len("(fp8)")].strip(), "fp8"
    return v, None


def config_relpath(task: str, size: str) -> Optional[str]:
    """Return the config path *relative to the* ``sapiens`` package.

    None for tasks that don't use the config-driven pipeline (``pretrain``).

    Note: pose uses ``config_slug="keypoints308"`` rather than its task
    name in both the directory and the filename — see ``TaskSpec``.
    """
    spec = get_task_spec(task)
    if task in RAW_BACKBONE_TASKS:
        return None
    validate_task_size(task, size)
    return (
        f"{spec.config_subpkg}/configs/{spec.config_slug}/{spec.dataset}/"
        f"sapiens2_{size}_{spec.config_slug}_{spec.dataset}-1024x768.py"
    )


# ---------------------------------------------------------------------------
# Local cache layout
# ---------------------------------------------------------------------------

def _comfyui_models_root() -> Optional[Path]:
    """Locate ``ComfyUI/models/`` from the FFMPEGA install dir.

    We're at ``ComfyUI/custom_nodes/ComfyUI-FFMPEGA/core/sapiens2/``, so
    going up four levels lands on ``ComfyUI/``.  Returns ``None`` if the
    layout isn't recognizable so callers can fall back to a temp dir.
    """
    here = Path(__file__).resolve()
    # core/sapiens2/_registry.py → sapiens2/ → core/ → ComfyUI-FFMPEGA/
    #   → custom_nodes/ → ComfyUI/   (parents[4] is the ComfyUI root)
    for candidate in (here.parents[4] / "models",):
        if candidate.is_dir():
            return candidate
    return None


def cache_dir(task: str) -> Path:
    """Return the local cache directory for a task's checkpoints.

    Creates the directory if it doesn't exist.  Falls back to
    ``$XDG_CACHE_HOME/sapiens2/<task>`` if ``ComfyUI/models`` is not
    available.
    """
    spec = get_task_spec(task)
    root = _comfyui_models_root()
    if root is None:
        root = Path(
            os.environ.get(
                "XDG_CACHE_HOME", Path.home() / ".cache"
            )
        )
        base = root / "sapiens2" / spec.subdir
    else:
        base = root / "sapiens2" / spec.subdir
    base.mkdir(parents=True, exist_ok=True)
    return base


def detector_cache_dir() -> Path:
    """Return the local cache directory for the DETR person detector."""
    root = _comfyui_models_root()
    if root is None:
        root = Path(
            os.environ.get(
                "XDG_CACHE_HOME", Path.home() / ".cache"
            )
        )
    base = root / "sapiens2" / "detector" / "detr-resnet-101-dc5"
    base.mkdir(parents=True, exist_ok=True)
    return base


# ---------------------------------------------------------------------------
# Model manager key
# ---------------------------------------------------------------------------

#: Per-task model_manager._MODEL_INFO keys, used for the download guard.
MODEL_MANAGER_KEY: dict[str, str] = {
    "pose": "sapiens2_pose",
    "seg": "sapiens2_seg",
    "normal": "sapiens2_normal",
    "pointmap": "sapiens2_pointmap",
    "matting": "sapiens2_matting",
    "pretrain": "sapiens2_pretrain",
}
