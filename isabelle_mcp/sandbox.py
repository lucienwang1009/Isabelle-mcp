"""Theory-file access with a path allow-list.

Reads are restricted to an allow-list of roots: the current working directory
(project root) plus any directories named in ``ISABELLE_MCP_ALLOWED_DIRS``
(``os.pathsep``-separated). Symlinks are resolved before the check, and paths
outside the allow-list are reported as ``file_not_found`` so the server does not
leak filesystem layout.
"""

from __future__ import annotations

import os
from pathlib import Path

from isabelle_mcp.errors import ToolError

__all__ = [
    "allowed_roots",
    "read_theory_file",
    "resolve_in_sandbox",
    "resolve_target",
]

_MAX_BYTES = 4_000_000  # refuse absurdly large files


def allowed_roots() -> list[Path]:
    """Return the resolved allow-list roots (CWD + ISABELLE_MCP_ALLOWED_DIRS)."""
    roots = [Path.cwd()]
    extra = os.environ.get("ISABELLE_MCP_ALLOWED_DIRS", "")
    for part in extra.split(os.pathsep):
        part = part.strip()
        if part:
            roots.append(Path(part).expanduser())
    resolved: list[Path] = []
    for root in roots:
        try:
            resolved.append(root.resolve())
        except OSError:
            continue
    return resolved


def _within(path: Path, roots: list[Path]) -> bool:
    return any(path == root or root in path.parents for root in roots)


def resolve_in_sandbox(path: str) -> Path:
    """Resolve ``path`` and ensure it lies within the allow-list.

    Raises ``file_not_found`` if it escapes the sandbox (symlinks resolved).
    """
    resolved = Path(path).expanduser().resolve()
    if not _within(resolved, allowed_roots()):
        raise ToolError("file_not_found", f"path outside the allowed roots: {path}")
    return resolved


def resolve_target(path: str) -> Path:
    """Resolve an *explicitly named* build/check target, bypassing the allow-list.

    The allow-list guards *incidental* reads, not a path the caller deliberately
    hands to a build/check tool: building the project you point ``check_project``
    at, or checking the ``.thy`` you name, is the tool's whole purpose. Symlinks
    and ``~`` are still resolved. Existence is validated by the caller.
    """
    return Path(path).expanduser().resolve()


def read_theory_file(path: str, *, trusted: bool = False) -> str:
    """Read a ``.thy`` file's text.

    With ``trusted=True`` the path is an explicit target and the allow-list is
    bypassed (see :func:`resolve_target`); otherwise it must lie within the
    allow-list. Raises ``invalid_argument`` for non-``.thy`` or oversized files,
    and ``file_not_found`` for missing files or paths outside the allow-list.
    """
    if Path(path).suffix != ".thy":
        raise ToolError("invalid_argument", f"not a .thy file: {path}")
    resolved = resolve_target(path) if trusted else resolve_in_sandbox(path)
    if not resolved.is_file():
        raise ToolError("file_not_found", f"no such theory file: {path}")
    if resolved.stat().st_size > _MAX_BYTES:
        raise ToolError("invalid_argument", f"theory file too large: {path}")
    return resolved.read_text(encoding="utf-8", errors="replace")
