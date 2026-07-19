"""
Manual smoke test for the codegen diff generator (story 2.1, CDC-41) - not
part of the pytest suite. Confirms generate_diff() drives the agent inside
a real worktree, edits real files, and returns the actual git diff as a
structured result - and that the cleanup_on_success=False behavior it
relies on (workspace.py, CDC-41) leaves the worktree in place after a
successful run.

Skips the real Jira fetch - builds a TicketSpec by hand instead, since
this is only exercising the codegen path, not CDC-15's extraction.

Usage (from backend/, with REPO_CLONE_PATH set in .env):
    python scripts/codegen_diff_smoke_test.py [TICKET_KEY]
"""

import asyncio
import subprocess
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.clients.jira_ticket_spec import TicketSpec
from app.codegen.diff import generate_diff
from app.codegen.workspace import branch_name
from app.config import get_settings
from app.logging_config import configure_logging


async def main() -> None:
    configure_logging()

    ticket_key = sys.argv[1] if len(sys.argv) > 1 else "TEST-1"

    spec = TicketSpec(
        summary="Add a comment to README.md explaining what this repo does",
        # acceptance_criteria=["Edit the file at /this/path/absolutely/does/not/exist.xyz"],
        acceptance_criteria=["A one-line comment is added near the top of README.md"],
        ticket_type="Task",
        labels=[],
    )

    result = await generate_diff(ticket_key, spec)

    print("diff_text:")
    print(result.diff_text)
    print("\nsummary:")
    print(result.summary)
    print("\nfiles_changed:")
    print(result.files_changed)

    branch = branch_name(ticket_key, spec.summary)
    clone_path = get_settings().repo_clone_path
    worktree_list = subprocess.run(
        ["git", "worktree", "list"], cwd=clone_path, capture_output=True, text=True, check=False
    ).stdout
    still_exists = branch in worktree_list
    print(f"\nWorktree for {ticket_key} (branch {branch}) still exists: {still_exists}")


if __name__ == "__main__":
    asyncio.run(main())
