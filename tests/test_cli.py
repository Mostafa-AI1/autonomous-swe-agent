"""Unit tests for the Typer and Rich CLI interface."""

import json
import re
from pathlib import Path

from typer.testing import CliRunner

from swe_agent.cli import app

runner = CliRunner(env={"NO_COLOR": "1", "TERM": "dumb"})


def _clean(output: str) -> str:
    """Strip ANSI color and styling escape sequences from CLI output."""
    return re.sub(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])", "", output)


def test_cli_version():
    """Verify version command outputs configuration table."""
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    out = _clean(result.output)
    assert "AUTONOMOUS SWE AGENT" in out
    assert "System Configuration" in out
    assert "gemini" in out


def test_cli_help():
    """Verify root help outputs available commands."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    out = _clean(result.output)
    assert "run" in out
    assert "benchmark" in out
    assert "inspect" in out
    assert "version" in out
    assert "demo" in out
    assert "web" in out


def test_cli_demo_help():
    """Verify demo command options."""
    result = runner.invoke(app, ["demo", "--help"])
    assert result.exit_code == 0
    out = _clean(result.output)
    assert "--port" in out


def test_cli_web_help():
    """Verify web command options."""
    result = runner.invoke(app, ["web", "--help"])
    assert result.exit_code == 0
    out = _clean(result.output)
    assert "--port" in out
    assert "--host" in out


def test_cli_run_help():
    """Verify run command options."""
    result = runner.invoke(app, ["run", "--help"])
    assert result.exit_code == 0
    out = _clean(result.output)
    assert "--issue" in out
    assert "--repo" in out
    assert "--mode" in out


def test_cli_benchmark_help():
    """Verify benchmark command options."""
    result = runner.invoke(app, ["benchmark", "--help"])
    assert result.exit_code == 0
    out = _clean(result.output)
    assert "--task" in out


def test_cli_inspect_trajectory(tmp_path: Path):
    """Verify inspect command parses and displays a .jsonl trajectory."""
    traj_file = tmp_path / "test_traj.jsonl"
    traj_lines = [
        json.dumps({
            "type": "METADATA",
            "task_id": "test-cli-task",
            "repository": "mock-repo",
            "execution_mode": "production",
            "started_at": "2026-10-03T12:00:00Z",
            "issue_statement": "Fix NullPointerException in processor"
        }),
        json.dumps({
            "type": "STEP",
            "step_number": 1,
            "phase": "EXPLORE",
            "thought": "Locating processor.py",
            "tool_calls": [{"name": "code_search", "arguments": {"query": "processor"}}],
            "tool_outputs": [{"output": "Found 1 file"}]
        }),
        json.dumps({
            "type": "SUMMARY",
            "success": True,
            "total_duration_seconds": 2.5,
            "metrics": {"resolved": True}
        })
    ]
    traj_file.write_text("\n".join(traj_lines), encoding="utf-8")

    result = runner.invoke(app, ["inspect", str(traj_file)])
    assert result.exit_code == 0
    assert "Trajectory Metadata" in result.output
    assert "test-cli-task" in result.output
    assert "Step 1" in result.output
    assert "code_search" in result.output
    assert "Final Outcome" in result.output
