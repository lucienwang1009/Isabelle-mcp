# M1 — MCP Minimal (Layer B over stdio) Implementation Plan

**Goal:** Ship a working `isabelle-mcp` MCP server that exposes I/R's REPL
(Layer B) over the stdio transport, so a human can drive an Isabelle proof from
Claude Code / Cursor / any stdio-MCP client. Done when `uvx isabelle-mcp`
(or `uv run isabelle-mcp`) starts, advertises the Layer B tools, and a user can
open a REPL, step a proof to completion, inspect state, undo, and close.

**Builds on M0:** M0 proved we can spawn I/R and drive `init/step/remove` over
loopback TCP (`isabelle_mcp/ir_client.py`). M1 wraps that in an MCP server.

**Architecture (three concerns):**
1. `isabelle_mcp/errors.py` — stable error taxonomy + `{ok, ...}` envelopes +
   mapping from I/R plain-text errors to codes. Pure, no I/O.
2. `isabelle_mcp/lifecycle.py` — `IRManager`: owns the I/R daemon handle and a
   registry mapping **server-issued opaque UUID `repl_id`** → I/R's internal
   repl id. Exposes synchronous Layer B operations, each opening a short-lived
   authenticated `IRSession` (REPL state lives daemon-side, so per-call
   connections are safe and avoid concurrency hazards).
3. `isabelle_mcp/tools/layer_b.py` + `isabelle_mcp/server.py` — register six MCP
   tools on a `FastMCP` instance and run the stdio transport.

**Tech stack:** Python 3.11+, `uv`, `mcp` (official SDK, provides
`mcp.server.fastmcp.FastMCP`), `anyio`, `pytest`. Isabelle 2025-2 + prebuilt HOL
for integration tests (skipped otherwise, same as M0).

---

## Key design decisions

- **Opaque `repl_id`.** The spec (§4) requires `repl_id` be a server UUID, not
  I/R's handle. `IRManager` keeps the bidirectional map. Internally we name I/R
  repls `mcp_<hex>` to avoid collisions with user-driven ids.
- **Per-call TCP connection.** `IRSession.connect` authenticates per connection.
  Because all proof state is held by the daemon keyed by repl id, a fresh
  connection per tool call is correct. M4 may pool; M1 keeps it simple.
- **Sync core, async edge.** FastMCP tool callbacks are `async`. The Layer B
  operations are blocking socket I/O; tool callbacks wrap them in
  `anyio.to_thread.run_sync` so the event loop is never blocked.
- **Every tool returns an envelope** `{ok: bool, ...}`; failures are
  `{ok: false, error: {code, message, correlation_id}, hint?}` per spec §4.
- **`at_end_of_proof` / goal parsing reuses the M0-validated heuristic**
  (`proof_closed` logic): no `goal (N subgoal` line + a `theorem` toplevel line.
- **SKILL stub → MCP `instructions`.** The ~200-word proving-loop preamble
  (spec §5) is served via FastMCP's `instructions` field. Full SKILL is M5.
- **Daemon lifecycle.** Started lazily on first tool call (or at server start),
  terminated on server shutdown. If I/R is unreachable, tools return
  `ir_unavailable`.

## Tool surface (M1 subset of spec §4 Layer B)

| MCP tool | I/R call(s) | Returns |
|---|---|---|
| `isabelle_open_repl(at, session?)` | `Ir.init id [theory]` or `Ir.fork parent new idx` | `{ok, repl_id, goal_summary?}` |
| `isabelle_step(repl_id, isar, timeout_s?)` | `Ir.step id text` | `{ok, output, at_end_of_proof, error?}` |
| `isabelle_undo(repl_id, n?)` | `Ir.back id` ×n (`Ir.truncate`) | `{ok, steps_undone, current_goal_summary?}` |
| `isabelle_state(repl_id)` | `Ir.text id` + `Ir.state id -1` | `{ok, history, current_goals, at_end_of_proof}` |
| `isabelle_fork_repl(repl_id)` | `Ir.fork parent new -1` | `{ok, repl_id}` |
| `isabelle_close_repl(repl_id)` | `Ir.remove id` | `{ok}` |

`at` is `{"theory": str}` (e.g. `{"theory": "Main"}`) or
`{"parent_repl_id": str}`. `session?` is accepted but unused in M1 (single HOL
session); kept for forward-compat.

---

## Tasks

### Task 1: Add the `mcp` dependency
- `uv add mcp` (and confirm `anyio` already present from M0).
- Verify `uv run python -c "from mcp.server.fastmcp import FastMCP; print('ok')"`.
- Commit: `build: add mcp SDK (FastMCP) for the MCP server`.

### Task 2: Extend `IRSession` with Layer B protocol methods
Add to `isabelle_mcp/ir_client.py` (keep file < 400 lines; split if needed):
- `fork(self, parent_id, new_id, *, state_idx=-1) -> str` → `Ir.fork`.
- `undo(self, repl_id, *, n=1) -> dict` → call `Ir.back` n times (or
  `Ir.truncate`); return the last envelope.
