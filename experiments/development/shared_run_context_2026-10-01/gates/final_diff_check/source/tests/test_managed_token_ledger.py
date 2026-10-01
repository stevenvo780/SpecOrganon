"""Durable, fail-closed token-budget ledger checks."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
from managed_token_ledger import (  # noqa: E402
    BudgetError, CostBudgetExhausted, TokenBudgetExhausted, TokenLedger,
)


PAYLOAD_SHA256 = hashlib.sha256(b"test payload bytes").hexdigest()
PRICE_PROFILE = {
    "model": "gpt-test-exact",
    "input_rate_micro_usd_per_million": 2_000_000,
    "cached_input_rate_micro_usd_per_million": 500_000,
    "cache_write_rate_micro_usd_per_million": 4_000_000,
    "output_rate_micro_usd_per_million": 8_000_000,
}


def _ledger(tmp_path: Path, *, limit: int = 100, max_requests: int = 10) -> TokenLedger:
    return TokenLedger.create(tmp_path / "ledger", limit, max_requests)


def _reserve(ledger: TokenLedger, request_id: str, role: str,
             input_tokens: int, output_tokens: int) -> dict:
    return ledger.reserve(request_id, role, PAYLOAD_SHA256, input_tokens, output_tokens)


def _cost_ledger(tmp_path: Path, *, cost_limit: int = 100,
                 token_limit: int = 100) -> TokenLedger:
    return TokenLedger.create(tmp_path / "ledger", token_limit, 10,
                              cost_limit_micro_usd=cost_limit,
                              price_profile=PRICE_PROFILE)


def _cost_reserve(ledger: TokenLedger, request_id: str,
                  input_tokens: int, output_tokens: int) -> dict:
    return ledger.reserve(request_id, "leader", PAYLOAD_SHA256,
                          input_tokens, output_tokens, model=PRICE_PROFILE["model"])


def test_budget_is_reserved_before_simulated_provider_send(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path, limit=10)
    sent: list[str] = []

    with pytest.raises(BudgetError, match="before provider request"):
        reservation = _reserve(ledger, "too-large", "leader", 6, 5)
        sent.append(reservation["request_id"])

    assert sent == []
    assert ledger.status()["committed_tokens"] == 0


def test_settlement_releases_unused_reservation(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path, limit=10)
    _reserve(ledger, "first", "leader", 5, 5)

    settled = ledger.settle("first", {
        "input_tokens": 5, "output_tokens": 2, "total_tokens": 7,
    })

    assert settled["state"] == "settled"
    assert ledger.status()["settled_tokens"] == 7
    assert ledger.status()["remaining_tokens"] == 3
    second = _reserve(ledger, "second", "reviewer", 1, 2)
    assert second["held_tokens"] == 3


def test_duplicate_request_id_is_rejected(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path)
    _reserve(ledger, "same", "leader", 1, 2)

    with pytest.raises(BudgetError, match="already been reserved"):
        _reserve(ledger, "same", "reviewer", 1, 2)


def test_request_cap_counts_all_reserved_requests(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path, limit=100, max_requests=1)
    _reserve(ledger, "first", "leader", 1, 1)

    with pytest.raises(BudgetError, match="request cap exhausted"):
        _reserve(ledger, "second", "reviewer", 1, 1)


@pytest.mark.parametrize("usage", [
    None,
    {"input_tokens": 4, "output_tokens": 1},
    {"input_tokens": 4, "output_tokens": 1, "total_tokens": 8},
    {"input_tokens": 3, "output_tokens": 1, "total_tokens": 4},
    {"input_tokens": 4, "output_tokens": 4, "total_tokens": 8},
    {"input_tokens": True, "output_tokens": 1, "total_tokens": 2},
])
def test_missing_or_inconsistent_usage_fails_closed(
    tmp_path: Path, usage: object,
) -> None:
    ledger = _ledger(tmp_path, limit=20)
    _reserve(ledger, "request", "leader", 4, 3)

    with pytest.raises(BudgetError):
        ledger.settle("request", usage)  # type: ignore[arg-type]

    recovered = TokenLedger(tmp_path / "ledger")
    status = recovered.status()
    assert status["blocked"] is True
    assert status["indeterminate_tokens"] == 7
    assert status["remaining_tokens"] == 13
    with pytest.raises(BudgetError, match="indeterminate request"):
        _reserve(recovered, "later", "reviewer", 0, 0)


def test_roles_share_one_budget(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path, limit=10)
    _reserve(ledger, "leader-call", "leader", 3, 3)
    ledger.settle("leader-call", {"input_tokens": 3, "output_tokens": 3,
                                  "total_tokens": 6})

    with pytest.raises(BudgetError, match="before provider request"):
        _reserve(ledger, "reviewer-call", "reviewer", 2, 3)

    assert ledger.status()["committed_tokens"] == 6


def test_crash_after_reservation_blocks_recovery_until_review(tmp_path: Path) -> None:
    directory = tmp_path / "ledger"
    TokenLedger.create(directory, limit_tokens=30, max_requests=4)
    marker = tmp_path / "fake-send-started"
    code = """
