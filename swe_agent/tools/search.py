"""Code search and AST-based symbol intelligence tools."""

import ast
import os
import re
from pathlib import Path
from typing import Literal, Optional, Type
from pydantic import BaseModel, Field

from swe_agent.sandbox.protocol import AbstractSandbox
from swe_agent.tools.base import BaseTool, ToolResult

EXCLUDE_DIRS = {
    ".git", ".venv", "venv", "env", "__pycache__", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", "node_modules", "dist", "build", ".egg-info"
}


class CodeSearchInput(BaseModel):
    """Input arguments for code_search."""
    query: str = Field(description="Search term or regex pattern to look for")
    path: str = Field(default=".", description="Relative subdirectory to search within")
    is_regex: bool = Field(default=False, description="Whether to treat query as regex")
    case_sensitive: bool = Field(default=False, description="Whether search should be case sensitive")
    file_pattern: Optional[str] = Field(
        default=None,
        description="Optional glob filter, e.g. '*.py' or 'tests/*'"
    )


class CodeSearchTool(BaseTool):
    """Fast code search using ripgrep or deterministic file scanning."""

    name = "code_search"
    description = (
        "Search codebase for exact text or regex patterns. "
        "Returns matched files, line numbers, and code snippets. "
        "Results are capped at 50 matches to protect context window."
    )
    args_schema: Type[BaseModel] = CodeSearchInput

    def execute(self, sandbox: AbstractSandbox, **kwargs) -> ToolResult:
        args = CodeSearchInput(**kwargs)

        # First attempt fast ripgrep inside sandbox
        rg_flags = ["--line-number", "--no-heading", "--color=never"]
        if not args.case_sensitive:
            rg_flags.append("-i")
        if not args.is_regex:
            rg_flags.append("-F")
        if args.file_pattern:
            rg_flags.extend(["-g", f"'{args.file_pattern}'"])

        # Exclude noisy dirs
        for d in EXCLUDE_DIRS:
            rg_flags.extend(["--glob", f"!{d}/**"])

        cmd = f"rg {' '.join(rg_flags)} -- '{args.query}' {args.path}"
        exec_res = sandbox.execute(cmd, timeout_seconds=15)

        if exec_res.exit_code == 0 and exec_res.stdout.strip():
            raw_lines = exec_res.stdout.strip().splitlines()
            return self._format_results(raw_lines, args.query)

        # Fallback to Python-based search if ripgrep not available or failed
        return self._python_fallback_search(sandbox, args)

    def _format_results(self, lines: list[str], query: str) -> ToolResult:
        max_matches = 50
        total_found = len(lines)
        truncated = total_found > max_matches
        display_lines = lines[:max_matches]

        header = f"Found {total_found} match(es) for '{query}':\n"
        if truncated:
            header += f"[Displaying first {max_matches} of {total_found} matches to preserve context]\n"

        return ToolResult(
            success=True,
            output=header + "\n".join(display_lines),
            data={"total_matches": total_found, "displayed_matches": len(display_lines)}
        )

    def _python_fallback_search(
        self, sandbox: AbstractSandbox, args: CodeSearchInput
    ) -> ToolResult:
        matches = []
        pattern_flags = 0 if args.case_sensitive else re.IGNORECASE
        try:
            pattern = re.compile(
                args.query if args.is_regex else re.escape(args.query),
                pattern_flags
            )
        except re.error as err:
            return ToolResult(success=False, output=f"Invalid regex pattern: {err}")

        # Scan workspace files
        workspace_dir = getattr(sandbox, "workspace_dir", None)
        if not workspace_dir or not Path(workspace_dir).exists():
            return ToolResult(success=True, output=f"No matches found for '{args.query}'.")

        search_root = (Path(workspace_dir) / args.path).resolve()

        for root, dirs, files in os.walk(search_root):
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
            for file in files:
                if args.file_pattern and not Path(file).match(args.file_pattern):
                    continue
                file_path = Path(root) / file
                rel_path = file_path.relative_to(workspace_dir).as_posix()
                try:
                    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                        for line_no, line in enumerate(f, start=1):
                            if pattern.search(line):
                                matches.append(f"{rel_path}:{line_no}:{line.strip()}")
                                if len(matches) >= 100:
                                    break
                except Exception:
                    continue

        if not matches:
            return ToolResult(success=True, output=f"No matches found for '{args.query}'.")

        return self._format_results(matches, args.query)


class FindSymbolInput(BaseModel):
    """Input arguments for find_symbol."""
    name: str = Field(description="Name of the function, method, or class to find")
    symbol_type: Literal["any", "function", "class"] = Field(
        default="any",
        description="Filter by 'function', 'class', or 'any'"
    )
    path: str = Field(default=".", description="Relative subdirectory to search within")


