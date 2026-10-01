"""Reopen distinct final synthetic runs without model I/O or tool effects."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    dossier = Path(__file__).resolve().parent
    repo = dossier.parents[2]
    sys.path.insert(0, str(repo / "scripts"))
    from managed_parallel_tools import read_tool_wave_status

    runs, identities = [], set()
    for name in ("final311", "final312"):
        report = json.loads((dossier / "checks" / name / "report.json").read_bytes())
        assert report["all_exit_zero"] and report["source_unchanged"]
        root = Path(report["runtime_root"])
        paths = sorted(path for path in root.iterdir() if path.is_dir() and not path.is_symlink()
                       and path.name.startswith(("test_real_http_private_tools", "test_real_cli_local_http")))
        assert len(paths) == 3
        for path in paths:
            run = path / "run"
            info = run.stat()
            identity = (info.st_dev, info.st_ino)
            assert identity not in identities
            identities.add(identity)
            state = read_tool_wave_status(run)
            assert state["state"] == state["stored_state"] == "completed"
            assert state["completed_requests"] == state["budget"]["request_count"] == 7
            assert state["budget"]["settled_tokens"] == 91 and not state["budget"]["blocked"]
            assert state["tool_calls_completed"] == state["context"]["tools_reserved"] == 4
            assert state["identity_authenticated"] is False and state["formal_cell_executed"] is False
            assert state["context"]["active_seconds"] <= state["context"]["active_limit_seconds"] == 60
            plan = json.loads((run / "plan.json").read_bytes())
            common = json.loads(plan["context"])
            base_path = Path(common["binding"]["base_state_path"])
            assert sha(base_path) == common["binding"]["base_state_sha256"]
            base = json.loads(base_path.read_bytes())
            merged_path = run / "merge" / "method_state.json"
            merged = json.loads(merged_path.read_bytes())
            assert merged["nodes"]["P1"]["version"] == merged["nodes"]["P2"]["version"] == 2
            assert merged["nodes"]["P1"]["status"] == merged["nodes"]["P2"]["status"] == "supported"
            assert all(merged["nodes"][node]["stale"] for node in ("N", "E", "R", "V"))
            assert merged["nodes"]["N"]["status"] == "pending" and merged["phase_status"] == base["phase_status"]
            receipt = json.loads((run / "merge" / "receipt.json").read_bytes())
            assert len(receipt["operations"]) == len(receipt["artifacts"]) == 2
            assert receipt["state_sha256"] == sha(merged_path)
            assert all(sha(Path(item["path"])) == item["sha256"] for item in receipt["artifacts"])
            trace = json.loads((path / "http_trace.json").read_bytes())
            sends = [item for item in trace if item["operation"] == "send"]
            assert len(sends) == 7
            for turn in (1, 2, 3):
                pair = [item for item in sends if item["task"] != "reviewer" and item["turn"] == turn]
                assert len(pair) == 2
                assert max(item["started_ns"] for item in pair) < min(item["ended_ns"] for item in pair)
                assert all(item["budget_at_send"]["request_count"] == turn * 2 for item in pair)
            reviewer = next(item for item in sends if item["task"] == "reviewer")
            assert reviewer["started_ns"] > max(item["ended_ns"] for item in sends if item["task"] != "reviewer")
            assert "SYNTHETIC-PRIVATE:" not in json.dumps(reviewer["request"]) and "tools" not in reviewer["request"]
            runs.append({"gate": name, "path": str(run), "case_id": base["case_id"],
                         "profile": state["execution_profile"], "model_requests": 7, "tool_calls": 4,
                         "fixture_reported_tokens": 91, "checkpoint_sha256": state["checkpoint_sha256"],
                         "state_sha256": sha(merged_path), "receipt_sha256": sha(run / "merge" / "receipt.json"),
                         "publication_sha256": sha(run / "publication.json"), "trace_sha256": sha(path / "http_trace.json"),
                         "original_base_unchanged": True, "overlap_three_waves": True,
                         "reviewer_has_private_reasoning": False, "formal_cell_executed": False})
    result = {"classification": "six_distinct_offline_synthetic_runs_not_models", "runs": runs,
              "verified": True, "formal_cells_executed": 0}
    (dossier / "verified_traces.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"distinct_runs": len(runs), "verified": True, "formal_cells_executed": 0}))


if __name__ == "__main__":
    main()
