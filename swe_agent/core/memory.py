"""Context management, pinned system grounding, and sliding-window compaction."""

from typing import Any
from swe_agent.core.state import AgentState


class ContextManager:
    """Manages LLM message history with context pinning and compaction.

    Key Concepts:
    - Pinned Grounding: The original issue description, repository context,
      and core safety rules are never evicted.
    - Dynamic Working Memory: Injects the current FSM phase, active hypothesis,
      and step budget directly into the prompt.
    - Sliding Window Compaction: Compacts older verbose tool execution outputs
      while keeping recent turns at full fidelity to prevent attention dilution.
    """

    def __init__(
        self,
        system_prompt: str,
        recent_turns_to_keep: int = 8,
        max_tool_summary_length: int = 250
    ):
        self.system_prompt = system_prompt
        self.recent_turns_to_keep = recent_turns_to_keep
        self.max_tool_summary_length = max_tool_summary_length
        self._history: list[dict[str, Any]] = []

    def initialize_conversation(self, issue_statement: str, repo_info: str) -> None:
        """Seed the conversation with pinned issue and repository context."""
        initial_user_prompt = (
            f"### ASSIGNED SOFTWARE ENGINEERING TASK\n\n"
            f"**Repository Context**:\n{repo_info}\n\n"
            f"**Issue Description**:\n{issue_statement}\n\n"
            f"### INSTRUCTIONS\n"
            f"1. Explore the codebase using `code_search` or `find_symbol` to locate root cause.\n"
            f"2. View the relevant files with `view_file`.\n"
            f"3. Create a reproduction script (e.g. `reproduce_issue.py`) with `create_file` to confirm the bug.\n"
            f"4. Apply minimal surgical edits using `edit_file_replace`.\n"
            f"5. Verify with `run_bash_command` (repro script + pytest).\n"
            f"6. Check `git_diff` before finishing and conclude with `conclude_task`."
        )
        self._history = [{"role": "user", "content": initial_user_prompt}]

    def add_assistant_message(
        self,
        content: str | None,
        tool_calls: list[dict[str, Any]] | None = None
    ) -> None:
        """Record model response (thought and tool calls)."""
        msg: dict[str, Any] = {"role": "assistant"}
        if content:
            msg["content"] = content
        if tool_calls:
            msg["tool_calls"] = tool_calls
        self._history.append(msg)

    def add_tool_result(self, tool_call_id: str, tool_name: str, output: str) -> None:
        """Record the output returned from a tool execution."""
        msg: dict[str, Any] = {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "name": tool_name,
            "content": output,
        }
        self._history.append(msg)

    def get_messages(self, state: AgentState) -> list[dict[str, Any]]:
        """Construct the prompt messages array with dynamic working memory injection."""
        # 1. Generate dynamic cognitive header
        dynamic_system_prompt = self._build_dynamic_system_prompt(state)

        # 2. Compact older tool messages to conserve tokens
        compacted_history = self._compact_history()

        return [
            {"role": "system", "content": dynamic_system_prompt},
            *compacted_history
        ]

    def _build_dynamic_system_prompt(self, state: AgentState) -> str:
        """Inject real-time FSM phase, hypothesis, and budget into system prompt."""
        status_banner = (
            f"\n\n================ CURRENT AGENT COGNITIVE STATE ================\n"
            f"• FSM Phase: {state.phase.value}\n"
            f"• Remaining Step Budget: {state.remaining_steps} / {state.max_steps}\n"
            f"• Active Hypothesis: {state.active_hypothesis}\n"
            f"• Modified Files: {', '.join(state.modified_files) if state.modified_files else 'None'}\n"
            f"• Reproduction Script: {state.reproduction_script or 'Not created yet'}\n"
            f"==============================================================="
        )
        return self.system_prompt + status_banner

    def _compact_history(self) -> list[dict[str, Any]]:
        """Prune verbose outputs in older turns while preserving recent turns."""
        if len(self._history) <= (self.recent_turns_to_keep * 2):
            return list(self._history)

        compacted: list[dict[str, Any]] = []
        cutoff_index = len(self._history) - (self.recent_turns_to_keep * 2)

        for idx, msg in enumerate(self._history):
            if idx < cutoff_index and msg.get("role") == "tool":
                raw_content = msg.get("content", "")
                if len(raw_content) > self.max_tool_summary_length:
                    tool_name = msg.get("name", "tool")
                    summary = (
                        f"[{tool_name} output from earlier step: "
                        f"{raw_content[:self.max_tool_summary_length].strip()}... (truncated)]"
                    )
                    compacted.append({**msg, "content": summary})
                else:
                    compacted.append(msg)
            else:
                compacted.append(msg)

        return compacted

    @property
    def total_messages(self) -> int:
        return len(self._history)
