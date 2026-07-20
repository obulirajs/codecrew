"""
Standalone sweep of stale codegen worktrees (story 2.8, CDC-52).

CDC-41's generate_diff() deliberately leaves a worktree in place after a
successful run (cleanup_on_success=False), so Epic 3 can commit directly
from the same worktree/branch later. If a ticket never gets picked up for
that commit/PR step, its worktree sits on disk indefinitely. This script
removes any worktree older than WORKTREE_RETENTION_HOURS (config.py,
default 48).

Not a background scheduler - meant to be run periodically via a simple
OS-level scheduled task (cron / Windows Task Scheduler) or by hand,
matching this project's scale.

Age is the worktree directory's filesystem modified time - git itself
doesn't track worktree creation time, so no additional bookkeeping is
introduced for this. Age past the retention window is treated as a
sufficient safety margin on its own against removing a worktree that's
actively mid-run: no real codegen run or Epic 3 commit takes anywhere
near that long, so no separate locking/heartbeat is needed here.

Usage (from backend/, with REPO_CLONE_PATH set in .env):
    python scripts/sweep_stale_worktrees.py
"""

import logging
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.codegen.workspace import TicketWorkspace, delete_ticket_branch, list_ticket_worktrees, remove_worktree
from app.config import get_settings
from app.logging_config import configure_logging

logger = logging.getLogger("codecrew.sweep_stale_worktrees")


def _age_hours(workspace: TicketWorkspace) -> float:
    return (time.time() - workspace.path.stat().st_mtime) / 3600


def main() -> None:
    configure_logging()
    retention_hours = get_settings().worktree_retention_hours

    worktrees = list_ticket_worktrees()
    removed = 0

    for workspace in worktrees:
        age_hours = _age_hours(workspace)
        if age_hours <= retention_hours:
            continue

        logger.info(
            "Removing stale worktree past retention window",
            extra={
                "ticket_key": workspace.ticket_key,
                "branch": workspace.branch,
                "age_hours": round(age_hours, 1),
                "retention_hours": retention_hours,
            },
        )
        remove_worktree(workspace)
        delete_ticket_branch(workspace)
        removed += 1

    logger.info(
        "Stale worktree sweep complete",
        extra={"checked": len(worktrees), "removed": removed, "retention_hours": retention_hours},
    )


if __name__ == "__main__":
    main()
