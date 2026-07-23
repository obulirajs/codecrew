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

Story 4.5 (CDC-34): every outcome - blocked by config, blocked by rules,
or executed - is logged to the "codecrew.audit" logger (same distinct
name merge_rules.py's evaluate_merge_eligibility() uses), carrying
ticket_key, pr_number, an explicit `executed` bool, and the full reasons
trace, regardless of which of the three outcomes occurred.
"""

import logging
from typing import Optional

from app.clients.github_client import GitHubClient
from app.config import get_settings
from app.review.merge_rules import MergeDecision

audit_logger = logging.getLogger("codecrew.audit")


def execute_auto_merge(ticket_key: str, pr_number: int, decision: MergeDecision) -> Optional[dict]:
    """
    Merge `pr_number` via GitHub's merge_pull_request(), but only if
    settings.auto_merge_enabled is True AND decision.allowed is True.
    Returns None (no GitHub call made) if either gate isn't met, returns
    GitHub's merge response if the merge is actually performed. Every
    outcome is logged as a single audit line via the codecrew.audit
    logger, with `executed` reflecting whether a merge actually happened.
    """
    settings = get_settings()

    if not settings.auto_merge_enabled:
        audit_logger.info(
            "Auto-merge decision: blocked by config",
            extra={"ticket_key": ticket_key, "pr_number": pr_number, "executed": False, "reasons": decision.reasons},
        )
        return None

    if not decision.allowed:
        audit_logger.info(
            "Auto-merge decision: blocked by rules",
            extra={"ticket_key": ticket_key, "pr_number": pr_number, "executed": False, "reasons": decision.reasons},
        )
        return None

    with GitHubClient() as client:
        result = client.merge_pull_request(pr_number)

    audit_logger.info(
        "Auto-merge decision: executed",
        extra={"ticket_key": ticket_key, "pr_number": pr_number, "executed": True, "reasons": decision.reasons},
    )
    return result
