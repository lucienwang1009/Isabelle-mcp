# isabelle-mcp — Design Spec

- **Date:** 2026-05-28
- **Status:** Draft for review
- **Target version:** v0.1
- **Owners:** TBD

## 1. Goals & non-goals

### Goals

- Ship an MCP server (`isabelle-mcp`) that exposes Isabelle/HOL to general-purpose LLMs (Claude, GPT) **without fine-tuning**.
- Support **autonomous theorem proving** as the primary use case: an LLM iteratively proposes tactics, observes Isabelle's response, and refines.
- Snapshot/branching state semantics: an LLM can fork a proof state, try alternatives, and backtrack — implemented via I/R's branching REPL model.
- Ship with rich enough automation (`sledgehammer`, `try0`, `find_theorems`, `nitpick`, `quickcheck`) that an unfine-tuned LLM has real chances of closing non-trivial goals.
- Be installable in one command: `uvx isabelle-mcp`.
- Run in Claude Code, Cursor, VS Code MCP, and any stdio-MCP client out of the box.

### Non-goals (v0.1)

- AFP support out-of-box. Users wire their own ROOT/session config; we don't ship pre-built AFP images.
- Multi-tenant / hosted version.
- Snapshot persistence across daemon restarts. After a crash, REPLs are re-opened by the LLM.
- A built-in proof-search agent. We provide tools; consumers build search.
- Web UI or dashboard.
- Interactive co-write features (real-time hover-while-typing). The MCP is request/response.
- LLM fine-tuning. We target prompt+tool usage by general LLMs only.

## 2. Background & related work

