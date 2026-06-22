---
name: isabelle-proving
description: >-
  Autonomous Isabelle/HOL theorem-proving loop for general LLMs driving the
  isabelle-mcp server: open a stateful REPL, state goals, search lemmas
  (find_theorems / sledgehammer / the AFP), drive Isar proofs one step at a
  time, falsify with nitpick/quickcheck, and close goals with the tactic
  cascade. Use whenever editing or extending `.thy` theories or making proofs
  go through. Not for Lean, Coq/Rocq, Agda, or other provers.
---

# Proving with isabelle-mcp

The server wraps a **stateful, branchable Isabelle/HOL REPL**. You build a proof
incrementally: each `isabelle_step` runs one Isar command and the returned proof
state is your feedback signal. Treat the type checker as your test suite — a goal
is proved only when Isabelle accepts it with no `sorry`/`oops`.

## Core principles

1. **Search before you prove.** Most facts already exist in the library. Run
   `isabelle_find_theorems` and `isabelle_sledgehammer` before hand-writing a
   proof. For results outside `HOL`, consult the **AFP** (see the
   `skill://isabelle/afp-and-search` resource).
2. **Build incrementally.** One Isar command per `isabelle_step`. Read the proof
   state after every step; never paste a whole script blind.
3. **Falsify before sinking time in.** Run `isabelle_nitpick` /
   `isabelle_quickcheck` on a doubtful goal first — a counterexample means the
   statement is wrong; fix the statement, don't fight the proof.
4. **Respect the statement.** Never weaken or rephrase the theorem to make it
   pass, and never fake success with `sorry`, `oops`, or `sorry`-backed lemmas.
   If a goal is genuinely false or needs an extra hypothesis, say so.
5. **Prefer structured Isar** for anything non-trivial. A `proof … qed` with
   named intermediate facts is more robust and readable than a long `apply`
   chain. See `skill://isabelle/isar-patterns`.

## The loop

1. **Open a REPL**: `isabelle_open_repl(theory="Main")` → opaque `repl_id`. Pass
   it to every later call. Import a richer session (e.g. `"Complex_Main"`) when
   you need more theories.
2. **State the goal**: `isabelle_step(repl_id, isar='theorem t: "P x"')`. The
   response shows the proof state and `at_end_of_proof`.
3. **Drive the proof**: one `isabelle_step` per Isar command (`by simp`,
   `apply auto`, `proof - … qed`, `next`, `qed`).
4. **Inspect**: `isabelle_state(repl_id)` returns history + open goals at any
   time. A step returning `at_end_of_proof: true` means the goal is closed.
5. **Backtrack**: `isabelle_undo(repl_id, n=1)` drops the last step(s);
   `isabelle_fork_repl(repl_id)` branches so you can try an alternative without
   losing the current line.
6. **Clean up**: `isabelle_close_repl(repl_id)` when finished.

## Tool reference

| Tool | Use |
|---|---|
| `isabelle_open_repl(theory)` | Start a branchable REPL session. |
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

`isabelle_multi_attempt(repl_id, tactics=["simp","auto","blast","force"])` races
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
| `skill://isabelle/tactics` | Choosing/ordering tactics; what each one does. |
| `skill://isabelle/isar-patterns` | Writing structured proofs: induction, cases, calc, obtain. |
| `skill://isabelle/sledgehammer` | Driving sledgehammer well and applying its output. |
| `skill://isabelle/afp-and-search` | Finding lemmas; using the **AFP** as a library. |
| `skill://isabelle/afp-setup` | Download/build the AFP and point the server at it. |
| `skill://isabelle/counterexamples` | nitpick/quickcheck workflow and reading output. |
| `skill://isabelle/errors` | Mapping `error.code` to a concrete fix. |

List them with the MCP resources API; fetch a resource to pull its full text
into context only when you need it.
