# Searching for lemmas — `find_theorems` and the AFP

The single biggest win in Isabelle proving is **reusing existing lemmas**. Search
before you write tactics.

## `isabelle_find_theorems` (in-session search)

Searches the theories currently loaded in your REPL session. Query forms (combine
them — they AND together):

| Query | Finds |
|---|---|
| `"_ + _ = _ + _"` | Lemmas whose conclusion matches the pattern (`_` = wildcard). |
| `name: comm` | Lemmas whose name contains `comm`. |
| `"comm" intro` | Lemmas usable as introduction rules about that pattern. |
| `simp: "_ mod _"` | Simp rules rewriting `_ mod _`. |
| `dest: "_ ∈ set _"` | Destruction rules. |
| `(100) "_ ≤ _"` | Cap results at 100. |

Workflow: find a candidate, then cite it — `by (simp add: foo)`,
`by (metis foo bar)`, or `apply (rule foo)`.

Tips:
- Search by the **shape of your goal**, not by English. Pattern queries on the
  goal's conclusion are the most productive.
- Combine a pattern with `name:` to narrow a flooded result set.
- `find_consts` (via `isabelle_run_code` if needed) locates a constant when you
  don't know its exact name.

## The Archive of Formal Proofs (AFP)

The AFP (<https://www.isa-afp.org/>) is Isabelle's large peer-reviewed library —
the analogue of Lean's mathlib. If a result is more advanced than core `HOL`
(number theory, analysis, algebra, automata, complexity, crypto, …), it likely
lives in an AFP **entry** (a named session).

### Browsing / discovering entries

- Topic index: <https://www.isa-afp.org/topics/> — browse by area.
- Full-text search: <https://www.isa-afp.org/search/> — search statements/names.
- Each entry page lists its session name, theories, and dependencies.

Examples of entries that come up in CS theory work:

| Topic | AFP entry (session) |
|---|---|
| Cook–Levin theorem / SAT NP-completeness | `Cook_Levin` |
| Propositional/Resolution proof systems | `Propositional_Proof_Systems` |
| Regular languages / automata | `Regular-Sets`, `Functional_Automata` |
| Graph theory | `Graph_Theory` |

(Always confirm the exact session name on the entry's AFP page.)

### Local AFP source index

For broad AFP discovery, download the current AFP sources into the local cache
and build a lightweight source index without building AFP heaps:

```bash
uv run isabelle-mcp afp-bootstrap
uv run isabelle-mcp afp-status
uv run isabelle-mcp afp-search "finite automata"
```

If AFP sources are already available locally, index that checkout instead:

```bash
uv run isabelle-mcp afp-index --afp-root /path/to/afp/thys
uv run isabelle-mcp afp-search "finite automata"
uv run isabelle-mcp afp-search "name:comm kind:lemma"
```

For one-shot local setup, `bash scripts/bootstrap.sh --with-afp` performs the
same download/extract/index step; `--afp-root /path/to/afp/thys` reuses an
existing checkout. Inside MCP, use `isabelle_afp_status()` to check readiness and
`isabelle_afp_search(query)` for the discovery step.

The index stores source-level facts
(entry/session/theory/path/imports/declaration statement/snippet). It does
**not** prove that a lemma is available in the running I/R session. After
finding a candidate, load/build the relevant session and confirm with
`isabelle_find_theorems`.

### Using an AFP entry from a theory

1. Download the AFP and register it as an Isabelle component (once):

   ```bash
   isabelle components -u /path/to/afp/thys
   ```

2. Import the entry's theory with the `Session.Theory` syntax:

   ```isabelle
   theory My_Work
     imports "Cook_Levin.Satisfiability"
   begin
   ```

3. In a `ROOT` file, declare the dependency so the session builds:

   ```
   session My_Session = Cook_Levin +
     theories My_Work
   ```

### Reaching AFP lemmas from this MCP server (current limitation)

`isabelle_find_theorems` and `isabelle_sledgehammer` only see theories loaded in
the **current session image**. The default session is `HOL`, which does **not**
include the AFP. To search/cite AFP lemmas:

- In a ROOT project, make the project session depend on the AFP entry, run
  `isabelle_check_project(root=..., session=...)`, then open the REPL with
  `session=...` and `session_dirs=[...]`.
- For a server-wide default, set `ISABELLE_MCP_SESSION` to a session image that
  imports the entry you need. The image must be built first with
  `isabelle build`.

For the full download → build → `ISABELLE_MCP_SESSION` workflow (and the
discovery-vs-availability distinction), see `skill://isabelle/afp-setup`. Until a
heap is built, treat the AFP as a *reference* you read to find the right lemma
name, then reproduce or import that lemma in a session the server can load.

## Reality check on hard targets

Big theorems (e.g. proving 3-SAT is NP-complete via Cook–Levin) are **not**
something the tactic cascade closes autonomously. The realistic path is: find the
relevant AFP entry, build/load a session that includes it, and *navigate and
extend* the existing formalization — not derive it from scratch with sledgehammer.
