"""
Headless Claude Agent SDK invocation, scoped to a codegen worktree
(story 2.2, CDC-42).

Epic 2's architecture decision: codegen goes through the Claude Agent SDK
in headless mode (not a single raw Anthropic Messages API call), since it
needs to explore the real repo - read existing files, follow conventions -
before writing any new code. This module proves that invocation works
end-to-end within a ticket's worktree; the actual "generate a diff for
this ticket" behavior is story 2.1 (CDC-41), built on top of this.
"""

import logging
from pathlib import Path

from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, ResultMessage, TextBlock, query

logger = logging.getLogger("codecrew.codegen_agent")


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
    async for message in query(prompt=prompt, options=options):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    text_parts.append(block.text)
        elif isinstance(message, ResultMessage):
            logger.info("Codegen agent run finished", extra={"subtype": message.subtype})

    return "".join(text_parts)
