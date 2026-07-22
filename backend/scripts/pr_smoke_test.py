"""
Manual smoke test for opening a PR from a ticket's already-pushed branch
(story 3.3, CDC-25) - not part of the pytest suite. Assumes the branch was
already committed and pushed for the given ticket key (e.g. via
commit_smoke_test.py + push_smoke_test.py) and calls open_pull_request()
against the real GitHub repo.

Skips the real Jira fetch and skips re-running codegen - builds a
TicketSpec and a CodegenResult by hand instead, same pattern as
scripts/commit_smoke_test.py. Re-running generate_diff() here would create
a fresh worktree rather than reusing the one the branch was actually
pushed from, so the CodegenResult is hardcoded to describe what that
worktree's real commit already contains.

Usage (from backend/, with REPO_CLONE_PATH and GITHUB_TOKEN set in .env):
    python scripts/pr_smoke_test.py [TICKET_KEY]
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.clients.jira_ticket_spec import TicketSpec
from app.codegen.diff import CodegenResult
from app.codegen.pr import PullRequestError, open_pull_request
from app.logging_config import configure_logging


def main() -> None:
    configure_logging()

    ticket_key = sys.argv[1] if len(sys.argv) > 1 else "TEST-8"

    spec = TicketSpec(
        summary="Add a comment to README.md explaining what this repo does",
        acceptance_criteria=["A one-line comment is added near the top of README.md"],
        ticket_type="Task",
        labels=[],
    )

    result = CodegenResult(
        diff_text="",
        summary="Added a comment to README.md explaining the repo",
        files_changed=["README.md"],
        needs_clarification=False,
        lint_errors=[],
    )

    try:
        pr = open_pull_request(ticket_key, spec, result)
    except PullRequestError as exc:
        print(f"open_pull_request failed: {exc}")
        return

    print(f"number: {pr.number}")
    print(f"url: {pr.url}")


if __name__ == "__main__":
    main()
