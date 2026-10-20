"""Unit and API integration tests for the FastAPI Web Dashboard."""

from fastapi.testclient import TestClient
from swe_agent.web.server import app

client = TestClient(app)


def test_serve_dashboard_html():
    """Verify root endpoint serves the single-page application dashboard."""
    response = client.get("/")
    assert response.status_code == 200
    assert "Autonomous SWE Agent" in response.text
    assert "Goal-Directed FSM" in response.text
    assert "reproduce_issue" in response.text or "Run Instant Demo" in response.text


def test_api_config_endpoint():
    """Verify /api/config returns active system settings."""
    response = client.get("/api/config")
    assert response.status_code == 200
    data = response.json()
    assert "version" in data
    assert "primary_model" in data
    assert "execution_mode" in data
    assert "max_steps" in data


def test_api_benchmark_endpoint():
    """Verify /api/benchmark returns frozen benchmark tasks."""
    response = client.get("/api/benchmark")
    assert response.status_code == 200
    tasks = response.json()
    assert len(tasks) >= 3
    task_ids = [t["task_id"] for t in tasks]
    assert "swe-mini-01-url-routing" in task_ids


def test_api_trajectories_endpoint():
    """Verify /api/trajectories returns a list of session trajectories."""
    response = client.get("/api/trajectories")
    assert response.status_code == 200
    assert isinstance(response.json(), list)
