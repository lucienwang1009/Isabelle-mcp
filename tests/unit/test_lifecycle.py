"""Unit tests for IRManager's opaque repl_id registry (no Isabelle required).

A fake session stands in for the real I/R connection so the mapping logic,
error translation, and registry bookkeeping can be tested without a daemon.
"""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from isabelle_mcp.errors import ToolError
from isabelle_mcp.lifecycle import IRManager


class FakeSession:
    """Minimal stand-in for IRSession; records calls, returns canned replies."""

    def __init__(self) -> None:
        self.inited: list[str] = []
        self.removed: list[str] = []
        self.steps: list[tuple[str, str, float]] = []
        self.timeouts: list[tuple[str, int]] = []
        self.loaded_theories: list[str] = []

    def init(self, *, repl_id: str, theories: list[str]) -> str:
        self.inited.append(repl_id)
        return repl_id

    def fork(self, parent_id: str, new_id: str, *, state_idx: int = -1) -> dict[str, Any]:
        return {"ok": True, "body": f'Forked REPL "{new_id}"'}

    def step(self, repl_id: str, *, isar: str, timeout_seconds: float = 60.0) -> dict[str, Any]:
        self.steps.append((repl_id, isar, timeout_seconds))
        return {"ok": True, "body": "theorem t: P\n[timing] 0.0s"}

    def _set_step_timeout(self, repl_id: str, secs: int) -> None:
        self.timeouts.append((repl_id, secs))

    def state(self, repl_id: str, *, state_idx: int = -1) -> dict[str, Any]:
        return {"ok": True, "body": ""}

    def history(self, repl_id: str) -> list[str]:
        return []

    def load_theory(
        self, theory: str, *, timeout_seconds: float = 120.0
    ) -> dict[str, Any]:
        self.loaded_theories.append(theory)
        return {"ok": True, "body": f'Loaded theory "{theory}"\n[timing] 0.0s'}

    def undo(self, repl_id: str, *, n: int = 1) -> dict[str, Any]:
        return {"ok": True, "body": "Truncated"}

    def remove(self, repl_id: str) -> None:
        self.removed.append(repl_id)


@pytest.fixture
def manager_with_fake() -> tuple[IRManager, FakeSession]:
    mgr = IRManager(isabelle_bin="/nonexistent", ir_dir=Path("/nonexistent"))
    fake = FakeSession()

    @contextlib.contextmanager
    def _fake_session() -> Iterator[FakeSession]:
        yield fake

    mgr._session = _fake_session  # type: ignore[assignment,method-assign]
    return mgr, fake


def test_idle_reaper_closes_stale_repls(monkeypatch: pytest.MonkeyPatch) -> None:
    import time

    mgr = IRManager(isabelle_bin="/nonexistent", ir_dir=Path("/nonexistent"))
    mgr._ttl = 0.01  # tiny TTL for the test
    fake = FakeSession()

    @contextlib.contextmanager
    def _fake_session() -> Iterator[FakeSession]:
        yield fake

    mgr._session = _fake_session  # type: ignore[assignment,method-assign]
    repl_id = mgr.open({"theory": "Main"})["repl_id"]
    internal = f"mcp_{repl_id}"
    # Force the REPL to look idle, then run one reaper pass.
    mgr._last_access[repl_id] = time.monotonic() - 100.0
    mgr._reap_once()

    assert internal in fake.removed
    with pytest.raises(ToolError) as exc:
        mgr.state(repl_id)
    assert exc.value.code == "repl_not_found"


def test_open_issues_opaque_id_mapped_to_internal(
    manager_with_fake: tuple[IRManager, FakeSession],
) -> None:
    mgr, fake = manager_with_fake
    result = mgr.open({"theory": "Main"})
    repl_id = result["repl_id"]
    # The opaque id is NOT the internal id given to I/R.
    assert isinstance(repl_id, str) and repl_id
    assert fake.inited == [f"mcp_{repl_id}"]
    assert repl_id != fake.inited[0]


def test_resolve_unknown_raises_repl_not_found(
    manager_with_fake: tuple[IRManager, FakeSession],
) -> None:
    mgr, _ = manager_with_fake
    with pytest.raises(ToolError) as exc:
        mgr.step("does-not-exist", "by simp")
    assert exc.value.code == "repl_not_found"


def test_step_sets_ir_timeout(
    manager_with_fake: tuple[IRManager, FakeSession],
) -> None:
    mgr, fake = manager_with_fake
    repl_id = mgr.open({"theory": "Main"})["repl_id"]
    internal = f"mcp_{repl_id}"

    mgr.step(repl_id, "by simp", timeout_seconds=42)

    assert fake.timeouts[-1] == (internal, 42)
    assert fake.steps[-1] == (internal, "by simp", 52.0)


