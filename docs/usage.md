# isabelle-mcp — usage & pipelines

A practical guide to the tool surface and the workflows it supports. For setup
see [`m0-setup.md`](m0-setup.md); for the wire protocol see
[`ir-protocol-notes.md`](ir-protocol-notes.md).

## What it is

A Python MCP server (FastMCP; stdio or HTTP/SSE) that wraps a **stateful,
branchable Isabelle/HOL REPL** — the vendored AutoCorrode I/R daemon — over
loopback TCP. `IRManager` owns the daemon, hands out opaque `repl_id`s, reaps
idle REPLs, and recovers from crashes.

The guiding principle: **the type checker is your test suite.** A goal is proved
only when Isabelle accepts it with no `sorry`/`oops`. Build proofs one Isar
command at a time and read the returned proof state after every step.

## Tool surface (three layers)

| Layer | Tools | Purpose |
|---|---|---|
| **B — REPL state machine** | `isabelle_open_repl`, `isabelle_step`, `isabelle_state`, `isabelle_undo`, `isabelle_fork_repl`, `isabelle_close_repl` | Drive a proof one command at a time; inspect, branch, backtrack |
| **C — automation / search** | `isabelle_try0`, `isabelle_sledgehammer`, `isabelle_find_theorems`, `isabelle_nitpick`, `isabelle_quickcheck`, `isabelle_thm_deps` | Close goals automatically; find lemmas; falsify statements |
| **A — file / project** | `isabelle_file_outline`, `isabelle_check_file`, `isabelle_check_project`, `isabelle_run_code`, `isabelle_multi_attempt`, `isabelle_afp_search`, `isabelle_afp_status` | Inspect/build `.thy` files & sessions; race tactics; discover AFP |

`isabelle_thm_deps` is exposed only when `ISABELLE_MCP_EXPOSE_ADVANCED=1`.

## The core proving loop

```
isabelle_open_repl(theory="Main")          → repl_id        # "Complex_Main" etc. for more theories
  │
isabelle_step(repl_id, isar='theorem t: "…"')               # state the goal
  │   one Isar command per step; read the proof state each time
  ├─ by simp / by auto / proof - … qed / next / qed
  │
  └─ when stuck, the automation cascade (stop at the first that closes it):
        isabelle_try0                       # cheap simp/auto/blast/… sweep — do this first
          ↓
        isabelle_find_theorems(query=…)     # cite a library lemma: by (simp add: lem)
          ↓
        isabelle_afp_status / isabelle_afp_search   # discover AFP candidates
          ↓
        isabelle_sledgehammer(timeout_s=120)        # external ATPs; paste back the one-liner
          ↓
        structured Isar                     # intro/cases/induction and recurse
  │
isabelle_close_repl(repl_id)
```

Two moves to weave in:

- **Falsify before sinking time in.** Run `isabelle_nitpick` / `isabelle_quickcheck`
  on a doubtful goal first — a counterexample means the *statement* is wrong;
  fix it rather than fight the proof.
- **Race tactics cheaply.** `isabelle_multi_attempt(repl_id, tactics=[…])` runs
  each candidate on an isolated fork and reports which close the goal, **without
  mutating your REPL** — a fast way to pick a tactic.

Backtracking: `isabelle_undo(repl_id, n)` drops the last `n` steps;
`isabelle_fork_repl(repl_id)` branches so you can try an alternative without
losing the current line.

## Common pipelines

### 1. Interactive proof development (REPL)
The loop above. Develop definitions and lemmas in the REPL, typechecking as you
go, then **transcribe** the proven script into a `.thy` file.

### 2. Project verification (the authoritative gate)
For a local project with a `ROOT`, prefer the build checker over a plain REPL
load:

```
isabelle_check_project(root="proof/my_project")
isabelle_check_file(path="proof/my_project/My.thy", session="My_Project")
```

