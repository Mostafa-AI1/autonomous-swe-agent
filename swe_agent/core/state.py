"""Goal-Directed Finite State Machine (FSM) and working memory models."""

from enum import Enum

from pydantic import BaseModel, Field


class AgentPhase(str, Enum):
    """Explicit lifecycle phases of the SWE agent."""
    INITIALIZE = "INITIALIZE"    # Environment setup and issue ingestion
    EXPLORE = "EXPLORE"          # Locating relevant files, symbols, and references
    REPRODUCE = "REPRODUCE"      # Writing reproduction script to trigger the bug
    PATCH = "PATCH"              # Formulating and applying minimal surgical code edits
    VERIFY = "VERIFY"            # Running repro script and test suite inside sandbox
    COMPLETE = "COMPLETE"        # Task successfully resolved and verified via git diff
    FAILED = "FAILED"            # Step budget exhausted or unrecoverable error


class AgentState(BaseModel):
    """Immutable snapshot of the agent's internal state and working memory."""

    task_id: str
    issue_statement: str
    repository: str
    phase: AgentPhase = AgentPhase.INITIALIZE
    step_count: int = 0
    max_steps: int = 30

    # Working Memory / Cognitive State
    active_hypothesis: str = Field(
        default="Investigating codebase to localize the root cause.",
        description="Current engineering hypothesis explaining the bug"
    )
    reproduction_script: str | None = Field(
        default=None,
        description="Path to created reproduction script (e.g. repro_issue.py)"
    )
    reproduction_confirmed: bool = Field(
        default=False,
        description="Whether the bug has been successfully reproduced (exit code != 0)"
    )
    modified_files: list[str] = Field(
        default_factory=list,
        description="List of files edited during the task"
    )
    recovery_attempts: int = Field(
        default=0,
        description="Count of self-recovery / rollback cycles performed"
    )

    # Termination Outcome
    completed: bool = False
    success: bool = False
    final_patch: str = ""
    conclusion_summary: str = ""

    def transition_to(self, new_phase: AgentPhase, reason: str | None = None) -> None:
        """Explicitly transition to a new FSM phase."""
        self.phase = new_phase

    def record_step(self) -> None:
        """Increment step counter and check budget exhaustion."""
        self.step_count += 1
        if self.step_count >= self.max_steps and not self.completed:
            self.phase = AgentPhase.FAILED
            self.completed = True
            self.success = False
            self.conclusion_summary = f"Exhausted step budget ({self.max_steps} steps) before completion."

    def track_file_edit(self, file_path: str) -> None:
        """Record modified file path uniquely."""
        if file_path not in self.modified_files:
            self.modified_files.append(file_path)

    @property
    def remaining_steps(self) -> int:
        return max(0, self.max_steps - self.step_count)
