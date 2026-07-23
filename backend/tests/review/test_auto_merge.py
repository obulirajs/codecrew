"""
Unit tests for app/review/auto_merge.py (story 4.3, CDC-32, built with
story 4.4's off-by-default guarantee - CDC-33; audit logging is story 4.5,
CDC-34).

GitHubClient is mocked wholesale - no real merge is ever performed here.
Focus is CDC-33's core guarantee: execute_auto_merge() must never call
GitHub at all unless BOTH auto_merge_enabled is true AND the decision
itself allows it - plus CDC-34's audit logging: every outcome (blocked by
config, blocked by rules, executed) logs one codecrew.audit line carrying
ticket_key, pr_number, and an explicit executed bool.
"""

import logging
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
            result = execute_auto_merge("CDC-99", 7, _ALLOWED)

        assert result is None
        instance.merge_pull_request.assert_not_called()

    def test_decision_not_allowed_never_calls_github_even_if_enabled(self):
        mock_cls, instance = _mock_github_client()
        with patch("app.review.auto_merge.GitHubClient", mock_cls), patch(
            "app.review.auto_merge.get_settings", return_value=SimpleNamespace(auto_merge_enabled=True)
        ):
            result = execute_auto_merge("CDC-99", 7, _BLOCKED)

        assert result is None
        instance.merge_pull_request.assert_not_called()

    def test_enabled_and_allowed_merges_and_returns_result(self):
        mock_cls, instance = _mock_github_client()
        with patch("app.review.auto_merge.GitHubClient", mock_cls), patch(
            "app.review.auto_merge.get_settings", return_value=SimpleNamespace(auto_merge_enabled=True)
        ):
            result = execute_auto_merge("CDC-99", 7, _ALLOWED)

        assert result == {"merged": True, "sha": "abc123"}
        instance.merge_pull_request.assert_called_once_with(7)


class TestAuditLogging:
    def test_blocked_by_config_logs_audit_line_with_executed_false(self, caplog):
        mock_cls, _ = _mock_github_client()
        with patch("app.review.auto_merge.GitHubClient", mock_cls), patch(
            "app.review.auto_merge.get_settings", return_value=SimpleNamespace(auto_merge_enabled=False)
        ), caplog.at_level(logging.INFO, logger="codecrew.audit"):
            execute_auto_merge("CDC-99", 7, _ALLOWED)

        record = _audit_record_for(caplog, "CDC-99")
        assert record.pr_number == 7
        assert record.executed is False
        assert record.reasons == _ALLOWED.reasons

    def test_blocked_by_rules_logs_audit_line_with_executed_false(self, caplog):
        mock_cls, _ = _mock_github_client()
        with patch("app.review.auto_merge.GitHubClient", mock_cls), patch(
            "app.review.auto_merge.get_settings", return_value=SimpleNamespace(auto_merge_enabled=True)
        ), caplog.at_level(logging.INFO, logger="codecrew.audit"):
            execute_auto_merge("CDC-99", 7, _BLOCKED)

        record = _audit_record_for(caplog, "CDC-99")
        assert record.executed is False
        assert record.reasons == _BLOCKED.reasons

    def test_executed_logs_audit_line_with_executed_true(self, caplog):
        mock_cls, _ = _mock_github_client()
        with patch("app.review.auto_merge.GitHubClient", mock_cls), patch(
            "app.review.auto_merge.get_settings", return_value=SimpleNamespace(auto_merge_enabled=True)
        ), caplog.at_level(logging.INFO, logger="codecrew.audit"):
            execute_auto_merge("CDC-99", 7, _ALLOWED)

        record = _audit_record_for(caplog, "CDC-99")
        assert record.executed is True

    def test_decision_for_a_ticket_key_can_be_found_in_captured_log_output(self, caplog):
        mock_cls, _ = _mock_github_client()
        with patch("app.review.auto_merge.GitHubClient", mock_cls), patch(
            "app.review.auto_merge.get_settings", return_value=SimpleNamespace(auto_merge_enabled=True)
        ), caplog.at_level(logging.INFO, logger="codecrew.audit"):
            execute_auto_merge("CDC-777", 42, _ALLOWED)
            execute_auto_merge("CDC-111", 7, _BLOCKED)

        record = _audit_record_for(caplog, "CDC-777")
        assert record.name == "codecrew.audit"
        assert record.pr_number == 42


def _audit_record_for(caplog, ticket_key: str):
    matching = [r for r in caplog.records if getattr(r, "ticket_key", None) == ticket_key]
    assert len(matching) == 1
    return matching[0]
