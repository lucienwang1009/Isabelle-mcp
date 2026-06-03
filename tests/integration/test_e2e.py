"""End-to-end: the deterministic auto-prover closes >=7/10 fixture lemmas.

Exercises the whole proving stack (open -> step -> try0 -> sledgehammer -> apply)
without an LLM. Marked heavy because sledgehammer's ATPs may run.
"""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from isabelle_mcp.lifecycle import IRManager

_PORT = 9158
_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "e2e_autoprove.py"


def _load_harness():
    spec = importlib.util.spec_from_file_location("e2e_autoprove", _SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # let @dataclass resolve cls.__module__
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def manager(isabelle_bin: str, ir_dir: Path, hol_built: None) -> Iterator[IRManager]:
    mgr = IRManager(
        isabelle_bin=isabelle_bin,
        ir_dir=ir_dir,
        session="HOL",
        port=_PORT,
        bash_server=True,
        startup_timeout_seconds=180.0,
    )
    mgr.start()
    try:
        yield mgr
    finally:
        mgr.close()


@pytest.mark.integration
@pytest.mark.heavy
def test_autoprove_closes_threshold(manager: IRManager) -> None:
    harness = _load_harness()
    outcomes = harness.run(manager)
    closed = [o.name for o in outcomes if o.closed]
    assert len(outcomes) == len(harness.LEMMAS)
    assert len(closed) >= harness.THRESHOLD, (
        f"only closed {len(closed)}/{len(outcomes)}: "
        + ", ".join(f"{o.name}={o.method}" for o in outcomes if not o.closed)
    )
