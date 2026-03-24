"""Centralized logging configuration for the ArtGuard backend.

Configures JSON structured logging so that CloudWatch Logs Insights can
parse and query log fields directly. Each log line is a JSON object with:

- ``timestamp``, ``level``, ``logger``, ``message``
- ``request_id`` (when inside a request context)
- ``user_id`` (when an authenticated user is identified)
- ``extra`` fields from the log call

The module also provides:

- ``get_request_id()`` / ``set_request_id()`` for per-request correlation
- ``RequestLoggingMiddleware`` for automatic request/response logging
- ``emit_metric()`` for CloudWatch Embedded Metric Format (EMF) custom metrics

Usage::

    # In main.py (called once at startup)
    from src.apps.backend.logging_config import setup_logging
    setup_logging()
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
import uuid
from contextvars import ContextVar
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Per-request context (thread/async-safe)
# ---------------------------------------------------------------------------

_request_id: ContextVar[str] = ContextVar("request_id", default="")
_user_id: ContextVar[str] = ContextVar("user_id", default="")


def get_request_id() -> str:
    """Return the current request's correlation ID, or empty string outside a request."""
    return _request_id.get()


def set_request_id(rid: str) -> None:
    """Set the correlation ID for the current request context."""
    _request_id.set(rid)


def get_context_user_id() -> str:
    """Return the authenticated user ID for the current request context."""
    return _user_id.get()


def set_context_user_id(uid: str) -> None:
    """Set the authenticated user ID for the current request context."""
    _user_id.set(uid)


# ---------------------------------------------------------------------------
# JSON formatter (CloudWatch Logs Insights compatible)
# ---------------------------------------------------------------------------

class JSONFormatter(logging.Formatter):
    """Format log records as single-line JSON for CloudWatch Logs Insights.

    Each log line contains:
    - ``timestamp``: ISO 8601 with milliseconds
    - ``level``: DEBUG / INFO / WARNING / ERROR / CRITICAL
    - ``logger``: Logger name (module path)
    - ``message``: The formatted log message
    - ``request_id``: Correlation ID from the request context
    - ``user_id``: Authenticated user (if available)
    - ``exc_info``: Exception traceback string (if present)
    """

    def format(self, record: logging.LogRecord) -> str:
        """Format a LogRecord as a JSON string."""
        entry: dict[str, Any] = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S.") + f"{int(record.msecs):03d}Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add request context if available
        rid = _request_id.get("")
        if rid:
            entry["request_id"] = rid
        uid = _user_id.get("")
        if uid:
            entry["user_id"] = uid

        # Add source location for errors
        if record.levelno >= logging.WARNING:
            entry["source"] = f"{record.pathname}:{record.lineno}"

        # Add exception info
        if record.exc_info and record.exc_info[1]:
            entry["exc_info"] = self.formatException(record.exc_info)

        return json.dumps(entry, default=str)


# ---------------------------------------------------------------------------
# Setup function (call once at startup)
# ---------------------------------------------------------------------------

def setup_logging() -> None:
    """Configure the root logger with JSON output to stdout.

    Sets log level from the ``LOG_LEVEL`` environment variable (default INFO).
    Removes any pre-existing handlers and installs a single stdout handler
    with the JSON formatter.

    Also quiets noisy third-party loggers (botocore, urllib3, uvicorn.access).
    """
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    root = logging.getLogger()
    # Remove existing handlers (uvicorn adds its own)
    root.handlers.clear()
    root.setLevel(level)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())
    root.addHandler(handler)

    # Quiet noisy libraries
    logging.getLogger("botocore").setLevel(logging.WARNING)
    logging.getLogger("boto3").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.error").setLevel(level)


# ---------------------------------------------------------------------------
# Request logging middleware
# ---------------------------------------------------------------------------

class RequestLoggingMiddleware:
    """ASGI middleware that logs every HTTP request and response.

    For each request, logs:
    - Method, path, status code, duration in ms
    - Request ID (generated or from X-Request-ID header)
    - Client IP, User-Agent
    - User ID (if authenticated via Authorization header)

    Attaches the request_id to the response as an ``X-Request-ID`` header
    for client-side correlation.
    """

    def __init__(self, app) -> None:
        """Initialize the middleware with the ASGI application."""
        self.app = app
        self.logger = logging.getLogger("artguard.access")

    async def __call__(self, scope, receive, send) -> None:
        """Process an ASGI request."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start = time.perf_counter()

        # Extract or generate request ID
        headers = dict(scope.get("headers", []))
        request_id = (
            headers.get(b"x-request-id", b"").decode()
            or str(uuid.uuid4())[:8]
        )
        set_request_id(request_id)

        # Extract path and method
        method = scope.get("method", "?")
        path = scope.get("path", "/")
        client = scope.get("client")
        client_ip = client[0] if client else "unknown"

        # Capture response status
        response_status = 0

        async def send_wrapper(message) -> None:
            nonlocal response_status
            if message["type"] == "http.response.start":
                response_status = message["status"]
                # Inject X-Request-ID into response headers
                resp_headers = list(message.get("headers", []))
                resp_headers.append((b"x-request-id", request_id.encode()))
                message = {**message, "headers": resp_headers}
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration_ms = (time.perf_counter() - start) * 1000

            # Don't log health checks to reduce noise
            if path != "/health":
                log_data = {
                    "method": method,
                    "path": path,
                    "status": response_status,
                    "duration_ms": round(duration_ms, 1),
                    "client_ip": client_ip,
                }
                if response_status >= 500:
                    self.logger.error("%(method)s %(path)s %(status)s %(duration_ms).1fms", log_data)
                elif response_status >= 400:
                    self.logger.warning("%(method)s %(path)s %(status)s %(duration_ms).1fms", log_data)
                else:
                    self.logger.info("%(method)s %(path)s %(status)s %(duration_ms).1fms", log_data)

            # Reset context vars
            set_request_id("")
            set_context_user_id("")


# ---------------------------------------------------------------------------
# CloudWatch Embedded Metric Format (EMF) helper
# ---------------------------------------------------------------------------

def emit_metric(
    namespace: str,
    metric_name: str,
    value: float,
    unit: str = "Count",
    dimensions: Optional[dict[str, str]] = None,
) -> None:
    """Emit a custom CloudWatch metric via Embedded Metric Format (EMF).

    CloudWatch automatically extracts metrics from structured log lines
    that follow the EMF schema. This avoids the need for a separate
    PutMetricData API call (which has cost and rate-limit implications).

    Supported units: Seconds, Milliseconds, Count, Bytes, Percent, None.

    >>> emit_metric("ArtGuard", "InferenceLatency", 4.2, "Seconds")

    Args:
        namespace:   CloudWatch metric namespace (e.g. ``"ArtGuard"``).
        metric_name: Name of the metric (e.g. ``"InferenceLatency"``).
        value:       Metric value.
        unit:        CloudWatch unit string (default ``"Count"``).
        dimensions:  Optional dict of dimension name-value pairs.
    """
    dims = dimensions or {}
    dimension_keys = list(dims.keys())

    emf_log = {
        "_aws": {
            "Timestamp": int(time.time() * 1000),
            "CloudWatchMetrics": [
                {
                    "Namespace": namespace,
                    "Dimensions": [dimension_keys] if dimension_keys else [],
                    "Metrics": [{"Name": metric_name, "Unit": unit}],
                }
            ],
        },
        metric_name: value,
        **dims,
    }

    # EMF logs must go to stdout as a single JSON line
    print(json.dumps(emf_log), flush=True)