def test_state_includes_pending_restart_event(
    manager_with_fake: tuple[IRManager, FakeSession],
) -> None:
    mgr, _ = manager_with_fake
    repl_id = mgr.open({"theory": "Main"})["repl_id"]
    mgr._pending_server_event = "ir_restarted"

    state = mgr.state(repl_id)

    assert state["server_event"] == "ir_restarted"
    assert "server_event" not in mgr.state(repl_id)


def test_step_blocks_raw_ml_by_default(
    manager_with_fake: tuple[IRManager, FakeSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ISABELLE_MCP_ALLOW_ML", raising=False)
    mgr, fake = manager_with_fake
    repl_id = mgr.open({"theory": "Main"})["repl_id"]

    with pytest.raises(ToolError) as exc:
        mgr.step(repl_id, 'ML "OS.Process.system \\"date\\""')

    assert exc.value.code == "ml_disabled"
    assert fake.steps == []


def test_tool_error_consumes_pending_restart_event(
    manager_with_fake: tuple[IRManager, FakeSession],
) -> None:
    mgr, _ = manager_with_fake
    repl_id = mgr.open({"theory": "Main"})["repl_id"]
    mgr._pending_server_event = "ir_restarted"

    with pytest.raises(ToolError) as exc:
        mgr.undo(repl_id, n=0)

    assert exc.value.server_event == "ir_restarted"


def test_check_file_loads_header_theory(
    manager_with_fake: tuple[IRManager, FakeSession],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    thy = tmp_path / "Foo.thy"
    thy.write_text("theory Foo imports Main begin\nlemma a: \"True\" by simp\nend\n")
    mgr, fake = manager_with_fake

    checked = mgr.check_file(str(thy), timeout_seconds=20)

    assert checked["checked"] is True
    assert checked["theory"] == "Foo"
    assert checked["imports"] == ["Main"]
    assert checked["errors"] == []
    assert fake.loaded_theories == ["Foo"]


def test_check_file_with_project_context_uses_build_checker(
    manager_with_fake: tuple[IRManager, FakeSession],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    project = tmp_path / "proof" / "Foo"
    project.mkdir(parents=True)
    (project / "ROOT").write_text("session Foo = HOL + theories Foo\n", encoding="utf-8")
    thy = project / "Foo.thy"
    thy.write_text("theory Foo imports Main begin\nlemma a: \"True\" by simp\nend\n")
    mgr, fake = manager_with_fake
    calls: list[dict[str, Any]] = []

    def fake_check_project(root: str, **kwargs: Any) -> dict[str, object]:
        calls.append({"root": root, **kwargs})
        return {
            "checked": True,
            "returncode": 0,
            "root": root,
            "session": kwargs["session"],
            "session_dirs": kwargs["session_dirs"],
            "command": ["isabelle", "build"],
            "command_text": "isabelle build",
            "errors": [],
            "warnings": [],
            "output": "",
        }

    mgr.check_project = fake_check_project  # type: ignore[method-assign]

    checked = mgr.check_file(str(thy), session="Foo", timeout_seconds=20)

    assert checked["checked"] is True
    assert checked["checked_via"] == "isabelle_build"
    assert checked["theory"] == "Foo"
    assert calls[0]["root"] == str(project)
    assert calls[0]["session"] == "Foo"
    assert fake.loaded_theories == []


def test_close_repl_removes_mapping_and_calls_remove(
    manager_with_fake: tuple[IRManager, FakeSession],
) -> None:
    mgr, fake = manager_with_fake
    repl_id = mgr.open({"theory": "Main"})["repl_id"]
    internal = f"mcp_{repl_id}"
    mgr.close_repl(repl_id)
    assert fake.removed == [internal]
    # Subsequent use of the id fails as not found.
    with pytest.raises(ToolError) as exc:
        mgr.state(repl_id)
    assert exc.value.code == "repl_not_found"


def test_open_requires_theory_or_parent(
    manager_with_fake: tuple[IRManager, FakeSession],
) -> None:
    mgr, _ = manager_with_fake
    with pytest.raises(ToolError) as exc:
        mgr.open({})
    assert exc.value.code == "invalid_argument"


def test_ir_unavailable_when_not_started() -> None:
    mgr = IRManager(isabelle_bin="/nonexistent", ir_dir=Path("/nonexistent"))
    with pytest.raises(ToolError) as exc:
        mgr.step("any", "by simp")
    # _resolve runs first and the id is unknown -> repl_not_found.
    assert exc.value.code == "repl_not_found"
