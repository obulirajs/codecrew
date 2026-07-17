"""
MS Teams adapter.

Two responsibilities, matching stories 0.1 and 0.2:
  1. normalize_teams_activity(): turn a raw Bot Framework "Activity" payload
     into our platform-agnostic NormalizedEvent.
  2. send_reply(): post a text reply back into the originating Teams thread,
     using real Bot Framework auth (botframework-connector handles the
     OAuth2 client-credentials token exchange for us).
"""

import asyncio
import logging
from functools import lru_cache

from botbuilder.schema import Activity, ChannelAccount, ConversationAccount
from botframework.connector import ConnectorClient
from botframework.connector.auth import MicrosoftAppCredentials

from app.config import get_settings
from app.models.events import NormalizedEvent, Platform

logger = logging.getLogger("codecrew.teams_adapter")


@lru_cache
def _get_credentials() -> MicrosoftAppCredentials:
    """
    Cached so the same MicrosoftAppCredentials instance - and its internal
    bearer-token cache - is reused across every reply for the process
    lifetime, instead of re-exchanging a token with Microsoft's OAuth
    endpoint on every single call.
    """
    settings = get_settings()
    return MicrosoftAppCredentials(
        app_id=settings.teams_app_id,
        password=settings.teams_app_password,
        channel_auth_tenant=settings.teams_tenant_id,
    )


def normalize_teams_activity(payload: dict) -> NormalizedEvent:
    """
    Convert a raw Bot Framework Activity JSON payload into a NormalizedEvent.

    Expected (simplified) shape of `payload`:
    {
      "from": {"id": "29:abc123..."},
      "conversation": {"id": "19:def456..."},
      "text": "@CodeCrew show me ticket PROJ-12",
      "timestamp": "2026-07-13T10:00:00.000Z",
      "channelId": "msteams",
      "serviceUrl": "https://smba.trafficmanager.net/..."
    }
    """
    return NormalizedEvent(
        user=payload["from"]["id"],
        channel=payload["conversation"]["id"],
        text=payload.get("text", ""),
        platform=Platform.teams,
    )


def _send_reply_sync(payload: dict, reply_text: str, settings) -> None:
    """
    The actual blocking call. botframework-connector's ConnectorClient is
    built on `msrest` and is synchronous - it also transparently handles the
    OAuth2 client-credentials exchange against login.microsoftonline.com
    using the credentials below, caching/refreshing the token for us.
    """
    service_url = payload["serviceUrl"]
    conversation_id = payload["conversation"]["id"]

    credentials = _get_credentials()
    connector = ConnectorClient(credentials, base_url=service_url)

    reply_activity = Activity(
        type="message",
        text=reply_text,
        recipient=ChannelAccount(
            id=payload["from"]["id"], name=payload["from"].get("name", "")
        ),
        from_property=ChannelAccount(
            id=payload["recipient"]["id"], name=payload["recipient"].get("name", "")
        ),
        conversation=ConversationAccount(id=conversation_id),
    )

    connector.conversations.send_to_conversation(conversation_id, reply_activity)


async def send_reply(payload: dict, reply_text: str) -> None:
    """
    Post a reply back into the Teams conversation the activity came from.

    `payload` is the original inbound activity - Bot Framework replies need
    its serviceUrl + conversation id to know where to send the response,
    plus the from/recipient IDs to address the reply correctly.

    Runs the blocking connector call in a worker thread via asyncio.to_thread
    so it doesn't stall the FastAPI event loop while waiting on the network.
    """
    settings = get_settings()

    if not payload.get("serviceUrl"):
        logger.warning("No serviceUrl on inbound activity; cannot send reply.")
        return

    try:
        await asyncio.to_thread(_send_reply_sync, payload, reply_text, settings)
        logger.info("Sent reply to conversation %s", payload["conversation"]["id"])
    except Exception:
        # Don't let a failed reply take down request handling - log and move on.
        logger.exception("Failed to send Teams reply")
