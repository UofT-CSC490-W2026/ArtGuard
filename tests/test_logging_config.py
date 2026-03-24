"""Tests for src.apps.backend.logging_config."""
import json
import logging
import os
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.apps.backend.logging_config import (
    JSONFormatter,
    RequestLoggingMiddleware,
    emit_metric,
    get_context_user_id,
    get_request_id,
    set_context_user_id,
    set_request_id,
    setup_logging,
)


# ---------------------------------------------------------------------------
# Context var helpers
# ---------------------------------------------------------------------------

class TestContextVars:
    def test_request_id_default(self):
        set_request_id("")
        assert get_request_id() == ""

    def test_set_and_get_request_id(self):
        set_request_id("abc-123")
        assert get_request_id() == "abc-123"
        set_request_id("")  # cleanup

    def test_user_id_default(self):
        set_context_user_id("")
        assert get_context_user_id() == ""

    def test_set_and_get_user_id(self):
        set_context_user_id("user-42")
        assert get_context_user_id() == "user-42"
        set_context_user_id("")  # cleanup


# ---------------------------------------------------------------------------
# JSONFormatter
# ---------------------------------------------------------------------------

class TestJSONFormatter:
    def setup_method(self):
        self.formatter = JSONFormatter()

    def test_basic_format(self):
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=10,
            msg="Hello %s",
            args=("world",),
            exc_info=None,
        )
        output = self.formatter.format(record)
        data = json.loads(output)
        assert data["level"] == "INFO"
        assert data["logger"] == "test.logger"
        assert data["message"] == "Hello world"
        assert "timestamp" in data

    def test_includes_request_id(self):
        set_request_id("req-abc")
        try:
            record = logging.LogRecord(
                name="test", level=logging.INFO, pathname="t.py",
                lineno=1, msg="hi", args=(), exc_info=None,
            )
            data = json.loads(self.formatter.format(record))
            assert data["request_id"] == "req-abc"
        finally:
            set_request_id("")

    def test_includes_user_id(self):
        set_context_user_id("user-99")
        try:
            record = logging.LogRecord(
                name="test", level=logging.INFO, pathname="t.py",
                lineno=1, msg="hi", args=(), exc_info=None,
            )
            data = json.loads(self.formatter.format(record))
            assert data["user_id"] == "user-99"
        finally:
            set_context_user_id("")

    def test_no_request_id_when_empty(self):
        set_request_id("")
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="t.py",
            lineno=1, msg="hi", args=(), exc_info=None,
        )
        data = json.loads(self.formatter.format(record))
        assert "request_id" not in data

    def test_warning_includes_source(self):
        record = logging.LogRecord(
            name="test", level=logging.WARNING, pathname="/app/foo.py",
            lineno=42, msg="warn", args=(), exc_info=None,
        )
        data = json.loads(self.formatter.format(record))
        assert data["source"] == "/app/foo.py:42"

    def test_error_includes_source(self):
        record = logging.LogRecord(
            name="test", level=logging.ERROR, pathname="/app/bar.py",
            lineno=99, msg="err", args=(), exc_info=None,
        )
        data = json.loads(self.formatter.format(record))
        assert "source" in data

    def test_info_no_source(self):
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="t.py",
            lineno=1, msg="hi", args=(), exc_info=None,
        )
        data = json.loads(self.formatter.format(record))
        assert "source" not in data

    def test_exception_info(self):
        try:
            raise ValueError("boom")
        except ValueError:
            import sys
            exc_info = sys.exc_info()

        record = logging.LogRecord(
            name="test", level=logging.ERROR, pathname="t.py",
            lineno=1, msg="fail", args=(), exc_info=exc_info,
        )
        data = json.loads(self.formatter.format(record))
        assert "exc_info" in data
        assert "ValueError: boom" in data["exc_info"]


# ---------------------------------------------------------------------------
# setup_logging
# ---------------------------------------------------------------------------

class TestSetupLogging:
    def test_configures_root_logger(self):
        setup_logging()
        root = logging.getLogger()
        assert root.level == logging.INFO
        assert len(root.handlers) == 1
        assert isinstance(root.handlers[0].formatter, JSONFormatter)

    def test_respects_log_level_env(self):
        with patch.dict(os.environ, {"LOG_LEVEL": "DEBUG"}):
            setup_logging()
            root = logging.getLogger()
            assert root.level == logging.DEBUG

    def test_quiets_noisy_loggers(self):
        setup_logging()
        assert logging.getLogger("botocore").level == logging.WARNING
        assert logging.getLogger("boto3").level == logging.WARNING
        assert logging.getLogger("urllib3").level == logging.WARNING
        assert logging.getLogger("uvicorn.access").level == logging.WARNING


