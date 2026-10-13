"""End-to-end unit tests for SweAgent execution loop with mocked model responses."""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock
from swe_agent.core.agent import SweAgent
from swe_agent.core.state import AgentPhase
from swe_agent.models.provider import ModelProvider, ModelResponse, ToolCall
from swe_agent.sandbox.local_sandbox import LocalSandbox
from swe_agent.telemetry.tracer import TrajectoryLogger
from swe_agent.tools.registry import create_default_registry


def test_agent_successful_solve_loop(tmp_path: Path):
    """Simulate a full 4-turn autonomous agent cycle to fix a bug."""
    # 1. Setup a test git repo in tmp_path
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "TestAgent"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "agent@test.com"], cwd=tmp_path, check=True)

    initial_code = (
        "def solve():\n"
        "    return 0\n"
    )
    test_code = (
        "from algo import solve\n"
        "assert solve() == 42\n"
        "print('PASS')\n"
    )

    (tmp_path / "algo.py").write_text(initial_code, encoding="utf-8")
    (tmp_path / "test_algo.py").write_text(test_code, encoding="utf-8")

    subprocess.run(["git", "add", "algo.py", "test_algo.py"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=tmp_path, check=True)

    # 2. Mock ModelProvider responses across 4 sequential turns
    mock_responses = [
        # Turn 1: Locate symbol
        ModelResponse(
            content="I will locate the solve function in the repository.",
            tool_calls=[
                ToolCall(id="call_1", name="find_symbol", arguments={"name": "solve", "symbol_type": "function"})
            ]
        ),
        # Turn 2: Apply patch
        ModelResponse(
            content="I will update solve() to return 42.",
            tool_calls=[
                ToolCall(
                    id="call_2",
                    name="edit_file_replace",
                    arguments={
                        "path": "algo.py",
                        "old_str": "def solve():\n    return 0",
                        "new_str": "def solve():\n    return 42"
                    }
                )
            ]
        ),
        # Turn 3: Verify with test
        ModelResponse(
            content="I will run the test script to verify.",
            tool_calls=[
                ToolCall(
                    id="call_3",
                    name="run_bash_command",
                    arguments={"command": "python test_algo.py"}
                )
            ]
        ),
        # Turn 4: Conclude task
        ModelResponse(
            content="The test passed! I am ready to conclude.",
            tool_calls=[
                ToolCall(
                    id="call_4",
                    name="conclude_task",
                    arguments={
                        "success": True,
                        "explanation": "Updated solve() to return 42; verified with test_algo.py."
                    }
                )
            ]
        ),
    ]

    mock_provider = MagicMock(spec=ModelProvider)
    mock_provider.generate.side_effect = mock_responses

    sandbox = LocalSandbox(workspace_dir=tmp_path)
    sandbox.start()

    trajectory_dir = tmp_path / "trajectories"
    tracer = TrajectoryLogger(trajectory_dir=trajectory_dir)

    agent = SweAgent(
        sandbox=sandbox,
        model_provider=mock_provider,
        tool_registry=create_default_registry(),
        tracer=tracer,
        max_steps=10
    )

    state = agent.solve_issue(
        task_id="mock-task-1",
        issue_statement="solve() should return 42 instead of 0",
        repo_info="Test Math Repo"
    )

    # 3. Assertions on completed state
    assert state.completed is True
    assert state.success is True
    assert state.phase == AgentPhase.COMPLETE
    assert "algo.py" in state.modified_files
    assert state.step_count == 4
    assert "+    return 42" in state.final_patch
    assert "-    return 0" in state.final_patch

    # 4. Verify trajectory was written
    traj_files = list(trajectory_dir.glob("*.jsonl"))
    assert len(traj_files) == 1

    sandbox.stop()
