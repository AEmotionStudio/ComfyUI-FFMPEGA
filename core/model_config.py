"""Model configuration loader for ComfyUI-FFMPEGA.

Reads ``config/models.yaml`` to provide the list of API-backed models shown
in the node dropdown.  Optionally performs a live fetch from provider APIs to
discover the freshest model names.

Usage::

    from core.model_config import load_api_models

    api_models = load_api_models()   # list[str], cached after first call
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Optional

logger = logging.getLogger("ffmpega")

# The config file lives at <project_root>/config/models.yaml
_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "models.yaml"


# ── YAML loader ─────────────────────────────────────────────────────────────

def _load_yaml(path: Path) -> dict:
    """Load *path* as YAML, falling back to an empty dict on any error."""
    try:
        import yaml  # type: ignore[import-not-found]
        with open(path) as f:
            return yaml.safe_load(f) or {}
    except ImportError:
        # PyYAML not installed — parse the simple list manually
        return _parse_simple_yaml(path)
    except Exception as exc:
        logger.warning("model_config: failed to load %s: %s", path, exc)
        return {}


def _parse_simple_yaml(path: Path) -> dict:
    """Minimal YAML parser for the models.yaml format (no PyYAML dependency).

    Handles the top-level ``api_models`` list and ``live_fetch.enabled`` flag
    without importing the full YAML library.
    """
    result: dict = {"api_models": [], "live_fetch": {"enabled": False}}
    try:
        with open(path) as f:
            lines = f.readlines()
    except Exception:
        return result

    in_api_models = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#") or not stripped:
            continue
        if stripped == "api_models:":
            in_api_models = True
            continue
        if stripped.endswith(":") and not stripped.startswith("-"):
            in_api_models = False
            continue
        if in_api_models and stripped.startswith("- "):
            model = stripped[2:].strip().strip("\"'")
            if model:
                result["api_models"].append(model)
        if "enabled:" in stripped and "live_fetch" not in stripped:
            val = stripped.split(":", 1)[1].strip().lower()
            result["live_fetch"]["enabled"] = val == "true"

    return result


# ── Live-fetch helpers ───────────────────────────────────────────────────────

def _fetch_openai_models(api_key: str, timeout: float) -> list[str]:
    """Fetch model IDs from OpenAI /v1/models that look like chat models."""
    try:
        import httpx  # type: ignore[import-not-found]
        with httpx.Client(timeout=timeout) as client:
            resp = client.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {api_key}"},
            )
            resp.raise_for_status()
            data = resp.json().get("data", [])
            # Filter for gpt-* models only (exclude embeddings, tts, etc.)
            models = sorted(
                m["id"] for m in data
                if isinstance(m.get("id"), str) and m["id"].startswith("gpt-")
            )
            logger.info("model_config: fetched %d OpenAI models", len(models))
            return models
    except Exception as exc:
        logger.warning("model_config: OpenAI live-fetch failed: %s", exc)
        return []


def _fetch_anthropic_models(api_key: str, timeout: float) -> list[str]:
    """Fetch model IDs from Anthropic /v1/models."""
    try:
        import httpx  # type: ignore[import-not-found]
        with httpx.Client(timeout=timeout) as client:
            resp = client.get(
                "https://api.anthropic.com/v1/models",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                },
            )
            resp.raise_for_status()
            data = resp.json().get("data", [])
            models = sorted(m["id"] for m in data if isinstance(m.get("id"), str))
            logger.info("model_config: fetched %d Anthropic models", len(models))
            return models
    except Exception as exc:
        logger.warning("model_config: Anthropic live-fetch failed: %s", exc)
        return []


# ── Public API ───────────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def load_api_models(
    config_path: Optional[str] = None,
    openai_key: Optional[str] = None,
    anthropic_key: Optional[str] = None,
) -> list[str]:
    """Return the list of API model names for the ComfyUI dropdown.

    Reads ``config/models.yaml`` and, if ``live_fetch.enabled`` is true,
    augments the result with fresh data from provider APIs.  The result is
    cached via :func:`functools.lru_cache` so the file is only read once per
    process — call :func:`invalidate_model_cache` to force a reload.

    Args:
        config_path: Override path to ``models.yaml``.  Defaults to the
            bundled ``config/models.yaml``.
        openai_key: OpenAI API key for live-fetch (falls back to
            ``OPENAI_API_KEY`` env var).
        anthropic_key: Anthropic API key for live-fetch (falls back to
            ``ANTHROPIC_API_KEY`` env var).

    Returns:
        Ordered list of model name strings.
    """
    path = Path(config_path) if config_path else _CONFIG_PATH
    cfg = _load_yaml(path)

    static_models: list[str] = cfg.get("api_models", [])
    if not isinstance(static_models, list):
        static_models = []

    live_cfg = cfg.get("live_fetch", {}) or {}
    live_enabled = bool(live_cfg.get("enabled", False))
    timeout = float(live_cfg.get("timeout_seconds", 5))
    providers: list[str] = live_cfg.get("providers", []) or []

    if not live_enabled:
        logger.debug(
            "model_config: live_fetch disabled — using %d static models",
            len(static_models),
        )
        return list(static_models)

    # ── Live-fetch mode ──────────────────────────────────────────────────────
    live_models: list[str] = []

    if "openai" in providers:
        key = openai_key or os.environ.get("OPENAI_API_KEY", "")
        if key:
            live_models.extend(_fetch_openai_models(key, timeout))
        else:
            logger.debug("model_config: OpenAI live-fetch skipped (no API key)")

    if "anthropic" in providers:
        key = anthropic_key or os.environ.get("ANTHROPIC_API_KEY", "")
        if key:
            live_models.extend(_fetch_anthropic_models(key, timeout))
        else:
            logger.debug("model_config: Anthropic live-fetch skipped (no API key)")

    if live_models:
        # Merge: live models first, then static fallbacks not already listed
        seen: set[str] = set(live_models)
        merged = list(live_models)
        for m in static_models:
            if m not in seen:
                merged.append(m)
                seen.add(m)
        logger.info(
            "model_config: %d live + %d static = %d total models",
            len(live_models), len(static_models), len(merged),
        )
        return merged

    # Live-fetch returned nothing — fall back to static list
    logger.warning(
        "model_config: live-fetch produced no models, using static list (%d)",
        len(static_models),
    )
    return list(static_models)


def invalidate_model_cache() -> None:
    """Clear the :func:`load_api_models` cache so the YAML is re-read on next call."""
    load_api_models.cache_clear()
    logger.info("model_config: cache invalidated")
