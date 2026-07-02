"""Unit test: SKILL reference files are exposed as MCP resources (no Isabelle)."""

from __future__ import annotations

import asyncio
from pathlib import Path

from isabelle_mcp.resources import REFERENCE_TITLES, register_resources
from isabelle_mcp.server import build_server

_REFERENCES_DIR = Path(__file__).resolve().parents[2] / "isabelle_mcp" / "skills" / "references"

_EXPECTED_URIS = {
    "skill://isabelle/project-workflow",
    "skill://isabelle/tactics",
    "skill://isabelle/isar-patterns",
    "skill://isabelle/sledgehammer",
    "skill://isabelle/afp-and-search",
    "skill://isabelle/afp-setup",
    "skill://isabelle/counterexamples",
    "skill://isabelle/errors",
}


def test_every_reference_file_has_a_title() -> None:
    stems = {p.stem for p in _REFERENCES_DIR.glob("*.md")}
    assert stems, "no reference markdown files found"
    assert stems <= set(REFERENCE_TITLES), stems - set(REFERENCE_TITLES)


def test_build_server_advertises_reference_resources() -> None:
    mcp = build_server()
    resources = asyncio.run(mcp.list_resources())
    uris = {str(r.uri).rstrip("/") for r in resources}
    assert _EXPECTED_URIS <= uris, _EXPECTED_URIS - uris


def test_afp_resource_mentions_archive_of_formal_proofs() -> None:
    mcp = build_server()
    contents = asyncio.run(mcp.read_resource("skill://isabelle/afp-and-search"))
    body = list(contents)[0].content
    assert "Archive of Formal Proofs" in body
    assert "isabelle components" in body  # AFP install command is documented
    assert "Cook_Levin" in body


def test_afp_setup_resource_documents_build_workflow() -> None:
    mcp = build_server()
    contents = asyncio.run(mcp.read_resource("skill://isabelle/afp-setup"))
    body = list(contents)[0].content
    assert "isabelle build -b" in body  # heap build command
    assert "ISABELLE_MCP_SESSION" in body  # how to point the server at it


def test_project_workflow_resource_documents_root_sessions() -> None:
    mcp = build_server()
    contents = asyncio.run(mcp.read_resource("skill://isabelle/project-workflow"))
    body = list(contents)[0].content
    assert "ROOT" in body
    assert "isabelle_check_project" in body
    assert "session_dirs" in body


def test_register_resources_counts_files() -> None:
    from mcp.server.fastmcp import FastMCP

    n = register_resources(FastMCP("t"))
    assert n == len(list(_REFERENCES_DIR.glob("*.md")))
    assert n >= 6
