"""FastAPI Web Server powering the Interactive Web Dashboard & Portfolio Demo."""

import json
import logging
import time
from pathlib import Path
from typing import Any, Optional

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from swe_agent import __version__
from swe_agent.config import ExecutionMode, settings
from swe_agent.core.agent import SweAgent
from swe_agent.models.provider import ModelProvider
from swe_agent.sandbox.local_sandbox import LocalSandbox
from swe_agent.telemetry.tracer import TrajectoryLogger
from swe_agent.tools.registry import create_default_registry
from benchmark.manifest import FROZEN_BENCHMARK_TASKS

logger = logging.getLogger(__name__)

# Base static paths
WEB_DIR = Path(__file__).parent.resolve()
STATIC_DIR = WEB_DIR / "static"

app = FastAPI(
    title="Autonomous SWE Agent - Web Dashboard",
    version=__version__,
    description="Interactive Web UI and Portfolio Demonstration for Autonomous SWE Agent"
)

# Enable CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static assets
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


class TaskRunRequest(BaseModel):
    """Payload to dispatch an agent run via API."""
    task_id: str = Field(default="web-task-01")
    issue_statement: str
    repo_path: str = Field(default=".")
    mode: str = Field(default="benchmark")
    model_override: Optional[str] = None


@app.get("/")
async def serve_dashboard():
    """Serve the single-page application dashboard."""
    index_file = STATIC_DIR / "index.html"
    if not index_file.exists():
        raise HTTPException(status_code=404, detail="Dashboard index.html not found.")
    return FileResponse(str(index_file))


@app.get("/api/config")
async def get_config() -> dict[str, Any]:
    """Retrieve system configuration and active model information."""
    return {
        "version": __version__,
        "execution_mode": settings.execution_mode.value,
        "primary_model": settings.primary_model,
        "fallback_model": settings.fallback_model,
        "max_steps": settings.max_steps,
        "truncation_limit": settings.max_tool_output_lines,
        "sandbox_image": settings.sandbox_image,
        "trajectories_dir": str(settings.trajectory_dir),
    }


@app.get("/api/benchmark")
async def get_benchmark_tasks() -> list[dict[str, Any]]:
    """Return frozen benchmark tasks and descriptions."""
    return [
        {
            "task_id": t.task_id,
            "repo_name": t.repo_name,
            "issue_statement": t.issue_statement,
            "expected_files": t.expected_files_to_touch,
            "test_command": t.test_command
        }
        for t in FROZEN_BENCHMARK_TASKS
    ]


@app.get("/api/trajectories")
async def list_trajectories() -> list[dict[str, Any]]:
    """List recorded JSONL trajectory sessions."""
    traj_dir = settings.trajectory_dir
    if not traj_dir.exists():
        return []

    trajectories = []
    for f in sorted(traj_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True):
        trajectories.append({
            "filename": f.name,
            "path": str(f),
            "size_bytes": f.stat().st_size,
            "modified_at": f.stat().st_mtime
        })
    return trajectories


@app.get("/api/trajectories/{filename}")
async def get_trajectory_detail(filename: str) -> list[dict[str, Any]]:
    """Fetch step-by-step history from a trajectory file."""
    file_path = (settings.trajectory_dir / filename).resolve()
    if not file_path.exists() or not file_path.is_relative_to(settings.trajectory_dir.resolve()):
        raise HTTPException(status_code=404, detail="Trajectory file not found.")

    lines = file_path.read_text(encoding="utf-8").strip().splitlines()
    return [json.loads(line) for line in lines if line.strip()]


@app.post("/api/run")
async def run_task(req: TaskRunRequest) -> dict[str, Any]:
    """Execute the autonomous agent on the assigned repository task."""
    target_dir = Path(req.repo_path).resolve()
    if not target_dir.exists():
        target_dir.mkdir(parents=True, exist_ok=True)

    sandbox = LocalSandbox(workspace_dir=target_dir)
    sandbox.start()

    exec_mode = ExecutionMode.BENCHMARK if req.mode.lower() == "benchmark" else ExecutionMode.PRODUCTION
    original_mode = settings.execution_mode
    settings.execution_mode = exec_mode

    tracer = TrajectoryLogger()
    model_provider = ModelProvider(primary_model=req.model_override) if req.model_override else ModelProvider()
    agent = SweAgent(
        sandbox=sandbox,
        model_provider=model_provider,
        tool_registry=create_default_registry(),
        tracer=tracer
    )

    start_time = time.perf_counter()
    try:
        state = agent.solve_issue(
            task_id=req.task_id,
            issue_statement=req.issue_statement,
            repo_info=str(target_dir)
        )
        duration = time.perf_counter() - start_time

        return {
            "success": state.success,
            "task_id": state.task_id,
            "phase": state.phase.value,
            "conclusion": state.conclusion_summary,
            "steps_count": state.step_count,
            "modified_files": state.modified_files,
            "final_patch": state.final_patch,
            "duration_seconds": round(duration, 2),
            "total_tokens": model_provider.total_prompt_tokens + model_provider.total_completion_tokens
        }
    except Exception as exc:
        logger.error(f"Execution failed: {exc}", exc_info=True)
        return {
            "success": False,
            "error": str(exc),
            "task_id": req.task_id
        }
    finally:
        sandbox.stop()
        settings.execution_mode = original_mode


def start_server(host: str = "127.0.0.1", port: int = 8000, reload: bool = False):
    """Launch the Web Dashboard server using Uvicorn."""
    logger.info(f"Starting SWE Agent Dashboard at http://{host}:{port}")
    uvicorn.run("swe_agent.web.server:app", host=host, port=port, reload=reload)


if __name__ == "__main__":
    start_server()
