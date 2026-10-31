"""Automated benchmark evaluator running tasks against headless agent and scoring metrics."""

import contextlib
import logging
import subprocess
import time
from pathlib import Path

from benchmark.manifest import FROZEN_BENCHMARK_TASKS, BenchmarkTask
from benchmark.metrics import (
    BenchmarkSummary,
    TaskEvaluationResult,
    aggregate_benchmark_results,
    calculate_patch_delta,
    calculate_spurious_edits,
)
from swe_agent.config import ExecutionMode, settings
from swe_agent.core.agent import SweAgent
from swe_agent.models.provider import ModelProvider
from swe_agent.sandbox.local_sandbox import LocalSandbox
from swe_agent.telemetry.tracer import TrajectoryLogger
from swe_agent.tools.registry import create_default_registry

logger = logging.getLogger(__name__)


class BenchmarkEvaluator:
    """Evaluates the autonomous agent against frozen benchmark tasks."""

    def __init__(
        self,
        base_eval_dir: Path = Path("./eval_workspaces"),
        results_dir: Path = Path("./eval_results")
    ):
        self.base_eval_dir = Path(base_eval_dir).resolve()
        self.results_dir = Path(results_dir).resolve()
        self.base_eval_dir.mkdir(parents=True, exist_ok=True)
        self.results_dir.mkdir(parents=True, exist_ok=True)

    def evaluate_task(
        self,
        task: BenchmarkTask,
        model_provider: ModelProvider | None = None
    ) -> TaskEvaluationResult:
        """Run single benchmark task in headless benchmark mode and compute 8 metrics."""
        task_dir = self.base_eval_dir / task.task_id
        task_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"--- Launching Benchmark Task: {task.task_id} ---")

        # 1. Setup repository baseline files
        for rel_path, content in task.initial_files.items():
            f_path = task_dir / rel_path
            f_path.parent.mkdir(parents=True, exist_ok=True)
            f_path.write_text(content, encoding="utf-8")

        # 2. Initialize git repository
        try:
            subprocess.run(["git", "init"], cwd=task_dir, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.name", "BenchmarkEval"], cwd=task_dir, check=True)
            subprocess.run(["git", "config", "user.email", "eval@benchmark.com"], cwd=task_dir, check=True)
            subprocess.run(["git", "add", "."], cwd=task_dir, check=True, capture_output=True)
            subprocess.run(["git", "commit", "-m", "Baseline state"], cwd=task_dir, check=True, capture_output=True)
        except Exception as git_err:
            logger.warning(f"Git init warning in benchmark eval: {git_err}")

        # 3. Instantiate sandboxed agent in BENCHMARK mode
        sandbox = LocalSandbox(workspace_dir=task_dir)
        sandbox.start()

        # Enforce headless BENCHMARK execution mode
        original_mode = settings.execution_mode
        settings.execution_mode = ExecutionMode.BENCHMARK

        tracer = TrajectoryLogger(trajectory_dir=self.results_dir / "trajectories")
        agent = SweAgent(
            sandbox=sandbox,
            model_provider=model_provider or ModelProvider(),
            tool_registry=create_default_registry(),
            tracer=tracer
        )

        start_time = time.perf_counter()
        agent_state = agent.solve_issue(
            task_id=task.task_id,
            issue_statement=task.issue_statement,
            repo_info=task.repo_name
        )
        duration = time.perf_counter() - start_time

        # Restore execution mode
        settings.execution_mode = original_mode

        # 4. Strict Evaluation Verification Step (Quarantined Test Injection)
        # Inject ground-truth verification tests into sandbox
        for rel_path, test_content in task.verification_test_files.items():
            sandbox.write_file(rel_path, test_content)

        # Run verification command
        verif_res = sandbox.execute(task.test_command)
        resolved = verif_res.is_success and "VERIFICATION SUCCESSFUL" in verif_res.combined_output

        # Clean up verification test files
        for rel_path in task.verification_test_files:
            with contextlib.suppress(Exception):
                (task_dir / rel_path).unlink(missing_ok=True)

        # 5. Check for regression in pre-existing tests (if any)
        existing_test_res = sandbox.execute("python -m pytest tests/")
        regression = (existing_test_res.exit_code != 0) if (task_dir / "tests").exists() else False

        sandbox.stop()

        # 6. Compute 8 metrics
        added, deleted = calculate_patch_delta(agent_state.final_patch)
        spurious = calculate_spurious_edits(agent_state.modified_files, task.expected_files_to_touch)

        # Tool breakdown calculation
        tool_counts: dict[str, int] = {}
        # In mock or real run, step_count reflects turns taken
        tool_total = agent_state.step_count

        return TaskEvaluationResult(
            task_id=task.task_id,
            resolved=resolved,
            regression=regression,
            spurious_edits=spurious,
            lines_added=added,
            lines_deleted=deleted,
            tool_calls_total=tool_total,
            tool_calls_breakdown=tool_counts,
            duration_seconds=round(duration, 2),
            prompt_tokens=agent.model_provider.total_prompt_tokens,
            completion_tokens=agent.model_provider.total_completion_tokens,
            estimated_cost_usd=0.0,  # Zero-cost on free tier / local models
            recovered=(agent_state.recovery_attempts > 0 and resolved)
        )

    def run_benchmark(
        self,
        tasks: list[BenchmarkTask] | None = None,
        model_provider: ModelProvider | None = None
    ) -> BenchmarkSummary:
        """Run full evaluation suite across all tasks and generate scoreboard."""
        selected_tasks = tasks or FROZEN_BENCHMARK_TASKS
        results: list[TaskEvaluationResult] = []

        logger.info(f"Starting custom SWE-bench-inspired evaluation across {len(selected_tasks)} tasks...")

        for task in selected_tasks:
            task_res = self.evaluate_task(task, model_provider=model_provider)
            results.append(task_res)

        summary = aggregate_benchmark_results(results)

        # Export summary JSON
        summary_path = self.results_dir / "benchmark_summary.json"
        summary_path.write_text(summary.model_dump_json(indent=2), encoding="utf-8")
        logger.info(f"Benchmark summary exported to: {summary_path}")

        return summary
