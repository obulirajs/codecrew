"""
Unit tests for app/clients/github_client.py (story 3.6, CDC-28).

Every test patches httpx.Client.request directly, so no real HTTP call
ever leaves the process - matching CDC-16's zero-real-network-calls
pattern for app/clients/jira_client.py.
"""

from typing import Optional
from unittest.mock import patch

import httpx
import pytest

from app.clients.github_client import (
    GitHubAPIError,
    GitHubAuthenticationError,
    GitHubClient,
    GitHubNotFoundError,
    GitHubValidationError,
)

PR_PAYLOAD = {"number": 7, "title": "CDC-41 add retry logic", "state": "open"}


def _response(status_code: int, json=None, headers: Optional[dict] = None) -> httpx.Response:
    return httpx.Response(status_code, json=json if json is not None else {}, headers=headers or {})


@pytest.fixture
def client():
    github_client = GitHubClient()
    yield github_client
    github_client.close()


def test_get_pull_request_success(client):
    with patch("httpx.Client.request", return_value=_response(200, PR_PAYLOAD)) as mock_request:
        result = client.get_pull_request(7)

    assert result == PR_PAYLOAD
    args, _ = mock_request.call_args
    assert args == ("GET", f"/repos/{client.owner}/{client.repo}/pulls/7")


def test_get_pull_request_not_found_raises_specific_exception(client):
    with patch("httpx.Client.request", return_value=_response(404)):
        with pytest.raises(GitHubNotFoundError):
            client.get_pull_request(999)


@pytest.mark.parametrize("status_code", [401, 403])
def test_auth_failure_raises_specific_exception(client, status_code):
    with patch("httpx.Client.request", return_value=_response(status_code)):
        with pytest.raises(GitHubAuthenticationError):
            client.get_pull_request(7)


def test_create_pull_request_validation_error_includes_message(client):
    error_payload = {
        "message": "Validation Failed",
        "errors": [{"resource": "PullRequest", "code": "custom", "message": "A pull request already exists."}],
    }
    with patch("httpx.Client.request", return_value=_response(422, error_payload)):
        with pytest.raises(GitHubValidationError, match="A pull request already exists"):
            client.create_pull_request(title="t", head="feature/x", base="main")


def test_create_pull_request_validation_error_without_json_body(client):
    response = httpx.Response(422, content=b"not json")
    with patch("httpx.Client.request", return_value=response):
        with pytest.raises(GitHubValidationError):
            client.create_pull_request(title="t", head="feature/x", base="main")


def test_self_review_error_with_dict_shaped_errors_surfaces_detailed_message(client):
    """
    Story 4.1 (CDC-30): GitHub rejects a token approving its own PR with a
    422 whose body carries the real reason in "errors[].message" (dict
    shape, seen on PR-creation 422s) - this detail, not just the generic
    HTTP reason phrase, must reach the raised exception.
    """
    error_payload = {
        "message": "Validation Failed",
        "errors": [{"resource": "PullRequestReview", "code": "custom", "message": "Can not approve your own pull request"}],
    }
    with patch("httpx.Client.request", return_value=_response(422, error_payload)):
        with pytest.raises(GitHubValidationError, match="Can not approve your own pull request"):
            client.create_pull_request_review(7, event="APPROVE", body="Looks good")


def test_self_review_error_with_string_shaped_errors_surfaces_detailed_message(client):
    """
    Story 4.1 (CDC-30): review-endpoint 422s carry "errors" as a list of
    plain strings, not {message: ...} objects (e.g. GitHub's actual
    "Review Can not request changes on your own pull request" response) -
    the original fix only handled the dict shape and silently missed this
    one, which is exactly what hid the real error during this story's
    testing.
    """
    error_payload = {
        "message": "Unprocessable Entity",
        "errors": ["Review Can not request changes on your own pull request"],
    }
    with patch("httpx.Client.request", return_value=_response(422, error_payload)):
        with pytest.raises(GitHubValidationError, match="Review Can not request changes on your own pull request"):
            client.create_pull_request_review(7, event="REQUEST_CHANGES", body="Needs work")