- `state(self, repl_id) -> dict` → `Ir.state "id" ~1` (current pretty state).
- `history(self, repl_id) -> list[str]` → `Ir.text "id"`, split on newlines.
- Reuse `_send_command`/`_read_response`. ML int `-1` is written `~1`.
- Unit-test the ML-formatting helpers where pure; integration covers the rest.
- Commit: `feat(ir_client): add fork/undo/state/history Layer B methods`.

### Task 3: Implement `errors.py`
- `class ToolError(Exception)` carrying `code`, `message`, `hint?`.
- `ERROR_HINTS: dict[str, list[str]]` (0–2 hints per code, spec §6).
- `ok(**fields) -> dict` and `error_envelope(code, message, correlation_id, hint?) -> dict`.
- `map_ir_error(body: str) -> str` mapping observed I/R error text to codes
  (`parse_error`, `tactic_failed`, `timeout`, `repl_not_found`, …). Conservative
  default `internal_error`.
- Unit tests in `tests/unit/test_errors.py` (no Isabelle).
- Commit: `feat(errors): stable error taxonomy and MCP envelopes`.

### Task 4: Implement `lifecycle.py` `IRManager`
- `IRManager(isabelle_bin, ir_dir, session="HOL")` with `start()`, `close()`.
- UUID registry: `open(at) -> repl_id`, `step`, `undo`, `state`, `fork`,
  `close`. Each maps opaque→internal, opens an `IRSession`, runs the command,
  returns a plain dict envelope (using `errors.py`). Raises `ToolError` with
  `repl_not_found` for unknown ids; `ir_unavailable` if daemon down.
- A `goal_summary` helper truncating to `ISABELLE_MCP_MAX_PREVIEW_CHARS`
  (default 4000).
- Unit-test the registry/mapping with a fake session (no Isabelle); integration
  test covers real daemon.
- Commit: `feat(lifecycle): IRManager with opaque repl_id registry`.

### Task 5: Implement Layer B tools, server, stdio, SKILL stub
- `tools/layer_b.py`: `register_layer_b(mcp: FastMCP, manager: IRManager)`
  defining the six async tools (each wrapping `anyio.to_thread.run_sync`), with
  spec-compliant LLM-facing descriptions (purpose / when / one example).
- `server.py`: `build_server() -> FastMCP` (instructions preamble + register
  tools + construct `IRManager` from env: `ISABELLE_HOME`, optional
  `ISABELLE_MCP_SESSION`). `main()` runs `mcp.run()` (stdio default).
- `isabelle_mcp/skills/isabelle-proving.md`: replace placeholder with the
  ~200-word M1 proving-loop preamble; load its body into `instructions`.
- `transports/stdio.py`: thin helper if needed (FastMCP's `run()` already does
  stdio; keep module minimal or note it's covered by `server.run`).
- Commit: `feat(server): FastMCP Layer B server over stdio with SKILL preamble`.

### Task 6: Tests, manual smoke, verify
- `tests/unit/test_server_build.py`: `build_server()` returns a FastMCP whose
  tool list contains the six `isabelle_*` names (no Isabelle needed; construct
  manager lazily / patch start).
- `tests/integration/test_mcp_layer_b.py`: drive the **tool callables** end to
  end against real I/R — open REPL at `Main`, step
  `theorem t: "1+1=(2::nat)" by simp`, assert `at_end_of_proof`; `state`
  returns history; `undo` works; `fork`; `close`. Mark `integration`.
- Manual: `ISABELLE_HOME=… uv run isabelle-mcp` starts without error (smoke a
  `tools/list` via a tiny stdio client or `mcp` dev tooling if convenient).
- Run `uv run pytest -v` (unit + integration).
- Commit: `test(m1): unit + integration coverage for Layer B MCP server`.

### Task 7: Tag the milestone
- Update `README.md` Quick start with the `uvx isabelle-mcp` / client-config
  snippet.
- `git tag -a v0.0.0-m1 -m "M1: FastMCP Layer B over stdio"`, push main + tag.

---

## Acceptance criteria
1. `uv run pytest` → unit tests pass with no Isabelle; integration tests pass
   with Isabelle 2025-2 + HOL (else skip).
2. `ISABELLE_HOME=… uv run isabelle-mcp` starts a stdio MCP server advertising
   the six `isabelle_*` Layer B tools.
3. An integration test proves `1 + 1 = (2::nat)` *through the MCP tool layer*
   (not just `ir_client`), asserting `at_end_of_proof`.
4. Tag `v0.0.0-m1` on the remote.

## Out of scope for M1 (later milestones)
- Layer C automation (sledgehammer/try0/…) — M2.
- Layer A file-anchored tools — M3.
- HTTP+SSE transport, sandbox, idle-TTL, crash-restart, metrics — M4.
- Full SKILL, Docker, polished descriptions, E2E ≥7/10 — M5.
- Raw ML eval, `thm_deps`, advanced-gated tools.
