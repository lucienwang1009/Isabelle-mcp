"""Theory-file access helpers.

M3 provides a minimal, read-only file accessor used by Layer A's
``isabelle_file_outline``. A full path allow-list (project root + Isabelle
stdlib + optional AFP) is M4; for now we only resolve, validate, and read.
"""

from __future__ import annotations

from pathlib import Path

from isabelle_mcp.errors import ToolError

__all__ = ["read_theory_file"]

_MAX_BYTES = 4_000_000  # refuse absurdly large files


def read_theory_file(path: str) -> str:
    """Read a ``.thy`` file's text.

    Raises ``ToolError`` with ``file_not_found`` if the path is missing or not a
    file, and ``invalid_argument`` if it is not a ``.thy`` file or is too large.
    """
    resolved = Path(path).expanduser()
    if resolved.suffix != ".thy":
        raise ToolError("invalid_argument", f"not a .thy file: {path}")
    if not resolved.is_file():
        raise ToolError("file_not_found", f"no such theory file: {path}")
    if resolved.stat().st_size > _MAX_BYTES:
        raise ToolError("invalid_argument", f"theory file too large: {path}")
    return resolved.read_text(encoding="utf-8", errors="replace")
