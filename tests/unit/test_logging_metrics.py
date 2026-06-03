"""Unit tests for structured JSON logging and metrics counters."""

from __future__ import annotations

import json
import logging

from isabelle_mcp import metrics
from isabelle_mcp.logging import JsonFormatter, log_tool_call


def _format(record: logging.LogRecord) -> dict:
    return json.loads(JsonFormatter().format(record))


def test_json_formatter_basic_fields() -> None:
    record = logging.makeLogRecord({"name": "x", "levelno": logging.INFO, "levelname": "INFO", "msg": "hi"})
    out = _format(record)
    assert out["level"] == "INFO"
    assert out["message"] == "hi"
    assert "ts" in out


def test_json_formatter_includes_extras() -> None:
    record = logging.makeLogRecord(
        {"name": "x", "levelname": "INFO", "msg": "tool_call", "tool": "isabelle_step", "ok": True}
    )
    out = _format(record)
    assert out["tool"] == "isabelle_step"
    assert out["ok"] is True


def test_log_tool_call_emits_structured_record(caplog) -> None:
    logger = logging.getLogger("isabelle_mcp.test")
    with caplog.at_level(logging.INFO, logger="isabelle_mcp.test"):
        log_tool_call(
            logger,
            tool="isabelle_step",
            correlation_id="abc",
            latency_ms=12.34,
            ok=False,
            error_code="parse_error",
        )
    rec = caplog.records[-1]
    assert rec.tool == "isabelle_step"
    assert rec.error_code == "parse_error"
    assert rec.latency_ms == 12.3


def test_metrics_increment_and_snapshot() -> None:
    metrics.reset()
    metrics.increment("tool_calls")
    metrics.increment("tool_calls", 2)
    metrics.increment("tool_errors_parse_error")
    snap = metrics.snapshot()
    assert snap["tool_calls"] == 3
    assert snap["tool_errors_parse_error"] == 1


def test_metrics_render_prometheus() -> None:
    metrics.reset()
    metrics.increment("repls_opened", 5)
    text = metrics.render_prometheus()
    assert "isabelle_mcp_repls_opened 5" in text
    assert "# TYPE isabelle_mcp_repls_opened counter" in text
    metrics.reset()
