"""
Create an ad-hoc branch with a user-supplied name, not tied to any ticket
(story 3.5, CDC-27). Composes CDC-28's GitHubClient the same way
app/codegen/pr.py and pr_list.py compose it - business logic lives here,
not in the pure REST wrapper.

Architecture note (per the ticket): unlike ticket-based branches (CDC-42),
this needs no local worktree/clone - there's no codegen involved and
nothing to commit yet. It's a pure REST operation: create a git ref
pointing at the repo's actual default branch's current commit (via
get_repository(), never a hardcoded "main").

Returns a plain function result - no orchestrator/Teams wiring exists yet
(same note as CDC-25/26/30).
"""

import logging
import re

from pydantic import BaseModel

from app.clients.github_client import GitHubClient, GitHubValidationError

logger = logging.getLogger("codecrew.codegen_branch")

_INVALID_CHARS_RE = re.compile(r"[^a-z0-9._-]+")
_REPEATED_DASHES_RE = re.compile(r"-{2,}")


class InvalidBranchNameError(Exception):
    """Raised when a branch name sanitizes down to nothing (e.g. an all-symbols/whitespace input)."""


class BranchAlreadyExistsError(Exception):
    """Raised when the sanitized name already exists as a branch on the remote - GitHub's 422 for this specific case, not a generic crash."""


class BranchResult(BaseModel):
    name: str
    url: str


def sanitize_branch_name(name: str) -> str:
    """
    Concrete sanitization rules (per the ticket): lowercase; replace
    whitespace and invalid git ref characters (~^:?*[ and others - here,
    anything outside [a-z0-9._-]) with a dash; collapse repeated dashes;
    strip leading/trailing dashes and dots. Raises InvalidBranchNameError
    if nothing is left afterward.
    """
    sanitized = name.lower()
    sanitized = _INVALID_CHARS_RE.sub("-", sanitized)
    sanitized = _REPEATED_DASHES_RE.sub("-", sanitized)
    sanitized = sanitized.strip("-.")

    if not sanitized:
        raise InvalidBranchNameError(f"Branch name {name!r} is empty after sanitization.")
    return sanitized


def create_ad_hoc_branch(name: str) -> BranchResult:
    """
    Sanitize `name` and create it as a new branch off the repo's actual
    default branch's current commit. Raises BranchAlreadyExistsError with
    a clear message (not a generic crash) if that name already exists as
    a branch on the remote.
    """
    sanitized = sanitize_branch_name(name)

    with GitHubClient() as client:
        default_branch = client.get_repository()["default_branch"]
        base_sha = client.get_git_ref(f"heads/{default_branch}")["object"]["sha"]

        try:
            client.create_git_ref(ref=f"refs/heads/{sanitized}", sha=base_sha)
        except GitHubValidationError:
            logger.info(
                "Branch already exists on the remote", extra={"branch": sanitized}
            )
            raise BranchAlreadyExistsError(f"Branch '{sanitized}' already exists on the remote.") from None

        url = f"https://github.com/{client.owner}/{client.repo}/tree/{sanitized}"

    logger.info("Created ad-hoc branch", extra={"branch": sanitized, "base": default_branch})
    return BranchResult(name=sanitized, url=url)
