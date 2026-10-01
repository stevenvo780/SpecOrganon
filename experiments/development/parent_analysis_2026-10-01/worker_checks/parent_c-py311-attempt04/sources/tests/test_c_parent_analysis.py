"""Mechanical C bootstrap with original public capsules and real sealed tools."""

from __future__ import annotations

import copy
import json
import subprocess
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import c_parent_analysis as c  # noqa: E402
from local_replay_sandbox import probe_sandbox  # noqa: E402
from prepare_development_round import _capsules  # noqa: E402


GOOD = ("import hashlib,json,sys\nfrom pathlib import Path\n"
        "p=Path(sys.argv[1]); print(json.dumps({'case_id':json.loads((p/'case.json').read_bytes())['case_id'],"
        "'task_sha256':hashlib.sha256((p/'task.md').read_bytes()).hexdigest()}))\n")


def nodes():
    return [{"id": key, "kind": kind, "phase": phase, "depends_on": deps,
             "status": "pending", "claim": "Mechanical public fixture " + key}
            for key, kind, phase, deps in (
                ("P1", "problem", "philosophy", []), ("P2", "assumption", "philosophy", []),
                ("N", "normative", "philosophy", ["P1"]), ("E", "evidence", "science", ["P1"]),
                ("R", "requirement", "engineering", ["E", "N"]), ("V", "test_result", "validation", ["R"]))]


def fixture_case(tmp_path, case_id="D-E"):
    tmp_path.mkdir(mode=0o700, parents=True, exist_ok=True)
    tmp_path.chmod(0o700)
    capsules = tmp_path / "capsules"
    capsules.mkdir(mode=0o700)
    _capsules(capsules, analysis=True)
    case, inputs = capsules / case_id, tmp_path / "inputs"
    inputs.mkdir(mode=0o700)
    (inputs / "tool_policy").write_bytes(b'{"schema":2}\n')
    (inputs / "arm_prompt").write_text(json.dumps({"alternative": "C", "mode": "risk",
        "instructions": "Mechanical parent fixture, not a formal cell."}))
    (inputs / "common_prompt").write_text("Use the public case sources; keep norms pending.")
    (inputs / "task_contract").write_text("Public offline bootstrap control, not model quality.")
    config = {"run_id": "parent-wave-D117-fixture", "model": "offline-fixture-model", "effort": "medium",
              "price_profile": {"model": "offline-fixture-model", "input_rate_micro_usd_per_million": 1000000,
                  "cached_input_rate_micro_usd_per_million": 1000000,
                  "cache_write_rate_micro_usd_per_million": 1000000, "output_rate_micro_usd_per_million": 1000000},
              "limit_tokens": 5000, "max_model_requests": 9, "cost_limit_micro_usd": 5000,
              "active_limit_seconds": 240, "workers": 2, "max_output_tokens": 256,
              "reviewer_max_output_tokens": 256, "max_model_turns": 3, "max_tool_calls": 5,
              "tool_wall_seconds": 5, "leader_max_model_turns": 2, "leader_max_output_tokens": 512}
    return case, inputs, config


def prepare(tmp_path, case_id="D-E"):
    case, inputs, config = fixture_case(tmp_path, case_id)
    run = tmp_path / "run"
    status = c.prepare_c_parent_analysis(run, case, inputs, config, admission_root=tmp_path / "admission")
    return run, status, case, inputs


class Fake:
    def __init__(self, task_id, operations, barrier=None):
        self.task_id, self.operations, self.barrier = task_id, operations, barrier
        self.counts = self.sends = 0
        self.payloads = []

    def count_input(self, payload, *, timeout_seconds):
        assert timeout_seconds > 0
        self.counts += 1
        return 5

    def send(self, payload, *, timeout_seconds):
        assert timeout_seconds > 0
        self.sends += 1
        self.payloads.append(copy.deepcopy(payload))
        if self.barrier:
            self.barrier.wait(10)
        operation = self.operations[self.sends - 1]
        output = [{"type": "reasoning", "encrypted_content": "SYNTHETIC-PRIVATE-" + self.task_id, "summary": []}]
        if operation is None:
            output.append({"type": "message", "role": "assistant", "status": "completed", "content": [
                {"type": "output_text", "text": "Public artifact " + self.task_id + "; empirical support unverified and norms pending."}]})
        else:
            output.append({"type": "function_call", "status": "completed", "name": operation["name"],
                           "call_id": f"call-{self.task_id}-{self.sends}", "arguments": json.dumps(operation["arguments"])})
        return {"id": f"response-{self.task_id}-{self.sends}", "model": "offline-fixture-model",
                "status": "completed", "service_tier": "default", "output": output,
                "usage": {"input_tokens": 5, "output_tokens": 2, "total_tokens": 7}}


