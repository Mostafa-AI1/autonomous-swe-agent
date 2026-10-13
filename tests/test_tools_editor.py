"""Unit tests for precision file editing tools: view_file, edit_file_replace, create_file."""

from pathlib import Path
from swe_agent.sandbox.local_sandbox import LocalSandbox
from swe_agent.tools.editor import CreateFileTool, EditFileReplaceTool, ViewFileTool


def test_view_file_pagination_and_numbering(tmp_path: Path):
    """Verify line numbering format and window boundaries."""
    sandbox = LocalSandbox(workspace_dir=tmp_path)
    sandbox.start()

    sample_content = "\n".join([f"line_{i}" for i in range(1, 21)])
    sandbox.write_file("sample.txt", sample_content)

    viewer = ViewFileTool()

    # View lines 5 to 10
    res = viewer.run(sandbox, path="sample.txt", start_line=5, line_count=6)
    assert res.success is True
    assert "Lines 5 - 10 of 20" in res.output
    assert "    5 | line_5" in res.output
    assert "   10 | line_10" in res.output
    assert "line_4" not in res.output
    assert "line_11" not in res.output

    # Viewing beyond file length
    err_res = viewer.run(sandbox, path="sample.txt", start_line=30, line_count=5)
    assert err_res.success is False
    assert "exceeds total lines" in err_res.output

    sandbox.stop()


def test_edit_file_replace_unique_match_rule(tmp_path: Path):
    """Verify that edit_file_replace enforces the 1-match requirement."""
    sandbox = LocalSandbox(workspace_dir=tmp_path)
    sandbox.start()

    initial_code = (
        "def calculate_total(a, b):\n"
        "    return a + b\n"
        "\n"
        "def calculate_tax(a, b):\n"
        "    return a * b\n"
    )
    sandbox.write_file("calc.py", initial_code)
    editor = EditFileReplaceTool()

    # Case 1: Exact unique match -> Success
    res = editor.run(
        sandbox,
        path="calc.py",
        old_str="def calculate_total(a, b):\n    return a + b",
        new_str="def calculate_total(a, b):\n    return round(a + b, 2)"
    )
    assert res.success is True
    updated = sandbox.read_file("calc.py")
    assert "round(a + b, 2)" in updated

    # Case 2: Zero matches -> Rejection
    err_zero = editor.run(
        sandbox,
        path="calc.py",
        old_str="non_existent_function()",
        new_str="new_func()"
    )
    assert err_zero.success is False
    assert "was not found" in err_zero.output

    # Case 3: Multiple matches -> Rejection
    err_multi = editor.run(
        sandbox,
        path="calc.py",
        old_str="(a, b)",
        new_str="(x, y)"
    )
    assert err_multi.success is False
    assert "matches 2 occurrences" in err_multi.output

    sandbox.stop()


def test_create_file_overwrite_protection(tmp_path: Path):
    """Verify create_file overwrite protection and creation."""
    sandbox = LocalSandbox(workspace_dir=tmp_path)
    sandbox.start()

    creator = CreateFileTool()

    # Fresh creation
    res = creator.run(sandbox, path="script.py", content="print('hello')")
    assert res.success is True
    assert sandbox.read_file("script.py") == "print('hello')"

    # Attempt to overwrite without flag
    res_blocked = creator.run(sandbox, path="script.py", content="print('overwritten')")
    assert res_blocked.success is False
    assert "already exists" in res_blocked.output

    # Allowed overwrite
    res_overwrite = creator.run(
        sandbox, path="script.py", content="print('overwritten')", overwrite=True
    )
    assert res_overwrite.success is True
    assert sandbox.read_file("script.py") == "print('overwritten')"

    sandbox.stop()
