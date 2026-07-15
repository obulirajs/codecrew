"""
Extracts a structured spec from a fetched JIRA ticket (story 1.4, CDC-15).

Scope note (per the ticket): this is an internal data-shaping utility for
Epic 2's codegen agent (not built yet) - NOT a chat-facing intent. It's a
pure function layered on app/clients/jira_client.py; nothing here touches
the orchestrator.

`ticket_type` and `labels` come straight from the issue's structured
fields. `acceptance_criteria` has to be parsed out of the free-text
`description` (ADF), since JIRA has no dedicated AC field. This project's
own tickets consistently mark section headers ("Acceptance criteria",
"Definition of done", "Scope note", ...) as a bold ("strong") text run
starting the paragraph, which is what the parser keys off to find the AC
section and to know where it ends.
"""

import re
from typing import Any, Optional

from pydantic import BaseModel

from app.clients.jira_client import adf_to_text

_AC_HEADER_RE = re.compile(r"^acceptance criteria\s*:?\s*(.*)$", re.IGNORECASE | re.DOTALL)
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


class TicketSpec(BaseModel):
    summary: str
    acceptance_criteria: list[str]
    ticket_type: str
    labels: list[str]


def extract_ticket_spec(issue: dict) -> TicketSpec:
    """Shape a fetched issue (JiraClient.get_issue's return value) into a TicketSpec."""
    fields = issue["fields"]
    return TicketSpec(
        summary=fields["summary"],
        acceptance_criteria=_extract_acceptance_criteria(fields.get("description")),
        ticket_type=fields["issuetype"]["name"],
        labels=fields.get("labels", []),
    )


def _section_header(paragraph_node: dict) -> Optional[tuple[bool, str]]:
    """
    If `paragraph_node` opens a bold-labeled section (this project's
    convention for headers like "Acceptance criteria", "Definition of
    done", "Scope note:"), return (is_acceptance_criteria, inline_remainder).
    Returns None if the paragraph isn't a section header at all (i.e. its
    first text run isn't bold) - a plain body paragraph.
    """
    content = paragraph_node.get("content") or []
    if not content or content[0].get("type") != "text":
        return None
    marks = content[0].get("marks") or []
    if not any(mark.get("type") == "strong" for mark in marks):
        return None

    first_text = content[0].get("text", "")
    match = _AC_HEADER_RE.match(first_text.strip())
    if not match:
        return False, ""

    remainder = (match.group(1) + "".join(n.get("text", "") for n in content[1:])).strip()
    return True, remainder


def _split_sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_SPLIT_RE.split(text.strip()) if s.strip()]


def _extract_acceptance_criteria(description: Optional[dict[str, Any]]) -> list[str]:
    if not description:
        return []

    criteria: list[str] = []
    in_ac_section = False

    for node in description.get("content", []) or []:
        node_type = node.get("type")

        if node_type == "paragraph":
            header = _section_header(node)
            if header is not None:
                is_ac, remainder = header
                in_ac_section = is_ac
                if is_ac and remainder:
                    criteria.extend(_split_sentences(remainder))
                continue

            if in_ac_section:
                text = adf_to_text(node)
                if text:
                    criteria.extend(_split_sentences(text))

        elif node_type in ("bulletList", "orderedList") and in_ac_section:
            for item in node.get("content", []) or []:
                text = adf_to_text(item)
                if text:
                    criteria.append(text)

    return criteria
