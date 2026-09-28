"""Score fixed, exposed Citi Bike source reasoning; no GOAL acceptance metric."""

from __future__ import annotations

import argparse
import hashlib
import json
from fractions import Fraction
from pathlib import Path


EXPECTED_CLAIMS = {
    "C1": "supported",
    "C2": "unsupported",
    "C3": "contradicted",
    "C4": "supported",
    "C5": "unsupported",
    "C6": "supported",
    "C7": "contradicted",
    "C8": "unsupported",
    "C9": "supported",
    "C10": "unsupported",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def score(task_path: Path, response_path: Path) -> dict:
    task = json.loads(task_path.read_text(encoding="utf-8"))
    response = json.loads(response_path.read_text(encoding="utf-8"))
    if set(task["claims"]) != set(EXPECTED_CLAIMS):
        raise ValueError("the predeclared claims changed")
    if type(response) is not dict or set(response) != {
        "claims", "fractions", "unit", "criterion_5", "next_measurement",
    }:
        raise ValueError("response schema differs")
    claims = response["claims"]
    fractions = response["fractions"]
    if type(claims) is not dict or set(claims) != set(EXPECTED_CLAIMS):
        raise ValueError("claim keys differ")
    if type(fractions) is not dict or set(fractions) != {"rental", "return"}:
        raise ValueError("fraction keys differ")
    facts = task["facts"]
    expected_fractions = {
        "rental": str(Fraction(facts["rental_enabled_with_bike_rows"], facts["eligible_rows"])),
        "return": str(Fraction(facts["return_enabled_with_dock_rows"], facts["eligible_rows"])),
    }
    checks = {
        **{key: claims[key] == expected for key, expected in EXPECTED_CLAIMS.items()},
        **{f"fraction_{key}": fractions[key] == expected
           for key, expected in expected_fractions.items()},
        "unit": response["unit"] == "station_snapshot_rows",
        "criterion_5": response["criterion_5"] == "not_assessed",
    }
    measurement = response["next_measurement"]
    if type(measurement) is not str or not measurement.strip():
        raise ValueError("next_measurement must be a sentence")
    return {
        "schema": 1,
        "classification": "exposed_development_source_reasoning_score_not_goal_4",
        "task_sha256": _sha256(task_path),
        "response_sha256": _sha256(response_path),
        "score": sum(checks.values()),
        "maximum": len(checks),
        "checks": checks,
        "next_measurement_scored": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("task", type=Path)
    parser.add_argument("response", type=Path)
    arguments = parser.parse_args()
    print(json.dumps(score(arguments.task, arguments.response), sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
