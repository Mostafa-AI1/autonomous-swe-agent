"""Unit tests for sandbox isolation, security boundaries, and smart output truncation."""

from pathlib import Path

import pytest

from swe_agent.sandbox.local_sandbox import LocalSandbox
from swe_agent.sandbox.protocol import smart_truncate_output


def test_smart_truncate_output_below_threshold():
    """Outputs below limit should remain untouched."""
    short_text = "line 1\nline 2\nline 3"
    truncated, was_cut = smart_truncate_output(short_text, max_lines=10)
    assert was_cut is False
    assert truncated == short_text


def test_smart_truncate_preserves_head_and_tail():
    """Verbose output should keep initial lines and final tracebacks."""
    lines = [f"setup step {i}" for i in range(25)]
    lines += [f"verbose middle noise {i}" for i in range(200)]
    lines += [f"CRITICAL TRACEBACK {i}" for i in range(25)]
    full_output = "\n".join(lines)

    truncated, was_cut = smart_truncate_output(
        full_output, max_lines=60, head_lines=10, tail_lines=15
    )

    assert was_cut is True
    assert "setup step 0" in truncated
    assert "setup step 9" in truncated
    assert "verbose middle noise 100" not in truncated
    assert "CRITICAL TRACEBACK 24" in truncated
    assert "Smart Truncation" in truncated


def test_local_sandbox_directory_traversal_prevention(tmp_path: Path):
    """Sandbox should actively block escaping beyond the workspace directory."""
    workspace = tmp_path / "safe_workspace"
    sandbox = LocalSandbox(workspace_dir=workspace)
    sandbox.start()

    # Attempting to read outside workspace should trigger security violation
    with pytest.raises(PermissionError, match="Directory Traversal Blocked"):
        sandbox.read_file("../../outside.txt")

    sandbox.stop()


def test_local_sandbox_file_lifecycle(tmp_path: Path):
    """Sandbox should write and read files within its boundary cleanly."""
    workspace = tmp_path / "safe_workspace"
    sandbox = LocalSandbox(workspace_dir=workspace)
    sandbox.start()

    sandbox.write_file("sub/hello.py", "print('hello from sandbox')")
    content = sandbox.read_file("sub/hello.py")
    assert "hello from sandbox" in content

    res = sandbox.execute("python -c \"print('execution test')\"")
    # Even if python isn't on host PATH, sandbox captures result cleanly without crashing
    assert isinstance(res.exit_code, int)
    assert res.timed_out is False

    sandbox.stop()