import os, sys
from pathlib import Path
from managed_token_ledger import TokenLedger
ledger = TokenLedger(Path(sys.argv[1]))
ledger.reserve('first', 'leader', sys.argv[3], 8, 10)
Path(sys.argv[2]).write_text('send started')
os._exit(137)
"""
    child = subprocess.run(
        [sys.executable, "-c", code, str(directory), str(marker), PAYLOAD_SHA256],
        env={**os.environ, "PYTHONPATH": str(SCRIPTS)}, check=False,
        capture_output=True, text=True,
    )
    assert child.returncode == 137
    assert marker.read_text() == "send started"

    recovered = TokenLedger(directory)
    assert recovered.status()["blocked"] is True
    assert recovered.status()["reserved_tokens"] == 18
    assert recovered.status()["remaining_tokens"] == 12
    with pytest.raises(BudgetError, match="unresolved reserved request"):
        _reserve(recovered, "second", "reviewer", 1, 1)


def test_real_processes_cannot_overreserve_shared_budget(tmp_path: Path) -> None:
    directory = tmp_path / "ledger"
    TokenLedger.create(directory, limit_tokens=10, max_requests=4)
    start_file = tmp_path / "start"
    code = """
import sys, time
sys.path.insert(0, sys.argv[3])
from managed_token_ledger import BudgetError, TokenLedger
ledger = TokenLedger(sys.argv[1])
while not __import__('pathlib').Path(sys.argv[2]).exists():
    time.sleep(0.001)
try:
    ledger.reserve(sys.argv[4], sys.argv[5], sys.argv[6], 6, 0)
except BudgetError:
    print('blocked')
else:
    print('reserved')
