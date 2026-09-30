"""Sandbox execution protocols, output models, and smart truncation utilities."""

from abc import ABC, abstractmethod
from typing import Optional
from pydantic import BaseModel, Field


class SandboxResult(BaseModel):
    """Result of executing a command inside the sandbox."""

    command: str = Field(description="The command that was executed")
    exit_code: int = Field(description="Exit code returned by the process (0 indicates success)")
    stdout: str = Field(default="", description="Captured standard output")
    stderr: str = Field(default="", description="Captured standard error")
    truncated: bool = Field(default=False, description="Whether the output was truncated due to length limits")
    duration_seconds: float = Field(default=0.0, description="Execution time in seconds")
    timed_out: bool = Field(default=False, description="Whether execution was terminated due to timeout")

    @property
    def is_success(self) -> bool:
        """Convenience property for exit code == 0."""
        return self.exit_code == 0 and not self.timed_out

    @property
    def combined_output(self) -> str:
        """Combine stdout and stderr with clean separation."""
        parts = []
        if self.stdout.strip():
            parts.append(self.stdout.strip())
        if self.stderr.strip():
            parts.append(f"[STDERR]\n{self.stderr.strip()}")
        return "\n".join(parts) if parts else "(No output emitted)"


def smart_truncate_output(
    text: str,
    max_lines: int = 120,
    head_lines: int = 25,
    tail_lines: int = 75
) -> tuple[str, bool]:
    """Truncate verbose terminal output while preserving critical test tracebacks.

    Why this matters in production:
    Dumping 5,000 lines of pytest output destroys the LLM context window.
    Naive head truncation cuts off the traceback at the bottom; naive tail truncation
    cuts off the test header at the top. Smart truncation preserves both ends.

    Args:
        text: Raw output string.
        max_lines: Total line threshold before triggering truncation.
        head_lines: Lines to preserve from the start of the output.
        tail_lines: Lines to preserve from the end of the output (tracebacks).

    Returns:
        tuple[str, bool]: (processed_text, was_truncated)
    """
    lines = text.splitlines()
    if len(lines) <= max_lines:
        return text, False

    total_omitted = len(lines) - (head_lines + tail_lines)
    if total_omitted <= 0:
        return text, False

    head = lines[:head_lines]
    tail = lines[-tail_lines:]
    truncation_banner = f"\n... [Smart Truncation: {total_omitted} lines omitted to conserve agent context] ...\n"

    truncated_text = "\n".join(head) + truncation_banner + "\n".join(tail)
    return truncated_text, True


class AbstractSandbox(ABC):
    """Abstract interface defining the execution and filesystem boundaries of the sandbox."""

    @abstractmethod
    def start(self) -> None:
        """Initialize the sandbox environment and prepare workspace."""
        pass

    @abstractmethod
    def stop(self) -> None:
        """Tear down the sandbox container and clean up ephemeral mounts."""
        pass

    @abstractmethod
    def execute(
        self,
        command: str,
        timeout_seconds: Optional[int] = None,
        workdir: Optional[str] = None
    ) -> SandboxResult:
        """Execute a shell command inside the isolated environment.

        Args:
            command: Shell command to run.
            timeout_seconds: Max seconds before SIGKILL.
            workdir: Optional working directory relative to sandbox root.

        Returns:
            SandboxResult containing exit code, output, and execution metadata.
        """
        pass

    @abstractmethod
    def read_file(self, path: str) -> str:
        """Read file content from within the sandbox."""
        pass

    @abstractmethod
    def write_file(self, path: str, content: str) -> None:
        """Write file content inside the sandbox."""
        pass

    def __enter__(self) -> "AbstractSandbox":
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.stop()
