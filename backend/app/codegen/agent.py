"""
Headless Claude Agent SDK invocation, scoped to a codegen worktree
(story 2.2, CDC-42).

Epic 2's architecture decision: codegen goes through the Claude Agent SDK
in headless mode (not a single raw Anthropic Messages API call), since it
needs to explore the real repo - read existing files, follow conventions -
before writing any new code. This module proves that invocation works
end-to-end within a ticket's worktree; the actual "generate a diff for
this ticket" behavior is story 2.1 (CDC-41), built on top of this.

Story 2.7 (CDC-50): prefer CLAUDE_CODE_OAUTH_TOKEN over ANTHROPIC_API_KEY
when present, so individual development bills against a Claude
subscription's Agent SDK credit instead of pay-as-you-go API credit. The
Agent SDK's underlying CLI subprocess reads credentials straight from its
own environment, and an inherited ANTHROPIC_API_KEY silently wins over an
OAuth token passed via ClaudeAgentOptions.env (env is merged on top of the
inherited environment, not a full replacement) - so when the OAuth token
is used, ANTHROPIC_API_KEY must actually be removed from the environment
the subprocess inherits, not just outranked.
"""

import logging
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, ResultMessage, TextBlock, query

from app.config import get_settings

logger = logging.getLogger("codecrew.codegen_agent")

_credential_path_logged = False


@contextmanager
def _credential_env() -> Iterator[None]:
    """
    Set up the process environment the Agent SDK subprocess will inherit:
    CLAUDE_CODE_OAUTH_TOKEN if configured (with ANTHROPIC_API_KEY removed
    so it can't silently win), otherwise ANTHROPIC_API_KEY as before.
    Restores the prior environment afterward.
    """
    global _credential_path_logged

    settings = get_settings()
    original_oauth_token = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")
    original_api_key = os.environ.get("ANTHROPIC_API_KEY")

    if settings.claude_code_oauth_token:
        os.environ["CLAUDE_CODE_OAUTH_TOKEN"] = settings.claude_code_oauth_token
        os.environ.pop("ANTHROPIC_API_KEY", None)
        credential_path = "oauth_token"
    else:
        os.environ.pop("CLAUDE_CODE_OAUTH_TOKEN", None)
        os.environ["ANTHROPIC_API_KEY"] = settings.anthropic_api_key
        credential_path = "api_key"

    if not _credential_path_logged:
        logger.info("Codegen agent credential path: %s", credential_path, extra={"credential_path": credential_path})
        _credential_path_logged = True

    try:
        yield
    finally:
        if original_oauth_token is not None:
            os.environ["CLAUDE_CODE_OAUTH_TOKEN"] = original_oauth_token
        else:
            os.environ.pop("CLAUDE_CODE_OAUTH_TOKEN", None)
        if original_api_key is not None:
            os.environ["ANTHROPIC_API_KEY"] = original_api_key
        else:
            os.environ.pop("ANTHROPIC_API_KEY", None)


async def run_headless(cwd: Path, prompt: str) -> str:
    """
    Run a single headless Claude Agent SDK query scoped to `cwd`, and
    return the assistant's concatenated final text.
    """
    options = ClaudeAgentOptions(
        cwd=str(cwd),
        permission_mode="acceptEdits",
        tools={"type": "preset", "preset": "claude_code"},
    )

    text_parts: list[str] = []
    with _credential_env():
        async for message in query(prompt=prompt, options=options):
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        text_parts.append(block.text)
            elif isinstance(message, ResultMessage):
                logger.info("Codegen agent run finished", extra={"subtype": message.subtype})

    return "".join(text_parts)
