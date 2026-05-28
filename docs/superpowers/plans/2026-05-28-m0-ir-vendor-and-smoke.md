# M0 — I/R Vendoring & Smoke Test Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Vendor AutoCorrode's I/R (Isabelle/REPL), bring up an Isabelle 2025-2 + HOL daemon, and prove `lemma "1 + 1 = (2::nat)" by simp` end-to-end from a Python smoke test driven over I/R's loopback TCP protocol.

**Architecture:** Three concerns separated. (1) The `vendor/AutoCorrode/` git submodule pinned to a known commit holds I/R's source unchanged. (2) `isabelle_mcp/ir_client.py` is a thin Python module that spawns I/R as a subprocess and sends framed JSON requests over a loopback TCP socket. (3) The smoke test (`tests/integration/test_m0_smoke.py` + `scripts/m0_smoke.py`) drives I/R to prove one trivial lemma and asserts the response indicates the proof closed.

**Tech Stack:** Python 3.11+, `uv` for environment, `httpx`/`anyio`/`pytest`/`pytest-asyncio` for the client and tests, Isabelle 2025-2 (system install, user-provided), git submodules.

---

## Context for agents picking this up cold

You are working on `isabelle-mcp`, a planned MCP server that exposes Isabelle/HOL theorem proving to general-purpose LLMs (Claude, GPT). The full design is in `docs/superpowers/specs/2026-05-28-isabelle-mcp-design.md` — read its Sections 1, 2, and 3 before touching code.

**M0 is the spike milestone.** It does NOT build the MCP server yet. It proves that we can reliably drive AutoCorrode's existing I/R daemon (in [awslabs/AutoCorrode](https://github.com/awslabs/AutoCorrode), subdirectory `ir/`) from Python. If M0 succeeds, the later milestones (M1 = MCP minimal, M2 = automation, M3 = file-anchored, M4 = hardening, M5 = ship) all become incremental wins. If M0 fails, we have to revisit the architecture, so be rigorous about verifying behavior.

**Prerequisites that must already be true on the machine running this plan:**

1. **Isabelle 2025-2 installed**, with the `isabelle` binary on `PATH`. Verify with `isabelle version` (must contain `Isabelle2025-2`). If not installed, stop and ask the user; do not try to install Isabelle yourself.
2. **HOL session image prebuilt.** Verify with `isabelle build -n -b HOL` (the `-n` is dry-run; it exits 0 if HOL is up to date). If it reports work to do, run `isabelle build -b HOL` once (this takes 5–15 minutes the first time). Stop and ask if the build fails.
3. **`uv` Python package manager installed.** Verify with `uv --version`.
4. **`git` ≥ 2.30** for submodules.
5. **macOS or Linux.** Windows is not in scope for M0.

If any prerequisite fails, **stop and report the issue.** Do not attempt to work around missing prereqs.

**Conventions enforced by this project (from `~/.claude/rules/coding-style.md`):**
- Files 200–400 lines max.
- All Python functions get type hints.
- Every package `__init__.py` defines `__all__`.
- Conventional Commits for all commit messages: `type(scope): subject`.
- Use module-level `logger = logging.getLogger(__name__)`; never `print` for diagnostics.

---

## File structure produced by M0

| Path | Created or modified | Responsibility |
|---|---|---|
| `.gitmodules` | Created | Submodule declaration for AutoCorrode. |
| `vendor/AutoCorrode/` | Created (submodule) | Pinned upstream source. I/R lives at `vendor/AutoCorrode/ir/`. |
| `vendor/ir/.gitkeep` | **Deleted** | Replaced by the actual submodule above. |
| `pyproject.toml` | Modified | Add real runtime + dev dependencies. |
| `uv.lock` | Created | uv lockfile. |
| `docs/ir-protocol-notes.md` | Created | Findings from reading I/R source. Future tasks reference this. |
| `docs/m0-setup.md` | Created | Manual prerequisite steps (Isabelle install, HOL build). |
| `isabelle_mcp/ir_client.py` | Modified | Subprocess launcher + TCP request/response client (M0-minimal). |
| `tests/integration/conftest.py` | Created | Pytest fixtures for Isabelle availability, HOL build check, IR daemon lifecycle. |
| `tests/integration/test_ir_environment.py` | Created | Verifies Isabelle + HOL are available. |
| `tests/integration/test_ir_subprocess.py` | Created | Verifies I/R can be spawned and reached over TCP. |
| `tests/integration/test_ir_protocol.py` | Created | Verifies the protocol helpers (init/step/close round-trip). |
| `tests/integration/test_m0_smoke.py` | Created | The end-to-end `1 + 1 = 2` proof. |
| `scripts/m0_smoke.py` | Created | A standalone runnable version of the smoke test (no pytest). |

All other files in the repo skeleton are untouched in M0.

---

## Acceptance criteria for completing M0

The agent (or human reviewer) declares M0 done when **all four** are true:

1. `git submodule status` shows `vendor/AutoCorrode/` at a pinned commit.
2. `uv run pytest tests/integration -v -m integration` reports 0 failures, including `test_m0_smoke.py::test_proves_one_plus_one_equals_two`.
3. `uv run python scripts/m0_smoke.py` exits 0 and prints `PROOF CLOSED: lemma "1 + 1 = (2::nat)" by simp`.
4. The branch is tagged `v0.0.0-m0` on the remote.

If any of these fail, M0 is not done; do not declare completion.

