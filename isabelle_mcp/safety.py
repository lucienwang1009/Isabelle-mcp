"""Safety checks for user-provided Isar command text."""

from __future__ import annotations

import os
import re

from isabelle_mcp.errors import ToolError

__all__ = [
    "RAW_ML_COMMANDS",
    "first_isar_command",
    "looks_multi_command",
    "raw_ml_allowed",
    "validate_isar_safe",
]

# Isar commands that each OPEN a new command (vs. proof connectives like `by`,
# `using`, `then`, `also` that stay within one step). Two or more openers in a
# single submission means several commands were pasted into one step.
_COMMAND_OPENERS = frozenset(
    {
        "lemma", "theorem", "corollary", "proposition", "definition",
        "fun", "function", "primrec", "datatype", "record", "abbreviation",
        "lemmas", "notation", "declare", "locale", "context", "interpretation",
        "sublocale", "instance", "instantiation",
        "proof", "qed", "next", "show", "have", "hence", "thus", "obtain",
        "fix", "assume", "case", "end",
    }
)


RAW_ML_COMMANDS = frozenset(
    {
        "ML",
        "ML_command",
        "ML_export",
        "ML_file",
        "ML_prf",
        "ML_val",
        "attribute_setup",
        "declaration",
        "local_setup",
        "method_setup",
        "oracle",
        "parse_ast_translation",
        "parse_translation",
        "print_ast_translation",
        "print_translation",
        "setup",
        "simproc_setup",
        "syntax_declaration",
        "typed_print_translation",
    }
)

_COMMAND_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_']*")


def raw_ml_allowed() -> bool:
    """Return True when the operator explicitly enables raw ML-ish commands."""
    return os.environ.get("ISABELLE_MCP_ALLOW_ML") == "1"


def first_isar_command(text: str) -> str:
    """Return the first Isar command token after whitespace/comments."""
    i = 0
    n = len(text)
    while i < n:
        while i < n and text[i].isspace():
            i += 1
        if text.startswith("(*", i):
            i = _skip_comment(text, i)
            continue
        break
    match = _COMMAND_RE.match(text, i)
    return match.group(0) if match else ""


def looks_multi_command(text: str) -> bool:
    """Heuristic: True when ``text`` contains two or more top-level Isar command
    openers, i.e. several commands were submitted as one step. Used only to add
    an advisory hint; proof connectives (``by``/``using``/``also``/…) and a
    single multi-line command statement do not trip it.
    """
    count = 0
    for raw in text.split("\n"):
        match = _COMMAND_RE.match(raw.strip())
        if match and match.group(0) in _COMMAND_OPENERS:
            count += 1
            if count >= 2:
                return True
    return False


def validate_isar_safe(text: str) -> None:
    """Raise ``ml_disabled`` when raw ML commands are disabled and detected."""
    command = first_isar_command(text)
    if command in RAW_ML_COMMANDS and not raw_ml_allowed():
        raise ToolError(
            "ml_disabled",
            f"Raw ML command `{command}` is disabled. "
            "Set ISABELLE_MCP_ALLOW_ML=1 to allow it.",
        )


def _skip_comment(text: str, start: int) -> int:
    """Skip a nested Isabelle block comment beginning at ``start``."""
    depth = 0
    i = start
    n = len(text)
    while i < n:
        two = text[i : i + 2]
        if two == "(*":
            depth += 1
            i += 2
            continue
        if two == "*)" and depth:
            depth -= 1
            i += 2
            if depth == 0:
                return i
            continue
        i += 1
    return n
