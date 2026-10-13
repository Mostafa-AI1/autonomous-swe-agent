"""Unit tests for ContextManager pinned grounding and sliding window compaction."""

from swe_agent.core.memory import ContextManager
from swe_agent.core.state import AgentPhase, AgentState


def test_pinned_initial_context():
    """Verify task description and instructions are pinned in context."""
    cm = ContextManager(system_prompt="You are a SWE agent.")
    cm.initialize_conversation(
        issue_statement="Fix AttributeError in session.py",
        repo_info="Repo: auth-service"
    )

    state = AgentState(
        task_id="t1",
        issue_statement="Fix AttributeError in session.py",
        repository="auth-service"
    )
    messages = cm.get_messages(state)

    # First message is system prompt with cognitive banner
    assert messages[0]["role"] == "system"
    assert "CURRENT AGENT COGNITIVE STATE" in messages[0]["content"]
    assert "FSM Phase: INITIALIZE" in messages[0]["content"]

    # Second message is pinned user instructions
    assert messages[1]["role"] == "user"
    assert "Fix AttributeError in session.py" in messages[1]["content"]
    assert "auth-service" in messages[1]["content"]


def test_dynamic_cognitive_state_updates():
    """Verify changes to active hypothesis and files are reflected in prompt."""
    cm = ContextManager(system_prompt="Base prompt.")
    state = AgentState(
        task_id="t2",
        issue_statement="bug",
        repository="repo",
        phase=AgentPhase.PATCH,
        active_hypothesis="Fixing regex in parser.py"
    )
    state.track_file_edit("src/parser.py")

    messages = cm.get_messages(state)
    sys_content = messages[0]["content"]

    assert "FSM Phase: PATCH" in sys_content
    assert "Fixing regex in parser.py" in sys_content
    assert "src/parser.py" in sys_content


def test_sliding_window_compaction_of_old_turns():
    """Verify that verbose tool outputs in older turns are pruned to save tokens."""
    cm = ContextManager(
        system_prompt="Base prompt.",
        recent_turns_to_keep=2,
        max_tool_summary_length=50
    )
    state = AgentState(task_id="t3", issue_statement="bug", repository="repo")

    # Add 6 interaction turns (12 messages)
    for i in range(6):
        cm.add_assistant_message(content=f"Step {i}")
        verbose_output = f"Tool return {i}: " + ("x" * 500)
        cm.add_tool_result(tool_call_id=f"call_{i}", tool_name="code_search", output=verbose_output)

    messages = cm.get_messages(state)

    # Oldest tool messages should have been compacted
    old_tool_msg = next(m for m in messages if m.get("tool_call_id") == "call_0")
    assert "... (truncated)]" in old_tool_msg["content"]
    assert len(old_tool_msg["content"]) < 200

    # Most recent tool messages should remain uncompacted at full length
    recent_tool_msg = next(m for m in messages if m.get("tool_call_id") == "call_5")
    assert "x" * 500 in recent_tool_msg["content"]
