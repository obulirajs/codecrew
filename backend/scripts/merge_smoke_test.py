"""
Manual smoke test for merge_pull_request() (story 4.3, CDC-32) - not part
of the pytest suite. Points a GitHubClient at a disposable scratch repo
(obulirajs/codecrew-merge-scratch) rather than the real obulirajs/codecrew
repo from .env, since a real merge changes shared main history and is far
harder to reverse than a push, PR, or comment.

Creates a real PR from test-merge-branch into main, then really merges it -
both against the scratch repo only.

Usage (from backend/, with GITHUB_TOKEN set in .env - that token must have
access to the scratch repo, and test-merge-branch must already exist there
with commits ahead of main):
    python scripts/merge_smoke_test.py
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.clients.github_client import GitHubClient, GitHubClientError
from app.logging_config import configure_logging


def main() -> None:
    configure_logging()

    client = GitHubClient()
    client.owner = "obulirajs"
    client.repo = "codecrew-merge-scratch"

    try:
        pr = client.create_pull_request(
            title="Merge smoke test", head="test-merge-branch", base="main"
        )
        pr_number = pr["number"]
        print(f"PR number: {pr_number}")

        merge_result = client.merge_pull_request(pr_number)
        print(f"merge response: {merge_result}")
    except GitHubClientError as exc:
        print(f"GitHub operation failed: {exc}")
    finally:
        client.close()


if __name__ == "__main__":
    main()
