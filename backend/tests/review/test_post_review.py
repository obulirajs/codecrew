"""
Unit tests for app/review/post_review.py (story 4.1, CDC-30).

review_pull_request() and GitHubClient are both mocked wholesale - no real
LLM call, no real HTTP call, no real GitHub review ever posted.
"""

from unittest.mock import MagicMock, patch

from app.review.post_review import PostedReview, post_pr_review
from app.review.pr_review import FileComment, ReviewResult

PR_PAYLOAD = {"number": 7, "html_url": "https://github.com/o/r/pull/7"}

_APPROVE_RESULT = ReviewResult(
    verdict="approve",
    risk_score=0.1,
    flagged_files=[],
    file_comments=[],
    summary="Looks good.",
)

_REQUEST_CHANGES_RESULT = ReviewResult(
    verdict="request_changes",
    risk_score=0.8,
    flagged_files=["app/foo.py"],
    file_comments=[FileComment(file="app/foo.py", line=10, body="Possible off-by-one error.")],
    summary="Found a likely bug.",
)


def _mock_github_client():
    mock_cls = MagicMock()
    instance = mock_cls.return_value.__enter__.return_value
    instance.get_pull_request.return_value = PR_PAYLOAD
    return mock_cls, instance


class TestPostPrReview:
    def test_approve_verdict_maps_to_comment_event(self):
        mock_cls, instance = _mock_github_client()
        with patch("app.review.post_review.GitHubClient", mock_cls), patch(
            "app.review.post_review.review_pull_request", return_value=_APPROVE_RESULT
        ):
            result = post_pr_review(7)

        assert isinstance(result, PostedReview)
        assert result.verdict == "approve"
        assert result.risk_score == 0.1
        assert result.url == "https://github.com/o/r/pull/7"

        _, kwargs = instance.create_pull_request_review.call_args
        assert kwargs["event"] == "COMMENT"
        assert kwargs["comments"] == []

    def test_request_changes_verdict_also_maps_to_comment_event(self):
        """GitHub blocks both APPROVE and REQUEST_CHANGES from a PR's own author - only COMMENT succeeds."""
        mock_cls, instance = _mock_github_client()
        with patch("app.review.post_review.GitHubClient", mock_cls), patch(
            "app.review.post_review.review_pull_request", return_value=_REQUEST_CHANGES_RESULT
        ):
            result = post_pr_review(7)

        assert result.verdict == "request_changes"
        assert result.risk_score == 0.8

        _, kwargs = instance.create_pull_request_review.call_args
        assert kwargs["event"] == "COMMENT"
        assert kwargs["comments"] == [{"path": "app/foo.py", "line": 10, "body": "Possible off-by-one error."}]

    def test_approve_verdict_body_states_recommended_approve(self):
        mock_cls, instance = _mock_github_client()
        with patch("app.review.post_review.GitHubClient", mock_cls), patch(
            "app.review.post_review.review_pull_request", return_value=_APPROVE_RESULT
        ):
            post_pr_review(7)

        _, kwargs = instance.create_pull_request_review.call_args
        body = kwargs["body"]
        assert "Recommended: Approve" in body
        assert "0.1" in body
        assert "none" in body
        assert "Looks good." in body

    def test_request_changes_verdict_body_states_recommended_request_changes_risk_and_flagged_files(self):
        mock_cls, instance = _mock_github_client()
        with patch("app.review.post_review.GitHubClient", mock_cls), patch(
            "app.review.post_review.review_pull_request", return_value=_REQUEST_CHANGES_RESULT
        ):
            post_pr_review(7)

        _, kwargs = instance.create_pull_request_review.call_args
        body = kwargs["body"]
        assert "Recommended: Request Changes" in body
        assert "0.8" in body
        assert "app/foo.py" in body
        assert "Found a likely bug." in body
        assert "Possible off-by-one error." in body

    def test_returns_pr_url_from_get_pull_request(self):
        mock_cls, instance = _mock_github_client()
        with patch("app.review.post_review.GitHubClient", mock_cls), patch(
            "app.review.post_review.review_pull_request", return_value=_APPROVE_RESULT
        ):
            result = post_pr_review(7)

        instance.get_pull_request.assert_called_once_with(7)
        assert result.url == PR_PAYLOAD["html_url"]
