"""Local source index for AFP theory files.

This is a discovery index, not a proof-availability oracle: it searches AFP
sources without building AFP heaps. A lemma found here still needs to be made
visible in the active Isabelle session before I/R can cite it.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import re
import sqlite3
import tarfile
import urllib.request
from pathlib import Path
from typing import Any, Sequence

from isabelle_mcp.errors import ToolError
from isabelle_mcp.theory_parse import parse_theory_outline

__all__ = [
    "AfpIndexStats",
    "afp_status",
    "build_index",
    "bootstrap_afp",
    "default_index_path",
    "main_bootstrap",
    "main_index",
    "main_search",
    "main_status",
    "search_index",
]

_SCHEMA_VERSION = "1"
_CACHE_DIR = Path("~/.cache/isabelle-mcp").expanduser()
_DOWNLOADS_DIR = _CACHE_DIR / "downloads"
_AFP_CACHE_DIR = _CACHE_DIR / "afp"
_DEFAULT_DB = _CACHE_DIR / "afp-index.sqlite3"
_AFP_CURRENT_URL = "https://isa-afp.org/release/afp-current.tar.gz"
_AFP_ARCHIVE_NAME = "afp-current.tar.gz"
_SESSION_RE = re.compile(r"^\s*session\s+([A-Za-z0-9_.\-]+)\s*=", re.MULTILINE)
_FILTER_RE = re.compile(r"\b(name|entry|session|theory|kind):([^\s]+)")
_TEXT_TOKEN_RE = re.compile(r"[A-Za-z0-9_'.]+")
_PROOF_START_RE = re.compile(
    r"^\s*(proof|by|apply|done|sorry|oops|qed|using|unfolding)\b"
)
_DECL_START_RE = re.compile(
    r"^\s*(theorem|lemma|corollary|proposition|definition|fun|function|primrec|"
    r"abbreviation|inductive|datatype|type_synonym|record|locale|class|instantiation)\b"
)


@dataclasses.dataclass(frozen=True)
class AfpIndexStats:
    """Summary returned by ``build_index``."""

    db_path: str
    afp_root: str
    theory_files: int
    records: int
    entries: int

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


def default_index_path() -> Path:
    """Return the default local AFP index path."""
    return Path(os.environ.get("ISABELLE_MCP_AFP_INDEX_DB", _DEFAULT_DB)).expanduser()


def afp_status(
    *,
    db_path: str | Path | None = None,
    cache_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Return local AFP source/index cache status."""
    target = Path(db_path).expanduser() if db_path is not None else default_index_path()
    root = Path(cache_dir).expanduser() if cache_dir is not None else _CACHE_DIR
    downloads = root / "downloads" if cache_dir is not None else _DOWNLOADS_DIR
    afp_dir = root / "afp" if cache_dir is not None else _AFP_CACHE_DIR
    archive = downloads / _AFP_ARCHIVE_NAME
    source_roots = _source_roots(afp_dir)
    metadata = _read_metadata(target) if target.is_file() else {}
    return {
        "cache_dir": str(root),
        "archive_path": str(archive),
        "archive_present": archive.is_file(),
        "archive_bytes": _file_size(archive),
        "source_roots": [str(path) for path in source_roots],
        "latest_thys": str(source_roots[-1] / "thys") if source_roots else None,
        "index_path": str(target),
        "index_present": target.is_file(),
        "index_bytes": _file_size(target),
        "metadata": metadata,
    }


