"""
GitHub API client wrapper - auth, retries, and error handling shared
across future Git/GitHub agent stories (story 3.6, CDC-28).

Architecture decision: authenticates with a Personal Access Token, not a
GitHub App - a GitHub App needs its own registration/installation/JWT
token-exchange flow, real overhead not justified at this project's scale.

Scope note: pushing a branch is a plain `git push` using the PAT as an
HTTPS credential - a git operation, same category as everything
app/codegen/workspace.py already does - NOT a REST API call, so it does
not live here. This client wraps what's genuinely a REST API operation:
creating a PR, listing PRs, fetching a single PR's details.
"""

import logging
import time
from typing import Any, List, Optional

import httpx

from app.config import get_settings

logger = logging.getLogger("codecrew.github_client")

_TRANSIENT_MAX_RETRIES = 1  # retry exactly once on 5xx/timeout, matching CDC-14's pattern
_RATE_LIMIT_MAX_RETRIES = 3
_API_VERSION = "2022-11-28"


class GitHubClientError(Exception):
    """Base class for all GitHub client errors."""


class GitHubAuthenticationError(GitHubClientError):
    """Raised on 401/403 - credentials are missing, wrong, or lack access. Not raised for a rate-limited 403 (see GitHubAPIError)."""


class GitHubNotFoundError(GitHubClientError):
    """Raised on 404 - the resource doesn't exist, or isn't visible with this token."""


class GitHubValidationError(GitHubClientError):
    """
    Raised on 422 - most notably, opening a PR for a branch that already
    has one open. Callers (Epic 3) must handle this as an expected
    outcome, not a generic crash.
    """


class GitHubAPIError(GitHubClientError):
    """Raised for any other non-2xx response, including retries/rate-limit backoff exhausted."""


