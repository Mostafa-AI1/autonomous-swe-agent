"""Unit tests for Git inspection and rollback tools."""

import subprocess
from pathlib import Path

from swe_agent.sandbox.local_sandbox import LocalSandbox
from swe_agent.tools.git_tools import GitDiffTool, GitRestoreTool, GitStatusTool


def test_git_tools_workflow(tmp_path: Path):
    """Test git status, diff, and restore in an isolated git repository."""
    # Initialize a clean git repository in tmp_path
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "TestUser"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)

    sandbox = LocalSandbox(workspace_dir=tmp_path)
    sandbox.start()

    # Commit initial clean state
    sandbox.write_file("main.py", "def run():\n    return 1\n")
    subprocess.run(["git", "add", "main.py"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=tmp_path, check=True)

    status_tool = GitStatusTool()
    diff_tool = GitDiffTool()
    restore_tool = GitRestoreTool()

    # Step 1: Initial state should be clean
    res_status_clean = status_tool.run(sandbox)
    assert res_status_clean.success is True
    assert "Clean repository state" in res_status_clean.output

    # Step 2: Make a modification
    sandbox.write_file("main.py", "def run():\n    return 42\n")

    res_status_dirty = status_tool.run(sandbox)
    assert res_status_dirty.success is True
    assert "M main.py" in res_status_dirty.output or "M  main.py" in res_status_dirty.output

    res_diff = diff_tool.run(sandbox)
    assert res_diff.success is True
    assert "+    return 42" in res_diff.output
    assert "-    return 1" in res_diff.output

    # Step 3: Self-recovery rollback via git_restore
    res_restore = restore_tool.run(sandbox, path="main.py")
    assert res_restore.success is True
    assert "Successfully restored 'main.py'" in res_restore.output

    # Verify content returned to baseline
    restored_code = sandbox.read_file("main.py")
    assert "return 1" in restored_code
    assert "return 42" not in restored_code

    sandbox.stop()
