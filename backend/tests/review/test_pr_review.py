"""
Unit tests for app/review/pr_review.py (story 4.2, CDC-31).

GitHubClient and chat_completion are both mocked wholesale - no real HTTP
call and no real LLM call. Coverage focuses on the ticket's core
requirement: malformed/unparseable model output must raise
ReviewParsingError, never silently default to a passing "approve" review.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from app.review.pr_review import ReviewParsingError, ReviewResult, review_pull_request

FILES_PAYLOAD = [
    {"filename": "app/foo.py", "status": "modified", "patch": "@@ -1,2 +1,3 @@\n+added line"},
    {"filename": "app/bar.png", "status": "modified"},
]

VALID_PAYLOAD = {
    "verdict": "request_changes",
    "risk_score": 0.7,
    "flagged_files": ["app/foo.py"],
    "file_comments": [{"file": "app/foo.py", "line": 10, "body": "Possible off-by-one error."}],
    "summary": "The change introduces a possible off-by-one bug.",
}


def _mock_github_client(files=FILES_PAYLOAD):
    mock_cls = MagicMock()
    instance = mock_cls.return_value.__enter__.return_value
    instance.get_pull_request_files.return_value = files
    return mock_cls, instance


class TestReviewPullRequest:
    def test_parses_valid_json_response_into_review_result(self):
        mock_cls, instance = _mock_github_client()
        with patch("app.review.pr_review.GitHubClient", mock_cls), patch(
            "app.review.pr_review.chat_completion", return_value=json.dumps(VALID_PAYLOAD)
        ) as mock_chat:
            result = review_pull_request(7)

        assert isinstance(result, ReviewResult)
        assert result.verdict == "request_changes"
        assert result.risk_score == 0.7
        assert result.flagged_files == ["app/foo.py"]
        assert result.file_comments[0].file == "app/foo.py"
        assert result.file_comments[0].line == 10
        assert result.summary == "The change introduces a possible off-by-one bug."

        instance.get_pull_request_files.assert_called_once_with(7)
        _, kwargs = mock_chat.call_args
        assert "app/foo.py" in kwargs["user_message"]
        assert "added line" in kwargs["user_message"]

    def test_binary_file_without_patch_gets_placeholder_note(self):
        mock_cls, instance = _mock_github_client()
        with patch("app.review.pr_review.GitHubClient", mock_cls), patch(
            "app.review.pr_review.chat_completion", return_value=json.dumps(VALID_PAYLOAD)
        ) as mock_chat:
            review_pull_request(7)

        _, kwargs = mock_chat.call_args
        assert "app/bar.png" in kwargs["user_message"]
        assert "no diff available" in kwargs["user_message"]

    def test_malformed_json_raises_parsing_error_not_default_approve(self):
        mock_cls, _ = _mock_github_client()
        with patch("app.review.pr_review.GitHubClient", mock_cls), patch(
            "app.review.pr_review.chat_completion", return_value="not json at all"
        ):
            with pytest.raises(ReviewParsingError):
                review_pull_request(7)

    def test_missing_required_field_raises_parsing_error(self):
        payload = dict(VALID_PAYLOAD)
        del payload["verdict"]
        mock_cls, _ = _mock_github_client()
        with patch("app.review.pr_review.GitHubClient", mock_cls), patch(
            "app.review.pr_review.chat_completion", return_value=json.dumps(payload)
        ):
            with pytest.raises(ReviewParsingError):
                review_pull_request(7)

    def test_invalid_verdict_value_raises_parsing_error(self):
        payload = dict(VALID_PAYLOAD, verdict="maybe")
        mock_cls, _ = _mock_github_client()
        with patch("app.review.pr_review.GitHubClient", mock_cls), patch(
            "app.review.pr_review.chat_completion", return_value=json.dumps(payload)
        ):
            with pytest.raises(ReviewParsingError):
                review_pull_request(7)

    def test_risk_score_out_of_range_raises_parsing_error(self):
        payload = dict(VALID_PAYLOAD, risk_score=1.5)
        mock_cls, _ = _mock_github_client()
        with patch("app.review.pr_review.GitHubClient", mock_cls), patch(
            "app.review.pr_review.chat_completion", return_value=json.dumps(payload)
        ):
            with pytest.raises(ReviewParsingError):
                review_pull_request(7)

    def test_response_wrapped_in_markdown_fence_is_still_parsed(self):
        fenced = f"```json\n{json.dumps(VALID_PAYLOAD)}\n```"
        mock_cls, _ = _mock_github_client()
        with patch("app.review.pr_review.GitHubClient", mock_cls), patch(
            "app.review.pr_review.chat_completion", return_value=fenced
        ):
            result = review_pull_request(7)

        assert result.verdict == "request_changes"

    def test_uses_strong_model(self):
        mock_cls, _ = _mock_github_client()
        with patch("app.review.pr_review.GitHubClient", mock_cls), patch(
            "app.review.pr_review.chat_completion", return_value=json.dumps(VALID_PAYLOAD)
        ) as mock_chat:
            review_pull_request(7)

        from app.config import get_settings

        _, kwargs = mock_chat.call_args
        assert kwargs["model"] == get_settings().strong_model