def test_auth_failure_surfaces_detailed_message_from_body(client):
    with patch("httpx.Client.request", return_value=_response(403, {"message": "Bad credentials"})):
        with pytest.raises(GitHubAuthenticationError, match="Bad credentials"):
            client.get_pull_request(7)


def test_create_pull_request_builds_expected_request(client):
    with patch("httpx.Client.request", return_value=_response(201, PR_PAYLOAD)) as mock_request:
        result = client.create_pull_request(title="My PR", head="feature/x", base="main", body="details")

    assert result == PR_PAYLOAD
    args, kwargs = mock_request.call_args
    assert args == ("POST", f"/repos/{client.owner}/{client.repo}/pulls")
    assert kwargs["json"] == {"title": "My PR", "head": "feature/x", "base": "main", "body": "details"}


def test_list_pull_requests_default_state_open(client):
    with patch("httpx.Client.request", return_value=_response(200, [PR_PAYLOAD])) as mock_request:
        result = client.list_pull_requests()

    assert result == [PR_PAYLOAD]
    args, kwargs = mock_request.call_args
    assert args == ("GET", f"/repos/{client.owner}/{client.repo}/pulls")
    assert kwargs["params"] == {"state": "open"}


def test_list_pull_requests_with_assignee_uses_search_api(client):
    search_payload = {"items": [PR_PAYLOAD]}
    with patch("httpx.Client.request", return_value=_response(200, search_payload)) as mock_request:
        result = client.list_pull_requests(state="open", assignee="octocat")

    assert result == [PR_PAYLOAD]
    args, kwargs = mock_request.call_args
    assert args == ("GET", "/search/issues")
    assert kwargs["params"] == {
        "q": f"repo:{client.owner}/{client.repo} type:pr state:open assignee:octocat"
    }


def test_list_pull_requests_with_head_filters_and_prefixes_owner(client):
    with patch("httpx.Client.request", return_value=_response(200, [PR_PAYLOAD])) as mock_request:
        result = client.list_pull_requests(state="open", head="feature/CDC-41-x")

    assert result == [PR_PAYLOAD]
    args, kwargs = mock_request.call_args
    assert args == ("GET", f"/repos/{client.owner}/{client.repo}/pulls")
    assert kwargs["params"] == {"state": "open", "head": f"{client.owner}:feature/CDC-41-x"}


def test_get_repository_success(client):
    repo_payload = {"name": client.repo, "default_branch": "main"}
    with patch("httpx.Client.request", return_value=_response(200, repo_payload)) as mock_request:
        result = client.get_repository()

    assert result == repo_payload
    args, _ = mock_request.call_args
    assert args == ("GET", f"/repos/{client.owner}/{client.repo}")


def test_get_authenticated_user_success(client):
    user_payload = {"login": "octocat", "id": 1}
    with patch("httpx.Client.request", return_value=_response(200, user_payload)) as mock_request:
        result = client.get_authenticated_user()

    assert result == user_payload
    args, _ = mock_request.call_args
    assert args == ("GET", "/user")


def test_create_pull_request_review_with_comments(client):
    review_payload = {"id": 99, "state": "CHANGES_REQUESTED"}
    comments = [{"path": "app/foo.py", "line": 10, "body": "Possible off-by-one error."}]
    with patch("httpx.Client.request", return_value=_response(200, review_payload)) as mock_request:
        result = client.create_pull_request_review(
            7, event="REQUEST_CHANGES", body="Overall summary", comments=comments
        )

    assert result == review_payload
    args, kwargs = mock_request.call_args
    assert args == ("POST", f"/repos/{client.owner}/{client.repo}/pulls/7/reviews")
    assert kwargs["json"] == {"event": "REQUEST_CHANGES", "body": "Overall summary", "comments": comments}


