# Isabelle/HOL tactic reference

Apply tactics with `isabelle_step(repl_id, isar="apply (<tactic>)")` or close a
goal with `by <tactic>` / `by (<tactic>)`. Race candidates with
`isabelle_multi_attempt`. Prefer the cheapest tactic that closes the goal.

## Closing / automation tactics

| Tactic | What it does | Reach for it when |
|---|---|---|
| `assumption` | Solves a goal already among the premises. | Goal literally matches a hypothesis. |
| `rule r` / `intro r` | Apply an intro/elim rule. | Driving a structured step manually. |
| `simp` | Rewrite with the simpset (+ `add:`/`del:`/`only:`). | Equational/rewriting goals. |
| `auto` | simp + classical reasoning across all subgoals. | General first attempt; may leave subgoals. |
| `blast` | Fast tableau prover (pure logic, no rewriting). | First-order logic, sets, relations. |
| `fastforce` | `auto`-style search that must close the goal. | One goal that `auto` almost solves. |
| `force` | Like `fastforce`, heavier single-goal search. | When `fastforce` is not quite enough. |
| `metis ls` | Resolution from the given lemmas only. | Applying a sledgehammer suggestion. |
| `meson` | Model-elimination first-order prover. | Pure FOL when `blast` stalls. |
| `arith` / `linarith` | Linear arithmetic over int/nat/real. | Goals that are pure linear (in)equalities. |
| `presburger` | Presburger arithmetic (int/nat, +, <, divisibility). | Integer arithmetic with quantifiers. |
| `algebra` | Commutative-ring/field equalities. | Polynomial identities. |
| `argo` / `smt` | SMT-backed (smt needs trust / external solver). | Mixed arithmetic + uninterpreted; last resort. |

## Tactic modifiers

- `simp add: l1 l2` — add lemmas to the simpset; `simp del: l` — remove;
  `simp only: ls` — use *only* these (precise, avoids loops).
- `auto simp add: ...` / `auto intro: ...` / `auto elim: ...` / `auto dest: ...`
  — feed extra rules to the classical reasoner.
- `(simp; fail)` — fail unless the goal is fully closed (good for scripting).
- Apply to one subgoal: `apply (simp)` acts on subgoal 1; use `prefer n` /
  `defer` to reorder, or `[1]`-style restrictions inside structured proofs.

## Structuring tactics (for `proof … qed`)

| Command | Purpose |
|---|---|
| `proof (induction x)` | Start an induction; one case per constructor. |
| `proof (cases "P")` | Split on a proposition or datatype. |
| `proof (rule r)` | Begin by applying intro rule `r`. |
| `case (Cons x xs)` | Name the current case + its bound variables. |
| `obtain x where "P x" using f by blast` | Eliminate an existential. |
| `moreover` / `ultimately` | Accumulate facts, then combine. |
| `also` / `finally` | Build a transitive `calc`-style chain (see isar-patterns). |
| `then`/`thus`/`hence` | Chain the previous fact into the next step. |

## Picking a tactic fast

1. `isabelle_try0` — it already sweeps simp/auto/blast/fastforce/force/metis.
2. If `try0` fails, `isabelle_multi_attempt(tactics=["by auto","by blast",
   "by force","by fastforce","by arith","by algebra"])` to see what bites.
3. Still open → `isabelle_find_theorems` for a missing lemma, then
   `by (simp add: <lemma>)` or `by (metis <lemma>)`.
4. Still open → `isabelle_sledgehammer`.
5. Still open → break it down with structured Isar and recurse on subgoals.

## Common pitfalls

- `simp` loops on a bad rewrite rule → switch to `simp only:` with an explicit
  set, or drop the offending lemma with `simp del:`.
- `metis`/`smt` from sledgehammer can be slow or fragile across versions; if a
  `metis` one-liner times out, re-run sledgehammer or prefer the `simp`/`auto`
  suggestion it also reports.
- `auto` leaving N subgoals is normal — inspect `isabelle_state` and attack each,
  rather than piling on more automation.
