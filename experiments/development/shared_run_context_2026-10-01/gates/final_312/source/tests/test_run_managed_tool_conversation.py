"""Offline integration of Responses calls with a real sealed staged tool."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
import sys
import time
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
    cost_limit: int = 1000, first_body: str = TOOL, active_limit_seconds: int = 30,
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
        limit_tokens=1000, active_limit_seconds=active_limit_seconds,
        cost_limit_micro_usd=cost_limit, price_profile=profile,
    )
    assert prepared["state"] == "prepared"
    assert stat.S_IMODE(run_dir.stat().st_mode) == 0o700
    return run_dir, plan, schedule


def _tree_bytes(root: Path) -> dict[Path, bytes | None]:
    return {path.relative_to(root): path.read_bytes() if path.is_file() else None
            for path in root.rglob("*")}


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


def _second_stage_run(tmp_path: Path, first: Path, plan: dict, schedule: dict) -> Path:
    state = json.loads((first / "run.json").read_bytes())
    stage = tmp_path / "second-stage"
    staged_fixture.stage_released_run.stage_released_run(
        schedule, tmp_path / "release", stage, development_unsequenced=True,
    )
    second = tmp_path / "second-managed-tool"
    budget = bridge.TokenLedger(first / "ledger").status()
    bridge.prepare_tool_conversation(
        second, Path(state["schedule_path"]), stage, plan,
        limit_tokens=state["limit_tokens"], active_limit_seconds=state["active_limit_seconds"],
        cost_limit_micro_usd=state["cost_limit_micro_usd"], price_profile=budget["price_profile"],
    )
    return second


def test_two_stage_copies_all_text_only_one_reaches_provider(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    first, plan, schedule = _prepare(tmp_path, monkeypatch)
    second = _second_stage_run(tmp_path, first, plan, schedule)
    first_transport = FakeTransport(plan["model"], [[_message("First text")], [_message("Final text")]])
    second_transport = FakeTransport(plan["model"], [[_message("Copied text")], [_message("Copied final")]])
    second_before = _tree_bytes(second)
    result = bridge.execute_tool_conversation(first, first_transport)
    assert result["state"] == "completed"
    rejected = False
    try:
        bridge.execute_tool_conversation(second, second_transport)
    except (bridge.ToolConversationError, bridge.SessionError, admission.AdmissionError):
        rejected = True
    print(json.dumps({
        "classification": "synthetic_duplicate_all_text_admission_control",
        "real_provider_calls": 0, "first_state": result["state"], "second_rejected": rejected,
        "first_fake_counts": len(first_transport.counts), "first_fake_sends": len(first_transport.sends),
        "second_fake_counts": len(second_transport.counts), "second_fake_sends": len(second_transport.sends),
        "second_ledger_unchanged": (second / "ledger" / "ledger.json").read_bytes()
            == second_before[Path("ledger/ledger.json")],
    }, sort_keys=True))
    assert rejected, "copied scheduled attempt reached the fake provider without a tool claim"
    assert second_transport.counts == second_transport.sends == []
    assert _tree_bytes(second) == second_before
    assert not list((first / "tool_session" / "calls").iterdir())
    assert not list((second / "tool_session" / "calls").iterdir())


def _claim_arguments(run_dir: Path, schedule: dict, plan: dict) -> tuple[dict, Path]:
    state = json.loads((run_dir / "run.json").read_bytes())
    manifest = json.loads((Path(state["session_dir"]) / "session.json").read_bytes())
    root = {key: manifest[key] for key in (
        "local_run_admission_root", "local_run_admission_root_identity", "local_run_admission_scope",
    )}
    arguments = {
        "schedule_sha256": schedule["schedule_sha256"], "run_id": plan["run_id"],
        "selected_owner": admission.owner("staged", Path(state["stage_dir"]), Path(state["session_dir"])),
        "root_descriptor": root, "attempt_number": manifest["attempt_number"],
    }
    path = Path(root["local_run_admission_root"]) / (
        admission._key(schedule["schedule_sha256"], plan["run_id"], manifest["attempt_number"]) + ".json"
    )
    return arguments, path


@pytest.mark.parametrize("claim_kind", ["foreign", "altered"])
def test_foreign_or_altered_claim_rejects_before_first_provider_operation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, claim_kind: str,
) -> None:
    run_dir, plan, schedule = _prepare(tmp_path, monkeypatch)
    arguments, path = _claim_arguments(run_dir, schedule, plan)
    if claim_kind == "foreign":
        foreign = arguments | {"selected_owner": admission.owner(
            "staged", tmp_path / "foreign-stage", tmp_path / "foreign-session",
        )}
        admission.publish_claim(**foreign)
    else:
        admission.acquire_staged_claim(**arguments)
        value = json.loads(path.read_bytes())
        value["run_id"] = "altered-synthetic-run"
        path.write_bytes(admission._canonical(value))
    before = _tree_bytes(run_dir)
    transport = FakeTransport(plan["model"], [])
    with pytest.raises(bridge.ToolConversationError, match="no longer empty and ready"):
        bridge.execute_tool_conversation(run_dir, transport)
    assert transport.counts == transport.sends == []
    assert _tree_bytes(run_dir) == before
    with pytest.raises(bridge.ToolConversationError, match="no longer empty and ready"):
        bridge.read_tool_conversation_status(run_dir)
    stored = json.loads((run_dir / "run.json").read_bytes())
    assert stored["state"] == "prepared"
    budget = bridge.TokenLedger(run_dir / "ledger").status()
    assert budget["request_count"] == budget["committed_tokens"] == 0


@pytest.mark.parametrize("alter_at", ["count", "first_response"])
def test_claim_is_revalidated_before_send_and_later_count(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, alter_at: str,
) -> None:
    run_dir, plan, schedule = _prepare(tmp_path, monkeypatch)
    arguments, path = _claim_arguments(run_dir, schedule, plan)

    def alter_claim() -> None:
        value = json.loads(path.read_bytes())
        value["run_id"] = "altered-synthetic-run"
        path.write_bytes(admission._canonical(value))

    class TamperingTransport(FakeTransport):
        def count_input(self, payload: dict) -> int:
            # The claim must already be durable before the first count.
            assert admission.require_claim(**arguments)
            count = super().count_input(payload)
            if alter_at == "count":
                alter_claim()
            return count

        def send(self, payload: dict) -> dict:
            result = super().send(payload)
            if alter_at == "first_response":
                alter_claim()
            return result

    transport = TamperingTransport(plan["model"], [[_message("Synthetic first response")]])
    with pytest.raises(bridge.ToolConversationError, match="indeterminate"):
        bridge.execute_tool_conversation(run_dir, transport)
    assert len(transport.counts) == 1
    assert len(transport.sends) == (0 if alter_at == "count" else 1)
    status = bridge.read_tool_conversation_status(run_dir)
    assert status["state"] == "indeterminate"
    assert status["model_requests_completed"] == len(transport.sends)
    assert status["budget"]["request_count"] == 1
    assert status["budget"]["indeterminate_tokens"] == (30 if alter_at == "count" else 0)
    assert status["budget"]["settled_tokens"] == (0 if alter_at == "count" else 15)
    retry = FakeTransport(plan["model"], [])
    with pytest.raises(bridge.ToolConversationError, match="no retry"):
        bridge.execute_tool_conversation(run_dir, retry)
    assert retry.counts == retry.sends == []


def test_interruption_after_claim_before_count_is_terminal_without_measured_usage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_dir, plan, _ = _prepare(tmp_path, monkeypatch)
    original = admission.acquire_staged_claim

    def interrupted_claim(**kwargs: object) -> str:
        original(**kwargs)
        raise KeyboardInterrupt("synthetic interruption after claim")

    monkeypatch.setattr(admission, "acquire_staged_claim", interrupted_claim)
    transport = FakeTransport(plan["model"], [])
    with pytest.raises(KeyboardInterrupt, match="synthetic interruption"):
        bridge.execute_tool_conversation(run_dir, transport)
    status = bridge.read_tool_conversation_status(run_dir)
    assert status["stored_state"] == "started" and status["state"] == "indeterminate"
    assert status["budget"]["request_count"] == status["budget"]["committed_tokens"] == 0
    assert status["budget"]["committed_cost_micro_usd"] == 0
    assert transport.counts == transport.sends == []
    with pytest.raises(bridge.ToolConversationError, match="no retry"):
        bridge.execute_tool_conversation(run_dir, transport)
    assert transport.counts == transport.sends == []


def test_concurrent_text_only_stage_copies_publish_one_claim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    first, plan, schedule = _prepare(tmp_path, monkeypatch)
    second = _second_stage_run(tmp_path, first, plan, schedule)
    before = {path: (path / "ledger" / "ledger.json").read_bytes() for path in (first, second)}
    release = tmp_path / "release-model-claims"
    code = """
