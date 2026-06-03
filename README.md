# isabelle-mcp

MCP server exposing Isabelle/HOL to general-purpose LLMs (Claude, GPT) for autonomous theorem proving.

Status: pre-alpha. See [`docs/superpowers/specs/2026-05-28-isabelle-mcp-design.md`](docs/superpowers/specs/2026-05-28-isabelle-mcp-design.md) for the design.

## Architecture

- Python MCP server wraps [AutoCorrode's I/R](https://github.com/awslabs/AutoCorrode/tree/main/ir) (Isabelle/REPL).
- I/R is vendored as a git submodule via `vendor/AutoCorrode/`. The actual REPL lives at `vendor/AutoCorrode/ir/`.
- Layer A (file-anchored), Layer B (REPL/snapshot), Layer C (automation) tool surface.
- Bundled SKILL guides LLMs through the standard proving loop.

## Quick start

> Status: **M2** — the stdio MCP server exposes Layer B (REPL) and Layer C
> (automation) tools. Layer A file-anchored tools land in later milestones.

**Prerequisites:** Isabelle 2025-2 with a prebuilt HOL image, `uv`, and the
vendored submodule. See [`docs/m0-setup.md`](docs/m0-setup.md).

```bash
git submodule update --init --recursive
uv sync
export ISABELLE_HOME=/path/to/Isabelle2025-2(.app)   # dir containing bin/isabelle
uv run isabelle-mcp                                   # serves MCP over stdio
```

Register it with an MCP client (e.g. Claude Code `.mcp.json`):

```json
{
  "mcpServers": {
    "isabelle": {
      "command": "uv",
      "args": ["run", "isabelle-mcp"],
      "env": { "ISABELLE_HOME": "/path/to/Isabelle2025-2.app" }
    }
  }
}
```

Tools advertised:

- **Layer B (REPL):** `isabelle_open_repl`, `isabelle_step`, `isabelle_undo`,
  `isabelle_state`, `isabelle_fork_repl`, `isabelle_close_repl`.
- **Layer C (automation):** `isabelle_try0`, `isabelle_sledgehammer`,
  `isabelle_find_theorems`, `isabelle_nitpick`, `isabelle_quickcheck`
  (+ `isabelle_thm_deps` when `ISABELLE_MCP_EXPOSE_ADVANCED=1`).

The proving-loop SKILL is served as the MCP `instructions` preamble.

Optional env: `ISABELLE_MCP_SESSION` (default `HOL`), `ISABELLE_MCP_PORT`,
`ISABELLE_MCP_NO_BASH_SERVER=1` (disables sledgehammer's ATPs for faster start),
`ISABELLE_MCP_EXPOSE_ADVANCED=1`, `ISABELLE_MCP_MAX_PREVIEW_CHARS` (default 4000),
`ISABELLE_MCP_LOG_LEVEL`.
