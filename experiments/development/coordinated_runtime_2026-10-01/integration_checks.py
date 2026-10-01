"""Six actual fresh CLI/HTTP runs over original cases with synthetic responses."""
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
    args = parser.parse_args()
    destination = args.destination
    destination.chmod(0o700)
    calls = []
    def cli(argv):
        number = len(calls) + 1
        process = subprocess.run([sys.executable, "-I", "-B", *map(str, argv)], capture_output=True, timeout=180)
        (destination / f"cli-{number:03d}.stdout").write_bytes(process.stdout)
        (destination / f"cli-{number:03d}.stderr").write_bytes(process.stderr)
        calls.append({"argv": [sys.executable, "-I", "-B", *map(str, argv)], "exit_code": process.returncode,
                      "stdout": f"cli-{number:03d}.stdout", "stderr": f"cli-{number:03d}.stderr"})
        (destination / "cli_calls.json").write_text(json.dumps(calls, indent=2) + "\n")
        if process.returncode:
            raise ValueError("CLI failed: " + process.stdout.decode(errors="replace") + process.stderr.decode(errors="replace"))
        return json.loads(process.stdout)
    bundle = destination / "bundle"
    source_config = destination / "bundle_configuration.json"
    source_config.write_text(json.dumps(bundle_configuration()))
    cli([runtime.SCRIPTS / "prepare_coordinated_development.py", "build", "--destination", bundle,
         "--configuration", source_config, "--contract-dir", runtime.SPEC / "public_contract",
         "--source-freeze-sha256", runtime.SPEC_SHA256])
    config = destination / "runtime_configuration.json"
    config.write_text(json.dumps(configuration()))
    schedule = json.loads((bundle / "schedule.json").read_bytes())
    rows = []
    for arm in "ABC":
        for case_id in ("D-F", "D-E"):
            parent = destination / (arm + "-" + case_id)
            parent.mkdir(mode=0o700)
            run = parent / "run"
            selected = next(row for row in schedule["runs"] if row["arm"] == arm
                            and row["case_id"] == case_id and row["replica"] == 1)
            script = runtime.SCRIPTS / "coordinated_prototype_runtime.py"
            status = cli([script, "prepare", "--run-dir", run, "--bundle", bundle, "--run-id", selected["run_id"],
                          "--configuration", config, "--admission-root", parent / "admission"])
            fixture = SyntheticRoles(run)
            try:
                with fixture.http_server() as endpoint:
                    for _ in range(50):
                        status = cli([script, "step", "--run-dir", run, "--expected-checkpoint", status["checkpoint_sha256"],
                                      "--local-http-fixture", endpoint])
                        if status["state"] != "paused":
                            break
                assert status["state"] == "completed", status
                reopened = cli([script, "status", "--run-dir", run])
                assert reopened["checkpoint_sha256"] == status["checkpoint_sha256"]
            finally:
                (parent / "http_trace.json").write_text(json.dumps(fixture.trace, sort_keys=True) + "\n")
            from coordinated_prototype_broker import CoordinatedPrototypeBroker
            broker = CoordinatedPrototypeBroker(run, json.loads((run / "run.json").read_bytes())["broker_binding"])
            delegations = [row for row in broker._events() if row["kind"] == "activate"]
            metrics = broker.current_metrics("leader")
            checked = runtime.delivery.check_delivery(bundle / "assets" / case_id, broker.leader_stage() / "work",
                                                      runtime.delivery.delivery_contract_template())
            sends = [row for row in fixture.trace if row["operation"] == "send"]
            assert len(delegations) >= 2 and metrics is not None and checked["structural_checks_passed"]
            assert status["budget"]["request_count"] == len(sends)
            assert status["budget"]["settled_tokens"] == 7 * len(sends)
            assert len([path for path in (parent / "admission").glob("*.json")
                        if not path.name.endswith(".coordinated-binding.json")]) == 1
            overlap = any(a["role"] != b["role"] and a["role"].startswith("worker-") and b["role"].startswith("worker-")
                and max(a["started_ns"], b["started_ns"]) < min(a["ended_ns"], b["ended_ns"])
                for i, a in enumerate(sends) for b in sends[i + 1:])
            assert overlap is (arm != "A")
            reviewer = [row for row in sends if row["role"] == "reviewer"]
            assert len(reviewer) == 1 and "tools" not in reviewer[0]["request"]
            assert "SYNTHETIC-PRIVATE:" not in json.dumps(reviewer[0]["request"])
            assert reviewer[0]["started_ns"] > max(row["ended_ns"] for row in sends if row["role"] != "reviewer")
            rows.append({"arm": arm, "case_id": case_id, "run": str(run), "run_id": selected["run_id"],
                         "mode": broker.public_state()["mode"], "delegations": len(delegations),
                         "model_requests": len(sends), "fixture_reported_tokens": 7 * len(sends),
                         "tool_calls": status["tool_calls_completed"], "local_worker_http_overlap": overlap,
                         "same_claim_count": 1, "final_metric": metrics, "delivery_checker": checked,
                         "trace_sha256": hashlib.sha256((parent / "http_trace.json").read_bytes()).hexdigest(),
                         "formal_cell_executed": False, "quality_assessed": False})
            (parent / "integration_result.json").write_text(json.dumps(rows[-1], indent=2) + "\n")
    result = {"schema": 1, "classification": "original_source_synthetic_response_runtime_controls",
              "runs": rows, "actual_cli_calls": len(calls), "all_cli_exit_zero": True,
              "formal_cells_executed": 0, "quality_assessed": False,
              "provider_activity_authenticated": False, "invoice_authenticated": False}
    (destination / "integration_result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"actual_runs": len(rows), "actual_cli_calls": len(calls), "formal_cells_executed": 0}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