---

## Tasks

### Task 1: Add AutoCorrode as a vendored submodule

**Files:**
- Delete: `vendor/ir/.gitkeep`
- Create (git plumbing): `.gitmodules`, `vendor/AutoCorrode` (submodule gitlink)
- Modify: `README.md` (1 line note about submodule location)

- [ ] **Step 1: Remove the placeholder**

```bash
git rm vendor/ir/.gitkeep
# Also remove now-empty vendor/ir directory if it still exists:
[ -d vendor/ir ] && rmdir vendor/ir
```

Expected: `git status` shows `vendor/ir/.gitkeep` as deleted.

- [ ] **Step 2: Add the submodule**

```bash
git submodule add https://github.com/awslabs/AutoCorrode.git vendor/AutoCorrode
git submodule update --init --recursive vendor/AutoCorrode
```

Expected: `.gitmodules` exists with a `[submodule "vendor/AutoCorrode"]` block; `vendor/AutoCorrode/ir/repl.py` exists.

- [ ] **Step 3: Pin to a specific commit (deterministic builds)**

```bash
cd vendor/AutoCorrode
# Pin to the HEAD of main at time of vendoring; record the SHA below
git rev-parse HEAD
cd ../..
```

Record the SHA printed in the commit message in Step 5. Do **not** check out an older commit unless instructed — `main` HEAD is fine.

- [ ] **Step 4: Verify the I/R files are present**

```bash
ls vendor/AutoCorrode/ir/
```

Expected: output includes `README.md`, `repl.py`, `ir.ML`, `mcp_server.py`, `tcp_handler.ML`, `requirements.txt`.

If any file is missing, **stop and report**: the upstream layout has shifted and the rest of this plan will not apply.

- [ ] **Step 5: Update README.md path reference**

Open `README.md`. Find the line referencing `vendor/ir/`. Replace with the new path.

Old:
```
- I/R is vendored as a git submodule under `vendor/ir/`.
```

New:
```
- I/R is vendored as a git submodule via `vendor/AutoCorrode/`. The actual REPL lives at `vendor/AutoCorrode/ir/`.
```

- [ ] **Step 6: Commit**

```bash
git add .gitmodules vendor/AutoCorrode README.md
git rm --cached vendor/ir/.gitkeep 2>/dev/null || true
git status   # verify clean staging
git commit -m "chore(vendor): add AutoCorrode as submodule, pin to <SHA>"
```

Replace `<SHA>` with the SHA from Step 3.

---

### Task 2: Add real Python dependencies via uv

**Files:**
- Modify: `pyproject.toml`
- Create: `uv.lock`, `.venv/` (gitignored)

- [ ] **Step 1: Confirm uv sees the project**

```bash
uv --version
uv sync --dry-run
```

Expected: `uv --version` prints `uv 0.4+`. `uv sync --dry-run` either reports "Would install …" or "Already up to date."

- [ ] **Step 2: Add runtime dependencies**

```bash
uv add httpx anyio
```

This edits `pyproject.toml` `[project] dependencies` and creates/updates `uv.lock`.

- [ ] **Step 3: Add dev dependencies**

```bash
uv add --dev pytest pytest-asyncio
```

This edits `pyproject.toml` `[dependency-groups.dev]`.

- [ ] **Step 4: Verify the venv works**

```bash
uv sync
uv run python -c "import httpx, anyio, pytest; print('ok')"
```

Expected: prints `ok`.

- [ ] **Step 5: Verify pytest discovers the integration directory**

```bash
uv run pytest tests/integration --collect-only 2>&1 | head -20
```

Expected: no errors; "collected 0 items" is fine (no tests yet).

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "build: add httpx, anyio runtime deps and pytest dev deps via uv"
```

---

### Task 3: Investigate I/R's TCP protocol and document findings

**Files:**
- Create: `docs/ir-protocol-notes.md`

This is a reading/documentation task. **No tests.** Acceptance is the document existing with the required sections filled in from actual source inspection.

- [ ] **Step 1: Read the I/R README in full**

```bash
sed -n '1,400p' vendor/AutoCorrode/ir/README.md
```

Note the CLI flags for `repl.py` (e.g., `--isabelle`, `--session`, `--dir`, port flags, auth flags).

- [ ] **Step 2: Read the TCP handler ML side**

```bash
sed -n '1,400p' vendor/AutoCorrode/ir/tcp_handler.ML
```

Identify the protocol framing (e.g., length-prefixed JSON? line-delimited? Look for `TextIO` / `Socket` calls and how messages are read/written).

- [ ] **Step 3: Read the Python REPL driver**

```bash
sed -n '1,600p' vendor/AutoCorrode/ir/repl.py
sed -n '600,1500p' vendor/AutoCorrode/ir/repl.py
```

Find the CLI argument parser (look for `argparse.ArgumentParser`). Note every flag and its meaning.

Find the TCP server setup. Note the default port, auth-token environment variable, and message framing.

- [ ] **Step 4: Identify the key commands**

Locate the implementations or routing of `Ir.init`, `Ir.step`, `Ir.close`, `Ir.find_theorems`, `Ir.sledgehammer`. Note the exact JSON shape expected and returned, including:
- the field used to identify the command (e.g., `"cmd": "init"` or `"method": "Ir.init"`)
- request parameters
- response fields, including how success vs failure is distinguished
- how proof completion is signaled (does the response carry `at_end_of_proof`? `current_goals: []`? something else?)

- [ ] **Step 5: Write `docs/ir-protocol-notes.md`**

Create the file with these required sections, filled in from your reading:

```markdown
# I/R Protocol Notes

