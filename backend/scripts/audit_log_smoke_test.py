"""
Manual smoke test for execute_auto_merge()'s audit logging (story 4.5,
CDC-34) - not part of the pytest suite. Uses a fake MergeDecision with
allowed=False, so execute_auto_merge() logs a "blocked by rules" (or
"blocked by config", depending on AUTO_MERGE_ENABLED) audit line via the
codecrew.audit logger and returns without ever calling GitHub - safe to
run as-is, no real PR is touched.

Usage (from backend/):
    python scripts/audit_log_smoke_test.py
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.logging_config import configure_logging
from app.review.auto_merge import execute_auto_merge
from app.review.merge_rules import MergeDecision


def main() -> None:
    configure_logging()

    decision = MergeDecision(
        allowed=False,
        reasons=[
            "review verdict: FAIL (verdict='request_changes', must be 'approve')",
            "CI status: FAIL (ci_status=None - must be a real 'success' check)",
        ],
    )

    result = execute_auto_merge(ticket_key="CDC-99", pr_number=999, decision=decision)
    print(f"result: {result}")


if __name__ == "__main__":
    main()
