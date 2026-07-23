"""
Unit tests for app/review/merge_rules.py (story 4.3, CDC-32).

evaluate_merge_eligibility() is a pure function - no GitHub calls, no
mocking needed beyond the settings defaults (auto_merge_enabled=False,
max_auto_merge_lines=200, sensitive paths/ticket-type allow-list) already
in place with no .env override.
"""

from app.review.merge_rules import evaluate_merge_eligibility
from app.review.pr_review import ReviewResult

_APPROVE = ReviewResult(verdict="approve", risk_score=0.1, flagged_files=[], file_comments=[], summary="Looks good.")
_REQUEST_CHANGES = ReviewResult(
    verdict="request_changes", risk_score=0.8, flagged_files=["a.py"], file_comments=[], summary="Needs work."
)


def _evaluate(**overrides):
    defaults = dict(
        ticket_key="CDC-99",
        pr_number=42,
        review=_APPROVE,
        ci_status="success",
        ticket_type="Task",
        changed_files=["app/foo.py"],
        diff_lines=10,
    )
    defaults.update(overrides)
    return evaluate_merge_eligibility(**defaults)


class TestEvaluateMergeEligibility:
    def test_all_rules_pass_is_allowed(self):
        decision = _evaluate()
        assert decision.allowed is True
        assert len(decision.reasons) == 5
        assert all("PASS" in r for r in decision.reasons)

    def test_request_changes_verdict_fails_review_rule(self):
        decision = _evaluate(review=_REQUEST_CHANGES)
        assert decision.allowed is False
        assert any("review verdict: FAIL" in r for r in decision.reasons)

    def test_no_ci_configured_fails_ci_rule_not_treated_as_passing(self):
        decision = _evaluate(ci_status=None)
        assert decision.allowed is False
        assert any("CI status: FAIL" in r and "None" in r for r in decision.reasons)

    def test_ci_failure_status_fails_ci_rule(self):
        decision = _evaluate(ci_status="failure")
        assert decision.allowed is False
        assert any("CI status: FAIL" in r for r in decision.reasons)

    def test_diff_over_threshold_fails_size_rule(self):
        decision = _evaluate(diff_lines=201)
        assert decision.allowed is False
        assert any("diff size: FAIL" in r for r in decision.reasons)

    def test_diff_at_threshold_passes_size_rule(self):
        decision = _evaluate(diff_lines=200)
        assert decision.allowed is True

    def test_config_py_is_a_sensitive_path_at_any_depth(self):
        decision = _evaluate(changed_files=["app/config.py"])
        assert decision.allowed is False
        assert any("sensitive paths: FAIL" in r for r in decision.reasons)

    def test_env_glob_is_a_sensitive_path(self):
        decision = _evaluate(changed_files=[".env.example"])
        assert decision.allowed is False

    def test_clients_directory_is_a_sensitive_path(self):
        decision = _evaluate(changed_files=["app/clients/github_client.py"])
        assert decision.allowed is False

    def test_non_sensitive_file_passes_rule(self):
        decision = _evaluate(changed_files=["app/review/merge_rules.py"])
        assert decision.allowed is True

    def test_ticket_type_not_in_allowlist_fails_rule(self):
        decision = _evaluate(ticket_type="Story")
        assert decision.allowed is False
        assert any("ticket type: FAIL" in r for r in decision.reasons)

    def test_ticket_type_in_allowlist_passes_rule(self):
        decision = _evaluate(ticket_type="Chore")
        assert decision.allowed is True

    def test_reasons_include_an_entry_for_every_rule_even_when_blocked(self):
        decision = _evaluate(review=_REQUEST_CHANGES, ci_status=None, diff_lines=500, ticket_type="Story")
        assert decision.allowed is False
        assert len(decision.reasons) == 5


class TestAuditLogging:
    def test_decision_for_a_ticket_key_can_be_found_in_captured_log_output(self, caplog):
        """Story 4.5 (CDC-34): a decision must be filterable by ticket_key from log output."""
        import logging

        with caplog.at_level(logging.INFO, logger="codecrew.audit"):
            _evaluate(ticket_key="CDC-777", pr_number=42)
            _evaluate(ticket_key="CDC-111", pr_number=7)

        matching = [r for r in caplog.records if getattr(r, "ticket_key", None) == "CDC-777"]
        assert len(matching) == 1
        record = matching[0]
        assert record.name == "codecrew.audit"
        assert record.pr_number == 42
        assert record.executed is False
        assert isinstance(record.reasons, list) and len(record.reasons) == 5
