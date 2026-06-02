"""TCP client speaking I/R's newline-delimited text protocol.

The daemon is spawned by :mod:`isabelle_mcp.ir_daemon`; this module opens an
authenticated connection to it and sends ML command strings (``Ir.init`` /
``Ir.step`` / ``Ir.fork`` / ``Ir.back`` / ``Ir.state`` / ``Ir.text`` /
``Ir.remove``), parsing the plain-text responses. See
``docs/ir-protocol-notes.md`` for the wire protocol.

``IRDaemonHandle`` and ``launch_ir_daemon`` are re-exported here for backward
compatibility with existing call sites.
"""

from __future__ import annotations

import contextlib
import logging
import re
import socket
from collections.abc import Iterator
from typing import Any

from isabelle_mcp.ir_daemon import IRDaemonHandle, launch_ir_daemon

logger = logging.getLogger(__name__)

__all__ = ["IRDaemonHandle", "IRSession", "launch_ir_daemon", "proof_closed"]

_SENTINEL = "<<DONE>>"


def _ml_escape(text: str) -> str:
    """Escape a Python string for inclusion in an SML string literal.

    Only ``\\`` and ``"`` need escaping for our purposes. Isabelle symbol
    names like ``\\<and>`` are sent literally (no special handling).
    """
    return text.replace("\\", "\\\\").replace('"', '\\"')


def _ml_int(n: int) -> str:
    """Render a Python int as an SML integer literal (negatives use ``~``)."""
    return f"~{abs(n)}" if n < 0 else str(n)


