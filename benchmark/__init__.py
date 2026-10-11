"""Evaluation & Benchmark subsystem for autonomous SWE agent."""

from benchmark.evaluator import BenchmarkEvaluator
from benchmark.manifest import FROZEN_BENCHMARK_TASKS, BenchmarkTask
from benchmark.metrics import (
    BenchmarkSummary,
    TaskEvaluationResult,
    aggregate_benchmark_results,
    calculate_patch_delta,
    calculate_spurious_edits,
)
from benchmark.swe_bench_lite import SweBenchLiteAdapter, SweBenchLiteInstance

__all__ = [
    "BenchmarkTask",
    "FROZEN_BENCHMARK_TASKS",
    "TaskEvaluationResult",
    "BenchmarkSummary",
    "BenchmarkEvaluator",
    "calculate_patch_delta",
    "calculate_spurious_edits",
    "aggregate_benchmark_results",
    "SweBenchLiteAdapter",
    "SweBenchLiteInstance",
]
