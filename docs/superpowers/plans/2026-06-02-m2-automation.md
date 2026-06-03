# M2 — Automation (Layer C) Implementation Plan

**Goal:** Add the Layer C automation tools so an unfine-tuned LLM can actually
close non-trivial goals: `isabelle_sledgehammer`, `isabelle_try0`,
`isabelle_find_theorems`, `isabelle_nitpick`, `isabelle_quickcheck`,
`isabelle_thm_deps`. Done when all pass integration against real Isabelle and
sledgehammer returns one-liners.

**Builds on M1:** reuses `IRManager`, the error taxonomy, FastMCP server, and
the opaque-`repl_id` registry. Adds a new `tools/layer_c.py` and Layer C
operations on `IRManager` / `IRSession`.

## Spike findings (resolved Week-1 unknowns)

Verified against Isabelle2025-2 (see `docs/ir-protocol-notes.md` "Layer C"):

- `Ir.find_theorems id n query` and `Ir.sledgehammer id secs` are **built-in**
  and query the proof state without appending a step. Sledgehammer needs the
  **Bash.Server** (launch without `--no-bash-server`).
- The `IR` signature does **not** expose the repl table, so a custom `extras.ML`
  cannot reach a REPL's proof state — and the submodule must stay pristine.
  **Decision: no `extras.ML`.** Implement `try0`/`nitpick`/`quickcheck`/
  `thm_deps` by stepping the native Isar diagnostic command and then `Ir.back`
  (diagnostics don't change state). Output is captured in the step body.
- Raw ML eval works over TCP but is unnecessary here.

## Tool surface (spec §4 Layer C)

| MCP tool | Mechanism | Returns |
|---|---|---|
| `isabelle_sledgehammer(repl_id, timeout_s=120, minimize=true)` | `Ir.sledgehammer` | `{ok, found, one_liner?, suggestions[], output}` |
| `isabelle_try0(repl_id, timeout_s=10)` | step `try0` + back | `{ok, found, tactic?, output}` |
| `isabelle_find_theorems(repl_id, query, max_results=20)` | `Ir.find_theorems` | `{ok, count, theorems[]}` |
| `isabelle_nitpick(repl_id, timeout_s=30)` | step `nitpick` + back | `{ok, result, output}` |
| `isabelle_quickcheck(repl_id, timeout_s=10)` | step `quickcheck` + back | `{ok, found_counterexample, output}` |
| `isabelle_thm_deps(name, repl_id)` | step `thm_deps <name>` + back | `{ok, dependencies[]}` (advanced-gated) |

`isabelle_thm_deps` is gated behind `ISABELLE_MCP_EXPOSE_ADVANCED=1` (spec §4).

## Tasks

### Task 1: IRSession Layer C protocol methods
- `find_theorems(repl_id, query, max_results) -> dict` → `Ir.find_theorems`.
- `sledgehammer(repl_id, timeout_secs) -> dict` → `Ir.sledgehammer`.
- `run_diagnostic(repl_id, command, timeout_secs) -> dict` → `Ir.step` the Isar
  command; on success `Ir.back` to drop the recorded step; return the captured
  body. On ERR, no back (no step appended).
- Commit: `feat(ir_client): add Layer C protocol methods (find_theorems, sledgehammer, diagnostics)`.

### Task 2: Enable Bash.Server in IRManager
- `IRManager(bash_server=True default)` → pass to `launch_ir_daemon`.
- `server.manager_from_env`: honor `ISABELLE_MCP_NO_BASH_SERVER=1` to disable.
- Commit folded into Task 4.

### Task 3: IRManager Layer C operations + parsing (`errors`-mapped)
- Methods `try0`, `sledgehammer`, `find_theorems`, `nitpick`, `quickcheck`,
  `thm_deps`, each resolving the opaque id and returning a structured payload.
- Pure parsing helpers (unit-testable, no Isabelle):
  - `_strip_trailing_state(body)` — cut at first `proof (` / `goal (N subgoal`.
  - `parse_try0(body)`, `parse_sledgehammer(body)`, `parse_nitpick(body)`,
    `parse_quickcheck(body)`, `parse_find_theorems(body)`, `parse_thm_deps(body)`.
- Commit: `feat(lifecycle): Layer C operations with output parsing`.

### Task 4: Layer C MCP tools + server wiring
- `tools/layer_c.py`: `register_layer_c(mcp, manager)` with the six tools and
  spec-compliant descriptions; register `isabelle_thm_deps` only when
  `ISABELLE_MCP_EXPOSE_ADVANCED=1`.
- `server.build_server`: call `register_layer_c`; construct manager with
  `bash_server`. Update SKILL preamble to mention sledgehammer/try0/find_theorems.
- Commit: `feat(server): register Layer C automation tools`.

### Task 5: Tests, verify, tag
- Unit: parsing helpers in `tests/unit/test_layer_c_parsing.py` (no Isabelle).
- Integration `tests/integration/test_mcp_layer_c.py` (own port, bash_server):
  open REPL, state a goal, assert `try0`/`find_theorems`/`quickcheck`/`nitpick`
  behave; `sledgehammer` returns a one-liner (mark `heavy`).
- Update README tool list. Run `uv run pytest`. Tag `v0.0.0-m2`, push.

## Acceptance criteria
1. `uv run pytest` green (unit no-Isabelle; integration with Isabelle).
2. All six Layer C tools callable via MCP; `thm_deps` appears only with
   `ISABELLE_MCP_EXPOSE_ADVANCED=1`.
3. `isabelle_sledgehammer` returns a `one_liner` on a provable goal.
4. Tag `v0.0.0-m2` on the remote.

## Out of scope (later)
- Layer A file-anchored tools (M3); HTTP/SSE, sandbox, metrics (M4); full SKILL,
  Docker, E2E (M5). Sledgehammer minimization tuning and prover selection beyond
  defaults.
