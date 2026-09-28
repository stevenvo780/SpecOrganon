"""Offline integration of Responses calls with a real sealed staged tool."""

from __future__ import annotations

import hashlib
import json
import stat
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import local_replay_sandbox as sandbox  # noqa: E402
import local_run_admission as admission  # noqa: E402
import run_managed_tool_conversation as bridge  # noqa: E402
import test_staged_tool_session as staged_fixture  # noqa: E402


TOOL = """
import json
import sys
from pathlib import Path
args = json.loads(sys.argv[4])
assert args == {'note': 'test'}
work = Path(sys.argv[3])
(work / 'report.md').write_text('sealed output\\n')
print('real sealed stdout')
"""


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _prepare(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *,
    max_model_requests: int = 3, max_tool_calls: int = 1,
    cost_limit: int = 1000, first_body: str = TOOL,
) -> tuple[Path, dict, dict]:
    monkeypatch.setenv(admission.ROOT_ENV, str(tmp_path / "admissions"))
    schedule, schedule_path, run_id, stage, tool, _, _ = staged_fixture._stage(
        tmp_path, first_body=first_body, cap=1,
    )
    run = next(item for item in schedule["runs"] if item["run_id"] == run_id)
    plan = {
        "schema": 1, "run_id": run_id, "model": run["model_id"],
        "service_tier": "default",
        "turns": [
            {"user": "Use the sealed function once.", "max_output_tokens": 20},
            {"user": "Summarize the result.", "max_output_tokens": 20},
        ],
        "functions": [{
            "type": "function", "name": "sealed_first",
            "description": "Execute the sealed local tool.",
            "parameters": {
                "type": "object", "properties": {"note": {"type": "string"}},
                "required": ["note"], "additionalProperties": False,
            },
            "strict": True, "tool_id": "first", "executable": str(tool),
        }],
        "max_model_requests": max_model_requests,
        "max_tool_calls": max_tool_calls,
        "tool_wall_seconds": 4,
    }
    if run["effort_provider_value"] is not None:
        plan["reasoning"] = {"effort": run["effort_provider_value"]}
    profile = {
        "model": run["model_id"],
        "input_rate_micro_usd_per_million": 1_000_000,
        "cached_input_rate_micro_usd_per_million": 1_000_000,
        "cache_write_rate_micro_usd_per_million": 1_000_000,
        "output_rate_micro_usd_per_million": 1_000_000,
    }
    run_dir = tmp_path / "managed-tool"
    prepared = bridge.prepare_tool_conversation(
        run_dir, schedule_path, stage, plan,
        limit_tokens=1000, active_limit_seconds=30,
        cost_limit_micro_usd=cost_limit, price_profile=profile,
    )
    assert prepared["state"] == "prepared"
    assert stat.S_IMODE(run_dir.stat().st_mode) == 0o700
    return run_dir, plan, schedule


class FakeTransport:
    def __init__(self, model: str, outputs: list[list[dict]]) -> None:
        self.model = model
        self.outputs = outputs
        self.counts: list[dict] = []
        self.sends: list[dict] = []

    def count_input(self, payload: dict) -> int:
        self.counts.append(payload)
        assert payload["tools"][0]["name"] == "sealed_first"
        assert payload["parallel_tool_calls"] is False
        return 10

    def send(self, payload: dict) -> dict:
        self.sends.append(payload)
        return {
            "id": f"resp_fake_{len(self.sends)}", "model": self.model,
            "service_tier": "default", "status": "completed",
            "usage": {"input_tokens": 10, "output_tokens": 5,
                      "total_tokens": 15},
            "output": self.outputs[len(self.sends) - 1],
        }


CALL = {"type": "function_call", "name": "sealed_first",
        "call_id": "call_1", "arguments": '{"note":"test"}', "status": "completed"}
REASONING = {"type": "reasoning", "encrypted_content": "opaque-local-reasoning"}


