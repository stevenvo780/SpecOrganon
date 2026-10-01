"""Three new A/B/C D-E runtimes with real CLI, loopback HTTP and native tools."""
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path, required=True)
    destination = parser.parse_args().destination
    destination.chmod(0o700)
    calls = []
    def cli(argv):
        number = len(calls) + 1
        command = [sys.executable, "-I", "-B", *map(str, argv)]
        process = subprocess.run(command, capture_output=True, timeout=180)
        (destination / f"cli-{number:03d}.stdout").write_bytes(process.stdout)
        (destination / f"cli-{number:03d}.stderr").write_bytes(process.stderr)
        calls.append({"argv": command, "exit_code": process.returncode, "stdout": f"cli-{number:03d}.stdout", "stderr": f"cli-{number:03d}.stderr"})
        (destination / "cli_calls.json").write_text(json.dumps(calls, indent=2) + "\n")
        assert process.returncode == 0, (number, process.stdout.decode(), process.stderr.decode())
        return json.loads(process.stdout)
    config = bundle_configuration()
    config["seed"] = 121
    source_config = destination / "bundle_configuration.json"
    source_config.write_text(json.dumps(config))
    bundle = destination / "bundle"
    cli([runtime.SCRIPTS / "prepare_coordinated_development.py", "build", "--destination", bundle,
         "--configuration", source_config, "--contract-dir", runtime.SPEC / "public_contract", "--source-freeze-sha256", runtime.SPEC_SHA256])
    config_path = destination / "runtime_configuration.json"
    config_path.write_text(json.dumps(configuration()))
    schedule = json.loads((bundle / "schedule.json").read_bytes())
    rows = []
    for arm in "ABC":
        parent = destination / (arm + "-D-E")
        parent.mkdir(mode=0o700)
        run, observation = parent / "run", parent / "observation"
        selected = next(row for row in schedule["runs"] if row["arm"] == arm and row["case_id"] == "D-E" and row["replica"] == 1)
        status = cli([runtime.SCRIPTS / "coordinated_prototype_runtime.py", "prepare", "--run-dir", run, "--bundle", bundle,
            "--run-id", selected["run_id"], "--configuration", config_path, "--admission-root", parent / "admission"])
        script = runtime.SCRIPTS / "observed_coordinated_runtime.py"
        cli([script, "release", "--run-dir", run, "--observation-dir", observation, "--expected-checkpoint", status["checkpoint_sha256"]])
        fixture = SyntheticRoles(run)
        try:
            with fixture.http_server() as endpoint:
                for _ in range(50):
                    result = cli([script, "step", "--run-dir", run, "--observation-dir", observation,
                        "--expected-checkpoint", status["checkpoint_sha256"], "--local-http-fixture", endpoint])
                    if "native_measurement" in result:
                        break
                    status = result
            assert result["observation"]["state"] == "delivered"
            reopened = cli([script, "report", "--run-dir", run, "--observation-dir", observation])
            assert reopened == result
        finally:
            # All data are public synthetic controls. Export only hashes/times,
            # without participant payloads or the fixture's private sentinels.
            trace = [{key: row[key] for key in ("operation", "role", "turn", "started_ns", "ended_ns", "declared_input_tokens") if key in row}
                     | {key + "_sha256": hashlib.sha256(json.dumps(row[key], sort_keys=True).encode()).hexdigest()
                        for key in ("request", "response") if key in row} for row in fixture.trace]
            (parent / "http_trace.json").write_text(json.dumps(trace, sort_keys=True) + "\n")
        measured, observed = result["native_measurement"], result["observation"]
        sends = [row for row in trace if row["operation"] == "send"]
        counts = [row for row in trace if row["operation"] == "count"]
        overlap = any(a["role"] != b["role"] and a["role"].startswith("worker-") and b["role"].startswith("worker-")
            and max(a["started_ns"], b["started_ns"]) < min(a["ended_ns"], b["ended_ns"])
            for i, a in enumerate(sends) for b in sends[i + 1:])
        assert overlap is (arm != "A")
        assert measured["totals"]["request_count"] == len(sends) == len(counts)
        assert measured["totals"]["total_tokens"] == 7 * len(sends)
        assert observed["metrics"]["by_kind"]["count_input"]["completed_intervals"] == len(counts)
        assert observed["metrics"]["by_kind"]["send"]["completed_intervals"] == len(sends)
        assert observed["metrics"]["by_kind"]["tool"]["completed_intervals"] == measured["totals"]["tool_count"]
        assert observed["W_local_elapsed_ns"] >= observed["metrics"]["all"]["union_ns"] >= 0
        assert observed["metrics"]["incomplete_operations"] == observed["metrics"]["failed_operations"] == 0
        assert result["native_D119_guard_replay_publication_verified"] is True
        assert all(result["coverage"][key] is True for key in ("local_release_to_delivery", "count_send_tool_exact", "native_send_interval_containment"))
        row = {"arm": arm, "case_id": "D-E", "run_dir": str(run), "observation_dir": str(observation),
               "run_id": selected["run_id"], "schedule_sha256": measured["schedule_sha256"], "native_requests": len(sends),
               "native_tools": measured["totals"]["tool_count"], "fixture_declared_tokens": 7 * len(sends),
               "worker_http_overlap": overlap, "W_local_elapsed_seconds": observed["W_local_elapsed_seconds"],
               "clock_info": observed["clock_info"], "boot_sha256": observed["events"][0]["boot_sha256"],
               "metrics": observed["metrics"], "report_sha256": hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest(),
               "formal_cell_executed": False, "quality_assessed": False}
        (parent / "integration_result.json").write_text(json.dumps(row, indent=2) + "\n")
        rows.append(row)
    result = {"schema": 1, "classification": "prospective_synthetic_local_observation_not_R1", "runs": rows,
              "actual_cli_calls": len(calls), "all_cli_exit_zero": True, "formal_cells_executed": 0,
              "quality_assessed": False, "paid_model_requests": 0, "authenticated_provider_activity": False}
    (destination / "integration_result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"actual_runs": len(rows), "actual_cli_calls": len(calls), "formal_cells_executed": 0}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
