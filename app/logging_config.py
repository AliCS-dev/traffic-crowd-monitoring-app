import json
import logging
from contextvars import ContextVar
from datetime import datetime, timezone

request_id_context: ContextVar[str | None] = ContextVar("request_id", default=None)


class StructuredFormatter(logging.Formatter):
    def format(self, record):
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
            "request_id": getattr(record, "request_id", request_id_context.get()),
        }
        for name in (
            "session_id",
            "duration_seconds",
            "status_code",
            "method",
            "route",
            "failure_code",
            "sampled_frames",
            "limits",
            "device",
        ):
            if hasattr(record, name):
                payload[name] = getattr(record, name)
        if record.exc_info and record.exc_info[0]:
            payload["exception_type"] = record.exc_info[0].__name__
        return json.dumps(payload)


def configure_application_logging():
    logger = logging.getLogger("app")
    if not any(
        getattr(handler, "structured_application", False) for handler in logger.handlers
    ):
        handler = logging.StreamHandler()
        handler.structured_application = True
        handler.setFormatter(StructuredFormatter())
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
