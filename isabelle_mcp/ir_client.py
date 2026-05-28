"""Client for the vendored I/R daemon: spawn, capture token from stdout, lifecycle.

M0 scope: launching + TCP-readiness check + token capture only. Protocol
helpers (init/step/Ir.remove) arrive in Task 7.
"""

from __future__ import annotations

import contextlib
import dataclasses
import logging
import os
import re
import selectors
import socket
import subprocess
import sys
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

__all__ = ["IRDaemonHandle", "IRSession", "launch_ir_daemon"]

# `IR_Repl.token: <token>` printed by repl.py:2456 (no ANSI codes).
_TOKEN_RE = re.compile(r"^IR_Repl\.token:\s*(\S+)\s*$")

# Default port we pin via `--port 9147` to avoid dynamic-port discovery
# (the announcement line includes ANSI escapes — see docs/ir-protocol-notes.md).
_DEFAULT_PORT = 9147


@dataclasses.dataclass
class IRDaemonHandle:
    """Bundle of state for a running I/R subprocess."""

    process: subprocess.Popen[str]
    port: int
    auth_token: str
    workdir: Path
    _stdout_drain: threading.Thread | None = None
    _stderr_drain: threading.Thread | None = None

    def terminate(self, grace_seconds: float = 5.0) -> None:
        """Stop the daemon; SIGTERM first, then SIGKILL after grace."""
        if self.process.poll() is not None:
            return
        self.process.terminate()
        try:
            self.process.wait(timeout=grace_seconds)
        except subprocess.TimeoutExpired:
            logger.warning("I/R did not exit on SIGTERM; sending SIGKILL")
            self.process.kill()
            self.process.wait(timeout=grace_seconds)
        # Join drain threads so any final log lines are flushed before we return.
        for thread in (self._stdout_drain, self._stderr_drain):
            if thread is not None and thread.is_alive():
                thread.join(timeout=2.0)


def _wait_for_listener(port: int, timeout_seconds: float) -> None:
    """Block until something accepts connections on 127.0.0.1:port, or fail."""
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1.0):
                return
        except OSError as exc:
            last_error = exc
            time.sleep(0.25)
    raise TimeoutError(
        f"I/R did not start listening on 127.0.0.1:{port} "
        f"within {timeout_seconds:.1f}s; last error: {last_error!r}"
    )


def _read_token_from_stdout(
    process: subprocess.Popen[str], timeout_seconds: float
) -> tuple[str, threading.Thread]:
    """Scan the process's stdout for `IR_Repl.token: <token>`.

    Returns (token, drain_thread). The drain_thread continues reading
    stdout into the logger after the token is captured so the pipe never
    blocks the daemon. Caller should join the drain thread before
    process teardown if it needs deterministic log ordering.

    Raises TimeoutError if not seen in time.
    """
    deadline = time.monotonic() + timeout_seconds
    token: str | None = None
    captured_lines: list[str] = []

    assert process.stdout is not None, "subprocess must be spawned with stdout=PIPE"

    sel = selectors.DefaultSelector()
    sel.register(process.stdout, selectors.EVENT_READ)
    try:
        while time.monotonic() < deadline:
            remaining = max(deadline - time.monotonic(), 0.0)
            poll_timeout = min(remaining, 1.0)
            ready = sel.select(timeout=poll_timeout)
            if not ready:
                continue  # Loop back to check deadline
            line = process.stdout.readline()
            if line == "":
                # EOF — process exited
                raise RuntimeError(
                    "I/R subprocess exited before printing the auth token. "
                    f"Captured stdout so far: {''.join(captured_lines)!r}"
                )
            captured_lines.append(line)
            logger.debug("ir stdout: %s", line.rstrip())
            m = _TOKEN_RE.match(line)
            if m:
                token = m.group(1)
                break
    finally:
        sel.close()

    if token is None:
        raise TimeoutError(
            f"I/R did not print `IR_Repl.token: ...` within {timeout_seconds:.1f}s. "
            f"Captured stdout: {''.join(captured_lines)!r}"
        )

    # Spawn a background thread to keep draining stdout, otherwise the daemon
    # will eventually block on a full pipe.
    def _drain() -> None:
        try:
            for tail_line in process.stdout:  # type: ignore[union-attr]
                logger.debug("ir stdout: %s", tail_line.rstrip())
        except Exception:
            pass

    drain_thread = threading.Thread(target=_drain, name="ir-stdout-drain", daemon=True)
    drain_thread.start()
    return token, drain_thread


