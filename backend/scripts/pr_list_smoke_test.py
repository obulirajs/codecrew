"""
Manual smoke test for listing PRs (story 3.4, CDC-26) - not part of the
pytest suite. Read-only against the real GitHub repo: calls both
list_open_pull_requests() and list_my_pull_requests() and prints both.

Usage (from backend/, with GITHUB_TOKEN set in .env):
    python scripts/pr_list_smoke_test.py
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.codegen.pr_list import list_my_pull_requests, list_open_pull_requests
from app.logging_config import configure_logging


def main() -> None:
    configure_logging()

    open_prs = list_open_pull_requests()
    print(f"open PRs ({len(open_prs)}):")
    for pr in open_prs:
        print(f"  {pr}")

    my_prs = list_my_pull_requests()
    print(f"\nmy PRs ({len(my_prs)}):")
    for pr in my_prs:
        print(f"  {pr}")


if __name__ == "__main__":
    main()
