"""
Unit tests for app/codegen/commit.py (story 3.2, CDC-24).

find_ticket_worktree() and git itself are both mocked out - these tests
cover the precondition-refusal contract (needs_clarification, lint_errors,
empty files_changed must never reach `git commit`) and the git add/commit
orchestration, not a real worktree or a real commit.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.codegen.commit import CommitError, commit_generated_code
from app.codegen.diff import CodegenResult
from app.codegen.workspace import TicketWorkspace
from app.config import get_settings

_WORKSPACE = TicketWorkspace(
    ticket_key="CDC-41", branch="feature/CDC-41-add-retry-logic", path=Path("/fake/worktree")
)


def _result(**overrides) -> CodegenResult:
    defaults = dict(
        diff_text="diff --git a/foo.py b/foo.py\n+added line\n",
        summary="Added retry logic to the client.",
        files_changed=["foo.py"],
        needs_clarification=False,
        clarifying_questions=[],
        lint_errors=[],
    )
    defaults.update(overrides)
    return CodegenResult(**defaults)


def _completed(returncode=0, stdout="", stderr=""):
    return MagicMock(returncode=returncode, stdout=stdout, stderr=stderr)


class TestPreconditions:
    def test_needs_clarification_refuses_without_touching_git(self):
        with patch("app.codegen.commit.find_ticket_worktree") as mock_find, patch(
            "app.codegen.commit.subprocess.run"
        ) as mock_run:
            with pytest.raises(CommitError, match="needs clarification"):
                commit_generated_code("CDC-41", _result(needs_clarification=True, files_changed=[], diff_text=""))

        mock_find.assert_not_called()
        mock_run.assert_not_called()

    def test_lint_errors_refuses_without_touching_git(self):
        with patch("app.codegen.commit.find_ticket_worktree") as mock_find, patch(
            "app.codegen.commit.subprocess.run"
        ) as mock_run:
            with pytest.raises(CommitError, match="lint error"):
                commit_generated_code("CDC-41", _result(lint_errors=["foo.py:3:5: F821 Undefined name `bar`"]))

        mock_find.assert_not_called()
        mock_run.assert_not_called()

    def test_empty_files_changed_refuses_without_touching_git(self):
        with patch("app.codegen.commit.find_ticket_worktree") as mock_find, patch(
            "app.codegen.commit.subprocess.run"
        ) as mock_run:
            with pytest.raises(CommitError, match="no files_changed"):
                commit_generated_code("CDC-41", _result(files_changed=[]))

        mock_find.assert_not_called()
        mock_run.assert_not_called()


class TestCommitGeneratedCode:
    def test_stages_exactly_files_changed_and_commits_with_ticket_message(self):
        settings = get_settings()
        result = _result(files_changed=["foo.py", "bar.py"])

        with patch("app.codegen.commit.find_ticket_worktree", return_value=_WORKSPACE), patch(
            "app.codegen.commit.subprocess.run",
            side_effect=[
                _completed(),  # git add
                _completed(),  # git commit
                _completed(stdout="abc123deadbeef\n"),  # git rev-parse HEAD
            ],
        ) as mock_run:
            sha = commit_generated_code("CDC-41", result)

        assert sha == "abc123deadbeef"
        assert mock_run.call_count == 3

        add_call = mock_run.call_args_list[0]
        assert add_call.args[0] == ["git", "add", "--", "foo.py", "bar.py"]
        assert add_call.kwargs["cwd"] == _WORKSPACE.path

        commit_call = mock_run.call_args_list[1]
        assert commit_call.args[0] == [
            "git",
            "-c", f"user.name={settings.git_commit_author_name}",
            "-c", f"user.email={settings.git_commit_author_email}",
            "commit", "-m", f"CDC-41 {result.summary}",
        ]
        assert commit_call.kwargs["cwd"] == _WORKSPACE.path

        rev_parse_call = mock_run.call_args_list[2]
        assert rev_parse_call.args[0] == ["git", "rev-parse", "HEAD"]

    def test_git_add_failure_raises_commit_error(self):
        with patch("app.codegen.commit.find_ticket_worktree", return_value=_WORKSPACE), patch(
            "app.codegen.commit.subprocess.run", return_value=_completed(returncode=1, stderr="boom")
        ):
            with pytest.raises(CommitError):
                commit_generated_code("CDC-41", _result())

    def test_git_commit_failure_raises_commit_error(self):
        with patch("app.codegen.commit.find_ticket_worktree", return_value=_WORKSPACE), patch(
            "app.codegen.commit.subprocess.run",
            side_effect=[_completed(), _completed(returncode=1, stderr="nothing to commit")],
        ):
            with pytest.raises(CommitError):
                commit_generated_code("CDC-41", _result())

    def test_git_rev_parse_failure_raises_commit_error(self):
        with patch("app.codegen.commit.find_ticket_worktree", return_value=_WORKSPACE), patch(
            "app.codegen.commit.subprocess.run",
            side_effect=[_completed(), _completed(), _completed(returncode=1, stderr="boom")],
        ):
            with pytest.raises(CommitError):
                commit_generated_code("CDC-41", _result())

    def test_worktree_not_found_propagates(self):
        from app.codegen.workspace import WorktreeNotFoundError

        with patch(
            "app.codegen.commit.find_ticket_worktree", side_effect=WorktreeNotFoundError("no worktree")
        ):
            with pytest.raises(WorktreeNotFoundError):
                commit_generated_code("CDC-41", _result())
