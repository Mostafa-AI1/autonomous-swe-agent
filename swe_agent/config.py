"""Configuration management and execution modes for Autonomous SWE Agent."""

from enum import StrEnum
from pathlib import Path

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ExecutionMode(StrEnum):
    """Operational mode of the agent."""
    PRODUCTION = "production"  # Interactive CLI with Human-In-The-Loop (HITL) for risky actions
    BENCHMARK = "benchmark"    # Fully autonomous, zero-HITL, strict hard safety blocks


class Settings(BaseSettings):
    """Central configuration for model, sandbox, execution mode, and telemetry."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Execution Mode
    execution_mode: ExecutionMode = Field(
        default=ExecutionMode.PRODUCTION,
        validation_alias=AliasChoices("execution_mode", "swe_execution_mode"),
        description="Operational mode: production (with HITL) or benchmark (fully autonomous)"
    )

    # Model Configuration
    # Cloud Default: Gemini 3.8 Flash (rapid reasoning, free-tier accessible, high context)
    primary_model: str = Field(
        default="gemini/gemini-3.8-flash",
        validation_alias=AliasChoices("primary_model", "swe_primary_model"),
        description="Primary model identifier (compatible with LiteLLM)"
    )
    # Local Default: Qwen3-Coder (local open-source coding model via Ollama/vLLM)
    fallback_model: str = Field(
        default="ollama/qwen3-coder:latest",
        validation_alias=AliasChoices("fallback_model", "swe_fallback_model"),
        description="Local fallback coding model when offline or testing without cloud API"
    )
    gemini_api_key: str | None = Field(
        default=None,
        description="API key for Google Gemini / AI Studio"
    )
    ollama_base_url: str = Field(
        default="http://localhost:11434",
        validation_alias=AliasChoices("ollama_base_url", "swe_ollama_base_url"),
        description="Base URL for local Ollama instance"
    )
    model_temperature: float = Field(
        default=0.0,
        validation_alias=AliasChoices("model_temperature", "swe_model_temperature"),
        description="Greedy decoding (0.0) ensures deterministic and reproducible code edits"
    )

    # Sandbox Isolation Settings
    sandbox_image: str = Field(
        default="swe-sandbox:latest",
        validation_alias=AliasChoices("sandbox_image", "swe_sandbox_image"),
        description="Docker image tag used for command and test execution"
    )
    sandbox_timeout_seconds: int = Field(
        default=120,
        validation_alias=AliasChoices("sandbox_timeout_seconds", "swe_sandbox_timeout_seconds"),
        description="Hard timeout for terminal execution inside sandbox"
    )
    sandbox_memory_limit: str = Field(
        default="2g",
        validation_alias=AliasChoices("sandbox_memory_limit", "swe_sandbox_memory_limit"),
        description="Memory limit for the sandbox container"
    )
    sandbox_cpu_limit: float = Field(
        default=2.0,
        validation_alias=AliasChoices("sandbox_cpu_limit", "swe_sandbox_cpu_limit"),
        description="CPU core limit for the sandbox container"
    )
    sandbox_workdir: str = Field(
        default="/workspace",
        validation_alias=AliasChoices("sandbox_workdir", "swe_sandbox_workdir"),
        description="Working directory inside the sandbox container"
    )

    # Agent Loop Bounds
    max_steps: int = Field(
        default=30,
        validation_alias=AliasChoices("max_steps", "swe_max_steps"),
        description="Maximum reasoning steps before halting to avoid runaway token loops"
    )
    max_tool_output_lines: int = Field(
        default=120,
        validation_alias=AliasChoices("max_tool_output_lines", "swe_max_tool_output_lines"),
        description="Maximum lines returned by terminal/tools before smart truncation"
    )

    # Telemetry & Trajectories (Incremental: JSONL first)
    trajectory_dir: Path = Field(
        default=Path("./trajectories"),
        validation_alias=AliasChoices("trajectory_dir", "swe_trajectory_dir"),
        description="Directory where structured JSONL trajectories are written"
    )
    log_level: str = Field(
        default="INFO",
        validation_alias=AliasChoices("log_level", "swe_log_level"),
        description="Logging level (DEBUG, INFO, WARNING, ERROR)"
    )
    enable_langfuse: bool = Field(
        default=False,
        validation_alias=AliasChoices("enable_langfuse", "swe_enable_langfuse"),
        description="Whether to export traces to Langfuse (pluggable telemetry)"
    )

    @field_validator("execution_mode", mode="before")
    @classmethod
    def parse_execution_mode(cls, v: str | ExecutionMode) -> ExecutionMode:
        if isinstance(v, str):
            return ExecutionMode(v.lower().strip())
        return v

    @property
    def is_benchmark_mode(self) -> bool:
        """Check if running in headless benchmark mode."""
        return self.execution_mode == ExecutionMode.BENCHMARK

    @property
    def is_production_mode(self) -> bool:
        """Check if running in interactive production mode with HITL."""
        return self.execution_mode == ExecutionMode.PRODUCTION


# Singleton config instance
settings = Settings()
