"""Git tools enabling diff inspection, status checks, and self-recovery rollback."""

from typing import Optional, Type
from pydantic import BaseModel, Field

from swe_agent.sandbox.protocol import AbstractSandbox
from swe_agent.tools.base import BaseTool, ToolResult


class GitDiffInput(BaseModel):
    """Input arguments for git_diff."""
    path: Optional[str] = Field(
        default=None,
        description="Optional specific file or directory to inspect diff for. Defaults to entire repository."
    )


class GitDiffTool(BaseTool):
    """Inspect current unstaged and staged git changes."""

    name = "git_diff"
    description = (
        "View the unified git diff of all changes made so far. "
        "Always call this before concluding a task to verify patch cleanliness."
    )
    args_schema: Type[BaseModel] = GitDiffInput

    def execute(self, sandbox: AbstractSandbox, **kwargs) -> ToolResult:
        args = GitDiffInput(**kwargs)
        cmd = f"git diff {args.path}" if args.path else "git diff"
        res = sandbox.execute(cmd)

        if not res.is_success:
            return ToolResult(
                success=False,
                output=f"Error executing git diff: {res.stderr}"
            )

        diff_text = res.stdout.strip()
        if not diff_text:
            return ToolResult(
                success=True,
                output="Working tree clean: No git differences detected.",
                data={"has_diff": False, "diff": ""}
            )

        return ToolResult(
            success=True,
            output=diff_text,
            data={"has_diff": True, "diff": diff_text}
        )


class GitStatusInput(BaseModel):
    """Input arguments for git_status."""
    pass


class GitStatusTool(BaseTool):
    """Check working tree status (modified, untracked, or deleted files)."""

    name = "git_status"
    description = (
        "Check git status to see which files are modified, untracked, or staged."
    )
    args_schema: Type[BaseModel] = GitStatusInput

    def execute(self, sandbox: AbstractSandbox, **kwargs) -> ToolResult:
        res = sandbox.execute("git status --short")

        if not res.is_success:
            return ToolResult(
                success=False,
                output=f"Error running git status: {res.stderr}"
            )

        output = res.stdout.strip()
        if not output:
            return ToolResult(
                success=True,
                output="Clean repository state (no modified or untracked files).",
                data={"dirty": False}
            )

        return ToolResult(
            success=True,
            output=f"Repository status:\n{output}",
            data={"dirty": True, "raw_status": output}
        )


class GitRestoreInput(BaseModel):
    """Input arguments for git_restore."""
    path: str = Field(
        description="Path of the file to restore/revert to HEAD, or '.' to revert all uncommitted changes"
    )


class GitRestoreTool(BaseTool):
    """Roll back uncommitted modifications to recover from failed patches."""

    name = "git_restore"
    description = (
        "Revert uncommitted modifications to a file or the entire repository. "
        "Use this self-recovery tool when an edit fails tests and you want to start fresh."
    )
    args_schema: Type[BaseModel] = GitRestoreInput

    def execute(self, sandbox: AbstractSandbox, **kwargs) -> ToolResult:
        args = GitRestoreInput(**kwargs)
        # Supports modern git restore with fallback to git checkout
        cmd = f"git restore {args.path} || git checkout -- {args.path}"
        res = sandbox.execute(cmd)

        if not res.is_success:
            return ToolResult(
                success=False,
                output=f"Failed to restore '{args.path}': {res.stderr}"
            )

        return ToolResult(
            success=True,
            output=f"Successfully restored '{args.path}' to clean git state.",
            data={"path": args.path, "restored": True}
        )