This runs `isabelle build` and returns structured `{checked, errors, warnings}`.
A proof is **done** only when this reports `checked: true` with no
`sorry`/`oops`/`axiomatization`. Explicitly named targets are trusted, so this
works on projects outside the server's working directory.

### 3. Tactic discovery
`isabelle_try0` → `isabelle_multi_attempt([...])` → `isabelle_sledgehammer`
(60–120 s budget); apply the returned `by (metis …)` / `by (smt …)` with a step.

### 4. Library / AFP lookup
`isabelle_find_theorems(query='name: rev')` or a pattern like
`'"_ + _ = _ + _"'` searches the loaded session. For the AFP, check
`isabelle_afp_status` then `isabelle_afp_search` — discovery only; a result
becomes citable once the matching AFP session is built and loaded.

### 5. Counterexample falsification
`isabelle_nitpick` (finite model finder) / `isabelle_quickcheck`
(randomised/exhaustive) before committing to a hard proof.

## Worked example

```text
open_repl(theory="Main")                                   → r
step(r, 'lemma rev_app: "rev (xs @ [x]) = x # rev xs"')    # goal stated
try0(r)                                                    # found? apply it
# if not:
multi_attempt(r, tactics=["by simp","by auto","by (induction xs) auto"])
step(r, "by (induction xs) auto")                          # at_end_of_proof: true
close_repl(r)
# then add the lemma to My.thy and:
check_project(root="proof/my_project")                     # checked: true
```

For larger developments, open the REPL **on your own session image** so your
project's theories are in scope instead of re-pasting definitions:

```
open_repl(theory="My_Theory", session="My_Project",
          session_dirs=["proof/my_project"])               # build the session first
```

(The daemon hosts one session at a time, so this relaunches it and invalidates
existing `repl_id`s — a `server_event` flags the switch.)

## Configuration (environment variables)

| Var | Purpose |
|---|---|
| `ISABELLE_MCP_SESSION` | Base session image the daemon loads (default `HOL`) |
| `ISABELLE_MCP_PORT` | I/R daemon TCP port (default 9147; if busy, the server auto-falls back to a free port) |
| `ISABELLE_MCP_TRANSPORT` | `stdio` (default), `sse`, `streamable-http` |
| `ISABELLE_MCP_NO_BASH_SERVER=1` | Disable sledgehammer's external ATPs (faster start) |
| `ISABELLE_MCP_ALLOW_ML=1` | Allow raw ML commands (`ML`, `ML_file`, `setup`, …); off by default |
| `ISABELLE_MCP_EXPOSE_ADVANCED=1` | Expose `isabelle_thm_deps` |
| `ISABELLE_MCP_DISABLED_TOOLS` | Comma-separated tool names to hide |
| `ISABELLE_MCP_ALLOWED_DIRS` | Extra allow-list roots for *incidental* reads (explicit check/build targets are already trusted) |
| `ISABELLE_MCP_REPL_TTL_S` | Idle-REPL TTL before reaping (default 1800) |
| `ISABELLE_MCP_MAX_TIMEOUT_S` | Per-call timeout ceiling (default 600) |
| `ISABELLE_MCP_MAX_PREVIEW_CHARS` | Output truncation (default 4000) |

## Anti-patterns

- ❌ Reaching for `sledgehammer` before `try0`.
- ❌ Ignoring a nitpick/quickcheck counterexample.
- ❌ Pasting a whole `proof … qed` block into one `isabelle_step` — it rolls back
  as a unit on failure, hiding the locus. One command per step. (To *sketch* a
  long proof you may `declare [[quick_and_dirty]]` once and use `sorry`, but
  remove every `sorry`/`oops` before `isabelle_check_project`.)
- ❌ Editing the theorem statement to dodge a hard subgoal, or declaring victory
  with a `sorry`/`oops` left in.

## Quality gate

A proof is finished when: the final `isabelle_step` reports
`at_end_of_proof: true`; `isabelle_check_project` reports `checked: true`; there
is **no** `sorry`/`oops`/`axiomatization` anywhere; and the statement is
unchanged from what was asked.
