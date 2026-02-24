"""Project-specific exception types for FFMPEGA.

All exceptions inherit from both the FFMPEGA base and a standard Python
exception so existing ``except ValueError`` / ``except RuntimeError``
catch blocks continue to work without modification.

Hierarchy::

    FFMPEGAError (RuntimeError)
    ├── ValidationError (FFMPEGAError, ValueError)   — bad input / path / param
    └── PipelineGenerationError (FFMPEGAError)       — LLM failed to produce pipeline
"""

from __future__ import annotations


class FFMPEGAError(RuntimeError):
    """Base class for all FFMPEGA errors."""


class ValidationError(FFMPEGAError, ValueError):
    """Raised when user-supplied input fails validation.

    Inherits from both ``FFMPEGAError`` and ``ValueError`` so existing
    callers that catch ``ValueError`` (e.g. ComfyUI's node runner) are
    unaffected.

    Examples
    --------
    - Path traversal attempt in a file path argument
    - Unsupported file extension for an output path
    - Empty prompt string
    """


class PipelineGenerationError(FFMPEGAError):
    """Raised when the LLM fails to produce a valid pipeline spec.

    Covers cases such as:
    - JSON parse failure after all retries
    - LLM returned an empty or unparseable response
    - All agentic loop iterations exhausted without a ``finalize`` call
    """
