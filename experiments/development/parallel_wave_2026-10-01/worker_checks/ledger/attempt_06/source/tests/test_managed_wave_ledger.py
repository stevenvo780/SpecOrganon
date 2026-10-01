"""Offline contract tests for the opt-in atomic wave budget."""

from __future__ import annotations

import hashlib
import json
import pickle
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import pytest


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
from managed_token_ledger import (  # noqa: E402
    BudgetError, CostBudgetExhausted, TokenBudgetExhausted, TokenLedger,
)
from managed_wave_ledger import WaveLedger  # noqa: E402


PROFILE = {
    "model": "gpt-fixture-exact",
    "input_rate_micro_usd_per_million": 1_000_000,
    "cached_input_rate_micro_usd_per_million": 500_000,
    "cache_write_rate_micro_usd_per_million": 2_000_000,
    "output_rate_micro_usd_per_million": 3_000_000,
}
SHA_A = hashlib.sha256(b"request-a").hexdigest()
SHA_B = hashlib.sha256(b"request-b").hexdigest()
RESPONSE_A = hashlib.sha256(b"response-a").hexdigest()
RESPONSE_B = hashlib.sha256(b"response-b").hexdigest()


def _ledger(tmp_path: Path, *, token_limit: int = 100,
            cost_limit: int = 100, max_requests: int = 8) -> WaveLedger:
    return WaveLedger.create(
        tmp_path / "ledger", token_limit, max_requests,
        cost_limit_micro_usd=cost_limit, price_profile=PROFILE, effort="high",
    )


def _item(request_id: str, payload_sha256: str, *, input_tokens: int = 2,
          max_output_tokens: int = 2, role: str = "specialist") -> dict:
    return {
        "request_id": request_id, "role": role,
        "payload_sha256": payload_sha256,
        "input_tokens": input_tokens, "max_output_tokens": max_output_tokens,
        "model": PROFILE["model"], "effort": "high",
    }


def _usage(input_tokens: int = 2, output_tokens: int = 1) -> dict:
    return {
        "input_tokens": input_tokens, "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
    }


def _raw(ledger: WaveLedger) -> bytes:
    return (ledger.directory / "ledger.json").read_bytes()


def test_snapshot_binds_exact_private_bytes_and_frozen_run_identity(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path)
    snap = ledger.snapshot()
    assert snap["schema"] == 3
    assert snap["ledger_sha256"] == hashlib.sha256(_raw(ledger)).hexdigest()
    assert {key: value for key, value in snap.items() if key != "ledger_sha256"} == ledger.status()
    assert snap["model"] == PROFILE["model"] and snap["effort"] == "high"
    assert snap["price_profile_sha256"] == hashlib.sha256(
        json.dumps(PROFILE, ensure_ascii=True, sort_keys=True,
                   separators=(",", ":")).encode() + b"\n").hexdigest()
    assert snap["request_count"] == 0 and snap["blocked"] is False
    assert snap["remaining_tokens"] == 100 and snap["remaining_cost_micro_usd"] == 100
    assert (ledger.directory / "ledger.json").stat().st_mode & 0o777 == 0o600
    assert ledger.directory.stat().st_mode & 0o777 == 0o700
    with pytest.raises(BudgetError):
        TokenLedger(ledger.directory)


@pytest.mark.parametrize("limit_kind", ["tokens", "cost", "requests"])
def test_full_wave_rejected_atomically_by_each_global_cap(
    tmp_path: Path, limit_kind: str,
) -> None:
    ledger = _ledger(
        tmp_path, token_limit=7 if limit_kind == "tokens" else 100,
        cost_limit=19 if limit_kind == "cost" else 100,
        max_requests=1 if limit_kind == "requests" else 8,
    )
    before = _raw(ledger)
    expected = CostBudgetExhausted if limit_kind == "cost" else TokenBudgetExhausted
    with pytest.raises(expected):
        ledger.reserve_wave("wave-1", [_item("a", SHA_A), _item("b", SHA_B)])
    assert _raw(ledger) == before
    assert ledger.status()["request_count"] == 0


