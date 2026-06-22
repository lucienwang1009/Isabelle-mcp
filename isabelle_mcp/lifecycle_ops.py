"""Layer C (automation) and Layer A (file/orchestration) operation mixins.

These are mixed into :class:`~isabelle_mcp.lifecycle.IRManager`; they rely on the
host providing ``_resolve``, ``_session`` (a context manager yielding an
``IRSession``), and the daemon lifecycle. Kept separate to keep each module
within the project's file-size limit.
"""

from __future__ import annotations

import math
import secrets
from collections.abc import Iterator
from pathlib import Path
from typing import Protocol

from isabelle_mcp import parsing
from isabelle_mcp.errors import ToolError, clamp_timeout, map_ir_error
from isabelle_mcp.ir_client import IRSession, proof_closed
from isabelle_mcp.project_build import check_isabelle_project, discover_project_root
from isabelle_mcp.sandbox import read_theory_file
from isabelle_mcp.sandbox import resolve_in_sandbox
from isabelle_mcp.safety import validate_isar_safe
from isabelle_mcp.textutil import strip_timing, truncate
from isabelle_mcp.theory_parse import parse_theory_outline

__all__ = ["AutomationMixin", "FileOpsMixin"]


class _Host(Protocol):
    """The subset of IRManager the mixins depend on."""

    _isabelle_bin: str

    def _resolve(self, repl_id: str) -> str: ...
    def _session(self) -> Iterator[IRSession]: ...  # contextmanager
    def _tool_error(self, code: str, message: str) -> ToolError: ...
    def _with_server_event(self, result: dict[str, object]) -> dict[str, object]: ...


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
            raise self._tool_error(map_ir_error(env["body"]), env["body"])
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
            raise self._tool_error(map_ir_error(env["body"]), env["body"])
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
            raise self._tool_error(map_ir_error(env["body"]), env["body"])
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
        validate_isar_safe(code)
        internal = f"mcp_run_{secrets.token_hex(6)}"
        with self._session() as session:
            session.init(repl_id=internal, theories=["Main"])
            session._set_step_timeout(internal, math.ceil(timeout_seconds))
            try:
                env = session.step(
                    internal, isar=code, timeout_seconds=float(timeout_seconds) + 10.0
                )
            finally:
                session.remove(internal)
        if not env["ok"]:
            raise self._tool_error(map_ir_error(env["body"]), env["body"])
        return self._with_server_event({
            "output": truncate(strip_timing(env["body"])),
            "at_end_of_proof": proof_closed(env),
        })

    def check_file(
        self: _Host,
        path: str,
        *,
        timeout_seconds: float = 120.0,
        session: str | None = None,
        session_dirs: list[str] | None = None,
    ) -> dict[str, object]:
        """Load/check a theory file by header, or build its project context."""
        timeout_seconds = clamp_timeout(timeout_seconds)
        text = read_theory_file(path)
        resolved = resolve_in_sandbox(path)
        outline = parse_theory_outline(text)
        theory = str(outline.get("name") or "")
        if not theory:
            raise self._tool_error("parse_error", f"could not find theory header in {path}")
        if session or session_dirs:
            root = discover_project_root(resolved)
            build = self.check_project(
                str(root),
                session=session,
                session_dirs=session_dirs,
                timeout_seconds=timeout_seconds,
            )
            return self._with_server_event({
                **build,
                "theory": theory,
                "theory_path": str(resolved),
                "imports": outline["imports"],
                "entries": outline["entries"],
                "checked_via": "isabelle_build",
            })
        with self._session() as ir_session:
            env = ir_session.load_theory(theory, timeout_seconds=timeout_seconds + 30.0)
        diagnostics = parsing.parse_theory_diagnostics(env["body"])
        return self._with_server_event({
            "checked": bool(env["ok"]),
            "theory": theory,
            "imports": outline["imports"],
            "entries": outline["entries"],
            "errors": diagnostics["errors"],
            "warnings": diagnostics["warnings"],
            "output": truncate(strip_timing(env["body"])),
        })

    def check_project(
        self: _Host,
        root: str,
        *,
        timeout_seconds: float = 300.0,
        session: str | None = None,
        session_dirs: list[str] | None = None,
        jobs: int | None = None,
        verbose: bool = False,
    ) -> dict[str, object]:
        """Run ``isabelle build`` for a project/session and return diagnostics."""
        timeout_seconds = clamp_timeout(timeout_seconds)
        root_path = resolve_in_sandbox(root)
        if root_path.is_file():
            root_path = discover_project_root(root_path)
        dirs = [resolve_in_sandbox(path) for path in (session_dirs or [])]
        return check_isabelle_project(
            isabelle_bin=self._isabelle_bin,
            root=Path(root_path),
            session=session,
            session_dirs=[Path(path) for path in dirs],
            timeout_seconds=timeout_seconds,
            jobs=jobs,
            verbose=verbose,
        )

    def multi_attempt(
        self: _Host, repl_id: str, tactics: list[str], *, timeout_seconds: float = 15.0
    ) -> dict[str, object]:
        """Try each tactic on a fork of the open-proof REPL; report outcomes."""
        timeout_seconds = clamp_timeout(timeout_seconds)
        for tactic in tactics:
            validate_isar_safe(tactic)
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
                    session._set_step_timeout(fork_id, math.ceil(timeout_seconds))
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
