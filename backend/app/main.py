"""
CodeCrew backend entrypoint.

Two endpoints for the Epic 0 walking skeleton:
  POST /teams/messages  - Bot Framework webhook (story 0.1, 0.2)
  GET  /health          - dependency status check (story 0.5)
"""

import logging

from fastapi import FastAPI, Request

from app.adapters.teams_adapter import normalize_teams_activity, send_reply
from app.config import get_settings
from app.logging_config import configure_logging
from app.orchestrator.graph import orchestrator_graph

configure_logging()
logger = logging.getLogger("codecrew.main")

app = FastAPI(title="CodeCrew Orchestrator")


@app.get("/health")
async def health():
    """
    Story 0.5: returns 200 with dependency status. Doesn't call out to
    Anthropic or Teams on every health check (too expensive/slow) - just
    confirms required config is present, which is what actually breaks
    the service if missing.
    """
    try:
        get_settings()
        deps_ok = True
    except Exception as exc:  # noqa: BLE001 - deliberately broad for a health check
        logger.error("Health check failed: missing/invalid config: %s", exc)
        deps_ok = False

    return {
        "status": "ok" if deps_ok else "degraded",
        "dependencies": {
            "config": "ok" if deps_ok else "missing_required_settings",
        },
    }


@app.post("/teams/messages")
async def teams_messages(request: Request):
    """
    Story 0.1: acknowledge any @-mention within 3s.
    Story 0.2: normalize the payload before it reaches the orchestrator.
    Story 0.3: run it through the orchestrator graph for intent classification.
    Story 1.1: reply with the jira_agent's ticket summary when available.
    """
    payload = await request.json()

    activity_type = payload.get("type")
    if activity_type != "message":
        logger.debug("Ignoring non-message activity: %s", activity_type)
        return {"received": True, "ignored": True, "activity_type": activity_type}

    event = normalize_teams_activity(payload)
    logger.info("Received Teams message", extra={"user": event.user, "channel": event.channel})

    result = orchestrator_graph.invoke({"event": event})
    intent = result.get("intent", "unknown")
    reply_text = result.get("reply_text") or f"Got it - classified as: {intent}"

    await send_reply(payload, reply_text)

    return {"received": True, "intent": intent}
