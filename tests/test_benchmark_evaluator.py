"""Integration tests for automated BenchmarkEvaluator against frozen tasks."""

from pathlib import Path
from unittest.mock import MagicMock

from benchmark.evaluator import BenchmarkEvaluator
from benchmark.manifest import FROZEN_BENCHMARK_TASKS
from swe_agent.models.provider import ModelProvider, ModelResponse, ToolCall


def test_benchmark_evaluator_task_resolution(tmp_path: Path):
    """Verify that BenchmarkEvaluator sets up workspace, runs agent, and verifies fix."""
    task = FROZEN_BENCHMARK_TASKS[0]  # swe-mini-01-url-routing

    # Mock ModelProvider to apply the correct fix
    mock_responses = [
        # Turn 1: Inspect file
        ModelResponse(
            content="Viewing routing.py",
            tool_calls=[
                ToolCall(
                    id="call_1",
                    name="view_file",
                    arguments={"path": "src/routing.py", "start_line": 1, "line_count": 10}
                )
            ]
        ),
        # Turn 2: Apply the fix
        ModelResponse(
            content="Fixing trailing slash handling in normalize_route",
            tool_calls=[
                ToolCall(
                    id="call_2",
                    name="edit_file_replace",
                    arguments={
                        "path": "src/routing.py",
                        "old_str": "    # BUG: Does not strip trailing slash for non-root routes\n    return route",
                        "new_str": "    if route != '/' and route.endswith('/'):\n        return route.rstrip('/')\n    return route"
                    }
                )
            ]
        ),
        # Turn 3: Conclude task
        ModelResponse(
            content="Task verified and concluded.",
            tool_calls=[
                ToolCall(
                    id="call_3",
                    name="conclude_task",
                    arguments={"success": True, "explanation": "Stripped trailing slash for non-root routes."}
                )
            ]
        )
    ]

    mock_provider = MagicMock(spec=ModelProvider)
    mock_provider.generate.side_effect = mock_responses
    mock_provider.total_prompt_tokens = 500
    mock_provider.total_completion_tokens = 100

    evaluator = BenchmarkEvaluator(
        base_eval_dir=tmp_path / "workspaces",
        results_dir=tmp_path / "results"
    )

    result = evaluator.evaluate_task(task, model_provider=mock_provider)

    # Assertions on 8 metrics
    assert result.task_id == task.task_id
    assert result.resolved is True  # Ground truth test passed!
    assert result.regression is False
    assert len(result.spurious_edits) == 0
    assert result.lines_added >= 2
    assert result.lines_deleted >= 1
    assert result.tool_calls_total == 3
    assert result.duration_seconds > 0.0

    # Test full benchmark run with export (reset mock responses for second invocation)
    mock_provider.generate.side_effect = list(mock_responses)
    summary = evaluator.run_benchmark(tasks=[task], model_provider=mock_provider)
    assert summary.total_tasks == 1
    assert summary.resolved_tasks == 1
    assert summary.resolution_rate == 100.0

    summary_file = tmp_path / "results" / "benchmark_summary.json"
    assert summary_file.exists()