def test_create_pull_request_review_without_comments_omits_comments_key(client):
    review_payload = {"id": 100, "state": "APPROVED"}
    with patch("httpx.Client.request", return_value=_response(200, review_payload)) as mock_request:
        result = client.create_pull_request_review(7, event="APPROVE", body="Looks good")

    assert result == review_payload
    _, kwargs = mock_request.call_args
    assert kwargs["json"] == {"event": "APPROVE", "body": "Looks good"}


def test_merge_pull_request_success(client):
    merge_payload = {"merged": True, "sha": "abc123", "message": "Pull Request successfully merged"}
    with patch("httpx.Client.request", return_value=_response(200, merge_payload)) as mock_request:
        result = client.merge_pull_request(7)

    assert result == merge_payload
    args, _ = mock_request.call_args
    assert args == ("PUT", f"/repos/{client.owner}/{client.repo}/pulls/7/merge")


def test_get_pull_request_files_success(client):
    files_payload = [
        {"filename": "app/foo.py", "status": "modified", "patch": "@@ -1,2 +1,3 @@\n+added line"},
        {"filename": "app/bar.png", "status": "modified"},
    ]
    with patch("httpx.Client.request", return_value=_response(200, files_payload)) as mock_request:
        result = client.get_pull_request_files(7)

    assert result == files_payload
    args, kwargs = mock_request.call_args
    assert args == ("GET", f"/repos/{client.owner}/{client.repo}/pulls/7/files")
    assert kwargs["params"] == {"per_page": 100}


def test_retries_once_on_transient_5xx_then_succeeds(client):
    responses = [_response(503), _response(200, PR_PAYLOAD)]
    with patch("httpx.Client.request", side_effect=responses) as mock_request:
        result = client.get_pull_request(7)

    assert result == PR_PAYLOAD
    assert mock_request.call_count == 2


def test_gives_up_after_one_retry_on_persistent_5xx(client):
    responses = [_response(503), _response(503)]
    with patch("httpx.Client.request", side_effect=responses) as mock_request:
        with pytest.raises(GitHubAPIError):
            client.get_pull_request(7)

    assert mock_request.call_count == 2


def test_retries_once_on_timeout_then_succeeds(client):
    responses = [httpx.TimeoutException("timed out"), _response(200, PR_PAYLOAD)]
    with patch("httpx.Client.request", side_effect=responses) as mock_request:
        result = client.get_pull_request(7)

    assert result == PR_PAYLOAD
    assert mock_request.call_count == 2


def test_gives_up_after_one_retry_on_persistent_timeout(client):
    responses = [httpx.TimeoutException("timed out"), httpx.TimeoutException("timed out")]
    with patch("httpx.Client.request", side_effect=responses) as mock_request:
        with pytest.raises(GitHubAPIError):
            client.get_pull_request(7)

    assert mock_request.call_count == 2


def test_backs_off_on_secondary_rate_limit_403_with_retry_after_then_succeeds(client):
    responses = [_response(403, headers={"Retry-After": "0"}), _response(200, PR_PAYLOAD)]
    with patch("httpx.Client.request", side_effect=responses) as mock_request, patch(
        "app.clients.github_client.time.sleep"
    ) as mock_sleep:
        result = client.get_pull_request(7)

    assert result == PR_PAYLOAD
    assert mock_request.call_count == 2
    mock_sleep.assert_called_once_with(0.0)


def test_403_without_retry_after_is_auth_failure_not_rate_limit(client):
    with patch("httpx.Client.request", return_value=_response(403)), patch(
        "app.clients.github_client.time.sleep"
    ) as mock_sleep:
        with pytest.raises(GitHubAuthenticationError):
            client.get_pull_request(7)

    mock_sleep.assert_not_called()


def test_gives_up_after_rate_limit_retry_budget_exhausted(client):
    responses = [_response(403, headers={"Retry-After": "0"})] * 4  # 1 initial attempt + 3 retries
    with patch("httpx.Client.request", side_effect=responses) as mock_request, patch(
        "app.clients.github_client.time.sleep"
    ):
        with pytest.raises(GitHubAPIError):
            client.get_pull_request(7)

    assert mock_request.call_count == 4
