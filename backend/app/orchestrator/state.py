"""
Shared state that flows through the orchestrator graph.

This TypedDict is what every LangGraph node reads from and writes back to.
Right now it only needs to carry the incoming event and the classified
intent - Epic 1 onward will add fields like `ticket_data`, `diff`,
`pr_number`, etc. as new nodes are added.
"""

from typing import TypedDict

from app.models.events import NormalizedEvent


class OrchestratorState(TypedDict, total=False):
    event: NormalizedEvent
    intent: str
    reply_text: str
