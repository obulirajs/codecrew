"""
Intent classification - the ONE thing every incoming chat message needs
before we know which agent (if any) should handle it.

Deliberately uses the cheap model tier (Epic 6): this is a narrow, low-
ambiguity classification task, not something that needs the strong model.
"""

import logging

from app.config import get_settings
from app.llm_client import chat_completion
from app.orchestrator.state import OrchestratorState

logger = logging.getLogger("codecrew.intent_classifier")

VALID_INTENTS = ["jira_query", "create_branch", "review_pr", "trigger_build", "unknown"]

SYSTEM_PROMPT = f"""You classify a chat message into exactly one intent.
Valid intents: {", ".join(VALID_INTENTS)}
Reply with ONLY the intent word, nothing else. If nothing fits, reply "unknown"."""


def classify_intent(state: OrchestratorState) -> OrchestratorState:
    settings = get_settings()

    print("====================********=====================")
    print(f"Selected Model is ->  {settings.cheap_model}")
    print("====================********=====================")
    

    message_text = state["event"].text

    raw_intent = chat_completion(
        model=settings.cheap_model,
        system=SYSTEM_PROMPT,
        user_message=message_text,
        max_tokens=10,
    ).lower()
    intent = raw_intent if raw_intent in VALID_INTENTS else "unknown"

    logger.info("Classified intent", extra={"intent": intent, "raw_text": message_text})

    return {**state, "intent": intent}
