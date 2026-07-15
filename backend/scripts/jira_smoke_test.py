"""
Manual smoke test for the JIRA client (story 1.3, CDC-14) - not part of the
pytest suite (see story 1.5 for that). Confirms real authentication against
obulirajs.atlassian.net works end to end by fetching a real ticket.

Usage (from backend/, with a real .env populated):
    python scripts/jira_smoke_test.py [ISSUE_KEY]
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.clients.jira_client import JiraClient


def main() -> None:
    issue_key = sys.argv[1] if len(sys.argv) > 1 else "CDC-6"

    with JiraClient() as client:
        issue = client.get_issue(issue_key)

    fields = issue["fields"]
    print(f"{issue['key']}: {fields['summary']}")
    print(f"Status: {fields['status']['name']}")


if __name__ == "__main__":
    main()
