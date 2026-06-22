"""Unit tests for diagnostic-step cleanup in the I/R client."""

from __future__ import annotations

from types import MethodType
from typing import Any

from isabelle_mcp.ir_client import IRSession


def _session_with_histories(histories: list[list[str]]) -> tuple[IRSession, list[str]]:
    session = IRSession.__new__(IRSession)
    sent: list[str] = []

    def history(self: IRSession, repl_id: str, timeout_seconds: float = 30.0) -> list[str]:
        return histories.pop(0)

    def set_timeout(self: IRSession, repl_id: str, secs: int) -> None:
        sent.append(f"timeout:{secs}")

    def step(
        self: IRSession,
        repl_id: str,
        *,
        isar: str,
        timeout_seconds: float = 60.0,
    ) -> dict[str, Any]:
        sent.append(f"step:{isar}")
        return {"ok": True, "body": "Try this: by simp"}

    def send(self: IRSession, cmd: str) -> None:
        sent.append(cmd)

    def read(self: IRSession, timeout_seconds: float = 30.0) -> dict[str, Any]:
        return {"ok": True, "body": "Truncated"}

    session.history = MethodType(history, session)
    session._set_step_timeout = MethodType(set_timeout, session)
    session.step = MethodType(step, session)
    session._send_command = MethodType(send, session)
    session._read_response = MethodType(read, session)
    return session, sent


def test_run_diagnostic_undos_only_when_history_grows() -> None:
    session, sent = _session_with_histories([["lemma"], ["lemma", "try0"]])

    env = session.run_diagnostic("R", command="try0", timeout_secs=5)

    assert env["ok"] is True
    assert 'Ir.back "R";' in sent


def test_run_diagnostic_does_not_blindly_back_on_unchanged_history() -> None:
    session, sent = _session_with_histories([["lemma"], ["lemma"]])

    session.run_diagnostic("R", command="try0", timeout_secs=5)

    assert 'Ir.back "R";' not in sent
