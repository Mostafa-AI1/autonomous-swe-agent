"""Local process sandbox with path isolation and timeout enforcement.

Useful for lightweight local development, unit testing, and environments
where Docker daemon cannot be initialized.
"""

import os
import subprocess
import time
from pathlib import Path
from typing import Optional

from swe_agent.config import settings
from swe_agent.safety.path_guard import validate_safe_path
from swe_agent.sandbox.protocol import AbstractSandbox, SandboxResult, smart_truncate_output


class LocalSandbox(AbstractSandbox):
    """Local execution sandbox with directory boundary validation and timeout control."""

    def __init__(self, workspace_dir: str | Path):
        self.workspace_dir = Path(workspace_dir).resolve()
        self._is_active = False

    def start(self) -> None:
        """Ensure workspace directory exists and initialize state."""
        self.workspace_dir.mkdir(parents=True, exist_ok=True)
        self._is_active = True

    def stop(self) -> None:
        """Tear down local sandbox session."""
        self._is_active = False

    def _resolve_safe_path(self, path: str | Path) -> Path:
        """Validate that target path does not escape the workspace directory.

        Prevents directory traversal attacks (e.g., '../../etc/passwd') and
        sensitive file leakage (.env, id_rsa).
        """
        return validate_safe_path(path=path, workspace_dir=self.workspace_dir)

    def execute(
        self,
        command: str,
        timeout_seconds: Optional[int] = None,
        workdir: Optional[str] = None
    ) -> SandboxResult:
        """Execute command locally inside the workspace directory."""
        if not self._is_active:
            raise RuntimeError("LocalSandbox must be started before executing commands.")

        effective_timeout = timeout_seconds or settings.sandbox_timeout_seconds
        target_dir = self._resolve_safe_path(workdir) if workdir else self.workspace_dir

        start_time = time.perf_counter()
        timed_out = False
        exit_code = -1
        stdout_raw = ""
        stderr_raw = ""

        try:
            # Execute command with POSIX/Windows shell compatibility
            process = subprocess.run(
                command,
                shell=True,
                cwd=target_dir,
                capture_output=True,
                text=True,
                timeout=effective_timeout,
                encoding="utf-8",
                errors="replace"
            )
            exit_code = process.returncode
            stdout_raw = process.stdout
            stderr_raw = process.stderr
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            stdout_raw = exc.stdout or "" if isinstance(exc.stdout, str) else ""
            stderr_raw = (exc.stderr or "") + f"\n[Process killed after {effective_timeout}s timeout]"
            exit_code = 124  # Standard POSIX timeout exit code
        except Exception as exc:
            stderr_raw = f"[Execution Error]: {str(exc)}"
            exit_code = 1

        duration = time.perf_counter() - start_time

        # Apply smart truncation to both stdout and stderr
        stdout_clean, trunc_out = smart_truncate_output(
            stdout_raw, max_lines=settings.max_tool_output_lines
        )
        stderr_clean, trunc_err = smart_truncate_output(
            stderr_raw, max_lines=settings.max_tool_output_lines
        )

        return SandboxResult(
            command=command,
            exit_code=exit_code,
            stdout=stdout_clean,
            stderr=stderr_clean,
            truncated=(trunc_out or trunc_err),
            duration_seconds=round(duration, 3),
            timed_out=timed_out
        )

    def read_file(self, path: str) -> str:
        """Read content of a file within the sandbox."""
        safe_path = self._resolve_safe_path(path)
        if not safe_path.exists():
            raise FileNotFoundError(f"File not found: {path}")
        return safe_path.read_text(encoding="utf-8", errors="replace")

    def write_file(self, path: str, content: str) -> None:
        """Write content to a file within the sandbox."""
        safe_path = self._resolve_safe_path(path)
        safe_path.parent.mkdir(parents=True, exist_ok=True)
        safe_path.write_text(content, encoding="utf-8", errors="replace")
