"""
Unit tests for app/codegen/pr_list.py (story 3.4, CDC-26).

GitHubClient is mocked wholesale - no real HTTP call.
"""

from unittest.mock import MagicMock, patch

from app.codegen.pr_list import PullRequestSummary, list_my_pull_requests, list_open_pull_requests

OPEN_PR = {"number": 7, "title": "Add retry logic", "state": "open", "draft": False, "html_url": "https://github.com/o/r/pull/7"}
DRAFT_PR = {"number": 8, "title": "WIP feature", "state": "open", "draft": True, "html_url": "https://github.com/o/r/pull/8"}
NO_DRAFT_FIELD_PR = {"number": 9, "title": "Legacy result shape", "state": "open", "html_url": "https://github.com/o/r/pull/9"}


def _mock_github_client(**method_returns):
    mock_cls = MagicMock()
    instance = mock_cls.return_value.__enter__.return_value
    for name, value in method_returns.items():
        getattr(instance, name).return_value = value
    return mock_cls, instance


class TestListOpenPullRequests:
    def test_returns_structured_summaries(self):
        mock_cls, instance = _mock_github_client(list_pull_requests=[OPEN_PR, DRAFT_PR])
        with patch("app.codegen.pr_list.GitHubClient", mock_cls):
            result = list_open_pull_requests()

        assert result == [
            PullRequestSummary(number=7, title="Add retry logic", state="open", draft=False, url="https://github.com/o/r/pull/7"),
            PullRequestSummary(number=8, title="WIP feature", state="open", draft=True, url="https://github.com/o/r/pull/8"),
        ]
        instance.list_pull_requests.assert_called_once_with(state="open")

    def test_no_open_prs_returns_empty_list_not_error(self):
        mock_cls, instance = _mock_github_client(list_pull_requests=[])
        with patch("app.codegen.pr_list.GitHubClient", mock_cls):
            result = list_open_pull_requests()

        assert result == []

    def test_missing_draft_field_defaults_to_false(self):
        mock_cls, instance = _mock_github_client(list_pull_requests=[NO_DRAFT_FIELD_PR])
        with patch("app.codegen.pr_list.GitHubClient", mock_cls):
            result = list_open_pull_requests()

        assert result[0].draft is False


class TestListMyPullRequests:
    def test_resolves_me_via_authenticated_user_and_filters_by_assignee(self):
        mock_cls, instance = _mock_github_client(
            get_authenticated_user={"login": "octocat"}, list_pull_requests=[OPEN_PR]
        )
        with patch("app.codegen.pr_list.GitHubClient", mock_cls):
            result = list_my_pull_requests()

        assert result == [
            PullRequestSummary(number=7, title="Add retry logic", state="open", draft=False, url="https://github.com/o/r/pull/7")
        ]
        instance.get_authenticated_user.assert_called_once()
        instance.list_pull_requests.assert_called_once_with(state="open", assignee="octocat")

    def test_nothing_assigned_returns_empty_list_not_error(self):
        mock_cls, instance = _mock_github_client(get_authenticated_user={"login": "octocat"}, list_pull_requests=[])
        with patch("app.codegen.pr_list.GitHubClient", mock_cls):
            result = list_my_pull_requests()

        assert result == []

    def test_state_override_is_passed_through(self):
        mock_cls, instance = _mock_github_client(get_authenticated_user={"login": "octocat"}, list_pull_requests=[])
        with patch("app.codegen.pr_list.GitHubClient", mock_cls):
            list_my_pull_requests(state="closed")

        instance.list_pull_requests.assert_called_once_with(state="closed", assignee="octocat")
