# I/R Protocol Notes

Vendored commit: ead52c44673ef3135f1239b0f70941bc55666a95
Date: 2026-05-28
Investigator: M0 Task 3 implementer (subagent)

## CLI invocation of `repl.py`

Full command line for M0 (HOL session, TCP listener, no MCP, no interactive console):

    python3 vendor/AutoCorrode/ir/repl.py \
        --isabelle /path/to/Isabelle2025-2.app/bin/isabelle \
        --session HOL \
        --server-only

The `--server-only` flag skips the stdin REPL and runs headlessly. Without it,
`repl.py` also expects an interactive terminal (prompt_toolkit). For automation
tasks 6–8 use `--server-only` or `--daemon`.

Source: `vendor/AutoCorrode/ir/repl.py`, lines 2036–2086 (argparse setup) and
lines 2509–2515 (server-only branch).

### Every CLI flag

| Flag | Default | Required? | Purpose |
|---|---|---|---|
| `--port` | `0` (try 9147, then OS-assigned) | no | TCP port for the `repl.py`-side server (the I/R daemon). Port 9147 is `REPL_DEFAULT_PORT` |
| `--poly-ml-port` | `0` (OS-assigned) | no | Port for the internal ML_Repl listener inside Poly/ML (port 9146 is tried first, then OS-assigned). Not exposed to clients |
| `--isabelle` | auto-detected (macOS: `/Applications/Isabelle2025-2.app/bin/isabelle`; Linux: `~/Isabelle2025-2/bin/isabelle`) | effectively yes (auto-detect may fail) | Path to Isabelle executable or Isabelle app/directory |
| `--session` | `HOL` | no | Isabelle session to load (heap) |
| `--dir` | `None` | no | Extra `-d DIR` passed to `isabelle ML_process` (custom session directory) |
| `--heaps` | `None` | no | Heaps base directory (overrides auto-discovery) |
| `--no-heap-db` | `False` | no | Disable heap DB integration (source verification, timings) |
| `--repl-only` | `False` | no | Plain REPL mode: skip heap DB, source matching, and extras (implies `--no-heap-db`) |
| `--kill-orphaned-processes` | `False` | no | Kill orphaned remote Bash.Server processes older than 6 h |
| `-v` / `--verbose` | `False` | no | Print the `isabelle ML_process` command being invoked |
| `--no-bash-server` | `False` | no | Skip Bash.Server startup (disables sledgehammer) |
| `--server-only` | `False` | no | Expose TCP server only; do not start a REPL on stdin |
| `--start-only` | `False` | no | Exec into Poly/ML with ML_Repl (replaces this process) |
| `--show-server` | `False` | no | Show info about a running ML_Repl and exit |
| `--kill-server` | `False` | no | Show info about a running ML_Repl, stop it, and exit |
| `--mcp` | `False` | no | Start `mcp_server.py` in the background |
| `--mcp-options` | `"--transport streamable-http"` | no | Options forwarded to `mcp_server.py` |
| `--daemon` | `False` | no | Run headlessly; management console served on a Unix socket |
| `--expect-ml` | `False` | no | Connect to an already-running ML_Repl (retry loop, never start own Poly/ML). Set `IR_REPL_AUTH_TOKEN` for the token |
| `--attach` | `False` | no | Attach to a running daemon's management console |
| `--kill-daemon` | `False` | no | Send `/quit` to a running daemon and exit |
| `--mgmt-socket` | auto-derived from TCP port | no | Unix socket path for `--daemon`/`--attach` |
| `--pool-size` | `5` | no | Number of persistent ML connections (1 reserved for console) |

Source: `vendor/AutoCorrode/ir/repl.py`, lines 2037–2086.

### Environment variables read

| Var | Required? | Purpose |
|---|---|---|
| `IR_AUTH_TOKEN` | optional | Override the random token for the `repl.py` TCP server. If unset, a random `secrets.token_urlsafe(24)` is generated at startup and printed to stdout as `IR_Repl.token: <token>` |
| `IR_REPL_AUTH_TOKEN` | only with `--expect-ml` | Token for the internal ML_Repl TCP connection (used when connecting to an externally-started ML_Repl) |
| `ISABELLE_REMOTE` | optional | Space-separated options forwarded to `isabelle ML_process` for remote execution (e.g. `--host remotehost -o ML_platform=arm64_32-darwin`) |

