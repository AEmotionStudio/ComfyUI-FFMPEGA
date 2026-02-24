"""Programmatic Tool Calling (PTC) executor for FFMPEGA.

Executes LLM-generated Python orchestration code in a restricted
sandbox.  Only explicitly allowed tool functions, ``json``, and
``print`` are available — ``import``, ``open``, ``eval``, ``exec``,
and all other builtins are removed.

The sandbox also blocks Python object-model introspection via static
code analysis — patterns like ``__subclasses__``, ``__globals__``,
``__class__``, ``__code__``, ``os.``, ``subprocess.``, etc. are
rejected before execution starts.

Inspired by Anthropic's Programmatic Tool Calling pattern, but
implemented model-agnostically so it works with any LLM provider.
"""

import io
import json
import logging
import re
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

logger = logging.getLogger("ffmpega")

# Patterns that indicate sandbox escape attempts in code.
# Uses word boundaries (\b) for module names to avoid false positives
# on strings like "videos.mp4" or "chaos.dat".
_BLOCKED_PATTERNS = re.compile(
    # Dunder attributes used for object-model introspection
    r"__subclasses__|__globals__|__builtins__|__code__|__import__|"
    r"__loader__|__spec__|__cached__|__file__|__path__|__class__|"
    # Traceback frame traversal (sandbox escape via exception frames)
    r"__traceback__|tb_frame|f_back|f_builtins|f_locals|f_globals|"
    # Module access (word boundary prevents matching inside strings)
    r"\bos\.\b|\bsubprocess\.|\bsys\.|\bshutil\.|\bpathlib\.|"
    # Dangerous builtins (with parens to avoid matching variable names)
    r"\bopen\s*\(|\bexec\s*\(|\beval\s*\(|\bcompile\s*\(|"
    r"\bbreakpoint\s*\(|\bexit\s*\(|\bquit\s*\(",
)


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

    Additionally, dangerous dunder attributes are blocked via static
    analysis of the code before execution, and ``type`` / ``getattr``
    are removed from the builtins to prevent object-model introspection
    escapes.

    Args:
        tool_handlers: Mapping of tool-name → callable.  Each callable
            accepts the same arguments as the corresponding MCP tool
            (keyword arguments).
        timeout: Maximum wall-clock seconds before the execution is
            forcibly terminated.
    """

    # Minimal safe builtins needed for basic Python operations
    # (loops, list comprehensions, dict construction, etc.)
    # NOTE: type, getattr, hasattr are intentionally EXCLUDED to prevent
    # sandbox escapes via Python object-model introspection.
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

    @staticmethod
    def _check_code_safety(code: str) -> Optional[str]:
        """Static check for blocked patterns before execution.

        Returns an error message if blocked patterns are found, else None.
        """
        match = _BLOCKED_PATTERNS.search(code)
        if match:
            return (
                f"Blocked pattern detected: '{match.group()}'. "
                "Direct access to __subclasses__, __globals__, os, subprocess, "
                "open(), exec(), eval(), and similar is not permitted in the "
                "sandbox. Use the provided tool functions instead."
            )
        return None

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

        # Static safety check before execution
        safety_error = self._check_code_safety(code)
        if safety_error:
            return PTCResult(
                success=False,
                error=safety_error,
                error_type="SecurityError",
            )

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

        # Execute with timeout using a daemon thread
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

        # daemon=True ensures thread is killed when main thread exits
        thread = threading.Thread(target=_run, daemon=True)
        thread.start()
        thread.join(timeout=self.timeout)

        if thread.is_alive():
            # Timeout — daemon thread will be cleaned up on process exit
            result.success = False
            result.error = (
                f"Execution timed out after {self.timeout}s. "
                "The code may contain an infinite loop. "
                "The orphaned thread is a daemon and will be cleaned up "
                "when the process exits."
            )
            result.error_type = "TimeoutError"
            logger.warning(
                "PTC execution timed out after %.1fs (daemon thread will "
                "be cleaned up on process exit)",
                self.timeout,
            )
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
