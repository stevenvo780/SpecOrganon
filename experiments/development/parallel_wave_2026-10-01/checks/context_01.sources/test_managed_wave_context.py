"""One durable context selects the real concurrent budget; no mirror ledger."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import managed_run_context as context  # noqa: E402
from managed_token_ledger import BudgetError, TokenLedger  # noqa: E402
from managed_wave_ledger import WaveLedger  # noqa: E402

PROFILE = {"model": "offline-exact", "input_rate_micro_usd_per_million": 1000000,
           "cached_input_rate_micro_usd_per_million": 1000000,
           "cache_write_rate_micro_usd_per_million": 1000000,
           "output_rate_micro_usd_per_million": 1000000}


def layout(path: Path):
    path.mkdir(mode=0o700)
    roots = []
    for name in ("tool_reservations", "tool_receipts", "requests", "responses"):
        folder = path / name
        folder.mkdir(mode=0o700)
        roots.append(folder)
    ledger = WaveLedger.create(path / "ledger", 100, 8, cost_limit_micro_usd=100,
                               price_profile=PROFILE, effort="medium")
    return ledger, roots + [ledger.directory]


def create(path: Path, **kwargs):
    ledger, roots = layout(path)
    ctx = context.RunContext.create(path / "context", ledger.directory, {},
                                    active_limit_seconds=30, max_tool_calls=0,
                                    roles=["coordinator"], journal_roots=roots,
                                    ledger_kind="wave_v1", **kwargs)
    return ctx, ledger


def reserve(ledger):
    return ledger.reserve_wave("workers", [
        {"request_id": f"request-{i}", "role": f"worker-{i}", "payload_sha256": str(i) * 64,
         "model": PROFILE["model"], "effort": "medium", "input_tokens": 2,
         "max_output_tokens": 3} for i in (1, 2)
    ])


def test_wave_context_uses_exact_budget_and_closes_after_out_of_order_settlement(tmp_path):
    ctx, ledger = create(tmp_path / "run")
    state = json.loads((ctx.directory / "run.json").read_bytes())
    assert state["schema"] == 2
    assert state["bindings"] == {"ledger_kind": "wave_v1", "ledger_schema": 3}
    assert ctx.status()["budget"]["ledger_sha256"] == hashlib.sha256(
        (ledger.directory / "ledger.json").read_bytes()).hexdigest()
    ctx.begin(ctx.status()["checkpoint_sha256"], "coordinator")
    permit = reserve(ledger)
    for i in (1, 2):
        permit.begin_send(f"request-{i}", str(i) * 64)
    with pytest.raises(context.RunContextError, match="unresolved"):
        ctx.finish(1)
    for i in (2, 1):
        ledger.settle(f"request-{i}", str(i + 2) * 64,
                      {"input_tokens": 2, "output_tokens": 1, "total_tokens": 3})
    assert ctx.finish(1)["state"] == "completed"
    reopened = context.RunContext(ctx.directory)
    assert reopened.status()["budget"]["settled_tokens"] == 6
    with pytest.raises(context.RunContextError, match="never resume"):
        reopened.begin(reopened.status()["checkpoint_sha256"], "coordinator")


def test_abort_retains_wave_holds_and_cannot_resume(tmp_path):
    ctx, ledger = create(tmp_path / "run")
    ctx.begin(ctx.status()["checkpoint_sha256"], "coordinator")
    reserve(ledger)
    aborted = ctx.abort("offline injected failure")
    assert aborted["state"] == "indeterminate"
    assert aborted["budget"]["held_tokens"] == 10
    assert aborted["held_active_seconds"] > 0
    with pytest.raises(context.RunContextError):
        ctx.begin(aborted["checkpoint_sha256"], "coordinator")


@pytest.mark.parametrize("field,value", [("ledger_kind", "token"), ("ledger_schema", 2),
                                          ("ledger_schema", True)])
def test_rehashed_selector_tamper_is_rejected(tmp_path, field, value):
    ctx, _ = create(tmp_path / "run")
    path = ctx.directory / "run.json"
    state = json.loads(path.read_bytes())
    state[field] = value
    state["checkpoint_sha256"] = context._checkpoint(state)
    path.write_bytes(context._canonical(state))
    with pytest.raises(context.RunContextError, match="selector"):
        context.RunContext(ctx.directory)


def test_legacy_selector_does_not_auto_detect_or_accept_wave_budget(tmp_path):
    ledger, roots = layout(tmp_path / "run")
    with pytest.raises(BudgetError):
        context.RunContext.create(tmp_path / "run" / "context", ledger.directory, {},
                                  active_limit_seconds=30, max_tool_calls=0,
                                  roles=["coordinator"], journal_roots=roots)
    assert not (tmp_path / "run" / "context").exists()
    with pytest.raises(BudgetError):
        TokenLedger(ledger.directory)


def test_wave_selector_rejects_a_legacy_budget_and_binding_conflict(tmp_path):
    path = tmp_path / "run"
    _, roots = layout(path)
    legacy = TokenLedger.create(path / "legacy", 100, 8)
    with pytest.raises(BudgetError):
        context.RunContext.create(path / "context", legacy.directory, {},
                                  active_limit_seconds=30, max_tool_calls=0,
                                  roles=["coordinator"], journal_roots=roots,
                                  ledger_kind="wave_v1")
    with pytest.raises(context.RunContextError, match="conflicts"):
        context.RunContext.create(path / "context", legacy.directory,
                                  {"ledger_schema": True}, active_limit_seconds=30,
                                  max_tool_calls=0, roles=["coordinator"],
                                  journal_roots=roots, ledger_kind="wave_v1")