def _message(text: str) -> dict:
    return {"type": "message", "role": "assistant",
            "content": [{"type": "output_text", "text": text}]}


@pytest.fixture
def available_sandbox() -> None:
    probe = sandbox.probe_sandbox()
    if not probe.available:
        pytest.skip(probe.reason or "sandbox unavailable")


def test_two_user_turns_replay_complete_output_and_sealed_tool(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, available_sandbox: None,
) -> None:
    run_dir, plan, _ = _prepare(tmp_path, monkeypatch)
    transport = FakeTransport(plan["model"], [[REASONING, CALL], [_message("Tool done.")],
                                               [_message("Summary.")]])
    result = bridge.execute_tool_conversation(run_dir, transport)

    assert result["state"] == "completed"
    assert result["turns_completed"] == 2
    assert result["model_requests_completed"] == 3
    assert result["tool_calls_completed"] == 1
    assert result["budget"]["request_count"] == 3
    assert result["budget"]["settled_cost_micro_usd"] == 45
    assert len(transport.counts) == len(transport.sends) == 3
    history = transport.sends[1]["input"]
    assert history[1] == REASONING
    assert history[2] == CALL
    assert history[3]["type"] == "function_call_output"
    assert history[3]["call_id"] == CALL["call_id"]
    output = json.loads(history[3]["output"])
    assert output["run_id"] == plan["run_id"]
    assert output["call_id"] == CALL["call_id"]
    assert output["stdout"] == "real sealed stdout\n"
    assert output["terminal"]["status"] == "success"
    assert transport.sends[2]["input"][-2] == _message("Tool done.")
    assert transport.sends[2]["input"][-1]["role"] == "user"
    receipt = json.loads((run_dir / "tool_receipts" / "0001.json").read_text())
    terminal_path = run_dir / "tool_session" / "calls" / "000001" / "terminal.json"
    assert receipt["terminal_sha256"] == _sha(terminal_path.read_bytes())
    assert receipt["arguments_sha256"] == _sha(b'{"note":"test"}')
    assert bridge.read_tool_conversation_status(run_dir)["completed_artifacts_verified"]
    with pytest.raises(bridge.ToolConversationError, match="no retry"):
        bridge.execute_tool_conversation(run_dir, transport)


def test_model_cap_stops_before_next_send(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, available_sandbox: None,
) -> None:
    run_dir, plan, _ = _prepare(tmp_path, monkeypatch, max_model_requests=2)
    transport = FakeTransport(plan["model"], [[CALL], [_message("Tool done.")]])
    result = bridge.execute_tool_conversation(run_dir, transport)
    assert result["state"] == "truncated"
    assert result["reason"] == "model_request_cap"
    assert result["model_requests_completed"] == 2
    assert result["turns_completed"] == 1
    assert len(transport.sends) == 2
    assert not (run_dir / "requests" / "0003.json").exists()


def test_tool_cap_stops_before_launch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_dir, plan, _ = _prepare(tmp_path, monkeypatch, max_tool_calls=0)
    transport = FakeTransport(plan["model"], [[CALL]])
    result = bridge.execute_tool_conversation(run_dir, transport)
    assert result["state"] == "truncated"
    assert result["reason"] == "tool_call_cap"
    assert result["tool_calls_completed"] == 0
    assert list((run_dir / "tool_reservations").iterdir()) == []
    assert list((run_dir / "tool_session" / "calls").iterdir()) == []


def test_unsupported_response_item_blocks_tool_launch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_dir, plan, _ = _prepare(tmp_path, monkeypatch)
    transport = FakeTransport(plan["model"], [[{"type": "computer_call"}, CALL]])
    result = bridge.execute_tool_conversation(run_dir, transport)
    assert result["state"] == "truncated"
    assert result["reason"] == "unsupported_response"
    assert list((run_dir / "tool_reservations").iterdir()) == []
    assert list((run_dir / "tool_session" / "calls").iterdir()) == []


