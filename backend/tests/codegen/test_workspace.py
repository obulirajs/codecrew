"""
Unit tests for app/codegen/workspace.py's ticket_workspace() cleanup
contract (story 2.1, CDC-41, extending story 2.2's CDC-42 module).

create_worktree()/remove_worktree() themselves shell out to git and are
exercised by the manual smoke test (scripts/codegen_smoke_test.py) against
a real clone; these tests patch both out to check only the
cleanup-on-success vs. cleanup-on-failure contract of the context manager.
"""

from pathlib import Path
from unittest.mock import patch

import pytest

from app.codegen.workspace import TicketWorkspace, ticket_workspace

_WORKSPACE = TicketWorkspace(ticket_key="CDC-41", branch="feature/CDC-41-test", path=Path("/fake/path"))


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
