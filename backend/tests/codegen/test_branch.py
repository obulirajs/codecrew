"""
Unit tests for app/codegen/branch.py (story 3.5, CDC-27).

GitHubClient is mocked wholesale for create_ad_hoc_branch() - no real HTTP
call. sanitize_branch_name() is a pure function, tested directly.
"""

from unittest.mock import MagicMock, patch

import pytest

from app.clients.github_client import GitHubValidationError
from app.codegen.branch import (
    BranchAlreadyExistsError,
    BranchResult,
    InvalidBranchNameError,
    create_ad_hoc_branch,
    sanitize_branch_name,
)


class TestSanitizeBranchName:
    def test_lowercases(self):
        assert sanitize_branch_name("MyBranch") == "mybranch"

    def test_replaces_whitespace_with_dash(self):
        assert sanitize_branch_name("my new branch") == "my-new-branch"

    def test_replaces_invalid_git_ref_characters_with_dash(self):
        assert sanitize_branch_name("feat~^:?*[branch") == "feat-branch"

    def test_collapses_repeated_dashes(self):
        assert sanitize_branch_name("a---b  c") == "a-b-c"

    def test_strips_leading_and_trailing_dashes_and_dots(self):
        assert sanitize_branch_name("-.foo.-") == "foo"

    def test_allows_dots_and_underscores_in_the_middle(self):
        assert sanitize_branch_name("release_1.2.3") == "release_1.2.3"

    def test_empty_after_sanitization_raises(self):
        with pytest.raises(InvalidBranchNameError):
            sanitize_branch_name("~^:?*[")

    def test_all_whitespace_raises(self):
        with pytest.raises(InvalidBranchNameError):
            sanitize_branch_name("   ")


def _mock_github_client():
    mock_cls = MagicMock()
    instance = mock_cls.return_value.__enter__.return_value
    instance.owner = "o"
    instance.repo = "r"
    instance.get_repository.return_value = {"default_branch": "main"}
    instance.get_git_ref.return_value = {"object": {"sha": "abc123"}}
    instance.create_git_ref.return_value = {"ref": "refs/heads/my-branch"}
    return mock_cls, instance


class TestCreateAdHocBranch:
    def test_creates_branch_from_default_branch_head_and_returns_result(self):
        mock_cls, instance = _mock_github_client()
        with patch("app.codegen.branch.GitHubClient", mock_cls):
            result = create_ad_hoc_branch("My Branch")

        assert isinstance(result, BranchResult)
        assert result.name == "my-branch"
        assert result.url == "https://github.com/o/r/tree/my-branch"

        instance.get_repository.assert_called_once()
        instance.get_git_ref.assert_called_once_with("heads/main")
        _, kwargs = instance.create_git_ref.call_args
        assert kwargs == {"ref": "refs/heads/my-branch", "sha": "abc123"}

    def test_uses_real_default_branch_not_hardcoded_main(self):
        mock_cls, instance = _mock_github_client()
        instance.get_repository.return_value = {"default_branch": "develop"}
        with patch("app.codegen.branch.GitHubClient", mock_cls):
            create_ad_hoc_branch("my-branch")

        instance.get_git_ref.assert_called_once_with("heads/develop")

    def test_existing_branch_raises_clear_specific_error_not_generic_crash(self):
        mock_cls, instance = _mock_github_client()
        instance.create_git_ref.side_effect = GitHubValidationError("Reference already exists")
        with patch("app.codegen.branch.GitHubClient", mock_cls):
            with pytest.raises(BranchAlreadyExistsError, match="my-branch"):
                create_ad_hoc_branch("my-branch")

    def test_invalid_name_never_reaches_github(self):
        mock_cls, instance = _mock_github_client()
        with patch("app.codegen.branch.GitHubClient", mock_cls):
            with pytest.raises(InvalidBranchNameError):
                create_ad_hoc_branch("~^:?*[")

        instance.create_git_ref.assert_not_called()
