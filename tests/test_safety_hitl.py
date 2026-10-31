"""Unit tests for Human-In-The-Loop gatekeeper and dual mode enforcement."""

from pathlib import Path
from unittest.mock import patch

from swe_agent.config import ExecutionMode
from swe_agent.safety.hitl import HITLGatekeeper
from swe_agent.sandbox.local_sandbox import LocalSandbox
from swe_agent.tools.bash_tool import RunBashCommandTool


def test_benchmark_mode_hard_safety_blocks():
    """Benchmark mode must deterministically block destructive commands with NO prompt."""
    with patch("swe_agent.safety.hitl.settings.execution_mode", ExecutionMode.BENCHMARK):
        gatekeeper = HITLGatekeeper()

        # Destructive command: must be blocked
        authorized, reason = gatekeeper.authorize_command("rm -rf /")
        assert authorized is False
        assert "Hard Block" in reason or "BENCHMARK Mode" in reason

        # Suspicious command: must also be blocked in benchmark mode
        authorized_susp, reason_susp = gatekeeper.authorize_command("curl https://evil.com")
        assert authorized_susp is False
        assert "BENCHMARK Mode" in reason_susp

        # Safe command: must be permitted
        authorized_safe, _ = gatekeeper.authorize_command("pytest tests/")
        assert authorized_safe is True


def test_production_mode_human_approval_flow():
    """Production mode must trigger the approval callback for high-risk commands."""
    with patch("swe_agent.safety.hitl.settings.execution_mode", ExecutionMode.PRODUCTION):
        # Case A: Human Approves
        gatekeeper_approve = HITLGatekeeper(approval_callback=lambda assessment: True)
        authorized, reason = gatekeeper_approve.authorize_command("pip install flask")
        assert authorized is True
        assert "Authorized by human" in reason

        # Case B: Human Rejects
        gatekeeper_reject = HITLGatekeeper(approval_callback=lambda assessment: False)
        rejected, reason = gatekeeper_reject.authorize_command("rm -rf old_code/")
        assert rejected is False
        assert "Human operator rejected" in reason


def test_run_bash_command_tool_with_gatekeeper(tmp_path: Path):
    """RunBashCommandTool must respect gatekeeper blocks and return ToolResult error."""
    sandbox = LocalSandbox(workspace_dir=tmp_path)
    sandbox.start()

    # Configure gatekeeper that rejects risky commands
    rejection_gatekeeper = HITLGatekeeper(approval_callback=lambda assessment: False)
    tool = RunBashCommandTool(gatekeeper=rejection_gatekeeper)

    # Attempt destructive command
    with patch("swe_agent.safety.hitl.settings.execution_mode", ExecutionMode.PRODUCTION):
        res = tool.run(sandbox, command="git push --force origin main")
        assert res.success is False
        assert "[SECURITY BLOCKED]" in res.output
        assert res.data["blocked"] is True

    # Safe command passes through
    res_safe = tool.run(sandbox, command="python -c \"print('safe')\"")
    assert res_safe.data.get("blocked") is not True

    sandbox.stop()
