import contextvars
import logging
import sys
import uuid
from typing import Any

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

# Context variable preserving active trace_id across asynchronous call chains
trace_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("trace_id", default="")


def get_current_trace_id() -> str:
    """
    Returns the currently active unified distributed trace ID.
    If no trace is active, generates a new UUID4.
    """
    tid = trace_id_ctx.get()
    if not tid:
        tid = str(uuid.uuid4())
        trace_id_ctx.set(tid)
    return tid


def set_current_trace_id(tid: str) -> None:
    """
    Sets active trace ID for background workers or incoming message handlers.
    """
    trace_id_ctx.set(tid)


class TraceContextLogFilter(logging.Filter):
    """
    Injects the active trace_id into every logging record.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.trace_id = trace_id_ctx.get() or "no-trace"
        return True


def setup_logging(log_level: str = "INFO"):
    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(TraceContextLogFilter())
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] [trace_id:%(trace_id)s] [%(name)s] %(message)s"
    )
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    # Clear existing handlers to prevent duplicate lines
    root_logger.handlers = [handler]


class TraceIdMiddleware(BaseHTTPMiddleware):
    """
    Standardized distributed tracing middleware.
    Accepts incoming X-Trace-Id or W3C traceparent headers.
    Generates a unique UUID4 trace_id if none provided.
    Propagates trace_id downstream in response headers and request state.
    """

    async def dispatch(self, request: Request, call_next: Any):
        # Check standard headers
        trace_id = (
            request.headers.get("X-Trace-Id")
            or request.headers.get("traceparent")
            or str(uuid.uuid4())
        )
        token = trace_id_ctx.set(trace_id)
        request.state.trace_id = trace_id

        try:
            response = await call_next(request)
            response.headers["X-Trace-Id"] = trace_id
            return response
        finally:
            trace_id_ctx.reset(token)
