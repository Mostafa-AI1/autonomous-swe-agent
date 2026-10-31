"""Unit tests for structured JSONL trajectory recording."""

import json
from pathlib import Path

from swe_agent.telemetry.tracer import TrajectoryLogger, TrajectoryStep


def test_trajectory_logger_lifecycle(tmp_path: Path):
    """Test full trajectory logging: metadata -> steps -> summary."""
    tracer = TrajectoryLogger(trajectory_dir=tmp_path)

    log_path = tracer.start_trajectory(
        task_id="test-issue-101",
        issue_statement="Fix ZeroDivisionError in math_utils.py",
        repository="mock/repo",
        execution_mode="benchmark"
    )
    assert log_path.exists()

    step = TrajectoryStep(
        step_number=1,
        phase="EXPLORE",
        thought="I should search for where division occurs",
        tool_calls=[{"name": "code_search", "args": {"query": "/"}}],
        tool_outputs=[{"result": "Found 2 files"}]
    )
    tracer.log_step(step)

    tracer.finalize(
        success=True,
        final_patch="diff --git a/math_utils.py...",
        metrics={"resolved": True, "steps_count": 1}
    )

    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 3

    meta = json.loads(lines[0])
    assert meta["type"] == "METADATA"
    assert meta["task_id"] == "test-issue-101"

    step_record = json.loads(lines[1])
    assert step_record["type"] == "STEP"
    assert step_record["phase"] == "EXPLORE"
    assert step_record["step_number"] == 1

    summary = json.loads(lines[2])
    assert summary["type"] == "SUMMARY"
    assert summary["success"] is True
