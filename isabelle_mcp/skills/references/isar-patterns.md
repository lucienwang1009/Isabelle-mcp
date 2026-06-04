# Structured Isar proof patterns

Send each line as its own `isabelle_step`. Structured proofs are more robust than
long `apply` chains: named facts make failures local and re-usable. Keep the
theorem statement exactly as asked.

## Skeleton

```isabelle
theorem t: "P x"
proof -
  have h1: "A" by simp
  have h2: "B" using h1 by blast
  show "P x" using h1 h2 by auto
qed
```

`proof -` starts a proof with no automatic initial rule. `proof` (no `-`) applies
the default intro rule for the goal's connective first.

## Induction

```isabelle
lemma "length (xs @ ys) = length xs + length ys"
proof (induction xs)
  case Nil
  show ?case by simp
next
  case (Cons a xs)
  show ?case using Cons.IH by simp
qed
```

- One `case` per constructor; `next` separates them.
- `Cons.IH` is the induction hypothesis; `Cons.prems` are the case premises.
- For numbers: `proof (induction n)` gives `0` and `Suc n` cases.
- Stronger schemes: `induction xs rule: rev_induct`, `induction n rule:
  nat_less_induct`, or `induction … arbitrary: y` to generalise a variable.

## Case split

```isabelle
proof (cases "x = 0")
  case True
  then show ?thesis by simp
next
  case False
  then show ?thesis by (auto simp: ...)
qed
```

For datatypes: `proof (cases xs)` → `Nil` / `Cons` cases. `case True` binds the
fact `True: "x = 0"` for use via `then`/`using`.

## Existentials and obtain

```isabelle
have "∃k. n = 2 * k" using assms by ...
then obtain k where "n = 2 * k" by blast
```

`obtain … where … by <tac>` discharges the existential and introduces the witness
`k` plus its property for the rest of the block.

## Calc chains (`also`/`finally`)

```isabelle
have "a = b"   by ...
also have "... = c" by ...
also have "... ≤ d" by ...
finally show "a ≤ d" .
```

`...` refers to the right-hand side of the previous step. `finally` combines the
chain via transitivity; the trailing `.` is `by this`.

## Accumulating facts

```isabelle
have "A" by ...
moreover have "B" by ...
moreover have "C" by ...
ultimately show "A ∧ B ∧ C" by blast
```

## Fixing and assuming

```isabelle
proof (rule allI, rule impI)
  fix x assume a: "P x"
  show "Q x" using a by ...
qed
```

Or let `proof` pick the intro rules: for `"⋀x. P x ⟹ Q x"` just write `proof`
then `fix x assume "P x"`.

## Tips

- Use `?thesis` to refer to the current goal, `?case` inside an induction/case.
- Name every non-trivial intermediate fact (`have h: "…"`) so later steps cite it
  explicitly — this survives refactoring better than `then`.
- When a `show` fails, `isabelle_state` to see the exact expected goal; mismatched
  `show` statements are the most common structured-proof error.
- Drafting: prove the shape with `sorry` placeholders **only locally while
  exploring**, then replace every `sorry` before declaring the proof done — a
  `sorry` left in fails the quality gate.
