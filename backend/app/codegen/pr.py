"""
Open a PR for a ticket's already-pushed branch, auto-filled from the
ticket's TicketSpec and the CodegenResult (story 3.3, CDC-25).

Composes CDC-28's GitHubClient with local ticket data (TicketSpec,
CodegenResult) - the PR-opening business logic lives here, not in
app/clients/github_client.py, which stays a pure REST wrapper per CDC-28's
own scoping.

Does NOT push: CDC-23/24 already committed and pushed the branch this
operates on, so the branch is assumed to already be on the remote.

No Teams/orchestrator wiring exists yet anywhere in this project, so this
module just returns the PR number/URL as a plain function result - a
future story turns that into a chat reply.
"""

import logging

from pydantic import BaseModel

from app.clients.github_client import GitHubClient, GitHubValidationError
from app.clients.jira_ticket_spec import TicketSpec
from app.codegen.diff import CodegenResult
from app.codegen.workspace import branch_name
from app.config import get_settings

logger = logging.getLogger("codecrew.codegen_pr")


class PullRequestError(Exception):
    """Raised when opening a PR fails unexpectedly - including the defensive case where a 422 fires but no existing PR is actually found."""


class PullRequestResult(BaseModel):
    number: int
    url: str


def _pr_title(ticket_key: str, spec: TicketSpec) -> str:
    """
    "<TICKET-KEY>: <summary>" - the ticket key alone is what makes GitHub
    for Atlassian auto-link this PR in the ticket's Development panel,
    the same mechanism already proven with commits (CDC-17). No separate
    Jira API call needed.
    """
    return f"{ticket_key}: {spec.summary}"


def _pr_body(ticket_key: str, spec: TicketSpec, result: CodegenResult) -> str:
    criteria = "\n".join(f"- {c}" for c in spec.acceptance_criteria) or "(none provided)"
    jira_url = f"{get_settings().jira_base_url.rstrip('/')}/browse/{ticket_key}"
    return (
        f"## {ticket_key}: {spec.summary}\n\n"
        f"**Jira ticket:** {jira_url}\n\n"
        f"### Acceptance criteria\n{criteria}\n\n"
        f"### What was generated\n{result.summary}\n"
    )


def _find_existing_pull_request(client: GitHubClient, branch: str) -> dict:
    """
    Look up the already-open PR for `branch` after create_pull_request()
    was refused with a 422 (one already exists for it).
    """
    matches = client.list_pull_requests(state="open", head=branch)
    if not matches:
        raise PullRequestError(
            f"GitHub said a PR already exists for {branch}, but none was found via list_pull_requests."
        )
    return matches[0]


def open_pull_request(ticket_key: str, spec: TicketSpec, result: CodegenResult) -> PullRequestResult:
    """
    Open a PR for `ticket_key`'s already-pushed branch (CDC-23/24), with
    title/body auto-filled from `spec` (the ticket) and `result` (what
    codegen actually did). `head` is derived the same way CDC-42's
    worktree creation and CDC-24's commit already derive it - not
    re-derived independently - so it always matches the real branch.
    `base` is the repo's actual default branch, fetched via GitHubClient
    rather than assumed.

    If a PR is already open for this branch, GitHubClient raises
    GitHubValidationError (422) - rather than crash, this looks the
    existing PR up and returns it instead, so re-running codegen for an
    already-open-PR ticket is idempotent.
    """
    branch = branch_name(ticket_key, spec.summary)
    title = _pr_title(ticket_key, spec)
    body = _pr_body(ticket_key, spec, result)

    with GitHubClient() as client:
        base = client.get_repository()["default_branch"]
        try:
            pr = client.create_pull_request(title=title, head=branch, base=base, body=body)
        except GitHubValidationError:
            logger.info(
                "PR already exists for branch, returning the existing one",
                extra={"ticket_key": ticket_key, "branch": branch},
            )
            pr = _find_existing_pull_request(client, branch)

    logger.info(
        "Opened pull request",
        extra={"ticket_key": ticket_key, "branch": branch, "pr_number": pr["number"]},
    )
    return PullRequestResult(number=pr["number"], url=pr["html_url"])
