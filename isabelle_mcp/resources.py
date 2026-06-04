"""Register the SKILL reference files as MCP resources.

The main proving SKILL is served as the FastMCP ``instructions`` preamble; the
deeper reference docs under ``skills/references/`` are exposed as on-demand MCP
resources (``skill://isabelle/<name>``) so clients can pull a topic into context
only when needed — the progressive-disclosure pattern.
"""

from __future__ import annotations

import logging
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.resources import TextResource
from pydantic import AnyUrl

logger = logging.getLogger(__name__)

__all__ = ["REFERENCE_TITLES", "register_resources"]

_REFERENCES_DIR = Path(__file__).parent / "skills" / "references"
_URI_PREFIX = "skill://isabelle/"

# Stem -> human-readable title shown in the resource listing.
REFERENCE_TITLES: dict[str, str] = {
    "tactics": "Isabelle/HOL tactic reference",
    "isar-patterns": "Structured Isar proof patterns",
    "sledgehammer": "Driving sledgehammer",
    "afp-and-search": "Searching for lemmas (find_theorems + the AFP)",
    "afp-setup": "Setting up the AFP: download, build, point the server",
    "counterexamples": "Falsifying goals: nitpick and quickcheck",
    "errors": "Error codes and recovery",
}


def register_resources(mcp: FastMCP, references_dir: Path | None = None) -> int:
    """Register every reference markdown file as a ``skill://isabelle/<stem>``
    resource. Returns the number of resources registered.
    """
    directory = references_dir if references_dir is not None else _REFERENCES_DIR
    count = 0
    for path in sorted(directory.glob("*.md")):
        stem = path.stem
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            logger.warning("could not read reference %s", path)
            continue
        title = REFERENCE_TITLES.get(stem, stem.replace("-", " ").title())
        resource = TextResource(
            uri=AnyUrl(f"{_URI_PREFIX}{stem}"),
            name=stem,
            title=title,
            description=f"isabelle-mcp proving reference: {title}.",
            mime_type="text/markdown",
            text=text,
        )
        mcp.add_resource(resource)
        count += 1
    logger.info("registered %d skill reference resources", count)
    return count
