"""
Unit tests for app/review/auto_merge.py (story 4.3, CDC-32, built with
story 4.4's off-by-default guarantee - CDC-33).

GitHubClient is mocked wholesale - no real merge is ever performed here.
Focus is CDC-33's core guarantee: execute_auto_merge() must never call
GitHub at all unless BOTH auto_merge_enabled is true AND the decision
itself allows it.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.review.auto_merge import execute_auto_merge
from app.review.merge_rules import MergeDecision

_ALLOWED = MergeDecision(allowed=True, reasons=["review verdict: PASS"])
_BLOCKED = MergeDecision(allowed=False, reasons=["review verdict: FAIL"])


def _mock_github_client():
    mock_cls = MagicMock()
    instance = mock_cls.return_value.__enter__.return_value
    instance.merge_pull_request.return_value = {"merged": True, "sha": "abc123"}
    return mock_cls, instance


class TestExecuteAutoMerge:
    def test_auto_merge_disabled_never_calls_github_even_if_decision_allowed(self):
        mock_cls, instance = _mock_github_client()
        with patch("app.review.auto_merge.GitHubClient", mock_cls), patch(
            "app.review.auto_merge.get_settings", return_value=SimpleNamespace(auto_merge_enabled=False)
        ):
            result = execute_auto_merge(7, _ALLOWED)

        assert result is None
        instance.merge_pull_request.assert_not_called()

    def test_decision_not_allowed_never_calls_github_even_if_enabled(self):
        mock_cls, instance = _mock_github_client()
        with patch("app.review.auto_merge.GitHubClient", mock_cls), patch(
            "app.review.auto_merge.get_settings", return_value=SimpleNamespace(auto_merge_enabled=True)
        ):
            result = execute_auto_merge(7, _BLOCKED)

        assert result is None
        instance.merge_pull_request.assert_not_called()

    def test_enabled_and_allowed_merges_and_returns_result(self):
        mock_cls, instance = _mock_github_client()
        with patch("app.review.auto_merge.GitHubClient", mock_cls), patch(
            "app.review.auto_merge.get_settings", return_value=SimpleNamespace(auto_merge_enabled=True)
        ):
            result = execute_auto_merge(7, _ALLOWED)

        assert result == {"merged": True, "sha": "abc123"}
        instance.merge_pull_request.assert_called_once_with(7)
