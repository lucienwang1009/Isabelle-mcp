"""Pure parser for Isabelle ``.thy`` source — theory outline extraction.

No Isabelle needed: this scans the text to surface the theory header imports and
top-level declarations (theorems, definitions, datatypes, …) with line numbers.
It is a pragmatic, heuristic parser intended for navigation/overview, not a full
Isar tokenizer. Block comments ``(* ... *)`` (which nest) are stripped first so
keywords inside them are ignored, with newlines preserved for line numbers.
"""

from __future__ import annotations

import re
from typing import Any

__all__ = ["parse_theory_outline"]

# Top-level declaration keywords we surface in the outline.
_ENTRY_KEYWORDS = (
    "theorem",
    "lemma",
    "corollary",
    "proposition",
    "definition",
    "fun",
    "function",
    "primrec",
    "abbreviation",
    "inductive",
    "datatype",
    "type_synonym",
    "record",
    "locale",
    "class",
    "instantiation",
)
_ENTRY_RE = re.compile(r"^(" + "|".join(_ENTRY_KEYWORDS) + r")\b(.*)$")
# An identifier (not a type variable like 'a); allows qualified/primed names.
_IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_'.]*")
_HEADER_RE = re.compile(r"\btheory\s+(\S+).*?\bimports\b(.*?)\bbegin\b", re.S)
_IMPORTS_ONLY_RE = re.compile(r"\bimports\b(.*?)\bbegin\b", re.S)
_NAME_TOKEN_RE = re.compile(r'"[^"]+"|[A-Za-z_][A-Za-z0-9_.\-]*')
_PREVIEW_MAX = 120


def _strip_comments(text: str) -> str:
    """Replace ``(* ... *)`` comments with spaces, preserving newlines/offsets."""
    out: list[str] = []
    depth = 0
    i = 0
    n = len(text)
    while i < n:
        two = text[i : i + 2]
        if two == "(*":
            depth += 1
            out.append("  ")
            i += 2
            continue
        if two == "*)" and depth > 0:
            depth -= 1
            out.append("  ")
            i += 2
            continue
        ch = text[i]
        out.append(ch if (depth == 0 or ch == "\n") else " ")
        i += 1
    return "".join(out)


def _extract_name(rest: str) -> str:
    """Best-effort name after a declaration keyword.

    Skips leading type variables (``'a``) and type-argument parentheses, stops at
    the statement (a quoted term) or a ``::`` / ``=`` / ``where`` marker, and
    returns the first identifier — which may carry a trailing ``:`` (``foo:``).
    """
    for token in rest.split():
        if token.startswith(("'", "(")):  # type variable or type-arg parens
            continue
        if token.startswith('"'):  # statement began: anonymous declaration
            return ""
        if token.startswith("::") or token in ("=", ":", "where", "and", "|"):
            return ""
        match = _IDENT_RE.match(token.rstrip(":"))
        return match.group(0) if match else ""
    return ""


def parse_theory_outline(text: str) -> dict[str, Any]:
    """Parse ``.thy`` source into ``{name, imports, entries}``.

    ``entries`` is a list of ``{kind, name, line, preview}`` for each top-level
    declaration (1-based line numbers).
    """
    clean = _strip_comments(text)

    name = ""
    imports: list[str] = []
    header = _HEADER_RE.search(clean)
    if header:
        name = header.group(1)
        imports_block = header.group(2)
    else:
        only = _IMPORTS_ONLY_RE.search(clean)
        imports_block = only.group(1) if only else ""
    for tok in _NAME_TOKEN_RE.findall(imports_block):
        imports.append(tok.strip('"'))

    entries: list[dict[str, Any]] = []
    for idx, raw_line in enumerate(clean.split("\n"), start=1):
        stripped = raw_line.strip()
        match = _ENTRY_RE.match(stripped)
        if not match:
            continue
        kind, rest = match.group(1), match.group(2).strip()
        preview = stripped[:_PREVIEW_MAX]
        entries.append(
            {
                "kind": kind,
                "name": _extract_name(rest),
                "line": idx,
                "preview": preview,
            }
        )
    return {"name": name, "imports": imports, "entries": entries}
