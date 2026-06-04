# Setting up the AFP: download, build, and point the server at it

This is the operational companion to `skill://isabelle/afp-and-search`. It covers
how to make AFP lemmas actually **citable** in proofs through the MCP server.

## The key distinction: discovery vs. availability

| Goal | Needs sources? | Needs a built heap? |
|---|---|---|
| **Discover** a lemma's name/statement (grep, browse) | Yes (or isa-afp.org) | No |
| **Cite** it so `find_theorems`/`sledgehammer` see it | Yes | **Yes** |

There are **no prebuilt AFP heaps to download** — Isabelle ships only `HOL` (and
a few base heaps) prebuilt. Any entry you want to *prove against* must have its
session heap built locally once. You never build the whole AFP — only the target
entry plus its transitive dependencies.

## 1. Download the sources (once)

Get the AFP release **matching your Isabelle version** (e.g. AFP for
Isabelle2025-2) from <https://www.isa-afp.org/download/> and unpack it, e.g. to
`~/afp`. A version mismatch will not build. The sources are a moderate download;
having them is enough for discovery (grep) with no build.

## 2. Register it as a component (once)

```bash
isabelle components -u ~/afp/thys
```

This puts every AFP entry on Isabelle's session path.

## 3. Build only the entry you need (selective, one-time per entry-set)

```bash
isabelle build -b -v <Entry>        # -b builds the heap image; -v is verbose
isabelle build -b -v -j 4 <Entry>   # parallelise heavy builds
```

- A leaf entry with light deps builds in minutes; a deep one can take much longer
  and significant RAM/disk.
- The heap is **cached and reused** across all REPL sessions — it is a one-time
  cost per entry-set, not per proof.
- List available session names with `isabelle build -l`, or read the entry's page
  on isa-afp.org.

### Bundling several entries

Define a custom session that imports the entries you want, then build it:

```
# ~/my-afp/ROOT
session isabelle-mcp-afp = HOL +
  sessions
    Cook_Levin
    Regular-Sets
  theories
    "Cook_Levin.Satisfiability"
    "Regular-Sets.Regular_Exp"
```

```bash
isabelle build -b -v -d ~/my-afp isabelle-mcp-afp
```

## 4. Point the MCP server at the built heap

```bash
export ISABELLE_MCP_SESSION=Cook_Levin          # or: isabelle-mcp-afp
uv run isabelle-mcp
```

Now `isabelle_open_repl` starts in that image, and `isabelle_find_theorems` /
`isabelle_sledgehammer` can see and cite its lemmas. Confirm scope with
`isabelle_session_info` (when available) before relying on a lemma being present.

## 5. Docker: pre-bake instead of build-at-runtime

Building must never happen at request time (multi-GB, minutes-to-hours, can't run
in CI). For distribution, bake a curated heap into a Docker layer at image-build
time so users `docker pull` instead of building:

```dockerfile
RUN isabelle components -u /opt/afp/thys \
 && isabelle build -b -v -j "$(nproc)" Cook_Levin
ENV ISABELLE_MCP_SESSION=Cook_Levin
```

## Discovery without building

You do **not** need a heap to find out what exists:

- Grep the unpacked sources: `grep -rn "lemma .*satisfiab" ~/afp/thys/Cook_Levin/`
- `isabelle build -l` lists sessions; entry pages list theories/lemmas.
- isa-afp.org full-text search.

Use discovery to pick the right entry, then build it (step 3) only if you must
cite its lemmas rather than reproduce them.

## Checklist

1. AFP version matches Isabelle version. ✅
2. `isabelle components -u .../thys` run once. ✅
3. `isabelle build -b <Entry>` succeeded (heap exists). ✅
4. `ISABELLE_MCP_SESSION` set to that session before starting the server. ✅
5. `find_theorems` now returns the entry's lemmas. ✅
