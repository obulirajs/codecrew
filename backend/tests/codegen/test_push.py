"""
Unit tests for app/codegen/push.py (story 3.1, CDC-23).

find_ticket_worktree() and git itself are both mocked out - these tests
cover URL construction/token redaction, rejection-vs-transient
classification, and the retry-once contract, not a real push.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.codegen.push import PushError, _redact, push_ticket_branch
from app.codegen.workspace import TicketWorkspace, WorktreeNotFoundError
from app.config import get_settings

_WORKSPACE = TicketWorkspace(
    ticket_key="CDC-41", branch="feature/CDC-41-add-retry-logic", path=Path("/fake/worktree")
)


def _completed(returncode=0, stdout="", stderr=""):
    return MagicMock(returncode=returncode, stdout=stdout, stderr=stderr)


class TestRedact:
    def test_removes_token_from_text(self):
        assert _redact("https://x-access-token:secret123@github.com/o/r.git", "secret123") == (
            "https://x-access-token:***@github.com/o/r.git"
        )

    def test_empty_token_returns_text_unchanged(self):
        assert _redact("some text", "") == "some text"


class TestPushTicketBranch:
    def test_success_pushes_expected_url_and_refspec(self):
        settings = get_settings()
        with patch("app.codegen.push.find_ticket_worktree", return_value=_WORKSPACE), patch(
            "app.codegen.push.subprocess.run", return_value=_completed()
        ) as mock_run:
            push_ticket_branch("CDC-41")

        mock_run.assert_called_once()
        args, kwargs = mock_run.call_args
        assert args[0][:2] == ["git", "push"]
        assert args[0][2] == (
            f"https://x-access-token:{settings.github_token}@github.com/"
            f"{settings.github_owner}/{settings.github_repo}.git"
        )
        assert args[0][3] == f"{_WORKSPACE.branch}:{_WORKSPACE.branch}"
        assert kwargs["cwd"] == _WORKSPACE.path

    def test_token_never_appears_in_raised_error_message(self):
        settings = get_settings()
        stderr = (
            f"fatal: unable to access "
            f"'https://x-access-token:{settings.github_token}@github.com/o/r.git/': "
            f"Could not resolve host"
        )
        with patch("app.codegen.push.find_ticket_worktree", return_value=_WORKSPACE), patch(
            "app.codegen.push.subprocess.run",
            return_value=_completed(returncode=128, stderr=stderr),
        ):
            with pytest.raises(PushError) as exc_info:
                push_ticket_branch("CDC-41")

        assert settings.github_token not in str(exc_info.value)

    def test_rejected_push_raises_immediately_without_retry_or_force(self):
        stderr = "! [rejected]        feature/CDC-41-x -> feature/CDC-41-x (non-fast-forward)"
        with patch("app.codegen.push.find_ticket_worktree", return_value=_WORKSPACE), patch(
            "app.codegen.push.subprocess.run", return_value=_completed(returncode=1, stderr=stderr)
        ) as mock_run:
            with pytest.raises(PushError, match="not force-pushing"):
                push_ticket_branch("CDC-41")

        mock_run.assert_called_once()
        for call in mock_run.call_args_list:
            assert "--force" not in call.args[0]
            assert "-f" not in call.args[0]

    def test_transient_failure_retries_once_then_succeeds(self):
        with patch("app.codegen.push.find_ticket_worktree", return_value=_WORKSPACE), patch(
            "app.codegen.push.subprocess.run",
            side_effect=[
                _completed(returncode=1, stderr="fatal: Could not resolve host: github.com"),
                _completed(returncode=0),
            ],
        ) as mock_run:
            push_ticket_branch("CDC-41")

        assert mock_run.call_count == 2

    def test_transient_failure_gives_up_after_one_retry(self):
        with patch("app.codegen.push.find_ticket_worktree", return_value=_WORKSPACE), patch(
            "app.codegen.push.subprocess.run",
            return_value=_completed(returncode=1, stderr="fatal: Could not resolve host: github.com"),
        ) as mock_run:
            with pytest.raises(PushError, match="after retry"):
                push_ticket_branch("CDC-41")

        assert mock_run.call_count == 2

    def test_worktree_not_found_propagates(self):
        with patch(
            "app.codegen.push.find_ticket_worktree", side_effect=WorktreeNotFoundError("no worktree")
        ):
            with pytest.raises(WorktreeNotFoundError):
                push_ticket_branch("CDC-41")
