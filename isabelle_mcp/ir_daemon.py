"""Spawn and supervise the vendored I/R daemon over loopback TCP.

Responsibilities: launch ``repl.py`` as a subprocess, capture its auth token
from stdout, wait for the TCP listener, and expose a handle for clean teardown.
The request/response protocol lives in :mod:`isabelle_mcp.ir_client`.
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

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows fallback
    fcntl = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

__all__ = ["IRDaemonHandle", "launch_ir_daemon"]

# `IR_Repl.token: <token>` printed by repl.py:2456 (no ANSI codes).
_TOKEN_RE = re.compile(r"^IR_Repl\.token:\s*(\S+)\s*$")

# Default port we try first for stable local debugging. Multi-process MCP
# startup is serialized by `_port_launch_lock`, so fallback selection is not
# racing other isabelle-mcp instances.
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


def _port_in_use(port: int) -> bool:
    """True if something is already accepting connections on 127.0.0.1:port.

    A stale I/R daemon from a previous run typically still holds the pinned
    port; binding over it is what produced the opaque "exited before printing
    the auth token" failures.
    """
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.5):
            return True
    except OSError:
        return False


def _find_free_port() -> int:
    """Ask the OS for an unused loopback TCP port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _resolve_port(port: int | None) -> int:
    """Choose the port to launch on, recovering from a busy default.

    If ``port`` is given explicitly (``ISABELLE_MCP_PORT``) and it is busy, we
    fail loudly with the remedy. If we are on the default port and it is busy
    (a stale daemon, or another concurrently-started MCP server), we
    transparently fall back to a free port. This runs under `_port_launch_lock`
    during real startup, so the free-port check remains valid until repl.py has
    bound the listener.
    """
    explicit = port is not None and port != 0
    chosen = port if explicit else _DEFAULT_PORT
    if not _port_in_use(chosen):
        return chosen
    if explicit:
        raise RuntimeError(
            f"configured I/R port {chosen} is already in use (a stale daemon?). "
            f"Free it (e.g. `lsof -nP -iTCP:{chosen}` then kill the PID) or set "
            "ISABELLE_MCP_PORT to a free port."
        )
    free = _find_free_port()
    logger.warning(
        "default I/R port %d is busy (stale daemon?); falling back to free port %d",
        chosen,
        free,
    )
    return free


def _port_lock_path() -> Path:
    raw = os.environ.get("ISABELLE_MCP_PORT_LOCK")
    if raw:
        return Path(raw).expanduser()
    return Path.home() / ".cache" / "isabelle-mcp" / "ir-port.lock"


@contextlib.contextmanager
def _port_launch_lock() -> Iterator[None]:
    """Serialize local port selection across concurrently-started MCP servers."""
    lock_path = _port_lock_path()
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("w", encoding="utf-8") as lock_file:
        if fcntl is None:
            yield
            return
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


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
    bash_server: bool = False,
    startup_timeout_seconds: float = 90.0,
    session_dir: Path | None = None,
) -> IRDaemonHandle:
    """Spawn I/R as a subprocess and wait until its TCP listener is up.

    Caller is responsible for calling `.terminate()` on the returned handle.

    The token is captured by line-scanning the daemon's stdout for the
    `IR_Repl.token: <token>` announcement (see docs/ir-protocol-notes.md).
    Port is passed explicitly via `--port` to avoid dynamic-port parsing.

    ``bash_server`` enables I/R's Bash.Server, required by sledgehammer's
    external ATPs (Layer C / M2). It is off by default to keep startup fast.
    """
    repl_script = ir_dir / "repl.py"
    if not repl_script.is_file():
        raise FileNotFoundError(f"missing I/R entry point: {repl_script}")

    env = os.environ.copy()

    with _port_launch_lock():
        chosen_port = _resolve_port(port)

        cmd: list[str] = [
            sys.executable,
            "-u",
            str(repl_script),
            "--isabelle",
            isabelle_bin,
            "--session",
            session,
            "--port",
            str(chosen_port),
            "--server-only",
        ]
        if session_dir is not None:
            cmd.extend(["--dir", str(session_dir)])
        if not bash_server:
            cmd.append("--no-bash-server")

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