def _drain_stderr(process: subprocess.Popen[str]) -> threading.Thread:
    """Spawn a daemon thread that drains process.stderr into the logger."""
    assert process.stderr is not None, "subprocess must be spawned with stderr=PIPE"

    def _drain() -> None:
        try:
            assert process.stderr is not None
            for line in process.stderr:
                logger.debug("ir stderr: %s", line.rstrip())
        except Exception:
            pass

    thread = threading.Thread(target=_drain, name="ir-stderr-drain", daemon=True)
    thread.start()
    return thread


def launch_ir_daemon(
    *,
    isabelle_bin: str,
    ir_dir: Path,
    session: str = "HOL",
    port: int | None = None,
    startup_timeout_seconds: float = 90.0,
) -> IRDaemonHandle:
    """Spawn I/R as a subprocess and wait until its TCP listener is up.

    Caller is responsible for calling `.terminate()` on the returned handle.

    The token is captured by line-scanning the daemon's stdout for the
    `IR_Repl.token: <token>` announcement (see docs/ir-protocol-notes.md).
    Port is passed explicitly via `--port` to avoid dynamic-port parsing.
    """
    repl_script = ir_dir / "repl.py"
    if not repl_script.is_file():
        raise FileNotFoundError(f"missing I/R entry point: {repl_script}")

    chosen_port = port if port is not None else _DEFAULT_PORT

    env = os.environ.copy()

    cmd: list[str] = [
        sys.executable,
        str(repl_script),
        "--isabelle",
        isabelle_bin,
        "--session",
        session,
        "--port",
        str(chosen_port),
        "--server-only",
        "--no-bash-server",
    ]

    logger.info("launching I/R: %s", " ".join(cmd))
    process = subprocess.Popen(
        cmd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,  # line-buffered, important for readline() loop
        cwd=str(ir_dir),
    )

    drain_thread: threading.Thread | None = None
    try:
        token, drain_thread = _read_token_from_stdout(process, startup_timeout_seconds)
        _wait_for_listener(chosen_port, startup_timeout_seconds)
    except Exception:
        # Terminate first so all pipes drain to EOF, then collect output.
        try:
            process.terminate()
        except OSError:
            pass
        # Let the drain thread observe EOF and exit gracefully.
        if drain_thread is not None:
            drain_thread.join(timeout=5.0)
        # Drain remaining stderr only — stdout was owned by drain_thread.
        stderr_data = ""
        try:
            if process.stderr is not None:
                stderr_data = process.stderr.read() or ""
        except Exception:
            pass
        if process.poll() is None:
            try:
                process.wait(timeout=3.0)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3.0)
        logger.error("I/R startup failed.\nstderr:\n%s", stderr_data)
        raise

    stderr_drain_thread = _drain_stderr(process)

    return IRDaemonHandle(
        process=process,
        port=chosen_port,
        auth_token=token,
        workdir=ir_dir,
        _stdout_drain=drain_thread,
        _stderr_drain=stderr_drain_thread,
    )


# -----------------------------------------------------------------------------
# IRSession — TCP client speaking I/R's newline-delimited text protocol.
# -----------------------------------------------------------------------------

_SENTINEL = "<<DONE>>"


def _ml_escape(text: str) -> str:
    """Escape a Python string for inclusion in an SML string literal.

    Only ``\\`` and ``"`` need escaping for our purposes. Isabelle symbol
    names like ``\\<and>`` are sent literally (no special handling).
    """
    return text.replace("\\", "\\\\").replace('"', '\\"')


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
