# coding: utf-8
"""Values shared by the widget modules that are not plain literals.

The sampler and scheduler lists mirror what agent_node.py computed at import
time: ComfyUI's own lists when available, otherwise a fixed fallback so the
dropdowns still populate outside ComfyUI (tests, tooling).
"""

from __future__ import annotations

try:
    import comfy.samplers  # type: ignore[import-not-found]
    _svi_samplers = comfy.samplers.KSampler.SAMPLERS
    _svi_schedulers = comfy.samplers.KSampler.SCHEDULERS
except (ImportError, AttributeError):
    _svi_samplers = ["euler", "euler_ancestral", "dpmpp_2m", "dpmpp_2m_sde", "dpmpp_sde", "uni_pc"]
    _svi_schedulers = ["normal", "karras", "exponential", "sgm_uniform", "simple", "ddim_uniform", "beta"]


def get_expression_presets() -> list[str]:
    """List available LivePortrait expression preset names for the dropdown."""
    try:
        try:
            from core.expression_presets import list_expressions
        except ImportError:
            from ...core.expression_presets import list_expressions  # type: ignore
        return list_expressions()
    except Exception:
        return []
