# Falsifying goals: nitpick and quickcheck

Before investing in a proof, check the goal is even true. A found counterexample
means **the statement is wrong** — fix the statement (or add the missing
hypothesis), don't keep attacking the proof.

## `isabelle_quickcheck`

Fast randomised + exhaustive testing of the current goal over small values.

- Cheap; run it routinely on any goal you're unsure of.
- Reports a concrete assignment that violates the goal, e.g.
  `x = 1, y = 0` falsifies `x * y = x`.
- "No counterexample found" is *evidence*, not proof — it only tested small
  cases. Proceed to prove it.
- Works only on executable goals (functions with code equations); purely abstract
  goals fall back to nitpick.

## `isabelle_nitpick`

Searches for a finite model that refutes the goal (SAT/model-finding based).

- Handles more abstract goals than quickcheck (sets, relations, records).
- Reports a counterexample model, or "no counterexample" within the scope it
  searched, or that it couldn't decide.
- Slower than quickcheck; use it when quickcheck can't run or finds nothing but
  you still doubt the goal.

## Workflow

1. State the goal with `isabelle_step`.
2. `isabelle_quickcheck` → if it finds a counterexample, **stop and fix the
   statement.**
3. If quickcheck is clean or inapplicable, `isabelle_nitpick`.
4. Both clean → the goal is plausibly true; proceed to the tactic cascade.

## Reading the result

- A counterexample lists variable bindings making the premises true and the
  conclusion false. Often it reveals a missing assumption (e.g. `x ≠ 0`,
  `finite A`, `sorted xs`) that belongs in the statement.
- "Potentially spurious" / "quasi-genuine" from nitpick means it used an
  unsound approximation — verify by hand before trusting it.

## Anti-patterns

- ❌ Ignoring a genuine counterexample and burning sledgehammer time on a false
  goal.
- ❌ Treating "no counterexample found" as a proof.
- ❌ Editing the *conclusion* to dodge a counterexample when the real fix is an
  added hypothesis — and only if changing the statement is permitted.
