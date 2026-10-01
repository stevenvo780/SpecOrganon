"""Check retained original-case HTTP traces, publication and provenance."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reports", nargs="+", type=Path, required=True)
    args = parser.parse_args()
    dossier = Path(__file__).resolve().parent
    repo = dossier.parents[2]
    sys.path.insert(0, str(repo / "scripts"))
    from c_parallel_analysis import read_c_analysis_wave_status
    from parallel_analysis_broker import AnalysisParallelToolBroker

    rows, seen = [], set()
    for report_path in args.reports:
        report = json.loads(report_path.read_bytes())
        root = Path(report["runtime_root"])
        originals = sorted(root.rglob("independent_calculation.json"))
        if len(originals) != 3:
            raise ValueError("final gate must retain D-F/D-E HTTP and D-E CLI original-source runs")
        for calculation_path in originals:
            parent, run = calculation_path.parent, calculation_path.parent / "run"
            if run in seen:
                raise ValueError("runtime aliases must not inflate positive run count")
            seen.add(run)
            status = read_c_analysis_wave_status(run)
            if (status["state"] != "completed" or status["formal_cell_executed"] is not False
                    or status["comparable_development_cell"] is not False
                    or status["budget"]["request_count"] != 11
                    or status["budget"]["settled_tokens"] != 143
                    or status["tool_calls_completed"] != 8):
                raise ValueError("original-source run did not close under its one synthetic budget")
            trace = json.loads((parent / "http_trace.json").read_bytes())
            sends = [item for item in trace if item["operation"] == "send"]
            if len(sends) != 11:
                raise ValueError("actual send trace differs from settled requests")
            for turn in range(1, 6):
                pair = [item for item in sends if item["task"] != "reviewer" and item["turn"] == turn]
                if (len(pair) != 2 or max(item["started_ns"] for item in pair) >=
                        min(item["ended_ns"] for item in pair)
                        or any(item["budget_at_send"]["request_count"] != turn * 2 for item in pair)):
                    raise ValueError("private worker sends lack overlap or global batch admission")
            reviewer = next(item for item in sends if item["task"] == "reviewer")
            if ("SYNTHETIC-PRIVATE:" in json.dumps(reviewer["request"])
                    or "tools" in reviewer["request"]
                    or reviewer["started_ns"] <= max(item["ended_ns"] for item in sends
                                                      if item["task"] != "reviewer")):
                raise ValueError("reviewer private-boundary or serial release changed")
            plan = json.loads((run / "plan.json").read_bytes())
            broker = AnalysisParallelToolBroker(run, plan["branch_manifest"])
            operations = broker.operations()
            if len(operations) != 8 or [item["global_ordinal"] for item in operations] != list(range(1, 9)):
                raise ValueError("tool replay differs from the eight globally counted calls")
            terminals = [item["terminal"] for item in operations if item["profile"] == "analysis_readonly"]
            if (len(terminals) != 4 or sum(item["analysis_status"] == "valid" for item in terminals) != 3
                    or sum(item["analysis_status"] == "invalid_json" for item in terminals) != 1
                    or any(item["analysis_work_before"] != item["analysis_work_after_child"]
                           for item in terminals)):
                raise ValueError("real readonly analyses or repair classification changed")
            artifacts = status["merge_result"]["analysis_artifacts"]
            if len(artifacts) != 2:
                raise ValueError("two current branch metrics were not exported")
            for entry in artifacts:
                current = broker.current_metrics(entry["task_id"])
                if (current is None or sha(Path(entry["metrics_path"]).read_bytes()) != entry["metrics_sha256"]
                        or sha(Path(entry["provenance_path"]).read_bytes()) != entry["provenance_sha256"]
                        or current["analysis_metrics_sha256"] != entry["metrics_sha256"]
                        or current["analysis_script_sha256"] != entry["analysis_script_sha256"]
                        or current["receipt_sha256"] != entry["broker_receipt_sha256"]):
                    raise ValueError("metric bytes, current source or provenance differs")
            claim_paths = list((parent / "admissions").glob("*.json"))
            if len(claim_paths) != 1:
                raise ValueError("run acquired more than one parent claim")
            calculation = json.loads(calculation_path.read_bytes())
            rows.append({"runtime": str(run), "report": str(report_path.resolve().relative_to(dossier)),
                         "case_id": json.loads(plan["context"])["prototype_state"]["case_id"],
                         "model_requests": 11, "fixture_reported_tokens": 143, "tools": 8,
                         "valid_analysis": 3, "invalid_analysis_repaired": 1,
                         "single_claim": str(claim_paths[0]), "analysis_artifacts": artifacts,
                         "calculation_sha256": sha(calculation_path.read_bytes()),
                         "observations": calculation["observations"], "formal_cell_executed": False})
    result = {"schema": 1, "classification": "verified_mechanical_original_source_traces_not_model_quality",
              "physical_runs": len(rows), "runs": rows, "formal_cells_executed": 0}
    (dossier / "verified_traces.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"physical_runs": len(rows), "formal_cells_executed": 0}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
