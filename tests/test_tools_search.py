"""Unit tests for code search and AST symbol intelligence tools."""

from pathlib import Path
from swe_agent.sandbox.local_sandbox import LocalSandbox
from swe_agent.tools.search import CodeSearchTool, FindSymbolTool, ListDirectoryTool


def test_find_symbol_ast_parser(tmp_path: Path):
    """Verify AST-based extraction of functions and classes with signatures."""
    sandbox = LocalSandbox(workspace_dir=tmp_path)
    sandbox.start()

    sample_py = (
        'class PaymentGateway:\n'
        '    """Handles payment transactions."""\n'
        '    def process_charge(self, amount, currency):\n'
        '        return True\n'
        '\n'
        'def standalone_helper(token):\n'
        '    """Validates user token."""\n'
        '    return token is not None\n'
    )
    sandbox.write_file("payments/gateway.py", sample_py)

    finder = FindSymbolTool()

    # Search for class PaymentGateway
    res_class = finder.run(sandbox, name="PaymentGateway", symbol_type="class")
    assert res_class.success is True
    assert "payments/gateway.py" in res_class.output
    assert "class PaymentGateway" in res_class.output
    assert "Handles payment transactions" in res_class.output

    # Search for method process_charge
    res_method = finder.run(sandbox, name="process_charge", symbol_type="function")
    assert res_method.success is True
    assert "def process_charge(self, amount, currency)" in res_method.output

    # Search for non-existent symbol
    res_none = finder.run(sandbox, name="non_existent", symbol_type="function")
    assert res_none.success is True
    assert "No symbol found" in res_none.output

    sandbox.stop()


def test_code_search_fallback(tmp_path: Path):
    """Verify code search locates regex and string patterns across files."""
    sandbox = LocalSandbox(workspace_dir=tmp_path)
    sandbox.start()

    sandbox.write_file("src/api.py", "def get_user_status(user_id):\n    return 'active'")
    sandbox.write_file("src/auth.py", "def authenticate():\n    status = get_user_status(42)")

    searcher = CodeSearchTool()
    res = searcher.run(sandbox, query="get_user_status", path="src")

    assert res.success is True
    assert "Found 2 match(es)" in res.output
    assert "src/api.py" in res.output
    assert "src/auth.py" in res.output

    sandbox.stop()


def test_list_directory_structure(tmp_path: Path):
    """Verify directory tree listing respects depth and filters caches."""
    sandbox = LocalSandbox(workspace_dir=tmp_path)
    sandbox.start()

    sandbox.write_file("pkg/subpkg/mod.py", "# mod")
    sandbox.write_file("__pycache__/cached.pyc", "binary")

    lister = ListDirectoryTool()
    res = lister.run(sandbox, path=".", max_depth=3)

    assert res.success is True
    assert "pkg/" in res.output
    assert "subpkg/" in res.output
    assert "mod.py" in res.output
    assert "__pycache__" not in res.output

    sandbox.stop()
