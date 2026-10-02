"""Command risk classification engine for detecting destructive and suspicious actions."""

import re
from enum import Enum
from pydantic import BaseModel, Field


class RiskLevel(str, Enum):
    """Classification of command execution risk."""
    SAFE = "SAFE"                # Standard development actions (pytest, git status, python test)
    SUSPICIOUS = "SUSPICIOUS"    # Network calls, dependency installations, env inspections
    DESTRUCTIVE = "DESTRUCTIVE"  # Destructive deletes, force pushes, pipe-to-shell, privilege changes


class CommandRiskAssessment(BaseModel):
    """Result of command risk analysis."""
    command: str
    risk_level: RiskLevel
    reason: str = Field(description="Explanation of why the risk level was assigned")
    blocked_by_default: bool = False


# Destructive command regex patterns
DESTRUCTIVE_PATTERNS = [
    (r"\brm\s+(-[a-zA-Z]*r[a-zA-Z]*f*|-[a-zA-Z]*f[a-zA-Z]*r*)\s+[\/\~]", "Recursive deletion targeting root or home directory"),
    (r"\brm\s+-[a-zA-Z]*r", "Recursive deletion command"),
    (r"\bgit\s+push\b", "Git remote push operations are forbidden to prevent repository tampering"),
    (r"\bgit\s+reset\s+--hard\b", "Hard git reset risks losing uncommitted progress without recovery"),
    (r"\bgit\s+clean\s+-[a-zA-Z]*f", "Force git clean can destroy untracked files permanently"),
    (r"\bchmod\s+(-R\s+)?777\b", "Permissive permission changes compromise security isolation"),
    (r"\bmkfs\b|\bdd\s+if=", "Low-level filesystem formatting operations are forbidden"),
    (r"\|\s*(bash|sh|zsh)\b", "Piping remote or dynamic streams into shell interpreter"),
    (r"\.github\/workflows", "Modifying CI/CD workflow files is restricted to prevent pipeline hijacking"),
]

# Suspicious command regex patterns
SUSPICIOUS_PATTERNS = [
    (r"\b(curl|wget|nc|ncat|netcat|ssh|scp|ftp)\b", "Network-facing utility detected; potential exfiltration or payload retrieval"),
    (r"\b(pip|pip3|npm|yarn|pnpm)\s+install\b", "Dependency installation alters environment reproducibility"),
    (r"\b(env|printenv|set)\b", "Environment variable dumps risk exposing runtime secrets"),
]


def classify_command(command: str) -> CommandRiskAssessment:
    """Analyze a shell command and return its risk classification and justification.

    Args:
        command: Raw shell command string requested by the agent.

    Returns:
        CommandRiskAssessment containing the risk level and safety rationale.
    """
    cleaned_cmd = command.strip()

    # 1. Check for destructive patterns
    for pattern, rationale in DESTRUCTIVE_PATTERNS:
        if re.search(pattern, cleaned_cmd, re.IGNORECASE):
            return CommandRiskAssessment(
                command=cleaned_cmd,
                risk_level=RiskLevel.DESTRUCTIVE,
                reason=rationale,
                blocked_by_default=True
            )

    # 2. Check for suspicious patterns
    for pattern, rationale in SUSPICIOUS_PATTERNS:
        if re.search(pattern, cleaned_cmd, re.IGNORECASE):
            return CommandRiskAssessment(
                command=cleaned_cmd,
                risk_level=RiskLevel.SUSPICIOUS,
                reason=rationale,
                blocked_by_default=False
            )

    # 3. Default to safe
    return CommandRiskAssessment(
        command=cleaned_cmd,
        risk_level=RiskLevel.SAFE,
        reason="Standard development or inspection command.",
        blocked_by_default=False
    )