- **PISA / QIsabelle** — Scala bridges around Isabelle/ML's `Toplevel.state`, originally from Cambridge. Powerful snapshot model; pinned to old Isabelle releases; high maintenance burden.
- **lean-lsp-mcp** ([oOo0oOo/lean-lsp-mcp](https://github.com/oOo0oOo/lean-lsp-mcp)) — file-anchored MCP server for Lean. Demonstrates that LSP-style position-anchored tools (`goal`, `hover`, `multi_attempt`) are sufficient for many LLM proving workflows. Source of patterns: `uvx` install, three transports, env-var config, path sandboxing, Docker, per-tool disable.
- **AutoCorrode / I/R** ([awslabs/AutoCorrode](https://github.com/awslabs/AutoCorrode)) — MIT-licensed AWS Labs project for Isabelle/HOL verification. Its `ir/` directory **is already an Isabelle MCP server**: HTTP MCP transport (port 9148) + token-auth TCP REPL (9147), built on Isabelle 2025-2, stateful branching REPL model, integrated sledgehammer and `find_theorems`. This eliminates the need to fork PISA. We build on top of I/R.

## 3. Architecture

Three logical layers in a single Python package, backed by AutoCorrode's I/R.

```
┌────────────────────────────────────────────────────┐
│  LLM client  (Claude Code / Cursor / VS Code MCP)  │
└───────────────┬────────────────────────────────────┘
                │ MCP (stdio default; http/sse opt.)
                ▼
┌────────────────────────────────────────────────────┐
│  isabelle-mcp   (Python, FastMCP, uvx)             │
│                                                    │
│  Layer A — file-anchored (composed over I/R)       │
│    isabelle_file_outline / diagnostics / goal_at   │
│    isabelle_hover / run_code / multi_attempt       │
│                                                    │
│  Layer B — REPL / snapshot (passthrough)           │
│    isabelle_open_repl / step / undo                │
│    isabelle_fork_repl / state / close_repl         │
│                                                    │
│  Layer C — automation                              │
│    isabelle_sledgehammer / find_theorems           │
│    isabelle_try0 / nitpick / quickcheck            │
│    isabelle_thm_deps                               │
│                                                    │
│  Cross-cutting                                     │
│    path sandbox | timeouts | structured logging    │
│    auth (bearer/token, http only)                  │
│    per-tool disable env var                        │
│    bundled SKILL surfaced via MCP instructions     │
└───────────────┬────────────────────────────────────┘
                │ HTTP / TCP (loopback)
                ▼
┌────────────────────────────────────────────────────┐
│  I/R   (vendored as git submodule under vendor/ir) │
│   repl.py + ir.ML + tcp_handler.ML                 │
└───────────────┬────────────────────────────────────┘
                ▼
        Isabelle2025-2 with HOL prebuilt
        user ROOT + .thy (mounted)
```

### Key decisions

- **Vendor I/R as a git submodule** under `vendor/ir/`; pin a commit. Switch to upstream PyPI when AWS publishes one.
- **Python-only on our side.** No JVM code. Layer C ML helpers (~20 lines each for `try0`/`nitpick`/`quickcheck`/`thm_deps`) live in `isabelle_mcp/ml/extras.ML`, loaded via Isabelle's `ML_file` at I/R boot.
- **Stdio transport added by us.** I/R only supports HTTP today. We implement stdio in our Python layer and proxy to I/R's loopback HTTP. Upstream the stdio support as a PR.
- **Layer A is orchestration over Layer B.** No new ML for the file-anchored tools beyond a one-time goal-extractor helper.
- **Layer B passthrough** with stable, MCP-friendly schemas. We do not expose I/R's internal handles; `repl_id` is a server-issued UUID.
- **No raw ML eval by default.** `isabelle_run_code` runs Isar/HOL only. ML opt-in behind `ISABELLE_MCP_ALLOW_ML=1`, with a guard module that overrides side-effecting primitives.

## 4. MCP tool surface

### Layer A — file-anchored

```
isabelle_file_outline(path: str)
  → {imports: [str],
     theorems: [{name, kind, line, statement_preview}],
     definitions: [...], lemmas: [...]}

isabelle_diagnostics(path: str,
                     severity?: "error"|"warning"|"info"|"hint",
                     interactive?: bool)
  → [{line, col, severity, message, source}]

isabelle_goal_at(path: str, line: int, col?: int)
  → {goals: [{id, hypotheses: [{name, term}],
              conclusion, schematic_vars, free_vars}],
     pretty: str, proof_context_size}

isabelle_hover(path: str, line: int, col: int)
  → {kind, signature, doc?, defined_at?: {path, line}}

isabelle_run_code(code: str, session?: str, timeout_s?: int=30)
  → {ok, output, errors: [str], elapsed_ms}

isabelle_multi_attempt(path: str, line: int, col?: int,
                       tactics: [str], timeout_s?: int=15)
  → [{tactic, ok, remaining_goals,
      goal_preview?, error?, elapsed_ms}]
```

### Layer B — REPL / snapshot

```
isabelle_open_repl(
    at: {theory: str} | {theory: str, line: int}
        | {parent_repl_id: str},
    session?: str)
  → {repl_id, goal_summary?}

isabelle_step(repl_id, isar: str, timeout_s?: int=60)
  → {ok, new_goals?, output, error?, elapsed_ms}

isabelle_undo(repl_id, n?: int=1)
  → {steps_undone, current_goal_summary?}

isabelle_fork_repl(repl_id)
  → {repl_id}    # independent state, shares prefix history

isabelle_state(repl_id)
  → {history: [str], current_goals, at_end_of_proof: bool}

isabelle_close_repl(repl_id)
  → {ok}
```

### Layer C — automation

```
isabelle_sledgehammer(repl_id, timeout_s?: int=120,
                      provers?: [str], minimize?: bool=true)
  → {found, isar_proof?, one_liner?,
     provers_succeeded: [str], elapsed_ms}

isabelle_try0(repl_id, timeout_s?: int=10)
  → {found, tactic?, candidates_tried: [str], elapsed_ms}

isabelle_find_theorems(repl_id?, query: str, max_results?: int=20)
  → [{name, statement, module}]

isabelle_nitpick(repl_id, timeout_s?: int=30)
  → {result: "counterexample"|"none_found"|"unknown",
     model?, elapsed_ms}

isabelle_quickcheck(repl_id, timeout_s?: int=10)
  → {counterexample?, tries: int, elapsed_ms}

isabelle_thm_deps(name: str, repl_id?)
  → {axioms: [str], theorems: [str]}
  # behind ISABELLE_MCP_EXPOSE_ADVANCED=1
```

### Default-exposed vs advanced

By default the LLM sees ~10 tools (the most useful ones). The following are gated behind `ISABELLE_MCP_EXPOSE_ADVANCED=1`:

- `isabelle_thm_deps`
- `isabelle_hover` (kept enabled by default — borderline; revisit after smoke tests)
- `isabelle_file_outline` (same)

The `ISABELLE_MCP_DISABLED_TOOLS` env var (comma-separated tool names) overrides on either side.

### Cross-cutting contracts

- All tools return `{ok}` at top level; failure is `{ok: false, error: {code, message, correlation_id}, hint?}`.
- Long-running tools accept `timeout_s` (server-clamped to `ISABELLE_MCP_MAX_TIMEOUT_S`, default 600).
- Goal previews truncated to `ISABELLE_MCP_MAX_PREVIEW_CHARS` (default 4000). Full state via `isabelle_state`.
- `repl_id` is an opaque server UUID; not I/R's internal handle.

### Explicitly not exposed

- File mutation. LLM uses normal Edit/Write on `.thy` files; MCP only reads.
- Raw ML eval (default).
- Remote-search wrappers (no `LeanSearch`-equivalent exists for Isabelle yet).

## 5. LLM ergonomics

### Bundled SKILL

Path: `isabelle_mcp/skills/isabelle-proving.md`. Surfaced via the MCP `instructions` field at session init, and discoverable by skill-aware clients. Contents:

1. **When to use.** "You're editing or extending Isabelle/HOL theories and need to make proofs go through."
2. **Standard autonomous-proving loop.**
   1. `isabelle_diagnostics(path)` — find unproved goals.
   2. `isabelle_goal_at(path, line)` — read the goal.
   3. `isabelle_try0` first (cheap).
   4. `isabelle_multi_attempt` with 3–5 candidate tactics.
   5. `isabelle_sledgehammer` (60–120s budget).
   6. If stuck: `isabelle_find_theorems` for relevant lemmas → retry step 4. Or `isabelle_nitpick` to check the goal is even true.
3. **State discipline.** At most one REPL per active proof. Close with `isabelle_close_repl`. Fork only when truly branching.
4. **Anti-patterns.** Sledgehammer-first; multi-line Isar inside `step`; ignoring nitpick counterexamples.

### Per-tool descriptions

Every tool ships with an LLM-facing description containing: plain-language purpose, when vs related tools, one example. Template enforced in code review.

### Structured goal representation

Goals returned as `{hypotheses: [{name, term}], conclusion, schematic_vars, free_vars}` plus a `pretty` string fallback. Costs one ML helper that walks the PIDE markup.

### Hints on failure

Every error code has 0–2 static hint strings curated up-front; no LLM-in-the-loop reasoning to generate.

### MCP `instructions` preamble

~200-word preamble served at session init, summarizing the proving loop. Reaches clients that don't auto-load skills.

### Residual difficulty (honest)

- Isar syntax mistakes by general LLMs — partially mitigated by `multi_attempt`.
- AFP / HOL library familiarity — `find_theorems` helps, but only if LLM searches.
- Goal-state size for locales / induction — truncation + `isabelle_state` paging.

## 6. Errors, timeouts, lifecycle

### Error taxonomy

Stable codes the LLM can branch on:

| Code | When | Recoverable? |
|---|---|---|
| `file_not_found` | Path missing or outside sandbox | No |
| `session_not_started` | HOL image not built | Yes |
| `parse_error` | Isar/HOL syntax bad | Yes |
| `tactic_failed` | `step` didn't change goals | Yes |
| `timeout` | Hit `timeout_s` or ceiling | Sometimes |
| `repl_not_found` | Stale `repl_id` | No |
| `repl_in_proof` | `step` past `qed` | Yes |
| `proof_not_open` | Tactic outside `proof` block | Yes |
| `ir_unavailable` | I/R daemon crashed | Server-side |
| `ml_disabled` | Raw ML attempted, `ALLOW_ML=0` | No |
| `internal_error` | Else | No |

### Timeouts — three layers

1. **Per-call** (`timeout_s` argument). Defaults: `step=60`, `multi_attempt=15`/tactic, `sledgehammer=120`, `nitpick=30`, `try0=10`, `run_code=30`.
2. **Server ceiling** (`ISABELLE_MCP_MAX_TIMEOUT_S`, default 600).
3. **Idle REPL TTL** (`ISABELLE_MCP_REPL_TTL_S`, default 1800).

On per-call timeout: **interrupt** at Isabelle layer (`Toplevel.interrupt` / Future cancellation via I/R) — do not kill the daemon.

### REPL lifecycle

```
open_repl ── ok ──▶ live ──┬── step OK ──▶ live
                            ├── step error ──▶ live (state unchanged)
                            ├── timeout ──▶ live (interrupt handled)
                            ├── qed / done ──▶ at_end_of_proof
                            ├── close_repl ──▶ closed
                            └── idle TTL ──▶ closed
```

Forks are reference-counted; closing a parent does not kill live children. A cleanup task drops expired REPLs each minute. Metrics over `GET /metrics` (Prometheus-style).

### Recovery from I/R crashes

1. **Detect** via 30s heartbeat to loopback; three misses → dead.
2. **Restart** I/R; HOL image survives.
3. **Invalidate** all `repl_id`s issued by the dead daemon; subsequent calls return `repl_not_found`.
4. **Tell the LLM** via one-shot `server_event: "restarted"` on the next call. SKILL says "reopen REPLs and resume."

No checkpoint/replay across restarts.

### Resource safety

- Path sandbox allow-list: project root, `$ISABELLE_HOME/src`, optional AFP root.
- ML eval disabled by default. With `ALLOW_ML=1`, ML guard module overrides `OS.Process.system` and unsandboxed `TextIO`.
- `ISABELLE_MCP_OFFLINE=1` blocks sledgehammer's remote ATPs; bundled local ATPs (CVC4, Z3, E, Vampire) only.
- Docker: cgroup memory limits. Outside Docker: `RLIMIT_AS` on the I/R subprocess.

### Logging

Single structured-JSON log to stderr. Fields: `ts, level, correlation_id, tool, repl_id?, latency_ms, ok, error_code?`. No goal text or file content in logs. One `--log-level` flag, `ISABELLE_MCP_LOG_LEVEL` env var.

## 7. Testing strategy

### Unit tests (Python, pytest, no Isabelle)

- Schema validation against JSON Schema.
- Path-sandbox enforcement (`../`, `/etc/`, symlinks).
- Error mapping from mock I/R responses.
- Timeout clamping.

### Integration tests (Python + real Isabelle)

- Boot with prebuilt HOL; run each tool against fixture `.thy` files in `tests/fixtures/`.
- Happy path per tool; documented failure modes.
- Sledgehammer gated behind `RUN_HEAVY=1`.

### E2E LLM smoke

- Scripted Claude/GPT session asked to prove ~10 fixture lemmas via MCP+SKILL only.
- Pass: ≥7/10 closed without human intervention.
- Lemmas in scope for general LLMs (Nat arithmetic, list induction, basic set algebra).
- Transcripts checked into `tests/e2e-transcripts/`; success-rate regression diff per release.

## 8. Milestones

| M | Scope | Done when | ETA |
|---|---|---|---|
| M0 — Spike | Vendor I/R; boot HOL; drive `Ir.init / step / close` over loopback from Python. | A Python script proves `lemma "1 + 1 = (2::nat)"` end-to-end. | week 1 |
| M1 — MCP minimal | FastMCP wrapping Layer B (`open_repl / step / undo / close_repl / state`). Stdio transport. SKILL stub. | `uvx isabelle-mcp` works in Claude Code; human drives a proof. | weeks 2–3 |
| M2 — Automation | Layer C: `try0 / sledgehammer / find_theorems / nitpick / quickcheck / thm_deps`. `extras.ML` loaded at boot. | All Layer C tools pass integration; sledgehammer returns one-liners. | week 4 |
| M3 — File-anchored | Layer A: `file_outline / diagnostics / goal_at / hover / run_code / multi_attempt / fork_repl`. Structured goal repr. | Layer A passes integration on fixtures. | weeks 5–6 |
| M4 — Hardening | HTTP+SSE transport. Sandbox, idle-TTL cleanup, crash-restart, metrics, per-tool disable. | 24h soak ≤ 5% memory growth; daemon restart recovers ≤ 30s. | week 7 |
| M5 — Ergonomics & ship | Full SKILL. Polished descriptions. Docker. README. E2E ≥7/10. Upstream PRs to AutoCorrode (stdio, try0). | First public `0.1`. | week 8 |

**Total: ~8 weeks** for v0.1 at half-time. PISA-fork path would be ~6 months — I/R is the difference.

## 9. Unknowns to verify in Week 1

1. **I/R subprocess interface.** Confirm I/R can be spawned as a child of another Python process and driven via loopback HTTP cleanly (graceful shutdown, stderr capture).
2. **I/R `mcp_server.py` tool manifest.** Read it directly to map I/R's MCP methods to our Layer B passthroughs; adjust schemas if mismatched.
3. **Sledgehammer minimization.** Whether `Ir.sledgehammer` returns the minimized one-liner already or we need a follow-up `minimize` call.
4. **`find_theorems` without active REPL.** Whether it works against a loaded image only, or requires an open REPL.
5. **`ML_file` loading.** Whether I/R supports loading additional ML files at startup; if not, upstream a `--ml-extras` flag or preload via a theory.
6. **Goal-extraction from PIDE markup.** Confirm we can extract structured `hypotheses + conclusion` from the same markup I/R already parses.

## 10. Glossary

- **MCP** — Model Context Protocol; the LLM tool-use standard.
- **I/R** — Isabelle/REPL, the `ir/` directory in [awslabs/AutoCorrode](https://github.com/awslabs/AutoCorrode).
- **PIDE** — Prover IDE; Isabelle's protocol for surfacing typed markup (errors, goals, hovers) over a theory file.
- **REPL** (in I/R sense) — A list of Isar steps anchored at a theory location or another REPL. Stateful and branchable.
- **AFP** — Archive of Formal Proofs.
- **Sledgehammer** — Isabelle's external-ATP integration.
