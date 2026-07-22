"""
Manual smoke test for the full Epic 2 + Epic 3 pipeline, end to end against
a real repo and a real GitHub remote (not part of the pytest suite): one
TicketSpec, one generate_diff() call, then commit -> push -> open PR, each
step built on the previous step's real output rather than hand-built
stand-ins (unlike commit_smoke_test.py / push_smoke_test.py /
pr_smoke_test.py, which each exercise one step in isolation).

Skips the real Jira fetch - builds a TicketSpec by hand, same pattern as
the other smoke scripts (the README-comment AC that's known to produce a
clean, lint-free diff).

Usage (from backend/, with REPO_CLONE_PATH and GITHUB_TOKEN set in .env):
    python scripts/full_pipeline_smoke_test.py [TICKET_KEY]
"""

import asyncio
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.clients.jira_ticket_spec import TicketSpec
from app.codegen.commit import CommitError, commit_generated_code
from app.codegen.diff import CodegenError, generate_diff
from app.codegen.pr import PullRequestError, open_pull_request
from app.codegen.push import PushError, push_ticket_branch
from app.logging_config import configure_logging


def _fail(step: str, exc: Exception) -> None:
    print(f"\nFAILED at step '{step}': {exc}")
    sys.exit(1)


async def main() -> None:
    configure_logging()

    ticket_key = sys.argv[1] if len(sys.argv) > 1 else "TEST-1"

    # spec = TicketSpec(
    #     summary="Add a comment to README.md explaining what this repo does",
    #     acceptance_criteria=["A one-line comment is added near the top of README.md"],
    #     ticket_type="Task",
    #     labels=[],
    # )

    # spec = TicketSpec(
    # summary="Add a CONTRIBUTING.md file",
    # acceptance_criteria=["Create a CONTRIBUTING.md file at the repo root with a one-line note that this is a personal learning project, contributions welcome from friends only"],
    # ticket_type="Task",
    # labels=[],
    # )

    spec = TicketSpec(
    summary="Add a divide function to backend/scripts/math_utils.py",
    acceptance_criteria=["Create backend/scripts/math_utils.py with a function divide(a, b) that returns a / b, with no handling for b being zero"],
    ticket_type="Task",
    labels=[],
    )

    try:
        result = await generate_diff(ticket_key, spec)
    except CodegenError as exc:
        _fail("generate_diff", exc)
        return

    print("generate_diff result:")
    print(f"  summary: {result.summary}")
    print(f"  files_changed: {result.files_changed}")
    print(f"  needs_clarification: {result.needs_clarification}")
    print(f"  lint_errors: {result.lint_errors}")

    if result.needs_clarification:
        print(f"\nSTOPPING: {ticket_key} needs clarification, not proceeding:")
        for question in result.clarifying_questions:
            print(f"  - {question}")
        sys.exit(1)

    if result.lint_errors:
        print(f"\nSTOPPING: {ticket_key} has lint errors, not proceeding:")
        for error in result.lint_errors:
            print(f"  - {error}")
        sys.exit(1)

    try:
        sha = commit_generated_code(ticket_key, result)
    except CommitError as exc:
        _fail("commit_generated_code", exc)
        return
    print(f"\ncommitted: {sha}")

    try:
        push_ticket_branch(ticket_key)
    except PushError as exc:
        _fail("push_ticket_branch", exc)
        return
    print(f"pushed branch for {ticket_key} successfully")

    try:
        pr = open_pull_request(ticket_key, spec, result)
    except PullRequestError as exc:
        _fail("open_pull_request", exc)
        return
    print(f"\nopened PR #{pr.number}: {pr.url}")


if __name__ == "__main__":
    asyncio.run(main())
