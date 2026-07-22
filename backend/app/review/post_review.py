"""
Review a PR and post the result as a real GitHub PR review (story 4.1,
CDC-30), consuming CDC-31's structured ReviewResult. Composes
github_client.py with review_pull_request() the same way
app/codegen/pr.py composes github_client.py to open a PR - business logic
lives here, not in the pure REST wrapper.

Corrected understanding (after two rounds of live testing): GitHub's
self-review restriction blocks BOTH APPROVE and REQUEST_CHANGES events on
a PR authored by the same token, not just APPROVE as first assumed - only
a plain COMMENT event succeeds regardless of authorship. Since
GITHUB_TOKEN always authors the PRs it would review, every review this
agent posts is a COMMENT event; the actual verdict, risk_score,
flagged_files, and per-file comments are communicated as text in the
review body instead, since none of that is conveyed by GitHub's native
review-state UI when using COMMENT.

This posts a real, visible action to GitHub (same caution category as
CDC-23's push and CDC-25's PR creation) - must NOT be run against the real
repo without explicit go-ahead.

Explicitly out of scope: any auto-merge decision or execution (CDC-32/33's
job) - this only reviews and comments, never merges.
"""

import logging
from typing import List, Literal

from pydantic import BaseModel

from app.clients.github_client import GitHubClient
from app.review.pr_review import ReviewResult, review_pull_request

logger = logging.getLogger("codecrew.post_review")

_VERDICT_LABEL = {"approve": "Approve", "request_changes": "Request Changes"}


class PostedReview(BaseModel):
    verdict: Literal["approve", "request_changes"]
    risk_score: float
    url: str


def _inline_comments(result: ReviewResult) -> List[dict]:
    return [{"path": c.file, "line": c.line, "body": c.body} for c in result.file_comments]


def _review_body(result: ReviewResult) -> str:
    lines = [
        f"**Recommended: {_VERDICT_LABEL[result.verdict]}**",
        "",
        f"Risk score: {result.risk_score}",
        "Flagged files: " + (", ".join(result.flagged_files) if result.flagged_files else "none"),
        "",
        result.summary,
    ]
    if result.file_comments:
        lines.append("")
        lines.append("File comments:")
        lines.extend(f"- {c.file}:{c.line}: {c.body}" for c in result.file_comments)
    return "\n".join(lines)


def post_pr_review(pr_number: int) -> PostedReview:
    """
    Review `pr_number`'s diff (CDC-31's review_pull_request()) and post it
    as a real GitHub PR review. Always posts a COMMENT event, regardless
    of verdict - GitHub rejects both APPROVE and REQUEST_CHANGES from a
    PR's own author, only COMMENT succeeds. `_review_body()` puts the
    actual recommended verdict, risk_score, flagged_files, and per-file
    comments into the body text so that information isn't lost to the
    COMMENT event's lack of native review-state signaling. Inline
    per-line comments (`file_comments`) are still attached via GitHub's
    own comments array, unaffected by any of this.

    Returns verdict/risk_score/url as a plain function result - "to chat"
    describes future orchestrator wiring, not this story's deliverable
    (same note as CDC-25).
    """
    result = review_pull_request(pr_number)
    comments = _inline_comments(result)
    body = _review_body(result)

    with GitHubClient() as client:
        client.create_pull_request_review(pr_number, event="COMMENT", body=body, comments=comments)
        pr = client.get_pull_request(pr_number)

    logger.info(
        "Posted PR review",
        extra={"pr_number": pr_number, "verdict": result.verdict, "risk_score": result.risk_score},
    )
    return PostedReview(verdict=result.verdict, risk_score=result.risk_score, url=pr["html_url"])
