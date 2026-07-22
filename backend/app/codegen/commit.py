"""
Commit codegen-generated code with a ticket-referencing message (story
3.2, CDC-24), built on top of CDC-41/43/45's generate_diff() output.

This is a git operation (a subprocess commit), not a REST API call - it
lives alongside app/codegen/workspace.py's other git-operations code, not
in app/clients/github_client.py.

Enforces the preconditions nothing before this enforced: a CodegenResult
flagged needs_clarification (CDC-43 - no code was ever written, and its
worktree is already gone) or carrying lint_errors (CDC-45 - a flawed
diff) must never reach `git commit`. Both are refused up front with a
clear, specific error before any git command runs, rather than failing
confusingly at the git level (e.g. staging nothing, or "nothing to
commit").
"""

import logging
import subprocess
from pathlib import Path
from typing import List

from app.codegen.diff import CodegenResult
from app.codegen.workspace import find_ticket_worktree
from app.config import get_settings

logger = logging.getLogger("codecrew.codegen_commit")


class CommitError(Exception):
    """Raised when a commit is refused (an unmet precondition) or a git command itself fails."""


def _run_git(args: List[str], cwd: Path) -> subprocess.CompletedProcess:
    logger.debug("Running git command", extra={"args": args, "cwd": str(cwd)})
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=False)


def commit_generated_code(ticket_key: str, result: CodegenResult) -> str:
    """
    Commit `result.files_changed` in the worktree already checked out for
    `ticket_key` (the one CDC-41's generate_diff() left behind on
    success), with a message combining the ticket key and
    result.summary - no separate LLM call needed to produce one, and the
    same "<TICKET-KEY> <description>" convention this project's other
    commits use so GitHub for Atlassian's Smart Commits auto-link it.

    Stages exactly files_changed via `git add --` (never a blind
    `git add -A`), so stray/unrelated files sitting in the worktree can
    never be swept into the commit. Sets the commit's author identity
    explicitly per-commit via `git -c user.name=... -c user.email=...`,
    not relying on any global git config being set up on whatever machine
    this runs on - a fresh machine has none, which would otherwise fail
    with "Please tell me who you are".

    Returns the new commit's SHA. On success the worktree is left exactly
    as generate_diff() left it - still not cleaned up - ready for CDC-23
    to push next.
    """
    if result.needs_clarification:
        raise CommitError(
            f"Cannot commit {ticket_key}: codegen needs clarification and wrote no "
            "code - its worktree was already cleaned up."
        )
    if result.lint_errors:
        raise CommitError(
            f"Cannot commit {ticket_key}: {len(result.lint_errors)} lint error(s) "
            "present - fix them before committing."
        )
    if not result.files_changed:
        raise CommitError(f"Cannot commit {ticket_key}: no files_changed to commit.")

    workspace = find_ticket_worktree(ticket_key)

    add_result = _run_git(["add", "--", *result.files_changed], cwd=workspace.path)
    if add_result.returncode != 0:
        raise CommitError(f"git add failed for {ticket_key}: {add_result.stderr.strip()}")

    settings = get_settings()
    commit_message = f"{ticket_key} {result.summary}"
    commit_result = _run_git(
        [
            "-c", f"user.name={settings.git_commit_author_name}",
            "-c", f"user.email={settings.git_commit_author_email}",
            "commit", "-m", commit_message,
        ],
        cwd=workspace.path,
    )
    if commit_result.returncode != 0:
        raise CommitError(f"git commit failed for {ticket_key}: {commit_result.stderr.strip()}")

    sha_result = _run_git(["rev-parse", "HEAD"], cwd=workspace.path)
    if sha_result.returncode != 0:
        raise CommitError(f"git rev-parse HEAD failed for {ticket_key}: {sha_result.stderr.strip()}")
    sha = sha_result.stdout.strip()

    logger.info(
        "Committed generated code",
        extra={
            "ticket_key": ticket_key,
            "branch": workspace.branch,
            "sha": sha,
            "files_changed": result.files_changed,
        },
    )
    return sha
