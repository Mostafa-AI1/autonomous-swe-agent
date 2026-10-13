"""Unit tests for the 8-dimensional evaluation metrics engine."""

from benchmark.metrics import (
    TaskEvaluationResult,
    aggregate_benchmark_results,
    calculate_patch_delta,
    calculate_spurious_edits,
)


def test_calculate_patch_delta():
    """Verify added and deleted lines calculation from unified diff."""
    sample_diff = (
        "diff --git a/routing.py b/routing.py\n"
        "--- a/routing.py\n"
        "+++ b/routing.py\n"
        "@@ -1,3 +1,3 @@\n"
        "-    return route\n"
        "+    if route != '/':\n"
        "+        return route.rstrip('/')\n"
        "     return route\n"
    )
    added, deleted = calculate_patch_delta(sample_diff)
    assert added == 2
    assert deleted == 1


def test_calculate_spurious_edits():
    """Verify detection of files modified outside the expected bug scope."""
    modified = ["src/routing.py", "src/unrelated.py", "reproduce_issue.py"]
    expected = ["src/routing.py"]

    # 'reproduce_issue.py' should be ignored as a temporary reproduction script
    spurious = calculate_spurious_edits(modified, expected)
    assert len(spurious) == 1
    assert spurious == ["src/unrelated.py"]


def test_aggregate_benchmark_results_and_scoreboard():
    """Verify aggregated metrics and scoreboard string formatting."""
    task1 = TaskEvaluationResult(
        task_id="t1",
        resolved=True,
        regression=False,
        spurious_edits=[],
        lines_added=4,
        lines_deleted=1,
        tool_calls_total=5,
        duration_seconds=12.5,
        prompt_tokens=1500,
        completion_tokens=200,
        recovered=True
    )
    task2 = TaskEvaluationResult(
        task_id="t2",
        resolved=False,
        regression=True,
        spurious_edits=["extra.py"],
        lines_added=10,
        lines_deleted=2,
        tool_calls_total=8,
        duration_seconds=15.0,
        prompt_tokens=2000,
        completion_tokens=300,
        recovered=False
    )

    summary = aggregate_benchmark_results([task1, task2])

    assert summary.total_tasks == 2
    assert summary.resolved_tasks == 1
    assert summary.resolution_rate == 50.0  # 1/2 = 50.0%
    assert summary.regression_rate == 50.0  # 1/2 = 50.0%
    assert summary.recovery_rate == 50.0    # 1/2 = 50.0%
    assert summary.spurious_edits_count == 1
    assert summary.total_prompt_tokens == 3500
    assert summary.avg_tool_calls == 6.5

    scoreboard = summary.generate_scoreboard_table()
    assert "BENCHMARK SCOREBOARD" in scoreboard
    assert "Resolution Rate (Pass@1): 50.0%" in scoreboard
    assert "[PASS] t1" in scoreboard
    assert "[FAIL] t2" in scoreboard
