"""
JIRA agent node (stories 1.1/1.2, CDC-12/CDC-13) - Epic 1's first
specialist agent.

Handles the "jira_query" intent, in two flavors distinguished by message
content:
  - a ticket key present (e.g. "show me ticket CDC-12") -> single-ticket
    lookup: title, status, assignee, description summary.
  - phrasing like "list my tickets" / "assigned to me" and no ticket key
    -> lists tickets assigned to the single JIRA account configured via
    JIRA_EMAIL (see CDC-13's scope note: real Teams-user-to-JIRA-account
    identity mapping is an Epic 8 concern), scoped to JIRA_PROJECT_KEY.

Both paths go through app/clients/jira_client.py.
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
_LIST_ASSIGNED_PATTERN = re.compile(
    r"\b(assigned to me|my tickets?|my queue|assigned tickets?)\b", re.IGNORECASE
)
_DESCRIPTION_SUMMARY_LIMIT = 300
_LIST_DISPLAY_LIMIT = 10


def _extract_ticket_key(text: str) -> Optional[str]:
    match = _TICKET_KEY_PATTERN.search(text.upper())
    return match.group(1) if match else None


def _looks_like_list_request(text: str) -> bool:
    return bool(_LIST_ASSIGNED_PATTERN.search(text))


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

    if ticket_key is None and _looks_like_list_request(message_text):
        return _handle_list_assigned(state)

    if ticket_key is None:
        logger.info("No ticket key found in jira_query message", extra={"raw_text": message_text})
        return {
            **state,
            "reply_text": (
                "I couldn't find a ticket key in that message - "
                'try something like "show me ticket CDC-12" or "list my tickets".'
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


def _handle_list_assigned(state: OrchestratorState) -> OrchestratorState:
    """
    Story 1.2 (CDC-13): list tickets assigned to the single configured JIRA
    account (JIRA_EMAIL), scoped to JIRA_PROJECT_KEY. "me" is that one
    account - see the ticket's scope note on why real Teams-user identity
    mapping isn't in play yet.
    """
    try:
        with JiraClient() as client:
            jql = f'project = "{client.project_key}" AND assignee = currentUser() ORDER BY updated DESC'
            results = client.search_issues(jql, max_results=_LIST_DISPLAY_LIMIT, fields=["summary", "status"])
    except JiraAuthenticationError:
        logger.error("Jira authentication failed while listing assigned tickets")
        return {**state, "reply_text": "I couldn't authenticate with Jira right now - please let a maintainer know."}
    except JiraAPIError:
        logger.exception("Jira API error while listing assigned tickets")
        return {**state, "reply_text": "Something went wrong listing your tickets from Jira - please try again shortly."}

    issues = results.get("issues", [])
    has_more = not results.get("isLast", True)

    logger.info("Listed assigned tickets", extra={"shown": len(issues), "has_more": has_more})

    if not issues:
        return {**state, "reply_text": "You have no tickets assigned right now."}

    lines = ["Tickets assigned to you:"]
    for issue in issues:
        fields = issue["fields"]
        lines.append(f"- {issue['key']}: {fields['summary']} ({fields['status']['name']})")
    if has_more:
        lines.append(f"...plus more beyond the {len(issues)} most recently updated shown here.")

    return {**state, "reply_text": "\n".join(lines)}
