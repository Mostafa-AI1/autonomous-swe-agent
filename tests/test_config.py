"""Unit tests for configuration and execution mode controls."""

from swe_agent.config import ExecutionMode, Settings


def test_default_settings():
    """Verify default models and production execution mode."""
    cfg = Settings()
    assert cfg.execution_mode == ExecutionMode.PRODUCTION
    assert cfg.is_production_mode is True
    assert cfg.is_benchmark_mode is False
    assert "gemini" in cfg.primary_model
    assert "qwen" in cfg.fallback_model
    assert cfg.max_steps == 30
    assert cfg.sandbox_timeout_seconds == 120


def test_benchmark_mode_switch():
    """Verify clean switch to headless benchmark mode."""
    cfg = Settings(execution_mode="benchmark")
    assert cfg.execution_mode == ExecutionMode.BENCHMARK
    assert cfg.is_benchmark_mode is True
    assert cfg.is_production_mode is False


def test_case_insensitive_execution_mode():
    """Verify parsing handles mixed casing."""
    cfg = Settings(execution_mode="PRODUCTION")
    assert cfg.execution_mode == ExecutionMode.PRODUCTION
