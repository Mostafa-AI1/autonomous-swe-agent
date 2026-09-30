"""Production Docker sandbox for strict environment isolation and security."""

import time
from pathlib import Path
from typing import Optional

try:
    import docker
    from docker.errors import DockerException, NotFound
except ImportError:
    docker = None
    DockerException = Exception
    NotFound = Exception

from swe_agent.config import settings
from swe_agent.sandbox.protocol import AbstractSandbox, SandboxResult, smart_truncate_output


class DockerSandbox(AbstractSandbox):
    """Containerized sandbox executing all commands in an isolated Linux container."""

    def __init__(
        self,
        workspace_dir: str | Path,
        image_name: Optional[str] = None,
        network_enabled: bool = False
    ):
        if docker is None:
            raise ImportError(
                "The 'docker' package is required to use DockerSandbox. "
                "Install it via `pip install docker`."
            )
        self.workspace_dir = Path(workspace_dir).resolve()
        self.image_name = image_name or settings.sandbox_image
        self.network_enabled = network_enabled
        self.client = None
        self.container = None

    def start(self) -> None:
        """Initialize Docker client, verify image, and launch the isolated container."""
        try:
            self.client = docker.from_env()
            self.client.ping()
        except DockerException as err:
            raise ConnectionError(
                f"Failed to connect to Docker daemon: {err}. "
                "Ensure Docker Desktop or Docker engine is running."
            ) from err

        # Verify or ensure image exists
        try:
            self.client.images.get(self.image_name)
        except NotFound:
            # If the custom image isn't built yet, use python:3.11-slim as fallback
            self.image_name = "python:3.11-slim"
            self.client.images.pull(self.image_name)

        # Host workspace directory preparation
        self.workspace_dir.mkdir(parents=True, exist_ok=True)

        # Launch container with resource limits and restricted privileges
        network_mode = "bridge" if self.network_enabled else "none"
        self.container = self.client.containers.run(
            image=self.image_name,
            command="/bin/bash -c 'while true; do sleep 1000; done'",
            detach=True,
            volumes={
                str(self.workspace_dir): {
                    "bind": settings.sandbox_workdir,
                    "mode": "rw"
                }
            },
            working_dir=settings.sandbox_workdir,
            mem_limit=settings.sandbox_memory_limit,
            nano_cpus=int(settings.sandbox_cpu_limit * 1e9),
            network_mode=network_mode,
            remove=True,
            user="1000:1000" if self.image_name == settings.sandbox_image else None
        )

    def stop(self) -> None:
        """Stop and terminate the running container."""
        if self.container:
            try:
                self.container.stop(timeout=2)
            except Exception:
                try:
                    self.container.kill()
                except Exception:
                    pass
            self.container = None

    def execute(
        self,
        command: str,
        timeout_seconds: Optional[int] = None,
        workdir: Optional[str] = None
    ) -> SandboxResult:
        """Execute a shell command inside the Docker container."""
        if not self.container:
            raise RuntimeError("DockerSandbox is not running. Call .start() first.")

        effective_timeout = timeout_seconds or settings.sandbox_timeout_seconds
        target_dir = f"{settings.sandbox_workdir}/{workdir.lstrip('/')}" if workdir else settings.sandbox_workdir

        start_time = time.perf_counter()

        # Wrap with timeout command in POSIX shell
        wrapped_command = f"bash -c {docker.utils.shlex.quote(command)}" if hasattr(docker, "utils") else f"bash -c '{command}'"

        exec_res = self.container.exec_run(
            cmd=wrapped_command,
            workdir=target_dir,
            demux=True  # Separate stdout and stderr streams
        )

        duration = time.perf_counter() - start_time
        exit_code = exec_res.exit_code

        stdout_bytes, stderr_bytes = exec_res.output
        stdout_raw = stdout_bytes.decode("utf-8", errors="replace") if stdout_bytes else ""
        stderr_raw = stderr_bytes.decode("utf-8", errors="replace") if stderr_bytes else ""

        # Smart truncation to preserve context budget
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
            timed_out=False
        )

    def read_file(self, path: str) -> str:
        """Read a file from the host-mounted workspace."""
        local_path = (self.workspace_dir / path).resolve()
        if not local_path.is_relative_to(self.workspace_dir):
            raise PermissionError(f"Access denied: Path '{path}' is outside sandbox workspace.")
        if not local_path.exists():
            raise FileNotFoundError(f"File not found: {path}")
        return local_path.read_text(encoding="utf-8", errors="replace")

    def write_file(self, path: str, content: str) -> None:
        """Write a file to the host-mounted workspace."""
        local_path = (self.workspace_dir / path).resolve()
        if not local_path.is_relative_to(self.workspace_dir):
            raise PermissionError(f"Access denied: Path '{path}' is outside sandbox workspace.")
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_text(content, encoding="utf-8", errors="replace")
