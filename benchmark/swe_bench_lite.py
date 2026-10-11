"""Adapter and conversion pipeline for the official SWE-bench Lite benchmark."""

import json
from pathlib import Path
from typing import Any, Optional
from pydantic import BaseModel, Field

from benchmark.manifest import BenchmarkTask


class SweBenchLiteInstance(BaseModel):
    """Schema representing an official SWE-bench Lite dataset record."""

    instance_id: str = Field(description="e.g. 'django__django-11099' or 'sympy__sympy-18057'")
    repo: str = Field(description="e.g. 'django/django'")
    base_commit: str = Field(description="Git commit SHA before PR was merged")
    problem_statement: str = Field(description="Issue text / problem description from GitHub issue")
    hints_text: Optional[str] = Field(default="", description="Optional conversation hints")
    patch: str = Field(description="Ground truth gold patch (quarantined)")
    test_patch: str = Field(description="Ground truth test patch (quarantined)")
    FAIL_TO_PASS: list[str] = Field(default_factory=list, description="Tests expected to fail before fix, pass after")
    PASS_TO_PASS: list[str] = Field(default_factory=list, description="Regression tests expected to pass throughout")
    version: str = Field(default="", description="Package version")


class SweBenchLiteAdapter:
    """Bridges official SWE-bench Lite dataset with our autonomous agent architecture."""

    @staticmethod
    def to_benchmark_task(instance: SweBenchLiteInstance) -> BenchmarkTask:
        """Translate official SWE-bench Lite record into our isolated BenchmarkTask.

        Guarantees that `instance.patch` (gold patch) is NEVER passed to the agent.
        """
        # Test command targets FAIL_TO_PASS tests
        test_cmd = f"pytest {' '.join(instance.FAIL_TO_PASS)}" if instance.FAIL_TO_PASS else "pytest tests/"

        return BenchmarkTask(
            task_id=instance.instance_id,
            repo_name=instance.repo,
            base_commit=instance.base_commit,
            issue_statement=instance.problem_statement,
            expected_files_to_touch=[],  # Can be parsed from instance.patch
            test_command=test_cmd,
            initial_files={},
            verification_test_files={}
        )

    @staticmethod
    def export_official_predictions(
        eval_results: list[dict[str, Any]],
        output_path: Path,
        model_name: str = "swe-agent-gemini-3.8-flash"
    ) -> None:
        """Export patches in the exact format required by official SWE-bench harness.

        Format:
        {
            "instance_id": "<instance_id>",
            "model_patch": "<git unified diff>",
            "model_name_or_path": "<model>"
        }
        """
        predictions: dict[str, dict[str, str]] = {}
        for r in eval_results:
            inst_id = r.get("task_id", "")
            patch_content = r.get("final_patch", "")
            if inst_id:
                predictions[inst_id] = {
                    "model_name_or_path": model_name,
                    "model_patch": patch_content
                }

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            for inst_id, pred in predictions.items():
                f.write(json.dumps({"instance_id": inst_id, **pred}) + "\n")
