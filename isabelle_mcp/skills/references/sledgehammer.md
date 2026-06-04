# Driving sledgehammer

`isabelle_sledgehammer` runs Isabelle's relevance filter + external ATPs
(E, Vampire, CVC, Z3, …) against the **current goal**, then reconstructs any proof
it finds into a one-liner you can paste back. It does not change the proof state.

## When to use it

- After `isabelle_try0` fails (try0 is cheaper and often enough).
- On a goal that needs library lemmas you can't name — sledgehammer finds them.
- **Not** as a first move, and not on a goal you haven't sanity-checked with
  nitpick/quickcheck (it will grind for a long time on a false goal).

## Reading the result

A successful run returns one or more suggestions, e.g.:

```
by (metis add.commute mult.assoc)
by (simp add: field_simps)
by (smt (z3) ...)
```

Apply one with `isabelle_step(repl_id, isar="by (metis add.commute mult.assoc)")`.

Preference among suggestions:

1. `by simp`/`by (simp add: …)` or `by auto` — most robust, fastest to re-check.
2. `by (metis …)` — usually fine; can be slow if it cites many lemmas.
3. `by (smt …)` — works but is the least portable across Isabelle versions and
   needs the SMT solver trusted; accept only if nothing else reconstructs.

## Tuning

- `timeout_s` — raise it (e.g. 120–300) for hard goals; lower it to fail fast
  while iterating. The server clamps to `ISABELLE_MCP_MAX_TIMEOUT_S`.
- If sledgehammer finds an ATP proof but reconstruction (`metis`/`smt`) fails or
  times out, re-run — relevance filtering is non-deterministic — or feed the
  cited lemmas into `find_theorems` and build the proof yourself.
- A goal too big for sledgehammer usually means **decompose first**: split with
  structured Isar (`cases`/`induction`/intro rules) and hammer the leaves.

## Requirements / gotchas

- Sledgehammer needs the Bash server, which the MCP daemon launches by default.
  If `ISABELLE_MCP_NO_BASH_SERVER=1` is set, the ATPs are disabled and this tool
  will report it is unavailable.
- External provers must be installed in the Isabelle distribution (they ship with
  the standard Isabelle bundle; a stripped image may lack some).
- Sledgehammer only sees theories loaded in the current session. To make it cite
  AFP lemmas, open the REPL on a session that imports them — see
  `skill://isabelle/afp-and-search`.
