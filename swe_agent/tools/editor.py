"""Windowed file viewer and precision string-replacement editor tools.

Built on the Princeton SWE-agent / OpenHands ACI paradigm:
- Forces exact-string matching to prevent hallucinated full-file regressions.
- Line-numbered windowed viewing prevents context-window blowout.
"""

from pathlib import Path
from typing import Type
from pydantic import BaseModel, Field

from swe_agent.sandbox.protocol import AbstractSandbox
from swe_agent.tools.base import BaseTool, ToolResult


class ViewFileInput(BaseModel):
    """Input arguments for view_file."""
    path: str = Field(description="Relative path to the file within the repository")
    start_line: int = Field(default=1, ge=1, description="1-indexed line number to start viewing from")
    line_count: int = Field(default=100, ge=1, le=400, description="Number of lines to view (max 400)")


class ViewFileTool(BaseTool):
    """View file content with line numbers in a paginated window."""

    name = "view_file"
    description = (
        "View file content with line numbers in a windowed range. "
        "Always view code before editing to inspect exact whitespace, indentation, and context."
    )
    args_schema: Type[BaseModel] = ViewFileInput

    def execute(self, sandbox: AbstractSandbox, **kwargs) -> ToolResult:
        args = ViewFileInput(**kwargs)
        try:
            content = sandbox.read_file(args.path)
        except FileNotFoundError:
            return ToolResult(
                success=False,
                output=f"Error: File '{args.path}' does not exist in workspace."
            )
        except Exception as exc:
            return ToolResult(success=False, output=f"Error reading file '{args.path}': {str(exc)}")

        lines = content.splitlines()
        total_lines = len(lines)

        if total_lines == 0:
            return ToolResult(
                success=True,
                output=f"File '{args.path}' is empty (0 lines).",
                data={"total_lines": 0}
            )

        if args.start_line > total_lines:
            return ToolResult(
                success=False,
                output=(
                    f"Error: start_line ({args.start_line}) exceeds total lines in file "
                    f"({total_lines})."
                )
            )

        end_index = min(args.start_line - 1 + args.line_count, total_lines)
        window = lines[args.start_line - 1 : end_index]

        formatted_lines = []
        for idx, line in enumerate(window, start=args.start_line):
            formatted_lines.append(f"{idx:5d} | {line}")

        output_header = (
            f"--- File: {args.path} (Lines {args.start_line} - {end_index} of {total_lines}) ---\n"
        )
        return ToolResult(
            success=True,
            output=output_header + "\n".join(formatted_lines),
            data={
                "path": args.path,
                "start_line": args.start_line,
                "end_line": end_index,
                "total_lines": total_lines
            }
        )


class EditFileReplaceInput(BaseModel):
    """Input arguments for edit_file_replace."""
    path: str = Field(description="Relative path to the file to edit")
    old_str: str = Field(description="Exact unique text snippet to replace (must match exactly once)")
    new_str: str = Field(description="New text snippet to insert in place of old_str")


class EditFileReplaceTool(BaseTool):
    """Precision search-and-replace editor requiring exact unique matches."""

    name = "edit_file_replace"
    description = (
        "Replaces exact unique snippet `old_str` with `new_str` in the target file. "
        "The `old_str` must match EXACTLY ONE occurrence in the file. If it matches 0 "
        "or >1 times, the edit is rejected. Include surrounding lines for uniqueness."
    )
    args_schema: Type[BaseModel] = EditFileReplaceInput

    def execute(self, sandbox: AbstractSandbox, **kwargs) -> ToolResult:
        args = EditFileReplaceInput(**kwargs)
        try:
            content = sandbox.read_file(args.path)
        except FileNotFoundError:
            return ToolResult(
                success=False,
                output=f"Error: File '{args.path}' does not exist in workspace."
            )
        except Exception as exc:
            return ToolResult(success=False, output=f"Error reading file '{args.path}': {str(exc)}")

        matches = content.count(args.old_str)

        if matches == 0:
            return ToolResult(
                success=False,
                output=(
                    f"Edit Rejected: `old_str` was not found in '{args.path}'.\n"
                    "Ensure exact matching of whitespace, indentation, and newlines. "
                    "Use `view_file` to verify the current lines."
                )
            )

        if matches > 1:
            return ToolResult(
                success=False,
                output=(
                    f"Edit Rejected: `old_str` matches {matches} occurrences in '{args.path}'.\n"
                    "The target must be unique. Please include more surrounding context lines "
                    "in `old_str` to uniquely identify the location."
                )
            )

        # Exactly 1 match found -> perform atomic replacement
        new_content = content.replace(args.old_str, args.new_str, 1)
        try:
            sandbox.write_file(args.path, new_content)
        except Exception as exc:
            return ToolResult(success=False, output=f"Failed to write patch: {str(exc)}")

        return ToolResult(
            success=True,
            output=f"Successfully edited '{args.path}'. Exactly 1 unique match was replaced.",
            data={"path": args.path, "occurrences_replaced": 1}
        )


class CreateFileInput(BaseModel):
    """Input arguments for create_file."""
    path: str = Field(description="Relative path for the new file to create")
    content: str = Field(description="Full text content of the new file")
    overwrite: bool = Field(
        default=False,
        description="Whether to overwrite existing file if it already exists"
    )


class CreateFileTool(BaseTool):
    """Create a new file (such as a reproduction script or new test)."""

    name = "create_file"
    description = (
        "Create a new file in the repository. "
        "Use this to write reproduction scripts (e.g., reproduce_issue.py) or new modules."
    )
    args_schema: Type[BaseModel] = CreateFileInput

    def execute(self, sandbox: AbstractSandbox, **kwargs) -> ToolResult:
        args = CreateFileInput(**kwargs)
        try:
            # Check if file already exists
            try:
                sandbox.read_file(args.path)
                exists = True
            except FileNotFoundError:
                exists = False

            if exists and not args.overwrite:
                return ToolResult(
                    success=False,
                    output=(
                        f"Error: File '{args.path}' already exists. "
                        "Set `overwrite=True` if you explicitly intend to replace it, "
                        "or use `edit_file_replace` to modify it."
                    )
                )

            sandbox.write_file(args.path, args.content)
            return ToolResult(
                success=True,
                output=f"Successfully created file '{args.path}' ({len(args.content.splitlines())} lines).",
                data={"path": args.path, "bytes": len(args.content.encode('utf-8'))}
            )
        except Exception as exc:
            return ToolResult(success=False, output=f"Failed to create file '{args.path}': {str(exc)}")