def test_provider_crash_after_reservation_blocks_continuation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_dir, plan, _ = _prepare(tmp_path, monkeypatch)

    class CrashingTransport(FakeTransport):
        def send(self, payload: dict) -> dict:
            self.sends.append(payload)
            raise RuntimeError("simulated lost response")

    transport = CrashingTransport(plan["model"], [])
    with pytest.raises(bridge.ToolConversationError, match="indeterminate"):
        bridge.execute_tool_conversation(run_dir, transport)
    status = bridge.read_tool_conversation_status(run_dir)
    assert status["state"] == "indeterminate"
    assert status["budget"]["blocked"] is True
    assert status["budget"]["requests"]["model-0001"]["state"] == "indeterminate"
    with pytest.raises(bridge.ToolConversationError, match="no retry"):
        bridge.execute_tool_conversation(run_dir, transport)
    assert len(transport.sends) == 1


def test_killed_process_started_marker_reports_held_model_reservation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_dir, plan, _ = _prepare(tmp_path, monkeypatch)
    state_path = run_dir / "run.json"
    state = json.loads(state_path.read_text())
    state["state"] = "started"
    state_path.write_bytes(bridge._canonical(state))
    request = bridge._request(
        plan, [{"role": "user", "content": plan["turns"][0]["user"]}], 1,
    )
    request_sha = _sha(bridge._json_bytes(request))
    bridge._new_private_file(run_dir / "requests" / "0001.json", bridge._canonical({
        "run_id": plan["run_id"], "request_index": 1, "turn": 1,
        "request_sha256": request_sha, "request": request,
    }))
    ledger = bridge.TokenLedger(run_dir / "ledger")
    ledger.reserve("model-0001", "agent", request_sha, 10, 20, model=plan["model"])
    status = bridge.read_tool_conversation_status(run_dir)
    assert status["state"] == "indeterminate"
    assert status["budget"]["reserved_tokens"] == 30
    assert status["completed_artifacts_verified"] is False
    assert status["pending_artifacts"]["requests"] == ["0001.json"]
    with pytest.raises(bridge.ToolConversationError, match="no retry"):
        bridge.execute_tool_conversation(run_dir, FakeTransport(plan["model"], []))


def test_tool_crash_after_bridge_reservation_blocks_continuation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_dir, plan, _ = _prepare(tmp_path, monkeypatch)
    transport = FakeTransport(plan["model"], [[CALL]])

    def crash_after_reservation(*_args: object, **_kwargs: object) -> dict:
        raise RuntimeError("simulated tool launch crash")

    monkeypatch.setattr(bridge, "call_tool", crash_after_reservation)
    with pytest.raises(bridge.ToolConversationError, match="indeterminate"):
        bridge.execute_tool_conversation(run_dir, transport)
    assert (run_dir / "tool_reservations" / "0001.json").exists()
    assert bridge.read_tool_conversation_status(run_dir)["state"] == "indeterminate"
    with pytest.raises(bridge.ToolConversationError, match="no retry"):
        bridge.execute_tool_conversation(run_dir, transport)
    assert len(transport.sends) == 1


