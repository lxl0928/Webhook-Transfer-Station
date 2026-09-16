import logging
import re
import time
import uuid

logger = logging.getLogger("station.http")
VALID_TRACE = re.compile(r"^[a-zA-Z0-9._-]{1,64}$")


class TraceMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = dict(scope["headers"])
        supplied = headers.get(b"x-trace-id", b"").decode("ascii", errors="ignore")
        trace_id = supplied if VALID_TRACE.fullmatch(supplied) else uuid.uuid4().hex
        scope.setdefault("state", {})["trace_id"] = trace_id
        started = time.monotonic()
        status = 500

        async def traced_send(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                message["headers"] = [
                    (k, v) for k, v in message["headers"] if k.lower() != b"x-trace-id"
                ]
                message["headers"].append((b"x-trace-id", trace_id.encode()))
            await send(message)

        try:
            await self.app(scope, receive, traced_send)
        finally:
            # Never log query strings: wid and target tokens are capability secrets.
            logger.info(
                "request trace_id=%s method=%s path=%s status=%s cost_ms=%.2f",
                trace_id,
                scope["method"],
                scope["path"],
                status,
                (time.monotonic() - started) * 1000,
            )
