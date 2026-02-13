"""Token usage tracker for LLM calls.

Accumulates token counts across agentic loop iterations and provides
summaries for console output, analysis embedding, and persistent logging.
"""

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("ffmpega")

# Rough chars-per-token ratio for estimation when native counts unavailable
_CHARS_PER_TOKEN = 4


@dataclass
class CallRecord:
    """Record of a single LLM call."""

    iteration: int
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    estimated: bool
    tool_calls: list[str] = field(default_factory=list)
    elapsed_sec: float = 0.0


class TokenTracker:
    """Accumulate token usage across an agentic loop run."""

    def __init__(self, model: str, provider: str) -> None:
        self.model = model
        self.provider = provider
        self.calls: list[CallRecord] = []
        self.start_time = time.time()
        self._tool_call_count = 0

    # ------------------------------------------------------------------ #
    #  Recording                                                          #
    # ------------------------------------------------------------------ #

    def record(
        self,
        response: "LLMResponse",  # noqa: F821 — forward ref
        iteration: int,
        tool_names: Optional[list[str]] = None,
        call_start: Optional[float] = None,
    ) -> None:
        """Record token usage from an LLMResponse.

        If the response has native token counts they are used directly.
        Otherwise, character-based estimation is applied and flagged.
        """
        estimated = False
        prompt_tokens = response.prompt_tokens or 0
        completion_tokens = response.completion_tokens or 0

        # Fallback: estimate from character length
        if not response.prompt_tokens and not response.completion_tokens:
            estimated = True
            # We don't have the prompt text here, so we estimate completion only
            prompt_tokens = 0  # will be filled if caller provides
            completion_tokens = self.estimate_tokens(response.content or "")

        total = prompt_tokens + completion_tokens

        elapsed = (time.time() - call_start) if call_start else 0.0

        if tool_names:
            self._tool_call_count += len(tool_names)

        self.calls.append(
            CallRecord(
                iteration=iteration,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total,
                estimated=estimated,
                tool_calls=tool_names or [],
                elapsed_sec=round(elapsed, 2),
            )
        )

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """Estimate token count from character length (~4 chars/token)."""
        if not text:
            return 0
        return max(1, len(text) // _CHARS_PER_TOKEN)

    # ------------------------------------------------------------------ #
    #  Summaries                                                          #
    # ------------------------------------------------------------------ #

    def summary(self) -> dict:
        """Return aggregated usage summary as a dict."""
        total_prompt = sum(c.prompt_tokens for c in self.calls)
        total_completion = sum(c.completion_tokens for c in self.calls)
        total_tokens = sum(c.total_tokens for c in self.calls)
        any_estimated = any(c.estimated for c in self.calls)
        elapsed = round(time.time() - self.start_time, 1)

        result: dict = {
            "model": self.model,
            "provider": self.provider,
            "total_prompt_tokens": total_prompt,
            "total_completion_tokens": total_completion,
            "total_tokens": total_tokens,
            "estimated": any_estimated,
            "llm_calls": len(self.calls),
            "tool_calls": self._tool_call_count,
            "elapsed_sec": elapsed,
        }

        if self.calls:
            result["per_call"] = [
                {
                    "iteration": c.iteration,
                    "prompt": c.prompt_tokens,
                    "completion": c.completion_tokens,
                    "total": c.total_tokens,
                    "estimated": c.estimated,
                    "tools": c.tool_calls,
                    "elapsed": c.elapsed_sec,
                }
                for c in self.calls
            ]

        return result

    # ------------------------------------------------------------------ #
    #  Persistent logging                                                  #
    # ------------------------------------------------------------------ #

    @staticmethod
    def append_to_log(entry: dict, log_dir: Optional[str] = None) -> None:
        """Append a log entry to usage_log.jsonl."""
        if log_dir is None:
            log_dir = str(Path(__file__).resolve().parent.parent)
        log_path = Path(log_dir) / "usage_log.jsonl"
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
            logger.debug("Token usage logged to %s", log_path)
        except OSError as exc:
            logger.warning("Failed to write usage log: %s", exc)
