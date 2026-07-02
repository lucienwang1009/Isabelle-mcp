---
name: isabelle-proving
description: >-
  Project-scale Isabelle/HOL proof workflow for general LLMs using
  isabelle-mcp: inspect ROOT/session projects, build/check sessions, open the
  right theory, decompose large theorems into lemmas, drive stateful REPL proofs
  one Isar command at a time, search existing facts, falsify bad conjectures,
  write proofs back to `.thy` files, and finish with strict project checks. Use
  whenever editing or extending Isabelle `.thy` theories, proving a large
  theorem, debugging a failed proof, or working with custom ROOT sessions. Not
  for Lean, Coq/Rocq, Agda, or other provers.
---

# Proving with isabelle-mcp

Default to a **project-first proof workflow**, not a tool-tour. The MCP server
wraps a stateful, branchable Isabelle/HOL REPL, but the source `.thy` file and
`isabelle_check_project` are the source of truth. Use the REPL to explore and
stabilize proofs, then write them back and run a strict build.

## Operating Procedure

Follow this workflow for any non-trivial theorem.

1. **Locate the project context.**
   Inspect the relevant `.thy` file and nearby `ROOT`. If a custom session is
   present, do not work in scratch `Main`; use that session.

2. **Build or check the session first.**
   For a ROOT project, run `isabelle_check_project(root=..., session=...)`
   before opening a REPL. A session is not automatically rebuilt when theory
   files or ROOT files change.

3. **Open the right theory in the right session.**
   Use `isabelle_open_repl(theory=..., session=..., session_dirs=[...])` for
   custom projects. Use `theory="Main"` only for isolated HOL experiments.

4. **Validate the statement before investing.**
   If the theorem is a conjecture or has complex assumptions, run
   `isabelle_quickcheck` and/or `isabelle_nitpick` early. A counterexample means
   the statement needs attention; do not force a false theorem through.

5. **Decompose the large theorem.**
   Identify missing intermediate facts, induction invariants, case splits, and
   algebraic or set-theoretic cleanup lemmas. Prove these as named lemmas in the
   source file. Large proofs should become a sequence of small checked facts,
   not one opaque automation call.

6. **Prove each subgoal incrementally.**
   Send exactly one Isar command per `isabelle_step`. Read the resulting state
   after each step. Use `isabelle_fork_repl` to try risky branches, and
   `isabelle_undo` to back out locally.

7. **Search before hand-writing proof machinery.**
   Use `isabelle_find_theorems` in the loaded session. If the fact is likely
   outside the session, use `isabelle_afp_status` / `isabelle_afp_search` for
   discovery, then make sure the needed session is actually built and loaded.

8. **Use automation as a tactic, not a plan.**
   On each stuck goal, try `isabelle_try0`, then targeted theorem search, then
   `isabelle_multi_attempt`, then `isabelle_sledgehammer`. If automation does
   not close the goal, write structured Isar and recurse on the new subgoals.

9. **Write back and rebuild.**
   Once a REPL proof works, edit the `.thy` file, remove all scaffolding, then
   run `isabelle_check_file` and finally `isabelle_check_project`. The task is
   not done until the project build accepts the source.

## Core Principles

1. **The source file and project build are authoritative.** REPL success is
   useful exploration; `isabelle_check_project` is the final gate.
2. **One command at a time.** A step that bundles several Isar commands rolls
   back as a unit on failure, losing the useful prefix.
3. **Respect the statement.** Never weaken a theorem, add hidden assumptions,
   or rely on `sorry`/`oops` to claim success.
4. **Prefer structured Isar for large proofs.** Use `proof ... qed`, named
   intermediate facts, induction, cases, `obtain`, and `calc` rather than long
   brittle apply scripts. See `skill://isabelle/isar-patterns`.
5. **Search before inventing.** Most facts already exist in the loaded session,
   HOL libraries, or AFP. Use the search tools before hand-writing library
   lemmas.

## REPL Loop

1. **Open a REPL**: for scratch use `isabelle_open_repl(theory="Main")`; for a
   project use `theory` + `session` + `session_dirs`. The result is an opaque
   `repl_id`; pass it to every later call.
2. **State the goal**: `isabelle_step(repl_id, isar='theorem t: "P x"')`.
3. **Drive the proof**: one `isabelle_step` per Isar command (`by simp`,
   `apply auto`, `proof -`, `next`, `qed`).
4. **Inspect**: `isabelle_state(repl_id)` returns history and open goals.
5. **Branch or backtrack**: `isabelle_fork_repl(repl_id)` for alternatives;
   `isabelle_undo(repl_id, n=1)` for local rollback.
6. **Clean up**: `isabelle_close_repl(repl_id)` when finished.

## Tool reference

