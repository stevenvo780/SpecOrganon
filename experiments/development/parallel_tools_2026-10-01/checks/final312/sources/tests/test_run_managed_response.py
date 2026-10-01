"""Offline tests for the concrete count/reserve/send Responses path."""

from __future__ import annotations

import hashlib
import http.server
import json
import stat
import sys
import threading
from pathlib import Path

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from managed_token_ledger import BudgetError, TokenLedger  # noqa: E402
from run_managed_response import (  # noqa: E402
    DispatchError,
    OpenAIResponsesHTTP,
    _parse_function_arguments,
    dispatch_response,
    main,
)


REQUEST = {"model": "gpt-6-luna", "input": "A short public question.",
           "reasoning": {"effort": "low"}, "max_output_tokens": 10}
PRICE_PROFILE = {
    "model": "gpt-6-luna",
    "input_rate_micro_usd_per_million": 1_000_000,
    "cached_input_rate_micro_usd_per_million": 1_000_000,
    "cache_write_rate_micro_usd_per_million": 2_000_000,
    "output_rate_micro_usd_per_million": 1_000_000,
}
PRICED_REQUEST = {**REQUEST, "service_tier": "default"}
FUNCTION_TOOL = {
    "type": "function", "name": "measure_sample",
    "description": "Measure one sample with declared values.",
    "parameters": {
        "type": "object",
        "properties": {
            "label": {"type": "string", "description": "Sample name."},
            "batch": {"type": "integer"},
            "ratio": {"type": "number"},
            "approved": {"type": "boolean"},
        },
        "required": ["label", "batch", "ratio", "approved"],
        "additionalProperties": False,
    },
    "strict": True,
}
FUNCTION_ARGUMENTS = '{"label":"A","batch":2,"ratio":0.5,"approved":false}'
TOOL_REQUEST = {**REQUEST, "tools": [FUNCTION_TOOL], "parallel_tool_calls": False}


class FakeTransport:
    def __init__(self, input_tokens: int = 8, output_tokens: int = 4) -> None:
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.counts: list[dict] = []
        self.sends: list[dict] = []
        self.response: dict | None = None
        self.send_error: Exception | None = None

    def count_input(self, payload: dict) -> int:
        self.counts.append(payload)
        return self.input_tokens

    def send(self, payload: dict) -> dict:
        self.sends.append(payload)
        if self.send_error is not None:
            raise self.send_error
        response = self.response or {
            "id": "resp_local_1", "model": "gpt-6-luna", "status": "completed",
            "usage": {"input_tokens": self.input_tokens,
                      "output_tokens": self.output_tokens,
                      "total_tokens": self.input_tokens + self.output_tokens},
            "output": [],
        }
        if self.response is None and payload.get("service_tier") == "default":
            response["service_tier"] = "default"
        return response


def _ledger(tmp_path: Path, limit: int = 30) -> TokenLedger:
    return TokenLedger.create(tmp_path / "ledger", limit, 8)


def _priced_ledger(tmp_path: Path, cost_limit: int = 100) -> TokenLedger:
    return TokenLedger.create(
        tmp_path / "ledger", 100, 8, cost_limit_micro_usd=cost_limit,
        price_profile=PRICE_PROFILE,
    )


def _output_dir(tmp_path: Path) -> Path:
    path = tmp_path / "responses"
    path.mkdir(mode=0o700)
    return path


def test_count_reserve_send_and_persist_response(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path)
    output = _output_dir(tmp_path) / "one.json"
    transport = FakeTransport()
    receipt = dispatch_response(ledger, request_id="one", role="leader",
                                request=REQUEST, response_path=output,
                                transport=transport)
    assert transport.counts == [{"model": "gpt-6-luna", "input": REQUEST["input"],
                                 "reasoning": REQUEST["reasoning"]}]
    assert transport.sends == [{**REQUEST, "store": False, "stream": False}]
    assert receipt["usage"]["total_tokens"] == 12
    assert receipt["response_sha256"] == hashlib.sha256(output.read_bytes()).hexdigest()
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    assert receipt["criterion_4"] == "not_assessed"


