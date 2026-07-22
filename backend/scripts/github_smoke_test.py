"""
Manual smoke test for the GitHub client (story 3.6, CDC-28) - not part of
the pytest suite (see tests/clients/test_github_client.py for that).
Confirms real PAT authentication against the configured
GITHUB_OWNER/GITHUB_REPO works end to end by listing open PRs.

Usage (from backend/, with a real .env populated):
    python scripts/github_smoke_test.py
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.clients.github_client import GitHubClient


def main() -> None:
    with GitHubClient() as client:
        owner, repo = client.owner, client.repo
        pull_requests = client.list_pull_requests(state="open")

    print(f"Open PRs in {owner}/{repo}: {len(pull_requests)}")
    for pr in pull_requests:
        print(f"  #{pr['number']}: {pr['title']} ({pr['html_url']})")


if __name__ == "__main__":
    main()
