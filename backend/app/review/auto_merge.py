"""
Execute an auto-merge decision (story 4.3, CDC-32, built together with
story 4.4's off-by-default guarantee - CDC-33). This is the one function
allowed to actually merge a PR - a real, visible, hard-to-reverse action
on shared main history, far harder to reverse than a push, PR, or comment.
Must NEVER be run against the real obulirajs/codecrew repo without
explicit, deliberate go-ahead.

execute_auto_merge() independently re-checks both gates itself - config
(`auto_merge_enabled`) and the rules-engine result
(`MergeDecision.allowed`) - rather than trusting the caller already did,
so this function is never reachable with auto-merge disabled regardless
of how many rules passed (CDC-33's core guarantee, verified here since
the two stories are one feature).
"""

import logging
from typing import Optional

from app.clients.github_client import GitHubClient
from app.config import get_settings
from app.review.merge_rules import MergeDecision

logger = logging.getLogger("codecrew.auto_merge")


def execute_auto_merge(pr_number: int, decision: MergeDecision) -> Optional[dict]:
    """
    Merge `pr_number` via GitHub's merge_pull_request(), but only if
    settings.auto_merge_enabled is True AND decision.allowed is True.
    Returns None (no GitHub call made) if either gate isn't met - logging
    which specific rule(s) blocked it when the decision itself disallowed
    it. Returns GitHub's merge response, logging which rule(s) permitted
    it, when the merge is actually performed.
    """
    settings = get_settings()

    if not settings.auto_merge_enabled:
        logger.info(
            "Auto-merge disabled by config - not merging",
            extra={"pr_number": pr_number},
        )
        return None

    if not decision.allowed:
        logger.info(
            "Auto-merge blocked by rules - not merging",
            extra={"pr_number": pr_number, "reasons": decision.reasons},
        )
        return None

    with GitHubClient() as client:
        result = client.merge_pull_request(pr_number)

    logger.info(
        "Auto-merged pull request",
        extra={"pr_number": pr_number, "reasons": decision.reasons},
    )
    return result
