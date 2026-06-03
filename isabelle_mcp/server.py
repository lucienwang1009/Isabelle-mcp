"""FastMCP server entry point. Wires the SKILL preamble, Layer B tools, and the
I/R daemon lifecycle, then serves over stdio.
"""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from isabelle_mcp.lifecycle import IRManager
from isabelle_mcp.tools.layer_a import register_layer_a
from isabelle_mcp.tools.layer_b import register_layer_b
from isabelle_mcp.tools.layer_c import register_layer_c
from isabelle_mcp.transports.stdio import run_stdio

logger = logging.getLogger(__name__)

__all__ = ["build_server", "main", "manager_from_env"]

_SKILL_PATH = Path(__file__).parent / "skills" / "isabelle-proving.md"


def _load_instructions() -> str:
    """Load the proving-loop preamble (SKILL body, frontmatter stripped)."""
    try:
        text = _SKILL_PATH.read_text(encoding="utf-8")
    except OSError:
        logger.warning("could not read SKILL at %s", _SKILL_PATH)
        return "isabelle-mcp: a stateful Isabelle/HOL REPL exposed as MCP tools."
    if text.startswith("---"):
        # Drop the YAML frontmatter block between the first two `---` lines.
        parts = text.split("---", 2)
        if len(parts) == 3:
            return parts[2].strip()
    return text.strip()


def _find_isabelle_bin() -> str:
    """Best-effort isabelle binary resolution; '' if not found (daemon fails later)."""
    env_home = os.environ.get("ISABELLE_HOME")
    if env_home:
        candidate = Path(env_home) / "bin" / "isabelle"
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    found = shutil.which("isabelle")
    return found or ""


def _ir_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "vendor" / "AutoCorrode" / "ir"


def manager_from_env() -> IRManager:
    """Construct an IRManager from environment (does not start the daemon)."""
    port_raw = os.environ.get("ISABELLE_MCP_PORT")
    port = int(port_raw) if port_raw else None
    # Bash.Server is needed for sledgehammer's ATPs; on by default (M2).
    bash_server = os.environ.get("ISABELLE_MCP_NO_BASH_SERVER") != "1"
    return IRManager(
        isabelle_bin=_find_isabelle_bin(),
        ir_dir=_ir_dir(),
        session=os.environ.get("ISABELLE_MCP_SESSION", "HOL"),
        port=port,
        bash_server=bash_server,
    )


def build_server(manager: IRManager | None = None) -> FastMCP:
    """Build a FastMCP server with the SKILL preamble and Layer A + B + C tools."""
    mcp = FastMCP("isabelle-mcp", instructions=_load_instructions())
    target = manager if manager is not None else manager_from_env()
    register_layer_a(mcp, target)
    register_layer_b(mcp, target)
    register_layer_c(mcp, target)
    return mcp


def main() -> None:
    """CLI entry point (pyproject [project.scripts] isabelle-mcp)."""
    logging.basicConfig(
        level=os.environ.get("ISABELLE_MCP_LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    manager = manager_from_env()
    mcp = build_server(manager)
    try:
        manager.start()
    except Exception:  # noqa: BLE001 - tools will report ir_unavailable
        logger.exception("failed to start I/R daemon; tools will report ir_unavailable")
    try:
        run_stdio(mcp)
    finally:
        manager.close()


if __name__ == "__main__":
    main()
