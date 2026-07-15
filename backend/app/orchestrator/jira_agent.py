"""
JIRA agent node (story 1.1, CDC-12) - Epic 1's first specialist agent.

Handles the "jira_query" intent: pulls a ticket key out of the user's
message, fetches it via app/clients/jira_client.py, and formats a
chat-friendly reply with title, status, assignee, and a description
summary.
"""

import logging
import re
from typing import Optional

from app.clients.jira_client import (
    JiraAPIError,
    JiraAuthenticationError,
    JiraClient,
    JiraIssueNotFoundError,
)
from app.orchestrator.state import OrchestratorState

logger = logging.getLogger("codecrew.jira_agent")

_TICKET_KEY_PATTERN = re.compile(r"\b([A-Z][A-Z0-9]{1,9}-\d+)\b")
_DESCRIPTION_SUMMARY_LIMIT = 300


def _extract_ticket_key(text: str) -> Optional[str]:
    match = _TICKET_KEY_PATTERN.search(text.upper())
    return match.group(1) if match else None


def _adf_to_text(node: Optional[dict]) -> str:
    """
    Flatten an Atlassian Document Format node into plain text - the JIRA
    REST v3 `description` field is ADF JSON, not plain text or markdown.
    """
    if not node:
        return ""

    parts: list[str] = []

    def walk(n: dict) -> None:
        if n.get("type") == "text":
            parts.append(n.get("text", ""))
        for child in n.get("content", []) or []:
            walk(child)
        if n.get("type") == "paragraph":
            parts.append("\n")

    walk(node)
    return "".join(parts).strip()


def _summarize(description: str, limit: int = _DESCRIPTION_SUMMARY_LIMIT) -> str:
    description = " ".join(description.split())
    if len(description) <= limit:
        return description
    return description[:limit].rstrip() + "..."


def handle_jira_query(state: OrchestratorState) -> OrchestratorState:
    message_text = state["event"].text
    ticket_key = _extract_ticket_key(message_text)

    if ticket_key is None:
        logger.info("No ticket key found in jira_query message", extra={"raw_text": message_text})
        return {
            **state,
            "reply_text": (
                "I couldn't find a ticket key in that message - "
                'try something like "show me ticket CDC-12".'
            ),
        }

    try:
        with JiraClient() as client:
            issue = client.get_issue(ticket_key)
    except JiraIssueNotFoundError:
        logger.info("Ticket not found", extra={"ticket_key": ticket_key})
        return {**state, "reply_text": f"I couldn't find a ticket called {ticket_key} - double check the key."}
    except JiraAuthenticationError:
        logger.error("Jira authentication failed while handling jira_query", extra={"ticket_key": ticket_key})
        return {**state, "reply_text": "I couldn't authenticate with Jira right now - please let a maintainer know."}
    except JiraAPIError:
        logger.exception("Jira API error while handling jira_query", extra={"ticket_key": ticket_key})
        return {**state, "reply_text": f"Something went wrong fetching {ticket_key} from Jira - please try again shortly."}

    fields = issue["fields"]
    title = fields["summary"]
    status = fields["status"]["name"]
    assignee = fields["assignee"]["displayName"] if fields.get("assignee") else "Unassigned"
    description_summary = _summarize(_adf_to_text(fields.get("description")))

    reply_lines = [
        f"{ticket_key}: {title}",
        f"Status: {status}",
        f"Assignee: {assignee}",
    ]
    if description_summary:
        reply_lines.append(f"Summary: {description_summary}")

    logger.info("Fetched ticket for jira_query", extra={"ticket_key": ticket_key, "status": status})

    return {**state, "reply_text": "\n".join(reply_lines)}
