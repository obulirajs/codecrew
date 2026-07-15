"""
Common internal event schema.

Every chat adapter (Teams, and later Slack / Google Chat) must translate its
platform-specific payload into this one shape. The orchestrator only ever
sees a NormalizedEvent - it never needs to know which platform sent it.
This is the contract that makes the chat layer swappable (story 0.2).
"""

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


class Platform(str, Enum):
    teams = "teams"
    slack = "slack"
    google_chat = "google_chat"


class NormalizedEvent(BaseModel):
    user: str = Field(..., description="Stable identifier for the sender on their platform")
    channel: str = Field(..., description="Channel/thread identifier the message came from")
    text: str = Field(..., description="Raw text of the user's message")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    platform: Platform
