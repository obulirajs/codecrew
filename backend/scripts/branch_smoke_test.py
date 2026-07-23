"""
Manual smoke test for creating an ad-hoc branch (story 3.5, CDC-27) - not
part of the pytest suite. Calls create_ad_hoc_branch(name) against the
real GitHub repo and prints the result, or the specific exception if one
is raised.

This creates a real branch on GitHub - a real, visible action - do not run
against the real repo without explicit go-ahead.

Usage (from backend/, with GITHUB_TOKEN set in .env):
    python scripts/branch_smoke_test.py BRANCH_NAME
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.codegen.branch import BranchAlreadyExistsError, InvalidBranchNameError, create_ad_hoc_branch
from app.logging_config import configure_logging


def main() -> None:
    configure_logging()

    if len(sys.argv) < 2:
        print("usage: python scripts/branch_smoke_test.py BRANCH_NAME")
        sys.exit(1)
    name = sys.argv[1]

    try:
        result = create_ad_hoc_branch(name)
    except InvalidBranchNameError as exc:
        print(f"invalid branch name: {exc}")
        return
    except BranchAlreadyExistsError as exc:
        print(f"branch already exists: {exc}")
        return

    print(f"name: {result.name}")
    print(f"url: {result.url}")


if __name__ == "__main__":
    main()