"""
    base = [sys.executable, "-c", code, str(directory), str(start_file), str(SCRIPTS)]
    first_args = [*base, "request-a", "leader", PAYLOAD_SHA256]
    second_args = [*base, "request-b", "reviewer", PAYLOAD_SHA256]
    first = subprocess.Popen(first_args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    second = subprocess.Popen(second_args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    start_file.touch()
    out_a, err_a = first.communicate(timeout=10)
    out_b, err_b = second.communicate(timeout=10)

    assert first.returncode == 0, err_a
    assert second.returncode == 0, err_b
    assert sorted([out_a.strip(), out_b.strip()]) == ["blocked", "reserved"]
    assert TokenLedger(directory).status()["committed_tokens"] == 6


def test_new_instance_recovers_canonical_durable_reservation(tmp_path: Path) -> None:
    directory = tmp_path / "ledger"
    ledger = TokenLedger.create(directory, limit_tokens=12, max_requests=3)
    reserved = _reserve(ledger, "recoverable", "specialist", 5, 4)

    raw = (directory / "ledger.json").read_bytes()
    assert raw.endswith(b"\n")
    assert raw == (json.dumps(json.loads(raw), sort_keys=True,
                              separators=(",", ":")) + "\n").encode()
    assert os.stat(directory).st_mode & 0o777 == 0o700
    assert os.stat(directory / "ledger.json").st_mode & 0o777 == 0o600

    recovered = TokenLedger(directory)
    assert recovered.status()["requests"]["recoverable"] == reserved
    assert recovered.status()["remaining_tokens"] == 3


def test_indeterminate_reason_text_is_not_persisted(tmp_path: Path) -> None:
    directory = tmp_path / "ledger"
    ledger = TokenLedger.create(directory, limit_tokens=10, max_requests=2)
    _reserve(ledger, "request", "leader", 2, 3)
    secret_like_reason = "private prompt fragment must not appear"

    ledger.mark_indeterminate("request", secret_like_reason)

    raw = (directory / "ledger.json").read_text(encoding="utf-8")
    assert secret_like_reason not in raw
    assert ledger.status()["blocked"] is True


def test_schema_one_durable_shape_and_optional_status_are_compatible(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path)
    assert set(json.loads((tmp_path / "ledger" / "ledger.json").read_text())) == {
        "schema", "limit_tokens", "max_requests", "requests",
    }
    ledger.reserve("first", "leader", PAYLOAD_SHA256, 1, 1, model="ignored-by-schema-one")
    ledger.settle("first", {"input_tokens": 1, "output_tokens": 0,
                            "total_tokens": 1},
                  usage_details={"input_tokens_details": {"cached_tokens": 100}})
    status = ledger.status()
    assert status["schema"] == 1
    assert status["committed_tokens"] == 1
    assert status["committed_cost_micro_usd"] is None
    assert status["price_profile"] is None


def test_schema_two_rejects_incomplete_or_invalid_profile_before_creating_directory(
    tmp_path: Path,
) -> None:
    path = tmp_path / "ledger"
    with pytest.raises(BudgetError, match="supplied together"):
        TokenLedger.create(path, 100, 10, cost_limit_micro_usd=100)
    assert not path.exists()
    with pytest.raises(BudgetError, match="nonnegative integer"):
        TokenLedger.create(path, 100, 10, cost_limit_micro_usd=100,
                           price_profile={**PRICE_PROFILE,
                                          "cache_write_rate_micro_usd_per_million": True})
    assert not path.exists()


def test_cost_cap_rejects_before_simulated_send_and_exposes_typed_exhaustion(
    tmp_path: Path,
) -> None:
    ledger = _cost_ledger(tmp_path, cost_limit=79)
    sent: list[str] = []
    with pytest.raises(CostBudgetExhausted, match="before provider request"):
        reservation = _cost_reserve(ledger, "too-expensive", 10, 5)
        sent.append(reservation["request_id"])
    assert sent == []
    status = TokenLedger(tmp_path / "ledger").status()
    assert status["committed_tokens"] == 0
    assert status["committed_cost_micro_usd"] == 0
    assert status["remaining_cost_micro_usd"] == 79
    assert status["price_profile"] == PRICE_PROFILE
    canonical_profile = (json.dumps(PRICE_PROFILE, sort_keys=True,
                                    separators=(",", ":")) + "\n").encode()
    assert status["price_profile_sha256"] == hashlib.sha256(canonical_profile).hexdigest()
    with pytest.raises(BudgetError, match="exactly match"):
        ledger.reserve("wrong-model", "leader", PAYLOAD_SHA256, 1, 1,
                       model="gpt-test-exact-variant")
    with pytest.raises(TokenBudgetExhausted):
        ledger.reserve("too-many-tokens", "leader", PAYLOAD_SHA256, 101, 0,
                       model=PRICE_PROFILE["model"])

    zero_cap = TokenLedger.create(tmp_path / "zero-cap", 100, 1,
                                  cost_limit_micro_usd=0, price_profile=PRICE_PROFILE)
    with pytest.raises(CostBudgetExhausted):
        _cost_reserve(zero_cap, "blocked-by-zero-cap", 1, 0)


def test_cache_write_premium_is_reserved_and_known_details_release_cost(
    tmp_path: Path,
) -> None:
    ledger = _cost_ledger(tmp_path, cost_limit=80)
    reserved = _cost_reserve(ledger, "first", 10, 5)
    assert reserved["held_cost_micro_usd"] == 80  # 10 * max(2, .5, 4) + 5 * 8
    details = {
        "input_tokens_details": {
            "cached_tokens": 2, "cache_write_tokens": 3, "uncached_tokens": 5,
            "future_provider_field": 9,
        },
        "output_tokens_details": {"reasoning_tokens": 1, "other_metadata": 7},
    }
    settled = ledger.settle("first", {"input_tokens": 10, "output_tokens": 2,
                                      "total_tokens": 12}, usage_details=details)
    assert settled["held_cost_micro_usd"] == 39  # 2*.5 + 3*4 + 5*2 + 2*8
    assert settled["usage_details"] == details
    status = TokenLedger(tmp_path / "ledger").status()
    assert status["settled_cost_micro_usd"] == 39
    assert status["remaining_cost_micro_usd"] == 41
    with pytest.raises(CostBudgetExhausted):
        _cost_reserve(ledger, "second", 1, 5)  # 4 + 40 > 41


def test_missing_input_breakdown_uses_maximum_rate_and_integer_ceiling(
    tmp_path: Path,
) -> None:
    ledger = _cost_ledger(tmp_path, cost_limit=100)
    _cost_reserve(ledger, "first", 10, 2)
    settled = ledger.settle("first", {"input_tokens": 10, "output_tokens": 2,
                                      "total_tokens": 12}, usage_details={
                                          "input_tokens_details": {"cached_tokens": 2},
                                      })
    assert settled["held_cost_micro_usd"] == 49  # 2*.5 + 8*4 + 2*8

    tiny_profile = {**PRICE_PROFILE,
                    "input_rate_micro_usd_per_million": 1,
                    "cached_input_rate_micro_usd_per_million": 0,
                    "cache_write_rate_micro_usd_per_million": 0,
                    "output_rate_micro_usd_per_million": 1}
    tiny = TokenLedger.create(tmp_path / "tiny", 2, 1,
                              cost_limit_micro_usd=1, price_profile=tiny_profile)
    assert tiny.reserve("tiny", "leader", PAYLOAD_SHA256, 1, 0,
                        model=tiny_profile["model"])["held_cost_micro_usd"] == 1


@pytest.mark.parametrize("details", [
    {"input_tokens_details": {"cached_tokens": 7, "cache_write_tokens": 4}},
    {"output_tokens_details": {"reasoning_tokens": 3}},
    {"input_tokens_details": {"cache_write_tokens": -1}},
    {"input_tokens_details": {"cached_tokens": 2, "cache_read_tokens": 3}},
])
def test_invalid_usage_details_hold_both_reservations_and_block(
    tmp_path: Path, details: dict,
) -> None:
    ledger = _cost_ledger(tmp_path, cost_limit=80)
    _cost_reserve(ledger, "first", 10, 5)
    with pytest.raises(BudgetError):
        ledger.settle("first", {"input_tokens": 10, "output_tokens": 2,
                                "total_tokens": 12}, usage_details=details)
    status = TokenLedger(tmp_path / "ledger").status()
    assert status["blocked"] is True
    assert status["indeterminate_tokens"] == 15
    assert status["indeterminate_cost_micro_usd"] == 80
    with pytest.raises(BudgetError, match="indeterminate request"):
        _cost_reserve(ledger, "later", 0, 0)


def test_schema_two_crash_after_reservation_retains_both_caps(tmp_path: Path) -> None:
    directory = tmp_path / "ledger"
    TokenLedger.create(directory, 100, 2, cost_limit_micro_usd=80,
                       price_profile=PRICE_PROFILE)
    marker = tmp_path / "fake-send-started"
    code = """