import json, sys, time
from pathlib import Path
sys.path.insert(0, sys.argv[1] + '/scripts')
sys.path.insert(0, sys.argv[1] + '/tests')
import test_run_managed_tool_conversation as fixture
original = fixture.admission.acquire_staged_claim
def synchronized(**kwargs):
    Path(sys.argv[4]).write_text('ready')
    deadline = time.monotonic() + 10
    while not Path(sys.argv[5]).exists():
        if time.monotonic() >= deadline:
            raise RuntimeError('synthetic claim barrier timed out')
        time.sleep(0.005)
    return original(**kwargs)
fixture.admission.acquire_staged_claim = synchronized
transport = fixture.FakeTransport(sys.argv[3], [[fixture._message('First')], [fixture._message('Final')]])
try:
    fixture.bridge.execute_tool_conversation(Path(sys.argv[2]), transport)
except fixture.bridge.ToolConversationError:
    pass
status = fixture.bridge.read_tool_conversation_status(Path(sys.argv[2]))
print(json.dumps({'state': status['state'], 'counts': len(transport.counts), 'sends': len(transport.sends),
                  'requests': status['budget']['request_count'], 'tokens': status['budget']['committed_tokens']}))
"""
    processes = []
    ready = [tmp_path / "first-model-ready", tmp_path / "second-model-ready"]
    try:
        for run_dir, marker in zip((first, second), ready, strict=True):
            processes.append(subprocess.Popen(
                [sys.executable, "-c", code, str(ROOT), str(run_dir), plan["model"], str(marker), str(release)],
                env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LANG": "C.UTF-8",
                     admission.ROOT_ENV: str(tmp_path / "admissions")},
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            ))
        deadline = time.monotonic() + 10
        while not all(path.exists() for path in ready):
            assert time.monotonic() < deadline, "synthetic concurrent claim barrier timed out"
            assert all(process.poll() is None for process in processes)
            time.sleep(0.005)
        release.write_text("release synthetic claims", encoding="utf-8")
        reports = []
        for process in processes:
            stdout, stderr = process.communicate(timeout=15)
            assert process.returncode == 0, stderr
            reports.append(json.loads(stdout))
        assert sorted(report["state"] for report in reports) == ["completed", "indeterminate"]
        assert sorted(report["counts"] for report in reports) == [0, 2]
        assert sorted(report["sends"] for report in reports) == [0, 2]
        assert sorted(report["requests"] for report in reports) == [0, 2]
        assert sorted(report["tokens"] for report in reports) == [0, 30]
        for run_dir, report in zip((first, second), reports, strict=True):
            if report["state"] == "indeterminate":
                assert (run_dir / "ledger" / "ledger.json").read_bytes() == before[run_dir]
                assert not list((run_dir / "responses").iterdir())
                assert not list((run_dir / "tool_session" / "calls").iterdir())
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
                process.communicate(timeout=5)


@pytest.fixture
def available_sandbox() -> None:
    probe = sandbox.probe_sandbox()
    if not probe.available:
        pytest.skip(probe.reason or "sandbox unavailable")


def test_prepare_rejects_time_ceiling_above_schedule_without_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(staged_fixture.plan_confirmatory, "ACTIVE_SECONDS_PER_RUN", 20)
    run_dir, plan, _ = _prepare(tmp_path, monkeypatch, active_limit_seconds=20)
    state = json.loads((run_dir / "run.json").read_text())
    budget = bridge.TokenLedger(run_dir / "ledger").status()
    before = _tree_bytes(tmp_path)
    rejected_dir = tmp_path / "rejected-tool"

    with pytest.raises(bridge.ToolConversationError, match="ceiling is invalid"):
        bridge.prepare_tool_conversation(
            rejected_dir, Path(state["schedule_path"]), Path(state["stage_dir"]), plan,
            limit_tokens=state["limit_tokens"], active_limit_seconds=21,
            cost_limit_micro_usd=state["cost_limit_micro_usd"],
            price_profile=budget["price_profile"],
        )

    assert not rejected_dir.exists()
    assert _tree_bytes(tmp_path) == before


@pytest.mark.parametrize("active_limit_seconds", [20, 19])
def test_prepare_accepts_time_ceiling_at_or_below_schedule(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, active_limit_seconds: int,
) -> None:
    monkeypatch.setattr(staged_fixture.plan_confirmatory, "ACTIVE_SECONDS_PER_RUN", 20)
    run_dir, _, schedule = _prepare(
        tmp_path, monkeypatch, active_limit_seconds=active_limit_seconds,
    )
    status = bridge.read_tool_conversation_status(run_dir)
    assert schedule["per_run_limits"]["active_seconds"] == 20
    assert status["state"] == "prepared"
    assert status["active_limit_seconds"] == active_limit_seconds
    assert status["budget"]["request_count"] == 0
    assert status["model_requests_completed"] == status["tool_calls_completed"] == 0


@pytest.mark.parametrize("operation", ["status", "execute"])
def test_reload_rejects_consistently_rewritten_plan_and_excess_time_ceiling(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, operation: str,
) -> None:
    monkeypatch.setattr(staged_fixture.plan_confirmatory, "ACTIVE_SECONDS_PER_RUN", 20)
    run_dir, plan, _ = _prepare(tmp_path, monkeypatch, active_limit_seconds=20)
    state_path = run_dir / "run.json"
    state = json.loads(state_path.read_text())
    plan["turns"][0]["user"] = "Use the same sealed function after editing the plan."
    plan_bytes = bridge._canonical(plan)
    (run_dir / "plan.json").write_bytes(plan_bytes)
    state.update(plan_sha256=_sha(plan_bytes), active_limit_seconds=21)
    state_path.write_bytes(bridge._canonical(state))
    before = _tree_bytes(tmp_path)
    transport = FakeTransport(plan["model"], [])

    with pytest.raises(bridge.ToolConversationError, match="time ceiling exceeds the schedule"):
        if operation == "status":
            bridge.read_tool_conversation_status(run_dir)
        else:
            bridge.execute_tool_conversation(run_dir, transport)

    assert _tree_bytes(tmp_path) == before
    assert transport.counts == transport.sends == []


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
