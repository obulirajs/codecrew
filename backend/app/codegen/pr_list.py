"""
List open PRs / PRs assigned to me (story 3.4, CDC-26). Composes CDC-28's
GitHubClient the same way app/codegen/pr.py composes it to open a PR -
business logic lives here, not in the pure REST wrapper.

Scope note (per the ticket): no real per-user identity mapping exists yet
(same simplification as CDC-13's JIRA identity gap - an Epic 8 concern for
later). "Me" resolves to whichever GitHub account the configured
GITHUB_TOKEN belongs to, via GitHubClient's get_authenticated_user().

"Assigned to me" means GitHub's actual assignees field specifically -
distinct from PR author or requested reviewers, which are different
GitHub concepts often conflated in casual speech - queried via
list_pull_requests(assignee=...)'s existing Search API path (CDC-28), not
anything new here. "List open PRs" uses that same existing
list_pull_requests(state="open") - no new REST capability needed for
either half beyond get_authenticated_user().

Returns plain function results, not literally posted to chat - no
orchestrator/Teams wiring exists yet anywhere in this project (same note
as CDC-25/CDC-30).
"""

import logging
from typing import List

from pydantic import BaseModel

from app.clients.github_client import GitHubClient

logger = logging.getLogger("codecrew.codegen_pr_list")


class PullRequestSummary(BaseModel):
    number: int
    title: str
    state: str
    draft: bool
    url: str


def _to_summary(pr: dict) -> PullRequestSummary:
    return PullRequestSummary(
        number=pr["number"],
        title=pr["title"],
        state=pr["state"],
        draft=pr.get("draft", False),
        url=pr["html_url"],
    )


def list_open_pull_requests() -> List[PullRequestSummary]:
    """List every open PR in the repo. Returns an empty list, not an error, if none are open."""
    with GitHubClient() as client:
        prs = client.list_pull_requests(state="open")

    logger.info("Listed open pull requests", extra={"count": len(prs)})
    return [_to_summary(pr) for pr in prs]


def list_my_pull_requests(state: str = "open") -> List[PullRequestSummary]:
    """
    List PRs assigned (GitHub's actual assignees field, not author or
    requested reviewers) to whichever account GITHUB_TOKEN belongs to.
    Returns an empty list, not an error, if nothing is assigned.
    """
    with GitHubClient() as client:
        me = client.get_authenticated_user()["login"]
        prs = client.list_pull_requests(state=state, assignee=me)

    logger.info("Listed pull requests assigned to me", extra={"assignee": me, "count": len(prs)})
    return [_to_summary(pr) for pr in prs]
