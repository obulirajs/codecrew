"""
The orchestrator graph itself.

Routes on `state["intent"]` via a conditional edge out of classify_intent
(story 1.1, CDC-12): "jira_query" goes to the jira_agent node, everything
else goes straight to END for now. From here, Epic 1+ onward will add:
  - one node per specialist agent (codegen_agent, git_agent, ...)
  - a final "notify" node that always runs before END (Epic 7)

Building it as a graph now - instead of a few if/else statements - means
that growth is additive: new nodes and edges, not a rewrite.
"""

from langgraph.graph import END, StateGraph

from app.orchestrator.intent_classifier import classify_intent
from app.orchestrator.jira_agent import handle_jira_query
from app.orchestrator.state import OrchestratorState


def _route_by_intent(state: OrchestratorState) -> str:
    return "jira_query" if state["intent"] == "jira_query" else "end"


def build_graph():
    graph = StateGraph(OrchestratorState)

    graph.add_node("classify_intent", classify_intent)
    graph.add_node("jira_agent", handle_jira_query)

    graph.set_entry_point("classify_intent")
    graph.add_conditional_edges(
        "classify_intent",
        _route_by_intent,
        {"jira_query": "jira_agent", "end": END},
    )
    graph.add_edge("jira_agent", END)

    return graph.compile()


# Compiled once at import time and reused across requests.
orchestrator_graph = build_graph()
