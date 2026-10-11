"""Frozen benchmark manifest for custom SWE-bench-inspired evaluation."""

from pydantic import BaseModel, Field


class BenchmarkTask(BaseModel):
    """A frozen, reproducible repository task definition.

    Invariant: The agent workspace is provided ONLY with repo_name,
    base_commit, and issue_statement. The ground truth patch and evaluation
    tests remain strictly quarantined in the evaluation harness.
    """

    task_id: str = Field(description="Unique benchmark identifier, e.g. 'custom-swe-01'")
    repo_name: str = Field(description="Repository name or package name")
    base_commit: str = Field(default="HEAD", description="Baseline commit before bug fix")
    issue_statement: str = Field(description="Raw problem description reported by user")
    expected_files_to_touch: list[str] = Field(
        default_factory=list,
        description="Files that the gold patch modifies (used to compute spurious edits)"
    )
    test_command: str = Field(
        description="Verification command executed by the EVAL HARNESS to test resolution"
    )
    initial_files: dict[str, str] = Field(
        default_factory=dict,
        description="Initial repository file contents representing the bug state"
    )
    verification_test_files: dict[str, str] = Field(
        default_factory=dict,
        description="Test files injected ONLY by the eval harness to verify the fix"
    )


# Curated frozen benchmark dataset representing real Python software engineering tasks
FROZEN_BENCHMARK_TASKS: list[BenchmarkTask] = [
    BenchmarkTask(
        task_id="swe-mini-01-url-routing",
        repo_name="flask-mock",
        issue_statement=(
            "Issue #3421: URL routing fails when an endpoint URL has a trailing slash. "
            "Calling `url_for('profile', slash=True)` returns a 404 instead of canonicalizing "
            "the route. Expected `normalize_route` in `src/routing.py` to strip trailing slashes."
        ),
        expected_files_to_touch=["src/routing.py"],
        test_command="python test_verification.py",
        initial_files={
            "src/routing.py": (
                "def normalize_route(route: str) -> str:\n"
                "    # BUG: Does not strip trailing slash for non-root routes\n"
                "    return route\n"
            ),
            "tests/test_existing.py": (
                "import sys, os\n"
                "sys.path.insert(0, os.path.abspath('.'))\n"
                "from src.routing import normalize_route\n"
                "def test_root():\n"
                "    assert normalize_route('/') == '/'\n"
            )
        },
        verification_test_files={
            "test_verification.py": (
                "from src.routing import normalize_route\n"
                "# Ground-truth test that proves the bug is fixed\n"
                "assert normalize_route('/users/profile/') == '/users/profile'\n"
                "assert normalize_route('/') == '/'\n"
                "print('VERIFICATION SUCCESSFUL')\n"
            )
        }
    ),
    BenchmarkTask(
        task_id="swe-mini-02-auth-headers",
        repo_name="requests-mock",
        issue_statement=(
            "Issue #4211: Session auth headers are case-sensitive. "
            "When user sets 'authorization' in lowercase, `prepare_auth` in `src/auth.py` "
            "overwrites it with a duplicate 'Authorization' header instead of case-insensitive merging."
        ),
        expected_files_to_touch=["src/auth.py"],
        test_command="python test_verification.py",
        initial_files={
            "src/auth.py": (
                "def prepare_auth(headers: dict, token: str) -> dict:\n"
                "    # BUG: Naively checks 'Authorization' without case-folding\n"
                "    if 'Authorization' not in headers:\n"
                "        headers['Authorization'] = f'Bearer {token}'\n"
                "    return headers\n"
            )
        },
        verification_test_files={
            "test_verification.py": (
                "from src.auth import prepare_auth\n"
                "headers = {'authorization': 'Bearer custom_token'}\n"
                "result = prepare_auth(headers, 'default_token')\n"
                "# Must not add duplicate capitalized Authorization key\n"
                "assert 'Authorization' not in result or result['authorization'] == 'Bearer custom_token'\n"
                "assert len([k for k in result if k.lower() == 'authorization']) == 1\n"
                "print('VERIFICATION SUCCESSFUL')\n"
            )
        }
    ),
    BenchmarkTask(
        task_id="swe-mini-03-cli-exception",
        repo_name="click-mock",
        issue_statement=(
            "Issue #1875: CLI parser raises unhandled KeyError when missing required option. "
            "In `src/parser.py`, `parse_args` should catch missing keys and raise `CLIArgumentError` "
            "with a clean user message instead of a raw KeyError."
        ),
        expected_files_to_touch=["src/parser.py"],
        test_command="python test_verification.py",
        initial_files={
            "src/parser.py": (
                "class CLIArgumentError(Exception):\n"
                "    pass\n\n"
                "def parse_args(args: dict, required_key: str) -> str:\n"
                "    # BUG: Directly indexes args without KeyError handling\n"
                "    return args[required_key]\n"
            )
        },
        verification_test_files={
            "test_verification.py": (
                "import pytest\n"
                "from src.parser import parse_args, CLIArgumentError\n"
                "try:\n"
                "    parse_args({}, 'config')\n"
                "    raise AssertionError('Should have raised CLIArgumentError')\n"
                "except CLIArgumentError:\n"
                "    print('VERIFICATION SUCCESSFUL')\n"
            )
        }
    )
]
