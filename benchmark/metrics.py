"""8-Dimensional Benchmark Metrics Engine for autonomous SWE agent evaluation."""

from pydantic import BaseModel, Field


class TaskEvaluationResult(BaseModel):
    """Evaluation result for an individual benchmark task across 8 dimensions."""

    task_id: str
    resolved: bool = Field(description="Pass@1: Did verification tests pass?")
    regression: bool = Field(default=False, description="Were pre-existing tests broken?")
    spurious_edits: list[str] = Field(
        default_factory=list,
        description="Files modified outside the bug's functional scope"
    )
    lines_added: int = Field(default=0, description="Lines added in git patch")
    lines_deleted: int = Field(default=0, description="Lines removed in git patch")
    tool_calls_total: int = Field(default=0, description="Total tool invocations")
    tool_calls_breakdown: dict[str, int] = Field(default_factory=dict)
    duration_seconds: float = Field(default=0.0, description="Wall-clock execution latency")
    prompt_tokens: int = Field(default=0, description="Total input tokens consumed")
    completion_tokens: int = Field(default=0, description="Total output tokens consumed")
    estimated_cost_usd: float = Field(default=0.0, description="Estimated model API cost")
    recovered: bool = Field(
        default=False,
        description="Whether agent self-corrected after an initial test failure or rollback"
    )

    @property
    def has_spurious_edits(self) -> bool:
        return len(self.spurious_edits) > 0


class BenchmarkSummary(BaseModel):
    """Aggregated scoreboard summarizing performance across all benchmark tasks."""

    total_tasks: int = 0
    resolved_tasks: int = 0
    resolution_rate: float = Field(default=0.0, description="pass@1 percentage (0.0 to 100.0)")
    regression_rate: float = Field(default=0.0, description="percentage of regressions introduced")
    avg_duration_seconds: float = 0.0
    avg_tool_calls: float = 0.0
    avg_lines_changed: float = 0.0
    spurious_edits_count: int = 0
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_cost_usd: float = 0.0
    recovery_count: int = 0
    recovery_rate: float = 0.0
    task_results: list[TaskEvaluationResult] = Field(default_factory=list)

    def generate_scoreboard_table(self) -> str:
        """Format an ASCII / Markdown scoreboard for terminal and portfolio reports."""
        lines = [
            "==========================================================================",
            "                 AUTONOMOUS SWE AGENT - BENCHMARK SCOREBOARD               ",
            "==========================================================================",
            f"• Tasks Evaluated:          {self.total_tasks}",
            f"• Resolution Rate (Pass@1): {self.resolution_rate:.1f}% ({self.resolved_tasks}/{self.total_tasks})",
            f"• Regression Rate:          {self.regression_rate:.1f}%",
            f"• Recovery Rate:            {self.recovery_rate:.1f}% ({self.recovery_count} self-corrections)",
            f"• Spurious Edits Total:     {self.spurious_edits_count} unexpected file(s)",
            f"• Avg Tool Calls per Task:  {self.avg_tool_calls:.1f}",
            f"• Avg Wall-Clock Latency:   {self.avg_duration_seconds:.2f}s",
            f"• Avg Patch Delta:          {self.avg_lines_changed:.1f} lines (+/-)",
            f"• Total Tokens (In/Out):    {self.total_prompt_tokens:,} / {self.total_completion_tokens:,}",
            f"• Total Estimated Cost:     ${self.total_cost_usd:.4f}",
            "==========================================================================",
            "TASK BREAKDOWN:",
        ]
        for res in self.task_results:
            status = "PASS" if res.resolved else "FAIL"
            delta = f"+{res.lines_added}/-{res.lines_deleted}"
            lines.append(
                f"  [{status:<4}] {res.task_id:<28} | {res.duration_seconds:5.1f}s | "
                f"Tools: {res.tool_calls_total:2d} | Delta: {delta:<8} | Spurious: {len(res.spurious_edits)}"
            )
        lines.append("==========================================================================")
        return "\n".join(lines)


def calculate_patch_delta(unified_diff: str) -> tuple[int, int]:
    """Parse unified diff string and return (lines_added, lines_deleted)."""
    added = 0
    deleted = 0
    for line in unified_diff.splitlines():
        if line.startswith("+++") or line.startswith("---"):
            continue
        elif line.startswith("+"):
            added += 1
        elif line.startswith("-"):
            deleted += 1
    return added, deleted


def calculate_spurious_edits(
    modified_files: list[str], expected_files: list[str]
) -> list[str]:
    """Identify files modified by the agent that were not in the expected scope."""
    expected_set = {f.replace("\\", "/").strip().lower() for f in expected_files}
    spurious = []
    for f in modified_files:
        norm_f = f.replace("\\", "/").strip().lower()
        # Ignore temporary reproduction scripts written by the agent
        if "repro" in norm_f or "temp_" in norm_f:
            continue
        if norm_f not in expected_set:
            spurious.append(f)
    return spurious


def aggregate_benchmark_results(results: list[TaskEvaluationResult]) -> BenchmarkSummary:
    """Aggregate individual task results into a consolidated BenchmarkSummary."""
    total = len(results)
    if total == 0:
        return BenchmarkSummary()

    resolved_count = sum(1 for r in results if r.resolved)
    regression_count = sum(1 for r in results if r.regression)
    spurious_total = sum(len(r.spurious_edits) for r in results)
    recoveries = sum(1 for r in results if r.recovered)

    total_duration = sum(r.duration_seconds for r in results)
    total_tools = sum(r.tool_calls_total for r in results)
    total_delta = sum(r.lines_added + r.lines_deleted for r in results)
    total_prompt = sum(r.prompt_tokens for r in results)
    total_comp = sum(r.completion_tokens for r in results)
    total_cost = sum(r.estimated_cost_usd for r in results)

    return BenchmarkSummary(
        total_tasks=total,
        resolved_tasks=resolved_count,
        resolution_rate=round((resolved_count / total) * 100, 1),
        regression_rate=round((regression_count / total) * 100, 1),
        avg_duration_seconds=round(total_duration / total, 2),
        avg_tool_calls=round(total_tools / total, 1),
        avg_lines_changed=round(total_delta / total, 1),
        spurious_edits_count=spurious_total,
        total_prompt_tokens=total_prompt,
        total_completion_tokens=total_comp,
        total_cost_usd=round(total_cost, 4),
        recovery_count=recoveries,
        recovery_rate=round((recoveries / total) * 100, 1),
        task_results=results
    )
