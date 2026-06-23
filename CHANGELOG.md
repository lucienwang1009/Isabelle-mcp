# Changelog

All notable changes to this project are documented here.
Pre-1.0 versioning: minor = features, patch = fixes.

## [Unreleased]

### Added
- `isabelle_open_repl` accepts `session` + `session_dirs` to anchor a REPL on a
  locally built session image (the daemon switches sessions on demand, so a
  proof can use your project's own theories without re-pasting definitions).
- `resolve_target`: explicitly named build/check targets are trusted, so
  `isabelle_check_project` / `isabelle_check_file` / `isabelle_file_outline`
  work on projects outside the server's working directory (no
  `ISABELLE_MCP_ALLOWED_DIRS` reconfigure needed).

### Changed
- I/R daemon port: when the default port (9147) is busy — typically a stale
  daemon from a previous run — the server now transparently falls back to a
  free port instead of failing with an opaque "exited before printing the auth
  token". An explicitly configured `ISABELLE_MCP_PORT` that is busy now fails
  with the precise remedy.
- `isabelle_sledgehammer` output drops the noisy `SMT: Warning: dropping
  assumption` blocks, keeping the found/one_liner/suggestions signal clear.
- Step/state output strips the repeated "double backslash auto-corrected"
  advisory banner; `isabelle_state` caps step history to the 50 most recent.

### Fixed
- A failed `isabelle_step` that bundled several Isar commands now carries a hint
  to submit one command per step (so failures localize).
- A `sorry`/`oops` rejection now maps to the `sorry_disabled` code with a hint
  pointing at `declare [[quick_and_dirty]]` for scaffolding.

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