def transports(leader_operations=None):
    sync = threading.Barrier(2)
    init = {"name": "development_method", "arguments": {"request": json.dumps({"op": "init", "nodes": nodes()})}}
    write = {"name": "development_method", "arguments": {"request": json.dumps({
        "op": "write", "path": "analysis.py", "offset": 0, "content": GOOD})}}
    analyze = {"name": "development_analysis", "arguments": {"script_sha256": c._sha(GOOD.encode())}}
    return {"leader": Fake("leader", leader_operations or [init, None]),
            "c-task-1": Fake("c-task-1", [write, analyze, None], sync),
            "c-task-2": Fake("c-task-2", [write, analyze, None], sync), "reviewer": Fake("reviewer", [None])}


def step(run, status, all_transports):
    selected = {"leader": all_transports["leader"]} if status["phase"] == "bootstrap" else {
        key: value for key, value in all_transports.items() if key != "leader"}
    return c.execute_c_parent_analysis_step(run, selected, expected_checkpoint=status["checkpoint_sha256"])


def sandbox():
    capability = probe_sandbox()
    if not capability.available:
        pytest.skip(capability.reason)


def test_prepare_empty_work_no_graph_manifest_or_claim(tmp_path):
    run, status, _, _ = prepare(tmp_path)
    assert status["state"] == "prepared" and status["phase"] == "bootstrap"
    assert status["budget"]["request_count"] == 0
    stages = tmp_path / "run-stages"
    assert list((stages / "leader/work").iterdir()) == []
    assert all(list(work.iterdir()) == [] for work in (stages / "slots").glob("*/work"))
    assert not (stages / "branch_manifest.json").exists()
    assert not (stages / "metadata/transition.json").exists()
    assert not list((tmp_path / "admission").glob("*.json"))
    assert not list((run / "seed").iterdir())


@pytest.mark.parametrize("case_id", ["D-F", "D-E"])
def test_real_init_one_parent_fresh_resume_private_workers_and_metrics(tmp_path, case_id):
    sandbox()
    run, status, case, _ = prepare(tmp_path, case_id)
    adapters = transports()
    status = step(run, status, adapters)
    assert status["state"] == "paused" and status["phase"] == "bootstrap", status
    assert status["budget"]["request_count"] == 1 and status["tool_calls_completed"] == 1
    live = json.loads((tmp_path / "run-stages/leader/work/method_state.json").read_bytes())
    assert live["history"][0]["action"] == "init" and live["case_id"] == case_id
    assert live["nodes"]["N"]["status"] == "pending"
    status = step(run, status, adapters)
    assert status["state"] == "paused" and status["phase"] == "wave", status
    seed_raw = (run / "seed/method_state.json").read_bytes()
    assert json.loads(seed_raw) == live
    reopened = subprocess.run([sys.executable, "-B", "-I", str(SCRIPTS / "c_parent_analysis.py"),
        "status", "--run-dir", str(run)], capture_output=True, text=True, timeout=60)
    assert reopened.returncode == 0, reopened.stdout + reopened.stderr
    assert json.loads(reopened.stdout)["checkpoint_sha256"] == status["checkpoint_sha256"]
    for _ in range(3):
        status = step(run, status, adapters)
        assert status["state"] in {"paused", "completed"}, status
    assert status["state"] == "completed", status
    assert status["budget"]["request_count"] == 9 and status["budget"]["settled_tokens"] == 63
    assert status["tool_calls_completed"] == 5
    assert len(list((tmp_path / "admission").glob("*.json"))) == 1
    assert (run / "seed/method_state.json").read_bytes() == seed_raw
    assert (run / "publication.json").is_file()
    merged = status["merge_result"]
    assert merged["caller_graph_required"] is False and merged["seed_origin"] == "sealed_bootstrap_init"
    for entry in merged["analysis_artifacts"]:
        metrics = json.loads(Path(entry["metrics_path"]).read_bytes())
        assert metrics == {"case_id": case_id, "task_sha256": c._sha((case / "task.md").read_bytes())}
    assert len(merged["analysis_artifacts"]) == 2
    assert "SYNTHETIC-PRIVATE-leader" not in json.dumps(adapters["c-task-1"].payloads)
    assert "SYNTHETIC-PRIVATE-" not in json.dumps(adapters["reviewer"].payloads)
    assert "function_call_output" not in json.dumps(adapters["reviewer"].payloads)


def test_final_text_without_real_init_blocks_before_branches(tmp_path):
    sandbox()
    run, status, _, _ = prepare(tmp_path)
    adapters = transports([None])
    status = step(run, status, adapters)
    assert status["state"] == "indeterminate", status
    assert status["budget"]["request_count"] == 1
    assert status["tool_calls_completed"] == 0
    assert not (tmp_path / "run-stages/branch_manifest.json").exists()
    assert not (run / "publication.json").exists()
    with pytest.raises(ValueError):
        step(run, status, adapters)
    assert adapters["leader"].sends == 1