def test_function_tools_are_counted_and_sent_with_complete_replay(
    tmp_path: Path,
) -> None:
    input_items = [
        {"role": "user", "content": "Measure sample A."},
        {"type": "reasoning", "encrypted_content": "opaque-replay"},
        {"type": "function_call", "id": "fc_1", "status": "completed",
         "name": FUNCTION_TOOL["name"], "call_id": "call_1",
         "arguments": FUNCTION_ARGUMENTS},
        {"type": "function_call_output", "call_id": "call_1", "output": "0.5"},
    ]
    request = {**TOOL_REQUEST, "input": input_items}
    transport = FakeTransport()
    output = _output_dir(tmp_path) / "one.json"

    receipt = dispatch_response(
        _ledger(tmp_path), request_id="one", role="leader", request=request,
        response_path=output, transport=transport,
    )

    assert transport.counts == [{
        "model": REQUEST["model"], "input": input_items,
        "reasoning": REQUEST["reasoning"], "tools": [FUNCTION_TOOL],
        "parallel_tool_calls": False,
    }]
    assert transport.sends == [{**request, "store": False, "stream": False}]
    assert receipt["usage"]["total_tokens"] == 12


@pytest.mark.parametrize("raw,expected", [
    (FUNCTION_ARGUMENTS, {"label": "A", "batch": 2, "ratio": 0.5,
                          "approved": False}),
    ('{"label":"A","batch":2,"ratio":3,"approved":true}',
     {"label": "A", "batch": 2, "ratio": 3, "approved": True}),
    ('{"label":"A","batch":2,"ratio":0.1,"approved":true}',
     {"label": "A", "batch": 2, "ratio": 0.1, "approved": True}),
])
def test_function_argument_parser_accepts_exact_primitive_object(
    raw: str, expected: dict,
) -> None:
    assert _parse_function_arguments(FUNCTION_TOOL, raw) == expected


@pytest.mark.parametrize("raw", [
    '{"label":"A","batch":2,"ratio":0.5}',
    '{"label":"A","batch":2,"ratio":0.5,"approved":false,"extra":1}',
    '{"label":"A","label":"B","batch":2,"ratio":0.5,"approved":false}',
    '{"label":"A","batch":true,"ratio":0.5,"approved":false}',
    '{"label":"A","batch":2,"ratio":true,"approved":false}',
    '{"label":"A","batch":2,"ratio":0.5,"approved":0}',
    '{"label":"A","batch":2.0,"ratio":0.5,"approved":false}',
    '{"label":"A","batch":2,"ratio":"0.5","approved":false}',
    '{"label":"A","batch":2,"ratio":NaN,"approved":false}',
    '{"label":"A","batch":2,"ratio":Infinity,"approved":false}',
    '{"label":"A","batch":2,"ratio":1e999,"approved":false}',
    '{"label":"A","batch":2,"ratio":1e-9999,"approved":false}',
    '{"label":"A","batch":2,"ratio":0.10000000000000001,"approved":false}',
    '["A",2,0.5,false]',
    'not JSON',
])
def test_function_argument_parser_rejects_invalid_json_or_schema(raw: str) -> None:
    with pytest.raises(DispatchError):
        _parse_function_arguments(FUNCTION_TOOL, raw)


@pytest.mark.parametrize("decimal", ["1e-9999", "0.10000000000000001"])
def test_lossy_function_decimal_rejects_before_count(
    tmp_path: Path, decimal: str,
) -> None:
    arguments = ('{"label":"A","batch":2,"ratio":' + decimal
                 + ',"approved":false}')
    input_items = [
        {"type": "function_call", "name": FUNCTION_TOOL["name"],
         "call_id": "call_1", "arguments": arguments},
        {"type": "function_call_output", "call_id": "call_1", "output": "0"},
    ]
    transport = FakeTransport()
    ledger = _ledger(tmp_path)
    with pytest.raises(DispatchError, match="loses precision"):
        dispatch_response(
            ledger, request_id="one", role="leader",
            request={**TOOL_REQUEST, "input": input_items},
            response_path=_output_dir(tmp_path) / "one.json", transport=transport,
        )
    assert transport.counts == transport.sends == []
    assert ledger.status()["request_count"] == 0


