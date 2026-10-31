"""Unit tests for AgentState and AgentPhase FSM transitions."""

from swe_agent.core.state import AgentPhase, AgentState


def test_state_initialization_and_budget():
    """Verify default state properties and step limit tracking."""
    state = AgentState(
        task_id="issue-42",
        issue_statement="Fix IndexOutOfBoundsException",
        repository="org/repo",
        max_steps=5
    )
    assert state.phase == AgentPhase.INITIALIZE
    assert state.step_count == 0
    assert state.remaining_steps == 5
    assert state.completed is False

    # Simulate steps
    state.record_step()
    state.record_step()
    assert state.step_count == 2
    assert state.remaining_steps == 3
    assert state.completed is False


def test_budget_exhaustion_transitions_to_failed():
    """Exhausting the step budget should trigger FAILED state."""
    state = AgentState(
        task_id="issue-99",
        issue_statement="Infinite loop bug",
        repository="org/repo",
        max_steps=2
    )
    state.record_step()  # step 1
    assert state.completed is False

    state.record_step()  # step 2 (max reached)
    assert state.completed is True
    assert state.success is False
    assert state.phase == AgentPhase.FAILED
    assert "Exhausted step budget" in state.conclusion_summary


def test_file_edit_tracking_uniqueness():
    """Track modified files without duplicates."""
    state = AgentState(
        task_id="issue-1",
        issue_statement="test",
        repository="repo"
    )
    state.track_file_edit("src/utils.py")
    state.track_file_edit("src/main.py")
    state.track_file_edit("src/utils.py")  # duplicate

    assert len(state.modified_files) == 2
    assert state.modified_files == ["src/utils.py", "src/main.py"]