def _validation_message(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return "GitHub validation error (422)"

    message = payload.get("message", "Validation failed")
    errors = payload.get("errors") or []
    if errors and isinstance(errors[0], dict) and errors[0].get("message"):
        return f"{message}: {errors[0]['message']}"
    return message


class GitHubClient:
    """Thin wrapper over the GitHub REST API, reusable across Git/GitHub agent stories."""

    def __init__(self) -> None:
        settings = get_settings()
        self.owner = settings.github_owner
        self.repo = settings.github_repo
        self._client = httpx.Client(
            base_url="https://api.github.com",
            headers={
                "Authorization": f"Bearer {settings.github_token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": _API_VERSION,
            },
            timeout=10.0,
        )

    def create_pull_request(self, title: str, head: str, base: str = "main", body: str = "") -> dict:
        """
        Open a PR from `head` (a branch name, e.g. feature/CDC-41-...)
        into `base`. Raises GitHubValidationError (422) if one is already
        open for that branch - a real-world case, not an edge case.
        """
        payload = {"title": title, "head": head, "base": base, "body": body}
        return self._request("POST", f"/repos/{self.owner}/{self.repo}/pulls", json=payload)

    def list_pull_requests(
        self, state: str = "open", assignee: Optional[str] = None, head: Optional[str] = None
    ) -> List[dict]:
        """
        List PRs in this repo. Plain `state`/`head` filtering uses the
        pulls list endpoint directly - `head` is a bare branch name in
        this repo (e.g. "feature/CDC-41-x"); GitHub's own API requires it
        as "owner:branch", so that prefixing happens here rather than
        leaking that detail to callers. Filtering by `assignee` goes
        through the Search API instead: GitHub's /pulls list endpoint has
        no assignee filter of its own. `head` and `assignee` are not
        combined - no caller needs that today.
        """
        if assignee:
            query = f"repo:{self.owner}/{self.repo} type:pr state:{state} assignee:{assignee}"
            result = self._request("GET", "/search/issues", params={"q": query})
            return result["items"]

        params: dict = {"state": state}
        if head:
            params["head"] = f"{self.owner}:{head}"
        return self._request("GET", f"/repos/{self.owner}/{self.repo}/pulls", params=params)

    def get_pull_request(self, pr_number: int) -> dict:
        """Fetch a single PR's details by number."""
        return self._request("GET", f"/repos/{self.owner}/{self.repo}/pulls/{pr_number}")

    def get_repository(self) -> dict:
        """Fetch this repo's metadata - most notably `default_branch`, so callers never have to hardcode it."""
        return self._request("GET", f"/repos/{self.owner}/{self.repo}")

    def get_pull_request_files(self, pr_number: int) -> List[dict]:
        """
        Fetch a PR's changed files, each with its `patch` (unified diff
        text GitHub itself computed) - story 4.2's (CDC-31) review agent
        reads this instead of exploring the repo, since the PR diff
        already carries per-file before/after context. Single page (up to
        100 files) - same simplicity as list_pull_requests(), which
        doesn't paginate either; no caller needs more yet.
        """
        return self._request(
            "GET", f"/repos/{self.owner}/{self.repo}/pulls/{pr_number}/files", params={"per_page": 100}
        )

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        transient_attempts = 0
        rate_limit_attempts = 0

        while True:
            try:
                response = self._client.request(method, path, **kwargs)
            except httpx.TimeoutException:
                if transient_attempts >= _TRANSIENT_MAX_RETRIES:
                    logger.error("GitHub request timed out after retry: %s %s", method, path)
                    raise GitHubAPIError(f"Timed out calling {method} {path} after retry")
                transient_attempts += 1
                logger.warning("GitHub request timed out, retrying once: %s %s", method, path)
                continue

            # GitHub's secondary rate limits (abuse detection) show up as
            # 403 or 429 with a Retry-After header - unlike the primary
            # rate limit (X-RateLimit-* headers, no Retry-After), which
            # this story doesn't need to handle. Checked before the
            # generic 401/403 handling below so a rate-limited 403 isn't
            # misreported as an auth failure.
            retry_after = response.headers.get("Retry-After")
            if retry_after is not None and response.status_code in (403, 429):
                if rate_limit_attempts >= _RATE_LIMIT_MAX_RETRIES:
                    logger.error("GitHub rate limit retry budget exhausted: %s %s", method, path)
                    raise GitHubAPIError(f"Rate limited on {method} {path} after {rate_limit_attempts} retries")
                wait_seconds = float(retry_after)
                rate_limit_attempts += 1
                logger.warning(
                    "GitHub rate limited (%d), backing off %.1fs before retry %d/%d: %s %s",
                    response.status_code, wait_seconds, rate_limit_attempts, _RATE_LIMIT_MAX_RETRIES, method, path,
                )
                time.sleep(wait_seconds)
                continue

            if response.status_code >= 500:
                if transient_attempts >= _TRANSIENT_MAX_RETRIES:
                    logger.error(
                        "GitHub server error persisted after retry: %s %s -> %d",
                        method, path, response.status_code,
                    )
                    raise GitHubAPIError(f"Server error {response.status_code} on {method} {path} after retry")
                transient_attempts += 1
                logger.warning(
                    "GitHub server error %d, retrying once: %s %s", response.status_code, method, path
                )
                continue

            if response.status_code in (401, 403):
                logger.error("GitHub authentication failed: %s %s -> %d", method, path, response.status_code)
                raise GitHubAuthenticationError(
                    f"Authentication failed ({response.status_code}) calling {method} {path}"
                )

            if response.status_code == 404:
                logger.warning("GitHub resource not found: %s %s", method, path)
                raise GitHubNotFoundError(f"Not found calling {method} {path}")

            if response.status_code == 422:
                logger.warning("GitHub validation error: %s %s", method, path)
                raise GitHubValidationError(_validation_message(response))

            if response.status_code >= 400:
                logger.error("GitHub request failed: %s %s -> %d", method, path, response.status_code)
                raise GitHubAPIError(f"Request failed ({response.status_code}) calling {method} {path}")

            return response.json()

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "GitHubClient":
        return self

    def __exit__(self, *exc_info: Any) -> None:
        self.close()