class IRSession:
    """One TCP connection to a running I/R daemon, post-authentication."""

    def __init__(self, sock: socket.socket) -> None:
        self._sock = sock
        self._buf = b""

    @classmethod
    @contextlib.contextmanager
    def connect(cls, handle: IRDaemonHandle) -> Iterator["IRSession"]:
        """Open a TCP connection, perform the auth handshake, yield session.

        Cleans up the socket on exit (shutdown + close). The caller is
        still responsible for terminating the daemon.
        """
        sock = socket.create_connection(("127.0.0.1", handle.port), timeout=30.0)
        try:
            sock.sendall((handle.auth_token + "\n").encode("utf-8"))
            session = cls(sock)
            ack = session._readline(timeout_seconds=10.0)
            if ack.rstrip("\n") != "OK":
                raise RuntimeError(
                    f"I/R auth failed; expected 'OK', got {ack!r}"
                )
            yield session
        finally:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            sock.close()

    # --- low-level I/O -------------------------------------------------------

    def _readline(self, timeout_seconds: float = 30.0) -> str:
        """Read one ``\\n``-terminated line from the socket."""
        self._sock.settimeout(timeout_seconds)
        while b"\n" not in self._buf:
            chunk = self._sock.recv(65536)
            if not chunk:
                raise ConnectionError("I/R closed the connection unexpectedly")
            self._buf += chunk
        line, _, rest = self._buf.partition(b"\n")
        self._buf = rest
        return (line + b"\n").decode("utf-8", errors="replace")

    def _send_command(self, cmd: str) -> None:
        """Send one ML command terminated with a newline."""
        data = (cmd + "\n").encode("utf-8")
        logger.debug("ir send: %s", cmd)
        self._sock.sendall(data)

    def _read_response(self, timeout_seconds: float = 30.0) -> dict[str, Any]:
        """Read lines until the ``<<DONE>>`` sentinel; return parsed envelope.

        Envelope shape: ``{"ok": bool, "body": str}``.
        On error (server-prefix ``ERR``), ok=False and body strips the ``ERR``
        prefix line but keeps subsequent error text.
        """
        lines: list[str] = []
        while True:
            line = self._readline(timeout_seconds=timeout_seconds).rstrip("\n")
            if line == _SENTINEL:
                break
            lines.append(line)
        if lines and lines[0] == "ERR":
            return {"ok": False, "body": "\n".join(lines[1:])}
        return {"ok": True, "body": "\n".join(lines)}

    # --- public commands -----------------------------------------------------

    def init(self, *, repl_id: str, theories: list[str]) -> str:
        """Open a new REPL.

        Args:
            repl_id: chosen identifier for the REPL.
            theories: non-empty list of theory names. In an HOL session,
                use ``["Main"]`` for plain HOL.

        Returns the repl_id on success; raises RuntimeError on failure.
        """
        if not theories:
            raise ValueError("theories must be non-empty")
        theories_lit = "[" + ", ".join(f'"{_ml_escape(t)}"' for t in theories) + "]"
        cmd = f'Ir.init "{_ml_escape(repl_id)}" {theories_lit};'
        self._send_command(cmd)
        envelope = self._read_response(timeout_seconds=60.0)
        if not envelope["ok"]:
            raise RuntimeError(f"Ir.init failed: {envelope['body']!r}")
        return repl_id

    def step(
        self,
        repl_id: str,
        *,
        isar: str,
        timeout_seconds: float = 60.0,
    ) -> dict[str, Any]:
        """Send one Isar step to the named REPL.

        Returns the response envelope. Does NOT raise on tactic failure —
        the caller inspects ``envelope["ok"]`` and/or ``envelope["body"]``.
        """
        cmd = f'Ir.step "{_ml_escape(repl_id)}" "{_ml_escape(isar)}";'
        self._send_command(cmd)
        return self._read_response(timeout_seconds=timeout_seconds)

    def remove(self, repl_id: str) -> None:
        """Destroy the named REPL on the daemon.

        Tolerant of socket already being half-closed by the daemon.
        """
        cmd = f'Ir.remove "{_ml_escape(repl_id)}";'
        try:
            self._send_command(cmd)
            envelope = self._read_response(timeout_seconds=10.0)
            if not envelope["ok"]:
                logger.warning("Ir.remove returned error: %r", envelope["body"])
        except (ConnectionError, socket.timeout, BrokenPipeError):
            # Daemon may have closed already; that's fine for cleanup.
            pass

    def fork(
        self,
        parent_id: str,
        new_id: str,
        *,
        state_idx: int = -1,
        timeout_seconds: float = 30.0,
    ) -> dict[str, Any]:
        """Fork ``parent_id`` at ``state_idx`` into a new REPL ``new_id``.

        ``state_idx`` follows I/R semantics: ``-1`` (default) forks at the
        parent's current/latest state. Returns the response envelope.
        """
        cmd = (
            f'Ir.fork "{_ml_escape(parent_id)}" "{_ml_escape(new_id)}" '
            f"{_ml_int(state_idx)};"
        )
        self._send_command(cmd)
        return self._read_response(timeout_seconds=timeout_seconds)

    def undo(
        self, repl_id: str, *, n: int = 1, timeout_seconds: float = 30.0
    ) -> dict[str, Any]:
        """Undo the last ``n`` steps via ``Ir.back`` (one step at a time).

        Returns the last response envelope. ``Ir.back`` is ``Ir.truncate id ~1``;
        repeating it drops one step per call.
        """
        if n < 1:
            raise ValueError("n must be >= 1")
        envelope: dict[str, Any] = {"ok": True, "body": ""}
        for _ in range(n):
            self._send_command(f'Ir.back "{_ml_escape(repl_id)}";')
            envelope = self._read_response(timeout_seconds=timeout_seconds)
            if not envelope["ok"]:
                break
        return envelope

    def state(
        self, repl_id: str, *, state_idx: int = -1, timeout_seconds: float = 30.0
    ) -> dict[str, Any]:
        """Return the pretty-printed proof state at ``state_idx`` (default current)."""
        cmd = f'Ir.state "{_ml_escape(repl_id)}" {_ml_int(state_idx)};'
        self._send_command(cmd)
        return self._read_response(timeout_seconds=timeout_seconds)

    def history(self, repl_id: str, *, timeout_seconds: float = 30.0) -> list[str]:
        """Return the Isar step texts of the REPL, oldest first.

        ``Ir.text`` returns the steps joined by newlines; an empty REPL yields
        an empty list.
        """
        self._send_command(f'Ir.text "{_ml_escape(repl_id)}";')
        envelope = self._read_response(timeout_seconds=timeout_seconds)
        if not envelope["ok"]:
            raise RuntimeError(f"Ir.text failed: {envelope['body']!r}")
        body = envelope["body"].strip("\n")
        if not body:
            return []
        # Drop the trailing "[timing] Ns" line if present.
        lines = [ln for ln in body.split("\n") if not ln.startswith("[timing]")]
        return [ln for ln in lines if ln != ""]


# -----------------------------------------------------------------------------
# Response interpretation helpers.
# -----------------------------------------------------------------------------

# Remaining goals are printed by Isabelle as e.g. "goal (1 subgoal):".
_REMAINING_GOALS_RE = re.compile(r"goal \(\d+ subgoal")
# A finished proof returns to the theory toplevel, printed as "theorem name: ...".
_THEOREM_TOPLEVEL_RE = re.compile(r"^theorem\b", re.MULTILINE)


def proof_closed(response: dict[str, Any]) -> bool:
    """Decide whether an :meth:`IRSession.step` response closed the proof.

    I/R's TCP protocol is plain text (no machine-readable goal count), so we
    inspect the rendered proof state. A proof is closed when the step
    succeeded, no remaining subgoals are printed, and the prover has returned
    to the theory toplevel (a ``theorem ...`` line). Verified empirically
    against Isabelle2025-2; see ``docs/ir-protocol-notes.md``.
    """
    if not response.get("ok"):
        return False
    body = response.get("body", "")
    if _REMAINING_GOALS_RE.search(body):
        return False
    return bool(_THEOREM_TOPLEVEL_RE.search(body))
