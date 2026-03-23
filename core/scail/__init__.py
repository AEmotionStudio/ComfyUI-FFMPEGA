# coding: utf-8
"""SCAIL — Studio-Grade Character Animation via In-Context Learning.

Vendored from the SCAIL Wan branch (https://github.com/zai-org/SCAIL/tree/wan).
Stripped of distributed/FSDP/USP code for single-GPU ComfyUI usage.
Original license: Apache 2.0.
"""

from .pipeline import SCAILPipeline
from .configs import SCAIL_CONFIGS

__all__ = ["SCAILPipeline", "SCAIL_CONFIGS"]
