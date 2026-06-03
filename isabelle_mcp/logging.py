"""Structured JSON logging to stderr.

One JSON object per log record. Tool-call records carry timing and outcome but
never goal text or file content (only counts, codes, ids). Use
``configure_logging`` once at startup and ``log_tool_call`` from the tool
adapter.
"""

from __future__ import annotations

import json
import logging
import sys
from typing import Any

__all__ = ["JsonFormatter", "configure_logging", "log_tool_call"]

# Standard LogRecord attributes we never copy into the "extra" payload.
_RESERVED = set(
    vars(logging.makeLogRecord({})).keys()
) | {"message", "asctime", "taskName"}


class JsonFormatter(logging.Formatter):
    """Render log records as single-line JSON to stderr."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        # Merge structured extras passed via logger(..., extra={...}).
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO") -> None:
    """Install the JSON formatter on the root logger's stderr handler."""
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())


def log_tool_call(
    logger: logging.Logger,
    *,
    tool: str,
    correlation_id: str,
    latency_ms: float,
    ok: bool,
    error_code: str | None = None,
) -> None:
    """Emit a single structured record for a completed tool call."""
    logger.info(
        "tool_call",
        extra={
            "event": "tool_call",
            "tool": tool,
            "correlation_id": correlation_id,
            "latency_ms": round(latency_ms, 1),
            "ok": ok,
            "error_code": error_code,
        },
    )
