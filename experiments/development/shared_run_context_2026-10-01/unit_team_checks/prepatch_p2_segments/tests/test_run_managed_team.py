"""Offline schema-2 role handoffs over one real staged local tool session."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import local_run_admission as admission  # noqa: E402
import run_managed_team as team  # noqa: E402
import test_staged_tool_session as staged_fixture  # noqa: E402


TOOL = """
import json
import sys
from pathlib import Path
assert json.loads(sys.argv[4]) == {'note': 'test'}
work = Path(sys.argv[3])
(work / 'report.md').write_text('sealed shared work\\n')
print('sealed tool stdout')
"""
CALL = {"type": "function_call", "name": "sealed_first", "call_id": "call_1",
        "arguments": '{"note":"test"}', "status": "completed"}
REASONING = {"type": "reasoning", "encrypted_content": "private-leader-reasoning"}
SPECIALIST_REASONING = {"type": "reasoning", "encrypted_content": "private-specialist-reasoning"}


def _message(text: str) -> dict:
    return {"type": "message", "role": "assistant",
            "content": [{"type": "output_text", "text": text}]}


class FakeTransport:
    def __init__(self, model: str, outputs: list[list[dict]]) -> None:
        self.model = model
        self.outputs = outputs
        self.counts: list[dict] = []
        self.sends: list[dict] = []

    def count_input(self, payload: dict) -> int:
        assert payload["parallel_tool_calls"] is False
        assert payload["model"] == self.model
        self.counts.append(payload)
        return 10

    def send(self, payload: dict) -> dict:
        assert payload["parallel_tool_calls"] is False
        self.sends.append(payload)
        return {"id": f"fake-{len(self.sends)}", "model": self.model,
                "service_tier": "default", "status": "completed",
                "usage": {"input_tokens": 10, "output_tokens": 5,
                          "total_tokens": 15},
                "output": self.outputs[len(self.sends) - 1]}


def _segments() -> list[dict]:
    return [
        {"role": "leader", "user": "Run the sealed tool and report.",
         "max_output_tokens": 20, "share_from": []},
        {"role": "specialist", "user": "Inspect the visible result.",
         "max_output_tokens": 20, "share_from": [1]},
        {"role": "leader", "user": "Integrate the specialist's result.",
         "max_output_tokens": 20, "share_from": [2]},
        {"role": "reviewer", "user": "Review artifacts and evidence.",
         "max_output_tokens": 20, "share_from": [1, 2, 3]},
    ]


def _prepare(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *,
    segments: list[dict] | None = None, max_model_requests: int = 6,
    max_tool_calls: int = 1, limit_tokens: int = 1000,
    cost_limit: int = 1000, active_limit_seconds: int = 30,
) -> tuple[Path, dict, dict]:
    monkeypatch.setenv(admission.ROOT_ENV, str(tmp_path / "admissions"))
    schedule, schedule_path, run_id, stage, tool, _, _ = staged_fixture._stage(
        tmp_path, first_body=TOOL, cap=max_tool_calls)
    run = next(item for item in schedule["runs"] if item["run_id"] == run_id)
    plan = {
        "schema": 2, "run_id": run_id, "model": run["model_id"],
        "service_tier": "default", "segments": _segments() if segments is None else segments,
        "functions": [{
            "type": "function", "name": "sealed_first",
            "description": "Execute the sealed generic local tool.",
            "parameters": {"type": "object", "properties": {"note": {"type": "string"}},
                           "required": ["note"], "additionalProperties": False},
            "strict": True, "tool_id": "first", "executable": str(tool),
        }],
        "max_model_requests": max_model_requests,
        "max_tool_calls": max_tool_calls, "tool_wall_seconds": 4,
    }
    if run["effort_provider_value"] is not None:
        plan["reasoning"] = {"effort": run["effort_provider_value"]}
    price = {"model": run["model_id"],
             "input_rate_micro_usd_per_million": 1_000_000,
             "cached_input_rate_micro_usd_per_million": 1_000_000,
             "cache_write_rate_micro_usd_per_million": 1_000_000,
             "output_rate_micro_usd_per_million": 1_000_000}
    run_dir = tmp_path / "managed-team"
    prepared = team.prepare_team(
        run_dir, schedule_path, stage, plan,
        limit_tokens=limit_tokens, active_limit_seconds=active_limit_seconds,
        cost_limit_micro_usd=cost_limit, price_profile=price)
    assert prepared["state"] == "prepared"
    assert prepared["budget"]["request_count"] == 0
    return run_dir, plan, schedule


def _run(run_dir: Path, model: str, outputs: list[list[dict]],
         checkpoint: str) -> tuple[dict, FakeTransport]:
    fake = FakeTransport(model, outputs)
    return team.execute_team_segment(run_dir, fake, checkpoint), fake


def _checkpoint(run_dir: Path) -> str:
    return team.read_team_status(run_dir)["checkpoint_sha256"]


def test_shared_run_handoffs_private_history_and_sealed_tool(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_dir, plan, _ = _prepare(tmp_path, monkeypatch)
    first, lead = _run(run_dir, plan["model"],
                       [[REASONING, CALL], [REASONING, _message("leader result")]],
                       _checkpoint(run_dir))
    assert first["state"] == "paused" and first["cursor"] == 1
    assert first["tool_calls_completed"] == 1
    assert (Path(json.loads((run_dir / "run.json").read_text())["stage_dir"])
            / "work" / "report.md").read_text() == "sealed shared work\n"
    second, specialist = _run(run_dir, plan["model"],
                               [[SPECIALIST_REASONING, _message("specialist result")]],
                               first["checkpoint_sha256"])
    assert second["state"] == "paused" and second["cursor"] == 2
    specialist_input = specialist.sends[0]["input"]
    assert "leader result" in json.dumps(specialist_input)
    assert "private-leader-reasoning" not in json.dumps(specialist_input)
    third, leader_again = _run(run_dir, plan["model"],
                                [[_message("integrated result")]],
                                second["checkpoint_sha256"])
    own_input = json.dumps(leader_again.sends[0]["input"])
    assert "private-leader-reasoning" in own_input
    assert "private-specialist-reasoning" not in own_input
    last, reviewer = _run(run_dir, plan["model"],
                           [[_message("review complete")]],
                           third["checkpoint_sha256"])
    assert last["state"] == "completed" and last["cursor"] == 4
    review_input = json.dumps(reviewer.sends[0]["input"])
    assert "leader result" in review_input and "specialist result" in review_input
    assert "private-leader-reasoning" not in review_input
    assert "private-specialist-reasoning" not in review_input
    assert last["budget"]["request_count"] == 5
    assert last["budget"]["settled_tokens"] == 75
    assert last["budget"]["settled_cost_micro_usd"] == 75
    assert len(lead.sends) == 2


def test_stale_checkpoint_rejects_without_new_provider_operation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_dir, plan, _ = _prepare(tmp_path, monkeypatch)
    old = _checkpoint(run_dir)
    _run(run_dir, plan["model"], [[_message("first")]], old)
    fake = FakeTransport(plan["model"], [[_message("should not send")]])
    with pytest.raises(ValueError):
        team.execute_team_segment(run_dir, fake, old)
    assert fake.counts == fake.sends == []
    assert team.read_team_status(run_dir)["cursor"] == 1


@pytest.mark.parametrize("reference", [[1], [0], [2], [1, 1], [True]])
def test_future_or_ambiguous_share_reference_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, reference: list,
) -> None:
    segments = _segments()
    segments[0]["share_from"] = reference
    monkeypatch.setenv(admission.ROOT_ENV, str(tmp_path / "admissions"))
    schedule, schedule_path, run_id, stage, tool, _, _ = staged_fixture._stage(
        tmp_path, first_body=TOOL, cap=1)
    run = next(item for item in schedule["runs"] if item["run_id"] == run_id)
    plan = {"schema": 2, "run_id": run_id, "model": run["model_id"],
            "service_tier": "default", "segments": segments,
            "functions": [{"type": "function", "name": "sealed_first",
                           "description": "Execute sealed tool.",
                           "parameters": {"type": "object", "properties": {},
                                          "required": [], "additionalProperties": False},
                           "strict": True, "tool_id": "first", "executable": str(tool)}],
            "max_model_requests": 6, "max_tool_calls": 1, "tool_wall_seconds": 4}
    with pytest.raises(team.TeamError, match="segment 1"):
        team._validate_plan(plan, schedule)
    assert not (tmp_path / "managed-team").exists()
    assert schedule_path.is_file() and stage.is_dir()


@pytest.mark.parametrize("folder", ["artifacts", "histories"])
def test_paused_source_tamper_blocks_replay_and_next_count(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, folder: str,
) -> None:
    run_dir, plan, _ = _prepare(tmp_path, monkeypatch)
    first, _ = _run(run_dir, plan["model"], [[_message("first")]], _checkpoint(run_dir))
    path = run_dir / folder / "0001.json"
    value = json.loads(path.read_bytes())
    value["role"] = "reviewer"
    path.write_text(json.dumps(value), encoding="utf-8")
    fake = FakeTransport(plan["model"], [[_message("second")]])
    with pytest.raises(ValueError):
        team.execute_team_segment(run_dir, fake, first["checkpoint_sha256"])
    assert fake.counts == fake.sends == []


def test_import_closure_drift_blocks_before_count(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_dir, plan, _ = _prepare(tmp_path, monkeypatch)
    original = team._source_closure
    monkeypatch.setattr(team, "_source_closure",
                        lambda: original() | {"scripts/fake_helper.py": "0" * 64})
    fake = FakeTransport(plan["model"], [[_message("never sent")]])
    with pytest.raises(team.TeamError, match="source closure"):
        team.execute_team_segment(run_dir, fake, _checkpoint_from_file(run_dir))
    assert fake.counts == fake.sends == []


def _checkpoint_from_file(run_dir: Path) -> str:
    # Read from the context directly when the runner's own source guard is
    # intentionally patched for a negative test.
    return team.RunContext(run_dir / "context").status()["checkpoint_sha256"]


def test_old_transport_cannot_count_after_handoff(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_dir, plan, _ = _prepare(tmp_path, monkeypatch)
    original = team._TeamTransport
    wrappers: list = []

    def capture(transport: FakeTransport, guard: object) -> object:
        wrapper = original(transport, guard)
        wrappers.append(wrapper)
        return wrapper

    monkeypatch.setattr(team, "_TeamTransport", capture)
    fake = FakeTransport(plan["model"], [[_message("first")]])
    team.execute_team_segment(run_dir, fake, _checkpoint(run_dir))
    with pytest.raises(ValueError):
        wrappers[0].count_input({"model": plan["model"]})
    assert len(fake.counts) == len(fake.sends) == 1


def test_model_request_cap_is_global_across_roles(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_dir, plan, _ = _prepare(tmp_path, monkeypatch, max_model_requests=4)
    status, _ = _run(run_dir, plan["model"],
                     [[REASONING, CALL], [_message("first")]], _checkpoint(run_dir))
    status, _ = _run(run_dir, plan["model"], [[_message("second")]],
                     status["checkpoint_sha256"])
    status, _ = _run(run_dir, plan["model"], [[_message("third")]],
                     status["checkpoint_sha256"])
    fake = FakeTransport(plan["model"], [[_message("forbidden fifth")]])
    with pytest.raises(team.TeamError, match="indeterminate"):
        team.execute_team_segment(run_dir, fake, status["checkpoint_sha256"])
    assert fake.counts == fake.sends == []
    stopped = team.read_team_status(run_dir)
    assert stopped["state"] == "truncated"
    assert stopped["budget"]["request_count"] == 4


@pytest.mark.parametrize("limited", ["tokens", "cost"])
def test_token_or_cost_cap_stays_spent_after_handoff(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, limited: str,
) -> None:
    run_dir, plan, _ = _prepare(
        tmp_path, monkeypatch,
        limit_tokens=45 if limited == "tokens" else 1000,
        cost_limit=45 if limited == "cost" else 1000)
    first, _ = _run(run_dir, plan["model"],
                    [[REASONING, CALL], [_message("first")]], _checkpoint(run_dir))
    fake = FakeTransport(plan["model"], [[_message("not admitted")]])
    with pytest.raises(team.TeamError, match="indeterminate"):
        team.execute_team_segment(run_dir, fake, first["checkpoint_sha256"])
    assert len(fake.counts) == 1 and fake.sends == []
    stopped = team.read_team_status(run_dir)
    assert stopped["state"] == "truncated"
    assert stopped["budget"]["request_count"] == 2
    assert stopped["budget"]["settled_tokens"] == 30
    assert stopped["budget"]["settled_cost_micro_usd"] == 30


def test_tool_cap_stays_spent_across_roles(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_dir, plan, _ = _prepare(tmp_path, monkeypatch)
    first, _ = _run(run_dir, plan["model"],
                    [[REASONING, CALL], [_message("first")]], _checkpoint(run_dir))
    fake = FakeTransport(plan["model"], [[CALL]])
    with pytest.raises(team.TeamError, match="indeterminate"):
        team.execute_team_segment(run_dir, fake, first["checkpoint_sha256"])
    assert len(fake.counts) == len(fake.sends) == 1
    stopped = team.read_team_status(run_dir)
    assert stopped["state"] == "truncated"
    assert stopped["tool_calls_completed"] == 1
    assert len(list((run_dir / "tool_session" / "calls").iterdir())) == 1


def test_late_provider_return_cannot_pause(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_dir, plan, _ = _prepare(tmp_path, monkeypatch, active_limit_seconds=1)

    class SlowTransport(FakeTransport):
        def send(self, payload: dict) -> dict:
            time.sleep(1.15)
            return super().send(payload)

    fake = SlowTransport(plan["model"], [[_message("too late")]])
    with pytest.raises(team.TeamError, match="indeterminate"):
        team.execute_team_segment(run_dir, fake, _checkpoint(run_dir))
    stopped = team.read_team_status(run_dir)
    assert stopped["context_state"] == "indeterminate"
    assert stopped["cursor"] == 0
    assert stopped["budget"]["blocked"]


def test_provider_uncertainty_retains_full_reservation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_dir, plan, _ = _prepare(tmp_path, monkeypatch)

    class BrokenTransport(FakeTransport):
        def send(self, payload: dict) -> dict:
            self.sends.append(payload)
            raise RuntimeError("synthetic transport failure")

    fake = BrokenTransport(plan["model"], [])
    with pytest.raises(team.TeamError, match="indeterminate"):
        team.execute_team_segment(run_dir, fake, _checkpoint(run_dir))
    status = team.read_team_status(run_dir)
    assert status["context_state"] == "indeterminate"
    assert status["budget"]["indeterminate_tokens"] == 30
    assert status["budget"]["remaining_tokens"] == 970
    assert len(fake.counts) == len(fake.sends) == 1
    with pytest.raises(team.TeamError, match="no segment"):
        team.execute_team_segment(run_dir, FakeTransport(plan["model"], []),
                                  status["checkpoint_sha256"])


def test_cli_requires_paid_flag_before_key_or_transport(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    run_dir, _, _ = _prepare(tmp_path, monkeypatch)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(team, "OpenAIResponsesHTTP",
                        lambda _key: pytest.fail("transport constructed without flag"))
    assert team.main(["execute", str(run_dir), "--expected-checkpoint", _checkpoint(run_dir)]) == 2
    assert "--allow-paid-requests" in capsys.readouterr().err
    assert team.read_team_status(run_dir)["state"] == "prepared"


def test_claimed_copy_cannot_prepare_second_owner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_dir, plan, schedule = _prepare(tmp_path, monkeypatch)
    second_stage = tmp_path / "stage-copy"
    staged_fixture.stage_released_run.stage_released_run(
        schedule, tmp_path / "release", second_stage, development_unsequenced=True)
    second = tmp_path / "managed-team-copy"
    price = team.TokenLedger(run_dir / "ledger").status()["price_profile"]
    with pytest.raises(ValueError):
        team.prepare_team(
            second, Path(json.loads((run_dir / "run.json").read_text())["schedule_path"]),
            second_stage, plan, limit_tokens=1000, active_limit_seconds=30,
            cost_limit_micro_usd=1000, price_profile=price)
    assert team.read_team_status(run_dir)["state"] == "prepared"
    assert team.TokenLedger(second / "ledger").status()["request_count"] == 0


def test_paused_run_resumes_in_new_python_process(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_dir, plan, _ = _prepare(tmp_path, monkeypatch)
    first, _ = _run(run_dir, plan["model"], [[_message("first")]], _checkpoint(run_dir))
    code = """
