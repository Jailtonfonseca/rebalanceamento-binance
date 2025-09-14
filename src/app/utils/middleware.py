"""Application middlewares for request tracing and error handling.

This module defines reusable Starlette/FastAPI middlewares that improve
observability and robustness:
- RequestIDMiddleware: injects a unique X-Request-ID header and attaches it to
  the request state for correlation in logs.
- ErrorHandlingMiddleware: catches unhandled exceptions and returns a
  standardized JSON error response while logging details.
"""

from __future__ import annotations

import json
import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

logger = logging.getLogger(__name__)


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Ensures each request has an X-Request-ID and logs basic access info."""

    def __init__(self, app, header_name: str = "X-Request-ID") -> None:
        super().__init__(app)
        self.header_name = header_name

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        request_id = request.headers.get(self.header_name) or str(uuid.uuid4())
        request.state.request_id = request_id

        start = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            duration_ms = (time.perf_counter() - start) * 1000
            # Minimal access log to avoid leaking sensitive data
            logger.info(
                json.dumps(
                    {
                        "request_id": request_id,
                        "method": request.method,
                        "path": request.url.path,
                        "status": getattr(response, "status_code", 500),
                        "duration_ms": round(duration_ms, 2),
                        "client": request.client.host if request.client else None,
                    }
                )
            )
        # Ensure header is present on response
        if isinstance(response, Response):
            response.headers[self.header_name] = request_id
        return response


class ErrorHandlingMiddleware(BaseHTTPMiddleware):
    """Catches unexpected exceptions and returns a safe JSON error body."""

    def __init__(self, app) -> None:
        super().__init__(app)

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        try:
            return await call_next(request)
        except Exception:  # noqa: BLE001 - top-level catch on purpose
            request_id = getattr(
                getattr(request, "state", object()), "request_id", None
            )
            logger.error(
                "Unhandled exception while processing request",
                exc_info=True,
                extra={"request_id": request_id},
            )
            body = {
                "error": "internal_server_error",
                "message": "An unexpected error occurred. Please try again later.",
            }
            if request_id:
                body["request_id"] = request_id
            return JSONResponse(status_code=500, content=body)
