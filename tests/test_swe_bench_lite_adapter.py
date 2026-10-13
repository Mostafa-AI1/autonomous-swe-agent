"""Unit tests for SWE-bench Lite adapter and predictions export."""

import json
from pathlib import Path
from benchmark.swe_bench_lite import SweBenchLiteAdapter, SweBenchLiteInstance


def test_swe_bench_lite_instance_translation():
    """Verify official SWE-bench Lite record converts to quarantined BenchmarkTask."""
    raw_instance = SweBenchLiteInstance(
        instance_id="django__django-11099",
        repo="django/django",
        base_commit="b8a21f7c89a",
        problem_statement="Username validator regex allows trailing newlines",
        patch="diff --git a/validators.py b/validators.py\n...",
        test_patch="diff --git a/tests/test_validators.py...",
        FAIL_TO_PASS=["tests.auth_tests.test_validators.TestUsernameValidators.test_trailing_newline"],
        PASS_TO_PASS=["tests.auth_tests.test_validators.TestUsernameValidators.test_standard_username"],
        version="3.0"
    )

    task = SweBenchLiteAdapter.to_benchmark_task(raw_instance)

    assert task.task_id == "django__django-11099"
    assert task.repo_name == "django/django"
    assert task.base_commit == "b8a21f7c89a"
    assert "Username validator regex" in task.issue_statement
    assert "test_trailing_newline" in task.test_command

    # Invariant: Gold patch must NOT be included in initial files
    assert len(task.initial_files) == 0


def test_official_predictions_export(tmp_path: Path):
    """Verify export format matches official SWE-bench prediction schema."""
    eval_results = [
        {
            "task_id": "sympy__sympy-18057",
            "final_patch": "diff --git a/sympy/core/expr.py b/sympy/core/expr.py\n..."
        }
    ]

    output_file = tmp_path / "predictions.jsonl"
    SweBenchLiteAdapter.export_official_predictions(
        eval_results=eval_results,
        output_path=output_file,
        model_name="swe-agent-gemini-3.8-flash"
    )

    assert output_file.exists()
    lines = output_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1

    entry = json.loads(lines[0])
    assert entry["instance_id"] == "sympy__sympy-18057"
    assert entry["model_name_or_path"] == "swe-agent-gemini-3.8-flash"
    assert "diff --git" in entry["model_patch"]
