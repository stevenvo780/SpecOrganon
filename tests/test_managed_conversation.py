"""Offline contract tests for a bounded, sequential Responses conversation."""

from __future__ import annotations

import copy
import hashlib
import json
import stat
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from managed_token_ledger import TokenLedger  # noqa: E402
from run_managed_conversation import (  # noqa: E402
    ActiveDeadlineExceeded,
    ConversationError,
    execute_conversation,
    main,
    prepare_conversation,
    read_conversation_status,
)


PRICE_PROFILE = {
    "model": "gpt-6-luna",
    "input_rate_micro_usd_per_million": 1_000_000,
    "cached_input_rate_micro_usd_per_million": 1_000_000,
    "cache_write_rate_micro_usd_per_million": 2_000_000,
    "output_rate_micro_usd_per_million": 1_000_000,
}


def _response(number: int, text: str | None, *, status: str = "completed",
              with_reasoning: bool = False,
              with_usage_details: bool = False,
              service_tier: str | None = None) -> dict[str, Any]:
    content = [] if text is None else [{"type": "output_text", "text": text}]
    output: list[dict[str, Any]] = []
    if with_reasoning:
        output.append({"id": f"rs_fake_{number}", "type": "reasoning", "summary": [],
                       "encrypted_content": "opaque-test-reasoning"})
    output.append({"id": f"msg_fake_{number}", "type": "message", "role": "assistant",
                   "phase": "final_answer", "content": content})
    usage: dict[str, Any] = {"input_tokens": 8, "output_tokens": 4,
                             "total_tokens": 12}
    if with_usage_details:
        usage["input_tokens_details"] = {"cached_tokens": 3}
        usage["output_tokens_details"] = {"reasoning_tokens": 2}
    response = {
        "id": f"resp_fake_{number}",
        "model": "gpt-6-luna",
        "status": status,
        "usage": usage,
        "output": output,
    }
    if service_tier is not None:
        response["service_tier"] = service_tier
    return response


