import logging
from time import monotonic
from uuid import uuid4

from app.logging_config import request_id_context

LOGGER = logging.getLogger(__name__)


class RequestLoggingMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        request_id = str(uuid4())
        token = request_id_context.set(request_id)
        scope.setdefault("state", {})["request_id"] = request_id
        started = monotonic()
        status_code = 500

        async def send_with_id(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                message = dict(message)
                message["headers"] = [
                    *message.get("headers", []),
                    (b"x-request-id", request_id.encode("ascii")),
                ]
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        finally:
            route = scope.get("route")
            LOGGER.info(
                "request_completed",
                extra={
                    "request_id": request_id,
                    "status_code": status_code,
                    "method": scope["method"],
                    "route": getattr(route, "path", "unmatched"),
                    "duration_seconds": round(monotonic() - started, 6),
                },
            )
            request_id_context.reset(token)
