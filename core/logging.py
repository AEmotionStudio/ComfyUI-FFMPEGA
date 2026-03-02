"""Structured logging setup for FFMPEGA.

Provides a JSON formatter for machine-readable logs and a convenience
``get_logger`` function that ensures all FFMPEGA loggers live under the
``ffmpega`` namespace.

Usage::

    from core.logging import get_logger
    log = get_logger(__name__)          # e.g. "ffmpega.pipeline_generator"
    log.info("Pipeline composed", extra={"skill_count": 5, "duration_ms": 42})

To enable JSON output (e.g. in production or CI)::

    from core.logging import setup_logging
    setup_logging(json_output=True)
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any


# ---------------------------------------------------------------------------
#  JSON Formatter
# ---------------------------------------------------------------------------


class JSONFormatter(logging.Formatter):
    """Emit log records as single-line JSON objects.

    Fields: ``timestamp``, ``level``, ``logger``, ``message``, plus any
    extra keys passed via ``extra={"key": value}``.
    """

    def format(self, record: logging.LogRecord) -> str:
        log_data: dict[str, Any] = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Merge extra fields (skip internal LogRecord attrs)
        _RESERVED = frozenset(logging.LogRecord("", 0, "", 0, "", (), None).__dict__)
        for key, value in record.__dict__.items():
            if key not in _RESERVED and key not in log_data:
                log_data[key] = value

        return json.dumps(log_data, default=str)


# ---------------------------------------------------------------------------
#  Setup
# ---------------------------------------------------------------------------

_CONFIGURED = False


def setup_logging(
    level: int = logging.INFO,
    json_output: bool | None = None,
) -> None:
    """Configure the ``ffmpega`` root logger.

    Args:
        level: Logging level (default ``INFO``).
        json_output: If ``True``, use JSON formatter.  If ``None`` (default),
            auto-detect from ``FFMPEGA_LOG_JSON=1`` env var.

    This is idempotent — calling it multiple times is safe.
    """
    global _CONFIGURED
    if _CONFIGURED:
        return
    _CONFIGURED = True

    if json_output is None:
        json_output = os.environ.get("FFMPEGA_LOG_JSON", "").strip() in ("1", "true")

    root = logging.getLogger("ffmpega")
    root.setLevel(level)

    if not root.handlers:
        handler = logging.StreamHandler()
        if json_output:
            handler.setFormatter(JSONFormatter())
        else:
            handler.setFormatter(logging.Formatter(
                "%(asctime)s [%(name)s] %(levelname)s: %(message)s",
                datefmt="%H:%M:%S",
            ))
        root.addHandler(handler)


# ---------------------------------------------------------------------------
#  Convenience
# ---------------------------------------------------------------------------


def get_logger(name: str) -> logging.Logger:
    """Return a logger under the ``ffmpega`` namespace.

    If *name* already starts with ``ffmpega``, it's returned as-is.
    Otherwise ``ffmpega.`` is prepended.  Module ``__name__`` values
    like ``core.pipeline_generator`` become ``ffmpega.pipeline_generator``.

    Args:
        name: Logger name (typically ``__name__``).

    Returns:
        A ``logging.Logger`` instance.
    """
    if name.startswith("ffmpega"):
        return logging.getLogger(name)

    # Strip common package prefixes for cleaner names
    for prefix in ("core.", "skills.", "nodes.", "mcp."):
        if name.startswith(prefix):
            name = name[len(prefix):]
            break

    return logging.getLogger(f"ffmpega.{name}")


class LogTimer:
    """Context manager that logs execution time.

    Usage::

        with LogTimer(log, "Pipeline execution"):
            execute_pipeline(...)
        # logs: "Pipeline execution completed in 1.234s"
    """

    def __init__(self, logger: logging.Logger, label: str, level: int = logging.INFO):
        self.logger = logger
        self.label = label
        self.level = level
        self._start: float = 0.0

    def __enter__(self) -> LogTimer:
        self._start = time.perf_counter()
        return self

    def __exit__(self, *exc_info: object) -> None:
        elapsed = time.perf_counter() - self._start
        self.logger.log(
            self.level,
            "%s completed in %.3fs",
            self.label,
            elapsed,
            extra={"duration_s": round(elapsed, 3)},
        )
