"""
LLM provider switch. Callers use chat_completion() regardless of whether
LLM_PROVIDER is "anthropic" or "ollama" - this is the one place that
branches on provider.
"""

import logging

from app.config import get_settings

logger = logging.getLogger("codecrew.llm_client")


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
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user_message}],
    )
    return response.content[0].text.strip()