class FakeTransport:
    def __init__(self, responses: list[dict[str, Any]], *, fail_send: bool = False) -> None:
        self.responses = responses
        self.fail_send = fail_send
        self.counts: list[dict[str, Any]] = []
        self.sends: list[dict[str, Any]] = []

    def count_input(self, payload: dict[str, Any]) -> int:
        self.counts.append(copy.deepcopy(payload))
        return 8

    def send(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.sends.append(copy.deepcopy(payload))
        if self.fail_send:
            raise TimeoutError("synthetic transport timeout")
        index = len(self.sends) - 1
        assert index < len(self.responses), "unexpected extra provider send"
        return copy.deepcopy(self.responses[index])


def _plan() -> dict[str, Any]:
    return {
        "schema": 1,
        "model": "gpt-6-luna",
        "instructions": "Answer only the user's current question.",
        "reasoning": {"effort": "low"},
        "turns": [
            {"user": "What is the first step?", "max_output_tokens": 10},
            {"user": "What follows that step?", "max_output_tokens": 10},
        ],
    }


def _priced_plan() -> dict[str, Any]:
    return {**_plan(), "service_tier": "default"}


def _ledger(run_dir: Path) -> dict[str, Any]:
    ledger_files = list(run_dir.rglob("ledger.json"))
    assert len(ledger_files) == 1, "the conversation must share one token ledger"
    return TokenLedger(ledger_files[0].parent).status()


def _assert_persisted_turn(run_dir: Path, number: int) -> None:
    name = f"{number:04d}.json"
    response_id = f"resp_fake_{number}"
    request_path = run_dir / "requests" / name
    response_path = run_dir / "responses" / name
    receipt_path = run_dir / "receipts" / name
    request = json.loads(request_path.read_text(encoding="utf-8"))
    response = json.loads(response_path.read_text(encoding="utf-8"))
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert request["model"] == "gpt-6-luna"
    assert response["id"] == receipt["provider_response_id"] == response_id
    assert receipt["response_sha256"] == hashlib.sha256(response_path.read_bytes()).hexdigest()
    for path in (request_path, response_path, receipt_path):
        assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_two_turns_chain_text_and_share_one_metered_ledger(tmp_path: Path) -> None:
    run_dir = tmp_path / "conversation"
    prepare_conversation(run_dir, _plan())
    assert stat.S_IMODE(run_dir.stat().st_mode) == 0o700
    assert _ledger(run_dir)["request_count"] == 0

    first_response = _response(1, "Start with a baseline.", with_reasoning=True,
                               with_usage_details=True)
    transport = FakeTransport([first_response,
                               _response(2, "Then compare the intervention.")])
    summary = execute_conversation(run_dir, transport)

    assert summary["state"] == "completed"
    assert summary["turns_completed"] == 2
    assert len(transport.counts) == len(transport.sends) == 2
    first, second = transport.sends
    assert first["model"] == second["model"] == "gpt-6-luna"
    assert first["instructions"] == second["instructions"] == _plan()["instructions"]
    assert first["reasoning"] == second["reasoning"] == {"effort": "low"}
    assert first["max_output_tokens"] == second["max_output_tokens"] == 10
    assert first["store"] is second["store"] is False
    assert first["stream"] is second["stream"] is False
    for counted, sent in zip(transport.counts, transport.sends, strict=True):
        assert counted == {key: value for key, value in sent.items()
                           if key not in {"max_output_tokens", "store", "stream"}}
    assert first["input"] == [{"role": "user", "content": "What is the first step?"}]
    assert second["input"] == [
        {"role": "user", "content": "What is the first step?"},
        *first_response["output"],
        {"role": "user", "content": "What follows that step?"},
    ]
    assert second["input"][1]["encrypted_content"] == "opaque-test-reasoning"
    assert second["input"][2]["phase"] == "final_answer"
    assert _ledger(run_dir)["request_count"] == 2
    assert _ledger(run_dir)["settled_tokens"] == 24
    _assert_persisted_turn(run_dir, 1)
    _assert_persisted_turn(run_dir, 2)
    receipt = json.loads((run_dir / "receipts" / "0001.json").read_text(encoding="utf-8"))
    assert receipt["usage"] == first_response["usage"]
    status = read_conversation_status(run_dir)
    assert status["state"] == "completed"
    assert status["completed_artifacts_verified"] is True


def test_priced_two_turns_share_cost_cap_and_status_verifies_receipts(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "conversation"
    prepared = prepare_conversation(
        run_dir, _priced_plan(), cost_limit_micro_usd=46,
        price_profile=PRICE_PROFILE,
    )
    assert prepared["budget"]["cost_limit_micro_usd"] == 46
    assert prepared["budget"]["request_count"] == 0
    transport = FakeTransport([
        _response(1, "Start with a baseline.", service_tier="default"),
        _response(2, "Then compare the intervention.", service_tier="default"),
    ])

    summary = execute_conversation(run_dir, transport)

    assert summary["state"] == "completed"
    assert summary["turns_completed"] == 2
    assert len(transport.counts) == len(transport.sends) == 2
    assert all("service_tier" not in payload for payload in transport.counts)
    assert all(payload["service_tier"] == "default" for payload in transport.sends)
    budget = summary["budget"]
    assert budget["request_count"] == 2
    assert budget["settled_tokens"] == 24
    assert budget["settled_cost_micro_usd"] == 40
    assert budget["remaining_cost_micro_usd"] == 6
    assert summary["cost_basis"] == "declared_price_ceiling_not_invoice"
    for number in (1, 2):
        receipt = json.loads((run_dir / "receipts" / f"{number:04d}.json").read_text())
        assert receipt["budget"]["held_cost_micro_usd"] == 20
        assert receipt["cost_basis"] == "declared_price_ceiling_not_invoice"
        _assert_persisted_turn(run_dir, number)
    status = read_conversation_status(run_dir)
    assert status["budget"]["settled_cost_micro_usd"] == 40
    assert status["completed_artifacts_verified"] is True

    receipt_path = run_dir / "receipts" / "0002.json"
    receipt = json.loads(receipt_path.read_text())
    receipt["budget"]["held_cost_micro_usd"] = 19
    receipt_path.write_text(
        json.dumps(receipt, ensure_ascii=True, sort_keys=True,
                   separators=(",", ":")) + "\n", encoding="utf-8",
    )
    with pytest.raises(ConversationError, match="artifacts disagree"):
        read_conversation_status(run_dir)

    receipt["budget"]["held_cost_micro_usd"] = 20
    response_path = run_dir / "responses" / "0002.json"
    response = json.loads(response_path.read_text())
    original_response = json.loads(response_path.read_text())
    response["usage"]["input_tokens_details"] = {"cached_tokens": 3}
    response_path.write_text(
        json.dumps(response, ensure_ascii=True, sort_keys=True,
                   separators=(",", ":")) + "\n", encoding="utf-8",
    )
    receipt["usage"] = response["usage"]
    receipt["response_sha256"] = hashlib.sha256(response_path.read_bytes()).hexdigest()
    receipt_path.write_text(
        json.dumps(receipt, ensure_ascii=True, sort_keys=True,
                   separators=(",", ":")) + "\n", encoding="utf-8",
    )
    with pytest.raises(ConversationError, match="artifacts disagree"):
        read_conversation_status(run_dir)

    response_path.write_text(
        json.dumps(original_response, ensure_ascii=True, sort_keys=True,
                   separators=(",", ":")) + "\n", encoding="utf-8",
    )
    receipt["usage"] = original_response["usage"]
    receipt["response_sha256"] = hashlib.sha256(response_path.read_bytes()).hexdigest()
    receipt_path.write_text(
        json.dumps(receipt, ensure_ascii=True, sort_keys=True,
                   separators=(",", ":")) + "\n", encoding="utf-8",
    )
    assert read_conversation_status(run_dir)["completed_artifacts_verified"] is True

    receipt["budget"]["held_tokens"] = 9999
    receipt_path.write_text(
        json.dumps(receipt, ensure_ascii=True, sort_keys=True,
                   separators=(",", ":")) + "\n", encoding="utf-8",
    )
    with pytest.raises(ConversationError, match="artifacts disagree"):
        read_conversation_status(run_dir)


def test_second_turn_cost_shortfall_truncates_without_send(tmp_path: Path) -> None:
    run_dir = tmp_path / "conversation"
    # First turn settles at 20. The second needs 26 reserved; only 25 remain.
    prepare_conversation(
        run_dir, _priced_plan(), cost_limit_micro_usd=45,
        price_profile=PRICE_PROFILE,
    )
    transport = FakeTransport([
        _response(1, "Start with a baseline.", service_tier="default"),
    ])

    summary = execute_conversation(run_dir, transport)

    assert summary["state"] == "truncated"
    assert summary["reason"] == "cost_budget"
    assert summary["turns_completed"] == 1
    assert len(transport.counts) == 2
    assert len(transport.sends) == 1
    budget = summary["budget"]
    assert budget["request_count"] == 1
    assert budget["settled_cost_micro_usd"] == 20
    assert budget["remaining_cost_micro_usd"] == 25
    assert read_conversation_status(run_dir)["reason"] == "cost_budget"
    assert (run_dir / "requests" / "0002.json").exists()
    assert not (run_dir / "responses" / "0002.json").exists()


def test_zero_cost_cap_is_a_valid_prepared_run_that_cannot_send(tmp_path: Path) -> None:
    run_dir = tmp_path / "conversation"
    prepared = prepare_conversation(
        run_dir, _priced_plan(), cost_limit_micro_usd=0,
        price_profile=PRICE_PROFILE,
    )
    assert prepared["budget"]["remaining_cost_micro_usd"] == 0
    assert read_conversation_status(run_dir)["state"] == "prepared"

    transport = FakeTransport([])
    summary = execute_conversation(run_dir, transport)

    assert summary["state"] == "truncated"
    assert summary["reason"] == "cost_budget"
    assert summary["turns_completed"] == 0
    assert len(transport.sends) == 0


def test_incomplete_response_stops_before_second_turn(tmp_path: Path) -> None:
    run_dir = tmp_path / "conversation"
    prepare_conversation(run_dir, _plan())
    transport = FakeTransport([_response(1, "Partial answer", status="incomplete")])

    summary = execute_conversation(run_dir, transport)

    assert summary["state"] == "truncated"
    assert summary["reason"] == "provider_incomplete"
    assert summary["turns_completed"] == 1
    assert len(transport.sends) == 1
    assert _ledger(run_dir)["request_count"] == 1
    assert _ledger(run_dir)["settled_tokens"] == 12
    _assert_persisted_turn(run_dir, 1)
    assert read_conversation_status(run_dir)["state"] == "truncated"


def test_second_turn_budget_shortfall_does_not_send(tmp_path: Path) -> None:
    run_dir = tmp_path / "conversation"
    # Turn one settles at 12; turn two requires 8 counted + 10 reserved = 18.
    prepare_conversation(run_dir, _plan(), limit_tokens=29)
    transport = FakeTransport([_response(1, "Start with a baseline.")])

    summary = execute_conversation(run_dir, transport)

    assert summary["state"] == "truncated"
    assert summary["reason"] == "token_budget"
    assert summary["turns_completed"] == 1
    assert len(transport.counts) == 2
    assert len(transport.sends) == 1
    ledger = _ledger(run_dir)
    assert ledger["request_count"] == 1
    assert ledger["settled_tokens"] == 12
    assert ledger["remaining_tokens"] == 17
    _assert_persisted_turn(run_dir, 1)
    assert read_conversation_status(run_dir)["state"] == "truncated"
    assert (run_dir / "requests" / "0002.json").exists()
    assert not (run_dir / "responses" / "0002.json").exists()


def test_send_failure_blocks_second_execution_without_retry(tmp_path: Path) -> None:
    run_dir = tmp_path / "conversation"
    prepare_conversation(run_dir, _plan())
    failed_transport = FakeTransport([], fail_send=True)

    with pytest.raises(ConversationError, match="indeterminate"):
        execute_conversation(run_dir, failed_transport)

    assert len(failed_transport.sends) == 1
    ledger = _ledger(run_dir)
    assert ledger["request_count"] == 1
    assert ledger["indeterminate_tokens"] == 18
    assert ledger["blocked"] is True
    assert read_conversation_status(run_dir)["state"] == "indeterminate"

    second_transport = FakeTransport([_response(1, "Should never be sent")])
    with pytest.raises(ConversationError, match="no retry"):
        execute_conversation(run_dir, second_transport)
    assert second_transport.sends == []
    assert _ledger(run_dir)["request_count"] == 1


def test_completed_response_without_output_text_does_not_continue(tmp_path: Path) -> None:
    run_dir = tmp_path / "conversation"
    prepare_conversation(run_dir, _plan())
    transport = FakeTransport([_response(1, None)])

    summary = execute_conversation(run_dir, transport)

    assert summary["state"] == "truncated"
    assert summary["reason"] == "nontext_response"
    assert summary["turns_completed"] == 1
    assert len(transport.sends) == 1
    assert _ledger(run_dir)["request_count"] == 1
    assert _ledger(run_dir)["settled_tokens"] == 12
    _assert_persisted_turn(run_dir, 1)
    assert read_conversation_status(run_dir)["state"] == "truncated"


def test_status_detects_response_modified_after_completed_run(tmp_path: Path) -> None:
    run_dir = tmp_path / "conversation"
    prepare_conversation(run_dir, _plan())
    transport = FakeTransport([_response(1, "Start with a baseline."),
                               _response(2, "Then compare the intervention.")])
    assert execute_conversation(run_dir, transport)["state"] == "completed"

    response_path = run_dir / "responses" / "0001.json"
    response = json.loads(response_path.read_text(encoding="utf-8"))
    response["output"][0]["content"][0]["text"] = "Altered after completion."
    response_path.write_text(
        json.dumps(response, ensure_ascii=True, sort_keys=True,
                   separators=(",", ":")) + "\n", encoding="utf-8",
    )
    assert stat.S_IMODE(response_path.stat().st_mode) == 0o600

    with pytest.raises(ConversationError, match="artifacts disagree"):
        read_conversation_status(run_dir)


def test_active_deadline_survives_transport_swallowing_alarm(tmp_path: Path) -> None:
    run_dir = tmp_path / "conversation"
    prepare_conversation(run_dir, _plan(), active_limit_seconds=1)

    class SlowTransport(FakeTransport):
        caught_deadline = False

        def send(self, payload: dict[str, Any]) -> dict[str, Any]:
            self.sends.append(copy.deepcopy(payload))
            try:
                time.sleep(2)
            except ActiveDeadlineExceeded:
                self.caught_deadline = True
            return _response(1, "A response after the deadline")

    transport = SlowTransport([])
    with pytest.raises(ConversationError, match="indeterminate") as caught:
        execute_conversation(run_dir, transport)

    # The fake swallowed SIGALRM, but the post-send deadline check still fails.
    assert transport.caught_deadline is True
    assert isinstance(caught.value.__cause__.__cause__, ActiveDeadlineExceeded)
    assert len(transport.counts) == len(transport.sends) == 1
    assert read_conversation_status(run_dir)["state"] == "indeterminate"
    assert _ledger(run_dir)["indeterminate_tokens"] == 18
    assert not (run_dir / "requests" / "0002.json").exists()
    assert not (run_dir / "responses" / "0001.json").exists()

    retry_transport = FakeTransport([_response(1, "Should never be sent")])
    with pytest.raises(ConversationError, match="no retry"):
        execute_conversation(run_dir, retry_transport)
    assert retry_transport.counts == retry_transport.sends == []


def test_prepare_and_status_cli_are_offline_without_paid_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    plan_file = tmp_path / "plan.json"
    plan_file.write_text(json.dumps(_plan()), encoding="utf-8")
    run_dir = tmp_path / "conversation"

    assert main(["prepare", str(plan_file), str(run_dir)]) == 0
    prepared = json.loads(capsys.readouterr().out)
    assert prepared["state"] == "prepared"
    assert prepared["budget"]["request_count"] == 0

    assert main(["status", str(run_dir)]) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["state"] == "prepared"
    assert status["budget"]["request_count"] == 0
    assert _ledger(run_dir)["request_count"] == 0


def test_cli_prepares_from_ordinary_price_json_and_execute_needs_paid_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    plan_file = tmp_path / "plan.json"
    profile_file = tmp_path / "prices.json"
    plan_file.write_text(json.dumps(_priced_plan(), indent=2), encoding="utf-8")
    profile_file.write_text(json.dumps(PRICE_PROFILE, indent=2), encoding="utf-8")
    run_dir = tmp_path / "conversation"
    monkeypatch.setenv("OPENAI_API_KEY", "offline-only-key")

    def fail_if_constructed(_api_key: str) -> None:
        pytest.fail("provider transport must not be constructed without paid flag")

    monkeypatch.setattr("run_managed_conversation.OpenAIResponsesHTTP", fail_if_constructed)
    assert main([
        "prepare", str(plan_file), str(run_dir), "--cost-limit-micro-usd", "46",
        "--price-profile", str(profile_file),
    ]) == 0
    prepared = json.loads(capsys.readouterr().out)
    assert prepared["state"] == "prepared"
    assert prepared["budget"]["cost_limit_micro_usd"] == 46
    assert prepared["budget"]["price_profile"] == PRICE_PROFILE
    assert prepared["budget"]["request_count"] == 0

    assert main(["execute", str(run_dir)]) == 2
    assert "--allow-paid-requests" in capsys.readouterr().err
    assert read_conversation_status(run_dir)["state"] == "prepared"
    assert _ledger(run_dir)["request_count"] == 0
    assert list((run_dir / "requests").iterdir()) == []


@pytest.mark.parametrize("priced", [False, True])
def test_child_death_during_send_leaves_reserved_run_unretryable(
    tmp_path: Path, priced: bool,
) -> None:
    run_dir = tmp_path / "conversation"
    if priced:
        prepare_conversation(
            run_dir, _priced_plan(), cost_limit_micro_usd=26,
            price_profile=PRICE_PROFILE,
        )
    else:
        prepare_conversation(run_dir, _plan())
    scripts_dir = Path(__file__).resolve().parents[1] / "scripts"
    child_code = """\
import os
import sys
from pathlib import Path

sys.path.insert(0, sys.argv[2])
from run_managed_conversation import execute_conversation

class ExitDuringSend:
    def count_input(self, payload):
        return 8

    def send(self, payload):
        os._exit(73)

execute_conversation(Path(sys.argv[1]), ExitDuringSend())
"""
    child = subprocess.run(
        [sys.executable, "-c", child_code, str(run_dir), str(scripts_dir)],
        capture_output=True, text=True, timeout=10, check=False,
    )
    assert child.returncode == 73, child.stderr

    status = read_conversation_status(run_dir)
    assert status["state"] == "indeterminate"
    assert status["stored_state"] == "started"
    assert status["turns_completed"] == 0
    budget = status["budget"]
    assert budget["request_count"] == 1
    assert budget["reserved_tokens"] == 18
    assert budget["indeterminate_tokens"] == 0
    assert budget["reserved_cost_micro_usd"] == (26 if priced else None)
    assert budget["indeterminate_cost_micro_usd"] == (0 if priced else None)
    assert budget["blocked"] is True
    assert budget["requests"]["turn-0001"]["state"] == "reserved"
    assert (run_dir / "requests" / "0001.json").exists()
    assert not (run_dir / "responses" / "0001.json").exists()
    assert not (run_dir / "receipts" / "0001.json").exists()

    retry_transport = FakeTransport([_response(1, "Should never be sent")])
    with pytest.raises(ConversationError, match="no retry"):
        execute_conversation(run_dir, retry_transport)
    assert retry_transport.counts == retry_transport.sends == []
