"""D113 integration: real sealed tools over original cases; fake model transport."""

from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import local_run_admission as admission  # noqa: E402
import prepare_development_round as adapter  # noqa: E402
import run_managed_team as team  # noqa: E402
import run_managed_tool_conversation as bridge  # noqa: E402
from preflight_assets import PreflightError, preflight  # noqa: E402
from plan_development_round import compile_schedule  # noqa: E402
from stage_released_run import stage_released_run  # noqa: E402
from test_prepare_development_round import call, configuration, nodes  # noqa: E402
from test_run_managed_team import FakeTransport, _message  # noqa: E402
from verify_development_analysis import evaluate  # noqa: E402


FIXTURES = ROOT / "experiments/development/isolated_analysis_2026-10-01/fixtures"


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def config() -> dict:
    result = configuration()
    result.update(schema=2, analysis_profile="read_only_v1", max_model_requests=128,
                  cost_limit_micro_usd=10_000)
    result["per_run_limits"].update(measured_tokens=4000, tool_calls=64)
    return result


def prepare(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
            case_id: str = "D-E", arm: str = "A") -> tuple[Path, Path, dict, dict]:
    monkeypatch.setenv(admission.ROOT_ENV, str(tmp_path / "admissions"))
    bundle, attempt = tmp_path / "bundle", tmp_path / "attempt"
    adapter.build_round(bundle, config())
    schedule = json.loads((bundle / "schedule.json").read_text())
    run = next(item for item in schedule["runs"]
               if item["case_id"] == case_id and item["arm"] == arm and item["replica"] == 1)
    ready = adapter.prepare_cell(bundle, run["run_id"], attempt)
    return bundle, attempt, run, ready


def analysis_call(raw: bytes, number: int) -> dict:
    return {"type": "function_call", "name": "development_analysis", "status": "completed",
            "call_id": f"offline-analysis-{number}",
            "arguments": json.dumps({"script_sha256": sha(raw)})}


def writes(raw: bytes, start: int) -> list[dict]:
    text = raw.decode("utf-8")
    chunks, offset = [], 0
    for index in range(0, len(text), 6000):
        content = text[index:index + 6000]
        chunks.append(call({"op": "write", "path": "analysis.py", "offset": offset,
                            "content": content}, start + len(chunks)))
        offset += len(content.encode("utf-8"))
    return chunks


def execute(attempt: Path, run: dict, ready: dict, calls: list[dict]) -> tuple[dict, FakeTransport]:
    transport = FakeTransport(run["model_id"], [[item] for item in calls]
                              + [[_message("offline mechanical analysis; norms pending")]])
    paused = team.execute_team_segment(attempt / "managed", transport, ready["checkpoint_sha256"])
    assert paused["state"] == "paused", paused
    final = team.execute_team_segment(
        attempt / "managed", FakeTransport(run["model_id"], [[_message("mechanical review only")]]),
        paused["checkpoint_sha256"])
    assert final["state"] == "completed", final
    return final, transport


@pytest.mark.parametrize("case_id", ["D-F", "D-E"])
@pytest.mark.parametrize("arm", ["A", "B", "C"])
def test_original_cases_actual_readonly_analysis_verified_independently(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case_id: str, arm: str,
) -> None:
    bundle, attempt, run, ready = prepare(tmp_path, monkeypatch, case_id, arm)
    fixture = FIXTURES / ("bread_analysis.py" if case_id == "D-F" else "building_energy_analysis.py")
    raw = fixture.read_bytes()
    immutable = {path: path.read_bytes() for root in (attempt / "stage/case", attempt / "stage/inputs")
                 for path in root.iterdir() if path.is_file()}
    calls = [call({"op": "init", "nodes": nodes()}, 1)] + writes(raw, 2)
    number = len(calls) + 1
    calls.append(analysis_call(raw, number))
    final, transport = execute(attempt, run, ready, calls)
    work = attempt / "stage/work"
    metrics = json.loads((work / "metrics.json").read_text())
    checked = evaluate(case_id, metrics, attempt / "stage/case")
    assert checked["passed"], checked["diagnostics"]
    (tmp_path / "independent_analysis_verification.json").write_text(json.dumps(checked, indent=2))
    assert all(path.read_bytes() == before for path, before in immutable.items())
    assert (work / "analysis.py").read_bytes() == raw
    state = json.loads((work / "method_state.json").read_text())
    assert state["mode"] == adapter.MODES[arm] and state["nodes"]["N"]["status"] == "pending"
    terminal = json.loads((attempt / "managed/tool_session/calls" / f"{number:06d}/terminal.json").read_text())
    assert terminal["execution_profile"] == "analysis_readonly"
    assert terminal["analysis_status"] == "valid" and terminal["analysis_work_readonly_unchanged"]
    assert terminal["analysis_script_sha256"] == sha(raw)
    assert terminal["analysis_metrics_sha256"] == sha((work / "metrics.json").read_bytes())
    assert final["tool_calls_completed"] == len(calls)
    assert final["budget"]["request_count"] == len(calls) + 2
    assert final["budget"]["settled_tokens"] == 15 * (len(calls) + 2)
    assert len(transport.sends[0]["tools"]) == 2
    assert json.loads((bundle / "preparation.json").read_text())["formal_cells_executed"] == 0
    assert team.read_team_status(attempt / "managed")["state"] == "completed"


