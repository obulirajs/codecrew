"""
Basic structured logging. Every log line is a single-line JSON object so
it's trivially greppable/parseable - this is the seed for Epic 7's
request-ID correlation later (each agent hop will add a request_id field
to the `extra` dict passed to these loggers).
"""

import json
import logging
import sys
from datetime import datetime, timezone


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        # Pull through any extra fields (e.g. request_id) attached to the record
        reserved = set(vars(logging.LogRecord("", "", "", 0, "", (), None)))
        for key, value in vars(record).items():
            if key not in reserved and key not in payload:
                payload[key] = value
        return json.dumps(payload)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
