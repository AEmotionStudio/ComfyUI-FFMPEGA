# coding: utf-8
"""Sapiens2 integration internals for FFMPEGA.

This subpackage holds the implementation details for the ``sapiens2``
no-LLM mode.  The public entry points (``run_sapiens2`` and ``cleanup``)
live in ``core.sapiens2_synthesizer`` so that ``_vram_utils`` can
discover the module via the standard ``*_synthesizer`` naming pattern.

Layout:
    _registry.py     pure-data task/size/config/checkpoint metadata
    _models.py       model loading + cache (dense, pose, pretrain backbone)
    _detector.py     DETR person detector (pose task only)
    _render.py       visualization helpers (vendored from sapiens vis tools)
    _io.py           video frame I/O
    _orchestrator.py per-task inference + post-processing

Public re-exports below are intended for the entry-point module only.
External callers should import from ``core.sapiens2_synthesizer``.
"""

from ._orchestrator import run_sapiens2, cleanup

__all__ = ["run_sapiens2", "cleanup"]
