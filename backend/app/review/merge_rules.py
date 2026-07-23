"""
Deterministic auto-merge eligibility rules (story 4.3, CDC-32). Built
together with story 4.4's off-by-default guarantee (CDC-33) - they're one
feature; that guarantee lives in app/review/auto_merge.py's
execute_auto_merge(), which is the only thing allowed to act on the
decision this module produces.

evaluate_merge_eligibility() is a pure function - no GitHub calls, no I/O -
so it's fully unit-testable on its own, deliberately separate from the
actual merge-execution function in auto_merge.py.

Critical constraints from the ticket:

* CI status: there is no CI pipeline yet (Epic 5 not built), so no real PR
  can ever satisfy this rule today. `ci_status` must be exactly "success"
  (a real passing check) to pass - None ("no CI configured") or any other
  value is always a failure, never silently treated as passing. This
  correctly makes auto-merge impossible until Epic 5 exists.
* Review verdict: checks `review.verdict` - CDC-31's internal ReviewResult,
  computed and stored directly by this codebase - never GitHub's own
  review-decision state. GitHub will never show this bot's review as
  "Approved" regardless of internal verdict, since CDC-30's self-review
  restriction means every review posts as a plain COMMENT. This function
  takes no GitHub review-decision parameter at all, so that mistake isn't
  representable here.

Story 4.5 (CDC-34): every evaluation is also logged to the "codecrew.audit"
logger - a name distinct from general app logs so audit entries are
independently filterable/greppable even before a dedicated audit store
exists (Epic 8 story 8.3) - carrying ticket_key and pr_number alongside
the reasons trace, so a decision can always be tied back to the Jira
ticket it originated from. `executed` is always False here: this function
only ever computes a decision, never performs a merge (that's
auto_merge.py's execute_auto_merge(), which logs its own outcome line to
the same logger).
"""

import fnmatch
import logging
from typing import List, Optional

from pydantic import BaseModel

from app.config import get_settings
from app.review.pr_review import ReviewResult

audit_logger = logging.getLogger("codecrew.audit")


class MergeDecision(BaseModel):
    allowed: bool
    reasons: List[str]


def _matches_sensitive_path(file_path: str, patterns: List[str]) -> bool:
    """
    Match `file_path` against a sensitive-path pattern (e.g. "config.py",
    ".env*", "clients/*") regardless of how deep in the repo it sits - by
    checking every path suffix (e.g. "app/clients/github_client.py" also
    tries "clients/github_client.py" and "github_client.py"), not just the
    full path or bare filename.
    """
    parts = file_path.split("/")
    suffixes = ["/".join(parts[i:]) for i in range(len(parts))]
    return any(fnmatch.fnmatch(suffix, pattern) for suffix in suffixes for pattern in patterns)


def evaluate_merge_eligibility(
    ticket_key: str,
    pr_number: int,
    review: ReviewResult,
    ci_status: Optional[str],
    ticket_type: str,
    changed_files: List[str],
    diff_lines: int,
) -> MergeDecision:
    """
    Evaluate every auto-merge rule independently and return a
    MergeDecision - `allowed` is True only if every rule passes;
    `reasons` always carries one PASS/FAIL entry per rule (not just
    failures), so both "which rule(s) blocked this" and "which rule(s)
    permitted this" are visible from the same trace. `ticket_key` and
    `pr_number` don't affect any rule - they're threaded through purely so
    the audit log line below can tie this decision back to its
    originating ticket and PR.
    """
    settings = get_settings()
    reasons: List[str] = []
    allowed = True

    if review.verdict == "approve":
        reasons.append(f"review verdict: PASS (verdict={review.verdict!r})")
    else:
        reasons.append(f"review verdict: FAIL (verdict={review.verdict!r}, must be 'approve')")
        allowed = False

    if ci_status == "success":
        reasons.append("CI status: PASS (success)")
    else:
        reasons.append(
            f"CI status: FAIL (ci_status={ci_status!r} - must be a real 'success' check; "
            "no CI configured is never treated as passing)"
        )
        allowed = False

    if diff_lines <= settings.max_auto_merge_lines:
        reasons.append(f"diff size: PASS ({diff_lines} <= {settings.max_auto_merge_lines} lines)")
    else:
        reasons.append(f"diff size: FAIL ({diff_lines} > {settings.max_auto_merge_lines} lines)")
        allowed = False

    sensitive_files = [f for f in changed_files if _matches_sensitive_path(f, settings.auto_merge_sensitive_paths)]
    if not sensitive_files:
        reasons.append("sensitive paths: PASS (no sensitive files changed)")
    else:
        reasons.append(f"sensitive paths: FAIL (sensitive files changed: {sensitive_files})")
        allowed = False

    if ticket_type in settings.auto_merge_allowed_ticket_types:
        reasons.append(f"ticket type: PASS ({ticket_type!r} allowed)")
    else:
        reasons.append(
            f"ticket type: FAIL ({ticket_type!r} not in allow-list {settings.auto_merge_allowed_ticket_types})"
        )
        allowed = False

    decision = MergeDecision(allowed=allowed, reasons=reasons)

    audit_logger.info(
        "Merge eligibility evaluated",
        extra={
            "ticket_key": ticket_key,
            "pr_number": pr_number,
            "executed": False,
            "allowed": decision.allowed,
            "reasons": decision.reasons,
        },
    )
    return decision
