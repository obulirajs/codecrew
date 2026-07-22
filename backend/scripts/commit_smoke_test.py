"""
Manual smoke test for committing generated code (story 3.2, CDC-24) - not
part of the pytest suite. Confirms commit_generated_code() drives a real
commit end to end: generate_diff() (CDC-41/43/45) produces a CodegenResult
in a real worktree, then commit_generated_code() either commits it with
the configured bot identity and a ticket-referencing message, or refuses
on a precondition (needs_clarification / lint_errors) without touching
git.

Skips the real Jira fetch - builds a TicketSpec by hand instead, same
pattern as scripts/codegen_diff_smoke_test.py.

Usage (from backend/, with REPO_CLONE_PATH set in .env):
    python scripts/commit_smoke_test.py [TICKET_KEY]
"""

import asyncio
import subprocess
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.clients.jira_ticket_spec import TicketSpec
from app.codegen.commit import CommitError, commit_generated_code
from app.codegen.diff import generate_diff
from app.codegen.workspace import find_ticket_worktree
from app.logging_config import configure_logging


async def main() -> None:
    configure_logging()

    ticket_key = sys.argv[1] if len(sys.argv) > 1 else "TEST-1"

    # spec = TicketSpec(
    #     summary="Add a comment to README.md explaining what this repo does",
    #     acceptance_criteria=["A one-line comment is added near the top of README.md"],
    #     ticket_type="Task",
    #     labels=[],
    # )

    spec = TicketSpec(
    summary="Add a broken debug script",
    acceptance_criteria=["Create backend/scripts/broken_test2.py with a function that returns an undefined variable named totally_undefined_name"],
    ticket_type="Task",
    labels=[],
    )

    # spec = TicketSpec(
    # summary="Add a comment to README.md explaining what this repo does",
    # acceptance_criteria=["Edit the file at /this/path/absolutely/does/not/exist.xyz"],
    # ticket_type="Task",
    # labels=[],
    # )

    result = await generate_diff(ticket_key, spec)

    print("needs_clarification:")
    print(result.needs_clarification)
    print("\nlint_errors:")
    print(result.lint_errors)
    print("\nfiles_changed:")
    print(result.files_changed)

    try:
        sha = commit_generated_code(ticket_key, result)
    except CommitError as exc:
        print(f"\ncommit refused: {exc}")
        return

    print(f"\ncommitted: {sha}")

    workspace = find_ticket_worktree(ticket_key)
    log_result = subprocess.run(
        ["git", "log", "-1"], cwd=workspace.path, capture_output=True, text=True, check=False
    )
    print("\ngit log -1:")
    print(log_result.stdout)


if __name__ == "__main__":
    asyncio.run(main())