def bootstrap_afp(
    *,
    url: str = _AFP_CURRENT_URL,
    cache_dir: str | Path | None = None,
    db_path: str | Path | None = None,
    force_download: bool = False,
    force_extract: bool = False,
) -> dict[str, Any]:
    """Download the current AFP source archive, extract it, and build the index."""
    root = Path(cache_dir).expanduser() if cache_dir is not None else _CACHE_DIR
    downloads = root / "downloads" if cache_dir is not None else _DOWNLOADS_DIR
    afp_dir = root / "afp" if cache_dir is not None else _AFP_CACHE_DIR
    downloads.mkdir(parents=True, exist_ok=True)
    afp_dir.mkdir(parents=True, exist_ok=True)

    archive = downloads / _AFP_ARCHIVE_NAME
    downloaded = False
    if force_download or not archive.is_file():
        _download_file(url, archive)
        downloaded = True

    extracted = False
    if force_extract or not _source_roots(afp_dir):
        _extract_archive(archive, afp_dir)
        extracted = True

    thys = _latest_thys(afp_dir)
    if thys is None:
        raise ToolError("file_not_found", f"could not find extracted AFP thys under {afp_dir}")

    stats = build_index(thys, db_path)
    status = afp_status(db_path=db_path, cache_dir=root)
    return {
        "downloaded": downloaded,
        "extracted": extracted,
        "source_thys": str(thys),
        "index": stats,
        "status": status,
    }


def build_index(afp_root: str | Path, db_path: str | Path | None = None) -> dict[str, Any]:
    """Build a SQLite/FTS index over ``afp_root`` and return summary stats."""
    root = _resolve_afp_root(afp_root)
    target = Path(db_path).expanduser() if db_path is not None else default_index_path()
    target.parent.mkdir(parents=True, exist_ok=True)

    session_by_entry = _read_sessions(root)
    conn = sqlite3.connect(target)
    try:
        _init_schema(conn)
        records = 0
        theory_files = 0
        entries = 0
        for thy in sorted(root.rglob("*.thy")):
            if _is_hidden_or_generated(thy):
                continue
            theory_files += 1
            text = thy.read_text(encoding="utf-8", errors="replace")
            outline = parse_theory_outline(text)
            entry = _entry_for_path(root, thy)
            session = session_by_entry.get(entry, entry)
            imports = outline.get("imports", [])
            theory = str(outline.get("name") or thy.stem)
            qualified_theory = _qualified_theory(session, theory)
            rel_path = str(thy.relative_to(root))
            abs_path = str(thy)
            for item in outline.get("entries", []):
                entries += 1
                statement, snippet = _statement_for_entry(text, item)
                record = {
                    "entry": entry,
                    "session": session,
                    "theory": theory,
                    "qualified_theory": qualified_theory,
                    "path": abs_path,
                    "rel_path": rel_path,
                    "kind": item.get("kind", ""),
                    "name": item.get("name", ""),
                    "line": item.get("line", 0),
                    "statement": statement,
                    "snippet": snippet,
                    "imports_json": json.dumps(imports),
                }
                _insert_record(conn, record)
                records += 1
            if theory_files % 250 == 0:
                conn.commit()
        _write_metadata(conn, root, theory_files, records)
        conn.commit()
    finally:
        conn.close()

    return AfpIndexStats(
        db_path=str(target),
        afp_root=str(root),
        theory_files=theory_files,
        records=records,
        entries=entries,
    ).to_dict()


def search_index(
    query: str,
    *,
    db_path: str | Path | None = None,
    max_results: int = 20,
) -> dict[str, Any]:
    """Search a built AFP index and return structured results."""
    target = Path(db_path).expanduser() if db_path is not None else default_index_path()
    if not target.is_file():
        raise ToolError(
            "afp_index_missing",
            f"AFP index not found: {target}",
            hint="Run `uv run isabelle-mcp afp-index --afp-root /path/to/afp/thys` first.",
        )

    filters, text_query = _split_query(query)
    limit = max(1, min(int(max_results), 100))
    conn = sqlite3.connect(target)
    conn.row_factory = sqlite3.Row
    try:
        rows = _search_rows(conn, text_query, filters, limit)
    finally:
        conn.close()

    results = [_row_to_result(row) for row in rows]
    return {
        "query": query,
        "db_path": str(target),
        "count": len(results),
        "results": results,
    }


def main_index(argv: Sequence[str] | None = None) -> int:
    """CLI entry point for ``isabelle-mcp afp-index``."""
    parser = argparse.ArgumentParser(description="Build a local AFP source index")
    parser.add_argument("--afp-root", required=True, help="AFP root or AFP thys directory")
    parser.add_argument("--db", default=None, help="Output sqlite index path")
    args = parser.parse_args(argv)
    print(json.dumps(build_index(args.afp_root, args.db), indent=2, sort_keys=True))
    return 0


