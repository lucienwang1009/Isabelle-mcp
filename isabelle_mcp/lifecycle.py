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
import math
import os
import secrets
import threading
import time
from collections.abc import Iterator
from pathlib import Path

from isabelle_mcp import metrics, parsing
from isabelle_mcp.errors import ToolError, clamp_timeout, map_ir_error
from isabelle_mcp.ir_client import IRSession, proof_closed
from isabelle_mcp.ir_daemon import IRDaemonHandle, launch_ir_daemon
from isabelle_mcp.lifecycle_ops import AutomationMixin, FileOpsMixin
from isabelle_mcp.safety import looks_multi_command, validate_isar_safe
from isabelle_mcp.textutil import strip_timing as _strip_timing
from isabelle_mcp.textutil import truncate as _truncate
from isabelle_mcp.textutil import state_at_end_of_proof as _state_at_end_of_proof

logger = logging.getLogger(__name__)

__all__ = ["IRManager"]

# Cap the step history returned by `state` so long proofs don't dump everything;
# the most recent steps are the relevant ones.
_HISTORY_CAP = 50


class IRManager(AutomationMixin, FileOpsMixin):
    """Owns the I/R daemon and maps opaque repl_ids to internal handles.

    Layer C automation and Layer A file/orchestration operations are provided by
    :class:`AutomationMixin` / :class:`FileOpsMixin` (see ``lifecycle_ops``).
    """

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
        self._session_dir: Path | None = None
        self._port = port
        self._bash_server = bash_server
        self._startup_timeout = startup_timeout_seconds
        self._handle: IRDaemonHandle | None = None
        self._registry: dict[str, str] = {}  # opaque uuid -> internal id
        self._last_access: dict[str, float] = {}  # opaque uuid -> monotonic ts
        self._pending_server_event: str | None = None
        self._lock = threading.Lock()
        ttl_raw = os.environ.get("ISABELLE_MCP_REPL_TTL_S", "1800")
        try:
            self._ttl = float(ttl_raw)
        except ValueError:
            self._ttl = 1800.0
        self._reaper_stop = threading.Event()
        self._reaper_thread: threading.Thread | None = None

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
                session_dir=self._session_dir,
            )
        self._start_reaper()

    def ensure_session(self, session: str, session_dir: Path | None) -> None:
        """Ensure the daemon runs ``session`` (with ``session_dir`` on its path).

        The daemon hosts a single session image, so opening a REPL on a different
        session relaunches it — invalidating existing repl_ids (a server_event is
        flagged). A no-op when the daemon already runs the requested session, so
        the common ``open_repl(theory=...)`` path is unaffected.
        """
        with self._lock:
            same = (
                self._handle is not None
                and self._handle.process.poll() is None
                and self._session_name == session
                and self._session_dir == session_dir
            )
        if same:
            return
        self._relaunch_session(session, session_dir)

    def _relaunch_session(self, session: str, session_dir: Path | None) -> None:
        """Terminate the current daemon and start one on the requested session."""
        with self._lock:
            handle, self._handle = self._handle, None
            self._registry.clear()
            self._last_access.clear()
            old_session_name = self._session_name
            old_session_dir = self._session_dir
            self._session_name = session
            self._session_dir = session_dir
            self._pending_server_event = "ir_session_changed"
        if handle is not None:
            logger.info("switching I/R session to %s (dir=%s)", session, session_dir)
            handle.terminate()
        try:
            self.start()
        except Exception:
            with self._lock:
                self._session_name = old_session_name
                self._session_dir = old_session_dir
            raise

    def close(self) -> None:
        """Terminate the daemon, stop the reaper, and drop the registry."""
        self._reaper_stop.set()
        reaper = self._reaper_thread
        if reaper is not None and reaper.is_alive():
            reaper.join(timeout=2.0)
        with self._lock:
            handle, self._handle = self._handle, None
            self._registry.clear()
            self._last_access.clear()
        if handle is not None:
            handle.terminate()

    def _ensure_alive(self) -> None:
        """(Re)start the daemon if it is not running; invalidate ids on crash."""
        handle = self._handle
        if handle is not None and handle.process.poll() is None:
            return
        crashed = handle is not None
        with self._lock:
            self._registry.clear()
            self._last_access.clear()
        if crashed:
            metrics.increment("ir_restarts")
            logger.warning("I/R daemon died; restarting and invalidating repl_ids")
            with self._lock:
                self._pending_server_event = "ir_restarted"
        try:
            self.start()
        except Exception as exc:  # noqa: BLE001
            raise self._tool_error(
                "ir_unavailable", f"I/R daemon unavailable: {exc}"
            ) from exc

    def _require_handle(self) -> IRDaemonHandle:
        self._ensure_alive()
        handle = self._handle
        if handle is None or handle.process.poll() is not None:
            raise self._tool_error("ir_unavailable", "I/R daemon is not running")
        return handle

    # --- idle-REPL reaper ----------------------------------------------------

    def _start_reaper(self) -> None:
        if self._ttl <= 0:
            return
        if self._reaper_thread is not None and self._reaper_thread.is_alive():
            return
        self._reaper_stop.clear()
        thread = threading.Thread(
            target=self._reap_loop, name="ir-repl-reaper", daemon=True
        )
        self._reaper_thread = thread
        thread.start()

    def _reap_loop(self) -> None:
        interval = min(60.0, max(1.0, self._ttl / 2))
        while not self._reaper_stop.wait(interval):
            try:
                self._reap_once()
            except Exception:  # noqa: BLE001
                logger.exception("idle-REPL reaper error")

    def _reap_once(self) -> None:
        now = time.monotonic()
        with self._lock:
            stale = [
                uuid
                for uuid, ts in self._last_access.items()
                if now - ts > self._ttl
            ]
        for uuid in stale:
            try:
                self.close_repl(uuid)
                metrics.increment("repls_reaped")
                logger.info("reaped idle repl %s", uuid)
            except ToolError:
                pass

    @contextlib.contextmanager
    def _session(self) -> Iterator[IRSession]:
        """Yield an authenticated session, translating socket errors."""
        handle = self._require_handle()
        try:
            with IRSession.connect(handle) as session:
                yield session
        except OSError as exc:  # includes ConnectionError, socket.timeout
            raise self._tool_error("ir_unavailable", f"cannot reach I/R: {exc}") from exc

    def _resolve(self, repl_id: str) -> str:
        with self._lock:
            internal = self._registry.get(repl_id)
            if internal is not None:
                self._last_access[repl_id] = time.monotonic()
        if internal is None:
            raise self._tool_error("repl_not_found", f"unknown repl_id {repl_id!r}")
        return internal

    def _consume_server_event(self) -> str | None:
        with self._lock:
            event, self._pending_server_event = self._pending_server_event, None
        return event

    def _with_server_event(self, result: dict[str, object]) -> dict[str, object]:
        event = self._consume_server_event()
        if event is not None:
            result["server_event"] = event
        return result

    def _tool_error(
        self, code: str, message: str, *, hint: str | None = None
    ) -> ToolError:
        return ToolError(
            code,
            message,
            hint=hint,
            server_event=self._consume_server_event(),
        )

    # --- Layer B operations --------------------------------------------------

    def open(self, at: dict[str, object]) -> dict[str, object]:
        """Open a REPL at a theory or by forking another REPL.

        ``at`` is ``{"theory": str}`` or ``{"parent_repl_id": str}``; a ``theory``
        open may also carry ``"session"`` / ``"session_dirs"`` to anchor the REPL
        on a locally built session image (relaunching the daemon if needed).
        Returns ``{"repl_id", "goal_summary"?}``.
        """
        requested_session = at.get("session")
        if requested_session is not None and "theory" in at:
            raw_dirs = at.get("session_dirs") or []
            session_dir = (
                Path(str(raw_dirs[0])).expanduser().resolve() if raw_dirs else None
            )
            self.ensure_session(str(requested_session), session_dir)
        new_uuid = secrets.token_hex(8)
        internal = f"mcp_{new_uuid}"
        try:
            with self._session() as session:
                if "parent_repl_id" in at:
                    parent_internal = self._resolve(str(at["parent_repl_id"]))
                    env = session.fork(parent_internal, internal)
                    if not env["ok"]:
                        raise self._tool_error(map_ir_error(env["body"]), env["body"])
                elif "theory" in at:
                    session.init(repl_id=internal, theories=[str(at["theory"])])
                else:
                    raise self._tool_error(
                        "invalid_argument",
                        "`at` must contain 'theory' or 'parent_repl_id'",
                    )
                summary = _strip_timing(session.state(internal).get("body", ""))
        except RuntimeError as exc:
            raise self._tool_error(map_ir_error(str(exc)), str(exc)) from exc

        with self._lock:
            self._registry[new_uuid] = internal
            self._last_access[new_uuid] = time.monotonic()
        metrics.increment("repls_opened")
        result: dict[str, object] = {"repl_id": new_uuid}
        if summary:
            result["goal_summary"] = _truncate(summary)
        return self._with_server_event(result)

    def step(
        self, repl_id: str, isar: str, *, timeout_seconds: float = 60.0
    ) -> dict[str, object]:
        """Run one Isar step. Returns ``{"output", "at_end_of_proof"}``."""
        timeout_seconds = clamp_timeout(timeout_seconds)
        validate_isar_safe(isar)
        internal = self._resolve(repl_id)
        with self._session() as session:
            session._set_step_timeout(internal, math.ceil(timeout_seconds))
            env = session.step(
                internal, isar=isar, timeout_seconds=timeout_seconds + 10.0
            )
        if not env["ok"]:
            code = map_ir_error(env["body"])
            hint: str | None = None
            if code in {"tactic_failed", "parse_error"} and looks_multi_command(isar):
                hint = (
                    "This step submitted multiple Isar commands, so the whole "
                    "block rolled back. Submit one command per isabelle_step so "
                    "the failure localizes and the applied prefix is kept."
                )
            raise self._tool_error(code, env["body"], hint=hint)
        return self._with_server_event({
            "output": _truncate(_strip_timing(env["body"])),
            "at_end_of_proof": proof_closed(env),
        })

    def undo(self, repl_id: str, *, n: int = 1) -> dict[str, object]:
        """Undo the last ``n`` steps. Returns ``{"steps_undone", "current_goal_summary"?}``."""
        if n < 1:
            raise self._tool_error("invalid_argument", "n must be >= 1")
        internal = self._resolve(repl_id)
        with self._session() as session:
            env = session.undo(internal, n=n)
            if not env["ok"]:
                raise self._tool_error(map_ir_error(env["body"]), env["body"])
            summary = _strip_timing(session.state(internal).get("body", ""))
        result: dict[str, object] = {"steps_undone": n}
        if summary:
            result["current_goal_summary"] = _truncate(summary)
        return self._with_server_event(result)

    def state(self, repl_id: str) -> dict[str, object]:
        """Return ``{"history", "current_goals", "at_end_of_proof"}``."""
        internal = self._resolve(repl_id)
        with self._session() as session:
            history = session.history(internal)
            state_env = session.state(internal)
        if len(history) > _HISTORY_CAP:
            omitted = len(history) - _HISTORY_CAP
            history = [f"… ({omitted} earlier step(s) omitted)", *history[-_HISTORY_CAP:]]
        if not state_env["ok"]:
            raise self._tool_error(map_ir_error(state_env["body"]), state_env["body"])
        body = _strip_timing(state_env["body"])
        return self._with_server_event({
            "history": history,
            "current_goals": _truncate(body),
            "goals": parsing.parse_goal_state(body),
            "at_end_of_proof": _state_at_end_of_proof(body),
        })

    def fork(self, repl_id: str) -> dict[str, object]:
        """Fork an existing REPL at its current state. Returns ``{"repl_id"}``."""
        return self.open({"parent_repl_id": repl_id})

    def close_repl(self, repl_id: str) -> dict[str, object]:
        """Remove a REPL (and its descendants) on the daemon."""
        internal = self._resolve(repl_id)
        with self._session() as session:
            session.remove(internal)
        with self._lock:
            self._registry.pop(repl_id, None)
            self._last_access.pop(repl_id, None)
        return self._with_server_event({})
