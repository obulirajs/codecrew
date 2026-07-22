"""
Unit tests for app/llm_client.py's chat_completion() (bug CDC-53).

The Anthropic client is mocked wholesale - no real API call. Coverage
focuses on the bug: chat_completion() must locate the actual text content
block by type rather than blindly indexing content[0], since an extended
thinking block (or any other non-text block) can precede it.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.llm_client import LLMResponseError, chat_completion

_USAGE = SimpleNamespace(
    cache_creation_input_tokens=0, cache_read_input_tokens=0, input_tokens=10, output_tokens=20
)


def _mock_anthropic_response(content):
    return SimpleNamespace(content=content, usage=_USAGE)


def _patch_anthropic(response):
    mock_cls = MagicMock()
    mock_cls.return_value.messages.create.return_value = response
    return patch("anthropic.Anthropic", mock_cls)


def test_extracts_text_block_when_it_is_the_only_block():
    response = _mock_anthropic_response([SimpleNamespace(type="text", text="  hello  ")])
    with _patch_anthropic(response):
        result = chat_completion(model="m", system="s", user_message="u")

    assert result == "hello"


def test_extracts_text_block_when_preceded_by_a_thinking_block():
    """
    CDC-53: a ThinkingBlock has no .text attribute - if chat_completion()
    ever indexes content[0] directly again, this test fails with an
    AttributeError instead of silently passing.
    """
    thinking_block = SimpleNamespace(type="thinking")  # no .text - matches the real ThinkingBlock shape
    text_block = SimpleNamespace(type="text", text="the actual answer")
    response = _mock_anthropic_response([thinking_block, text_block])

    with _patch_anthropic(response):
        result = chat_completion(model="m", system="s", user_message="u")

    assert result == "the actual answer"


def test_raises_specific_error_when_no_text_block_present():
    response = _mock_anthropic_response([SimpleNamespace(type="thinking")])
    with _patch_anthropic(response):
        with pytest.raises(LLMResponseError):
            chat_completion(model="m", system="s", user_message="u")


def test_raises_specific_error_on_empty_content():
    response = _mock_anthropic_response([])
    with _patch_anthropic(response):
        with pytest.raises(LLMResponseError):
            chat_completion(model="m", system="s", user_message="u")
