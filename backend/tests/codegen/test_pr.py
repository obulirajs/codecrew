"""
Unit tests for app/codegen/pr.py (story 3.3, CDC-25).

GitHubClient is mocked wholesale - no real HTTP call - these tests cover
title/body content, head/base derivation, the idempotent 422 lookup path,
and the defensive "422 but no match found" failure.
"""

from unittest.mock import MagicMock, patch

import pytest

from app.clients.github_client import GitHubValidationError
from app.clients.jira_ticket_spec import TicketSpec
from app.codegen.diff import CodegenResult
from app.codegen.pr import PullRequestError, PullRequestResult, open_pull_request
from app.codegen.workspace import branch_name
from app.config import get_settings

_SPEC = TicketSpec(
    summary="Add retry logic",
    acceptance_criteria=["Retries once on timeout", "Logs a warning on retry"],
    ticket_type="Story",
    labels=["backend"],
)

_RESULT = CodegenResult(
    diff_text="diff --git a/foo.py b/foo.py\n+added line\n",
    summary="Added a retry loop around the HTTP call.",
    files_changed=["foo.py"],
    needs_clarification=False,
    clarifying_questions=[],
    lint_errors=[],
)

PR_PAYLOAD = {"number": 7, "html_url": "https://github.com/o/r/pull/7"}


def _mock_github_client(**method_returns):
    mock_cls = MagicMock()
    instance = mock_cls.return_value.__enter__.return_value
    instance.owner = "o"
    instance.repo = "r"
    instance.get_repository.return_value = {"default_branch": "main"}
    for name, value in method_returns.items():
        getattr(instance, name).return_value = value
    return mock_cls, instance


class TestOpenPullRequest:
    def test_creates_pr_with_expected_title_head_base_and_returns_result(self):
        mock_cls, instance = _mock_github_client(create_pull_request=PR_PAYLOAD)
        with patch("app.codegen.pr.GitHubClient", mock_cls):
            result = open_pull_request("CDC-41", _SPEC, _RESULT)

        assert isinstance(result, PullRequestResult)
        assert result.number == 7
        assert result.url == "https://github.com/o/r/pull/7"

        _, kwargs = instance.create_pull_request.call_args
        assert kwargs["title"] == "CDC-41: Add retry logic"
        assert kwargs["head"] == branch_name("CDC-41", _SPEC.summary)
        assert kwargs["base"] == "main"
        instance.get_repository.assert_called_once()

    def test_body_includes_ticket_key_ac_summary_and_jira_link(self):
        mock_cls, instance = _mock_github_client(create_pull_request=PR_PAYLOAD)
        with patch("app.codegen.pr.GitHubClient", mock_cls):
            open_pull_request("CDC-41", _SPEC, _RESULT)

        _, kwargs = instance.create_pull_request.call_args
        body = kwargs["body"]
        assert "CDC-41" in body
        assert "Retries once on timeout" in body
        assert "Logs a warning on retry" in body
        assert "Added a retry loop around the HTTP call." in body
        assert get_settings().jira_base_url.rstrip("/") + "/browse/CDC-41" in body

    def test_existing_pr_on_422_is_looked_up_and_returned_instead_of_raising(self):
        mock_cls, instance = _mock_github_client()
        instance.create_pull_request.side_effect = GitHubValidationError("A pull request already exists")
        instance.list_pull_requests.return_value = [PR_PAYLOAD]

        with patch("app.codegen.pr.GitHubClient", mock_cls):
            result = open_pull_request("CDC-41", _SPEC, _RESULT)

        assert result.number == 7
        assert result.url == "https://github.com/o/r/pull/7"

        _, kwargs = instance.list_pull_requests.call_args
        assert kwargs["state"] == "open"
        assert kwargs["head"] == branch_name("CDC-41", _SPEC.summary)

    def test_422_with_no_existing_pr_found_raises_pull_request_error(self):
        mock_cls, instance = _mock_github_client()
        instance.create_pull_request.side_effect = GitHubValidationError("A pull request already exists")
        instance.list_pull_requests.return_value = []

        with patch("app.codegen.pr.GitHubClient", mock_cls):
            with pytest.raises(PullRequestError):
                open_pull_request("CDC-41", _SPEC, _RESULT)