@pytest.mark.parametrize("change", [
    {"tools": []},
    {"tools": [FUNCTION_TOOL] * 9},
    {"parallel_tool_calls": True},
    {"parallel_tool_calls": None},
    {"tools": [{**FUNCTION_TOOL, "type": "web_search"}]},
    {"tools": [{**FUNCTION_TOOL, "type": "custom"}]},
    {"tools": [{**FUNCTION_TOOL, "strict": False}]},
    {"tools": [{**FUNCTION_TOOL, "name": "bad name"}]},
    {"tools": [{**FUNCTION_TOOL, "description": " "}]},
    {"tools": [{**FUNCTION_TOOL, "execution": "client"}]},
    {"tools": [FUNCTION_TOOL, FUNCTION_TOOL]},
    {"tools": [{**FUNCTION_TOOL, "parameters": {
        **FUNCTION_TOOL["parameters"], "additionalProperties": True,
    }}]},
    {"tools": [{**FUNCTION_TOOL, "parameters": {
        **FUNCTION_TOOL["parameters"], "required": ["label"],
    }}]},
    {"tools": [{**FUNCTION_TOOL, "parameters": {
        **FUNCTION_TOOL["parameters"],
        "required": ["label", "batch", "ratio", "ratio"],
    }}]},
    {"tools": [{**FUNCTION_TOOL, "parameters": {
        **FUNCTION_TOOL["parameters"],
        "properties": {"label": {"type": "array"}},
        "required": ["label"],
    }}]},
    {"tools": [{**FUNCTION_TOOL, "parameters": {
        **FUNCTION_TOOL["parameters"],
        "properties": {"label": {"type": "string", "enum": ["A"]}},
        "required": ["label"],
    }}]},
])
def test_invalid_function_tool_contract_rejects_before_count(
    tmp_path: Path, change: dict,
) -> None:
    transport = FakeTransport()
    with pytest.raises(DispatchError):
        dispatch_response(
            _ledger(tmp_path), request_id="one", role="leader",
            request={**TOOL_REQUEST, **change},
            response_path=_output_dir(tmp_path) / "one.json", transport=transport,
        )
    assert transport.counts == transport.sends == []


def test_parallel_setting_without_tools_rejects_before_count(tmp_path: Path) -> None:
    transport = FakeTransport()
    with pytest.raises(DispatchError, match="requires tools"):
        dispatch_response(
            _ledger(tmp_path), request_id="one", role="leader",
            request={**REQUEST, "parallel_tool_calls": False},
            response_path=_output_dir(tmp_path) / "one.json", transport=transport,
        )
    assert transport.counts == transport.sends == []


def test_tools_without_explicit_parallel_false_reject_before_count(
    tmp_path: Path,
) -> None:
    transport = FakeTransport()
    with pytest.raises(DispatchError, match="parallel_tool_calls false"):
        dispatch_response(
            _ledger(tmp_path), request_id="one", role="leader",
            request={**REQUEST, "tools": [FUNCTION_TOOL]},
            response_path=_output_dir(tmp_path) / "one.json", transport=transport,
        )
    assert transport.counts == transport.sends == []


@pytest.mark.parametrize("input_items", [
    [{"type": "function_call_output", "call_id": "call_1", "output": "0.5"}],
    [{"type": "function_call", "name": "measure_sample", "call_id": "call_1",
      "arguments": FUNCTION_ARGUMENTS}],
    [{"type": "function_call", "name": "unknown", "call_id": "call_1",
      "arguments": FUNCTION_ARGUMENTS},
     {"type": "function_call_output", "call_id": "call_1", "output": "0.5"}],
    [{"type": "function_call", "name": "measure_sample", "call_id": "call_1",
      "arguments": FUNCTION_ARGUMENTS, "program": "print('unsafe')"},
     {"type": "function_call_output", "call_id": "call_1", "output": "0.5"}],
    [{"type": "function_call", "name": "measure_sample", "call_id": "call_1",
      "arguments": FUNCTION_ARGUMENTS},
     {"type": "function_call_output", "call_id": "wrong", "output": "0.5"}],
    [{"type": "function_call", "name": "measure_sample", "call_id": "call_1",
      "arguments": FUNCTION_ARGUMENTS},
     {"type": "function_call_output", "call_id": "call_1", "output": {"result": 1}}],
    [{"type": "computer_call", "call_id": "call_1", "action": "click"}],
])
def test_unsupported_function_replay_rejects_before_count(
    tmp_path: Path, input_items: list[dict],
) -> None:
    transport = FakeTransport()
    with pytest.raises(DispatchError):
        dispatch_response(
            _ledger(tmp_path), request_id="one", role="leader",
            request={**TOOL_REQUEST, "input": input_items},
            response_path=_output_dir(tmp_path) / "one.json", transport=transport,
        )
    assert transport.counts == transport.sends == []


