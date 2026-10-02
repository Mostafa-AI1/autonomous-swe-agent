"""Path traversal and filesystem boundary validation guardrails."""

from pathlib import Path
from typing import Union


class SecurityViolationError(PermissionError):
    """Raised when an agent attempts an unauthorized or dangerous operation."""
    pass


SENSITIVE_FILES_BLOCKLIST = {
    ".env",
    ".env.local",
    ".env.production",
    "id_rsa",
    "id_ed25519",
    ".git/config",
    ".git/hooks",
}


def validate_safe_path(
    path: Union[str, Path],
    workspace_dir: Union[str, Path],
    allow_creation: bool = True
) -> Path:
    """Validate that target path remains strictly within the workspace directory.

    Guards against:
    - Path traversal attacks (e.g., '../../../../etc/passwd')
    - Escapes to root or host drives ('C:\\Windows', '/etc/')
    - Access to sensitive credentials or secrets files (.env, private keys)

    Args:
        path: Path string or Path object requested by the agent.
        workspace_dir: Canonical workspace boundary path.
        allow_creation: If True, parent directory must resolve inside workspace.

    Returns:
        Path: Fully resolved, validated safe Path.

    Raises:
        SecurityViolationError: If boundary violation or sensitive file access is detected.
    """
    ws = Path(workspace_dir).resolve()
    target = (ws / path).resolve()

    # Boundary containment check
    try:
        target.relative_to(ws)
    except ValueError as exc:
        raise SecurityViolationError(
            f"Directory Traversal Blocked: Path '{path}' resolves to '{target}', "
            f"which escapes the designated workspace boundary '{ws}'."
        ) from exc

    # Sensitive file inspection
    relative_str = target.relative_to(ws).as_posix().lower()
    for sensitive in SENSITIVE_FILES_BLOCKLIST:
        if relative_str == sensitive or relative_str.endswith(f"/{sensitive}"):
            raise SecurityViolationError(
                f"Security Blocked: Direct access to sensitive credential file '{relative_str}' "
                f"is strictly prohibited."
            )

    return target
