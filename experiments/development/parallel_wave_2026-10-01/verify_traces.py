"""Read six distinct HTTP fixture traces; pytest symlink aliases are excluded."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


def main():
    dossier = Path(__file__).resolve().parent
    sys.path.insert(0, str(dossier.parents[2] / "scripts"))
    import c_parallel_work as c

    rows = []
    for interpreter in ("final311", "final312"):
        gate = json.loads((dossier / "checks" / interpreter / "report.json").read_text())
        root = Path(gate["runtime_root"])
        for folder in sorted(root.iterdir()):
            if folder.is_symlink() or not folder.is_dir():
                continue
            if not (folder.name.startswith("test_real_http_c_wave_overla")
                    or folder.name.startswith("test_c_cli_prepare_and_status")):
                continue
            run = folder / "run"
            plan = json.loads((run / "plan.json").read_text())
            c._guard(plan)
            snapshot = c.read_wave_status(run)
            assert snapshot["state"] == "completed" and snapshot["artifact_count"] == 3
            assert snapshot["budget"]["request_count"] == 3
            assert snapshot["budget"]["settled_tokens"] == 39 and not snapshot["formal_cell_executed"]
            prompts = [json.loads(json.loads((run / "requests" / f"{task}.json").read_text())["input"][0]["content"])
                       for task in ("c-task-1", "c-task-2", "reviewer")]
            assert all(prompt["common_context"] == plan["context"] for prompt in prompts)
            assert "PRIVATE:" not in json.dumps(prompts[2])
            sends = [json.loads((run / "receipts" / f"c-task-{i}.json").read_text()) for i in (1, 2)]
            overlap = min(v["send_ended_ns"] for v in sends) - max(v["send_started_ns"] for v in sends)
            assert overlap > 0
            reviewer = json.loads((run / "receipts" / "reviewer.json").read_text())
            assert reviewer["send_started_ns"] > max(v["send_ended_ns"] for v in sends)
            bound = json.loads(plan["context"])
            base_path = Path(bound["binding"]["base_state_path"])
            base_raw = base_path.read_bytes()
            base = json.loads(base_raw)
            assert hashlib.sha256(base_raw).hexdigest() == bound["binding"]["base_state_sha256"]
            assert base["nodes"]["N"]["status"] == "pending"
            assert not any(v == "accepted" for v in base["phase_status"].values())
            for artifact in snapshot["artifacts"]:
                assert hashlib.sha256(Path(artifact["path"]).read_bytes()).hexdigest() == artifact["sha256"]
            rows.append({"interpreter": interpreter, "runtime_path": str(folder), "case_id": base["case_id"],
                         "cli_subprocess": folder.name.startswith("test_c_cli"), "state": "completed",
                         "send_overlap_ns": overlap, "review_after_workers": True,
                         "common_context_identical": True, "private_reasoning_excluded_from_review": True,
                         "requests": 3, "reported_synthetic_usage_tokens": 39, "normative_status": "pending",
                         "core_state_unchanged_verified": True, "artifacts": snapshot["artifacts"], "formal_cell": False})
    assert len(rows) == 6 and sum(row["cli_subprocess"] for row in rows) == 2
    assert len({row["runtime_path"] for row in rows}) == 6
    report = {"classification": "six_public_synthetic_http_traces_not_model_runs", "traces": rows,
              "formal_cells_executed": 0,
              "enumeration_correction": "initial inline checker included pytest current symlink; identity guard rejected alias; tool-only stderr, no run or provider was launched"}
    (dossier / "verified_traces.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"verified_positive_traces": len(rows), "model_runs": 0}))


if __name__ == "__main__":
    main()
