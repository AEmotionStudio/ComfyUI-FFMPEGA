"""Programmatic Tool Calling (PTC) executor for FFMPEGA.

Executes LLM-generated Python orchestration code in a restricted
sandbox.  Only explicitly allowed tool functions, ``json``, and
``print`` are available — ``import``, ``open``, ``eval``, ``exec``,
and all other builtins are removed.

Inspired by Anthropic's Programmatic Tool Calling pattern, but
implemented model-agnostically so it works with any LLM provider.
"""

import io
import json
import logging
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

logger = logging.getLogger("ffmpega")


@dataclass
class PTCResult:
    """Result of a PTC execution."""

    stdout: str = ""
    success: bool = True
    error: Optional[str] = None
    error_type: Optional[str] = None
    frame_paths: list = field(default_factory=list)


class PTCExecutor:
    """Execute LLM-generated orchestration code in a restricted sandbox.

    The sandbox strips ``__builtins__`` entirely so the code cannot
    ``import``, ``open``, ``eval``, or ``exec`` anything.  Only the
    tool functions passed in *tool_handlers*, the ``json`` stdlib
    module, and a captured ``print`` are injected into the namespace.

    Args:
        tool_handlers: Mapping of tool-name → callable.  Each callable
            accepts the same arguments as the corresponding MCP tool
            (keyword arguments).
        timeout: Maximum wall-clock seconds before the execution is
            forcibly terminated.
    """

    # Minimal safe builtins needed for basic Python operations
    # (loops, list comprehensions, dict construction, etc.)
    _SAFE_BUILTINS = {
        # Types & constructors
        "True": True,
        "False": False,
        "None": None,
        "int": int,
        "float": float,
        "str": str,
        "bool": bool,
        "list": list,
        "dict": dict,
        "tuple": tuple,
        "set": set,
        "frozenset": frozenset,
        "bytes": bytes,
        "bytearray": bytearray,
        # Iteration & sequences
        "range": range,
        "len": len,
        "enumerate": enumerate,
        "zip": zip,
        "map": map,
        "filter": filter,
        "reversed": reversed,
        "sorted": sorted,
        "min": min,
        "max": max,
        "sum": sum,
        "any": any,
        "all": all,
        "abs": abs,
        "round": round,
        # String & repr
        "repr": repr,
        "isinstance": isinstance,
        "type": type,
        "hasattr": hasattr,
        "getattr": getattr,
        # Exceptions (so try/except works)
        "Exception": Exception,
        "ValueError": ValueError,
        "TypeError": TypeError,
        "KeyError": KeyError,
        "IndexError": IndexError,
        "RuntimeError": RuntimeError,
        "StopIteration": StopIteration,
        "ZeroDivisionError": ZeroDivisionError,
        "AttributeError": AttributeError,
        "LookupError": LookupError,
        "ArithmeticError": ArithmeticError,
        "OverflowError": OverflowError,
        "NotImplementedError": NotImplementedError,
    }

    def __init__(
        self,
        tool_handlers: dict[str, Callable],
        timeout: float = 30.0,
    ):
        self.tool_handlers = dict(tool_handlers)
        self.timeout = timeout

    def execute(self, code: str) -> PTCResult:
        """Run *code* in the sandbox, returning captured stdout.

        Args:
            code: Python source code to execute.

        Returns:
            A :class:`PTCResult` with stdout, success flag, and error
            details (if any).
        """
        if not code or not code.strip():
            return PTCResult(success=False, error="Empty code", error_type="ValueError")

        captured = io.StringIO()

        # Build the restricted global namespace
        allowed_globals: dict[str, Any] = {
            "__builtins__": dict(self._SAFE_BUILTINS),
            "json": json,
            "print": lambda *args, **kwargs: print(
                *args, file=captured, **kwargs
            ),
        }

        # Inject tool handlers as top-level callable functions
        for name, handler in self.tool_handlers.items():
            allowed_globals[name] = handler

        # Execute with timeout
        _collected_frame_paths: list[str] = []
        allowed_globals["_collected_frame_paths"] = _collected_frame_paths
        result = PTCResult()
        exec_error: Optional[BaseException] = None

        def _run():
            nonlocal exec_error
            try:
                exec(code, allowed_globals)  # noqa: S102
            except Exception as exc:
                exec_error = exc

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()
        thread.join(timeout=self.timeout)

        if thread.is_alive():
            # Timeout — the thread is a daemon so it will be cleaned up
            result.success = False
            result.error = (
                f"Execution timed out after {self.timeout}s. "
                "The code may contain an infinite loop."
            )
            result.error_type = "TimeoutError"
            logger.warning("PTC execution timed out after %.1fs", self.timeout)
            return result

        if exec_error is not None:
            result.success = False
            error_msg = str(exec_error)
            result.error_type = type(exec_error).__name__

            # Add helpful hints for common sandbox errors
            if isinstance(exec_error, ImportError) or (
                isinstance(exec_error, NameError)
                and "__import__" in error_msg
            ):
                error_msg += (
                    ". No imports are allowed — json and all tool "
                    "functions (search_skills, get_skill_details, "
                    "build_pipeline, etc.) are already available as "
                    "globals. Remove any import statements."
                )

            result.error = error_msg
            logger.warning("PTC execution error: %s: %s", result.error_type, result.error)
        
        result.stdout = captured.getvalue()
        result.frame_paths = list(_collected_frame_paths)
        return result
