"""
Manual smoke test for pushing a ticket's branch to GitHub (story 3.1,
CDC-23) - not part of the pytest suite. Assumes a worktree with real
commits already exists for the given ticket key (e.g. from running
commit_smoke_test.py first) and pushes it via push_ticket_branch().

Usage (from backend/, with REPO_CLONE_PATH and GITHUB_TOKEN set in .env):
    python scripts/push_smoke_test.py [TICKET_KEY]
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.codegen.push import PushError, push_ticket_branch
from app.logging_config import configure_logging


def main() -> None:
    configure_logging()

    ticket_key = sys.argv[1] if len(sys.argv) > 1 else "TEST-1"

    try:
        push_ticket_branch(ticket_key)
    except PushError as exc:
        print(f"push failed: {exc}")
        return

    print(f"pushed branch for {ticket_key} successfully")


if __name__ == "__main__":
    main()
