"""Layer C (automation) and Layer A (file/orchestration) operation mixins.

These are mixed into :class:`~isabelle_mcp.lifecycle.IRManager`; they rely on the
host providing ``_resolve``, ``_session`` (a context manager yielding an
``IRSession``), and the daemon lifecycle. Kept separate to keep each module
within the project's file-size limit.
"""

from __future__ import annotations

import secrets
from collections.abc import Iterator
from typing import Protocol

from isabelle_mcp import parsing
from isabelle_mcp.errors import ToolError, clamp_timeout, map_ir_error
from isabelle_mcp.ir_client import IRSession, proof_closed
from isabelle_mcp.textutil import strip_timing, truncate

__all__ = ["AutomationMixin", "FileOpsMixin"]


class _Host(Protocol):
    """The subset of IRManager the mixins depend on."""

    def _resolve(self, repl_id: str) -> str: ...
    def _session(self) -> Iterator[IRSession]: ...  # contextmanager


class AutomationMixin:
    """Layer C: try0, sledgehammer, find_theorems, nitpick, quickcheck, thm_deps."""

    def _diagnostic(self: _Host, repl_id: str, command: str, timeout_seconds: float) -> str:
        """Run a diagnostic Isar command and return its raw body (raises on error)."""
        timeout_seconds = clamp_timeout(timeout_seconds)
        internal = self._resolve(repl_id)
        with self._session() as session:
            env = session.run_diagnostic(
                internal, command=command, timeout_secs=int(timeout_seconds)
            )
        if not env["ok"]:
            raise ToolError(map_ir_error(env["body"]), env["body"])
        return env["body"]

    def try0(self: _Host, repl_id: str, *, timeout_seconds: float = 10.0) -> dict[str, object]:
        """Try standard tactics on the current goal. Returns ``{found, tactic?, output}``."""
        body = self._diagnostic(repl_id, "try0", timeout_seconds)
        parsed = parsing.parse_try0(body)
        return {
            "found": parsed["found"],
            "tactic": parsed["tactic"],
            "output": truncate(parsed["output"]),
        }

    def sledgehammer(
        self: _Host, repl_id: str, *, timeout_seconds: float = 120.0
    ) -> dict[str, object]:
        """Run sledgehammer. Returns ``{found, one_liner?, suggestions, output}``."""
        timeout_seconds = clamp_timeout(timeout_seconds)
        internal = self._resolve(repl_id)
        with self._session() as session:
            env = session.sledgehammer(internal, timeout_secs=int(timeout_seconds))
        if not env["ok"]:
            raise ToolError(map_ir_error(env["body"]), env["body"])
        parsed = parsing.parse_sledgehammer(env["body"])
        return {
            "found": parsed["found"],
            "one_liner": parsed["one_liner"],
            "suggestions": parsed["suggestions"],
            "output": truncate(parsed["output"]),
        }

    def find_theorems(
        self: _Host, repl_id: str, *, query: str, max_results: int = 20
    ) -> dict[str, object]:
        """Search the theorem database. Returns ``{count, theorems}``."""
        internal = self._resolve(repl_id)
        with self._session() as session:
            env = session.find_theorems(internal, query=query, max_results=max_results)
        if not env["ok"]:
            raise ToolError(map_ir_error(env["body"]), env["body"])
        parsed = parsing.parse_find_theorems(env["body"])
        return {"count": parsed["count"], "theorems": parsed["theorems"]}

    def nitpick(self: _Host, repl_id: str, *, timeout_seconds: float = 30.0) -> dict[str, object]:
        """Look for a counterexample. Returns ``{result, output}``."""
        body = self._diagnostic(repl_id, "nitpick", timeout_seconds)
        parsed = parsing.parse_nitpick(body)
        return {"result": parsed["result"], "output": truncate(parsed["output"])}

    def quickcheck(
        self: _Host, repl_id: str, *, timeout_seconds: float = 10.0
    ) -> dict[str, object]:
        """Randomized counterexample search. Returns ``{found_counterexample, output}``."""
        body = self._diagnostic(repl_id, "quickcheck", timeout_seconds)
        parsed = parsing.parse_quickcheck(body)
        return {
            "found_counterexample": parsed["found_counterexample"],
            "output": truncate(parsed["output"]),
        }

    def thm_deps(
        self: _Host, name: str, repl_id: str, *, timeout_seconds: float = 30.0
    ) -> dict[str, object]:
        """List the axioms/theorems a named theorem depends on. ``{dependencies}``."""
        body = self._diagnostic(repl_id, f"thm_deps {name}", timeout_seconds)
        parsed = parsing.parse_thm_deps(body)
        return {"dependencies": parsed["dependencies"]}


class FileOpsMixin:
    """Layer A: run_code (transient REPL) and multi_attempt (per-tactic forks)."""

    def run_code(self: _Host, code: str, *, timeout_seconds: float = 30.0) -> dict[str, object]:
        """Run one Isar/HOL command in a fresh transient REPL on ``Main``."""
        timeout_seconds = clamp_timeout(timeout_seconds)
        internal = f"mcp_run_{secrets.token_hex(6)}"
        with self._session() as session:
            session.init(repl_id=internal, theories=["Main"])
            session._set_step_timeout(internal, int(timeout_seconds))
            try:
                env = session.step(
                    internal, isar=code, timeout_seconds=float(timeout_seconds) + 10.0
                )
            finally:
                session.remove(internal)
        if not env["ok"]:
            raise ToolError(map_ir_error(env["body"]), env["body"])
        return {
            "output": truncate(strip_timing(env["body"])),
            "at_end_of_proof": proof_closed(env),
        }

    def multi_attempt(
        self: _Host, repl_id: str, tactics: list[str], *, timeout_seconds: float = 15.0
    ) -> dict[str, object]:
        """Try each tactic on a fork of the open-proof REPL; report outcomes."""
        timeout_seconds = clamp_timeout(timeout_seconds)
        internal = self._resolve(repl_id)
        attempts: list[dict[str, object]] = []
        with self._session() as session:
            for tactic in tactics:
                fork_id = f"{internal}_ma_{secrets.token_hex(4)}"
                fork_env = session.fork(internal, fork_id)
                if not fork_env["ok"]:
                    attempts.append(
                        {
                            "tactic": tactic,
                            "ok": False,
                            "error_code": map_ir_error(fork_env["body"]),
                            "error": truncate(fork_env["body"]),
                        }
                    )
                    continue
                try:
                    session._set_step_timeout(fork_id, int(timeout_seconds))
                    env = session.step(
                        fork_id,
                        isar=tactic,
                        timeout_seconds=float(timeout_seconds) + 10.0,
                    )
                finally:
                    session.remove(fork_id)
                if env["ok"]:
                    goals = parsing.parse_goal_state(env["body"])
                    attempts.append(
                        {
                            "tactic": tactic,
                            "ok": True,
                            "closes_goal": proof_closed(env),
                            "remaining_goals": goals["goal_count"],
                            "goal_preview": truncate(strip_timing(env["body"])),
                        }
                    )
                else:
                    attempts.append(
                        {
                            "tactic": tactic,
                            "ok": False,
                            "error_code": map_ir_error(env["body"]),
                            "error": truncate(env["body"]),
                        }
                    )
        return {"attempts": attempts}
