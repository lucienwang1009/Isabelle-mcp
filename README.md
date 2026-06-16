# isabelle-mcp

MCP server exposing Isabelle/HOL to general-purpose LLMs (Claude, GPT) for autonomous theorem proving.

Status: **0.2 (beta).** Layer A/B/C tools over stdio or HTTP, with sandboxing,
crash recovery, idle-REPL cleanup, structured logging, and metrics. See
[`docs/superpowers/specs/2026-05-28-isabelle-mcp-design.md`](docs/superpowers/specs/2026-05-28-isabelle-mcp-design.md)
for the design and `docs/superpowers/plans/` for the milestone history.

## Architecture

- Python MCP server wraps [AutoCorrode's I/R](https://github.com/awslabs/AutoCorrode/tree/main/ir) (Isabelle/REPL).
- I/R is vendored as a git submodule via `vendor/AutoCorrode/`. The actual REPL lives at `vendor/AutoCorrode/ir/`.
- Layer A (file-anchored), Layer B (REPL/snapshot), Layer C (automation) tool surface.
- Bundled SKILL guides LLMs through the standard proving loop.

## Install

> **Install from source — not from PyPI.** The server shells out to the vendored
> I/R subprocess (`vendor/AutoCorrode/ir/`), which is not part of the importable
> Python package, so a bare `pip`/`uvx` wheel install will not run. Clone with
> submodules and run via `uv`. (The package named `isabelle-mcp` *on PyPI* is an
> unrelated project — do **not** `uvx isabelle-mcp`.)

**Prerequisites:** Isabelle 2025-2 with a prebuilt HOL image and `uv`.
See [`docs/m0-setup.md`](docs/m0-setup.md).

```bash
git clone --recurse-submodules https://github.com/lucienwang1009/Isabelle-mcp.git
cd Isabelle-mcp
uv sync
export ISABELLE_HOME=/path/to/Isabelle2025-2(.app)   # dir containing bin/isabelle
uv run isabelle-mcp                                   # serves MCP over stdio
```

> Already cloned without `--recurse-submodules`? Run
> `git submodule update --init --recursive`.

## Quick start

The server exposes Layer A (file/utility), Layer B (REPL) and Layer C
(automation) tools. Position-anchored `goal_at`/`diagnostics` and `hover`
remain deferred (I/R strips PIDE markup to plain text — see the M3 plan).

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

- **Layer A (file/utility):** `isabelle_file_outline`, `isabelle_run_code`,
  `isabelle_multi_attempt`.
- **Layer B (REPL):** `isabelle_open_repl`, `isabelle_step`, `isabelle_undo`,
  `isabelle_state`, `isabelle_fork_repl`, `isabelle_close_repl`.
- **Layer C (automation):** `isabelle_try0`, `isabelle_sledgehammer`,
  `isabelle_find_theorems`, `isabelle_nitpick`, `isabelle_quickcheck`
  (+ `isabelle_thm_deps` when `ISABELLE_MCP_EXPOSE_ADVANCED=1`).

The proving-loop SKILL is served as the MCP `instructions` preamble, and a set of
deeper reference docs are exposed as on-demand MCP **resources** (progressive
disclosure, modelled on [lean4-skills](https://github.com/cameronfreer/lean4-skills)):

| Resource URI | Topic |
|---|---|
| `skill://isabelle/tactics` | Tactic catalog + when to use each |
| `skill://isabelle/isar-patterns` | Structured Isar: induction, cases, calc, obtain |
| `skill://isabelle/sledgehammer` | Driving sledgehammer + applying its output |
| `skill://isabelle/afp-and-search` | `find_theorems` and using the **AFP** as a library |
| `skill://isabelle/afp-setup` | Download/build the AFP and point the server at a heap |
| `skill://isabelle/counterexamples` | nitpick/quickcheck falsification workflow |
| `skill://isabelle/errors` | Mapping `error.code` to a concrete fix |

Source for all of these lives under `isabelle_mcp/skills/` (`isabelle-proving.md`
plus `references/*.md`).

### Transports

Default is stdio. Set `ISABELLE_MCP_TRANSPORT=streamable-http` (or `sse`) to
serve over HTTP on `ISABELLE_MCP_HOST` (default `127.0.0.1`) /
`ISABELLE_MCP_PORT_HTTP` (default `8000`); a Prometheus `GET /metrics` endpoint
is exposed under HTTP.

### Environment variables

| Var | Purpose |
|---|---|
| `ISABELLE_MCP_SESSION` | Isabelle session image (default `HOL`) |
| `ISABELLE_MCP_TRANSPORT` | `stdio` (default), `sse`, `streamable-http` |
| `ISABELLE_MCP_PORT` | I/R daemon TCP port (default 9147) |
| `ISABELLE_MCP_HOST` / `ISABELLE_MCP_PORT_HTTP` | HTTP bind (default 127.0.0.1:8000) |
| `ISABELLE_MCP_NO_BASH_SERVER=1` | Disable sledgehammer's ATPs (faster start) |
| `ISABELLE_MCP_EXPOSE_ADVANCED=1` | Expose `isabelle_thm_deps` |
| `ISABELLE_MCP_DISABLED_TOOLS` | Comma-separated tool names to hide |
| `ISABELLE_MCP_ALLOWED_DIRS` | Extra roots for `file_outline` (path-separated) |
| `ISABELLE_MCP_MAX_TIMEOUT_S` | Per-call timeout ceiling (default 600) |
| `ISABELLE_MCP_REPL_TTL_S` | Idle-REPL TTL before reaping (default 1800) |
| `ISABELLE_MCP_MAX_PREVIEW_CHARS` | Output truncation (default 4000) |
| `ISABELLE_MCP_LOG_LEVEL` | Log level for the JSON logs |

## Docker

A `Dockerfile` is provided (installs Isabelle 2025-2, builds the HOL heap, and
runs the server). The image is multi-GB and not built in CI:

```bash
docker build -t isabelle-mcp .
docker run --rm -i isabelle-mcp           # stdio
```

## Development

```bash
uv sync
uv run pytest                              # unit tests run without Isabelle
ISABELLE_HOME=/path/to/Isabelle2025-2.app uv run pytest   # + integration
```

Tests are marked `integration` (need Isabelle 2025-2 + HOL; auto-skip otherwise)
and `heavy` (sledgehammer / the end-to-end auto-prover). The reproducible
end-to-end harness lives at `scripts/e2e_autoprove.py` and closes ≥7/10 fixture
lemmas via `try0`/`sledgehammer` with no LLM in the loop.
