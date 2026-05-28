"""Client for the vendored I/R daemon: spawn, capture token from stdout, lifecycle.

M0 scope: launching + TCP-readiness check + token capture only. Protocol
helpers (init/step/Ir.remove) arrive in Task 7.
"""

from __future__ import annotations

import dataclasses
import logging
import os
import re
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

logger = logging.getLogger(__name__)

__all__ = ["IRDaemonHandle", "launch_ir_daemon"]

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
) -> str:
    """Scan the process's stdout for `IR_Repl.token: <token>`.

    Drains stdout into the logger after the token is found so the pipe
    never blocks the daemon.

    Returns the captured token. Raises TimeoutError if not seen in time.
    """
    deadline = time.monotonic() + timeout_seconds
    token: str | None = None
    captured_lines: list[str] = []

    assert process.stdout is not None, "subprocess must be spawned with stdout=PIPE"

    while time.monotonic() < deadline:
        # readline() blocks until a newline or EOF; check we're not past deadline often.
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
    return token


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

    try:
        token = _read_token_from_stdout(process, startup_timeout_seconds)
        _wait_for_listener(chosen_port, startup_timeout_seconds)
    except Exception:
        # Capture diagnostic output before tearing down.
        try:
            stderr_tail = ""
            if process.stderr is not None:
                # Non-blocking-ish stderr drain (best effort)
                process.terminate()
                try:
                    _, stderr_data = process.communicate(timeout=3.0)
                except subprocess.TimeoutExpired:
                    process.kill()
                    _, stderr_data = process.communicate()
                stderr_tail = stderr_data or ""
            logger.error("I/R startup failed.\nstderr:\n%s", stderr_tail)
        except Exception:
            pass
        raise

    return IRDaemonHandle(
        process=process,
        port=chosen_port,
        auth_token=token,
        workdir=ir_dir,
    )
