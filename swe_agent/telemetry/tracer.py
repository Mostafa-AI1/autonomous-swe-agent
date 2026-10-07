"""Incremental Observability: Zero-overhead JSONL Trajectory Recorder.

Records complete, deterministic trajectories of every agent thought,
tool execution, terminal output, and patch mutation for debugging and evals.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from pydantic import BaseModel, Field

from swe_agent.config import settings

logger = logging.getLogger(__name__)


class TrajectoryStep(BaseModel):
    """An atomic step in the agent's execution trajectory."""
    step_number: int
    phase: str = Field(description="FSM state: e.g. EXPLORE, REPRODUCE, PATCH, VERIFY")
    thought: Optional[str] = None
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    tool_outputs: list[dict[str, Any]] = Field(default_factory=list)
    duration_seconds: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class TrajectoryLogger:
    """Records agent trajectories to append-only JSONL files."""

    def __init__(self, trajectory_dir: Optional[Path] = None):
        self.trajectory_dir = trajectory_dir or settings.trajectory_dir
        self.trajectory_dir.mkdir(parents=True, exist_ok=True)
        self.active_file: Optional[Path] = None
        self.task_id: str = ""
        self.start_time: Optional[datetime] = None

    def start_trajectory(
        self,
        task_id: str,
        issue_statement: str,
        repository: str,
        execution_mode: str
    ) -> Path:
        """Initialize a new trajectory session."""
        self.task_id = task_id
        self.start_time = datetime.now(timezone.utc)
        timestamp_slug = self.start_time.strftime("%Y%m%d_%H%M%S")
        self.active_file = self.trajectory_dir / f"{task_id}_{timestamp_slug}.jsonl"

        header = {
            "type": "METADATA",
            "task_id": task_id,
            "repository": repository,
            "execution_mode": execution_mode,
            "issue_statement": issue_statement,
            "started_at": self.start_time.isoformat(),
            "primary_model": settings.primary_model,
        }
        self._append_line(header)
        logger.info(f"Trajectory logging initiated: {self.active_file}")
        return self.active_file

    def log_step(self, step: TrajectoryStep) -> None:
        """Record an individual reasoning and tool step."""
        if not self.active_file:
            raise RuntimeError("Trajectory session not started. Call start_trajectory() first.")

        payload = {
            "type": "STEP",
            **step.model_dump()
        }
        self._append_line(payload)

    def finalize(
        self,
        success: bool,
        final_patch: str,
        metrics: Optional[dict[str, Any]] = None
    ) -> None:
        """Finalize the trajectory record with outcome, patch diff, and summary metrics."""
        if not self.active_file:
            return

        end_time = datetime.now(timezone.utc)
        duration_total = (end_time - (self.start_time or end_time)).total_seconds()

        footer = {
            "type": "SUMMARY",
            "task_id": self.task_id,
            "ended_at": end_time.isoformat(),
            "total_duration_seconds": round(duration_total, 2),
            "success": success,
            "final_patch": final_patch,
            "metrics": metrics or {}
        }
        self._append_line(footer)
        logger.info(f"Trajectory finalized for {self.task_id}: success={success}")
        self.active_file = None

    def _append_line(self, data: dict[str, Any]) -> None:
        """Safely append a JSON line."""
        if not self.active_file:
            return
        with open(self.active_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(data, ensure_ascii=False) + "\n")