Source: `vendor/AutoCorrode/ir/repl.py`, lines 35–44 (docstring), 917, 2210.

## TCP listener

- **Default port**: `9147` (`REPL_DEFAULT_PORT`, defined at line 302). When `--port 0` (default), repl.py tries to bind 9147 first; if that fails, lets the OS assign any free port.
- **Override flag**: `--port NN`
- **Bind address**: `127.0.0.1` exclusively. Hard-coded in `Server.__init__` (line 911, default `host="127.0.0.1"` argument) and confirmed in README.md ("All TCP listeners bind exclusively to `127.0.0.1`").
- **Auth handshake**: The client must send the token as the **first line** (terminated by `\n`) immediately after connecting. The server responds with `OK\n` on success or `ERR: authentication failed\n` on failure (lines 1333–1343). The token is printed to stdout on startup: `IR_Repl.token: <token>`. It can be pre-set via `IR_AUTH_TOKEN`.
- **Message framing (client → server)**: Newline-delimited plain text. The client sends ML-style command strings as a single line ending with `\n`. Commands accumulate until a line whose stripped text ends with `;` — that is the command terminator. Multi-line commands are joined with spaces. The server processes one command at a time per connection (serialized through the ML connection pool).
- **Message framing (server → client)**: Each command response is a text block terminated by the sentinel line `<<DONE>>\n`. Error responses are prefixed with `ERR\n` before the body text, followed by `<<DONE>>\n`. YXML markup in the raw ML output is stripped to plain text before sending over TCP. The sentinel constant is defined as `SENTINEL = "<<DONE>>"` at line 301.

Source: `vendor/AutoCorrode/ir/repl.py`, lines 301–303, 911–941, 1317–1410; `vendor/AutoCorrode/ir/README.md`, lines 102–108.

### Reference: minimal Python client snippet

```python
import socket

sock = socket.socket()
sock.connect(("127.0.0.1", 9147))

sock.sendall(b"token-here\n")          # auth
# read until b"OK\n"
sock.sendall(b'Ir.init "R" ["Main"];\n')
# read until b"\n<<DONE>>\n"
sock.sendall(b'Ir.step "R" "lemma foo: 1 + 1 = (2::nat)";\n')
# read until b"\n<<DONE>>\n"
sock.sendall(b'Ir.step "R" "by simp";\n')
# read until b"\n<<DONE>>\n"
sock.sendall(b'Ir.remove "R";\n')
# read until b"\n<<DONE>>\n"
```

This is a reference for Task 7 — not a test assertion. In practice, use a buffered reader that accumulates lines until a line equal to `<<DONE>>` is received.

### Internal ML_Repl framing (repl.py ↔ Poly/ML, not client-facing)

The `repl.py`-to-Poly/ML connection uses a different, lower-level PIDE message framing protocol (distinct from the client-facing TCP protocol described above):

- Client sends a single line (command + `\n`) to ML_Repl.
- ML_Repl replies with length-prefixed, YXML-encoded PIDE messages using `Byte_Message.write_message_yxml`. Each message is: header line of comma-separated chunk sizes, followed by raw chunk bytes. Chunk 0 = `kind` string (e.g. `writeln`, `error`, `state`, `done`); chunk 1 = count of property chunks; chunks 2..2+n = properties; remaining chunks = YXML body.
- A `kind = "done"` message signals end of output for that command.

Source: `vendor/AutoCorrode/ir/repl.py`, `PolyMLConnection` class, lines 687–817; `vendor/AutoCorrode/ir/ml_repl.ML`, lines 1–15.

## Commands used by M0

All commands are sent as ML function-call syntax over the TCP connection, ending with `;`. Responses are plain text (YXML stripped) terminated by `<<DONE>>\n`. There is no JSON envelope. The "request shape" is an ML expression; the "response shape" is human-readable text.

### init

**Request shape** (text line sent to TCP server):

    Ir.init "R" ["Main"];

- First argument: REPL id (quoted string).
- Second argument: list of theory names (ML string list). Must be non-empty. Each element can be `"TheoryName"`, `"Session.TheoryName"`, `"TheoryName:idx"` (segment), or `"pin@OtherReplId"` (pinned theory snapshot).

