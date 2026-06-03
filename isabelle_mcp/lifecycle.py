"""IRManager — owns the I/R daemon and the opaque ``repl_id`` registry.

The MCP layer never sees I/R's internal repl handles. ``IRManager`` issues an
opaque UUID for each REPL and maps it to an internal ``mcp_<hex>`` id that it
uses when talking to the daemon (design spec §4: ``repl_id`` is a server UUID).

Each operation opens a short-lived authenticated :class:`IRSession`. All proof
state lives daemon-side keyed by the internal id, so per-call connections are
correct and avoid sharing a socket across threads.

Layer B operations return plain success payload dicts and raise
:class:`ToolError` on mapped failures; the tool layer wraps these in envelopes.
"""

from __future__ import annotations

import contextlib
import logging
import os
import secrets
import threading
from collections.abc import Iterator
from pathlib import Path

from isabelle_mcp.errors import ToolError, map_ir_error
from isabelle_mcp.ir_client import IRSession, proof_closed
from isabelle_mcp.ir_daemon import IRDaemonHandle, launch_ir_daemon

logger = logging.getLogger(__name__)

__all__ = ["IRManager"]

_DEFAULT_MAX_PREVIEW_CHARS = 4000


def _max_preview_chars() -> int:
    raw = os.environ.get("ISABELLE_MCP_MAX_PREVIEW_CHARS")
    if raw:
        try:
            return max(0, int(raw))
        except ValueError:
            logger.warning("invalid ISABELLE_MCP_MAX_PREVIEW_CHARS=%r; using default", raw)
    return _DEFAULT_MAX_PREVIEW_CHARS


def _strip_timing(body: str) -> str:
    """Drop I/R's trailing ``[timing] Ns`` lines from a response body."""
    lines = [ln for ln in body.split("\n") if not ln.startswith("[timing]")]
    return "\n".join(lines).rstrip("\n")


def _truncate(text: str) -> str:
    limit = _max_preview_chars()
    if limit and len(text) > limit:
        return text[:limit] + "\n… [truncated; use isabelle_state for full output]"
    return text


def _state_at_end_of_proof(body: str) -> bool:
    """True when a state body shows no open proof (no remaining goals)."""
    if "subgoal" in body and "goal (" in body:
        return False
    return not body.lstrip().startswith("proof (")


