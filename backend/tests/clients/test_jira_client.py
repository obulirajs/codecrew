"""
Unit tests for app/clients/jira_client.py (story 1.5, CDC-16).

Every test patches httpx.Client.request directly, so no real HTTP call
ever leaves the process - this is what CDC-16's Definition of Done
("pytest passes with zero real network calls") requires.
"""

from typing import Optional
from unittest.mock import patch

import httpx
import pytest

from app.clients.jira_client import (
    JiraAPIError,
    JiraAuthenticationError,
    JiraClient,
    JiraIssueNotFoundError,
)

ISSUE_PAYLOAD = {"key": "CDC-6", "fields": {"summary": "Test ticket"}}


def _response(status_code: int, json: Optional[dict] = None, headers: Optional[dict] = None) -> httpx.Response:
    return httpx.Response(status_code, json=json or {}, headers=headers or {})


@pytest.fixture
def client():
    jira_client = JiraClient()
    yield jira_client
    jira_client.close()


def test_get_issue_success(client):
    with patch("httpx.Client.request", return_value=_response(200, ISSUE_PAYLOAD)) as mock_request:
        result = client.get_issue("CDC-6")

    assert result == ISSUE_PAYLOAD
    mock_request.assert_called_once()


def test_get_issue_not_found_raises_specific_exception(client):
    with patch("httpx.Client.request", return_value=_response(404)):
        with pytest.raises(JiraIssueNotFoundError):
            client.get_issue("CDC-999")


@pytest.mark.parametrize("status_code", [401, 403])
def test_get_issue_auth_failure_raises_specific_exception(client, status_code):
    with patch("httpx.Client.request", return_value=_response(status_code)):
        with pytest.raises(JiraAuthenticationError):
            client.get_issue("CDC-6")


def test_retries_once_on_transient_5xx_then_succeeds(client):
    responses = [_response(503), _response(200, ISSUE_PAYLOAD)]
    with patch("httpx.Client.request", side_effect=responses) as mock_request:
        result = client.get_issue("CDC-6")

    assert result == ISSUE_PAYLOAD
    assert mock_request.call_count == 2


def test_gives_up_after_one_retry_on_persistent_5xx(client):
    responses = [_response(503), _response(503)]
    with patch("httpx.Client.request", side_effect=responses) as mock_request:
        with pytest.raises(JiraAPIError):
            client.get_issue("CDC-6")

    assert mock_request.call_count == 2


def test_retries_once_on_timeout_then_succeeds(client):
    responses = [httpx.TimeoutException("timed out"), _response(200, ISSUE_PAYLOAD)]
    with patch("httpx.Client.request", side_effect=responses) as mock_request:
        result = client.get_issue("CDC-6")

    assert result == ISSUE_PAYLOAD
    assert mock_request.call_count == 2


def test_gives_up_after_one_retry_on_persistent_timeout(client):
    responses = [httpx.TimeoutException("timed out"), httpx.TimeoutException("timed out")]
    with patch("httpx.Client.request", side_effect=responses) as mock_request:
        with pytest.raises(JiraAPIError):
            client.get_issue("CDC-6")

    assert mock_request.call_count == 2


def test_backs_off_and_retries_on_429_then_succeeds(client):
    responses = [_response(429, headers={"Retry-After": "0"}), _response(200, ISSUE_PAYLOAD)]
    with patch("httpx.Client.request", side_effect=responses) as mock_request, patch(
        "app.clients.jira_client.time.sleep"
    ) as mock_sleep:
        result = client.get_issue("CDC-6")

    assert result == ISSUE_PAYLOAD
    assert mock_request.call_count == 2
    mock_sleep.assert_called_once()


def test_gives_up_after_rate_limit_retry_budget_exhausted(client):
    responses = [_response(429, headers={"Retry-After": "0"})] * 4  # 1 initial attempt + 3 retries
    with patch("httpx.Client.request", side_effect=responses) as mock_request, patch(
        "app.clients.jira_client.time.sleep"
    ):
        with pytest.raises(JiraAPIError):
            client.get_issue("CDC-6")

    assert mock_request.call_count == 4


def test_search_issues_builds_expected_request(client):
    search_payload = {"issues": [{"key": "CDC-1"}], "isLast": True}
    with patch("httpx.Client.request", return_value=_response(200, search_payload)) as mock_request:
        result = client.search_issues("project = CDC", max_results=5, fields=["summary", "status"])

    assert result == search_payload
    args, kwargs = mock_request.call_args
    assert args == ("GET", "/search/jql")
    assert kwargs["params"] == {"jql": "project = CDC", "maxResults": 5, "fields": "summary,status"}
