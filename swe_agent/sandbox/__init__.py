"""Sandbox module providing isolation and execution environments."""

from swe_agent.sandbox.docker_sandbox import DockerSandbox
from swe_agent.sandbox.local_sandbox import LocalSandbox
from swe_agent.sandbox.protocol import AbstractSandbox, SandboxResult, smart_truncate_output

__all__ = [
    "AbstractSandbox",
    "SandboxResult",
    "DockerSandbox",
    "LocalSandbox",
    "smart_truncate_output",
]