import json, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import run_managed_team as team
class Fake:
    def count_input(self, payload): return 10
    def send(self, payload):
        return {'id':'child-2','model':payload['model'],'service_tier':'default',
                'status':'completed','usage':{'input_tokens':10,'output_tokens':5,
                'total_tokens':15},'output':[{'type':'message','role':'assistant',
                'content':[{'type':'output_text','text':'child result'}]}]}
result=team.execute_team_segment(Path(sys.argv[2]), Fake(), sys.argv[3])
print(json.dumps({'state':result['state'],'cursor':result['cursor']}))
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(ROOT / "scripts"), str(run_dir),
         first["checkpoint_sha256"]], capture_output=True, text=True, check=False,
        timeout=30, env=os.environ.copy())
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["cursor"] == 2
    assert team.read_team_status(run_dir)["budget"]["request_count"] == 2


def test_active_process_crash_cannot_resume_or_recover_balance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_dir, plan, _ = _prepare(tmp_path, monkeypatch)
    code = """
import os, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import run_managed_team as team
class Crash:
    def count_input(self, payload): return 10
    def send(self, payload): os._exit(17)
team.execute_team_segment(Path(sys.argv[2]), Crash(), sys.argv[3])
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(ROOT / "scripts"), str(run_dir),
         _checkpoint(run_dir)], capture_output=True, text=True, check=False,
        timeout=30, env=os.environ.copy())
    assert result.returncode == 17
    status = team.read_team_status(run_dir)
    assert status["context_state"] == "indeterminate"
    assert status["cursor"] == 0
    assert status["budget"]["blocked"]
    assert status["budget"]["request_count"] == 1
    fake = FakeTransport(plan["model"], [])
    with pytest.raises(team.TeamError, match="no segment"):
        team.execute_team_segment(run_dir, fake, status["checkpoint_sha256"])
    assert fake.counts == fake.sends == []
