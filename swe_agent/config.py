"""Configuration management and execution modes for Autonomous SWE Agent."""

from enum import Enum
from pathlib import Path
from typing import Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ExecutionMode(str, Enum):
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
        description="Operational mode: production (with HITL) or benchmark (fully autonomous)"
    )

    # Model Configuration
    # Cloud Default: Gemini 3.8 Flash (rapid reasoning, free-tier accessible, high context)
    primary_model: str = Field(
        default="gemini/gemini-3.8-flash",
        description="Primary model identifier (compatible with LiteLLM)"
    )
    # Local Default: Qwen3-Coder (local open-source coding model via Ollama/vLLM)
    fallback_model: str = Field(
        default="ollama/qwen3-coder:latest",
        description="Local fallback coding model when offline or testing without cloud API"
    )
    gemini_api_key: Optional[str] = Field(
        default=None,
        description="API key for Google Gemini / AI Studio"
    )
    ollama_base_url: str = Field(
        default="http://localhost:11434",
        description="Base URL for local Ollama instance"
    )
    model_temperature: float = Field(
        default=0.0,
        description="Greedy decoding (0.0) ensures deterministic and reproducible code edits"
    )

    # Sandbox Isolation Settings
    sandbox_image: str = Field(
        default="swe-sandbox:latest",
        description="Docker image tag used for command and test execution"
    )
    sandbox_timeout_seconds: int = Field(
        default=120,
        description="Hard timeout for terminal execution inside sandbox"
    )
    sandbox_memory_limit: str = Field(
        default="2g",
        description="Memory limit for the sandbox container"
    )
    sandbox_cpu_limit: float = Field(
        default=2.0,
        description="CPU core limit for the sandbox container"
    )
    sandbox_workdir: str = Field(
        default="/workspace",
        description="Working directory inside the sandbox container"
    )

    # Agent Loop Bounds
    max_steps: int = Field(
        default=30,
        description="Maximum reasoning steps before halting to avoid runaway token loops"
    )
    max_tool_output_lines: int = Field(
        default=120,
        description="Maximum lines returned by terminal/tools before smart truncation"
    )

    # Telemetry & Trajectories (Incremental: JSONL first)
    trajectory_dir: Path = Field(
        default=Path("./trajectories"),
        description="Directory where structured JSONL trajectories are written"
    )
    log_level: str = Field(
        default="INFO",
        description="Logging level (DEBUG, INFO, WARNING, ERROR)"
    )
    enable_langfuse: bool = Field(
        default=False,
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