import os, sys
from pathlib import Path
from managed_token_ledger import TokenLedger
ledger = TokenLedger(Path(sys.argv[1]))
ledger.reserve('first', 'leader', sys.argv[3], 10, 5, model='gpt-test-exact')
Path(sys.argv[2]).write_text('send started')
os._exit(137)
"""
    child = subprocess.run(
        [sys.executable, "-c", code, str(directory), str(marker), PAYLOAD_SHA256],
        env={**os.environ, "PYTHONPATH": str(SCRIPTS)}, check=False,
        capture_output=True, text=True,
    )
    assert child.returncode == 137
    assert marker.read_text() == "send started"
    status = TokenLedger(directory).status()
    assert status["reserved_tokens"] == 15
    assert status["reserved_cost_micro_usd"] == 80
    assert status["remaining_cost_micro_usd"] == 0
    with pytest.raises(BudgetError, match="unresolved reserved request"):
        _cost_reserve(TokenLedger(directory), "later", 0, 0)


def test_real_processes_cannot_overreserve_schema_two_cost_cap(tmp_path: Path) -> None:
    directory = tmp_path / "ledger"
    TokenLedger.create(directory, 100, 2, cost_limit_micro_usd=4,
                       price_profile=PRICE_PROFILE)
    start_file = tmp_path / "start"
    code = """
import sys, time
from pathlib import Path
from managed_token_ledger import BudgetError, TokenLedger
ledger = TokenLedger(Path(sys.argv[1]))
while not Path(sys.argv[2]).exists():
    time.sleep(0.001)
try:
    ledger.reserve(sys.argv[3], 'leader', sys.argv[4], 1, 0,
                   model='gpt-test-exact')
except BudgetError:
    print('blocked')
else:
    print('reserved')
"""
    base = [sys.executable, "-c", code, str(directory), str(start_file)]
    first = subprocess.Popen([*base, "request-a", PAYLOAD_SHA256],
                             env={**os.environ, "PYTHONPATH": str(SCRIPTS)},
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    second = subprocess.Popen([*base, "request-b", PAYLOAD_SHA256],
                              env={**os.environ, "PYTHONPATH": str(SCRIPTS)},
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    start_file.touch()
    out_a, err_a = first.communicate(timeout=10)
    out_b, err_b = second.communicate(timeout=10)
    assert first.returncode == 0, err_a
    assert second.returncode == 0, err_b
    assert sorted([out_a.strip(), out_b.strip()]) == ["blocked", "reserved"]
    status = TokenLedger(directory).status()
    assert status["reserved_tokens"] == 1
    assert status["reserved_cost_micro_usd"] == 4
    assert status["remaining_cost_micro_usd"] == 0
