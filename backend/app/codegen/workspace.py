"""
Git worktree lifecycle for the codegen agent (story 2.2, CDC-42).

Epic 2's architecture: one permanent canonical clone lives at
REPO_CLONE_PATH (one-time setup - this module never creates or clones it).
Each in-flight ticket gets its own git worktree checked out off that
clone, on a branch named feature/<TICKET>-<slug> - the same convention
Epic 3's story 3.1 will use for its own branch creation, so the two stay
consistent once that epic exists.

Story 2.8 (CDC-52): list_ticket_worktrees()/delete_ticket_branch() support
scripts/sweep_stale_worktrees.py, which removes worktrees CDC-41's
cleanup_on_success=False deliberately left behind once they've sat past a
retention window without being picked up for commit/PR.
"""

import logging
import re
import subprocess
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, List, Optional, Tuple

from app.config import get_settings

logger = logging.getLogger("codecrew.codegen_workspace")

_SLUG_MAX_WORDS = 6
_NON_WORD_RE = re.compile(r"[^a-z0-9]+")


class WorkspaceError(Exception):
    """Base class for codegen workspace errors."""


class RepoNotConfiguredError(WorkspaceError):
    """Raised when REPO_CLONE_PATH isn't set, or doesn't point at a real git clone."""


class WorktreeInProgressError(WorkspaceError):
    """
    Raised when a worktree is genuinely checked out on this ticket's
    branch right now - e.g. a duplicate concurrent request - so the
    caller can reply with a clear "already in progress" message rather
    than a conflicting second worktree. A leftover branch whose worktree
    was already removed does NOT trigger this (CDC-51).
    """


@dataclass
class TicketWorkspace:
    ticket_key: str
    branch: str
    path: Path


def branch_name(ticket_key: str, summary: str) -> str:
    """feature/<TICKET>-<slug>, matching Epic 3 story 3.1's convention."""
    slug_words = _NON_WORD_RE.sub(" ", summary.lower()).split()[:_SLUG_MAX_WORDS]
    slug = "-".join(slug_words)
    return f"feature/{ticket_key}-{slug}" if slug else f"feature/{ticket_key}"


def _canonical_clone_path() -> Path:
    settings = get_settings()
    if not settings.repo_clone_path:
        raise RepoNotConfiguredError(
            "REPO_CLONE_PATH isn't set - the codegen agent needs a one-time "
            "canonical clone of the target repo configured on the server."
        )
    clone_path = Path(settings.repo_clone_path)
    if not (clone_path / ".git").exists():
        raise RepoNotConfiguredError(f"{clone_path} isn't a git clone (no .git directory found).")
    return clone_path


def _run_git(args: List[str], cwd: Path) -> subprocess.CompletedProcess:
    logger.debug("Running git command", extra={"args": args, "cwd": str(cwd)})
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=False)


def _worktree_path(clone_path: Path, ticket_key: str) -> Path:
    return clone_path.parent / "codegen-worktrees" / ticket_key


def _parse_worktree_entries(porcelain_output: str) -> List[Tuple[Path, Optional[str]]]:
    """
    Parse `git worktree list --porcelain` into (path, branch) pairs - one
    per worktree, including the canonical clone's own "main" worktree
    entry. `branch` is None for a detached-HEAD entry (not something this
    module's worktrees are ever created as, but git worktree list can
    still contain other worktrees an operator made by hand).
    """
    entries: List[Tuple[Path, Optional[str]]] = []
    current_path: Optional[Path] = None
    current_branch: Optional[str] = None

    for line in porcelain_output.splitlines():
        if line.startswith("worktree "):
            if current_path is not None:
                entries.append((current_path, current_branch))
            current_path = Path(line[len("worktree "):].strip())
            current_branch = None
        elif line.startswith("branch "):
            ref = line[len("branch "):].strip()
            current_branch = ref[len("refs/heads/"):] if ref.startswith("refs/heads/") else ref

    if current_path is not None:
        entries.append((current_path, current_branch))

    return entries


def _list_worktree_entries(clone_path: Path) -> List[Tuple[Path, Optional[str]]]:
    result = _run_git(["worktree", "list", "--porcelain"], cwd=clone_path)
    if result.returncode != 0:
        raise WorkspaceError(f"git worktree list failed: {result.stderr.strip()}")
    return _parse_worktree_entries(result.stdout)


def _branches_with_active_worktrees(clone_path: Path) -> set:
    """
    Find which branches currently have a worktree actually checked out.
    This is the only reliable signal for "in progress" - `git branch
    --list` can't tell the difference between an active worktree and a
    branch left over from a prior run whose worktree was already removed
    (CDC-51: `git worktree remove` deletes the worktree directory but
    leaves the branch behind).
    """
    return {branch for _, branch in _list_worktree_entries(clone_path) if branch}


def list_ticket_worktrees() -> List[TicketWorkspace]:
    """
    List every per-ticket worktree currently checked out off the canonical
    clone - every `git worktree list` entry except the canonical clone's
    own "main" worktree, which must never be identified or treated as a
    per-ticket worktree (CDC-52), and any detached-HEAD entry, which this
    module never creates and so isn't a ticket worktree either.

    Used by scripts/sweep_stale_worktrees.py to find candidates for
    removal; each ticket's worktree directory is named after its ticket
    key (see _worktree_path()), which becomes TicketWorkspace.ticket_key.
    """
    clone_path = _canonical_clone_path()
    resolved_clone_path = clone_path.resolve()

    worktrees = []
    for path, branch in _list_worktree_entries(clone_path):
        if branch is None or path.resolve() == resolved_clone_path:
            continue
        worktrees.append(TicketWorkspace(ticket_key=path.name, branch=branch, path=path))
    return worktrees


