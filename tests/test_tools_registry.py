"""Unit tests for ToolRegistry and schema conversion."""

from pathlib import Path

from swe_agent.sandbox.local_sandbox import LocalSandbox
from swe_agent.tools.registry import create_default_registry


def test_default_tool_registry():
    """Verify default registry contains all essential SWE tools."""
    registry = create_default_registry()
    names = registry.tool_names

    assert "code_search" in names
    assert "find_symbol" in names
    assert "list_directory" in names
    assert "view_file" in names
    assert "edit_file_replace" in names
    assert "create_file" in names
    assert "git_diff" in names
    assert "git_status" in names
    assert "git_restore" in names
    assert "run_bash_command" in names


def test_schema_generation():
    """Verify tool schemas conform to OpenAI/Gemini function calling specifications."""
    registry = create_default_registry()
    schemas = registry.get_schemas()

    assert len(schemas) >= 10

    # Inspect edit_file_replace schema structure
    edit_schema = next(s for s in schemas if s["function"]["name"] == "edit_file_replace")
    fn = edit_schema["function"]
    assert "description" in fn
    assert "parameters" in fn
    assert fn["parameters"]["type"] == "object"
    props = fn["parameters"]["properties"]
    assert "path" in props
    assert "old_str" in props
    assert "new_str" in props
    assert "path" in fn["parameters"]["required"]


def test_registry_dispatch(tmp_path: Path):
    """Verify registry dispatches execution with input validation."""
    sandbox = LocalSandbox(workspace_dir=tmp_path)
    sandbox.start()

    registry = create_default_registry()

    # Successful dispatch
    res = registry.execute_tool(
        "create_file",
        {"path": "hello.txt", "content": "world"},
        sandbox
    )
    assert res.success is True
    assert sandbox.read_file("hello.txt") == "world"

    # Non-existent tool dispatch
    res_invalid = registry.execute_tool(
        "magic_fix_all_bugs",
        {"param": "please"},
        sandbox
    )
    assert res_invalid.success is False
    assert "does not exist" in res_invalid.output

    sandbox.stop()
