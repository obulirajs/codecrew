"""
Unit tests for app/codegen/diff.py (story 2.1, CDC-41).

Both the Agent SDK call (run_headless) and git itself are mocked out -
these tests cover prompt content, diff-capture parsing, and orchestration,
not a real agent run or a real repo.
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.clients.jira_ticket_spec import TicketSpec
from app.codegen.diff import CodegenError, CodegenResult, _build_prompt, _capture_diff, generate_diff
from app.codegen.workspace import TicketWorkspace

_SPEC = TicketSpec(
    summary="Add retry logic",
    acceptance_criteria=["Retries once on timeout", "Logs a warning on retry"],
    ticket_type="Story",
    labels=["backend"],
)

_WORKSPACE = TicketWorkspace(
    ticket_key="CDC-41", branch="feature/CDC-41-add-retry-logic", path=Path("/fake/worktree")
)


def _completed(stdout="", returncode=0, stderr=""):
    return MagicMock(returncode=returncode, stdout=stdout, stderr=stderr)


class TestBuildPrompt:
    def test_includes_ticket_key_and_spec_fields(self):
        prompt = _build_prompt("CDC-41", _SPEC)

        assert "CDC-41" in prompt
        assert "Add retry logic" in prompt
        assert "Story" in prompt
        assert "backend" in prompt
        assert "Retries once on timeout" in prompt
        assert "Logs a warning on retry" in prompt

    def test_instructs_agent_to_edit_files_not_print_a_diff(self):
        prompt = _build_prompt("CDC-41", _SPEC).lower()

        assert "do not just describe or print a diff" in prompt

    def test_instructs_agent_not_to_commit_push_or_open_a_pr(self):
        prompt = _build_prompt("CDC-41", _SPEC)

        assert "git commit" in prompt
        assert "git push" in prompt
        assert "pull request" in prompt

    def test_handles_empty_acceptance_criteria_and_labels(self):
        spec = TicketSpec(summary="Bare ticket", acceptance_criteria=[], ticket_type="Bug", labels=[])
        prompt = _build_prompt("CDC-99", spec)

        assert "(none provided)" in prompt
        assert "(none)" in prompt


class TestCaptureDiff:
    def test_stages_and_returns_diff_and_changed_files(self):
        diff_output = "diff --git a/foo.py b/foo.py\n+added line\n"
        names_output = "foo.py\nbar.py\n"

        with patch(
            "app.codegen.diff.subprocess.run",
            side_effect=[_completed(), _completed(stdout=diff_output), _completed(stdout=names_output)],
        ) as mock_run:
            diff_text, files_changed = _capture_diff(_WORKSPACE)

        assert diff_text == diff_output
        assert files_changed == ["foo.py", "bar.py"]
        assert mock_run.call_count == 3

        add_call = mock_run.call_args_list[0]
        assert add_call.args[0] == ["git", "add", "-A"]
        assert add_call.kwargs["cwd"] == _WORKSPACE.path

    def test_git_add_failure_raises_codegen_error(self):
        with patch("app.codegen.diff.subprocess.run", return_value=_completed(returncode=1, stderr="boom")):
            with pytest.raises(CodegenError):
                _capture_diff(_WORKSPACE)

    def test_git_diff_failure_raises_codegen_error(self):
        with patch(
            "app.codegen.diff.subprocess.run",
            side_effect=[_completed(), _completed(returncode=1, stderr="boom")],
        ):
            with pytest.raises(CodegenError):
                _capture_diff(_WORKSPACE)

    def test_no_changes_returns_empty_diff_and_no_files(self):
        with patch(
            "app.codegen.diff.subprocess.run",
            side_effect=[_completed(), _completed(stdout=""), _completed(stdout="")],
        ):
            diff_text, files_changed = _capture_diff(_WORKSPACE)

        assert diff_text == ""
        assert files_changed == []


class TestGenerateDiff:
    @pytest.mark.asyncio
    async def test_runs_agent_in_worktree_and_returns_structured_result(self):
        with patch("app.codegen.diff.ticket_workspace") as mock_ticket_workspace, patch(
            "app.codegen.diff.run_headless", new_callable=AsyncMock
        ) as mock_run_headless, patch(
            "app.codegen.diff._capture_diff", return_value=("diff text", ["foo.py"])
        ) as mock_capture:
            mock_ticket_workspace.return_value.__enter__.return_value = _WORKSPACE
            mock_ticket_workspace.return_value.__exit__.return_value = False
            mock_run_headless.return_value = "Added retry logic to the client."

            result = await generate_diff("CDC-41", _SPEC)

        assert isinstance(result, CodegenResult)
        assert result.diff_text == "diff text"
        assert result.files_changed == ["foo.py"]
        assert result.summary == "Added retry logic to the client."

        mock_ticket_workspace.assert_called_once_with("CDC-41", _SPEC.summary, cleanup_on_success=False)
        assert mock_run_headless.call_args.args[0] == _WORKSPACE.path
        mock_capture.assert_called_once_with(_WORKSPACE)

    @pytest.mark.asyncio
    async def test_agent_failure_propagates(self):
        with patch("app.codegen.diff.ticket_workspace") as mock_ticket_workspace, patch(
            "app.codegen.diff.run_headless", new_callable=AsyncMock
        ) as mock_run_headless:
            mock_ticket_workspace.return_value.__enter__.return_value = _WORKSPACE
            mock_ticket_workspace.return_value.__exit__.return_value = False
            mock_run_headless.side_effect = RuntimeError("agent crashed")

            with pytest.raises(RuntimeError):
                await generate_diff("CDC-41", _SPEC)
