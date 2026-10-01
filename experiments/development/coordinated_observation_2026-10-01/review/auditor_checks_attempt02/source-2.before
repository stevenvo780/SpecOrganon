"""Six finite report-only native CLI reads; preserve raw output and inventories."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess

import audit_frozen_evidence as audit


def main():
    source_before = audit.source_audit()
    rows = []
    for interpreter in ("311", "312"):
        directory = audit.DOSSIER / "checks" / ("integration" + interpreter)
        gate = audit.read_json(directory / "report.json")
        root = Path(gate["runtime_destination"])
        before = audit.inventory(root)
        audit.require(audit.same(before, audit.read_json(directory / "runtime_inventory.json")), "pre-read archived origin inventory differs")
        cli_calls = audit.read_json(root / "cli_calls.json")
        for row in gate["integration_result"]["runs"]:
            argv = [f"/tmp/specorganon-D107-deps-re8v1j45/venv-{interpreter}/bin/python", "-I", "-B",
                    str(audit.ROOT / "scripts/observed_coordinated_runtime.py"), "report",
                    "--run-dir", row["run_dir"], "--observation-dir", row["observation_dir"]]
            expected_command = next(call for call in cli_calls if call["argv"][4] == "report"
                                    and call["argv"][call["argv"].index("--run-dir") + 1] == row["run_dir"])
            expected = (root / expected_command["stdout"]).read_bytes()
            result = subprocess.run(argv, cwd=audit.ROOT, capture_output=True, timeout=60)
            stem = "reopened_" + interpreter + "_" + row["arm"]
            for kind, data in (("stdout", result.stdout), ("stderr", result.stderr)):
                with (audit.REVIEW / (stem + "." + kind)).open("xb") as stream:
                    stream.write(data)
            audit.require(result.returncode == 0 and result.stderr == b"", "read-only report command rejected")
            audit.require(result.stdout == expected, "reopened final report bytes differ recorded CLI")
            audit.require(all(value not in result.stdout for value in (b"SYNTHETIC-PRIVATE", b"PRIVATE-")), "reopened projection leaks private sentinel")
            rows.append({"interpreter": interpreter, "arm": row["arm"], "run_id": row["run_id"], "argv": argv,
                         "exit_code": result.returncode, "stdout_bytes": len(result.stdout),
                         "stdout_sha256": hashlib.sha256(result.stdout).hexdigest(),
                         "stderr_bytes": len(result.stderr), "stderr_sha256": hashlib.sha256(result.stderr).hexdigest(),
                         "stdout_path": stem + ".stdout", "stderr_path": stem + ".stderr",
                         "matches_original_report_bytes": True})
        audit.require(audit.same(before, audit.inventory(root)), "report reads changed runtime/observation/bundle/admission bytes or modes")
    audit.require(source_before == audit.source_audit(), "sources changed during report reads")
    # Also recheck all historical receipt pins and twelve originals after reads.
    baseline = audit.baseline_audit(audit.read_json(audit.DOSSIER / "checks/final311/baseline_before.json"))
    report = {"schema": 1, "scope": "six_native_report_only_CLI_reads_no_model_or_tool_invocations",
              "source_freeze_commit": audit.FREEZE_COMMIT, "commands": rows,
              "new_runtime_complete_inventories_before_after_equal": True, "sources_before_after_equal": True,
              "historical_baseline_after": baseline, "formal_cells_executed": 0, "paid_model_requests": 0,
              "limits": ["Native guards/readers are local cooperative checks, not authenticated custody",
                         "No step, count, send, tool launch, native suite, restore or extraction performed"]}
    with (audit.REVIEW / "reopened_reports_review.json").open("x") as stream:
        json.dump(report, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"read_only_commands": len(rows), "all_exit_zero": True,
                      "original_final_report_bytes_equal": True, "all_inventories_equal": True}))


if __name__ == "__main__":
    main()
