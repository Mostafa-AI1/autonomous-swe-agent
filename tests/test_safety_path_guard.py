"""Unit tests for path traversal guard and sensitive file blocklists."""

from pathlib import Path

import pytest

from swe_agent.safety.path_guard import SecurityViolationError, validate_safe_path


def test_allowed_safe_paths(tmp_path: Path):
    """Safe paths inside workspace boundary should resolve successfully."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    safe_file = validate_safe_path("src/module.py", workspace)
    assert safe_file == (workspace / "src/module.py").resolve()


def test_directory_traversal_blocked(tmp_path: Path):
    """Attempts to escape workspace boundary must raise SecurityViolationError."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    with pytest.raises(SecurityViolationError, match="Directory Traversal Blocked"):
        validate_safe_path("../../etc/passwd", workspace)

    with pytest.raises(SecurityViolationError, match="Directory Traversal Blocked"):
        validate_safe_path("../outside.py", workspace)


def test_sensitive_files_blocked(tmp_path: Path):
    """Attempts to read .env or SSH keys must raise SecurityViolationError."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    with pytest.raises(SecurityViolationError, match="sensitive credential file"):
        validate_safe_path(".env", workspace)

    with pytest.raises(SecurityViolationError, match="sensitive credential file"):
        validate_safe_path("config/.env", workspace)

    with pytest.raises(SecurityViolationError, match="sensitive credential file"):
        validate_safe_path("keys/id_rsa", workspace)
