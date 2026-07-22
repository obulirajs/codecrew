"""
Push a ticket's branch to the GitHub remote (story 3.1, CDC-23) - the last
step before a future Epic 3 story can open a PR from it.

Scope correction (per the ticket): the local branch itself is already
created by CDC-42 at worktree creation time. This module is specifically
about pushing that existing branch - with the real commits CDC-24 put on
it - to GitHub.

This is a git operation (a subprocess push), not a REST API call - it
lives alongside app/codegen/workspace.py's and commit.py's other
git-operations code, not in app/clients/github_client.py, per CDC-28's
own architecture note.

Authenticates via GITHUB_TOKEN (the same PAT from CDC-28) embedded in an
explicit HTTPS remote URL, rather than pushing through the worktree's
already-configured "origin" remote - this way the push authenticates
correctly regardless of whatever ambient git credentials (SSH key,
credential manager, or none at all) happen to be set up on the machine
this runs on. The token is redacted from every log line and error
message this module produces - it must never appear in a log, matching
the discipline already applied to other credentials in this project.

Never force-pushes: a rejected (non-fast-forward) push is a clear error,
not a signal to overwrite remote history.
"""

import logging
import subprocess

from app.codegen.workspace import find_ticket_worktree
from app.config import get_settings

logger = logging.getLogger("codecrew.codegen_push")

_TRANSIENT_MAX_RETRIES = 1  # matches CDC-14/CDC-28's retry-once pattern
_REJECTED_MARKERS = ("[rejected]", "non-fast-forward", "failed to push some refs")


class PushError(Exception):
    """Raised when a push is rejected by the remote, or fails after its retry budget is exhausted."""


def _redact(text: str, token: str) -> str:
    return text.replace(token, "***") if token else text


def _authenticated_remote_url(owner: str, repo: str, token: str) -> str:
    return f"https://x-access-token:{token}@github.com/{owner}/{repo}.git"


def _is_rejected(stderr: str) -> bool:
    return any(marker in stderr for marker in _REJECTED_MARKERS)


def push_ticket_branch(ticket_key: str) -> None:
    """
    Push the worktree's branch (with its CDC-24 commits) to the GitHub
    remote.

    Raises PushError immediately - never force-pushes - if the remote
    rejects the push (e.g. a non-fast-forward conflict): that's a real
    conflict to resolve by hand, not something to retry or overwrite.
    Any other failure is assumed transient (network blip, momentary
    GitHub outage) and retried exactly once before raising PushError,
    matching this project's existing retry-once pattern.
    """
    workspace = find_ticket_worktree(ticket_key)
    settings = get_settings()
    remote_url = _authenticated_remote_url(settings.github_owner, settings.github_repo, settings.github_token)
    redacted_url = _redact(remote_url, settings.github_token)
    refspec = f"{workspace.branch}:{workspace.branch}"

    attempts = 0
    while True:
        logger.debug(
            "Running git push",
            extra={"ticket_key": ticket_key, "branch": workspace.branch, "remote": redacted_url},
        )
        result = subprocess.run(
            ["git", "push", remote_url, refspec],
            cwd=workspace.path,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            logger.info(
                "Pushed branch to GitHub remote",
                extra={"ticket_key": ticket_key, "branch": workspace.branch},
            )
            return

        stderr = _redact(result.stderr.strip(), settings.github_token)

        if _is_rejected(stderr):
            logger.error(
                "git push rejected - not force-pushing",
                extra={"ticket_key": ticket_key, "branch": workspace.branch, "stderr": stderr},
            )
            raise PushError(
                f"git push rejected for {ticket_key} (branch {workspace.branch}): the remote has "
                f"commits this branch doesn't - not force-pushing. {stderr}"
            )

        if attempts < _TRANSIENT_MAX_RETRIES:
            attempts += 1
            logger.warning(
                "git push failed, retrying once",
                extra={"ticket_key": ticket_key, "branch": workspace.branch, "stderr": stderr},
            )
            continue

        logger.error(
            "git push failed after retry",
            extra={"ticket_key": ticket_key, "branch": workspace.branch, "stderr": stderr},
        )
        raise PushError(f"git push failed for {ticket_key} (branch {workspace.branch}) after retry: {stderr}")
