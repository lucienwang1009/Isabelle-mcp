# M4 — Hardening Implementation Plan

**Goal:** Make the server robust enough to run unattended: structured logging,
path sandboxing, timeout clamping, per-tool disable, idle-REPL cleanup, I/R
crash recovery, an HTTP/SSE transport, and lightweight metrics.

**Builds on M1–M3.** No submodule changes.

## Tasks & scope

### Task 1: Structured JSON logging + metrics (`logging.py`, `metrics.py`)
- `configure_logging(level)` installs a JSON formatter to **stderr**. Each tool
  call logs one line: `ts, level, event, tool, correlation_id, repl_id?,
  latency_ms, ok, error_code?`. **No goal text or file content.**
- `metrics.py`: process-wide counters (`tool_calls`, `tool_errors`,
  per-code error counts, `repls_opened`, `repls_reaped`, `ir_restarts`) with a
  `snapshot()` and Prometheus text rendering.
- `tools.run_tool` times each call, logs the structured line, bumps counters.

### Task 2: Path sandbox, timeout clamp, per-tool disable
- `sandbox.py`: allow-list = CWD/project root + `ISABELLE_MCP_ALLOWED_DIRS`
  (`os.pathsep`-separated). `read_theory_file` resolves symlinks and rejects
  paths outside the allow-list (`file_not_found` to avoid leaking layout).
- `errors.clamp_timeout(requested)` → min(requested, `ISABELLE_MCP_MAX_TIMEOUT_S`,
  default 600); applied in tool callbacks.
- Registration honors `ISABELLE_MCP_DISABLED_TOOLS` (comma-separated names):
  a disabled tool is not registered.

### Task 3: Idle-REPL TTL + crash recovery (`lifecycle.py`)
- Track `last_access` per opaque repl_id; a daemon reaper thread closes REPLs
  idle longer than `ISABELLE_MCP_REPL_TTL_S` (default 1800) and counts them.
- `_require_handle` detects a dead daemon process; `start()` can restart it.
  On restart, the registry is cleared so stale ids return `repl_not_found`
  (the LLM is told to reopen). Count `ir_restarts`.

### Task 4: HTTP/SSE transport + tests + tag
- `transports/http.py`: `run_http(mcp, transport)` for `sse` /
  `streamable-http` (loopback bind; FastMCP host/port from env).
- `server.main` selects transport via `ISABELLE_MCP_TRANSPORT`
  (`stdio` default).
- Tests: unit for logging formatter, metrics, sandbox, timeout clamp, tool
  disable, TTL reaper (short TTL, fake session); integration for crash recovery
  (kill daemon → stale id `repl_not_found`, new open works) and that an HTTP
  server starts and lists tools. Tag `v0.0.0-m4`.

## Acceptance criteria
1. `uv run pytest` green.
2. Path traversal outside the allow-list is refused.
3. Killing the I/R daemon and calling a tool recovers (restart) and invalidates
   stale repl_ids.
4. Idle REPLs are reaped after the TTL.
5. `ISABELLE_MCP_TRANSPORT=streamable-http` starts an HTTP server advertising
   the tools. Tag `v0.0.0-m4` on the remote.

## Notes / deferrals
- HTTP **bearer-token auth** beyond loopback binding is left minimal (loopback
  only); a full OAuth/token middleware is out of M4 scope.
- `/metrics` is exposed as a custom route when running under HTTP; under stdio,
  metrics are logged on shutdown.
