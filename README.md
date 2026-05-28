# isabelle-mcp

MCP server exposing Isabelle/HOL to general-purpose LLMs (Claude, GPT) for autonomous theorem proving.

Status: pre-alpha. See [`docs/superpowers/specs/2026-05-28-isabelle-mcp-design.md`](docs/superpowers/specs/2026-05-28-isabelle-mcp-design.md) for the design.

## Architecture

- Python MCP server wraps [AutoCorrode's I/R](https://github.com/awslabs/AutoCorrode/tree/main/ir) (Isabelle/REPL).
- I/R is vendored as a git submodule under `vendor/ir/`.
- Layer A (file-anchored), Layer B (REPL/snapshot), Layer C (automation) tool surface.
- Bundled SKILL guides LLMs through the standard proving loop.

## Quick start

Not yet shippable. Watch this space.
