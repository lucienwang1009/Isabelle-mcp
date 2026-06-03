---
name: isabelle-proving
description: Standard autonomous-proving loop for LLMs using isabelle-mcp.
---

# Proving with isabelle-mcp

Use these tools when you are extending Isabelle/HOL theories and need to make
proofs go through. The server wraps a stateful, branchable Isabelle REPL.

## The loop

1. **Open a REPL** at a theory with `isabelle_open_repl(theory="Main")`. You get
   back an opaque `repl_id`; pass it to every other call.
2. **State the goal**: `isabelle_step(repl_id, isar='theorem t: "P x"')`. The
   response shows the current proof state and `at_end_of_proof`.
3. **Drive the proof** with one `isabelle_step` per Isar command (e.g.
   `by simp`, `apply auto`, `proof - … qed`). Send ONE command per step.
4. **Check progress**: when a step returns `at_end_of_proof: true`, the goal is
   closed. Use `isabelle_state(repl_id)` any time to see history + open goals.
5. **Backtrack** with `isabelle_undo(repl_id, n=1)` to drop the last step(s);
   `isabelle_fork_repl(repl_id)` to try an alternative without losing the
   current line.
6. **Clean up** with `isabelle_close_repl(repl_id)` when done.

## Discipline

- One REPL per active proof; close it when finished.
- One Isar command per `isabelle_step` — never paste a whole proof script.
- Read `error.code` on failure: `parse_error` (fix syntax), `tactic_failed`
  (the tactic didn't close the goal — inspect state, try another), `timeout`
  (raise `timeout_s` or simplify), `repl_not_found` (open a fresh REPL).

## Automation (use when stuck on a goal)

These inspect the current goal without changing it:

- `isabelle_try0(repl_id)` — cheap; tries simp/auto/blast/… and reports a
  one-liner if one closes the goal. **Try this first.**
- `isabelle_sledgehammer(repl_id, timeout_s=120)` — external provers search for
  a proof; returns `one_liner` tactics. Use when `try0` fails.
- `isabelle_find_theorems(repl_id, query=...)` — find lemmas to cite, then retry.
- `isabelle_nitpick(repl_id)` / `isabelle_quickcheck(repl_id)` — check whether
  the goal is even true (look for a counterexample) before sinking time into it.

When `try0`/`sledgehammer` returns a one-liner, apply it with `isabelle_step`.
Anti-patterns: reaching for sledgehammer first; ignoring a nitpick/quickcheck
counterexample.

- `isabelle_multi_attempt(repl_id, tactics=[...])` — try several tactics at once
  on isolated forks; it reports which close the goal without changing your REPL.

## Utilities

- `isabelle_file_outline(path)` — list a `.thy` file's imports and declarations
  with line numbers, to orient before editing.
- `isabelle_run_code(code)` — run one Isar command in a scratch context (no REPL
  bookkeeping) for a quick check.
