"""Batch Isabelle project/session checking via ``isabelle build``."""

from __future__ import annotations

import re
import shlex
import subprocess
from pathlib import Path
from typing import Any, Sequence

from isabelle_mcp.errors import ToolError, clamp_timeout
from isabelle_mcp.textutil import truncate

__all__ = [
    "check_isabelle_project",
    "discover_project_root",
    "parse_build_diagnostics",
]

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
_FAILED_LINE_RE = re.compile(
    r"^(?P<message>.*?)(?: \(line (?P<line>\d+) of \"(?P<file>[^\"]+)\"\))?:?$"
)
_AT_COMMAND_RE = re.compile(
    r"^At command \"(?P<command>[^\"]+)\""
    r"(?: \(line (?P<line>\d+) of \"(?P<file>[^\"]+)\"\))?"
)
_WARNING_RE = re.compile(r"\bwarning\b", re.IGNORECASE)


def discover_project_root(path: Path) -> Path:
    """Return the nearest ancestor containing ``ROOT``, or the file's parent."""
    current = path if path.is_dir() else path.parent
    while True:
        if (current / "ROOT").is_file():
            return current
        if current.parent == current:
            return path if path.is_dir() else path.parent
        current = current.parent


def check_isabelle_project(
    *,
    isabelle_bin: str,
    root: Path,
    session: str | None = None,
    session_dirs: Sequence[Path] | None = None,
    timeout_seconds: float = 300.0,
    jobs: int | None = None,
    verbose: bool = False,
) -> dict[str, Any]:
    """Run ``isabelle build`` for a project directory and return diagnostics."""
    if not isabelle_bin:
        raise ToolError(
            "ir_unavailable",
            "Isabelle binary not configured; run `isabelle-mcp doctor`.",
        )
    if not root.is_dir():
        raise ToolError("file_not_found", f"project root is not a directory: {root}")

    timeout_seconds = clamp_timeout(timeout_seconds)
    dirs = [Path(d).expanduser().resolve() for d in (session_dirs or [])]
    command = _build_command(
        isabelle_bin=isabelle_bin,
        root=root,
        session=session,
        session_dirs=dirs,
        jobs=jobs,
        verbose=verbose,
    )

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise ToolError(
            "timeout",
            f"`isabelle build` exceeded timeout_s={timeout_seconds:g}",
        ) from exc
    except OSError as exc:
        raise ToolError(
            "ir_unavailable",
            f"could not run Isabelle build command: {exc}",
        ) from exc

    output = _join_output(result.stdout, result.stderr)
    diagnostics = parse_build_diagnostics(output)
    if result.returncode != 0 and not diagnostics["errors"]:
        diagnostics["errors"].append({"message": _fallback_error_message(output)})

    return {
        "checked": result.returncode == 0,
        "returncode": result.returncode,
        "root": str(root),
        "session": session,
        "session_dirs": [str(d) for d in dirs],
        "command": command,
        "command_text": shlex.join(command),
        "errors": diagnostics["errors"],
        "warnings": diagnostics["warnings"],
        "output": truncate(output),
    }


def parse_build_diagnostics(output: str) -> dict[str, list[dict[str, Any]]]:
    """Extract best-effort structured diagnostics from Isabelle build output."""
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None

    for raw_line in output.splitlines():
        line = _ANSI_RE.sub("", raw_line).rstrip()
        if not line:
            continue
        starred = line[4:] if line.startswith("*** ") else line
        if line.startswith("*** "):
            at_command = _AT_COMMAND_RE.match(starred)
            if at_command and current is not None:
                _merge_command(current, at_command)
                continue
            if _WARNING_RE.search(starred):
                warnings.append(_parse_message(starred))
                continue
            if _is_primary_error(starred):
                current = _parse_message(starred)
                errors.append(current)
                continue
        elif _WARNING_RE.search(line):
            warnings.append({"message": line})

    return {"errors": errors, "warnings": warnings}


def _build_command(
    *,
    isabelle_bin: str,
    root: Path,
    session: str | None,
    session_dirs: Sequence[Path],
    jobs: int | None,
    verbose: bool,
) -> list[str]:
    command = [isabelle_bin, "build"]
    if verbose:
        command.append("-v")
    if jobs is not None:
        command.extend(["-j", str(max(1, int(jobs)))])
    for directory in session_dirs:
        command.extend(["-d", str(directory)])
    if session:
        command.extend(["-d", str(root), session])
    else:
        command.extend(["-D", str(root)])
    return command


def _parse_message(text: str) -> dict[str, Any]:
    match = _FAILED_LINE_RE.match(text)
    if not match:
        return {"message": text}
    item: dict[str, Any] = {"message": match.group("message").strip()}
    if match.group("line") is not None:
        item["line"] = int(match.group("line"))
    if match.group("file") is not None:
        item["file"] = str(Path(match.group("file")).expanduser())
    return item


def _merge_command(item: dict[str, Any], match: re.Match[str]) -> None:
    item["command"] = match.group("command")
    if match.group("line") is not None:
        item.setdefault("line", int(match.group("line")))
    if match.group("file") is not None:
        item.setdefault("file", str(Path(match.group("file")).expanduser()))


def _is_primary_error(text: str) -> bool:
    lowered = text.lower()
    return any(
        marker in lowered
        for marker in (
            "failed",
            "error",
            "exception",
            "bad ",
            "undefined",
            "inner syntax",
            "outer syntax",
            "timeout",
        )
    )


def _join_output(stdout: str, stderr: str) -> str:
    stdout = stdout or ""
    stderr = stderr or ""
    if stdout and stderr:
        return stdout.rstrip("\n") + "\n" + stderr.lstrip("\n")
    return stdout or stderr


def _fallback_error_message(output: str) -> str:
    text = output.strip()
    if not text:
        return "isabelle build failed with no output"
    return text[:1000]
