"""Process-wide counters with a thread-safe API and Prometheus rendering.

Lightweight by design: a small set of integer counters covering tool activity,
REPL lifecycle, and daemon restarts. No external dependency.
"""

from __future__ import annotations

import threading
from collections import Counter

__all__ = ["increment", "snapshot", "render_prometheus", "reset"]

_lock = threading.Lock()
_counters: Counter[str] = Counter()


def increment(name: str, amount: int = 1) -> None:
    """Add ``amount`` to the named counter (thread-safe)."""
    with _lock:
        _counters[name] += amount


def snapshot() -> dict[str, int]:
    """Return a copy of all counters."""
    with _lock:
        return dict(_counters)


def reset() -> None:
    """Clear all counters (used by tests)."""
    with _lock:
        _counters.clear()


def render_prometheus() -> str:
    """Render counters in Prometheus text exposition format."""
    lines: list[str] = []
    for name, value in sorted(snapshot().items()):
        metric = f"isabelle_mcp_{name}"
        lines.append(f"# TYPE {metric} counter")
        lines.append(f"{metric} {value}")
    return "\n".join(lines) + "\n"
