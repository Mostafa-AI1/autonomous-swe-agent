"""Sandboxed Bash execution tool with smart output truncation and timeout enforcement."""


from pydantic import BaseModel, Field

from swe_agent.safety.hitl import HITLGatekeeper
from swe_agent.sandbox.protocol import AbstractSandbox
from swe_agent.tools.base import BaseTool, ToolResult


class RunBashCommandInput(BaseModel):
    """Input arguments for run_bash_command."""
    command: str = Field(description="The shell command to execute inside the sandbox")
    timeout_seconds: int | None = Field(
        default=None,
        ge=5,
        le=600,
        description="Optional timeout in seconds (defaults to sandbox config limit)"
    )
    workdir: str | None = Field(
        default=None,
        description="Optional subdirectory within workspace to run command from"
    )


class RunBashCommandTool(BaseTool):
    """Execute shell commands inside the secure sandbox environment."""

    name = "run_bash_command"
    description = (
        "Execute a shell command inside the isolated sandbox (e.g., pytest, python, git). "
        "Captures exit code, stdout, and stderr with smart truncation to prevent context blowup."
    )
    args_schema: type[BaseModel] = RunBashCommandInput

    def __init__(self, gatekeeper: HITLGatekeeper | None = None):
        self.gatekeeper = gatekeeper or HITLGatekeeper()

    def execute(self, sandbox: AbstractSandbox, **kwargs) -> ToolResult:
        args = RunBashCommandInput(**kwargs)

        # Intercept command via safety gatekeeper (dual mode enforcement)
        authorized, feedback = self.gatekeeper.authorize_command(args.command)
        if not authorized:
            return ToolResult(
                success=False,
                output=f"[SECURITY BLOCKED]: {feedback}",
                data={"command": args.command, "blocked": True, "reason": feedback}
            )

        res = sandbox.execute(
            command=args.command,
            timeout_seconds=args.timeout_seconds,
            workdir=args.workdir
        )

        status_tag = f"[Exit Code: {res.exit_code} | Duration: {res.duration_seconds}s]"
        if res.timed_out:
            status_tag += " [TIMED OUT]"

        body = res.combined_output
        formatted_output = f"{status_tag}\n{body}"

        return ToolResult(
            success=res.is_success,
            output=formatted_output,
            data={
                "command": args.command,
                "exit_code": res.exit_code,
                "duration_seconds": res.duration_seconds,
                "timed_out": res.timed_out,
                "truncated": res.truncated
            }
        )
