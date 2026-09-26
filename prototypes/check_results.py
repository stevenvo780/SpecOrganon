"""Check the comparison record against workflow acceptance and negative controls."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("record", type=Path)
    args = parser.parse_args()
    data = json.loads(args.record.read_text(encoding="utf-8"))
    result = {(row["scenario"], row["mode"]): row for row in data["results"]}
    errors: list[str] = []

    def require(condition: bool, message: str) -> None:
        if not condition:
            errors.append(message)

    if "inputs_sha256" in data:
        base = Path(__file__).resolve().parent
        for relative, expected in data["inputs_sha256"].items():
            path = base / relative
            require(path.exists() and hashlib.sha256(path.read_bytes()).hexdigest() == expected,
                    f"input hash mismatch: {relative}")

    for mode in ("sequential", "graph", "risk"):
        for scenario in ("nominal", "resume_after_process_exit", "recovery_after_correction"):
            row = result[(scenario, mode)]
            require(not row["failed_commands"], f"{scenario}/{mode}: unexpected command failure")
            require(len(row["status"]["accepted_phases"]) == 4,
                    f"{scenario}/{mode}: expected four accepted phases")
            require(not row["status"]["unsafe_accepted_phases"],
                    f"{scenario}/{mode}: unsafe accepted phase")
        for scenario, command in (("missing_approval", "advance"),
                                  ("insufficient_evidence", "advance"),
                                  ("invalid_dependency", "init")):
            row = result[(scenario, mode)]
            require(len(row["failed_commands"]) == 1 and
                    row["failed_commands"][0]["command"] == command,
                    f"{scenario}/{mode}: expected {command} rejection")
        require(result[("invalid_dependency", mode)]["state_bytes"] == 0,
                f"invalid_dependency/{mode}: state created despite invalid case")

    expected_unsafe = {
        "late_contradiction": ["engineering", "validation"],
        "evidence_reestimated": ["engineering", "validation"],
        "assumption_shift": ["science", "engineering", "validation"],
        "problem_reframed": ["science", "engineering", "validation"],
    }
    for scenario, expected in expected_unsafe.items():
        require(result[(scenario, "sequential")]["status"]["unsafe_accepted_phases"] == expected,
                f"{scenario}/sequential: negative control changed")
        for mode in ("graph", "risk"):
            require(not result[(scenario, mode)]["status"]["unsafe_accepted_phases"],
                    f"{scenario}/{mode}: unsafe accepted phase")

    for mode in ("graph", "risk"):
        require(result[("problem_reframed", mode)]["status"]["pending_normative"] == ["N"],
                f"problem_reframed/{mode}: normative decision not reopened")
    require(result[("problem_reframed", "sequential")]["status"]["pending_normative"] == [],
            "problem_reframed/sequential: negative control changed")
    require(result[("recovery_after_correction", "sequential")]["repair_commands"] == 4,
            "sequential repair count changed")
    require(result[("recovery_after_correction", "graph")]["repair_commands"] == 6,
            "graph repair count changed")
    require(result[("recovery_after_correction", "risk")]["repair_commands"] == 6,
            "risk repair count changed")
    risk_status = result[("late_contradiction", "risk")]["status"]
    require(risk_status["potential_waves"] == [["E"], ["R"], ["V"]],
            "risk plan did not preserve dependency order")
    require([item["id"] for item in risk_status["work_queue"]] == ["E", "R", "V"],
            "risk work queue changed")
    for mode in ("sequential", "graph"):
        row = result[("early_science_exploration", mode)]
        require(len(row["failed_commands"]) == 2 and not row["status"]["accepted_phases"],
                f"early_science_exploration/{mode}: phase order gate changed")
    early_risk = result[("early_science_exploration", "risk")]
    require(len(early_risk["failed_commands"]) == 1 and
            early_risk["status"]["accepted_phases"] == ["science"] and
            not early_risk["status"]["unsafe_accepted_phases"],
            "early_science_exploration/risk: independent science exploration failed")

    if errors:
        for error in errors:
            print(f"FAIL: {error}")
        return 1
    print(f"PASS: {len(result)} scenario/mode runs; safety checks and negative controls match")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
