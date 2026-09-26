from __future__ import annotations

import contextvars
import json
import logging
from datetime import datetime, timezone


request_id_context: contextvars.ContextVar[str | None] = contextvars.ContextVar("request_id", default=None)
organisation_id_context: contextvars.ContextVar[str | None] = contextvars.ContextVar("organisation_id", default=None)
user_id_context: contextvars.ContextVar[str | None] = contextvars.ContextVar("user_id", default=None)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "service": "regbridge-api",
            "logger": record.name,
            "event": getattr(record, "event", record.getMessage()),
        }
        for key, value in (
            ("request_id", request_id_context.get()),
            ("organisation_id", organisation_id_context.get() or getattr(record, "organisation_id", None)),
            ("user_id", user_id_context.get()),
            ("method", getattr(record, "method", None)),
            ("path", getattr(record, "path", None)),
            ("status", getattr(record, "status", None)),
            ("duration_ms", getattr(record, "duration_ms", None)),
            ("result", getattr(record, "result", None)),
            ("run_id", getattr(record, "run_id", None)),
            ("artifact_id", getattr(record, "artifact_id", None)),
            ("run_revision", getattr(record, "run_revision", None)),
            ("lifecycle_event", getattr(record, "lifecycle_event", None)),
            ("version", getattr(record, "version", None)),
            ("environment", getattr(record, "environment", None)),
        ):
            if value is not None:
                payload[key] = value
        if record.exc_info:
            payload["exception"] = record.exc_info[0].__name__ if record.exc_info[0] else "Exception"
        return json.dumps(payload, separators=(",", ":"), ensure_ascii=True)


def configure_logging(log_level: str) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(log_level.upper())
    # These access loggers include raw query strings; OIDC callbacks carry codes.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpx2").setLevel(logging.WARNING)
    logging.getLogger("httpcore2").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
