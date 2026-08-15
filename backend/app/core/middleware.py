import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Binds a request_id to every log line emitted while handling this request.

    Downstream services (workers publishing to Kafka, DB writes) should
    propagate/attach their own correlation fields (import_id, campaign_id,
    campaign_run_id, message_id, worker_id) on top of this per the
    observability requirement - this middleware only seeds request_id.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get("X-Request-Id", str(uuid.uuid4()))
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)
        response = await call_next(request)
        response.headers["X-Request-Id"] = request_id
        return response
