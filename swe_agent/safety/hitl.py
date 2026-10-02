"""Human-In-The-Loop (HITL) Gatekeeper enforcing dual execution modes."""

import logging
from typing import Callable, Optional

from swe_agent.config import settings
from swe_agent.safety.classifier import CommandRiskAssessment, RiskLevel, classify_command

logger = logging.getLogger(__name__)

# Type alias for custom approval callbacks (used for testing or custom UIs)
ApprovalCallback = Callable[[CommandRiskAssessment], bool]


def default_terminal_approval_prompt(assessment: CommandRiskAssessment) -> bool:
    """Default interactive CLI prompt for human developer confirmation."""
    print("\n" + "=" * 65)
    print("⚠️   [HITL GATEKEEPER] HIGH-RISK ACTION INTERCEPTED")
    print(f"• Command:    {assessment.command}")
    print(f"• Risk Level: {assessment.risk_level.value}")
    print(f"• Reason:     {assessment.reason}")
    print("=" * 65)

    try:
        choice = input("Do you approve executing this command? [y/N]: ").strip().lower()
        return choice in ("y", "yes")
    except (EOFError, KeyboardInterrupt):
        return False


class HITLGatekeeper:
    """Enforces safety policies based on current execution mode (PRODUCTION vs. BENCHMARK)."""

    def __init__(self, approval_callback: Optional[ApprovalCallback] = None):
        self.approval_callback = approval_callback or default_terminal_approval_prompt

    def authorize_command(self, command: str) -> tuple[bool, str]:
        """Check whether a shell command is permitted under the active execution mode.

        Returns:
            tuple[bool, str]: (is_authorized, reason_or_feedback)
        """
        assessment = classify_command(command)

        # 1. Safe commands are always auto-authorized
        if assessment.risk_level == RiskLevel.SAFE:
            return True, "Safe to execute."

        # 2. Benchmark Mode: Zero human intervention. Enforce deterministic hard blocks.
        if settings.is_benchmark_mode:
            logger.warning(
                f"Benchmark Mode Hard Block: Command '{command}' rejected. "
                f"Reason: {assessment.reason}"
            )
            return False, (
                f"Security Blocked (BENCHMARK Mode): Command '{command}' was rejected "
                f"because it is classified as {assessment.risk_level.value} ({assessment.reason}). "
                f"Benchmarking requires headless execution with zero destructive actions."
            )

        # 3. Production Mode: Interactive Human-In-The-Loop Prompt
        logger.info(f"Escalating command '{command}' to Human-In-The-Loop approval.")
        approved = self.approval_callback(assessment)

        if approved:
            logger.info(f"Human developer approved command '{command}'.")
            return True, f"Authorized by human operator: {assessment.reason}"
        else:
            logger.warning(f"Human developer rejected command '{command}'.")
            return False, (
                f"Operation Cancelled: Human operator rejected command '{command}' "
                f"({assessment.reason}). Please select a safe alternative approach."
            )
