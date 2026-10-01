"""Offline context controls; provider requests and identity claims are absent."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import managed_run_context as context  # noqa: E402
from managed_token_ledger import BudgetError, TokenLedger  # noqa: E402

# A prepatch negative loads preserved bytes directly, without restoring live code.
if source := os.environ.get("SPECORGANON_CONTEXT_SOURCE"):
    spec = importlib.util.spec_from_file_location("preserved_run_context", source)
    preserved = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(preserved)
    context = preserved


class Clock:
    def __init__(self) -> None:
        self.mono = 10.0
        self.wall = 1000.0
        self.sequence: list[float] = []

    def monotonic(self) -> float:
        if self.sequence:
            self.mono = self.sequence.pop(0)
        return self.mono

    def time(self) -> float:
        return self.wall


def _file(path: Path, raw: bytes = b"{}\n") -> None:
    path.write_bytes(raw)
    path.chmod(0o600)


def _layout(root: Path) -> tuple[TokenLedger, list[Path]]:
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    root.chmod(0o700)
    roots = []
    for name in ("requests", "responses", "receipts", "tool_reservations", "tool_receipts"):
        path = root / name
        path.mkdir(mode=0o700)
        roots.append(path)
    _file(root / "plan.json")
    roots.append(root / "plan.json")
    ledger = TokenLedger.create(root / "ledger", 100, 4)
    roots.append(root / "ledger")
    return ledger, roots


def _create(root: Path, *, seconds: float = 10, cap: int = 2):
    ledger, roots = _layout(root)
    ctx = context.RunContext.create(root / "context", root / "ledger",
                                    {"plan_sha256": "a" * 64},
                                    active_limit_seconds=seconds, max_tool_calls=cap,
                                    roles=["leader", "reviewer"], journal_roots=roots)
    return ctx, ledger


def _begin(ctx, role: str = "leader") -> None:
    ctx.begin(ctx.status()["checkpoint_sha256"], role)


def _settle(ledger: TokenLedger, name: str, role: str, total: int) -> None:
    ledger.reserve(name, role, "b" * 64, 2, total)
    ledger.settle(name, {"input_tokens": 2, "output_tokens": total - 2, "total_tokens": total})


def test_roles_and_segments_reuse_ledger_and_accumulate_active_and_pause_time(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = Clock()
    monkeypatch.setattr(context, "time", clock)
    ledger, roots = _layout(tmp_path)
    _settle(ledger, "already-spent", "leader", 6)
    ctx = context.RunContext.create(tmp_path / "context", tmp_path / "ledger", {},
                                    active_limit_seconds=10, max_tool_calls=2,
                                    roles=["leader", "reviewer"], journal_roots=roots)
    _begin(ctx)
    _settle(ledger, "segment-one", "leader", 8)
    clock.mono, clock.wall = 13, 1003
    paused = ctx.pause(1)
    assert paused["active_seconds"] == 3
    assert paused["remaining_active_seconds"] == 7
    assert paused["budget"]["committed_tokens"] == 14
    clock.mono, clock.wall = 100, 1123
    recovered = context.RunContext(tmp_path / "context")
    resumed = recovered.begin(paused["checkpoint_sha256"], "reviewer")
    assert recovered.deadline == 107
    assert resumed["paused_seconds"] == 120
    _settle(ledger, "segment-two", "reviewer", 10)
    clock.mono = 102
    finished = recovered.finish(2)
    assert finished["state"] == "completed"
    assert finished["active_seconds"] == 5
    assert finished["remaining_active_seconds"] == 5
    assert finished["budget"]["request_count"] == 3
    assert finished["budget"]["committed_tokens"] == 24
    assert [record["role"] for record in ledger.status()["requests"].values()].count("reviewer") == 1
    assert context.RunContext(tmp_path / "context").status() == finished


def test_checkpoint_rejects_file_directory_ledger_and_binding_mutations(tmp_path: Path) -> None:
    for mutation in ("file", "directory", "deletion", "symlink", "ledger", "binding"):
        root = tmp_path / mutation
        ctx, ledger = _create(root)
        checkpoint = ctx.status()["checkpoint_sha256"]
        if mutation == "file":
            _file(root / "plan.json", b"changed\n")
        elif mutation == "directory":
            (root / "requests" / "new-empty-directory").mkdir()
        elif mutation == "deletion":
            (root / "plan.json").unlink()
        elif mutation == "symlink":
            (root / "requests" / "link").symlink_to(root / "plan.json")
        elif mutation == "ledger":
            _settle(ledger, "unbound-write", "leader", 6)
        else:
            state = json.loads((root / "context" / "run.json").read_bytes())
            state["bindings"]["plan_sha256"] = "c" * 64
            _file(root / "context" / "run.json", context._canonical(state))
        with pytest.raises(ValueError):
            ctx.begin(checkpoint, "leader")
        assert json.loads((root / "context" / "run.json").read_bytes())["state"] == "prepared"


def test_stale_instance_cannot_mutate_a_new_lease(tmp_path: Path) -> None:
    old, _ = _create(tmp_path)
    _begin(old)
    paused = old.pause(1)
    current = context.RunContext(tmp_path / "context")
    current.begin(paused["checkpoint_sha256"], "reviewer")
    before = (tmp_path / "context" / "run.json").read_bytes()
    for action in (old.require_active, lambda: old.pause(2), lambda: old.finish(2),
                   lambda: old.abort("old instance")):
        with pytest.raises(context.RunContextError, match="lease"):
            action()
        assert (tmp_path / "context" / "run.json").read_bytes() == before
    assert context.RunContext(tmp_path / "context").status()["state"] == "indeterminate"
    current.finish(2)


def test_real_processes_compare_and_swap_one_checkpoint(tmp_path: Path) -> None:
    ctx, _ = _create(tmp_path)
    checkpoint = ctx.status()["checkpoint_sha256"]
    code = """import sys