def main_bootstrap(argv: Sequence[str] | None = None) -> int:
    """CLI entry point for ``isabelle-mcp afp-bootstrap``."""
    parser = argparse.ArgumentParser(
        description="Download AFP sources into the local cache and build the source index"
    )
    parser.add_argument("--url", default=_AFP_CURRENT_URL, help="AFP tarball URL")
    parser.add_argument("--cache-dir", default=None, help="Cache directory")
    parser.add_argument("--db", default=None, help="Output sqlite index path")
    parser.add_argument("--force-download", action="store_true")
    parser.add_argument("--force-extract", action="store_true")
    args = parser.parse_args(argv)
    print(
        json.dumps(
            bootstrap_afp(
                url=args.url,
                cache_dir=args.cache_dir,
                db_path=args.db,
                force_download=args.force_download,
                force_extract=args.force_extract,
            ),
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def main_search(argv: Sequence[str] | None = None) -> int:
    """CLI entry point for ``isabelle-mcp afp-search``."""
    parser = argparse.ArgumentParser(description="Search the local AFP source index")
    parser.add_argument("query", help="Search text; supports filters like name:foo")
    parser.add_argument("--db", default=None, help="sqlite index path")
    parser.add_argument("--max-results", type=int, default=20)
    parser.add_argument("--json", action="store_true", help="Print raw JSON")
    args = parser.parse_args(argv)
    result = search_index(args.query, db_path=args.db, max_results=args.max_results)
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(_render_search(result))
    return 0


def main_status(argv: Sequence[str] | None = None) -> int:
    """CLI entry point for ``isabelle-mcp afp-status``."""
    parser = argparse.ArgumentParser(description="Show local AFP source/index cache status")
    parser.add_argument("--cache-dir", default=None, help="Cache directory")
    parser.add_argument("--db", default=None, help="sqlite index path")
    args = parser.parse_args(argv)
    print(
        json.dumps(
            afp_status(cache_dir=args.cache_dir, db_path=args.db),
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def _resolve_afp_root(root: str | Path) -> Path:
    resolved = Path(root).expanduser().resolve()
    if (resolved / "thys").is_dir():
        resolved = resolved / "thys"
    if not resolved.is_dir():
        raise ToolError("file_not_found", f"AFP root is not a directory: {root}")
    return resolved


def _source_roots(afp_dir: Path) -> list[Path]:
    if not afp_dir.is_dir():
        return []
    return sorted(path for path in afp_dir.glob("afp-*") if (path / "thys").is_dir())


def _latest_thys(afp_dir: Path) -> Path | None:
    roots = _source_roots(afp_dir)
    return roots[-1] / "thys" if roots else None


def _download_file(url: str, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    request = urllib.request.Request(url, headers={"User-Agent": "isabelle-mcp"})
    with urllib.request.urlopen(request, timeout=120) as response, tmp.open("wb") as out:
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            out.write(chunk)
    tmp.replace(target)


def _extract_archive(archive: Path, target_dir: Path) -> None:
    if not archive.is_file():
        raise ToolError("file_not_found", f"AFP archive not found: {archive}")
    target_dir.mkdir(parents=True, exist_ok=True)
    target_root = target_dir.resolve()
    with tarfile.open(archive, "r:gz") as tar:
        members = tar.getmembers()
        for member in members:
            destination = (target_root / member.name).resolve()
            if destination != target_root and target_root not in destination.parents:
                raise ToolError("invalid_argument", f"unsafe path in AFP archive: {member.name}")
        tar.extractall(target_root, members=members)


def _file_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def _read_metadata(path: Path) -> dict[str, str]:
    try:
        conn = sqlite3.connect(path)
        try:
            rows = conn.execute("SELECT key, value FROM metadata")
            return {str(key): str(value) for key, value in rows}
        finally:
            conn.close()
    except sqlite3.Error:
        return {}


def _read_sessions(root: Path) -> dict[str, str]:
    sessions: dict[str, str] = {}
    for root_file in sorted(root.rglob("ROOT")):
        try:
            rel = root_file.parent.relative_to(root)
        except ValueError:
            continue
        if not rel.parts:
            continue
        entry = rel.parts[0]
        text = root_file.read_text(encoding="utf-8", errors="replace")
        match = _SESSION_RE.search(text)
        if match and entry not in sessions:
            sessions[entry] = match.group(1)
    return sessions


def _init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        DROP TABLE IF EXISTS metadata;
        DROP TABLE IF EXISTS records;
        DROP TABLE IF EXISTS records_fts;

        CREATE TABLE metadata (
          key TEXT PRIMARY KEY,
          value TEXT NOT NULL
        );

        CREATE TABLE records (
          id INTEGER PRIMARY KEY,
          entry TEXT NOT NULL,
          session TEXT NOT NULL,
          theory TEXT NOT NULL,
          qualified_theory TEXT NOT NULL,
          path TEXT NOT NULL,
          rel_path TEXT NOT NULL,
          kind TEXT NOT NULL,
          name TEXT NOT NULL,
          line INTEGER NOT NULL,
          statement TEXT NOT NULL,
          snippet TEXT NOT NULL,
          imports_json TEXT NOT NULL
        );

        CREATE VIRTUAL TABLE records_fts USING fts5(
          name,
          kind,
          statement,
          snippet,
          theory,
          qualified_theory,
          entry,
          session,
          content='records',
          content_rowid='id'
        );
        """
    )


def _write_metadata(
    conn: sqlite3.Connection, root: Path, theory_files: int, records: int
) -> None:
    payload = {
        "schema_version": _SCHEMA_VERSION,
        "afp_root": str(root),
        "theory_files": str(theory_files),
        "records": str(records),
    }
    conn.executemany(
        "INSERT INTO metadata(key, value) VALUES(?, ?)",
        sorted(payload.items()),
    )


def _insert_record(conn: sqlite3.Connection, record: dict[str, Any]) -> None:
    fields = (
        "entry",
        "session",
        "theory",
        "qualified_theory",
        "path",
        "rel_path",
        "kind",
        "name",
        "line",
        "statement",
        "snippet",
        "imports_json",
    )
    values = [record[field] for field in fields]
    cursor = conn.execute(
        "INSERT INTO records("
        + ", ".join(fields)
        + ") VALUES("
        + ", ".join("?" for _ in fields)
        + ")",
        values,
    )
    rowid = cursor.lastrowid
    conn.execute(
        """
        INSERT INTO records_fts(
          rowid, name, kind, statement, snippet, theory, qualified_theory, entry, session
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            rowid,
            record["name"],
            record["kind"],
            record["statement"],
            record["snippet"],
            record["theory"],
            record["qualified_theory"],
            record["entry"],
            record["session"],
        ),
    )


def _entry_for_path(root: Path, path: Path) -> str:
    rel = path.relative_to(root)
    return rel.parts[0] if rel.parts else path.parent.name


def _qualified_theory(session: str, theory: str) -> str:
    if not session or "." in theory:
        return theory
    return f"{session}.{theory}"


def _is_hidden_or_generated(path: Path) -> bool:
    blocked = {".git", ".hg", "browser_info", "heaps", "__pycache__"}
    return any(part in blocked for part in path.parts)


def _statement_for_entry(text: str, item: dict[str, Any]) -> tuple[str, str]:
    lines = text.splitlines()
    start = max(int(item.get("line", 1)) - 1, 0)
    collected: list[str] = []
    for idx in range(start, min(len(lines), start + 16)):
        line = lines[idx]
        if idx > start and _DECL_START_RE.match(line):
            break
        if idx > start and _PROOF_START_RE.match(line):
            break
        collected.append(line.strip())
    snippet = " ".join(part for part in collected if part)
    statement = re.sub(r"\s+", " ", snippet).strip()
    return statement, snippet[:500]


def _split_query(query: str) -> tuple[dict[str, list[str]], str]:
    filters: dict[str, list[str]] = {}
    for key, value in _FILTER_RE.findall(query):
        filters.setdefault(key, []).append(value)
    text = _FILTER_RE.sub(" ", query)
    text = re.sub(r"\s+", " ", text).strip()
    return filters, text


def _fts_query(text: str) -> str:
    tokens = [token for token in _TEXT_TOKEN_RE.findall(text) if token.strip("_.")]
    return " ".join(f'"{token}"' for token in tokens)


def _search_rows(
    conn: sqlite3.Connection,
    text_query: str,
    filters: dict[str, list[str]],
    limit: int,
) -> list[sqlite3.Row]:
    match = _fts_query(text_query)
    if match:
        try:
            return _search_rows_fts(conn, match, filters, limit)
        except sqlite3.OperationalError:
            return _search_rows_like(conn, text_query, filters, limit)
    return _search_rows_like(conn, text_query, filters, limit)


def _search_rows_fts(
    conn: sqlite3.Connection,
    match: str,
    filters: dict[str, list[str]],
    limit: int,
) -> list[sqlite3.Row]:
    where = ["records_fts MATCH ?"]
    params: list[Any] = [match]
    _append_filters(where, params, filters, table_prefix="records.")
    sql = (
        "SELECT records.*, bm25(records_fts) AS rank "
        "FROM records_fts JOIN records ON records_fts.rowid = records.id "
        f"WHERE {' AND '.join(where)} "
        "ORDER BY rank, line LIMIT ?"
    )
    params.append(limit)
    return list(conn.execute(sql, params))


def _search_rows_like(
    conn: sqlite3.Connection,
    text_query: str,
    filters: dict[str, list[str]],
    limit: int,
) -> list[sqlite3.Row]:
    where: list[str] = []
    params: list[Any] = []
    if text_query:
        needle = f"%{text_query.lower()}%"
        where.append(
            "(lower(name) LIKE ? OR lower(statement) LIKE ? OR lower(snippet) LIKE ? "
            "OR lower(theory) LIKE ? OR lower(entry) LIKE ?)"
        )
        params.extend([needle, needle, needle, needle, needle])
    _append_filters(where, params, filters, table_prefix="")
    clause = f"WHERE {' AND '.join(where)}" if where else ""
    sql = f"SELECT records.*, 0.0 AS rank FROM records {clause} ORDER BY line LIMIT ?"
    params.append(limit)
    return list(conn.execute(sql, params))


def _append_filters(
    where: list[str],
    params: list[Any],
    filters: dict[str, list[str]],
    *,
    table_prefix: str,
) -> None:
    for key, values in sorted(filters.items()):
        if key not in {"name", "entry", "session", "theory", "kind"}:
            continue
        for value in values:
            where.append(f"lower({table_prefix}{key}) LIKE ?")
            params.append(f"%{value.lower()}%")


def _row_to_result(row: sqlite3.Row) -> dict[str, Any]:
    imports = json.loads(row["imports_json"])
    return {
        "entry": row["entry"],
        "session": row["session"],
        "theory": row["theory"],
        "qualified_theory": row["qualified_theory"],
        "path": row["path"],
        "rel_path": row["rel_path"],
        "kind": row["kind"],
        "name": row["name"],
        "line": row["line"],
        "statement": row["statement"],
        "snippet": row["snippet"],
        "imports": imports,
    }


def _render_search(result: dict[str, Any]) -> str:
    lines = [
        f"AFP index search: {result['query']}",
        f"results: {result['count']}",
    ]
    for idx, item in enumerate(result["results"], start=1):
        label = item["name"] or "<anonymous>"
        lines.append(
            f"{idx}. {item['kind']} {label} "
            f"({item['qualified_theory']}:{item['line']})"
        )
        if item["statement"]:
            lines.append(f"   {item['statement']}")
        lines.append(f"   {item['rel_path']}")
    return "\n".join(lines)
