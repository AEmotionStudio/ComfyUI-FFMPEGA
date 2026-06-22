# coding: utf-8
"""Sapiens2 (Meta, ICLR 2026) integration for FFMPEGA.

Thin public entry point that re-exports the orchestrator API from the
``core.sapiens2`` subpackage.  The module name matches the
``*_synthesizer`` convention used by ``core._vram_utils`` so VRAM
eviction can find ``cleanup()`` via attribute lookup.

Provides the ``sapiens2`` no-LLM mode with six task families:

- ``pose``     — 308-keypoint top-down pose (body + face + hands + feet)
- ``seg``      — 29-class human body-part segmentation
- ``normal``   — surface normals
- ``pointmap`` — 3D pointmap (z-channel rendered as turbo colormap)
- ``matting``  — human matting (alpha + premult fgr, composited on green)
- ``pretrain`` — backbone features (PCA-visualized as RGB)

Models are loaded from the ``AEmotionStudio/sapiens2-*`` HuggingFace
mirrors with ``facebook/sapiens2-*`` as a fallback.

License:
    Sapiens2 / Meta Proprietary.  Not for surveillance, biometric
    identification, deepfake generation, or weapons / critical-
    infrastructure use.  Attribution required on publications.
"""

from .sapiens2 import run_sapiens2, cleanup

__all__ = ["run_sapiens2", "cleanup"]