@pytest.mark.parametrize("change", ["duplicate", "model", "effort", "digest", "bool_count"])
def test_invalid_wave_item_has_no_partial_reservation(
    tmp_path: Path, change: str,
) -> None:
    ledger = _ledger(tmp_path)
    other = _item("b", SHA_B)
    if change == "duplicate":
        other["request_id"] = "a"
    elif change == "model":
        other["model"] = "different-model"
    elif change == "effort":
        other["effort"] = "low"
    elif change == "digest":
        other["payload_sha256"] = "not-a-sha"
    else:
        other["input_tokens"] = True
    before = _raw(ledger)
    with pytest.raises(BudgetError):
        ledger.reserve_wave("wave-1", [_item("a", SHA_A), other])
    assert _raw(ledger) == before


def test_one_atomic_wave_precedes_all_send_markers_and_permit_cannot_replay(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    permit = ledger.reserve_wave("wave-1", [_item("a", SHA_A), _item("b", SHA_B)])
    snap = ledger.snapshot()
    assert snap["request_count"] == 2 and snap["blocked"] is True
    assert snap["reserved_tokens"] == 8 and snap["reserved_cost_micro_usd"] == 20
    assert {record["state"] for record in snap["requests"].values()} == {"reserved"}
    assert snap["ledger_sha256"] == hashlib.sha256(_raw(ledger)).hexdigest()
    with pytest.raises(BudgetError, match="exact reserved request"):
        permit.begin_send("a", SHA_B)
    assert ledger.status()["reserved_tokens"] == 8
    started = permit.begin_send("a", SHA_A)
    assert started["state"] == "inflight" and started["send_started_ns"] > 0
    with pytest.raises(BudgetError, match="exact reserved request"):
        permit.begin_send("a", SHA_A)
    with pytest.raises(TypeError):
        pickle.dumps(permit)
    reopened = WaveLedger(ledger.directory)
    with pytest.raises(BudgetError, match="unresolved"):
        reopened.reserve_wave("wave-2", [_item("c", SHA_A)])
    with pytest.raises(BudgetError, match="permit"):
        reopened._begin_send("wave-1", "0" * 64, snap["waves"]["wave-1"]["manifest_sha256"],
                             "b", SHA_B)


@pytest.mark.parametrize("started", [False, True])
def test_process_death_after_wave_reservation_retains_every_hold(
    tmp_path: Path, started: bool,
) -> None:
    path = tmp_path / "ledger"
    code = """
import hashlib, os, sys
from pathlib import Path
sys.path.insert(0, sys.argv[2])
from managed_wave_ledger import WaveLedger
profile = {'model':'gpt-fixture-exact','input_rate_micro_usd_per_million':1000000,
 'cached_input_rate_micro_usd_per_million':500000,
 'cache_write_rate_micro_usd_per_million':2000000,
 'output_rate_micro_usd_per_million':3000000}
ledger = WaveLedger.create(Path(sys.argv[1]), 100, 8,
 cost_limit_micro_usd=100, price_profile=profile, effort='high')
items = [{'request_id':name,'role':'specialist','payload_sha256':hashlib.sha256(name.encode()).hexdigest(),
 'input_tokens':2,'max_output_tokens':2,'model':profile['model'],'effort':'high'}
 for name in ('a','b')]
permit = ledger.reserve_wave('wave-1', items)
if sys.argv[3] == 'started':
 permit.begin_send('a', hashlib.sha256(b'a').hexdigest())
os._exit(0)
"""
    child = subprocess.run([sys.executable, "-c", code, str(path), str(SCRIPTS),
                            "started" if started else "reserved"],
                           capture_output=True, text=True, check=False, timeout=5)
    assert child.returncode == 0 and child.stdout == "" and child.stderr == ""
    ledger = WaveLedger(path)
    assert ledger.status()["reserved_tokens"] == (4 if started else 8)
    assert ledger.status()["inflight_tokens"] == (4 if started else 0)
    assert ledger.status()["reserved_cost_micro_usd"] == (10 if started else 20)
    assert ledger.status()["inflight_cost_micro_usd"] == (10 if started else 0)
    with pytest.raises(BudgetError, match="unresolved"):
        ledger.reserve_wave("wave-2", [_item("c", SHA_A)])


def test_competing_wave_reservations_publish_only_one_complete_batch(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path, token_limit=8, cost_limit=20)
    start = Barrier(2)

    def reserve(wave_id: str, prefix: str) -> str:
        start.wait(timeout=5)
        try:
            ledger.reserve_wave(wave_id, [_item(prefix + "a", SHA_A),
                                          _item(prefix + "b", SHA_B)])
        except BudgetError:
            return "rejected"
        return "reserved"

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(reserve, "wave-1", "one-")
        second = pool.submit(reserve, "wave-2", "two-")
        assert sorted((first.result(timeout=5), second.result(timeout=5))) == [
            "rejected", "reserved"]
    snap = ledger.snapshot()
    assert snap["request_count"] == 2 and snap["wave_count"] == 1
    assert snap["committed_tokens"] == 8 and snap["committed_cost_micro_usd"] == 20


def test_out_of_order_concurrent_settlement_keeps_exact_cost_and_global_cap(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path, token_limit=20, cost_limit=50)
    permit = ledger.reserve_wave("wave-1", [_item("a", SHA_A), _item("b", SHA_B)])
    permit.begin_send("a", SHA_A)
    permit.begin_send("b", SHA_B)
    barrier = Barrier(2)

    def settle_one(request_id: str, response_sha: str, output_tokens: int) -> dict:
        barrier.wait(timeout=5)
        return ledger.settle(request_id, response_sha, _usage(output_tokens=output_tokens))

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(settle_one, "b", RESPONSE_B, 0)
        second = pool.submit(settle_one, "a", RESPONSE_A, 1)
        results = [first.result(timeout=5), second.result(timeout=5)]
    assert {result["state"] for result in results} == {"settled"}
    snap = ledger.snapshot()
    assert snap["blocked"] is False and snap["committed_tokens"] == 5
    assert snap["committed_cost_micro_usd"] == 11
    assert snap["requests"]["a"]["response_sha256"] == RESPONSE_A
    assert snap["requests"]["b"]["response_sha256"] == RESPONSE_B
    second_wave = ledger.reserve_wave("wave-2", [_item("c", SHA_A)])
    assert second_wave.begin_send("c", SHA_A)["state"] == "inflight"
    assert ledger.status()["committed_tokens"] == 9


def test_invalid_usage_spends_one_full_hold_while_sibling_can_settle(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    permit = ledger.reserve_wave("wave-1", [_item("a", SHA_A), _item("b", SHA_B)])
    permit.begin_send("a", SHA_A)
    permit.begin_send("b", SHA_B)
    with pytest.raises(BudgetError, match="measured input"):
        ledger.settle("a", RESPONSE_A, _usage(input_tokens=3))
    other = ledger.settle("b", RESPONSE_B, _usage())
    assert other["state"] == "settled"
    snap = ledger.snapshot()
    assert snap["requests"]["a"]["state"] == "indeterminate"
    assert snap["requests"]["a"]["response_sha256"] == RESPONSE_A
    assert snap["indeterminate_tokens"] == 4 and snap["indeterminate_cost_micro_usd"] == 10
    assert snap["settled_tokens"] == 3 and snap["settled_cost_micro_usd"] == 7
    assert snap["blocked"] is True
    with pytest.raises(BudgetError, match="unresolved"):
        ledger.reserve_wave("wave-2", [_item("c", SHA_A)])


def test_mark_unsent_indeterminate_blocks_sibling_launch_and_keeps_full_hold(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    permit = ledger.reserve_wave("wave-1", [_item("a", SHA_A), _item("b", SHA_B)])
    with pytest.raises(BudgetError, match="unsent wave reservation"):
        ledger.mark_indeterminate("a", "false response", response_sha256=RESPONSE_A)
    assert ledger.status()["requests"]["a"]["state"] == "reserved"
    record = ledger.mark_indeterminate("a", "fixture failure before send")
    assert record["send_started_ns"] is None
    assert record["reason_sha256"] == hashlib.sha256(
        b"fixture failure before send").hexdigest()
    assert "fixture failure before send" not in _raw(ledger).decode()
    with pytest.raises(BudgetError, match="indeterminate sibling"):
        permit.begin_send("b", SHA_B)
    assert ledger.status()["committed_tokens"] == 8
    assert ledger.status()["committed_cost_micro_usd"] == 20


def test_cache_details_price_exactly_and_invalid_details_never_refund(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path)
    permit = ledger.reserve_wave("wave-1", [_item("a", SHA_A, input_tokens=5,
                                                 max_output_tokens=2)])
    permit.begin_send("a", SHA_A)
    details = {"input_tokens_details": {"cache_read_tokens": 2,
                                        "cache_write_tokens": 1,
                                        "uncached_tokens": 2},
               "output_tokens_details": {"reasoning_tokens": 1}}
    settled = ledger.settle("a", RESPONSE_A, _usage(input_tokens=5), usage_details=details)
    assert settled["held_cost_micro_usd"] == 8  # 2*.5 + 1*2 + 2*1 + 1*3
    assert settled["usage_details"] == details
    second = ledger.reserve_wave("wave-2", [_item("b", SHA_B, input_tokens=1,
                                                  max_output_tokens=1)])
    second.begin_send("b", SHA_B)
    bad = {"input_tokens_details": {"cached_tokens": 2, "cache_read_tokens": 1}}
    with pytest.raises(BudgetError, match="aliases disagree"):
        ledger.settle("b", RESPONSE_B, _usage(input_tokens=1), usage_details=bad)
    assert ledger.status()["requests"]["b"]["state"] == "indeterminate"
    assert ledger.status()["requests"]["b"]["held_cost_micro_usd"] == 5


@pytest.mark.parametrize("tamper", ["whitespace", "duplicate_key", "wrong_effort",
                                    "wrong_state", "wrong_cost", "symlink", "mode"])
def test_reopen_rejects_tampered_or_nonprivate_ledger(tmp_path: Path, tamper: str) -> None:
    ledger = _ledger(tmp_path)
    ledger.reserve_wave("wave-1", [_item("a", SHA_A)])
    path = ledger.directory / "ledger.json"
    raw = path.read_bytes()
    if tamper == "whitespace":
        path.write_bytes(raw + b" ")
    elif tamper == "duplicate_key":
        path.write_bytes(raw[:-2] + b',"schema":3}\n')
    elif tamper == "wrong_effort":
        value = json.loads(raw)
        value["effort"] = "low"
        path.write_bytes(json.dumps(value, sort_keys=True, separators=(",", ":"))
                         .encode() + b"\n")
    elif tamper == "wrong_state":
        value = json.loads(raw)
        value["requests"]["a"]["state"] = []
        path.write_bytes(json.dumps(value, sort_keys=True, separators=(",", ":"))
                         .encode() + b"\n")
    elif tamper == "wrong_cost":
        value = json.loads(raw)
        value["requests"]["a"]["held_cost_micro_usd"] = 0
        path.write_bytes(json.dumps(value, sort_keys=True, separators=(",", ":"))
                         .encode() + b"\n")
    elif tamper == "symlink":
        outside = tmp_path / "outside.json"
        outside.write_bytes(raw)
        path.unlink()
        path.symlink_to(outside)
    else:
        path.chmod(0o644)
    with pytest.raises(BudgetError):
        WaveLedger(ledger.directory)
