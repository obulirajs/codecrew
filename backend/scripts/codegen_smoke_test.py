"""
Manual smoke test for the codegen agent (story 2.2, CDC-42; credential
precedence from story 2.7, CDC-50) - not part of the pytest suite. Confirms
a git worktree can be created off the configured REPO_CLONE_PATH, the
Claude Agent SDK can read real files inside it, and the worktree is
removed afterward - end to end, against a fake ticket key.

Usage (from backend/, with REPO_CLONE_PATH set in .env):
    python scripts/codegen_smoke_test.py [TICKET_KEY]
"""

import asyncio
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.codegen.agent import run_headless
from app.codegen.workspace import ticket_workspace
from app.logging_config import configure_logging


async def main() -> None:
    configure_logging()

    ticket_key = sys.argv[1] if len(sys.argv) > 1 else "TEST-1"

    with ticket_workspace(ticket_key, "codegen smoke test") as workspace:
        print(f"Created worktree for {ticket_key} on branch {workspace.branch}")
        print(f"Path: {workspace.path}")

        result = await run_headless(
            workspace.path,
            "List the files in this directory and tell me what app/config.py's Settings class requires",
        )
        print("Agent response:")
        print(result)

    print(f"Worktree for {ticket_key} removed.")


if __name__ == "__main__":
    asyncio.run(main())