@pytest.mark.parametrize("bad,expected", [
    (b"print('not JSON')\n", "invalid_json"),
    (b"raise ValueError('participant mistake')\n", "participant_failed"),
    (b"import sys\nsys.stdout.buffer.write(bytes([255]))\n", "error"),
    (b"print('x'*131073)\n", "error"),
    (b"import sys\nsys.exit(79)\n", "participant_failed"),
])
def test_participant_failure_feedback_repair_uses_same_ledger(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, bad: bytes, expected: str,
) -> None:
    _, attempt, run, ready = prepare(tmp_path, monkeypatch)
    good = (FIXTURES / "building_energy_analysis.py").read_bytes()
    calls = [call({"op": "init", "nodes": nodes()}, 1)] + writes(bad, 2)
    bad_number = len(calls) + 1
    calls += [analysis_call(bad, bad_number),
              call({"op": "replace", "path": "analysis.py", "expected_sha256": sha(bad),
                    "content": good.decode()}, bad_number + 1),
              analysis_call(good, bad_number + 2)]
    final, transport = execute(attempt, run, ready, calls)
    receipt = json.loads((attempt / "managed/tool_receipts" / f"{bad_number:04d}.json").read_text())
    output = json.loads(receipt["output"])
    assert output["terminal"]["analysis_status"] == expected
    raw = (attempt / "managed/tool_session/calls" / f"{bad_number:06d}/stdout").read_bytes()
    assert receipt["stdout_sha256"] == sha(raw)
    assert json.loads(output["stdout"])["raw_stdout_sha256"] == sha(raw)
    assert len(output["stdout"].encode()) < 1024
    assert receipt["output"] in transport.sends[bad_number]["input"][-1]["output"]
    metrics = json.loads((attempt / "stage/work/metrics.json").read_text())
    assert evaluate("D-E", metrics, attempt / "stage/case")["passed"]
    assert final["tool_calls_completed"] == len(calls)
    assert final["budget"]["request_count"] == len(calls) + 2


