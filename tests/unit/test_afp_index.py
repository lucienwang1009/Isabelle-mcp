"""Unit tests for the local AFP source index."""

from __future__ import annotations

import asyncio
import json
import tarfile
from pathlib import Path
from typing import Any

import pytest

from isabelle_mcp.afp_index import afp_status, bootstrap_afp, build_index, search_index
from isabelle_mcp.errors import ToolError
from isabelle_mcp.server import build_server


def _write_fake_afp(root: Path) -> Path:
    thys = root / "thys"
    entry = thys / "Toy_AFP"
    entry.mkdir(parents=True)
    (entry / "ROOT").write_text(
        """
session Toy_AFP = HOL +
  theories Toy
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (entry / "Toy.thy").write_text(
        """
theory Toy
  imports Main
begin

lemma toy_comm:
  "x + y = y + (x::nat)"
  by simp

definition toy_square where
  "toy_square n = n * (n::nat)"

theorem finite_automata_language:
  "True"
  by simp

end
""".lstrip(),
        encoding="utf-8",
    )
    return thys


def test_build_and_search_local_afp_index(tmp_path: Path) -> None:
    thys = _write_fake_afp(tmp_path / "afp")
    db = tmp_path / "afp.sqlite3"

    stats = build_index(thys, db)
    assert stats["theory_files"] == 1
    assert stats["records"] == 3

    result = search_index("finite automata", db_path=db)

    assert result["count"] == 1
    item = result["results"][0]
    assert item["name"] == "finite_automata_language"
    assert item["entry"] == "Toy_AFP"
    assert item["session"] == "Toy_AFP"
    assert item["qualified_theory"] == "Toy_AFP.Toy"
    assert item["imports"] == ["Main"]


def test_search_supports_name_and_kind_filters(tmp_path: Path) -> None:
    thys = _write_fake_afp(tmp_path / "afp")
    db = tmp_path / "afp.sqlite3"
    build_index(thys, db)

    result = search_index("name:toy kind:definition", db_path=db)

    assert result["count"] == 1
    assert result["results"][0]["name"] == "toy_square"


def test_search_combines_text_and_filters(tmp_path: Path) -> None:
    thys = _write_fake_afp(tmp_path / "afp")
    db = tmp_path / "afp.sqlite3"
    build_index(thys, db)

    result = search_index("automata kind:theorem", db_path=db)

    assert result["count"] == 1
    assert result["results"][0]["name"] == "finite_automata_language"


def test_search_missing_index_has_actionable_error(tmp_path: Path) -> None:
    with pytest.raises(ToolError) as exc:
        search_index("anything", db_path=tmp_path / "missing.sqlite3")

    assert exc.value.code == "afp_index_missing"
    assert "afp-index" in (exc.value.hint or "")


def test_afp_status_reports_index_metadata(tmp_path: Path) -> None:
    thys = _write_fake_afp(tmp_path / "afp")
    db = tmp_path / "afp.sqlite3"
    build_index(thys, db)

    status = afp_status(cache_dir=tmp_path / "cache", db_path=db)

    assert status["index_present"] is True
    assert status["index_bytes"] > 0
    assert status["metadata"]["schema_version"] == "1"
    assert status["metadata"]["theory_files"] == "1"
    assert status["metadata"]["records"] == "3"


def test_bootstrap_afp_extracts_cached_archive_and_indexes(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    archive = cache / "downloads" / "afp-current.tar.gz"
    archive.parent.mkdir(parents=True)
    source_root = tmp_path / "src" / "afp-2099-01-01"
    _write_fake_afp(source_root)
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(source_root, arcname=source_root.name)

    result = bootstrap_afp(cache_dir=cache, db_path=tmp_path / "afp.sqlite3")

    assert result["downloaded"] is False
    assert result["extracted"] is True
    assert result["index"]["theory_files"] == 1
    assert result["index"]["records"] == 3
    assert result["status"]["archive_present"] is True
    assert result["status"]["index_present"] is True
    assert result["status"]["latest_thys"].endswith("afp-2099-01-01/thys")


async def _call(mcp: Any, name: str, **arguments: Any) -> dict[str, Any]:
    result = await mcp.call_tool(name, arguments)
    if isinstance(result, tuple):
        _content, structured = result
        if isinstance(structured, dict):
            return structured
    return json.loads(result[0].text)  # type: ignore[index]


def test_mcp_afp_search_tool(tmp_path: Path) -> None:
    thys = _write_fake_afp(tmp_path / "afp")
    db = tmp_path / "afp.sqlite3"
    build_index(thys, db)
    mcp = build_server()

    result = asyncio.run(
        _call(
            mcp,
            "isabelle_afp_search",
            query="comm",
            max_results=5,
            db_path=str(db),
        )
    )

    assert result["ok"] is True
    assert result["results"][0]["name"] == "toy_comm"


def test_mcp_afp_status_tool(tmp_path: Path) -> None:
    thys = _write_fake_afp(tmp_path / "afp")
    db = tmp_path / "afp.sqlite3"
    build_index(thys, db)
    mcp = build_server()

    result = asyncio.run(_call(mcp, "isabelle_afp_status", db_path=str(db)))

    assert result["ok"] is True
    assert result["index_present"] is True
    assert result["metadata"]["records"] == "3"
