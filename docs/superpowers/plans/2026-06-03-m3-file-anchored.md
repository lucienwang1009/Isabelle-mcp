# M3 — File-anchored (Layer A) Implementation Plan

**Goal:** Add Layer A tools that help an LLM work with theory files and explore
tactics, composed over Layer B. Done when the in-scope Layer A tools pass
integration on fixtures and goals are returned in a structured form.

**Builds on M1/M2:** reuses `IRManager`, the error taxonomy, FastMCP server.

## Scope decision (important)

The design spec §4 lists six Layer A tools. Two hard constraints in the
**vendored** I/R (which must stay pristine) shape what is achievable now:

1. **The TCP layer strips PIDE markup to plain text** (see
   `docs/ir-protocol-notes.md`). There is no typed markup over the wire, so
   `isabelle_hover` (types/definition-at-position) cannot be implemented without
   substantial custom ML. **Deferred.**
2. **`Ir.source`/`source_map` need a heap built with `record_theories=true`**
   (`ir.ML:120–124`); the standard HOL heap is not. Reliable file line →
   command-segment mapping for arbitrary user files is therefore not available,
   so position-anchored `isabelle_goal_at` and whole-file `isabelle_diagnostics`
   are **deferred** (they need either a recorded heap or a raw-ML tokenizer
   helper — a good follow-up, out of M3).

**In scope for M3 (robust, high-value, no submodule changes):**

| MCP tool | Mechanism | Returns |
|---|---|---|
| `isabelle_file_outline(path)` | Python `.thy` text parser (no Isabelle) | `{ok, imports, entries[]}` |
| `isabelle_run_code(code, timeout_s=30)` | transient REPL on `Main`, one Isar command | `{ok, output, at_end_of_proof, error?}` |
| `isabelle_multi_attempt(repl_id, tactics, timeout_s=15)` | fork the open-proof REPL per tactic, step, report | `{ok, attempts[]}` |

Plus **structured goal representation**: a `parse_goal_state` helper turns the
pretty proof state into `{goal_count, subgoals[]}`, surfaced in
`isabelle_state` (as `goals`) and in each `multi_attempt` result.

`isabelle_multi_attempt` is **REPL-anchored** (operates on an open-proof
`repl_id`) rather than path/line-anchored as in the spec sketch — this fits the
REPL-centric model and is far more robust than file-line anchoring given the
constraints above. Documented as an intentional deviation.

## Tasks

### Task 1: Parsers
- `theory_parse.py` (pure): `parse_theory_outline(text) -> {imports, entries}`
  where each entry is `{kind, name, line, preview}` for
  theorem/lemma/corollary/proposition/definition/fun/function/primrec/
  abbreviation/datatype/type_synonym/locale/class/instantiation.
- `parsing.parse_goal_state(body) -> {goal_count, subgoals}`.
- Unit-tested, no Isabelle.

### Task 2: IRManager operations
- `run_code(code, timeout_seconds)` — open a transient internal REPL on `Main`,
  `step` the code, remove the REPL; return `{output, at_end_of_proof}` or raise
  ToolError on failure.
- `multi_attempt(repl_id, tactics, timeout_seconds)` — for each tactic: fork the
  resolved REPL to a throwaway internal id, set its step timeout, step the
  tactic, record `{tactic, ok, closes_goal, remaining_goals, error?}`, remove
  the fork. Forks are not registered (ephemeral).
- `state()` gains a `goals` field from `parse_goal_state`.
- `read_theory_file(path)` helper: resolve, ensure exists + `.thy`, return text;
  raise `file_not_found` otherwise. (Full sandbox is M4.)

### Task 3: Layer A tools + wiring
- `tools/layer_a.py`: `register_layer_a(mcp, manager)` with the three tools and
  spec-style descriptions. `file_outline` reads the file via the helper and
  calls the pure parser (no daemon needed).
- Wire `register_layer_a` into `server.build_server`; update SKILL + README.

### Task 4: Tests, verify, tag
- Unit: `test_theory_parse.py`, goal-state cases in `test_layer_c_parsing.py`
  (or a new `test_goal_parse.py`).
- Integration `test_mcp_layer_a.py` (own port): `run_code` proves a lemma;
  `multi_attempt` reports which of several tactics close a goal; `file_outline`
  on a fixture `.thy`.
- Fixture `tests/fixtures/example.thy`.
- Run `uv run pytest`; tag `v0.0.0-m3`, push.

## Acceptance criteria
1. `uv run pytest` green (unit no-Isabelle; integration with Isabelle).
2. The three Layer A tools are callable via MCP; `isabelle_state` returns
   structured `goals`.
3. `multi_attempt` correctly distinguishes a goal-closing tactic from a failing
   one on a fixture goal.
4. Tag `v0.0.0-m3` on the remote.

## Deferred to a later milestone (documented)
- `isabelle_hover` — needs typed PIDE markup (stripped by I/R's TCP layer).
- `isabelle_goal_at`, `isabelle_diagnostics` — need a `record_theories` heap or a
  raw-ML file tokenizer helper to map file lines → command segments.