Vendored commit: <SHA from Task 1 Step 3>
Date: 2026-05-28
Investigator: <agent name / handle>

## CLI invocation of `repl.py`

Full command line we will use in M0:

    python3 vendor/AutoCorrode/ir/repl.py \
        --isabelle <path>/bin/isabelle \
        --session HOL \
        <other required flags from actual --help output>

Source: vendor/AutoCorrode/ir/repl.py, lines NN–MM.

## TCP listener

- Default port: <NN>
- Override flag: `<--tcp-port=NN>` (or env var if applicable)
- Auth: token sent as first line / header / handshake; env var: `IR_AUTH_TOKEN` (or actual)
- Message framing: <length-prefixed | newline-delimited | JSON-RPC framed>

Source: <file>, lines NN–MM.

## Commands used by M0

### init
- Request shape: `{ "<field>": "init", ... }`
- Response shape: `{ ... }`
- How to read the goal/state from the response: <description>

### step
- Request shape: ...
- Response shape: ...
- Proof-closed indicator: <field name and value, e.g. `at_end_of_proof: true` or `goals: []`>

### close
- Request shape: ...

## Open questions / quirks

- <any non-obvious behavior — list explicitly so future tasks can compensate>
```

Every section must contain real findings, not placeholders. If a section is genuinely empty after thorough reading, write "(none found; behavior to be discovered at runtime)" and continue.

- [ ] **Step 6: Verify the file is non-trivial**

```bash
wc -l docs/ir-protocol-notes.md
grep -E "^##" docs/ir-protocol-notes.md
```

Expected: ≥ 60 lines, at least 5 `## ` headings present.

- [ ] **Step 7: Commit**

```bash
git add docs/ir-protocol-notes.md
git commit -m "docs(ir): document I/R TCP protocol from vendored source"
```

---

### Task 4: Pytest fixture for Isabelle availability

**Files:**
- Create: `tests/integration/conftest.py`
- Create: `tests/integration/test_ir_environment.py`

- [ ] **Step 1: Write the failing test first**

Create `tests/integration/test_ir_environment.py`:

```python
"""Verify Isabelle 2025-2 is installed and reachable."""

from __future__ import annotations

import subprocess

import pytest


@pytest.mark.integration
def test_isabelle_binary_exists(isabelle_bin: str) -> None:
    """The `isabelle` binary is on PATH or pointed to by ISABELLE_HOME."""
    assert isabelle_bin, "no isabelle binary located"


@pytest.mark.integration
def test_isabelle_version_is_2025_2(isabelle_bin: str) -> None:
    """Reject older Isabelle releases — I/R requires 2025-2 features."""
    result = subprocess.run(
        [isabelle_bin, "version"], capture_output=True, text=True, check=True
    )
    assert "Isabelle2025-2" in result.stdout, (
        f"unexpected Isabelle version: {result.stdout!r}"
    )
```

- [ ] **Step 2: Run the test and verify it fails**

```bash
uv run pytest tests/integration/test_ir_environment.py -v
```

Expected: FAIL with fixture error — `fixture 'isabelle_bin' not found`.

- [ ] **Step 3: Implement the fixture in conftest.py**

Create `tests/integration/conftest.py`:

```python
"""Shared fixtures for integration tests.

These all require a working Isabelle 2025-2 install. Each fixture
skips the test (rather than erroring) when prerequisites are not met.
"""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path

import pytest

logger = logging.getLogger(__name__)


@pytest.fixture(scope="session")
def isabelle_bin() -> str:
    """Locate the `isabelle` binary. Skip the test if not found."""
    env_home = os.environ.get("ISABELLE_HOME")
    if env_home:
        candidate = Path(env_home) / "bin" / "isabelle"
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    found = shutil.which("isabelle")
    if found:
        return found
    pytest.skip("isabelle binary not found (set ISABELLE_HOME or PATH)")


@pytest.fixture(scope="session")
def repo_root() -> Path:
    """Absolute path to the repository root."""
    return Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def ir_dir(repo_root: Path) -> Path:
    """Absolute path to vendored I/R directory."""
    path = repo_root / "vendor" / "AutoCorrode" / "ir"
    if not (path / "repl.py").is_file():
        pytest.skip("vendor/AutoCorrode/ir/repl.py missing; run git submodule update --init")
    return path
```

- [ ] **Step 4: Register the marker**

Open `pyproject.toml`. Verify the `[tool.pytest.ini_options]` block includes the `integration` marker (it was added in the initial scaffold). If missing, add:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
markers = [
    "integration: needs a real Isabelle install",
    "heavy: needs ATPs and >60s budget (sledgehammer, etc.)",
]
```

- [ ] **Step 5: Run the test and verify it passes**

```bash
uv run pytest tests/integration/test_ir_environment.py -v -m integration
```

Expected: 2 PASSED (assuming Isabelle 2025-2 is installed). If skipped, your environment doesn't meet the prereqs — re-check the "Prerequisites" section at the top of this plan.

- [ ] **Step 6: Commit**

```bash
git add tests/integration/conftest.py tests/integration/test_ir_environment.py
git commit -m "test(integration): add Isabelle 2025-2 environment check"
```

---

### Task 5: Fixture and test for the prebuilt HOL session image

**Files:**
- Modify: `tests/integration/conftest.py`
- Modify: `tests/integration/test_ir_environment.py`
- Create: `docs/m0-setup.md`

- [ ] **Step 1: Write the failing test for the HOL fixture**

Append to `tests/integration/test_ir_environment.py`:

```python
@pytest.mark.integration
def test_hol_session_is_built(hol_built: None) -> None:
    """The HOL session image is up to date (built via `isabelle build -b HOL`)."""
    # Reaching here means the fixture confirmed HOL is built.
    assert True
