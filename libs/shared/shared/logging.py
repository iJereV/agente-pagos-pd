"""Structured JSON logs on stdout, in the shape Cloud Logging parses.

Extra fields passed with ``logger.info("msg", extra={"order_id": "..."})`` are
emitted as top-level JSON keys, so they become searchable ``jsonPayload`` fields.
"""

import json
import logging
import sys
from datetime import UTC, datetime

_RESERVED = frozenset(vars(logging.makeLogRecord({})).keys()) | {"message", "asctime"}

_SEVERITY = {
    logging.DEBUG: "DEBUG",
    logging.INFO: "INFO",
    logging.WARNING: "WARNING",
    logging.ERROR: "ERROR",
    logging.CRITICAL: "CRITICAL",
}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, object] = {
            "severity": _SEVERITY.get(record.levelno, "DEFAULT"),
            "message": record.getMessage(),
            "time": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "logger": record.name,
        }
        entry.update({k: v for k, v in vars(record).items() if k not in _RESERVED})
        if record.exc_info:
            entry["stack_trace"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str, ensure_ascii=False)


def setup_logging(level: int | str = logging.INFO) -> None:
    """Route every logger (including uvicorn's) through one JSON handler."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
    for name in ("uvicorn", "uvicorn.error"):
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.propagate = True
    # Access logs print full URLs, and some carry tokens (Meta's hub.verify_token,
    # link tokens). Cloud Run already records requests, so drop them here. uvicorn
    # decides whether to log access with hasHandlers(), so propagation must be off.
    access = logging.getLogger("uvicorn.access")
    access.handlers.clear()
    access.propagate = False
    # httpx logs every request URL at INFO; Meta media URLs are signed.
    logging.getLogger("httpx").setLevel(logging.WARNING)
