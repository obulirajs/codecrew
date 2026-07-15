"""
JIRA API client wrapper - auth, retries, and error handling shared across
agents that need to read from Jira (story 1.3, CDC-14).
"""

import logging
import time
from typing import Any, Optional

import httpx

from app.config import get_settings

logger = logging.getLogger("codecrew.jira_client")

_TRANSIENT_MAX_RETRIES = 1  # retry exactly once on 5xx/timeout, per CDC-14 AC
_RATE_LIMIT_MAX_RETRIES = 3
_DEFAULT_BACKOFF_SECONDS = 2.0


def adf_to_text(node: Optional[dict]) -> str:
    """
    Flatten an Atlassian Document Format node (e.g. an issue's `description`
    field) into plain text - JIRA REST v3 returns rich-text fields as ADF
    JSON, not plain text or markdown. Shared by anything that reads issue
    text: the jira_agent chat replies and the CDC-15 ticket-spec extractor.
    """
    if not node:
        return ""

    parts: list[str] = []

    def walk(n: dict) -> None:
        if n.get("type") == "text":
            parts.append(n.get("text", ""))
        for child in n.get("content", []) or []:
            walk(child)
        if n.get("type") == "paragraph":
            parts.append("\n")

    walk(node)
    return "".join(parts).strip()


class JiraClientError(Exception):
    """Base class for all JIRA client errors."""


class JiraAuthenticationError(JiraClientError):
    """Raised on 401/403 - credentials are missing, wrong, or lack access."""


class JiraIssueNotFoundError(JiraClientError):
    """Raised on 404 - the issue key doesn't exist or isn't visible to this account."""


class JiraAPIError(JiraClientError):
    """Raised for any other non-2xx response, including retries exhausted."""


class JiraClient:
    """Thin wrapper over the JIRA REST API v3, reusable across agents."""

    def __init__(self) -> None:
        settings = get_settings()
        self.project_key = settings.jira_project_key
        self._client = httpx.Client(
            base_url=f"{settings.jira_base_url.rstrip('/')}/rest/api/3",
            auth=(settings.jira_email, settings.jira_api_token),
            headers={"Accept": "application/json"},
            timeout=10.0,
        )

    def get_issue(self, issue_key: str) -> dict[str, Any]:
        """Fetch a single issue by key, e.g. "CDC-6"."""
        return self._request("GET", f"/issue/{issue_key}")

    def search_issues(self, jql: str, max_results: int = 50, fields: Optional[list[str]] = None) -> dict[str, Any]:
        """
        Search issues using JQL, e.g. f"project = {client.project_key}".

        Uses /search/jql (not the deprecated /search - Atlassian removed it,
        see https://developer.atlassian.com/changelog/#CHANGE-2046). This
        endpoint is cursor-paginated: the response has "issues", "isLast",
        and "nextPageToken" instead of a "total" count.
        """
        params: dict[str, Any] = {"jql": jql, "maxResults": max_results}
        if fields:
            params["fields"] = ",".join(fields)
        return self._request("GET", "/search/jql", params=params)

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        transient_attempts = 0
        rate_limit_attempts = 0

        while True:
            try:
                response = self._client.request(method, path, **kwargs)
            except httpx.TimeoutException:
                if transient_attempts >= _TRANSIENT_MAX_RETRIES:
                    logger.error("Jira request timed out after retry: %s %s", method, path)
                    raise JiraAPIError(f"Timed out calling {method} {path} after retry")
                transient_attempts += 1
                logger.warning("Jira request timed out, retrying once: %s %s", method, path)
                continue

            if response.status_code == 429:
                if rate_limit_attempts >= _RATE_LIMIT_MAX_RETRIES:
                    logger.error("Jira rate limit retry budget exhausted: %s %s", method, path)
                    raise JiraAPIError(f"Rate limited on {method} {path} after {rate_limit_attempts} retries")
                retry_after = float(response.headers.get("Retry-After", _DEFAULT_BACKOFF_SECONDS))
                rate_limit_attempts += 1
                logger.warning(
                    "Jira rate limited (429), backing off %.1fs before retry %d/%d: %s %s",
                    retry_after, rate_limit_attempts, _RATE_LIMIT_MAX_RETRIES, method, path,
                )
                time.sleep(retry_after)
                continue

            if response.status_code >= 500:
                if transient_attempts >= _TRANSIENT_MAX_RETRIES:
                    logger.error(
                        "Jira server error persisted after retry: %s %s -> %d",
                        method, path, response.status_code,
                    )
                    raise JiraAPIError(f"Server error {response.status_code} on {method} {path} after retry")
                transient_attempts += 1
                logger.warning(
                    "Jira server error %d, retrying once: %s %s", response.status_code, method, path
                )
                continue

            if response.status_code in (401, 403):
                logger.error("Jira authentication failed: %s %s -> %d", method, path, response.status_code)
                raise JiraAuthenticationError(
                    f"Authentication failed ({response.status_code}) calling {method} {path}"
                )

            if response.status_code == 404:
                logger.warning("Jira resource not found: %s %s", method, path)
                raise JiraIssueNotFoundError(f"Not found calling {method} {path}")

            if response.status_code >= 400:
                logger.error("Jira request failed: %s %s -> %d", method, path, response.status_code)
                raise JiraAPIError(f"Request failed ({response.status_code}) calling {method} {path}")

            return response.json()

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "JiraClient":
        return self

    def __exit__(self, *exc_info: Any) -> None:
        self.close()