**Response on success**:

    Created REPL "R"
    <<DONE>>

**Response on error** (e.g., REPL id already exists, theory not found):

    ERR
    <error message text>
    <<DONE>>

Source: `vendor/AutoCorrode/ir/ir.ML`, `init` function, lines 393–424; `vendor/AutoCorrode/ir/repl.py`, `_handle_client`, lines 1404–1408.

### step

**Request shape**:

    Ir.step "R" "lemma my_lemma: 1 + 1 = (2::nat)";

or continuing a proof:

    Ir.step "R" "by simp";

- First argument: REPL id.
- Second argument: Isar text to execute (quoted string, ML-escaped).

#### ML string escaping

SML string-literal escaping rules apply to the second argument of `Ir.step`:

- `\\` for a literal backslash
- `\"` for a literal double-quote
- `\n` for newline
- `\t` for tab

Example — to send the Isar command:

    lemma foo: "True"

construct the TCP payload:

    Ir.step "R" "lemma foo: \"True\"";

Isabelle symbol syntax such as `\<and>` does NOT need extra escaping — only
the SML string-literal escapes above. Send `\<and>` as the literal six-character
sequence `\`, `<`, `a`, `n`, `d`, `>` — Isabelle's tokenizer parses these ASCII
characters as its own Unicode symbol names, so they are not a workaround but the
correct, canonical form inside an SML string literal.

(Source: standard SML escaping; consumed by `Ir.step` at `ir.ML:474–484`.)

**Response on success** — the current proof state (or theory state if proof is closed):

    proof (prove)
    goal (1 subgoal):
     1. 1 + 1 = 2
    <<DONE>>

When a proof closes (e.g., after `by simp` on a trivially provable goal), the response shows the theorem statement rather than remaining goals:

    theorem my_lemma: 1 + 1 = 2
    <<DONE>>

**Proof-closed indicator (heuristic — must be empirically validated in Task 7)**:

Empirically expected: after a successful `by simp` or `done`/`qed`, the response
body shows no `goal (N subgoal` line and includes a `theorem ` line printed by
`Toplevel.pretty_state` when the proof state returns to theory toplevel.

This heuristic is NOT machine-readable and MAY differ for `oops`, `sorry`,
structured proofs, and locales. See "Open questions / quirks" item 1.

**Step timeout**: Default 10 seconds per step. On timeout, the response is prefixed `ERR\n` with body `Step timed out after 10s`. Override per-REPL with `Ir.timeout "R" N;` (0 = unlimited).

**Error indicator**: Any error response is prefixed `ERR\n` before the body text (line 1404 in `_handle_client`). The body contains the Isabelle error message.

Source: `vendor/AutoCorrode/ir/ir.ML`, `step` function and `step_repl`, lines 474–484; `vendor/AutoCorrode/ir/repl.py`, lines 1404–1408.

### close (remove)

There is no `Ir.close` command. To clean up a REPL, use `Ir.remove`:

**Request shape**:

    Ir.remove "R";

**Response**:

    Removed "R"
    <<DONE>>

> Note: when the REPL being removed has descendant REPLs (forked sub-REPLs), the response
> lists all removed REPLs comma-separated:
>
>     Removed "R", "child1", "child2"
>     <<DONE>>
>
> Clients should match the prefix `Removed ` rather than an exact string.
> (Source: `vendor/AutoCorrode/ir/ir.ML:708`.)

`Ir.remove` also removes all descendant REPLs forked from the target.

Source: `vendor/AutoCorrode/ir/ir.ML`, `remove` function, lines 690–708.

## Other commands (out of M0 scope but documented for later milestones)

### find_theorems

**Request shape**:

    Ir.find_theorems "R" 5 "name: conjI";

- Arguments: REPL id, max results (0 = unlimited), query string.

**Response**: Human-readable list of theorems with their types, terminated by `<<DONE>>`.

Source: `vendor/AutoCorrode/ir/ir.ML`, `find_theorems` function, lines 758–775.

### sledgehammer

**Request shape**:

    Ir.sledgehammer "R" 30;

- Arguments: REPL id, timeout in seconds.

**Response**: Human-readable Sledgehammer results (provers tried, "Try this: by ..." suggestions), terminated by `<<DONE>>`. Requires `--no-bash-server` to be absent (Bash.Server must be running).

Source: `vendor/AutoCorrode/ir/ir.ML`, `sledgehammer` function, lines 777–808.

### MCP server (`mcp_server.py`)

`mcp_server.py` is a separate process launched by `repl.py --mcp`. It wraps the same TCP protocol via an HTTP/MCP layer on port 9148 by default. For M0 we use raw TCP directly and do not need MCP.

Source: `vendor/AutoCorrode/ir/mcp_server.py` (not read in detail; confirmed it is a wrapper around the TCP protocol).

## Open questions / quirks

1. **Proof-closed detection**: There is no machine-readable `"goals": []` or `"at_end_of_proof": true` field — the protocol is plain text. A client must parse the response text for the presence of `theorem <name>:` (or absence of `goal (N subgoal`) to detect proof completion. This will need to be tested empirically in Task 7 since edge cases (e.g., `done`, `oops`, `sorry`) may produce different output.

2. **Command terminator sensitivity**: The server accumulates lines into one command until a line ending in `;` is received. Sending a command without a trailing semicolon will hang the connection. The ML side also validates this and immediately returns an error if the semicolon is missing.

3a. **Token discovery (outer server)**: The token for the outer `repl.py` TCP server is printed to stdout — ANSI-free — as:

        IR_Repl.token: <token>

    This line appears at `repl.py:2456` **before** the port announcement. Capture it with:

        r"IR_Repl\.token: (\S+)"

    The token can also be pre-set via the `IR_AUTH_TOKEN` environment variable to skip stdout parsing entirely.

3b. **Port discovery (outer server vs. internal ML port — do not confuse)**:

    The outer `repl.py` server port is announced at `repl.py:2457–2458`:

        ● REPL ready. Waiting for connections on 127.0.0.1:<port>

    That line is emitted via `mgmt_output(...)` (which is `print()` to stdout). The
    raw bytes look like:

        \033[32m● REPL ready.\033[0m Waiting for connections on \033[1m127.0.0.1:9147\033[0m

    Note that `\033[1m` (BOLD) sits **between** `"on "` and `"127.0.0.1:..."`, so
    a naïve regex will fail. Two correct approaches:

    **Option A — strip ANSI first (recommended):**

    ```python
    import re
    ANSI_RE = re.compile(r"\033\[[0-9;]*m")
    clean = ANSI_RE.sub("", line)
    m = re.search(r"Waiting for connections on 127\.0\.0\.1:(\d+)", clean)
    ```

    **Option B — tolerate the optional escape inline:**

    ```python
    re.search(r"Waiting for connections on (?:\033\[\d+m)?127\.0\.0\.1:(\d+)", line)
    ```

    **The `Tcp_Handler: listening on 127.0.0.1:(\d+)(?: \(token "([^"]*)"\))?` regex is for the *internal* Poly/ML ML_Repl port** — it is consumed by `PolyMLProcess.read_actual_port()` inside `repl.py` itself (`repl.py:621–624`) and is NOT intended for external clients. Do not use it in Task 6's subprocess launcher.

    **Recommended mitigation**: pass `--port 9147` (or any chosen fixed port) explicitly to `repl.py`. Then Task 6's launcher never needs to parse the port at all — only the token needs to be captured from stdout (ANSI-free, see 3a above).

4. **Port discovery:** See item 3b above.

5. **`Ir.close` does not exist**: The correct teardown command is `Ir.remove "R";`. Or simply close the TCP socket — there is no session-end handshake required.

6. **YXML in error messages**: While TCP output has YXML stripped to plain text by `tcp_transforms`, some error messages may contain residual control characters if YXML stripping misses edge cases. Verify in Task 6/7 that error responses are cleanly readable.

7. **Concurrency model**: Commands are serialized through the ML connection pool. The pool has a configurable size (default 5); the management console uses one dedicated connection, leaving up to 4 for client commands. For M0 (single-threaded client) this is not a concern.

8. **`--no-bash-server` for M0**: For the smoke test (M0 Task 8), sledgehammer is not needed. Pass `--no-bash-server` to skip the Bash.Server startup step and reduce startup time.