def delete_ticket_branch(workspace: TicketWorkspace) -> None:
    """
    Force-delete `workspace.branch` from the canonical clone.

    remove_worktree() deliberately leaves the branch behind (CDC-51) so a
    single failed run stays inspectable. The stale-worktree sweep
    (CDC-52) calls this afterward, once a worktree has aged past the
    retention window without being picked up: at that point the branch
    has had its window to be inspected or committed from, so it's deleted
    too instead of accumulating forever.
    """
    clone_path = _canonical_clone_path()
    result = _run_git(["branch", "-D", workspace.branch], cwd=clone_path)
    if result.returncode != 0:
        raise WorkspaceError(f"git branch -D failed for {workspace.ticket_key}: {result.stderr.strip()}")

    logger.info(
        "Deleted stale ticket branch", extra={"ticket_key": workspace.ticket_key, "branch": workspace.branch}
    )


def create_worktree(ticket_key: str, summary: str) -> TicketWorkspace:
    """
    Create a new git worktree off the canonical clone for `ticket_key`, on
    branch feature/<TICKET>-<slug>, cut from the latest origin/main.

    If a worktree is genuinely already checked out on that branch (e.g. a
    duplicate concurrent request), raises WorktreeInProgressError rather
    than silently creating a conflicting second one. A branch left over
    from a prior, already-cleaned-up run (see remove_worktree()) is not
    a duplicate - it's deleted here so the new worktree can be created.
    """
    clone_path = _canonical_clone_path()
    branch = branch_name(ticket_key, summary)
    worktree_path = _worktree_path(clone_path, ticket_key)

    fetch_result = _run_git(["fetch", "origin"], cwd=clone_path)
    if fetch_result.returncode != 0:
        raise WorkspaceError(f"git fetch failed: {fetch_result.stderr.strip()}")

    if branch in _branches_with_active_worktrees(clone_path):
        logger.info("Worktree already in progress", extra={"ticket_key": ticket_key, "branch": branch})
        raise WorktreeInProgressError(f"A worktree for {ticket_key} is already in progress ({branch}).")

    # Not actively checked out anywhere - safe to drop a stale branch left
    # over from a prior run before recreating it. Ignore failure: the
    # branch may simply not exist yet, which is the common case.
    _run_git(["branch", "-D", branch], cwd=clone_path)

    result = _run_git(
        ["worktree", "add", "-b", branch, str(worktree_path), "origin/main"],
        cwd=clone_path,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip()
        if "already used by worktree" in stderr:
            logger.info("Worktree already in progress", extra={"ticket_key": ticket_key, "branch": branch})
            raise WorktreeInProgressError(f"A worktree for {ticket_key} is already in progress ({branch}).")
        raise WorkspaceError(f"git worktree add failed for {ticket_key}: {stderr}")

    logger.info("Created worktree", extra={"ticket_key": ticket_key, "branch": branch, "path": str(worktree_path)})
    return TicketWorkspace(ticket_key=ticket_key, branch=branch, path=worktree_path)


def remove_worktree(workspace: TicketWorkspace) -> None:
    """
    Remove the worktree via `git worktree remove`, leaving the canonical
    clone itself untouched.

    Deliberately does NOT delete `workspace.branch` (CDC-51's decision):
    this runs in a `finally` regardless of whether the codegen work
    inside succeeded, so the branch is the only remaining record of a
    failed run's commits if the failure happened before anything was
    pushed - keeping it lets a developer check out that branch and
    inspect what happened. This does not reintroduce CDC-51's bug:
    create_worktree() decides "in progress" from `git worktree list`
    (actual checkout state), not branch existence, and force-deletes a
    stale branch itself before reusing it.
    """
    clone_path = _canonical_clone_path()
    result = _run_git(["worktree", "remove", "--force", str(workspace.path)], cwd=clone_path)
    if result.returncode != 0:
        logger.error(
            "Failed to remove worktree",
            extra={"ticket_key": workspace.ticket_key, "stderr": result.stderr.strip()},
        )
        raise WorkspaceError(f"git worktree remove failed for {workspace.ticket_key}: {result.stderr.strip()}")

    logger.info("Removed worktree", extra={"ticket_key": workspace.ticket_key, "path": str(workspace.path)})


@contextmanager
def ticket_workspace(
    ticket_key: str, summary: str, cleanup_on_success: bool = True
) -> Iterator[TicketWorkspace]:
    """
    Create a worktree for `ticket_key` and yield it.

    By default (cleanup_on_success=True, CDC-42's original behavior),
    the worktree is always removed afterward, whether the codegen work
    inside succeeds or raises.

    Story 2.1 (CDC-41) needs the opposite on the success path: the
    worktree, with its real uncommitted file changes, must survive a
    successful diff-generation run so Epic 3 can commit directly from
    that same worktree/branch later - avoiding any risk of a saved patch
    failing to reapply if main has moved on by then. Passing
    cleanup_on_success=False keeps the worktree in that case.

    Failure/error behavior is unchanged either way: an exception raised
    inside the block always removes the worktree before propagating, so
    a duplicate run doesn't collide with a half-finished one.
    """
    workspace = create_worktree(ticket_key, summary)
    try:
        yield workspace
    except BaseException:
        remove_worktree(workspace)
        raise
    else:
        if cleanup_on_success:
            remove_worktree(workspace)
