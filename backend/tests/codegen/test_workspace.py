"""
Unit tests for app/codegen/workspace.py: ticket_workspace()'s cleanup
contract (story 2.1, CDC-41, extending story 2.2's CDC-42 module), and the
worktree-listing/branch-deletion helpers added for the stale-worktree
sweep (story 2.8, CDC-52).

create_worktree()/remove_worktree() themselves shell out to git and are
exercised by the manual smoke test (scripts/codegen_smoke_test.py) against
a real clone; these tests patch git calls out (via _run_git/_canonical_clone_path)
to check parsing and orchestration logic in isolation.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.codegen.workspace import (
    TicketWorkspace,
    WorkspaceError,
    _branches_with_active_worktrees,
    _parse_worktree_entries,
    delete_ticket_branch,
    list_ticket_worktrees,
    ticket_workspace,
)

_WORKSPACE = TicketWorkspace(ticket_key="CDC-41", branch="feature/CDC-41-test", path=Path("/fake/path"))

_CLONE_PATH = Path("/repo/canonical")

_PORCELAIN_OUTPUT = (
    "worktree /repo/canonical\n"
    "HEAD abc123\n"
    "branch refs/heads/main\n"
    "\n"
    "worktree /repo/codegen-worktrees/CDC-41\n"
    "HEAD def456\n"
    "branch refs/heads/feature/CDC-41-add-retry-logic\n"
    "\n"
    "worktree /repo/codegen-worktrees/orphan\n"
    "HEAD ghi789\n"
    "detached\n"
)


def test_default_removes_worktree_on_success():
    with patch("app.codegen.workspace.create_worktree", return_value=_WORKSPACE) as mock_create, patch(
        "app.codegen.workspace.remove_worktree"
    ) as mock_remove:
        with ticket_workspace("CDC-41", "Some summary") as workspace:
            assert workspace is _WORKSPACE

    mock_create.assert_called_once_with("CDC-41", "Some summary")
    mock_remove.assert_called_once_with(_WORKSPACE)


def test_cleanup_on_success_false_keeps_worktree_after_success():
    with patch("app.codegen.workspace.create_worktree", return_value=_WORKSPACE), patch(
        "app.codegen.workspace.remove_worktree"
    ) as mock_remove:
        with ticket_workspace("CDC-41", "Some summary", cleanup_on_success=False) as workspace:
            assert workspace is _WORKSPACE

    mock_remove.assert_not_called()


def test_cleanup_on_success_false_still_removes_worktree_on_failure():
    with patch("app.codegen.workspace.create_worktree", return_value=_WORKSPACE), patch(
        "app.codegen.workspace.remove_worktree"
    ) as mock_remove:
        with pytest.raises(RuntimeError):
            with ticket_workspace("CDC-41", "Some summary", cleanup_on_success=False):
                raise RuntimeError("boom")

    mock_remove.assert_called_once_with(_WORKSPACE)


def test_default_still_removes_worktree_on_failure():
    with patch("app.codegen.workspace.create_worktree", return_value=_WORKSPACE), patch(
        "app.codegen.workspace.remove_worktree"
    ) as mock_remove:
        with pytest.raises(RuntimeError):
            with ticket_workspace("CDC-41", "Some summary"):
                raise RuntimeError("boom")

    mock_remove.assert_called_once_with(_WORKSPACE)


class TestParseWorktreeEntries:
    def test_parses_multiple_worktrees_with_branches(self):
        entries = _parse_worktree_entries(_PORCELAIN_OUTPUT)

        assert entries == [
            (Path("/repo/canonical"), "main"),
            (Path("/repo/codegen-worktrees/CDC-41"), "feature/CDC-41-add-retry-logic"),
            (Path("/repo/codegen-worktrees/orphan"), None),
        ]

    def test_empty_output_returns_no_entries(self):
        assert _parse_worktree_entries("") == []


class TestBranchesWithActiveWorktrees:
    def test_returns_branch_names_only_excluding_detached(self):
        with patch(
            "app.codegen.workspace._run_git",
            return_value=MagicMock(returncode=0, stdout=_PORCELAIN_OUTPUT, stderr=""),
        ):
            branches = _branches_with_active_worktrees(_CLONE_PATH)

        assert branches == {"main", "feature/CDC-41-add-retry-logic"}

    def test_git_failure_raises_workspace_error(self):
        with patch(
            "app.codegen.workspace._run_git", return_value=MagicMock(returncode=1, stdout="", stderr="boom")
        ):
            with pytest.raises(WorkspaceError):
                _branches_with_active_worktrees(_CLONE_PATH)


class TestListTicketWorktrees:
    def test_excludes_canonical_clone_and_detached_entries(self):
        with patch(
            "app.codegen.workspace._canonical_clone_path", return_value=_CLONE_PATH
        ), patch(
            "app.codegen.workspace._run_git",
            return_value=MagicMock(returncode=0, stdout=_PORCELAIN_OUTPUT, stderr=""),
        ):
            worktrees = list_ticket_worktrees()

        assert worktrees == [
            TicketWorkspace(
                ticket_key="CDC-41",
                branch="feature/CDC-41-add-retry-logic",
                path=Path("/repo/codegen-worktrees/CDC-41"),
            )
        ]

    def test_no_ticket_worktrees_returns_empty_list(self):
        output = "worktree /repo/canonical\nHEAD abc123\nbranch refs/heads/main\n"
        with patch("app.codegen.workspace._canonical_clone_path", return_value=_CLONE_PATH), patch(
            "app.codegen.workspace._run_git", return_value=MagicMock(returncode=0, stdout=output, stderr="")
        ):
            assert list_ticket_worktrees() == []

    def test_git_worktree_list_failure_raises_workspace_error(self):
        with patch("app.codegen.workspace._canonical_clone_path", return_value=_CLONE_PATH), patch(
            "app.codegen.workspace._run_git", return_value=MagicMock(returncode=1, stdout="", stderr="boom")
        ):
            with pytest.raises(WorkspaceError):
                list_ticket_worktrees()


class TestDeleteTicketBranch:
    def test_deletes_branch_via_git_branch_dash_capital_d(self):
        with patch("app.codegen.workspace._canonical_clone_path", return_value=_CLONE_PATH), patch(
            "app.codegen.workspace._run_git", return_value=MagicMock(returncode=0, stdout="", stderr="")
        ) as mock_run_git:
            delete_ticket_branch(_WORKSPACE)

        mock_run_git.assert_called_once_with(["branch", "-D", _WORKSPACE.branch], cwd=_CLONE_PATH)

    def test_failure_raises_workspace_error(self):
        with patch("app.codegen.workspace._canonical_clone_path", return_value=_CLONE_PATH), patch(
            "app.codegen.workspace._run_git", return_value=MagicMock(returncode=1, stdout="", stderr="boom")
        ):
            with pytest.raises(WorkspaceError):
                delete_ticket_branch(_WORKSPACE)
