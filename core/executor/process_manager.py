"""Process management for FFMPEG execution."""

import asyncio
import logging
import re
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Callable, AsyncIterator
from .command_builder import FFMPEGCommand
from core.bin_paths import get_ffmpeg_bin

logger = logging.getLogger("ffmpega")


@dataclass
class ProcessResult:
    """Result of an FFMPEG process execution."""
    success: bool
    return_code: int
    stdout: str
    stderr: str
    command: str
    duration: Optional[float] = None
    output_path: Optional[str] = None
    error_message: Optional[str] = None

    @property
    def output_size(self) -> Optional[int]:
        """Get output file size if available."""
        if self.output_path and Path(self.output_path).exists():
            return Path(self.output_path).stat().st_size
        return None


@dataclass
class ProgressInfo:
    """Progress information during FFMPEG execution."""
    frame: int = 0
    fps: float = 0.0
    time: float = 0.0
    bitrate: str = ""
    speed: str = ""
    size: int = 0
    progress_percent: float = 0.0


class ProcessManager:
    """Manages FFMPEG process execution with progress tracking."""

    def __init__(self, ffmpeg_path: Optional[str] = None):
        """Initialize process manager.

        Args:
            ffmpeg_path: Path to ffmpeg executable. If None, searches PATH.
        """
        self.ffmpeg_path = ffmpeg_path or get_ffmpeg_bin()
        if not self.ffmpeg_path:
            raise RuntimeError("ffmpeg not found in PATH")

        # Cancellation support
        self._active_proc: Optional[subprocess.Popen] = None
        self._active_async_proc = None  # asyncio.subprocess.Process, typed as Any
        self._cancel_lock = threading.Lock()
        self._cancelled = False

    def cancel(self) -> bool:
        """Request cancellation of the currently in-flight FFmpeg process.

        Kills both sync (``subprocess.Popen``) and async
        (``asyncio.subprocess.Process``) processes if one is active.

        Returns:
            ``True`` if a running process was killed, ``False`` if there
            was nothing to cancel.
        """
        killed = False
        with self._cancel_lock:
            self._cancelled = True
            if self._active_proc is not None:
                try:
                    self._active_proc.kill()
                    logger.info("ProcessManager: cancelled in-flight subprocess (pid=%s)",
                                self._active_proc.pid)
                    killed = True
                except Exception as exc:
                    logger.warning("ProcessManager: failed to kill subprocess: %s", exc)
                finally:
                    self._active_proc = None
            if self._active_async_proc is not None:
                try:
                    self._active_async_proc.kill()
                    logger.info("ProcessManager: cancelled in-flight async process")
                    killed = True
                except Exception as exc:
                    logger.warning("ProcessManager: failed to kill async process: %s", exc)
                finally:
                    self._active_async_proc = None
        return killed

    def _reset_cancel(self) -> None:
        """Clear the cancelled flag before starting a new execution."""
        with self._cancel_lock:
            self._cancelled = False


    def execute(
        self,
        command: FFMPEGCommand | list[str],
        timeout: Optional[float] = None,
    ) -> ProcessResult:
        """Execute an FFMPEG command synchronously.

        Args:
            command: FFMPEGCommand object or list of arguments.
            timeout: Maximum execution time in seconds.

        Returns:
            ProcessResult with execution details.
        """
        if isinstance(command, FFMPEGCommand):
            args = command.to_args()
            cmd_string = command.to_string()
            output_path = command.outputs[0] if command.outputs else None
        else:
            args = command
            cmd_string = " ".join(args)
            output_path = None

        # Replace 'ffmpeg' with actual path
        if args[0] == "ffmpeg" and self.ffmpeg_path:
            args[0] = self.ffmpeg_path

        self._reset_cancel()
        try:
            proc = subprocess.Popen(
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            with self._cancel_lock:
                if self._cancelled:
                    proc.kill()
                else:
                    self._active_proc = proc

            try:
                stdout_bytes, stderr_bytes = proc.communicate(timeout=timeout)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.communicate()  # drain pipes
                return ProcessResult(
                    success=False,
                    return_code=-1,
                    stdout="",
                    stderr="Process timed out",
                    command=cmd_string,
                    error_message="Execution timed out",
                )
            finally:
                with self._cancel_lock:
                    if self._active_proc is proc:
                        self._active_proc = None

            if self._cancelled:
                return ProcessResult(
                    success=False,
                    return_code=-1,
                    stdout="",
                    stderr="Cancelled",
                    command=cmd_string,
                    error_message="Cancelled by user",
                )

            stdout_str = stdout_bytes.decode("utf-8", errors="replace")
            stderr_str = stderr_bytes.decode("utf-8", errors="replace")
            success = proc.returncode == 0
            error_message = None if success else self._parse_error(stderr_str)

            return ProcessResult(
                success=success,
                return_code=proc.returncode,
                stdout=stdout_str,
                stderr=stderr_str,
                command=cmd_string,
                output_path=output_path,
                error_message=error_message,
            )

        except Exception as e:
            return ProcessResult(
                success=False,
                return_code=-1,
                stdout="",
                stderr=str(e),
                command=cmd_string,
                error_message=str(e),
            )

    async def execute_async(
        self,
        command: FFMPEGCommand | list[str],
        progress_callback: Optional[Callable[[ProgressInfo], None]] = None,
        total_duration: Optional[float] = None,
    ) -> ProcessResult:
        """Execute an FFMPEG command asynchronously with progress.

        Args:
            command: FFMPEGCommand object or list of arguments.
            progress_callback: Callback for progress updates.
            total_duration: Total video duration for percentage calculation.

        Returns:
            ProcessResult with execution details.
        """
        if isinstance(command, FFMPEGCommand):
            args = command.to_args()
            cmd_string = command.to_string()
            output_path = command.outputs[0] if command.outputs else None
        else:
            args = command
            cmd_string = " ".join(args)
            output_path = None

        # Replace 'ffmpeg' with actual path
        if args[0] == "ffmpeg" and self.ffmpeg_path:
            args[0] = self.ffmpeg_path

        # Add progress reporting
        args = [args[0], "-progress", "pipe:1", "-nostats"] + args[1:]

        self._reset_cancel()
        try:
            process = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            with self._cancel_lock:
                if self._cancelled:
                    process.kill()
                else:
                    self._active_async_proc = process

            stdout_data = []
            stderr_data = []

            async def read_stderr():
                assert process.stderr is not None
                while True:
                    line = await process.stderr.readline()
                    if not line:
                        break
                    stderr_data.append(line.decode())

            async def read_stdout():
                assert process.stdout is not None
                progress = ProgressInfo()
                while True:
                    line = await process.stdout.readline()
                    if not line:
                        break

                    line_str = line.decode().strip()
                    stdout_data.append(line_str)

                    # Parse progress info
                    if "=" in line_str:
                        key, value = line_str.split("=", 1)
                        if key == "frame":
                            progress.frame = int(value)
                        elif key == "fps":
                            progress.fps = float(value) if value else 0.0
                        elif key == "out_time_ms":
                            progress.time = int(value) / 1_000_000
                            if total_duration and total_duration > 0:
                                progress.progress_percent = min(
                                    100, (progress.time / total_duration) * 100
                                )
                        elif key == "bitrate":
                            progress.bitrate = value
                        elif key == "speed":
                            progress.speed = value
                        elif key == "total_size":
                            progress.size = int(value) if value.isdigit() else 0
                        elif key == "progress":
                            if progress_callback:
                                progress_callback(progress)
                            if value == "end":
                                progress.progress_percent = 100
                                if progress_callback:
                                    progress_callback(progress)

            # Run both readers concurrently
            await asyncio.gather(read_stdout(), read_stderr())
            await process.wait()

            with self._cancel_lock:
                if self._active_async_proc is process:
                    self._active_async_proc = None

            if self._cancelled:
                return ProcessResult(
                    success=False,
                    return_code=-1,
                    stdout="",
                    stderr="Cancelled",
                    command=cmd_string,
                    error_message="Cancelled by user",
                )

            success = process.returncode == 0
            stderr_str = "".join(stderr_data)
            error_message = None if success else self._parse_error(stderr_str)

            return ProcessResult(
                success=success,
                return_code=process.returncode or 0,
                stdout="\n".join(stdout_data),
                stderr=stderr_str,
                command=cmd_string,
                output_path=output_path,
                error_message=error_message,
            )

        except Exception as e:
            return ProcessResult(
                success=False,
                return_code=-1,
                stdout="",
                stderr=str(e),
                command=cmd_string,
                error_message=str(e),
            )

    async def execute_with_progress(
        self,
        command: FFMPEGCommand | list[str],
        total_duration: Optional[float] = None,
    ) -> AsyncIterator[ProgressInfo | ProcessResult]:
        """Execute command yielding progress updates.

        Args:
            command: FFMPEGCommand object or list of arguments.
            total_duration: Total video duration for percentage calculation.

        Yields:
            ProgressInfo during execution, ProcessResult at the end.
        """
        if isinstance(command, FFMPEGCommand):
            args = command.to_args()
            cmd_string = command.to_string()
            output_path = command.outputs[0] if command.outputs else None
        else:
            args = command
            cmd_string = " ".join(args)
            output_path = None

        if args[0] == "ffmpeg" and self.ffmpeg_path:
            args[0] = self.ffmpeg_path

        args = [args[0], "-progress", "pipe:1", "-nostats"] + args[1:]

        process = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stderr_data = []
        progress = ProgressInfo()

        # Read stderr in background
        async def collect_stderr():
            assert process.stderr is not None
            while True:
                line = await process.stderr.readline()
                if not line:
                    break
                stderr_data.append(line.decode())

        stderr_task = asyncio.create_task(collect_stderr())

        # Read stdout and yield progress
        assert process.stdout is not None
        while True:
            line = await process.stdout.readline()
            if not line:
                break

            line_str = line.decode().strip()
            if "=" in line_str:
                key, value = line_str.split("=", 1)
                if key == "frame":
                    progress.frame = int(value)
                elif key == "fps":
                    progress.fps = float(value) if value else 0.0
                elif key == "out_time_ms":
                    progress.time = int(value) / 1_000_000
                    if total_duration and total_duration > 0:
                        progress.progress_percent = min(
                            100, (progress.time / total_duration) * 100
                        )
                elif key == "bitrate":
                    progress.bitrate = value
                elif key == "speed":
                    progress.speed = value
                elif key == "progress":
                    yield progress

        await stderr_task
        await process.wait()

        success = process.returncode == 0
        stderr_str = "".join(stderr_data)

        yield ProcessResult(
            success=success,
            return_code=process.returncode or 0,
            stdout="",
            stderr=stderr_str,
            command=cmd_string,
            output_path=output_path,
            error_message=None if success else self._parse_error(stderr_str),
        )

    def _parse_error(self, stderr: str) -> str:
        """Extract meaningful error message from ffmpeg stderr."""
        lines = stderr.strip().split("\n")

        # Look for common error patterns
        error_patterns = [
            r"Error.*",
            r"Invalid.*",
            r"No such file.*",
            r".*not found.*",
            r"Permission denied.*",
            r"Discarding.*",
        ]

        for line in reversed(lines):
            for pattern in error_patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    return line.strip()

        # Return last non-empty line if no pattern matched
        for line in reversed(lines):
            if line.strip():
                return line.strip()

        return "Unknown error"

    def validate_command(self, command: FFMPEGCommand) -> tuple[bool, Optional[str]]:
        """Validate a command without executing it.

        Args:
            command: Command to validate.

        Returns:
            Tuple of (is_valid, error_message).
        """
        # Check inputs exist
        for input_path in command.inputs:
            if not Path(input_path).exists():
                return False, f"Input file not found: {input_path}"

        # Check output directory exists
        for output_path in command.outputs:
            output_dir = Path(output_path).parent
            if not output_dir.exists():
                return False, f"Output directory not found: {output_dir}"

        # Basic command structure validation
        if not command.inputs:
            return False, "No input files specified"

        if not command.outputs:
            return False, "No output file specified"

        return True, None

    def dry_run(
        self,
        command: FFMPEGCommand,
        timeout: float = 30,
    ) -> ProcessResult:
        """Validate an FFMPEG command without producing output.

        Runs the command with -f null - as output to check filter
        validity and input accessibility without writing files.

        Args:
            command: FFMPEGCommand to validate.
            timeout: Maximum time for the dry run.

        Returns:
            ProcessResult — success=True means filters/inputs are valid.
        """
        import copy
        dry_cmd = copy.deepcopy(command)
        # Replace outputs with null sink
        dry_cmd.outputs = ["-"]
        dry_cmd.output_options = [
            opt for opt in dry_cmd.output_options
            if opt not in ("-y",)
        ] + ["-f", "null"]

        return self.execute(dry_cmd, timeout=timeout)
