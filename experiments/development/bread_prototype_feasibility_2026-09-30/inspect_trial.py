"""Inspect preserved native trial bytes; no model, field or custody verdict.

Usage: python inspect_trial.py STAGING_RECEIPT TRIAL_ID TRIAL_DIRECTORY
The staging receipt may redact the directory names; pins identify fixed files.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def pin(path: Path) -> dict:
    raw = path.read_bytes()
    return {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}


def inspect(receipt: Path, trial_id: str, work: Path) -> dict:
    staging = json.loads(receipt.read_text())
    trial = next(row for row in staging["trials"] if row["trial_id"] == trial_id)
    mismatches = [name for name, expected in trial["fixed_files"].items()
                  if not (work / name).is_file() or pin(work / name) != expected]
    names = ["analysis.py", "metrics.json", "sources.json", "report.md",
             "prototype_case.json", "state.json", "prototype_calls.jsonl"]
    artifacts = {name: pin(work / name) for name in names if (work / name).is_file()}
    result = {"schema": 1, "trial_id": trial_id, "mode": trial["mode"],
              "classification": "local_native_trial_byte_inspection",
              "fixed_file_mismatches": mismatches, "artifacts": artifacts,
              "missing_artifacts": [name for name in names if name not in artifacts],
              "native_tokens": None, "native_cost": None,
              "custody_independent": False, "counts_toward_required_24_runs": False}
    if "report.md" in artifacts:
        result["report_word_count_whitespace"] = len((work / "report.md").read_text().split())
    if not all(name in artifacts for name in ["prototype_case.json", "state.json", "prototype_calls.jsonl"]):
        return result
    case = json.loads((work / "prototype_case.json").read_text())
    state = json.loads((work / "state.json").read_text())
    rows = [json.loads(line) for line in (work / "prototype_calls.jsonl").read_text().splitlines()]
    nodes = state["nodes"]
    norm_ids = [key for key, node in nodes.items() if node["kind"] == "normative"]

    def ancestors(key: str, visited: set | None = None) -> set:
        seen = set() if visited is None else visited
        for parent in nodes[key]["depends_on"]:
            if parent not in seen:
                seen.add(parent)
                ancestors(parent, seen)
        return seen

    links = {key: sorted(set(norm_ids) & ancestors(key)) for key, node in nodes.items()
             if node["kind"] == "requirement" and node["phase"] == "engineering"}
    initial_norms = [node for node in case["nodes"] if node["kind"] == "normative"]
    engineering_rejections = [row["seq"] for row in rows
                              if row["argv"][2:3] == ["advance"]
                              and "--phase" in row["argv"]
                              and row["argv"][row["argv"].index("--phase") + 1] == "engineering"
                              and row["exit_code"] != 0]
    history_approval = any(row.get("action") == "approve" for row in state["history"])
    captured_approval = any(row["argv"][2:3] == ["approve"] for row in rows)
    chain_ok = bool(rows) and rows[0]["state_before_sha256"] is None
    for index, row in enumerate(rows):
        chain_ok &= row["seq"] == index + 1 and row["mode"] == trial["mode"]
        chain_ok &= row["helper_sha256"] == trial["fixed_files"]["capture_prototype.py"]["sha256"]
        if index:
            chain_ok &= row["state_before_sha256"] == rows[index - 1]["state_after_sha256"]
    if rows:
        chain_ok &= rows[-1]["state_after_sha256"] == artifacts["state.json"]["sha256"]
    result.update({
        "journal_calls": len(rows), "journal_hash_chain_consistent": bool(chain_ok),
        "prototype_call_allowance_observed": len(rows) <= 20,
        "nonzero_exit_sequences": [row["seq"] for row in rows if row["exit_code"] != 0],
        "phase_status": state["phase_status"], "engineering_rejection_sequences": engineering_rejections,
        "normative_ids": norm_ids, "engineering_normative_links": links,
        "initial_norms_exist_and_pending": bool(initial_norms) and all(
            node["status"] == "pending" for node in initial_norms),
        "final_norms_exist_and_pending": bool(norm_ids) and all(
            nodes[key]["status"] == "pending" for key in norm_ids),
        "normative_link_exists": any(links.values()),
        "engineering_accepted": state["phase_status"]["engineering"] == "accepted",
        "approval_in_state_history": history_approval,
        "approval_in_captured_calls": captured_approval,
        "observed_normative_control": bool(initial_norms) and bool(norm_ids)
        and all(node["status"] == "pending" for node in initial_norms)
        and all(nodes[key]["status"] == "pending" for key in norm_ids)
        and any(links.values()) and bool(engineering_rejections)
        and not history_approval and not captured_approval
        and state["phase_status"]["engineering"] != "accepted",
    })
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("staging_receipt", type=Path)
    parser.add_argument("trial_id")
    parser.add_argument("trial_directory", type=Path)
    args = parser.parse_args()
    print(json.dumps(inspect(args.staging_receipt, args.trial_id, args.trial_directory),
                     indent=2, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
