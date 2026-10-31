"""Conclusion tool allowing the agent to formally signal task completion."""


from pydantic import BaseModel, Field

from swe_agent.sandbox.protocol import AbstractSandbox
from swe_agent.tools.base import BaseTool, ToolResult


class ConcludeTaskInput(BaseModel):
    """Input arguments for conclude_task."""
    success: bool = Field(description="Whether the bug was resolved and verified")
    explanation: str = Field(description="Summary of the root cause, changes made, and verification results")


class ConcludeTaskTool(BaseTool):
    """Signals that the task has reached its final state and provides summary."""

    name = "conclude_task"
    description = (
        "Call this tool when you have finished the task (or determined it cannot be completed). "
        "Summarize the root cause, the fix applied, and how you verified it."
    )
    args_schema: type[BaseModel] = ConcludeTaskInput

    def execute(self, sandbox: AbstractSandbox, **kwargs) -> ToolResult:
        args = ConcludeTaskInput(**kwargs)
        status_str = "SUCCESS" if args.success else "FAILURE"
        return ToolResult(
            success=True,
            output=f"Task conclusion recorded [{status_str}]: {args.explanation}",
            data={"concluded": True, "success": args.success, "explanation": args.explanation}
        )
