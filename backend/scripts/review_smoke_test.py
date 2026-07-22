"""
Manual smoke test for reviewing a real PR's diff (story 4.2, CDC-31) - not
part of the pytest suite. Calls review_pull_request() against the real
GitHub repo and real strong-tier model, and prints the full structured
ReviewResult.

Usage (from backend/, with REPO_CLONE_PATH, GITHUB_TOKEN, and
ANTHROPIC_API_KEY set in .env):
    python scripts/review_smoke_test.py PR_NUMBER
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.logging_config import configure_logging
from app.review.pr_review import ReviewParsingError, review_pull_request


def main() -> None:
    configure_logging()

    if len(sys.argv) < 2:
        print("usage: python scripts/review_smoke_test.py PR_NUMBER")
        sys.exit(1)
    pr_number = int(sys.argv[1])

    try:
        result = review_pull_request(pr_number)
    except ReviewParsingError as exc:
        print(f"review parsing failed: {exc}")
        return

    print(f"verdict: {result.verdict}")
    print(f"risk_score: {result.risk_score}")
    print(f"flagged_files: {result.flagged_files}")
    print("file_comments:")
    for comment in result.file_comments:
        print(f"  {comment.file}:{comment.line}: {comment.body}")
    print(f"summary: {result.summary}")


if __name__ == "__main__":
    main()
