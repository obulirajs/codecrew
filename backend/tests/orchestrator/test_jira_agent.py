"""
Unit tests for app/orchestrator/jira_agent.py (stories 1.1/1.2, CDC-16
coverage). JiraClient is mocked wholesale here - no real network calls;
its own retry/error/HTTP behavior is unit-tested separately in
tests/clients/test_jira_client.py.
"""

from unittest.mock import MagicMock, patch

from app.clients.jira_client import JiraIssueNotFoundError
from app.models.events import NormalizedEvent, Platform
from app.orchestrator.jira_agent import handle_jira_query

ISSUE_PAYLOAD = {
    "fields": {
        "summary": "Test ticket",
        "status": {"name": "In Progress"},
        "assignee": {"displayName": "Jane Doe"},
        "description": {
            "type": "doc",
            "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Some details."}]}],
        },
    }
}


def _state(text: str) -> dict:
    event = NormalizedEvent(user="u1", channel="c1", text=text, platform=Platform.teams)
    return {"event": event, "intent": "jira_query"}


def _mock_jira_client(**method_returns):
    """Stand in for `with JiraClient() as client: ...` with canned method returns."""
    mock_cls = MagicMock()
    instance = mock_cls.return_value.__enter__.return_value
    instance.project_key = "CDC"
    for name, value in method_returns.items():
        getattr(instance, name).return_value = value
    return mock_cls, instance


class TestShowTicket:
    def test_valid_ticket_key_returns_correct_summary(self):
        mock_cls, _ = _mock_jira_client(get_issue=ISSUE_PAYLOAD)
        with patch("app.orchestrator.jira_agent.JiraClient", mock_cls):
            result = handle_jira_query(_state("show me ticket CDC-12"))

        reply = result["reply_text"]
        assert "CDC-12" in reply
        assert "Test ticket" in reply
        assert "In Progress" in reply
        assert "Jane Doe" in reply

    def test_no_recognizable_key_asks_for_a_valid_key(self):
        mock_cls, instance = _mock_jira_client()
        with patch("app.orchestrator.jira_agent.JiraClient", mock_cls):
            result = handle_jira_query(_state("hello there"))

        assert "ticket key" in result["reply_text"].lower()
        instance.get_issue.assert_not_called()

    def test_nonexistent_key_returns_not_found_reply(self):
        mock_cls, instance = _mock_jira_client()
        instance.get_issue.side_effect = JiraIssueNotFoundError("not found")
        with patch("app.orchestrator.jira_agent.JiraClient", mock_cls):
            result = handle_jira_query(_state("show me ticket CDC-999"))

        assert "couldn't find" in result["reply_text"].lower()


class TestListAssigned:
    def test_returns_tickets_for_the_configured_user(self):
        search_result = {
            "issues": [
                {"key": "CDC-1", "fields": {"summary": "First", "status": {"name": "To Do"}}},
                {"key": "CDC-2", "fields": {"summary": "Second", "status": {"name": "Done"}}},
            ],
            "isLast": True,
        }
        mock_cls, instance = _mock_jira_client(search_issues=search_result)
        with patch("app.orchestrator.jira_agent.JiraClient", mock_cls):
            result = handle_jira_query(_state("list my tickets"))

        reply = result["reply_text"]
        assert "CDC-1" in reply and "First" in reply
        assert "CDC-2" in reply and "Second" in reply
        instance.search_issues.assert_called_once()

    def test_empty_list_returns_no_tickets_assigned_reply(self):
        mock_cls, _ = _mock_jira_client(search_issues={"issues": [], "isLast": True})
        with patch("app.orchestrator.jira_agent.JiraClient", mock_cls):
            result = handle_jira_query(_state("what's assigned to me"))

        assert "no tickets assigned" in result["reply_text"].lower()

    def test_large_result_set_stays_capped_and_readable(self):
        issues = [
            {"key": f"CDC-{i}", "fields": {"summary": f"Ticket {i}", "status": {"name": "To Do"}}}
            for i in range(10)
        ]
        mock_cls, instance = _mock_jira_client(search_issues={"issues": issues, "isLast": False})
        with patch("app.orchestrator.jira_agent.JiraClient", mock_cls):
            result = handle_jira_query(_state("list my tickets"))

        reply = result["reply_text"]
        assert reply.count("- CDC-") == 10
        assert "more" in reply.lower()
        _, kwargs = instance.search_issues.call_args
        assert kwargs["max_results"] == 10