def test_later_invalid_analysis_retires_host_metrics(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, attempt, run, ready = prepare(tmp_path, monkeypatch)
    good, bad = b"print('{}')\n", b"print('invalid')\n"
    calls = [call({"op": "init", "nodes": nodes()}, 1)] + writes(good, 2)
    calls += [analysis_call(good, 3),
              call({"op": "replace", "path": "analysis.py", "expected_sha256": sha(good),
                    "content": bad.decode()}, 4), analysis_call(bad, 5)]
    final, _ = execute(attempt, run, ready, calls)
    assert not (attempt / "stage/work/metrics.json").exists()
    assert final["tool_calls_completed"] == 5


def test_valid_json_between_64_and_128_kib_remains_usable_feedback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, attempt, run, ready = prepare(tmp_path, monkeypatch)
    raw = b"import json\nprint(json.dumps({'public_fixture': 'x'*70000}))\n"
    final, _ = execute(attempt, run, ready,
                       [call({"op": "init", "nodes": nodes()}, 1)] + writes(raw, 2) + [analysis_call(raw, 3)])
    assert final["tool_calls_completed"] == 3
    assert len(json.loads((attempt / "stage/work/metrics.json").read_text())["public_fixture"]) == 70_000


def test_v2_common_sources_caps_and_v1_limits_stay_distinct(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    adapter.build_round(bundle, config())
    schedule = json.loads((bundle / "schedule.json").read_text())
    assert schedule["schema"] == "specorganon.development_round_schedule.v2"
    assert schedule["max_model_requests"] == 128 and schedule["per_run_limits"]["tool_calls"] == 64
    for case_id, originals in adapter.CASE_INPUTS.items():
        for source in originals:
            assert (bundle / "assets" / case_id / Path(source).name).read_bytes() == (ROOT / source).read_bytes()
    names = {p.name for p in (bundle / "assets/D-F").iterdir()}
    assert "source_lca_page_01.txt" in names and "source_survey.txt" in names
    assert not names & {"analysis.py", "report.md", "metrics.json"}
    assert len(json.loads((bundle / "assets/D-E/case.json").read_text())["files"]) == 3
    with pytest.raises(PreflightError, match="confirmatory gate"):
        preflight(schedule, json.loads((bundle / "assets.json").read_text()), gate_root=tmp_path / "gate")
    for schema, cap, requests in [(1, 17, 32), (1, 16, 33), (2, 65, 128), (2, 64, 129)]:
        invalid = config() if schema == 2 else configuration()
        invalid["per_run_limits"]["tool_calls"], invalid["max_model_requests"] = cap, requests
        target = tmp_path / f"invalid-{schema}-{cap}-{requests}"
        with pytest.raises(ValueError):
            adapter.build_round(target, invalid)
        assert not target.exists()


@pytest.mark.parametrize("key", ["name", "tool_id", "executable"])
def test_duplicate_bindings_rejected_before_effects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, key: str,
) -> None:
    bundle, attempt, _, _ = prepare(tmp_path, monkeypatch)
    plan = json.loads((attempt / "managed/plan.json").read_text())
    plan["functions"][1][key] = plan["functions"][0][key]
    with pytest.raises(ValueError, match="unique"):
        team.prepare_team(tmp_path / "bad", bundle / "schedule.json", attempt / "stage", plan,
                          limit_tokens=4000, active_limit_seconds=120, cost_limit_micro_usd=10000,
                          price_profile=config()["price_profile"])
    assert not (tmp_path / "bad").exists()


def test_replay_rejects_mislabelled_selected_function(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, attempt, run, ready = prepare(tmp_path, monkeypatch)
    raw = b"print('{}')\n"
    calls = [call({"op": "init", "nodes": nodes()}, 1)] + writes(raw, 2) + [analysis_call(raw, 3)]
    execute(attempt, run, ready, calls)
    managed = attempt / "managed"
    state, plan = (json.loads((managed / name).read_text()) for name in ("run.json", "plan.json"))
    reservation_path, receipt_path = managed / "tool_reservations/0003.json", managed / "tool_receipts/0003.json"
    reservation = json.loads(reservation_path.read_text())
    reservation["name"], reservation["tool_id"] = "development_method", "method"
    receipt = json.loads(receipt_path.read_text())
    receipt.update(reservation)
    reservation_raw = bridge._canonical(reservation)
    reservation_path.write_bytes(reservation_raw)
    receipt["reservation_sha256"] = sha(reservation_raw)
    receipt_path.write_bytes(bridge._canonical(receipt))
    with pytest.raises(ValueError, match="differ"):
        team._verify_tool_receipt(managed, state, plan, 3, 3, calls[-1],
                                  reservation["request_sha256"], reservation["response_sha256"])


def test_direct_bridge_dispatches_both_profiles(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bundle, attempt, run, _ = prepare(tmp_path, monkeypatch)
    plan = copy.deepcopy(json.loads((attempt / "managed/plan.json").read_text()))
    plan["schema"] = 1
    plan["turns"] = [{"user": segment["user"], "max_output_tokens": segment["max_output_tokens"]}
                     for segment in plan.pop("segments")]
    managed = tmp_path / "direct_bridge"
    schedule = json.loads((bundle / "schedule.json").read_text())
    assets = json.loads((bundle / "assets.json").read_text())
    release, stage = tmp_path / "bridge_release", tmp_path / "bridge_stage"
    preflight(schedule, assets, run_id=run["run_id"], output_dir=release, development_unsequenced=True)
    stage_released_run(schedule, release, stage, development_unsequenced=True)
    bridge.prepare_tool_conversation(managed, bundle / "schedule.json", stage, plan,
                                     limit_tokens=4000, active_limit_seconds=120, cost_limit_micro_usd=10000,
                                     price_profile=config()["price_profile"])
    raw = (FIXTURES / "building_energy_analysis.py").read_bytes()
    calls = [call({"op": "init", "nodes": nodes()}, 1)] + writes(raw, 2) + [analysis_call(raw, 3)]
    transport = FakeTransport(run["model_id"], [[item] for item in calls]
                              + [[_message("mechanical partial")], [_message("mechanical review")]])
    result = bridge.execute_tool_conversation(managed, transport)
    assert result["state"] == "completed", result
    assert result["tool_calls_completed"] == 3
    assert evaluate("D-E", json.loads((stage / "work/metrics.json").read_text()), stage / "case")["passed"]
    assert bridge.read_tool_conversation_status(managed)["state"] == "completed"


def test_legacy_plan_rejects_multiple_functions_before_creation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(admission.ROOT_ENV, str(tmp_path / "admissions"))
    bundle, attempt = tmp_path / "bundle", tmp_path / "attempt"
    adapter.build_round(bundle, configuration())
    schedule = json.loads((bundle / "schedule.json").read_text())
    adapter.prepare_cell(bundle, schedule["runs"][0]["run_id"], attempt)
    plan = json.loads((attempt / "managed/plan.json").read_text())
    extra = dict(plan["functions"][0], name="another", tool_id="another",
                 executable=str(tmp_path / "absent_extra_tool"))
    plan["functions"].append(extra)
    with pytest.raises(ValueError, match="exactly one"):
        team.prepare_team(tmp_path / "bad", bundle / "schedule.json", attempt / "stage", plan,
                          limit_tokens=1000, active_limit_seconds=120, cost_limit_micro_usd=1000,
                          price_profile=configuration()["price_profile"])
    assert not (tmp_path / "bad").exists()


def test_legacy_single_function_rejects_per_tool_profile_policy_before_creation(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    adapter.build_round(bundle, configuration())
    policy_path = bundle / "assets/tool_policy"
    policy = json.loads(policy_path.read_text())
    policy["schema"] = 2
    policy["generic_tools"][0]["profile"] = "analysis_readonly"
    raw = adapter._bytes(policy)
    policy_path.write_bytes(raw)
    original = json.loads((bundle / "schedule.json").read_text())
    manifest = original["manifest"]
    manifest["inputs"]["tool_policy"]["sha256"] = sha(raw)
    schedule = compile_schedule(manifest)
    (bundle / "schedule.json").write_bytes(adapter._bytes(schedule))
    assets = json.loads((bundle / "assets.json").read_text())
    assets.update(schedule_sha256=schedule["schedule_sha256"], input_sha256=schedule["input_sha256"])
    (bundle / "assets.json").write_bytes(adapter._bytes(assets))
    with pytest.raises(ValueError, match="schema differs"):
        adapter.prepare_cell(bundle, schedule["runs"][0]["run_id"], tmp_path / "bad")
    assert not (tmp_path / "bad").exists()
    fake_stage = tmp_path / "staged"
    (fake_stage / "inputs").mkdir(parents=True)
    (fake_stage / "inputs/tool_policy").write_bytes(raw)
    with pytest.raises(ValueError, match="legacy.*policy v1"):
        bridge._tool_binding(fake_stage, schedule, {"name": "only_one", "tool_id": "method",
                                                   "executable": str(bundle / "assets/method_tool")})


@pytest.mark.parametrize("change", ["price", "cost", "requests", "tools", "role"])
def test_v2_direct_team_cannot_bypass_frozen_limits_or_solo_role(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, change: str,
) -> None:
    bundle, attempt, _, _ = prepare(tmp_path, monkeypatch)
    plan = json.loads((attempt / "managed/plan.json").read_text())
    profile, cost = config()["price_profile"], 10000
    if change == "price":
        profile["input_rate_micro_usd_per_million"] += 1
    elif change == "cost":
        cost += 1
    elif change == "requests":
        plan["max_model_requests"] += 1
    elif change == "tools":
        plan["max_tool_calls"] += 1
    else:
        plan["segments"][1]["role"] = "reviewer"
    with pytest.raises(ValueError):
        team.prepare_team(tmp_path / "bypass", bundle / "schedule.json", attempt / "stage", plan,
                          limit_tokens=4000, active_limit_seconds=120, cost_limit_micro_usd=cost,
                          price_profile=profile)
    assert not (tmp_path / "bypass").exists()