class FindSymbolTool(BaseTool):
    """AST-based symbol locator that pinpoints class and function definitions."""

    name = "find_symbol"
    description = (
        "Locate Python functions, methods, or classes using AST analysis. "
        "Returns file paths, line ranges, signatures, and docstring headers."
    )
    args_schema: Type[BaseModel] = FindSymbolInput

    def execute(self, sandbox: AbstractSandbox, **kwargs) -> ToolResult:
        args = FindSymbolInput(**kwargs)
        workspace_dir = getattr(sandbox, "workspace_dir", None)
        if not workspace_dir:
            return ToolResult(success=False, output="Sandbox workspace directory inaccessible.")

        search_root = (Path(workspace_dir) / args.path).resolve()
        results = []

        for root, dirs, files in os.walk(search_root):
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
            for file in files:
                if not file.endswith(".py"):
                    continue
                file_path = Path(root) / file
                rel_path = file_path.relative_to(workspace_dir).as_posix()
                try:
                    code = file_path.read_text(encoding="utf-8", errors="replace")
                    tree = ast.parse(code, filename=rel_path)
                except SyntaxError:
                    continue

                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        if args.symbol_type in ("any", "function") and node.name == args.name:
                            sig = self._format_func_sig(node)
                            doc = ast.get_docstring(node)
                            doc_summary = f" - '{doc.splitlines()[0]}'" if doc else ""
                            results.append(
                                f"{rel_path}:{node.lineno}-{node.end_lineno or node.lineno} "
                                f"[function] def {sig}{doc_summary}"
                            )
                    elif isinstance(node, ast.ClassDef):
                        if args.symbol_type in ("any", "class") and node.name == args.name:
                            bases = [ast.unparse(b) for b in node.bases]
                            base_str = f"({', '.join(bases)})" if bases else ""
                            doc = ast.get_docstring(node)
                            doc_summary = f" - '{doc.splitlines()[0]}'" if doc else ""
                            results.append(
                                f"{rel_path}:{node.lineno}-{node.end_lineno or node.lineno} "
                                f"[class] class {node.name}{base_str}{doc_summary}"
                            )

        if not results:
            return ToolResult(
                success=True,
                output=f"No symbol found matching '{args.name}' with type='{args.symbol_type}'."
            )

        return ToolResult(
            success=True,
            output=f"Found {len(results)} symbol definition(s) for '{args.name}':\n" + "\n".join(results),
            data={"symbols_found": len(results)}
        )

    def _format_func_sig(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
        args = []
        for arg in node.args.args:
            args.append(arg.arg)
        return f"{node.name}({', '.join(args)})"


class ListDirectoryInput(BaseModel):
    """Input arguments for list_directory."""
    path: str = Field(default=".", description="Relative directory path to list")
    max_depth: int = Field(default=2, ge=1, le=4, description="Depth of subdirectory recursion")


class ListDirectoryTool(BaseTool):
    """List directory structure hierarchically with depth bounds."""

    name = "list_directory"
    description = (
        "Explore folder layout and file tree. "
        "Respects recursion depth and excludes cache/git directories."
    )
    args_schema: Type[BaseModel] = ListDirectoryInput

    def execute(self, sandbox: AbstractSandbox, **kwargs) -> ToolResult:
        args = ListDirectoryInput(**kwargs)
        workspace_dir = getattr(sandbox, "workspace_dir", None)
        if not workspace_dir:
            return ToolResult(success=False, output="Workspace directory unavailable.")

        target_dir = (Path(workspace_dir) / args.path).resolve()
        if not target_dir.exists():
            return ToolResult(success=False, output=f"Directory '{args.path}' does not exist.")

        tree_lines = [f"{args.path}/"]
        self._build_tree(target_dir, target_dir, tree_lines, current_depth=1, max_depth=args.max_depth)

        return ToolResult(
            success=True,
            output="\n".join(tree_lines),
            data={"path": args.path, "lines_listed": len(tree_lines)}
        )

    def _build_tree(
        self,
        base_dir: Path,
        current_dir: Path,
        lines: list[str],
        current_depth: int,
        max_depth: int
    ) -> None:
        if current_depth > max_depth:
            return

        try:
            entries = sorted(list(current_dir.iterdir()), key=lambda e: (not e.is_dir(), e.name.lower()))
        except PermissionError:
            return

        indent = "  " * current_depth
        for entry in entries:
            if entry.name in EXCLUDE_DIRS or entry.name.startswith("."):
                continue

            if entry.is_dir():
                lines.append(f"{indent}📁 {entry.name}/")
                self._build_tree(base_dir, entry, lines, current_depth + 1, max_depth)
            else:
                lines.append(f"{indent}📄 {entry.name}")
