"""
LLM provider switch. Callers use chat_completion() regardless of whether
LLM_PROVIDER is "anthropic" or "ollama" - this is the one place that
branches on provider.
"""

import logging

from app.config import get_settings

logger = logging.getLogger("codecrew.llm_client")


class LLMResponseError(Exception):
    """Raised when an Anthropic response contains no text content block - e.g. only extended-thinking or tool-use blocks - rather than an unrelated AttributeError from blindly indexing content[0]."""


def _extract_text(content) -> str:
    """
    Find the actual text block by checking each block's type, instead of
    assuming content[0] is always text - extended thinking (or any other
    non-text block) can precede it (CDC-53).
    """
    for block in content:
        if getattr(block, "type", None) == "text":
            return block.text.strip()
    raise LLMResponseError("Anthropic response contained no text content block.")


def chat_completion(model: str, system: str, user_message: str, max_tokens: int = 512) -> str:
    settings = get_settings()

    if settings.llm_provider == "ollama":
        import ollama
        client = ollama.Client(host=settings.ollama_base_url)
        response = client.chat(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_message},
            ],
        )
        return response["message"]["content"].strip()

    from anthropic import Anthropic
    client = Anthropic(api_key=settings.anthropic_api_key)

    if len(system) > 500:
        system_param = [
            {
                "type": "text",
                "text": system,
                "cache_control": {"type": "ephemeral"}
            }
        ]
    else:
        system_param = system

    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system_param,
        messages=[{"role": "user", "content": user_message}],
    )

    logger.debug(
        "LLM call usage",
        extra={
            "cache_creation_input_tokens": getattr(response.usage, "cache_creation_input_tokens", None),
            "cache_read_input_tokens": getattr(response.usage, "cache_read_input_tokens", None),
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
        },
    )

    return _extract_text(response.content)
