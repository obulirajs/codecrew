"""
The orchestrator graph itself.

Right now this is deliberately the smallest possible graph: one node,
classify_intent, start -> node -> end. This proves the LangGraph wiring
(story 0.3). From Epic 1 onward, we'll add:
  - conditional edges routing on `state["intent"]`
  - one node per specialist agent (jira_agent, codegen_agent, git_agent, ...)
  - a final "notify" node that always runs before END (Epic 7)

Building it as a graph now - instead of a few if/else statements - means
that growth is additive: new nodes and edges, not a rewrite.
"""

from langgraph.graph import END, StateGraph

from app.orchestrator.intent_classifier import classify_intent
from app.orchestrator.state import OrchestratorState


def build_graph():
    graph = StateGraph(OrchestratorState)

    graph.add_node("classify_intent", classify_intent)
    graph.set_entry_point("classify_intent")
    graph.add_edge("classify_intent", END)

    return graph.compile()


# Compiled once at import time and reused across requests.
orchestrator_graph = build_graph()