```

- [ ] **Step 2: Run the test and verify it fails**

```bash
uv run pytest tests/integration/test_ir_environment.py::test_hol_session_is_built -v
```

Expected: FAIL with `fixture 'hol_built' not found`.

- [ ] **Step 3: Implement the `hol_built` fixture**

Append to `tests/integration/conftest.py`:

```python
@pytest.fixture(scope="session")
def hol_built(isabelle_bin: str) -> None:
    """Skip the test unless `isabelle build -n -b HOL` reports nothing to do.

    A built HOL image is required for I/R to start in reasonable time.
    Building HOL from scratch takes 5–15 minutes; we never build it
    inside a test.
    """
    import subprocess

    result = subprocess.run(
        [isabelle_bin, "build", "-n", "-b", "HOL"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        pytest.skip(
            "HOL session image not built. Run "
            f"`{isabelle_bin} build -b HOL` (takes 5–15 minutes the first time). "
            f"stderr: {result.stderr.strip()!r}"
        )
```

- [ ] **Step 4: Write the manual-setup doc**

Create `docs/m0-setup.md`:

```markdown
# M0 Manual Setup

Before running the M0 integration tests, the host must have:

1. **Isabelle 2025-2** installed, with `isabelle` on PATH, OR `ISABELLE_HOME` exported.

   Download: <https://isabelle.in.tum.de/website-Isabelle2025-2/>

   Verify:
   ```bash
   isabelle version
   # Expected: Isabelle2025-2: ...
   ```

2. **HOL session image** prebuilt. This takes 5–15 minutes the first time
   on a typical laptop, and is cached afterwards.

   ```bash
   isabelle build -b HOL
   # Verify it is up to date (returncode 0):
   isabelle build -n -b HOL
   ```

3. **Submodules initialized**:
   ```bash
   git submodule update --init --recursive
   ```

4. **uv environment synced**:
   ```bash
   uv sync
   ```

5. (Optional) `IR_AUTH_TOKEN` environment variable can be set to a fixed
   string for reproducibility. If unset, the M0 client generates a random
   token per run.

If any of the above is not satisfied, the integration tests **skip rather
than fail** so that unit tests still pass on CI without an Isabelle install.
```

- [ ] **Step 5: Run the test and verify it passes**

```bash
uv run pytest tests/integration/test_ir_environment.py -v -m integration
```

Expected: 3 PASSED (or 1 SKIPPED if HOL is not built on the local host — but read the skip message and resolve before continuing).

- [ ] **Step 6: Commit**

```bash
git add tests/integration/conftest.py tests/integration/test_ir_environment.py docs/m0-setup.md
git commit -m "test(integration): add HOL prebuild check and manual setup doc"
```

---

### Task 6: Spawn I/R as a subprocess and verify it accepts TCP connections

**Files:**
- Modify: `isabelle_mcp/ir_client.py`
- Create: `tests/integration/test_ir_subprocess.py`
- Modify: `tests/integration/conftest.py` (add `ir_daemon` fixture)

This task only verifies the daemon **starts and accepts a TCP connection**. It does not send any I/R commands yet — that is Task 7.

- [ ] **Step 1: Write the failing test**

Create `tests/integration/test_ir_subprocess.py`:

```python
"""Verify I/R subprocess lifecycle: spawn, accept a TCP connection, terminate."""

from __future__ import annotations

import socket

import pytest


@pytest.mark.integration
def test_ir_daemon_accepts_tcp_connection(ir_daemon: "IRDaemonHandle") -> None:
    """A bare TCP connection to the daemon's listener succeeds within timeout."""
    with socket.create_connection(("127.0.0.1", ir_daemon.port), timeout=10) as sock:
        # Just opening the socket and closing is enough for M0 step 1.
        assert sock.fileno() != -1


@pytest.mark.integration
def test_ir_daemon_process_is_alive(ir_daemon: "IRDaemonHandle") -> None:
    """The subprocess is still running after the fixture set it up."""
    assert ir_daemon.process.poll() is None, (
        "I/R subprocess exited prematurely; "
        f"returncode={ir_daemon.process.returncode}"
    )
```

The forward reference to `IRDaemonHandle` is intentional — it gets defined by `ir_client.py` in Step 3.

- [ ] **Step 2: Run and verify the tests fail**

```bash
uv run pytest tests/integration/test_ir_subprocess.py -v -m integration
```

Expected: errors about missing `ir_daemon` fixture and unresolved `IRDaemonHandle`.

- [ ] **Step 3: Implement the daemon launcher in `isabelle_mcp/ir_client.py`**

Replace the contents of `isabelle_mcp/ir_client.py` with:

```python
"""Client for the vendored I/R daemon: spawn, heartbeat, JSON over loopback TCP.

M0 scope: launching + lifecycle only. Protocol helpers (init/step/close)
arrive in Task 7.
"""

from __future__ import annotations

import dataclasses
import logging
import os
import secrets
import socket
import subprocess
import sys
import time
from pathlib import Path

logger = logging.getLogger(__name__)

__all__ = ["IRDaemonHandle", "launch_ir_daemon"]


@dataclasses.dataclass
class IRDaemonHandle:
    """Bundle of state for a running I/R subprocess."""

    process: subprocess.Popen[bytes]
    port: int
    auth_token: str
    workdir: Path

    def terminate(self, grace_seconds: float = 5.0) -> None:
        """Stop the daemon; SIGTERM first, then SIGKILL after grace."""
        if self.process.poll() is not None:
            return
        self.process.terminate()
        try:
            self.process.wait(timeout=grace_seconds)
        except subprocess.TimeoutExpired:
            logger.warning("I/R did not exit on SIGTERM; sending SIGKILL")
            self.process.kill()
            self.process.wait(timeout=grace_seconds)


def _pick_free_port() -> int:
    """Bind to port 0 to let the OS pick an unused TCP port, then release it."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_listener(port: int, timeout_seconds: float) -> None:
    """Block until something accepts connections on 127.0.0.1:port, or fail."""
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1.0):
                return
        except OSError as exc:
            last_error = exc
            time.sleep(0.25)
    raise TimeoutError(
        f"I/R did not start listening on 127.0.0.1:{port} "
        f"within {timeout_seconds:.1f}s; last error: {last_error!r}"
    )


def launch_ir_daemon(
    *,
    isabelle_bin: str,
    ir_dir: Path,
    session: str = "HOL",
    auth_token: str | None = None,
    port: int | None = None,
    startup_timeout_seconds: float = 60.0,
) -> IRDaemonHandle:
    """Spawn I/R as a subprocess and wait until its TCP listener is up.

    Caller is responsible for calling `.terminate()` on the returned handle.

    NOTE: The exact `repl.py` CLI flags MUST match what was documented in
    `docs/ir-protocol-notes.md` (Task 3). If you are reading this and the
    flags below differ from what the upstream `repl.py --help` reports,
    update them here and re-record the change in the protocol notes.
    """
    repl_script = ir_dir / "repl.py"
    if not repl_script.is_file():
        raise FileNotFoundError(f"missing I/R entry point: {repl_script}")

    chosen_port = port if port is not None else _pick_free_port()
    chosen_token = auth_token if auth_token is not None else secrets.token_hex(16)

    env = os.environ.copy()
    env["IR_AUTH_TOKEN"] = chosen_token

    cmd: list[str] = [
        sys.executable,
        str(repl_script),
        "--isabelle",
        isabelle_bin,
        "--session",
        session,
        "--tcp-port",
        str(chosen_port),
    ]

    logger.info("launching I/R: %s", " ".join(cmd))
    process = subprocess.Popen(
        cmd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(ir_dir),
    )

    try:
        _wait_for_listener(chosen_port, startup_timeout_seconds)
    except Exception:
        # Capture any startup output before bailing.
        stdout, stderr = b"", b""
        try:
            stdout, stderr = process.communicate(timeout=2.0)
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate()
        logger.error(
            "I/R failed to start.\nstdout:\n%s\nstderr:\n%s",
            stdout.decode(errors="replace"),
            stderr.decode(errors="replace"),
        )
        raise

    return IRDaemonHandle(
        process=process,
        port=chosen_port,
        auth_token=chosen_token,
        workdir=ir_dir,
    )
```

**Adapt the CLI flags** in the `cmd` list to match what `vendor/AutoCorrode/ir/repl.py --help` actually accepts. The flags above (`--isabelle`, `--session`, `--tcp-port`) are the expected ones per the upstream README, but if Task 3's investigation produced different flag names, use those and update both files. If the upstream uses `IR_AUTH_TOKEN` as documented in the README, leave the env var as-is; otherwise update.

- [ ] **Step 4: Implement the `ir_daemon` fixture**

Append to `tests/integration/conftest.py`:

```python
from collections.abc import Generator

from isabelle_mcp.ir_client import IRDaemonHandle, launch_ir_daemon


@pytest.fixture(scope="session")
def ir_daemon(
    isabelle_bin: str, ir_dir: Path, hol_built: None
) -> Generator[IRDaemonHandle, None, None]:
    """A long-lived I/R subprocess for the whole test session."""
    handle = launch_ir_daemon(
        isabelle_bin=isabelle_bin,
        ir_dir=ir_dir,
        session="HOL",
        startup_timeout_seconds=90.0,
    )
    try:
        yield handle
    finally:
        handle.terminate()
```

The fixture is session-scoped because starting I/R is slow (~30s) and we want to reuse it across tests.

- [ ] **Step 5: Run the tests and verify they pass**

```bash
uv run pytest tests/integration/test_ir_subprocess.py -v -m integration
```

Expected: 2 PASSED. If failures occur:
- "did not start listening on port" → check that the CLI flags match upstream's actual `--help` output. Run `uv run python vendor/AutoCorrode/ir/repl.py --help` and reconcile.
- ImportError → check that `isabelle_mcp/__init__.py` and `isabelle_mcp/ir_client.py` are committed and `uv sync` is current.
- HOL build skip → see Task 5.

- [ ] **Step 6: Verify both lifecycle ends work**

```bash
uv run pytest tests/integration/test_ir_subprocess.py -v -m integration --log-cli-level=INFO
```

Expected log output includes `launching I/R: ...` and the test completes within 90s. No orphan Python processes left behind (verify with `pgrep -f vendor/AutoCorrode/ir/repl.py`; expect no matches after pytest exits).

- [ ] **Step 7: Commit**

```bash
git add isabelle_mcp/ir_client.py tests/integration/conftest.py tests/integration/test_ir_subprocess.py
git commit -m "feat(ir_client): spawn I/R subprocess with TCP listener and lifecycle"
```

---

### Task 7: Implement and test minimal protocol round-trip (init / step / close)

**Files:**
- Modify: `isabelle_mcp/ir_client.py`
- Create: `tests/integration/test_ir_protocol.py`

This task implements only the three commands needed for M0: opening a REPL, sending one Isar step, and closing the REPL. Other commands (sledgehammer, find_theorems, etc.) are out of scope until M2.

- [ ] **Step 1: Write the failing tests**

Create `tests/integration/test_ir_protocol.py`:

```python
"""Round-trip tests for the minimal I/R command set used in M0."""

from __future__ import annotations

import pytest

from isabelle_mcp.ir_client import IRDaemonHandle, IRSession


@pytest.mark.integration
def test_open_and_close_repl(ir_daemon: IRDaemonHandle) -> None:
    """We can open a REPL anchored at HOL and close it cleanly."""
    with IRSession.connect(ir_daemon) as session:
        repl_id = session.init(theory="HOL.HOL")
        assert isinstance(repl_id, str) and repl_id
        session.close(repl_id)


@pytest.mark.integration
def test_step_returns_response(ir_daemon: IRDaemonHandle) -> None:
    """A trivial Isar command (`theorem dummy: "True" by simp`) returns a response.

    We don't yet assert success — Task 8's smoke test does that. This
    just verifies the request/response framing round-trips.
    """
    with IRSession.connect(ir_daemon) as session:
        repl_id = session.init(theory="HOL.HOL")
        try:
            response = session.step(repl_id, isar='theorem ir_smoke: "True" by simp')
            assert isinstance(response, dict)
            assert "ok" in response or "error" in response or "result" in response, (
                f"unexpected step response shape: {response!r}"
            )
        finally:
            session.close(repl_id)
```

- [ ] **Step 2: Run and verify the tests fail**

```bash
uv run pytest tests/integration/test_ir_protocol.py -v -m integration
```

Expected: ImportError on `IRSession` from `isabelle_mcp.ir_client`.

- [ ] **Step 3: Implement `IRSession` in `isabelle_mcp/ir_client.py`**

**Adapt this skeleton** to match the actual protocol framing documented in `docs/ir-protocol-notes.md` from Task 3. The skeleton below assumes newline-delimited JSON with a one-line auth handshake; if the upstream actually uses length-prefixed framing or JSON-RPC, replace the read/write helpers accordingly. **Cross-check against the notes before writing.**

Append to `isabelle_mcp/ir_client.py`:

```python
import contextlib
import json
from collections.abc import Iterator
from typing import Any


__all__ += ["IRSession"]


class IRSession:
    """Connection to a running I/R daemon, speaking its TCP command protocol."""

    def __init__(self, socket_: socket.socket) -> None:
        self._sock = socket_
        self._buf = b""

    @classmethod
    @contextlib.contextmanager
    def connect(cls, handle: IRDaemonHandle) -> Iterator["IRSession"]:
        """Open a TCP connection, perform auth handshake, yield a session."""
        sock = socket.create_connection(("127.0.0.1", handle.port), timeout=30)
        try:
            sock.sendall((handle.auth_token + "\n").encode("utf-8"))
            session = cls(sock)
            yield session
        finally:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            sock.close()

    def _send(self, payload: dict[str, Any]) -> None:
        data = (json.dumps(payload) + "\n").encode("utf-8")
        self._sock.sendall(data)

    def _recv_one(self, timeout_seconds: float = 60.0) -> dict[str, Any]:
        self._sock.settimeout(timeout_seconds)
        while b"\n" not in self._buf:
            chunk = self._sock.recv(65536)
            if not chunk:
                raise ConnectionError("I/R closed the connection unexpectedly")
            self._buf += chunk
        line, _, rest = self._buf.partition(b"\n")
        self._buf = rest
        return json.loads(line.decode("utf-8"))  # type: ignore[no-any-return]

    def init(self, *, theory: str) -> str:
        """Open a new REPL anchored at the given theory. Returns repl_id."""
        self._send({"cmd": "Ir.init", "theory": theory})
        response = self._recv_one()
        if "error" in response:
            raise RuntimeError(f"Ir.init failed: {response['error']!r}")
        repl_id = response.get("repl_id") or response.get("result", {}).get("repl_id")
        if not isinstance(repl_id, str):
            raise RuntimeError(f"Ir.init: no repl_id in response {response!r}")
        return repl_id

    def step(self, repl_id: str, *, isar: str, timeout_seconds: float = 60.0) -> dict[str, Any]:
        """Send one Isar command to the REPL. Returns the raw response dict."""
        self._send({"cmd": "Ir.step", "repl_id": repl_id, "isar": isar})
        return self._recv_one(timeout_seconds=timeout_seconds)

    def close(self, repl_id: str) -> None:
        """Close the named REPL on the daemon."""
        self._send({"cmd": "Ir.close", "repl_id": repl_id})
        # Discard one response (ack) but don't error if the daemon closes early.
        try:
            self._recv_one(timeout_seconds=5.0)
        except (ConnectionError, TimeoutError, json.JSONDecodeError):
            pass
```

**Adapt** the command field names (`cmd`, `theory`, `repl_id`, `isar`) and the response field names (`repl_id`, `error`, `result`) to whatever the actual protocol uses — these are best-guesses from the README. If the protocol disagrees with this code, the right move is to update both the code and `docs/ir-protocol-notes.md`.

- [ ] **Step 4: Run the tests and verify they pass**

```bash
uv run pytest tests/integration/test_ir_protocol.py -v -m integration
```

Expected: 2 PASSED.

If `test_open_and_close_repl` fails with "no repl_id in response":
- The actual response shape differs. Inspect with `--log-cli-level=DEBUG` after adding a `logger.debug("recv: %s", response)` line in `_recv_one`.
- Update both `docs/ir-protocol-notes.md` and `IRSession.init` to match.

If `test_step_returns_response` times out:
- The Isar command may have side effects we didn't expect. Try a simpler step like `Theorem.lemma "True"` and iterate.

- [ ] **Step 5: Commit**

```bash
git add isabelle_mcp/ir_client.py tests/integration/test_ir_protocol.py
# Stage the protocol notes if they were updated during this task:
git add -u docs/ir-protocol-notes.md 2>/dev/null || true
git commit -m "feat(ir_client): add IRSession with init/step/close round-trip"
```

---

### Task 8: The end-to-end smoke test (`1 + 1 = (2::nat)`)

**Files:**
- Create: `tests/integration/test_m0_smoke.py`
- Create: `scripts/m0_smoke.py`

- [ ] **Step 1: Add the `proof_closed` helper to `ir_client.py`**

Both the test and the standalone script need to interpret an I/R step response. Place the helper in the library so they share one source of truth.

Append to `isabelle_mcp/ir_client.py`:

```python
def proof_closed(response: dict[str, Any]) -> bool:
    """Inspect an I/R step response and decide whether the proof was accepted.

    Tolerant of several response shapes because we don't yet know the
    canonical one. Update both this function and docs/ir-protocol-notes.md
    once the real shape is observed.
    """
    if response.get("error"):
        return False
    result = response.get("result") if isinstance(response.get("result"), dict) else None
    if response.get("at_end_of_proof") is True:
        return True
    if isinstance(result, dict) and result.get("at_end_of_proof") is True:
        return True
    if response.get("new_goals") == [] or (result is not None and result.get("new_goals") == []):
        return True
    if response.get("goals") == [] or (result is not None and result.get("goals") == []):
        return True
    return False


__all__ += ["proof_closed"]
```

- [ ] **Step 2: Write the smoke test**

Create `tests/integration/test_m0_smoke.py`:

```python
"""The M0 acceptance test: prove `1 + 1 = (2::nat)` end-to-end."""

from __future__ import annotations

import pytest

from isabelle_mcp.ir_client import IRDaemonHandle, IRSession, proof_closed


@pytest.mark.integration
def test_proves_one_plus_one_equals_two(ir_daemon: IRDaemonHandle) -> None:
    """Drive I/R to prove a trivial lemma and confirm the proof closes."""
    with IRSession.connect(ir_daemon) as session:
        repl_id = session.init(theory="HOL.HOL")
        try:
            response = session.step(
                repl_id,
                isar='theorem m0_smoke: "1 + 1 = (2::nat)" by simp',
                timeout_seconds=60.0,
            )
        finally:
            session.close(repl_id)

    assert proof_closed(response), (
        f"expected the lemma to close; got response={response!r}"
    )
```

- [ ] **Step 3: Run the smoke test and verify it fails or skips appropriately**

```bash
uv run pytest tests/integration/test_m0_smoke.py -v -m integration --log-cli-level=INFO
```

This may fail until your `proof_closed` heuristic matches the real protocol. Iterate Steps 1 + 4 below until it passes.

- [ ] **Step 4: If the heuristic is wrong, update both files**

Use `--log-cli-level=DEBUG` to capture the full response dict. Update `proof_closed` in `isabelle_mcp/ir_client.py` to assert on the actual shape, and tighten the description in `docs/ir-protocol-notes.md` accordingly. Commit interim discoveries to `docs/ir-protocol-notes.md` even if the smoke test still does not pass.

- [ ] **Step 5: Run the smoke test and confirm it passes**

```bash
uv run pytest tests/integration/test_m0_smoke.py -v -m integration
```

Expected: 1 PASSED.

- [ ] **Step 6: Write the standalone script `scripts/m0_smoke.py`**

Create `scripts/m0_smoke.py`:

```python
"""Standalone M0 smoke: prove `1 + 1 = (2::nat)` without pytest.

Usage:
    uv run python scripts/m0_smoke.py

Exits 0 on success, non-zero on failure.
"""

from __future__ import annotations

import logging
import os
import shutil
import sys
from pathlib import Path

from isabelle_mcp.ir_client import IRSession, launch_ir_daemon, proof_closed

LOGGER = logging.getLogger("m0_smoke")


def _find_isabelle() -> str:
    env_home = os.environ.get("ISABELLE_HOME")
    if env_home:
        candidate = Path(env_home) / "bin" / "isabelle"
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    found = shutil.which("isabelle")
    if not found:
        raise SystemExit("error: isabelle binary not found on PATH or ISABELLE_HOME")
    return found


def main() -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    repo_root = Path(__file__).resolve().parents[1]
    ir_dir = repo_root / "vendor" / "AutoCorrode" / "ir"
    if not (ir_dir / "repl.py").is_file():
        raise SystemExit(
            "error: vendor/AutoCorrode/ir/repl.py missing; "
            "run git submodule update --init"
        )
    isabelle_bin = _find_isabelle()

    handle = launch_ir_daemon(
        isabelle_bin=isabelle_bin,
        ir_dir=ir_dir,
        session="HOL",
        startup_timeout_seconds=90.0,
    )
    try:
        with IRSession.connect(handle) as session:
            repl_id = session.init(theory="HOL.HOL")
            response = session.step(
                repl_id,
                isar='theorem m0_smoke: "1 + 1 = (2::nat)" by simp',
                timeout_seconds=60.0,
            )
            session.close(repl_id)
    finally:
        handle.terminate()

    if not proof_closed(response):
        LOGGER.error("PROOF FAILED: response=%r", response)
        return 1
    print('PROOF CLOSED: lemma "1 + 1 = (2::nat)" by simp')
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 7: Run the standalone script**

```bash
uv run python scripts/m0_smoke.py
```

Expected: prints `PROOF CLOSED: lemma "1 + 1 = (2::nat)" by simp` and exits 0.

- [ ] **Step 8: Commit**

```bash
git add isabelle_mcp/ir_client.py tests/integration/test_m0_smoke.py scripts/m0_smoke.py
# Stage docs if they were updated during iteration:
git add -u docs/ir-protocol-notes.md 2>/dev/null || true
git commit -m "test(integration): end-to-end M0 smoke proves 1 + 1 = (2::nat)"
```

---

### Task 9: Tag the milestone and push

**Files:**
- No file changes. Git tag only.

- [ ] **Step 1: Run the full integration suite one last time**

```bash
uv run pytest tests/integration -v -m integration
```

Expected: all PASSED (no failures, no errors). Skips are acceptable only if a prereq is genuinely missing — re-read the prerequisites if anything skips.

- [ ] **Step 2: Run the standalone smoke one last time**

```bash
uv run python scripts/m0_smoke.py
```

Expected: prints `PROOF CLOSED: ...` and exits 0.

- [ ] **Step 3: Inspect the git log**

```bash
git log --oneline
```

Expected: at least 8 commits since the initial scaffold (one per Task 1–8). Commit messages use Conventional Commits format.

- [ ] **Step 4: Tag the milestone**

```bash
git tag -a v0.0.0-m0 -m "M0: I/R vendored, HOL boots, 1+1=2 proved end-to-end"
git push origin main
git push origin v0.0.0-m0
```

Expected: push succeeds; the tag is visible on the remote.

- [ ] **Step 5: Verify acceptance criteria**

Walk through the four acceptance criteria at the top of this plan and confirm each holds:

1. `git submodule status` shows `vendor/AutoCorrode/` at a pinned commit. → `git submodule status`
2. `uv run pytest tests/integration -v -m integration` → 0 failures.
3. `uv run python scripts/m0_smoke.py` → exits 0, prints success line.
4. The branch is tagged `v0.0.0-m0` on the remote. → `git ls-remote --tags origin`

If all four hold, M0 is done. Report success to the user with a one-line summary and the smoke output. **Do not start M1.** Wait for the next plan.

If any acceptance criterion does not hold, **stop and report the specific failure** with the relevant logs. Do not declare completion.

---

## Out of scope for M0 (do not work on these)

- The MCP server itself (no FastMCP, no stdio transport, no tool schemas). Belongs to M1.
- Layer A / B / C tools. Belongs to M1–M3.
- The bundled SKILL document. Belongs to M5.
- Sledgehammer / try0 / nitpick / quickcheck wrappers. Belongs to M2.
- Docker, HTTP transport, authentication beyond IR's loopback token. Belongs to M4–M5.
- AFP support. Out of v0.1.
- Sandboxing, structured JSON logging beyond what's already in this plan, metrics, crash recovery. Belongs to M4.

Do not add scaffolding for any of these in M0 even if it "looks easy." The whole point of M0 is to be the smallest possible thing that proves the I/R foundation works.

---

## Notes for the agent executing this plan

- **Iterate on the protocol notes (`docs/ir-protocol-notes.md`) as you learn.** Tasks 6, 7, 8 are coupled; expect to discover protocol details that contradict initial assumptions and update both code and notes. Commit each correction.
- **If you find a real bug in upstream I/R**, do not patch the submodule. Open a GitHub issue at `awslabs/AutoCorrode` and document the workaround locally. The submodule must stay pristine for the upstream PR pathway planned in M5.
- **All commits go on `main`.** No PRs in M0 (single-developer milestone). M1 onwards may switch to a PR-per-task workflow if multiple agents collaborate.
- **Do not edit `~/.claude/` config**, the `docs/superpowers/specs/` design, or any file outside the paths listed in each task's "Files" header.
- **If any command needs to run interactively (Isabelle login, gh auth, etc.), stop and ask the user to run it themselves.**
- **Time budget guidance**: a fluent agent should finish M0 in 4–8 hours wallclock (less if HOL is already built). If you've spent more than 2 hours on a single task without progress, stop and report what's blocking.
