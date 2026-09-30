"""D099 transport is fake; sandbox and toolkit integration use local real processes."""
from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time

import pytest

from scripts import run_subscription_method_trial as trial


# The D099 protocol keeps its original source pins after later CLI additions.
# This fixture tests those exact historical bytes without restoring the checkout.
FROZEN_COMMIT = "0f8c651d15ccd6da99882abba901099fdae6486e"


def _pin(raw):
    return {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


@pytest.fixture(scope="session")
def frozen_repo(tmp_path_factory):
    protocol_raw = trial.PLAN.read_bytes()
    assert hashlib.sha256(protocol_raw).hexdigest() == trial.PLAN_SHA
    protocol = json.loads(protocol_raw)
    repository = tmp_path_factory.mktemp("d099-historical-repo")
    for relative, expected in protocol["toolkit"]["source_files"].items():
        raw = subprocess.run(
            ["git", "show", f"{FROZEN_COMMIT}:{relative}"], cwd=trial.ROOT,
            capture_output=True, check=True, timeout=10,
        ).stdout
        assert _pin(raw) == expected, relative
        target = repository / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    for category in ("sources", "prompts"):
        for expected in protocol[category].values():
            relative = expected["path"]
            raw = (trial.ROOT / relative).read_bytes()
            assert _pin(raw) == {key: expected[key] for key in ("bytes", "sha256")}, relative
            target = repository / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
    return repository


SCRIPT = """import csv, json, sys
from pathlib import Path
rows = list(csv.DictReader((Path(sys.argv[1]) / 'sample_first_complete_week.csv').open()))
print(json.dumps({'rows': len(rows)}))
"""


def _items():
    return [
        {"id": "p1", "kind": "problem", "text": "Reduce energy with household constraints", "refs": [], "data": {}},
        {"id": "a1", "kind": "actor", "text": "Household inhabitants; authority not assumed", "refs": [], "data": {}},
        {"id": "b1", "kind": "boundary", "text": "Public observational sample, no field action", "refs": ["p1"], "data": {}},
        {"id": "e1", "kind": "evidence", "text": "Public dataset provenance, no causal identification", "refs": [],
         "data": {"origin": "published", "source": "UCI Appliances energy prediction", "date": "2016",
                  "locator": "sample_first_complete_week.csv"}},
        {"id": "n1", "kind": "norm", "text": "Do not compromise comfort or safety; decision pending",
         "refs": ["p1", "a1"], "data": {}},
        {"id": "r1", "kind": "requirement", "text": "A prospective proposal remains contingent on inhabitants",
         "refs": ["p1", "n1", "e1"], "data": {"test_duration_weeks": 4}},
    ]


def _proposal(script=SCRIPT, *, items=None):
    return {"analysis_py": script, "draft_report_md": "  Preliminary; human decisions remain pending.\n",
            "items_json": json.dumps([] if items is None else items)}


@pytest.fixture
def admission(tmp_path, monkeypatch, frozen_repo):
    monkeypatch.setenv(trial.ADMISSION_ENV, str(tmp_path / "admission"))
    capture = trial._capture
    toolkit_cli = json.loads(trial.PLAN.read_bytes())["toolkit"]["cli_path"]

    def historical_toolkit_capture(argv, *args, **kwargs):
        if argv[0] == toolkit_cli:
            # The real fixed entry point imports this exact pinned package in
            # local T tests; production authority and admission are unchanged.
            kwargs["env"] = {**kwargs["env"], "PYTHONPATH": str(frozen_repo / "src")}
        return capture(argv, *args, **kwargs)

    monkeypatch.setattr(trial, "_capture", historical_toolkit_capture)
    return frozen_repo


def _fake_cli(tmp_path, monkeypatch, *, proposal=None, behavior="valid"):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    proposal = _proposal() if proposal is None else proposal
    cli = bindir / "codex"
    cli.write_text("#!" + sys.executable + "\n" + f'''
import json, os, sys, time
from pathlib import Path
args = sys.argv[1:]
if args == ["login", "status"]:
    print("Logged in using {"API key" if behavior == "api_key" else "ChatGPT"}")
    sys.exit(0)
root = Path(__file__).parent
schema = json.loads(Path(args[args.index("--output-schema") + 1]).read_text())
first = "analysis_py" in schema["required"]
label = "first" if first else "second"
with (root / "calls.txt").open("a") as stream:
    stream.write(label + "\\n")
(root / (label + ".input.txt")).write_text(sys.stdin.read())
(root / "api_env_present.txt").write_text(str("OPENAI_API_KEY" in os.environ))
if {behavior!r} == "timeout":
    print(json.dumps({{"type":"thread.started","thread_id":"test-only"}}), flush=True)
    time.sleep(300)
value = {proposal!r} if first else {{"report_md":"Observed feedback; no field effect or normative approval."}}
if {behavior!r} == "second_code" and not first:
    value["analysis_py"] = "print('replacement')"
if {behavior!r} == "empty_final" and not first:
    value["report_md"] = "   \\n"
text = json.dumps(value)
Path(args[args.index("-o") + 1]).write_text(text)
kind = "command_execution" if {behavior!r} == "tool" else "agent_message"
events = [{{"type":"thread.started","thread_id":"test-only"}},
          {{"type":"item.completed","item":{{"id":"message","type":kind,"text":text}}}}]
if {behavior!r} in {{"updated_valid", "updated_error"}}:
    events.insert(1, {{"type":"item.updated","item":{{"id":"message","type":
        "error" if {behavior!r} == "updated_error" else "agent_message","text":"partial"}}}})
if {behavior!r} == "error":
    events.append({{"type":"error","message":"synthetic provider failure"}})
events.append({{"type":"turn.completed","usage":{{"input_tokens":0 if {behavior!r} == "zero" else 10,
    "cached_input_tokens":0,"cache_write_input_tokens":0,"output_tokens":10,"reasoning_output_tokens":2}}}})
for event in events:
    print(json.dumps(event), flush=True)
''', encoding="utf-8")
    cli.chmod(0o700)
    host = bindir / "codex-code-mode-host"
    host.write_text("#!" + sys.executable + "\nprint('synthetic local host help')\n")
    host.chmod(0o700)
    monkeypatch.setenv("PATH", str(bindir) + os.pathsep + os.environ["PATH"])
    return bindir


def _prepare(tmp_path, repository, *, arm="N", name="run"):
    directory = tmp_path / name
    assert trial.prepare(repository, directory, arm=arm)["state"] == "prepared"
    return directory


def _review_sha(directory):
    return hashlib.sha256((directory / "first.proposal.json").read_bytes()).hexdigest()


def _calls(bindir):
    path = bindir / "calls.txt"
    return path.read_text().splitlines() if path.exists() else []


def _rejected(call):
    try:
        result = call()
    except (trial.TrialError, trial.CheckpointError, ValueError):
        return
    assert result["state"] == "failed", result


def _require_sandbox():
    from scripts.local_replay_sandbox import probe_sandbox
    assert probe_sandbox().available, "D099 requires actual Linux sandbox for this gate"


def test_prepare_preserves_packet_and_excludes_reference_answers(tmp_path, admission):
    directory = _prepare(tmp_path, admission)
    prompt = (directory / "first.prompt.txt").read_bytes()
    assert (trial.ROOT / "cases/building_energy/task.md").read_bytes() in prompt
    assert (trial.ROOT / "cases/building_energy/source_manifest.json").read_bytes() in prompt
    assert (directory / "input/sample_first_complete_week.csv").stat().st_size == 612074
    assert b"118.28" not in prompt and b"reference.json" not in prompt
    assert not list(directory.rglob("*auth*"))
    assert json.loads((directory / "plan.json").read_bytes())["source_repo"] == str(admission)
    for target in (directory, trial.ROOT / "new-d099-run", admission / "new-d099-run"):
        with pytest.raises(trial.TrialError):
            trial.prepare(admission, target, arm="N")


def test_current_changed_toolkit_is_rejected_without_repinning_or_admission(tmp_path, admission):
    protocol_raw = trial.PLAN.read_bytes()
    protocol = json.loads(protocol_raw)
    originals = {relative: (trial.ROOT / relative).read_bytes()
                 for relative in protocol["toolkit"]["source_files"]}
    changed = {relative for relative, raw in originals.items()
               if _pin(raw) != protocol["toolkit"]["source_files"][relative]}
    assert {"src/specorganon/cli.py", "src/specorganon/server.py"} <= changed
    destination = tmp_path / "current-source-rejection"
    for _ in range(2):
        with pytest.raises(trial.TrialError, match="registered bytes changed"):
            trial.prepare(trial.ROOT, destination, arm="N")
        assert not destination.exists()
        assert not (tmp_path / "admission").exists()
        assert trial.PLAN.read_bytes() == protocol_raw
        assert all((trial.ROOT / relative).read_bytes() == raw
                   for relative, raw in originals.items())


def test_first_turn_exact_preservation_no_auto_replay_and_environment(tmp_path, monkeypatch, admission):
    directory = _prepare(tmp_path, admission)
    proposal = _proposal()
    bindir = _fake_cli(tmp_path, monkeypatch, proposal=proposal)
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-not-a-credential")
    monkeypatch.setenv("ORGANON_APPROVERS_FILE", str(tmp_path / "must-not-be-read"))
    result = trial.generate(directory)
    assert result["state"] == "awaiting_review", result["run"].get("error")
    for key, name in trial.OUTPUTS.items():
        assert (directory / name).read_bytes() == proposal[key].encode()
    assert not (directory / "metrics.json").exists()
    assert (bindir / "api_env_present.txt").read_text() == "False"
    assert result["approved_normative_decisions"] == result["completed_phases"] == 0
    _rejected(lambda: trial.generate(directory))
    assert _calls(bindir) == ["first"]


def test_two_turns_real_sealed_replay_no_code_replacement_or_third_call(tmp_path, monkeypatch, admission):
    _require_sandbox()
    directory = _prepare(tmp_path, admission)
    bindir = _fake_cli(tmp_path, monkeypatch)
    trial.generate(directory)
    original = (directory / "first.analysis.py").read_bytes()
    with pytest.raises(trial.TrialError):
        trial.feedback(directory, reviewed_proposal_sha="0" * 64)
    assert trial.status(directory)["state"] == "awaiting_review"
    result = trial.feedback(directory, reviewed_proposal_sha=_review_sha(directory))
    assert result["state"] == "feedback_ready", result["run"].get("error")
    assert result["analysis_successful"] is True
    assert json.loads((directory / "metrics.json").read_bytes()) == {"rows": 1008}
    result = trial.finalize(directory)
    assert result["state"] == "completed", result["run"].get("error")
    assert (directory / "first.analysis.py").read_bytes() == original
    second_prompt = (bindir / "second.input.txt").read_text()
    assert "1008" in second_prompt
    assert (directory / "first.proposal.json").read_text() in second_prompt
    assert _calls(bindir) == ["first", "second"]
    for call in (lambda: trial.generate(directory),
                 lambda: trial.feedback(directory, reviewed_proposal_sha=_review_sha(directory)),
                 lambda: trial.finalize(directory)):
        _rejected(call)
    assert _calls(bindir) == ["first", "second"]
    process = subprocess.run([sys.executable, str(trial.ROOT / "scripts/run_subscription_method_trial.py"),
                              "status", str(directory)], capture_output=True, text=True, check=True)
    assert json.loads(process.stdout)["state"] == "completed"
    archive = tmp_path / "read-only-archive"
    shutil.copytree(directory, archive)
    assert trial.status(archive)["state"] == "completed"
    _rejected(lambda: trial.finalize(archive))
    assert _calls(bindir) == ["first", "second"]


@pytest.mark.parametrize("behavior", ["api_key", "tool", "error", "zero", "updated_error"])
def test_model_rejection_is_terminal_and_has_no_fallback(tmp_path, monkeypatch, admission, behavior):
    directory = _prepare(tmp_path, admission)
    bindir = _fake_cli(tmp_path, monkeypatch, behavior=behavior)
    result = trial.generate(directory)
    assert result["state"] == "failed"
    _rejected(lambda: trial.generate(directory))
    assert _calls(bindir) == ([] if behavior == "api_key" else ["first"])
    assert trial.status(directory)["state"] == "failed"


def test_safe_updated_message_event_is_accepted(tmp_path, monkeypatch, admission):
    directory = _prepare(tmp_path, admission)
    bindir = _fake_cli(tmp_path, monkeypatch, behavior="updated_valid")
    result = trial.generate(directory)
    assert result["state"] == "awaiting_review", result["run"].get("error")
    assert _calls(bindir) == ["first"]


def test_copies_cannot_add_generation_replay_or_final_call(tmp_path, monkeypatch, admission):
    _require_sandbox()
    directory = _prepare(tmp_path, admission)
    bindir = _fake_cli(tmp_path, monkeypatch)
    prepared = tmp_path / "prepared-copy"
    shutil.copytree(directory, prepared)
    trial.generate(directory)
    _rejected(lambda: trial.generate(prepared))
    assert _calls(bindir) == ["first"]
    awaiting = tmp_path / "awaiting-copy"
    shutil.copytree(directory, awaiting)
    _rejected(lambda: trial.feedback(awaiting, reviewed_proposal_sha=_review_sha(awaiting)))
    assert not (awaiting / "metrics.json").exists()
    trial.feedback(directory, reviewed_proposal_sha=_review_sha(directory))
    feedback_ready = tmp_path / "feedback-copy"
    shutil.copytree(directory, feedback_ready)
    _rejected(lambda: trial.finalize(feedback_ready))
    assert _calls(bindir) == ["first"]
    assert trial.finalize(directory)["state"] == "completed"
    assert _calls(bindir) == ["first", "second"]


def test_safe_prospective_metadata_is_allowed_but_authority_keys_are_not():
    item = _items()[-1]
    item = {**item, "refs": [], "data": {"test_duration_weeks": 4, "test_plan": "proposed", "latest_source": "public"}}
    assert trial._items(json.dumps([item]).encode()) == [item]
    for key in ("approved", "signature", "argv"):
        altered = copy.deepcopy(item)
        altered["data"]["nested"] = {key: True}
        with pytest.raises(trial.TrialError):
            trial._items(json.dumps([altered]).encode())


@pytest.mark.parametrize("change", ["duplicate", "forward_ref", "wrong_kind", "nonfinite", "extra_key"])
def test_items_reject_invalid_graph_before_any_toolkit_call(change):
    items = _items()
    if change == "duplicate":
        items[1]["id"] = items[0]["id"]
    elif change == "forward_ref":
        items[0]["refs"] = ["r1"]
    elif change == "wrong_kind":
        items[0]["kind"] = "test"
    elif change == "nonfinite":
        items[0]["data"]["value"] = float("nan")
    else:
        items[0]["command"] = "approve"
    with pytest.raises((trial.TrialError, trial.CheckpointError)):
        trial._items(json.dumps(items).encode())


@pytest.mark.parametrize("leading_dash", [False, True])
def test_actual_toolkit_trace_has_six_puts_and_no_approval_or_advance(tmp_path, monkeypatch, admission, leading_dash):
    _require_sandbox()
    directory = _prepare(tmp_path, admission, arm="T")
    items = _items()
    if leading_dash:
        items[0]["text"] = "--A literal problem statement starting with dashes"
    bindir = _fake_cli(tmp_path, monkeypatch, proposal=_proposal(items=items))
    trial.generate(directory)
    result = trial.feedback(directory, reviewed_proposal_sha=_review_sha(directory))
    assert result["state"] == "feedback_ready", result["run"].get("error")
    ledgers = []
    for path in directory.rglob("*.json"):
        value = json.loads(path.read_bytes())
        if type(value) is dict and type(value.get("project")) is dict and "events" in value:
            ledgers.append(value)
    assert len(ledgers) == 1
    assert ledgers[0]["project"]["approval_policy"] == "signed"
    assert [event["kind"] for event in ledgers[0]["events"]] == ["item_put"] * 6
    assert ledgers[0]["events"][0]["payload"]["text"] == items[0]["text"]
    assert trial.finalize(directory)["state"] == "completed"
    second_prompt = (bindir / "second.input.txt").read_text()
    assert "requires a verified human approval" in second_prompt
    assert "previous phase is not currently accepted" in second_prompt
    assert _calls(bindir) == ["first", "second"]


def test_negative_analysis_can_inform_report_without_metrics(tmp_path, monkeypatch, admission):
    _require_sandbox()
    directory = _prepare(tmp_path, admission)
    bindir = _fake_cli(tmp_path, monkeypatch, proposal=_proposal("import sys\nprint('expected offline failure', file=sys.stderr)\nsys.exit(2)\n"))
    trial.generate(directory)
    result = trial.feedback(directory, reviewed_proposal_sha=_review_sha(directory))
    assert result["state"] == "feedback_ready", result["run"].get("error")
    assert result["analysis_successful"] is False and not (directory / "metrics.json").exists()
    assert trial.finalize(directory)["state"] == "completed"
    assert "expected offline failure" in (bindir / "second.input.txt").read_text()


def test_second_turn_cannot_return_replacement_code(tmp_path, monkeypatch, admission):
    _require_sandbox()
    directory = _prepare(tmp_path, admission)
    bindir = _fake_cli(tmp_path, monkeypatch, behavior="second_code")
    trial.generate(directory)
    trial.feedback(directory, reviewed_proposal_sha=_review_sha(directory))
    result = trial.finalize(directory)
    assert result["state"] == "failed"
    assert _calls(bindir) == ["first", "second"]
    _rejected(lambda: trial.finalize(directory))
    assert _calls(bindir) == ["first", "second"]


def test_empty_final_report_is_terminal_failure_without_third_call(tmp_path, monkeypatch, admission):
    _require_sandbox()
    directory = _prepare(tmp_path, admission)
    bindir = _fake_cli(tmp_path, monkeypatch, behavior="empty_final")
    trial.generate(directory)
    trial.feedback(directory, reviewed_proposal_sha=_review_sha(directory))
    assert trial.finalize(directory)["state"] == "failed"
    assert _calls(bindir) == ["first", "second"]
    _rejected(lambda: trial.finalize(directory))
    assert _calls(bindir) == ["first", "second"]


def test_tampered_artifact_does_not_remain_valid(tmp_path, monkeypatch, admission):
    directory = _prepare(tmp_path, admission)
    _fake_cli(tmp_path, monkeypatch)
    trial.generate(directory)
    (directory / "first.analysis.py").write_text("print('changed')\n")
    with pytest.raises(trial.TrialError):
        trial.status(directory)


def test_second_call_receives_only_remaining_cumulative_budget(tmp_path, monkeypatch, admission):
    _require_sandbox()
    directory = _prepare(tmp_path, admission)
    _fake_cli(tmp_path, monkeypatch)
    capture = trial._capture
    second_limits = []

    def measured_capture(*args, **kwargs):
        if kwargs.get("stage") == "second":
            second_limits.append(kwargs["timeout_seconds"])
        result = capture(*args, **kwargs)
        if kwargs.get("stage") == "first":
            time.sleep(0.2)
        return result

    monkeypatch.setattr(trial, "_capture", measured_capture)
    first = trial.generate(directory)
    assert first["run"]["active_seconds_used"] >= 0.2
    time.sleep(0.1)  # Review latency is excluded by the registered protocol.
    feedback = trial.feedback(directory, reviewed_proposal_sha=_review_sha(directory))
    remaining = 360 - feedback["run"]["active_seconds_used"]
    result = trial.finalize(directory)
    assert result["state"] == "completed", result["run"].get("error")
    assert len(second_limits) == 1 and second_limits[0] <= remaining
    assert result["run"]["active_seconds_used"] == pytest.approx(
        sum(stage["active_seconds"] for stage in result["run"]["stages"].values()))


def test_model_timeout_preserves_partial_trace_and_forbids_relaunch(tmp_path, monkeypatch, admission):
    directory = _prepare(tmp_path, admission)
    bindir = _fake_cli(tmp_path, monkeypatch, behavior="timeout")
    capture = trial._capture

    def bounded_capture(*args, **kwargs):
        if kwargs.get("stage") == "first":
            kwargs.update(timeout_seconds=0.2, active_deadline=time.monotonic() + 0.2)
        return capture(*args, **kwargs)

    monkeypatch.setattr(trial, "_capture", bounded_capture)
    result = trial.generate(directory)
    assert result["state"] == "failed" and result["run"]["first"]["model"]["timed_out"]
    assert b"thread.started" in (directory / "first.model.stdout.jsonl").read_bytes()
    assert trial.status(directory)["state"] == "failed"
    _rejected(lambda: trial.generate(directory))
    assert _calls(bindir) == ["first"]


def test_toolkit_launch_failure_is_attempted_not_executed(tmp_path, monkeypatch, admission):
    _require_sandbox()
    directory = _prepare(tmp_path, admission, arm="T")
    _fake_cli(tmp_path, monkeypatch, proposal=_proposal(items=_items()))
    capture = trial._capture

    def missing_toolkit(*args, **kwargs):
        if kwargs.get("stage") == "toolkit:init":
            argv = list(args[0])
            argv[0] = str(tmp_path / "nonexistent-toolkit")
            args = (argv, *args[1:])
        return capture(*args, **kwargs)

    monkeypatch.setattr(trial, "_capture", missing_toolkit)
    trial.generate(directory)
    result = trial.feedback(directory, reviewed_proposal_sha=_review_sha(directory))
    assert result["state"] == "feedback_ready", result["run"].get("error")
    feedback = json.loads((directory / "feedback.json").read_bytes())
    assert feedback["toolkit"]["attempted"] is True
    assert feedback["toolkit"]["executed"] is False
    assert feedback["toolkit"]["successful_commands"] == 0
    assert feedback["toolkit"]["trace_created"] is False
    assert not (directory / "case/organon.json").exists()
    assert trial.finalize(directory)["state"] == "completed"


def test_consistent_total_rewrite_below_capture_times_is_rejected(tmp_path, monkeypatch, admission):
    directory = _prepare(tmp_path, admission)
    _fake_cli(tmp_path, monkeypatch)
    trial.generate(directory)
    state = json.loads((directory / "run.json").read_bytes())
    state["active_seconds_used"] = 0
    state["stages"]["generate"]["active_seconds"] = 0
    (directory / "run.json").write_text(json.dumps(state))
    with pytest.raises(trial.TrialError):
        trial.status(directory)


def test_successful_toolkit_cannot_lose_ledger_and_stay_valid(tmp_path, monkeypatch, admission):
    _require_sandbox()
    directory = _prepare(tmp_path, admission, arm="T")
    _fake_cli(tmp_path, monkeypatch, proposal=_proposal(items=_items()))
    trial.generate(directory)
    trial.feedback(directory, reviewed_proposal_sha=_review_sha(directory))
    (directory / "case/organon.json").unlink()
    state = json.loads((directory / "run.json").read_bytes())
    state["artifacts"].pop("case/organon.json")
    (directory / "run.json").write_text(json.dumps(state))
    with pytest.raises(trial.TrialError):
        trial.status(directory)