| Tool | Use |
|---|---|
| `isabelle_open_repl(theory)` | Start a branchable REPL session. Pass `session`+`session_dirs` (a pre-built local session) to open on your own project's theories instead of re-pasting definitions. |
| `isabelle_step(repl_id, isar)` | Run ONE Isar command; returns new state. |
| `isabelle_state(repl_id)` | Current goals + history (read-only). |
| `isabelle_undo(repl_id, n)` | Drop the last `n` steps. |
| `isabelle_fork_repl(repl_id)` | Branch to explore an alternative. |
| `isabelle_close_repl(repl_id)` | Release the session. |
| `isabelle_try0(repl_id)` | Cheap tactic sweep; **try this first when stuck.** |
| `isabelle_sledgehammer(repl_id, timeout_s)` | External provers; returns one-liners. |
| `isabelle_find_theorems(repl_id, query)` | Search the loaded library for lemmas. |
| `isabelle_afp_search(query)` | Search the local AFP source index for candidate lemmas (discovery only). |
| `isabelle_afp_status()` | Check whether the local AFP source cache/index is ready. |
| `isabelle_nitpick(repl_id)` | Look for a finite counterexample. |
| `isabelle_quickcheck(repl_id)` | Randomised/exhaustive counterexample search. |
| `isabelle_multi_attempt(repl_id, tactics)` | Race several tactics on isolated forks. |
| `isabelle_file_outline(path)` | List a `.thy`'s imports + declarations with lines. |
| `isabelle_check_project(root)` | Run `isabelle build` on a ROOT/session project and return build diagnostics. |
| `isabelle_check_file(path, session)` | Check a theory file; with `session`/`session_dirs`, uses project build. |
| `isabelle_run_code(code)` | Run one command in a throwaway scratch context. |

## Automation cascade (when stuck on a goal)

Try in order; stop on the first that closes the goal. Apply any returned
one-liner with `isabelle_step`.

```
isabelle_try0            # runs simp/auto/blast/metis/… — cheapest, do this first
↓ (didn't close)
isabelle_find_theorems   # find a lemma to cite, then: by (simp add: lemma) / (metis lemma)
↓
isabelle_afp_status      # check whether the local AFP source index is ready
↓
isabelle_afp_search      # discover AFP candidates when the loaded session is too small
↓
isabelle_sledgehammer    # external ATPs; paste back the suggested metis/smt one-liner
↓
structured Isar          # break the goal down (intro/cases/induction) and recurse
```

Raw tactic preference inside a step (rough order of cost):
`assumption`/`rule` → `simp` → `auto` → `blast` → `force`/`fastforce` →
`arith`/`presburger`/`linarith` → `algebra` → `metis`/`meson`. Full catalog with
when-to-use in `skill://isabelle/tactics`.

`isabelle_multi_attempt(repl_id, tactics=["by simp","by auto","by blast"])` races
these at once and reports which close the goal without mutating your REPL — a
fast way to pick a tactic.

## Quality gate

A proof is done when:

- the final `isabelle_step` reports `at_end_of_proof: true` (or `theorem`/`lemma`
  is accepted with no remaining subgoals);
- for edited files in a local session, `isabelle_check_project(root=...)` reports
  `checked: true`;
- there is **no** `sorry` or `oops` anywhere in the proof;
- the statement is unchanged from what was asked.

## Anti-patterns

- ❌ Reaching for `sledgehammer` before `try0`. ❌ Ignoring a nitpick/quickcheck
  counterexample. ❌ Pasting a multi-line proof into one `isabelle_step`.
- ❌ Long brittle `apply` chains where structured Isar would be clearer.
- ❌ Inserting `sorry`/`oops` and declaring victory. ❌ Editing the theorem
  statement to dodge a hard subgoal.
- ❌ Hand-writing arithmetic/set lemmas that `find_theorems` would have found.

## References (fetch on demand via MCP resources)

| Resource | Read when |
|---|---|
| `skill://isabelle/project-workflow` | Working in a ROOT/session project, proving a large theorem, coordinating multi-agent proof work. |
| `skill://isabelle/tactics` | Choosing/ordering tactics; what each one does. |
| `skill://isabelle/isar-patterns` | Writing structured proofs: induction, cases, calc, obtain. |
| `skill://isabelle/sledgehammer` | Driving sledgehammer well and applying its output. |
| `skill://isabelle/afp-and-search` | Finding lemmas; using the **AFP** as a library. |
| `skill://isabelle/afp-setup` | Download/build the AFP and point the server at it. |
| `skill://isabelle/counterexamples` | nitpick/quickcheck workflow and reading output. |
| `skill://isabelle/errors` | Mapping `error.code` to a concrete fix. |

List them with the MCP resources API; fetch a resource to pull its full text
into context only when you need it.
