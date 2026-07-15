"""
Basic structured logging. Every log line is a single-line JSON object so
it's trivially greppable/parseable - this is the seed for Epic 7's
request-ID correlation later (each agent hop will add a request_id field
to the `extra` dict passed to these loggers).

Story 0.7 (CDC-18): the same JSON lines are also written to a local
rotating log file, so past requests can be inspected after the fact and
so pointing this at a real log aggregator later (ELK, CloudWatch,
Datadog) needs no format change.
"""

import json
import logging
import sys
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path


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


def configure_logging(
    level: str = "INFO",
    log_file_path: str = "logs/codecrew.log",
    log_file_max_bytes: int = 5_000_000,
    log_file_backup_count: int = 3,
) -> None:
    formatter = JsonFormatter()

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)

    Path(log_file_path).parent.mkdir(parents=True, exist_ok=True)
    file_handler = RotatingFileHandler(
        log_file_path, maxBytes=log_file_max_bytes, backupCount=log_file_backup_count
    )
    file_handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers = [stream_handler, file_handler]
    root.setLevel(level)