class IRManager:
    """Owns the I/R daemon and maps opaque repl_ids to internal handles."""

    def __init__(
        self,
        *,
        isabelle_bin: str,
        ir_dir: Path,
        session: str = "HOL",
        port: int | None = None,
        bash_server: bool = True,
        startup_timeout_seconds: float = 120.0,
    ) -> None:
        self._isabelle_bin = isabelle_bin
        self._ir_dir = ir_dir
        self._session_name = session
        self._port = port
        self._bash_server = bash_server
        self._startup_timeout = startup_timeout_seconds
        self._handle: IRDaemonHandle | None = None
        self._registry: dict[str, str] = {}  # opaque uuid -> internal id
        self._lock = threading.Lock()

    # --- daemon lifecycle ----------------------------------------------------

    def start(self) -> None:
        """Launch the I/R daemon if not already running (idempotent)."""
        with self._lock:
            if self._handle is not None and self._handle.process.poll() is None:
                return
            logger.info("starting I/R daemon (session=%s)", self._session_name)
            self._handle = launch_ir_daemon(
                isabelle_bin=self._isabelle_bin,
                ir_dir=self._ir_dir,
                session=self._session_name,
                port=self._port,
                bash_server=self._bash_server,
                startup_timeout_seconds=self._startup_timeout,
            )

    def close(self) -> None:
        """Terminate the daemon and drop the registry."""
        with self._lock:
            handle, self._handle = self._handle, None
            self._registry.clear()
        if handle is not None:
            handle.terminate()

    def _require_handle(self) -> IRDaemonHandle:
        handle = self._handle
        if handle is None or handle.process.poll() is not None:
            raise ToolError("ir_unavailable", "I/R daemon is not running")
        return handle

    @contextlib.contextmanager
    def _session(self) -> Iterator[IRSession]:
        """Yield an authenticated session, translating socket errors."""
        handle = self._require_handle()
        try:
            with IRSession.connect(handle) as session:
                yield session
        except OSError as exc:  # includes ConnectionError, socket.timeout
            raise ToolError("ir_unavailable", f"cannot reach I/R: {exc}") from exc

    def _resolve(self, repl_id: str) -> str:
        with self._lock:
            internal = self._registry.get(repl_id)
        if internal is None:
            raise ToolError("repl_not_found", f"unknown repl_id {repl_id!r}")
        return internal

    # --- Layer B operations --------------------------------------------------

    def open(self, at: dict[str, object]) -> dict[str, object]:
        """Open a REPL at a theory or by forking another REPL.

        ``at`` is ``{"theory": str}`` or ``{"parent_repl_id": str}``.
        Returns ``{"repl_id", "goal_summary"?}``.
        """
        new_uuid = secrets.token_hex(8)
        internal = f"mcp_{new_uuid}"
        try:
            with self._session() as session:
                if "parent_repl_id" in at:
                    parent_internal = self._resolve(str(at["parent_repl_id"]))
                    env = session.fork(parent_internal, internal)
                    if not env["ok"]:
                        raise ToolError(map_ir_error(env["body"]), env["body"])
                elif "theory" in at:
                    session.init(repl_id=internal, theories=[str(at["theory"])])
                else:
                    raise ToolError(
                        "invalid_argument",
                        "`at` must contain 'theory' or 'parent_repl_id'",
                    )
                summary = _strip_timing(session.state(internal).get("body", ""))
        except RuntimeError as exc:
            raise ToolError(map_ir_error(str(exc)), str(exc)) from exc

        with self._lock:
            self._registry[new_uuid] = internal
        result: dict[str, object] = {"repl_id": new_uuid}
        if summary:
            result["goal_summary"] = _truncate(summary)
        return result

    def step(
        self, repl_id: str, isar: str, *, timeout_seconds: float = 60.0
    ) -> dict[str, object]:
        """Run one Isar step. Returns ``{"output", "at_end_of_proof"}``."""
        internal = self._resolve(repl_id)
        with self._session() as session:
            env = session.step(internal, isar=isar, timeout_seconds=timeout_seconds)
        if not env["ok"]:
            raise ToolError(map_ir_error(env["body"]), env["body"])
        return {
            "output": _truncate(_strip_timing(env["body"])),
            "at_end_of_proof": proof_closed(env),
        }

    def undo(self, repl_id: str, *, n: int = 1) -> dict[str, object]:
        """Undo the last ``n`` steps. Returns ``{"steps_undone", "current_goal_summary"?}``."""
        if n < 1:
            raise ToolError("invalid_argument", "n must be >= 1")
        internal = self._resolve(repl_id)
        with self._session() as session:
            env = session.undo(internal, n=n)
            if not env["ok"]:
                raise ToolError(map_ir_error(env["body"]), env["body"])
            summary = _strip_timing(session.state(internal).get("body", ""))
        result: dict[str, object] = {"steps_undone": n}
        if summary:
            result["current_goal_summary"] = _truncate(summary)
        return result

    def state(self, repl_id: str) -> dict[str, object]:
        """Return ``{"history", "current_goals", "at_end_of_proof"}``."""
        internal = self._resolve(repl_id)
        with self._session() as session:
            history = session.history(internal)
            state_env = session.state(internal)
        if not state_env["ok"]:
            raise ToolError(map_ir_error(state_env["body"]), state_env["body"])
        body = _strip_timing(state_env["body"])
        return {
            "history": history,
            "current_goals": _truncate(body),
            "at_end_of_proof": _state_at_end_of_proof(body),
        }

    def fork(self, repl_id: str) -> dict[str, object]:
        """Fork an existing REPL at its current state. Returns ``{"repl_id"}``."""
        return {"repl_id": self.open({"parent_repl_id": repl_id})["repl_id"]}

    def close_repl(self, repl_id: str) -> dict[str, object]:
        """Remove a REPL (and its descendants) on the daemon."""
        internal = self._resolve(repl_id)
        with self._session() as session:
            session.remove(internal)
        with self._lock:
            self._registry.pop(repl_id, None)
        return {}
