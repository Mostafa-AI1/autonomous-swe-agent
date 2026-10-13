"""Unit tests for the frozen benchmark manifest and quarantine invariants."""

from benchmark.manifest import FROZEN_BENCHMARK_TASKS, BenchmarkTask


def test_frozen_manifest_integrity():
    """Verify tasks have complete specs and frozen problem statements."""
    assert len(FROZEN_BENCHMARK_TASKS) >= 3

    for task in FROZEN_BENCHMARK_TASKS:
        assert isinstance(task, BenchmarkTask)
        assert task.task_id.startswith("swe-mini-")
        assert len(task.issue_statement) > 20
        assert len(task.test_command) > 0
        assert len(task.expected_files_to_touch) >= 1
        assert len(task.initial_files) >= 1
        assert len(task.verification_test_files) >= 1


def test_gold_patch_quarantine():
    """Verify that gold patches are not exposed inside the task initial files."""
    for task in FROZEN_BENCHMARK_TASKS:
        for file_path in task.initial_files.keys():
            assert "verification" not in file_path.lower()
            assert "gold" not in file_path.lower()