def test_provider_usage_details_are_preserved_without_double_counting(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    output = _output_dir(tmp_path) / "one.json"
    transport = FakeTransport()
    transport.response = {
        "id": "resp_local_1", "model": "gpt-6-luna", "status": "completed",
        "usage": {"input_tokens": 8, "output_tokens": 4, "total_tokens": 12,
                  "input_tokens_details": {"cached_tokens": 3},
                  "output_tokens_details": {"reasoning_tokens": 2}},
        "output": [],
    }
    receipt = dispatch_response(ledger, request_id="one", role="leader",
                                request=REQUEST, response_path=output,
                                transport=transport)
    assert receipt["budget"]["held_tokens"] == 12
    assert json.loads(output.read_text())["usage"]["output_tokens_details"] == {
        "reasoning_tokens": 2}


def test_priced_dispatch_reserves_before_send_and_settles_schema_two(
    tmp_path: Path,
) -> None:
    ledger = _priced_ledger(tmp_path, cost_limit=26)
    output = _output_dir(tmp_path) / "one.json"

    class InspectingTransport(FakeTransport):
        def send(self, payload: dict) -> dict:
            before_send = ledger.status()
            assert before_send["request_count"] == 1
            assert before_send["reserved_tokens"] == 18
            assert before_send["reserved_cost_micro_usd"] == 26
            assert before_send["requests"]["one"]["state"] == "reserved"
            return super().send(payload)

    transport = InspectingTransport()
    receipt = dispatch_response(
        ledger, request_id="one", role="leader", request=PRICED_REQUEST,
        response_path=output, transport=transport,
    )

    assert transport.counts == [{
        "model": REQUEST["model"], "input": REQUEST["input"],
        "reasoning": REQUEST["reasoning"],
    }]
    assert transport.sends == [{**PRICED_REQUEST, "store": False, "stream": False}]
    assert json.loads((ledger.directory / "ledger.json").read_text())["schema"] == 2
    assert receipt["cost_basis"] == "declared_price_ceiling_not_invoice"
    assert receipt["budget"]["held_cost_micro_usd"] == 20
    status = ledger.status()
    assert status["settled_cost_micro_usd"] == 20
    assert status["remaining_cost_micro_usd"] == 6


def test_priced_dispatch_accounts_for_cache_write_premium(tmp_path: Path) -> None:
    ledger = _priced_ledger(tmp_path)
    output = _output_dir(tmp_path) / "one.json"
    transport = FakeTransport()
    transport.response = {
        "id": "resp_local_1", "model": REQUEST["model"], "status": "completed",
        "service_tier": "default",
        "usage": {
            "input_tokens": 8, "output_tokens": 4, "total_tokens": 12,
            "input_tokens_details": {
                "cache_write_tokens": 3, "cached_tokens": 2, "uncached_tokens": 3,
            },
            "output_tokens_details": {"reasoning_tokens": 2},
        },
        "output": [],
    }

    receipt = dispatch_response(
        ledger, request_id="one", role="leader", request=PRICED_REQUEST,
        response_path=output, transport=transport,
    )
    # 3 cache writes at 2 each, 5 other input tokens at 1, 4 output at 1.
    assert receipt["budget"]["held_cost_micro_usd"] == 15
    assert receipt["cost_basis"] == "declared_price_ceiling_not_invoice"
    assert ledger.status()["settled_cost_micro_usd"] == 15
    assert ledger.status()["requests"]["one"]["usage_details"] == {
        "input_tokens_details": transport.response["usage"]["input_tokens_details"],
        "output_tokens_details": {"reasoning_tokens": 2},
    }


def test_cost_cap_rejects_before_send(tmp_path: Path) -> None:
    ledger = _priced_ledger(tmp_path, cost_limit=25)
    output = _output_dir(tmp_path) / "one.json"
    transport = FakeTransport()

    with pytest.raises(BudgetError, match="cost budget exhausted"):
        dispatch_response(
            ledger, request_id="one", role="leader", request=PRICED_REQUEST,
            response_path=output, transport=transport,
        )
    assert len(transport.counts) == 1
    assert transport.sends == []
    assert ledger.status()["request_count"] == 0
    assert not output.exists()


@pytest.mark.parametrize("payload", [
    {**REQUEST, "model": "different-model", "service_tier": "default"},
    REQUEST,
])
def test_priced_model_or_tier_mismatch_rejects_before_count(
    tmp_path: Path, payload: dict,
) -> None:
    ledger = _priced_ledger(tmp_path)
    output = _output_dir(tmp_path) / "one.json"
    transport = FakeTransport()

    with pytest.raises(DispatchError, match="price profile|service tier"):
        dispatch_response(
            ledger, request_id="one", role="leader", request=payload,
            response_path=output, transport=transport,
        )
    assert transport.counts == transport.sends == []
    assert ledger.status()["request_count"] == 0
    assert not output.exists()


def test_reported_input_above_preflight_count_blocks_future_sends_but_cannot_undo_cost(
    tmp_path: Path,
) -> None:
    ledger = _priced_ledger(tmp_path, cost_limit=3)
    request = {**PRICED_REQUEST, "max_output_tokens": 1}
    transport = FakeTransport(input_tokens=1, output_tokens=1)
    transport.response = {
        "id": "resp_local_1", "model": "gpt-6-luna", "status": "completed",
        "service_tier": "default",
        "usage": {"input_tokens": 100, "output_tokens": 1, "total_tokens": 101},
        "output": [],
    }
    output = _output_dir(tmp_path) / "one.json"

    with pytest.raises(DispatchError, match="indeterminate; reservation held"):
        dispatch_response(ledger, request_id="one", role="leader",
                          request=request, response_path=output,
                          transport=transport)

    status = ledger.status()
    assert output.exists()
    assert len(transport.sends) == 1
    assert status["blocked"] is True
    assert status["indeterminate_cost_micro_usd"] == 3
    assert status["requests"]["one"]["state"] == "indeterminate"


def test_reported_tier_mismatch_retains_token_and_cost_reservations(
    tmp_path: Path,
) -> None:
    ledger = _priced_ledger(tmp_path)
    output = _output_dir(tmp_path) / "one.json"
    transport = FakeTransport()
    transport.response = {
        "id": "resp_local_1", "model": REQUEST["model"], "status": "completed",
        "service_tier": "flex",
        "usage": {"input_tokens": 8, "output_tokens": 4, "total_tokens": 12},
        "output": [],
    }

    with pytest.raises(DispatchError, match="reservation held"):
        dispatch_response(
            ledger, request_id="one", role="leader", request=PRICED_REQUEST,
            response_path=output, transport=transport,
        )
    assert json.loads(output.read_text())["service_tier"] == "flex"
    status = ledger.status()
    assert status["indeterminate_tokens"] == 18
    assert status["indeterminate_cost_micro_usd"] == 26
    assert status["blocked"] is True
    assert status["requests"]["one"]["state"] == "indeterminate"


def test_over_budget_rejects_before_send(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path, limit=17)
    output = _output_dir(tmp_path) / "one.json"
    transport = FakeTransport()
    with pytest.raises(BudgetError):
        dispatch_response(ledger, request_id="one", role="leader", request=REQUEST,
                          response_path=output, transport=transport)
    assert len(transport.counts) == 1
    assert transport.sends == []
    assert not output.exists()


def test_unsupported_tool_route_rejects_before_count(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path)
    output = _output_dir(tmp_path) / "one.json"
    transport = FakeTransport()
    with pytest.raises(DispatchError, match="strict custom function"):
        dispatch_response(ledger, request_id="one", role="leader",
                          request={**REQUEST, "tools": [{"type": "web_search"}],
                                   "parallel_tool_calls": False},
                          response_path=output, transport=transport)
    assert transport.counts == transport.sends == []


def test_multimodal_message_is_rejected_before_count(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path)
    output = _output_dir(tmp_path) / "one.json"
    transport = FakeTransport()
    with pytest.raises(DispatchError, match="only text"):
        dispatch_response(ledger, request_id="one", role="leader",
                          request={**REQUEST, "input": [{"role": "user", "content": [
                              {"type": "input_image", "image_url": "https://example.com/a.png"}
                          ]}]}, response_path=output, transport=transport)
    assert transport.counts == transport.sends == []


def test_count_transport_cannot_change_payload_before_reservation(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path)
    output = _output_dir(tmp_path) / "one.json"

    class MutatingTransport(FakeTransport):
        def count_input(self, payload: dict) -> int:
            payload["input"] = "different text"
            return 8

    transport = MutatingTransport()
    with pytest.raises(DispatchError, match="changed during token counting"):
        dispatch_response(ledger, request_id="one", role="leader", request=REQUEST,
                          response_path=output, transport=transport)
    assert transport.sends == []
    assert dispatch_response(ledger, request_id="one", role="leader", request=REQUEST,
                             response_path=output,
                             transport=FakeTransport())["usage"]["total_tokens"] == 12


def test_transport_failure_holds_reservation_without_retry(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path)
    output = _output_dir(tmp_path) / "one.json"
    transport = FakeTransport()
    transport.send_error = TimeoutError("timeout")
    with pytest.raises(DispatchError, match="reservation held"):
        dispatch_response(ledger, request_id="one", role="leader", request=REQUEST,
                          response_path=output, transport=transport)
    assert len(transport.sends) == 1
    with pytest.raises(BudgetError):
        dispatch_response(ledger, request_id="one", role="leader", request=REQUEST,
                          response_path=output, transport=FakeTransport())
    assert not output.exists()


def test_bad_usage_preserves_response_and_blocks_next_request(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path)
    output = _output_dir(tmp_path) / "one.json"
    transport = FakeTransport()
    transport.response = {"id": "resp_local_1", "model": "gpt-6-luna",
                          "status": "completed", "usage": None, "output": []}
    with pytest.raises(DispatchError, match="reservation held"):
        dispatch_response(ledger, request_id="one", role="leader", request=REQUEST,
                          response_path=output, transport=transport)
    assert output.exists()
    with pytest.raises(BudgetError):
        dispatch_response(ledger, request_id="two", role="reviewer", request=REQUEST,
                          response_path=output.parent / "two.json", transport=FakeTransport())


def test_reported_model_mismatch_is_indeterminate(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path)
    output = _output_dir(tmp_path) / "one.json"
    transport = FakeTransport()
    transport.response = {"id": "resp_local_1", "model": "different-model",
                          "status": "completed", "usage": {"input_tokens": 8,
                          "output_tokens": 4, "total_tokens": 12}, "output": []}
    with pytest.raises(DispatchError, match="reservation held"):
        dispatch_response(ledger, request_id="one", role="leader", request=REQUEST,
                          response_path=output, transport=transport)
    assert json.loads(output.read_text())["model"] == "different-model"
    with pytest.raises(BudgetError):
        dispatch_response(ledger, request_id="two", role="reviewer", request=REQUEST,
                          response_path=output.parent / "two.json", transport=FakeTransport())


def test_incomplete_response_is_metered_but_run_policy_remains_external(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path, limit=50)
    output_dir = _output_dir(tmp_path)
    transport = FakeTransport(input_tokens=8, output_tokens=10)
    transport.response = {"id": "resp_local_1", "model": "gpt-6-luna",
                          "status": "incomplete", "usage": {"input_tokens": 8,
                          "output_tokens": 10, "total_tokens": 18}, "output": []}
    first = dispatch_response(ledger, request_id="one", role="leader",
                              request=REQUEST, response_path=output_dir / "one.json",
                              transport=transport)
    assert first["provider_status"] == "incomplete"
    assert first["budget"]["held_tokens"] == 18
    second = dispatch_response(ledger, request_id="two", role="leader",
                               request=REQUEST, response_path=output_dir / "two.json",
                               transport=FakeTransport())
    assert second["budget"]["held_tokens"] == 12


def test_cli_init_is_offline_and_send_requires_explicit_flag(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ledger_dir = tmp_path / "ledger"
    assert main(["init", str(ledger_dir), "--limit-tokens", "30",
                 "--max-requests", "2"]) == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out)["provider_calls"] == 0
    assert main(["send", str(ledger_dir), str(tmp_path / "missing.json"),
                 str(tmp_path / "out.json"), "--request-id", "one",
                 "--role", "leader"]) == 2
    assert "--allow-paid-request" in capsys.readouterr().err


def test_cli_paid_send_rejects_legacy_ledger_before_provider_setup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    ledger = _ledger(tmp_path)
    request_file = tmp_path / "request.json"
    request_file.write_text(json.dumps(PRICED_REQUEST), encoding="utf-8")
    output = _output_dir(tmp_path) / "one.json"
    monkeypatch.setenv("OPENAI_API_KEY", "offline-only-key")

    def fail_if_constructed(_api_key: str) -> None:
        pytest.fail("provider transport must not be constructed for a legacy ledger")

    monkeypatch.setattr("run_managed_response.OpenAIResponsesHTTP", fail_if_constructed)
    assert main([
        "send", str(ledger.directory), str(request_file), str(output),
        "--request-id", "one", "--role", "leader", "--allow-paid-request",
    ]) == 2
    assert "prepared cost ceiling" in capsys.readouterr().err
    assert ledger.status()["request_count"] == 0
    assert not output.exists()


@pytest.mark.parametrize("request_payload", [REQUEST, TOOL_REQUEST])
def test_http_transport_uses_count_then_response_endpoint(
    tmp_path: Path, request_payload: dict,
) -> None:
    calls: list[tuple[str, dict]] = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            length = int(self.headers["Content-Length"])
            payload = json.loads(self.rfile.read(length))
            calls.append((self.path, payload))
            assert self.headers["Authorization"] == "Bearer test-only-key"
            if self.path.endswith("/input_tokens"):
                response = {"object": "response.input_tokens", "input_tokens": 8}
            else:
                response = {"id": "resp_local_2", "model": "gpt-6-luna",
                            "status": "completed",
                            "usage": {"input_tokens": 8, "output_tokens": 4,
                                      "total_tokens": 12}, "output": []}
            raw = json.dumps(response).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def log_message(self, *args: object) -> None:
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        transport = OpenAIResponsesHTTP(
            "test-only-key", base_url=f"http://127.0.0.1:{server.server_port}/v1")
        output = _output_dir(tmp_path) / "one.json"
        receipt = dispatch_response(_ledger(tmp_path), request_id="one", role="leader",
                                    request=request_payload, response_path=output,
                                    transport=transport)
    finally:
        server.shutdown()
        thread.join(timeout=3)
        server.server_close()
    assert receipt["usage"]["total_tokens"] == 12
    assert [path for path, _ in calls] == ["/v1/responses/input_tokens", "/v1/responses"]
    assert calls[0][1].get("tools") == request_payload.get("tools")
    assert calls[1][1].get("tools") == request_payload.get("tools")
    if "tools" in request_payload:
        assert calls[0][1]["parallel_tool_calls"] is False
        assert calls[1][1]["parallel_tool_calls"] is False


def test_http_transport_rejects_redirect_without_forwarding_key() -> None:
    leaked_headers: list[str | None] = []

    class Target(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            leaked_headers.append(self.headers.get("Authorization"))
            self.send_response(200)
            self.end_headers()

        def do_POST(self) -> None:
            self.do_GET()

        def log_message(self, *args: object) -> None:
            pass

    target = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Target)

    class Redirect(http.server.BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            self.send_response(302)
            self.send_header("Location", f"http://127.0.0.1:{target.server_port}/leak")
            self.end_headers()

        def log_message(self, *args: object) -> None:
            pass

    source = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Redirect)
    workers = [threading.Thread(target=server.serve_forever, daemon=True)
               for server in (source, target)]
    for worker in workers:
        worker.start()
    try:
        transport = OpenAIResponsesHTTP(
            "test-only-key", base_url=f"http://127.0.0.1:{source.server_port}/v1")
        with pytest.raises(DispatchError, match="provider HTTP 302"):
            transport.count_input({"model": "gpt-6-luna", "input": "public"})
    finally:
        for server in (source, target):
            server.shutdown()
            server.server_close()
        for worker in workers:
            worker.join(timeout=3)
    assert leaked_headers == []