sys.path.insert(0, sys.argv[1])
from pathlib import Path
from managed_run_context import RunContext, RunContextError
c = RunContext(Path(sys.argv[2]))
try:
    c.begin(sys.argv[3], 'leader')
except RunContextError:
    print('blocked')
else:
    print('active')
"""
    argv = [sys.executable, "-I", "-c", code, str(SCRIPTS), str(tmp_path / "context"), checkpoint]
    children = [subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"}) for _ in range(2)]
    outputs = []
    for child in children:
        out, err = child.communicate(timeout=10)
        assert child.returncode == 0, err
        outputs.append(out.strip())
    assert sorted(outputs) == [b"active", b"blocked"]
    recovered = context.RunContext(tmp_path / "context")
    status = recovered.status()
    assert (status["state"], status["stored_state"]) == ("indeterminate", "active")
    assert status["held_active_seconds"] == 10
    assert status["active_seconds"] == status["remaining_active_seconds"] == 0
    with pytest.raises(context.RunContextError):
        recovered.begin(status["checkpoint_sha256"], "reviewer")


def test_pause_wall_clock_rollback_does_not_resume_or_rewrite(tmp_path: Path, monkeypatch) -> None:
    clock = Clock()
    monkeypatch.setattr(context, "time", clock)
    ctx, _ = _create(tmp_path)
    _begin(ctx)
    clock.mono = 12
    paused = ctx.pause(1)
    before = (tmp_path / "context" / "run.json").read_bytes()
    clock.wall = 999
    with pytest.raises(context.RunContextError, match="rolled back"):
        context.RunContext(tmp_path / "context").begin(paused["checkpoint_sha256"], "reviewer")
    assert (tmp_path / "context" / "run.json").read_bytes() == before


def test_pending_model_or_tool_and_tool_cap_prevent_clean_pause(tmp_path: Path) -> None:
    for mode in ("model", "tool", "cap"):
        root = tmp_path / mode
        ctx, ledger = _create(root, cap=1)
        _begin(ctx)
        if mode == "model":
            ledger.reserve("pending", "leader", "d" * 64, 2, 8)
        else:
            _file(root / "tool_reservations" / "0001.json")
            if mode == "cap":
                _file(root / "tool_receipts" / "0001.json")
                _file(root / "tool_reservations" / "0002.json")
                _file(root / "tool_receipts" / "0002.json")
        ctx.require_active()  # Live journals can grow before their receipt exists.
        with pytest.raises(context.RunContextError):
            ctx.pause(1)
        status = ctx.abort("synthetic uncertain result")
        assert status["state"] == "indeterminate"
        if mode == "model":
            assert status["budget"]["reserved_tokens"] == 10
            with pytest.raises(BudgetError):
                ledger.reserve("no-retry", "reviewer", "e" * 64, 1, 1)


def test_invalid_create_rejects_before_mkdir(tmp_path: Path) -> None:
    _, roots = _layout(tmp_path)
    for index, changes in enumerate((
        {"active_limit_seconds": float("nan")}, {"active_limit_seconds": True},
        {"bindings": {"plan_sha256": "malformed"}}, {"roles": ["leader", "leader"]},
        {"journal_roots": [tmp_path]}, {"journal_roots": roots + [roots[0]]},
        {"journal_roots": [tmp_path / "ledger", tmp_path / "ledger" / "ledger.json"]},
    )):
        target = tmp_path / f"invalid-{index}"
        kwargs = {"bindings": {}, "active_limit_seconds": 10, "max_tool_calls": 1,
                  "roles": ["leader"], "journal_roots": roots} | changes
        with pytest.raises(context.RunContextError):
            context.RunContext.create(target, tmp_path / "ledger", **kwargs)
        assert not target.exists()


@pytest.mark.parametrize("fail_compensation", [False, True])
def test_deadline_crossing_during_checkpoint_never_leaves_resumable_or_invalid_state(
    tmp_path: Path, monkeypatch, fail_compensation: bool,
) -> None:
    clock = Clock()
    monkeypatch.setattr(context, "time", clock)
    ctx, _ = _create(tmp_path)
    _begin(ctx)
    clock.sequence = [19, 19.5, 21, 21]
    original_write = context._write_state

    def write(directory, state):
        if fail_compensation and state["state"] == "indeterminate":
            raise OSError("synthetic compensatory persistence failure")
        original_write(directory, state)

    monkeypatch.setattr(context, "_write_state", write)
    with pytest.raises((context.RunContextError, OSError)):
        ctx.finish(1)
    fresh = context.RunContext(tmp_path / "context")
    status = fresh.status()
    assert status["state"] == "indeterminate"
    assert 0 <= status["active_seconds"] <= 10
    with pytest.raises(context.RunContextError):
        fresh.begin(status["checkpoint_sha256"], "reviewer")


def test_expired_lease_cannot_finish_but_can_abort(tmp_path: Path, monkeypatch) -> None:
    clock = Clock()
    monkeypatch.setattr(context, "time", clock)
    ctx, ledger = _create(tmp_path)
    _begin(ctx)
    clock.mono = 21
    with pytest.raises(context.RunContextError, match="deadline"):
        ctx.require_active()
    with pytest.raises(context.RunContextError, match="deadline"):
        ctx.finish(1)
    status = ctx.abort("deadline swallowed by caller")
    assert status["state"] == "indeterminate"
    assert ledger.status()["request_count"] == 0
