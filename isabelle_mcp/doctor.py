"""Preflight checks for running the Isabelle MCP server."""

from __future__ import annotations

import dataclasses
import os
import shutil
import socket
import subprocess
from pathlib import Path
from typing import Sequence

__all__ = [
    "Check",
    "check_ir_submodule",
    "main",
    "render_checks",
    "run_checks",
]

_DEFAULT_IR_PORT = 9147
_EXPECTED_ISABELLE_VERSION = "Isabelle2025-2"


@dataclasses.dataclass(frozen=True)
class Check:
    """One preflight result."""

    name: str
    status: str
    message: str
    fix: str | None = None


def run_checks() -> list[Check]:
    """Run all local preflight checks."""
    checks: list[Check] = []
    repo = _repo_root()
    ir_dir = repo / "vendor" / "AutoCorrode" / "ir"
    checks.append(check_ir_submodule(ir_dir))

    isabelle_bin = _find_isabelle_bin()
    checks.append(_check_isabelle_binary(isabelle_bin))
    if isabelle_bin:
        checks.append(_check_isabelle_version(isabelle_bin))
        session = os.environ.get("ISABELLE_MCP_SESSION", "HOL")
        checks.append(_check_session_built(isabelle_bin, session))

    checks.append(_check_ir_port())
    checks.append(_check_http_binding())
    checks.append(_check_ml_gate())
    checks.append(_check_bash_server())
    return checks


def check_ir_submodule(ir_dir: Path) -> Check:
    """Verify the vendored AutoCorrode I/R submodule is present."""
    missing = [name for name in ("repl.py", "ir.ML") if not (ir_dir / name).is_file()]
    if missing:
        return Check(
            "I/R submodule",
            "fail",
            f"missing {', '.join(missing)} under {ir_dir}",
            "run `git submodule update --init --recursive` from the repo root",
        )
    return Check("I/R submodule", "ok", f"found {ir_dir}")


def render_checks(checks: Sequence[Check]) -> str:
    """Render checks as human-readable terminal text."""
    lines = ["isabelle-mcp doctor"]
    for check in checks:
        lines.append(f"[{check.status.upper():4}] {check.name}: {check.message}")
        if check.fix:
            lines.append(f"       fix: {check.fix}")
    failed = sum(1 for check in checks if check.status == "fail")
    warned = sum(1 for check in checks if check.status == "warn")
    lines.append(f"summary: {failed} failed, {warned} warnings")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point for ``isabelle-mcp doctor``."""
    _ = argv
    checks = run_checks()
    print(render_checks(checks))
    return 1 if any(check.status == "fail" for check in checks) else 0


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _find_isabelle_bin() -> str:
    env_home = os.environ.get("ISABELLE_HOME")
    if env_home:
        candidate = Path(env_home) / "bin" / "isabelle"
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    found = shutil.which("isabelle")
    if found:
        return found
    for candidate in (
        Path("/Applications/Isabelle2025-2.app/bin/isabelle"),
        Path.home() / "Isabelle2025-2" / "bin" / "isabelle",
    ):
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return ""


def _check_isabelle_binary(isabelle_bin: str) -> Check:
    if not isabelle_bin:
        return Check(
            "Isabelle binary",
            "fail",
            "not found via ISABELLE_HOME/bin/isabelle or PATH",
            "export ISABELLE_HOME=/path/to/Isabelle2025-2(.app)",
        )
    return Check("Isabelle binary", "ok", isabelle_bin)


def _check_isabelle_version(isabelle_bin: str) -> Check:
    try:
        result = subprocess.run(
            [isabelle_bin, "version"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return Check("Isabelle version", "fail", f"could not run version check: {exc}")

    output = (result.stdout + result.stderr).strip()
    if result.returncode != 0:
        return Check("Isabelle version", "fail", _preview(output))
    if _EXPECTED_ISABELLE_VERSION not in output:
        return Check(
            "Isabelle version",
            "warn",
            f"expected {_EXPECTED_ISABELLE_VERSION}, got {_preview(output)}",
        )
    return Check("Isabelle version", "ok", output)


def _check_session_built(isabelle_bin: str, session: str) -> Check:
    try:
        result = subprocess.run(
            [isabelle_bin, "build", "-n", "-b", session],
            capture_output=True,
            text=True,
            timeout=90,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return Check(f"Isabelle session {session}", "fail", f"could not check heap: {exc}")

    output = _preview((result.stdout + result.stderr).strip())
    if result.returncode != 0:
        return Check(
            f"Isabelle session {session}",
            "fail",
            output or "heap check failed",
            f"run `{isabelle_bin} build -b {session}`",
        )
    return Check(f"Isabelle session {session}", "ok", "heap is built or up to date")


def _check_ir_port() -> Check:
    raw = os.environ.get("ISABELLE_MCP_PORT")
    try:
        explicit = raw not in {None, "", "0"}
        port = int(raw) if explicit else _DEFAULT_IR_PORT
    except ValueError:
        return Check("I/R TCP port", "fail", f"invalid ISABELLE_MCP_PORT={raw!r}")

    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.5):
            if explicit:
                return Check(
                    "I/R TCP port",
                    "fail",
                    f"configured port 127.0.0.1:{port} is already accepting connections",
                    "free it or set ISABELLE_MCP_PORT to another port",
                )
            return Check(
                "I/R TCP port",
                "ok",
                f"default port 127.0.0.1:{port} is busy; startup will fall back",
            )
    except OSError:
        return Check("I/R TCP port", "ok", f"127.0.0.1:{port} appears available")


def _check_http_binding() -> Check:
    transport = os.environ.get("ISABELLE_MCP_TRANSPORT", "stdio")
    host = os.environ.get("ISABELLE_MCP_HOST", "127.0.0.1")
    if transport != "stdio" and host not in {"127.0.0.1", "localhost", "::1"}:
        return Check(
            "HTTP binding",
            "warn",
            f"{transport} is configured on non-loopback host {host!r}",
            "bind to 127.0.0.1 unless the network is trusted",
        )
    return Check("HTTP binding", "ok", "stdio or loopback-only HTTP")


def _check_ml_gate() -> Check:
    if os.environ.get("ISABELLE_MCP_ALLOW_ML") == "1":
        return Check(
            "Raw ML gate",
            "warn",
            "ISABELLE_MCP_ALLOW_ML=1 permits raw Isabelle/ML commands",
        )
    return Check("Raw ML gate", "ok", "raw ML commands are blocked by default")


def _check_bash_server() -> Check:
    if os.environ.get("ISABELLE_MCP_NO_BASH_SERVER") == "1":
        return Check(
            "Bash.Server",
            "warn",
            "disabled; sledgehammer external ATPs will not be available",
        )
    return Check("Bash.Server", "ok", "enabled for sledgehammer")


def _preview(text: str, limit: int = 500) -> str:
    text = text.replace("\n", " ").strip()
    if len(text) > limit:
        return text[:limit] + "..."
    return text