def test_cost_cap_blocks_before_send(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_dir, plan, _ = _prepare(tmp_path, monkeypatch, cost_limit=29)
    transport = FakeTransport(plan["model"], [[CALL]])
    result = bridge.execute_tool_conversation(run_dir, transport)
    assert result["state"] == "truncated"
    assert result["reason"] == "CostBudgetExhausted"
    assert transport.counts
    assert transport.sends == []
    assert result["budget"]["request_count"] == 0


def test_cost_cap_stops_before_next_send_after_tool(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, available_sandbox: None,
) -> None:
    run_dir, plan, _ = _prepare(tmp_path, monkeypatch, cost_limit=44)
    transport = FakeTransport(plan["model"], [[CALL]])
    result = bridge.execute_tool_conversation(run_dir, transport)
    assert result["state"] == "truncated"
    assert result["reason"] == "CostBudgetExhausted"
    assert result["tool_calls_completed"] == 1
    assert len(transport.sends) == 1
    assert not (run_dir / "responses" / "0002.json").exists()


@pytest.mark.parametrize("body", [
    TOOL.replace("print('real sealed stdout')", "sys.stdout.buffer.write(b'\\xff')"),
    TOOL.replace("print('real sealed stdout')", "print('x' * 70000)"),
])
def test_unreadable_or_unbounded_tool_stream_truncates_without_next_send(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, available_sandbox: None,
    body: str,
) -> None:
    run_dir, plan, _ = _prepare(tmp_path, monkeypatch, first_body=body)
    transport = FakeTransport(plan["model"], [[CALL]])
    result = bridge.execute_tool_conversation(run_dir, transport)
    assert result["state"] == "truncated"
    assert result["tool_calls_completed"] == 1
    assert len(transport.sends) == 1
    assert not (run_dir / "responses" / "0002.json").exists()
    receipt = json.loads((run_dir / "tool_receipts" / "0001.json").read_text())
    assert receipt["output"] is None
    assert "tool stream" in receipt["output_error"]


def test_default_scheduled_effort_rejects_forced_high_reasoning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, plan, schedule = _prepare(tmp_path, monkeypatch)
    default = next(item for item in schedule["runs"]
                   if item["effort_provider_value"] is None)
    plan.update(run_id=default["run_id"], model=default["model_id"],
                reasoning={"effort": "high"})
    with pytest.raises(bridge.ToolConversationError, match="scheduled effort"):
        bridge._validate_plan(plan, schedule)


def test_status_rejects_mutated_schedule_or_tool_terminal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, available_sandbox: None,
) -> None:
    run_dir, plan, _ = _prepare(tmp_path, monkeypatch)
    transport = FakeTransport(plan["model"], [[CALL], [_message("Done.")],
                                               [_message("Summary.")]])
    bridge.execute_tool_conversation(run_dir, transport)
    terminal = run_dir / "tool_session" / "calls" / "000001" / "terminal.json"
    original = terminal.read_bytes()
    terminal.write_bytes(original + b" ")
    with pytest.raises(ValueError):
        bridge.read_tool_conversation_status(run_dir)


def test_status_rejects_forged_completed_state_without_provider_turns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_dir, _, _ = _prepare(tmp_path, monkeypatch)
    state_path = run_dir / "run.json"
    state = json.loads(state_path.read_text())
    state.update(state="completed", turns_completed=2)
    state_path.write_bytes(bridge._canonical(state))
    with pytest.raises(bridge.ToolConversationError, match="two finished user turns"):
        bridge.read_tool_conversation_status(run_dir)


def test_replay_rejects_second_turn_that_drops_prior_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, available_sandbox: None,
) -> None:
    run_dir, plan, _ = _prepare(tmp_path, monkeypatch)
    transport = FakeTransport(plan["model"], [[CALL], [_message("Done.")],
                                               [_message("Summary.")]])
    original_request = bridge._request

    def incomplete_request(plan_: dict, history: list[dict], turn: int) -> dict:
        if turn == 2:
            return original_request(plan_, [history[-1]], turn)
        return original_request(plan_, history, turn)

    monkeypatch.setattr(bridge, "_request", incomplete_request)
    with pytest.raises(bridge.ToolConversationError, match="indeterminate"):
        bridge.execute_tool_conversation(run_dir, transport)
    assert len(transport.sends) == 3
    with pytest.raises(bridge.ToolConversationError, match="prior complete output"):
        bridge.read_tool_conversation_status(run_dir)


def test_cli_execute_requires_flag_and_api_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_dir, _, _ = _prepare(tmp_path, monkeypatch)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert bridge.main(["execute", str(run_dir)]) == 2
    assert bridge.main(["execute", str(run_dir), "--allow-paid-requests"]) == 2
    assert bridge.read_tool_conversation_status(run_dir)["state"] == "prepared"