@pytest.mark.parametrize("bad", ["missing_policy", "schema1", "bool_turns", "old_identity", "extra"])
def test_bad_prepare_has_zero_run_stage_or_admission_effects(tmp_path, bad):
    case, inputs, config = fixture_case(tmp_path)
    if bad == "missing_policy":
        (inputs / "tool_policy").unlink()
    elif bad == "schema1":
        (inputs / "tool_policy").write_bytes(b'{"schema":1}')
    elif bad == "bool_turns":
        config["leader_max_model_turns"] = True
    elif bad == "old_identity":
        config["run_id"] = "tool-wave-not-parent"
    else:
        config["state_path"] = "/unused/caller-graph.json"
    with pytest.raises((ValueError, OSError)):
        c.prepare_c_parent_analysis(tmp_path / "run", case, inputs, config, admission_root=tmp_path / "admission")
    assert not (tmp_path / "run").exists()
    assert not (tmp_path / "run-stages").exists()
    assert not (tmp_path / "admission").exists()


@pytest.mark.parametrize("location", ["case", "inputs", "case_alias", "inputs_alias"])
def test_prepare_rejects_physical_source_overlap_without_mutation(tmp_path, location):
    case, inputs, config = fixture_case(tmp_path)
    source = case if location.startswith("case") else inputs
    parent = source
    if location.endswith("alias"):
        parent = tmp_path / "public-source-alias"
        parent.symlink_to(source, target_is_directory=True)
    run = parent / "new-run"
    stages = parent / "new-run-stages"
    before = [c.original._tree(path) for path in (case, inputs)]
    with pytest.raises(ValueError, match="must not overlap"):
        c.prepare_c_parent_analysis(run, case, inputs, config, admission_root=tmp_path / "admission")
    assert [c.original._tree(path) for path in (case, inputs)] == before
    assert not run.exists() and not stages.exists()
    assert not (tmp_path / "admission").exists()


@pytest.mark.parametrize("change", ["source_bytes", "new_local_import"])
def test_cached_source_closure_rechecks_bytes_and_new_local_import(tmp_path, monkeypatch, change):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    for name in ("c_parent_analysis", "managed_parent_analysis", "parent_analysis_broker"):
        (scripts / f"{name}.py").write_text("import optional_dependency\n")
    core_path = tmp_path / "core.py"
    core_path.write_text("# public fixture core\n")
    monkeypatch.setattr(c, "SCRIPTS", scripts)
    monkeypatch.setattr(c, "CORE_PATH", core_path)
    monkeypatch.setattr(c, "_SOURCE_CACHE", None)
    before = c._sources()
    assert c._sources() == before
    if change == "source_bytes":
        (scripts / "c_parent_analysis.py").write_text("import optional_dependency\n# changed\n")
    else:
        (scripts / "optional_dependency.py").write_text("# newly importable local source\n")
    after = c._sources()
    assert after != before
    plan = {"context": c._canonical({"parent_binding": {
        "profile": c.PROFILE, "source_digests": before}}).decode()}
    with pytest.raises(ValueError, match="source closure changed"):
        c.guard_c_parent(plan, {"phase": "bootstrap", "transition": None}, None)


@pytest.mark.parametrize("location", ["case", "inputs", "case_alias", "inputs_alias",
                                      "run", "stages", "default_env", "default_passwd", "ancestor"])
def test_prepare_rejects_admission_overlap_before_any_output(tmp_path, monkeypatch, location):
    case, inputs, config = fixture_case(tmp_path)
    run, stages = tmp_path / "run", tmp_path / "run-stages"
    if location in {"case", "inputs", "case_alias", "inputs_alias"}:
        source = case if location.startswith("case") else inputs
        parent = source
        if location.endswith("alias"):
            parent = tmp_path / "source-alias"
            parent.symlink_to(source, target_is_directory=True)
        selected_root = parent / "registry"
        override = selected_root
    elif location in {"run", "stages"}:
        selected_root = (run if location == "run" else stages) / "registry"
        override = selected_root
    elif location == "default_env":
        selected_root = inputs / "default-registry"
        monkeypatch.setenv(c.admission.ROOT_ENV, str(selected_root))
        override = None
    elif location == "default_passwd":
        monkeypatch.delenv(c.admission.ROOT_ENV, raising=False)
        monkeypatch.setattr(c.admission.pwd, "getpwuid", lambda _: SimpleNamespace(pw_dir=str(case)))
        selected_root = case / ".specorganon-local-admissions-v1"
        override = None
    else:
        selected_root = tmp_path
        override = selected_root
    before = [c.original._tree(path) for path in (case, inputs)]
    existing_root = selected_root.exists()
    with pytest.raises(ValueError, match="admission root must not overlap"):
        c.prepare_c_parent_analysis(run, case, inputs, config, admission_root=override)
    assert [c.original._tree(path) for path in (case, inputs)] == before
    assert not run.exists() and not stages.exists()
    if not existing_root:
        assert not selected_root.exists()
    assert not list(selected_root.glob("*.json"))
