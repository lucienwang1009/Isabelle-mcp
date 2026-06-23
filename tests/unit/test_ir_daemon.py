"""Unit tests for I/R daemon port selection (no Isabelle required)."""

from __future__ import annotations

import socket

import pytest

from isabelle_mcp import ir_daemon
from isabelle_mcp.ir_daemon import (
    _DEFAULT_PORT,
    _find_free_port,
    _port_in_use,
    _resolve_port,
)


def test_find_free_port_is_actually_free() -> None:
    port = _find_free_port()
    assert isinstance(port, int) and 0 < port < 65536
    assert not _port_in_use(port)


def test_port_in_use_detects_listener() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as srv:
        srv.bind(("127.0.0.1", 0))
        srv.listen(1)
        port = srv.getsockname()[1]
        assert _port_in_use(port) is True
    # Socket closed -> no longer in use.
    assert _port_in_use(port) is False


def test_resolve_port_uses_default_when_free(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ir_daemon, "_port_in_use", lambda _p: False)
    assert _resolve_port(None) == _DEFAULT_PORT


def test_resolve_port_falls_back_when_default_busy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(ir_daemon, "_port_in_use", lambda _p: True)
    monkeypatch.setattr(ir_daemon, "_find_free_port", lambda: 54321)
    # No explicit port -> transparently recover from a stale daemon on the default.
    assert _resolve_port(None) == 54321


def test_resolve_port_explicit_busy_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ir_daemon, "_port_in_use", lambda _p: True)
    with pytest.raises(RuntimeError) as exc:
        _resolve_port(9999)
    assert "9999" in str(exc.value)


def test_resolve_port_explicit_free_returns_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(ir_daemon, "_port_in_use", lambda _p: False)
    assert _resolve_port(9999) == 9999
