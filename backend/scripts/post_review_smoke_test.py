"""
Manual smoke test for posting a real PR review (story 4.1, CDC-30) - not
part of the pytest suite. Calls post_pr_review() against the real GitHub
repo and real strong-tier model, posting an actual review to the PR.

This posts a real, visible action to GitHub (same caution category as
push_smoke_test.py and pr_smoke_test.py) - do not run against the real
repo without explicit go-ahead.

Usage (from backend/, with REPO_CLONE_PATH, GITHUB_TOKEN, and
ANTHROPIC_API_KEY set in .env):
    python scripts/post_review_smoke_test.py PR_NUMBER
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.logging_config import configure_logging
from app.review.pr_review import ReviewParsingError
from app.review.post_review import post_pr_review


def main() -> None:
    configure_logging()

    if len(sys.argv) < 2:
        print("usage: python scripts/post_review_smoke_test.py PR_NUMBER")
        sys.exit(1)
    pr_number = int(sys.argv[1])

    try:
        result = post_pr_review(pr_number)
    except ReviewParsingError as exc:
        print(f"review parsing failed: {exc}")
        return

    print(f"verdict: {result.verdict}")
    print(f"risk_score: {result.risk_score}")
    print(f"url: {result.url}")


if __name__ == "__main__":
    main()
