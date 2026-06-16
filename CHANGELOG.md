# Changelog

All notable changes to this project are documented here.
Pre-1.0 versioning: minor = features, patch = fixes.

## [0.2.0] - 2026-06-16

### Added
- Enriched proving SKILL and AFP-aware reference resources (tactics, Isar
  patterns, sledgehammer, `find_theorems`/AFP, AFP setup, counterexamples,
  errors), served as on-demand MCP resources.

### Changed
- Packaging metadata: real author and repository URLs.
- README: documented that installation is **from source** (clone with
  submodules + `uv sync`); a bare `uvx isabelle-mcp` fetches an unrelated
  PyPI project, not this one.

## [0.1.0] - 2026-06-03

### Added
- Initial beta: Layer A/B/C MCP tools over stdio and HTTP/SSE, path-allowlist
  sandboxing, idle-REPL TTL reaper, I/R crash recovery, structured JSON
  logging, Prometheus `/metrics`, a Docker image, and a deterministic
  end-to-end auto-prover (`scripts/e2e_autoprove.py`) closing ≥7/10 fixture
  lemmas with no LLM in the loop.
