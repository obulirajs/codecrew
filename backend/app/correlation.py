"""
Request correlation ID (story 0.8, CDC-19).

Established once per incoming Teams activity in main.py, then read
automatically by JsonFormatter (app/logging_config.py) for every log line
emitted while handling that request - via contextvars, so it never needs
to be threaded explicitly through adapters/, orchestrator nodes, or
clients/. This is a lightweight, early version of Epic 7's full request-ID
tracing (story 7.2).
"""

import uuid
from contextvars import ContextVar, Token
from typing import Optional

_correlation_id: ContextVar[str] = ContextVar("correlation_id", default="-")


def new_correlation_id(activity_id: Optional[str] = None) -> str:
    """
    Reuse the Bot Framework activity's own `id` when present - it already
    uniquely identifies the activity, including redeliveries, which is
    directly useful for diagnosing duplicate-message issues. Falls back to
    a generated ID only if absent.
    """
    return activity_id or str(uuid.uuid4())


def set_correlation_id(correlation_id: str) -> Token:
    return _correlation_id.set(correlation_id)


def reset_correlation_id(token: Token) -> None:
    _correlation_id.reset(token)


def get_correlation_id() -> str:
    return _correlation_id.get()
