"""New actual CLI controls; synthetic loopback responses, never formal cells."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

DOSSIER = Path(__file__).resolve().parent
ROOT = DOSSIER.parents[2]
sys.path.insert(0, str(ROOT / "tests"))
from coordinated_runtime_fixture import SyntheticRoles, bundle_configuration, configuration, runtime  # noqa: E402

ENV = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "TZ": "UTC", "PYTHONDONTWRITEBYTECODE": "1"}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def inventory(root):
    return [{"path": p.relative_to(root).as_posix(), "mode": p.stat().st_mode & 0o777,
             "sha256": sha(p.read_bytes()) if p.is_file() else None}
            for p in sorted(root.rglob("*"))]


class IncompleteRoles(SyntheticRoles):
    def send(self, role, payload):
        response = super().send(role, payload)
        response.update(status="incomplete", output=[], incomplete_details={"reason": "max_output_tokens"})
        return response


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path, required=True)
    destination = parser.parse_args().destination
    destination.mkdir(mode=0o700)
    calls = []
    def cli(argv, expected=0):
        number = len(calls) + 1
        command = [sys.executable, "-I", "-B", *map(str, argv)]
        process = subprocess.run(command, capture_output=True, timeout=180, env=ENV)
        out, err = f"cli-{number:03d}.stdout", f"cli-{number:03d}.stderr"
        (destination / out).write_bytes(process.stdout)
        (destination / err).write_bytes(process.stderr)
        calls.append({"argv": command, "exit_code": process.returncode, "expected_exit_code": expected,
                      "stdout": out, "stderr": err, "stdout_sha256": sha(process.stdout), "stderr_sha256": sha(process.stderr)})
        write(destination / "cli_calls.json", calls)
        assert process.returncode == expected, (number, process.stdout.decode(), process.stderr.decode())
        return json.loads(process.stdout)
    config = bundle_configuration()
    config["seed"] = 123
    config_path = destination / "bundle_configuration.json"
    write(config_path, config)
    bundle = destination / "bundle"
    build_script = runtime.SCRIPTS / "prepare_coordinated_development.py"
    cli([build_script, "build", "--destination", bundle, "--configuration", config_path,
         "--contract-dir", runtime.SPEC / "public_contract", "--source-freeze-sha256", runtime.SPEC_SHA256])
    policy = destination / "runtime_configuration.json"
    write(policy, configuration())
    schedule = json.loads((bundle / "schedule.json").read_bytes())
    entry = runtime.SCRIPTS / "authorized_coordinated_runtime.py"
    observer = runtime.SCRIPTS / "observed_coordinated_runtime.py"
    def prepare(arm, name, selected_bundle=bundle, selected_schedule=schedule):
        parent = destination / name
        parent.mkdir(mode=0o700)
        run, obs = parent / "run", parent / "observation"
        selected = next(r for r in selected_schedule["runs"] if r["arm"] == arm and r["case_id"] == "D-E" and r["replica"] == 1)
        status = cli([runtime.SCRIPTS / "coordinated_prototype_runtime.py", "prepare", "--run-dir", run,
                      "--bundle", selected_bundle, "--run-id", selected["run_id"], "--configuration", policy,
                      "--admission-root", parent / "admission"])
        cli([observer, "release", "--run-dir", run, "--observation-dir", obs,
             "--expected-checkpoint", status["checkpoint_sha256"]])
        return parent, run, obs, status
    rows = []
    for arm in "ABC":
        parent, run, obs, status = prepare(arm, arm + "-D-E")
        fixture = SyntheticRoles(run)
        with fixture.http_server() as endpoint:
            for _ in range(50):
                preview = cli([entry, "preflight", "--run-dir", run, "--observation-dir", obs,
                               "--expected-checkpoint", status["checkpoint_sha256"]])
                assert preview["credentials_read"] is False and preview["provider_requests"] == 0
                result = cli([entry, "step-fixture", "--run-dir", run, "--observation-dir", obs,
                              "--expected-checkpoint", status["checkpoint_sha256"], "--local-http-fixture", endpoint])
                assert result["step_failed"] is False
                native = result["result"]
                if "native_measurement" in native:
                    break
                status = native
        assert native["observation"]["state"] == "delivered"
        sends = [r for r in fixture.trace if r["operation"] == "send"]
        counts = [r for r in fixture.trace if r["operation"] == "count"]
        assert native["native_measurement"]["totals"]["request_count"] == len(sends) == len(counts)
        overlap = any(a["role"] != b["role"] and a["role"].startswith("worker-") and b["role"].startswith("worker-")
                      and max(a["started_ns"], b["started_ns"]) < min(a["ended_ns"], b["ended_ns"])
                      for i, a in enumerate(sends) for b in sends[i + 1:])
        assert overlap is (arm != "A")
        before = inventory(parent)
        outcome = cli([entry, "outcomes", "--run-dir", run])
        assert inventory(parent) == before
        assert outcome["native_guard_verified"] and outcome["native_replay_verified"]
        assert outcome["totals"]["reported_usage"]["unknown_requests"] == 0
        rows.append({"arm": arm, "native_requests": len(sends), "worker_http_overlap": overlap,
                     "report_sha256": sha(json.dumps(native, sort_keys=True).encode()),
                     "readonly_outcomes_unchanged": True, "formal_cell_executed": False})
    parent, run, obs, status = prepare("A", "incomplete")
    fixture = IncompleteRoles(run)
    with fixture.http_server() as endpoint:
        argv = [entry, "step-fixture", "--run-dir", run, "--observation-dir", obs,
                "--expected-checkpoint", status["checkpoint_sha256"], "--local-http-fixture", endpoint]
        failed = cli(argv, expected=2)
        assert failed["step_failed"] and not failed["reexecution_authorized"]
        before = inventory(parent)
        outcomes = cli([entry, "outcomes", "--run-dir", run])
        assert outcomes["native_guard_verified"] and not outcomes["native_replay_verified"]
        assert outcomes["totals"]["reported_usage"]["known_requests"] == 1
        assert outcomes["requests"][0]["response_status"] == "incomplete"
        held = outcomes["totals"]["ledger_commitment"]
        assert held["held_tokens"] == 133
        cli(argv, expected=2)
        assert inventory(parent) == before
        assert len([r for r in fixture.trace if r["operation"] == "send"]) == 1
    write(destination / "incomplete_result.json", {"outcomes": outcomes, "readonly_and_rejection_unchanged": True,
                                                   "http_sends": 1, "original_reservation_retained": True})
    proposed = json.loads((ROOT / "experiments/development/real_route_proposal_2026-10-01/candidates/luna/configuration.json").read_bytes())
    real_config = destination / "openai_configuration.json"
    write(real_config, proposed)
    real_bundle = destination / "openai_bundle"
    cli([build_script, "build", "--destination", real_bundle, "--configuration", real_config,
         "--contract-dir", runtime.SPEC / "public_contract", "--source-freeze-sha256", runtime.SPEC_SHA256])
    real_schedule = json.loads((real_bundle / "schedule.json").read_bytes())
    parent, run, obs, status = prepare("A", "openai_unapproved", real_bundle, real_schedule)
    before = inventory(parent)
    cli([entry, "preflight", "--run-dir", run, "--observation-dir", obs,
         "--expected-checkpoint", status["checkpoint_sha256"]])
    cli([entry, "step", "--run-dir", run, "--observation-dir", obs,
         "--expected-checkpoint", status["checkpoint_sha256"], "--operator-declaration", destination / "missing-declaration.json"], expected=2)
    cli([entry, "step-fixture", "--run-dir", run, "--observation-dir", obs,
         "--expected-checkpoint", status["checkpoint_sha256"], "--local-http-fixture", "http://127.0.0.1:1/v1"], expected=2)
    assert inventory(parent) == before
    report = {"classification": "actual_CLI_synthetic_controls_not_R1", "runs": rows,
              "incomplete_no_reexecution": True, "openai_unapproved_unchanged": True,
              "actual_cli_calls": len(calls), "all_expected_exits": True, "paid_model_requests": 0,
              "formal_cells_executed": 0, "quality_assessed": False, "credentials_passed_to_subprocess": False}
    write(destination / "integration_result.json", report)
    print(json.dumps(report))


if __name__ == "__main__":
    main()
