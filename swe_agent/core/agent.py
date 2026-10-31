"""Autonomous Software Engineering Agent - Core Controller and ReAct Loop."""

import logging

from swe_agent.config import settings
from swe_agent.core.memory import ContextManager
from swe_agent.core.prompts import SYSTEM_PROMPT
from swe_agent.core.state import AgentPhase, AgentState
from swe_agent.models.provider import ModelProvider
from swe_agent.sandbox.protocol import AbstractSandbox
from swe_agent.telemetry.tracer import TrajectoryLogger, TrajectoryStep
from swe_agent.tools.registry import ToolRegistry, create_default_registry

logger = logging.getLogger(__name__)


class SweAgent:
    """Stateful Autonomous Software Engineering Agent.

    Orchestrates the Goal-Directed Finite State Machine:
    EXPLORE -> REPRODUCE -> PATCH -> VERIFY -> COMPLETE.
    """

    def __init__(
        self,
        sandbox: AbstractSandbox,
        model_provider: ModelProvider | None = None,
        tool_registry: ToolRegistry | None = None,
        tracer: TrajectoryLogger | None = None,
        max_steps: int | None = None
    ):
        self.sandbox = sandbox
        self.model_provider = model_provider or ModelProvider()
        self.tool_registry = tool_registry or create_default_registry()
        self.tracer = tracer or TrajectoryLogger()
        self.max_steps = max_steps or settings.max_steps

    def solve_issue(
        self,
        task_id: str,
        issue_statement: str,
        repo_info: str = "Standard Python Repository"
    ) -> AgentState:
        """Run the autonomous agent loop to resolve the assigned repository issue."""
        state = AgentState(
            task_id=task_id,
            issue_statement=issue_statement,
            repository=repo_info,
            max_steps=self.max_steps
        )
        context_mgr = ContextManager(system_prompt=SYSTEM_PROMPT)
        context_mgr.initialize_conversation(issue_statement, repo_info)

        # Initialize structured trajectory
        self.tracer.start_trajectory(
            task_id=task_id,
            issue_statement=issue_statement,
            repository=repo_info,
            execution_mode=settings.execution_mode.value
        )

        state.transition_to(AgentPhase.EXPLORE)
        logger.info(f"Agent starting task '{task_id}' in EXPLORE phase.")

        while not state.completed:
            state.record_step()
            if state.completed:  # Budget exhausted in record_step
                break

            step_record = TrajectoryStep(
                step_number=state.step_count,
                phase=state.phase.value
            )

            # 1. Fetch current context and tool schemas
            messages = context_mgr.get_messages(state)
            schemas = self.tool_registry.get_schemas()

            # 2. Invoke model
            try:
                response = self.model_provider.generate(messages=messages, tools=schemas)
            except Exception as exc:
                logger.error(f"Model generation error at step {state.step_count}: {exc}")
                state.transition_to(AgentPhase.FAILED)
                state.completed = True
                state.conclusion_summary = f"Fatal model invocation error: {str(exc)}"
                break

            step_record.thought = response.content
            step_record.prompt_tokens = response.prompt_tokens
            step_record.completion_tokens = response.completion_tokens
            step_record.duration_seconds = response.latency_seconds

            # 3. Record assistant message
            tool_calls_raw = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.name, "arguments": str(tc.arguments)}
                }
                for tc in response.tool_calls
            ] if response.has_tool_calls else None

            context_mgr.add_assistant_message(
                content=response.content,
                tool_calls=tool_calls_raw
            )

            # 4. Handle model responses without tool calls
            if not response.has_tool_calls:
                # Nudge model if it did not call a tool or conclude
                context_mgr.add_tool_result(
                    tool_call_id="system_nudge",
                    tool_name="system",
                    output="Reminder: Please take action by invoking a tool (search, view, edit, run) or call `conclude_task` if finished."
                )
                self.tracer.log_step(step_record)
                continue

            # 5. Execute each tool call
            for tc in response.tool_calls:
                step_record.tool_calls.append({"name": tc.name, "arguments": tc.arguments})

                # Update working memory and FSM based on tool semantics
                self._update_fsm_and_memory(state, tc.name, tc.arguments)

                # Special handling for task conclusion
                if tc.name == "conclude_task":
                    state.completed = True
                    state.success = tc.arguments.get("success", False)
                    state.conclusion_summary = tc.arguments.get("explanation", "")
                    state.transition_to(AgentPhase.COMPLETE if state.success else AgentPhase.FAILED)
                    context_mgr.add_tool_result(tc.id, tc.name, "Task concluded.")
                    step_record.tool_outputs.append({"output": state.conclusion_summary})
                    break

                # Execute tool inside sandbox
                result = self.tool_registry.execute_tool(tc.name, tc.arguments, self.sandbox)
                context_mgr.add_tool_result(tc.id, tc.name, result.output)
                step_record.tool_outputs.append({"output": result.output, "success": result.success})

                # If test execution or git restore, adjust cognitive state
                if tc.name == "git_restore":
                    state.recovery_attempts += 1
                elif tc.name == "run_bash_command" and "reproduce" in str(tc.arguments.get("command", "")):
                    state.reproduction_confirmed = not result.success

            self.tracer.log_step(step_record)

        # 6. Capture final git diff and finalize trajectory
        diff_res = self.sandbox.execute("git diff")
        state.final_patch = diff_res.stdout.strip() if diff_res.is_success else ""

        self.tracer.finalize(
            success=state.success,
            final_patch=state.final_patch,
            metrics={
                "steps_taken": state.step_count,
                "modified_files": state.modified_files,
                "recovery_attempts": state.recovery_attempts,
                "summary": state.conclusion_summary
            }
        )

        logger.info(
            f"Agent completed task '{task_id}' with status: {state.phase.value} "
            f"(success={state.success}, steps={state.step_count})"
        )
        return state

    def _update_fsm_and_memory(
        self, state: AgentState, tool_name: str, args: dict
    ) -> None:
        """Heuristic FSM phase alignment based on agent actions."""
        if tool_name in ("code_search", "find_symbol", "list_directory") and state.phase == AgentPhase.INITIALIZE:
            state.transition_to(AgentPhase.EXPLORE)
        elif tool_name == "create_file" and "repro" in str(args.get("path", "")):
            state.reproduction_script = args.get("path")
            state.transition_to(AgentPhase.REPRODUCE)
        elif tool_name == "edit_file_replace":
            path = args.get("path", "")
            if path:
                state.track_file_edit(path)
            state.transition_to(AgentPhase.PATCH)
        elif tool_name == "run_bash_command" and state.phase in (AgentPhase.PATCH, AgentPhase.REPRODUCE):
            state.transition_to(AgentPhase.VERIFY)