# ---------------------------------------------------------------------------
# RequestLoggingMiddleware
# ---------------------------------------------------------------------------

class TestRequestLoggingMiddleware:
    @pytest.mark.asyncio
    async def test_non_http_passthrough(self):
        inner = AsyncMock()
        mw = RequestLoggingMiddleware(inner)
        scope = {"type": "websocket"}
        await mw(scope, AsyncMock(), AsyncMock())
        inner.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_http_request_logging(self):
        async def fake_app(scope, receive, send):
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"ok"})

        mw = RequestLoggingMiddleware(fake_app)
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/api/test",
            "headers": [],
            "client": ("127.0.0.1", 8000),
        }
        sent = []

        async def capture_send(msg):
            sent.append(msg)

        await mw(scope, AsyncMock(), capture_send)
        # Check X-Request-ID was injected
        start_msg = sent[0]
        header_keys = [h[0] for h in start_msg["headers"]]
        assert b"x-request-id" in header_keys

    @pytest.mark.asyncio
    async def test_health_not_logged(self):
        async def fake_app(scope, receive, send):
            await send({"type": "http.response.start", "status": 200, "headers": []})

        mw = RequestLoggingMiddleware(fake_app)
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/health",
            "headers": [],
            "client": ("127.0.0.1", 8000),
        }
        with patch.object(mw.logger, "info") as mock_log:
            await mw(scope, AsyncMock(), AsyncMock())
            mock_log.assert_not_called()

    @pytest.mark.asyncio
    async def test_uses_existing_request_id(self):
        async def fake_app(scope, receive, send):
            assert get_request_id() == "custom-id"
            await send({"type": "http.response.start", "status": 200, "headers": []})

        mw = RequestLoggingMiddleware(fake_app)
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/test",
            "headers": [(b"x-request-id", b"custom-id")],
            "client": ("127.0.0.1", 8000),
        }
        await mw(scope, AsyncMock(), AsyncMock())

    @pytest.mark.asyncio
    async def test_logs_500_as_error(self):
        async def fake_app(scope, receive, send):
            await send({"type": "http.response.start", "status": 500, "headers": []})

        mw = RequestLoggingMiddleware(fake_app)
        scope = {
            "type": "http",
            "method": "POST",
            "path": "/fail",
            "headers": [],
            "client": ("10.0.0.1", 9000),
        }
        with patch.object(mw.logger, "error") as mock_error:
            await mw(scope, AsyncMock(), AsyncMock())
            mock_error.assert_called_once()

    @pytest.mark.asyncio
    async def test_logs_400_as_warning(self):
        async def fake_app(scope, receive, send):
            await send({"type": "http.response.start", "status": 404, "headers": []})

        mw = RequestLoggingMiddleware(fake_app)
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/missing",
            "headers": [],
            "client": ("10.0.0.1", 9000),
        }
        with patch.object(mw.logger, "warning") as mock_warn:
            await mw(scope, AsyncMock(), AsyncMock())
            mock_warn.assert_called_once()


# ---------------------------------------------------------------------------
# emit_metric
# ---------------------------------------------------------------------------

class TestEmitMetric:
    def test_basic_metric(self, capsys):
        emit_metric("ArtGuard", "TestMetric", 42.0)
        output = capsys.readouterr().out
        data = json.loads(output)
        assert data["TestMetric"] == 42.0
        assert data["_aws"]["CloudWatchMetrics"][0]["Namespace"] == "ArtGuard"

    def test_metric_with_dimensions(self, capsys):
        emit_metric("ArtGuard", "Latency", 1.5, "Seconds", {"env": "prod"})
        output = capsys.readouterr().out
        data = json.loads(output)
        assert data["env"] == "prod"
        assert data["Latency"] == 1.5
        cw = data["_aws"]["CloudWatchMetrics"][0]
        assert cw["Metrics"][0]["Unit"] == "Seconds"
        assert cw["Dimensions"] == [["env"]]

    def test_metric_without_dimensions(self, capsys):
        emit_metric("NS", "Count", 1.0)
        output = capsys.readouterr().out
        data = json.loads(output)
        cw = data["_aws"]["CloudWatchMetrics"][0]
        assert cw["Dimensions"] == []

    def test_metric_has_timestamp(self, capsys):
        emit_metric("NS", "M", 0.0)
        output = capsys.readouterr().out
        data = json.loads(output)
        ts = data["_aws"]["Timestamp"]
        assert isinstance(ts, int)
        assert ts > 0
