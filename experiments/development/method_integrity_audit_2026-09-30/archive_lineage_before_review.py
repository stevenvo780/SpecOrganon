#!/usr/bin/env python3
"""Read-only typed lineage inventory; matching metadata is not scientific proof."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path


WHEEL = "experiments/development/lot_journal_prospectus_2026-09-30/installed/specorganon-0.1.0-py3-none-any.whl"
CASES = {
    "bread64": (
        "experiments/development/lot_journal_prospectus_2026-09-30/installed/312/prospectus/case",
        64,
        [f"{prefix}{name}" for name in ("r_capture", "r_basis", "r_safety", "r_service")
         for prefix in ("", "i_", "c_")] + ["i_doc_mass"],
    ),
    "citibike42": ("cases/citibike_march2024_lineage", 42, ["i_rows", "req_row_report"]),
}


def pin(path: Path) -> dict:
    raw = path.read_bytes()
    return {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def closure(items: dict, key: str) -> set[str]:
    visited, pending = set(), [key]
    while pending:
        current = pending.pop()
        if current in visited:
            continue
        visited.add(current)
        require(current in items, f"missing graph node: {current}")
        pending.extend(items[current]["deps"])
    return visited


def signature(item: dict) -> dict:
    data = item["data"]
    return {"id": item["id"], "kind": item["kind"], "version": item["version"],
            "seq": item["seq"], "deps": item["deps"], "metric": data.get("metric"),
            "unit": data.get("unit"), "threshold": data.get("threshold"),
            "stale": item["stale"], "contested": item["contested"],
            "issues": item["issues"], "approved": item["approved"],
            "approval_status": item["approval_status"],
            "field_measurement_available": data.get("field_measurement_available")}


def indicator_candidates(items: dict, indicator: dict) -> dict:
    data = indicator["data"]
    metric, unit = data.get("metric"), data.get("unit")
    candidates = {"exact_typed_candidates": [], "provisional_metadata_candidates": [],
                  "explicit_mismatch_candidates": []}
    for key in sorted(closure(items, indicator["id"]) - {indicator["id"]}):
        item = items[key]
        if item["kind"] != "evidence":
            continue
        evidence = item["data"]
        record = {"id": key, "version": item["version"], "seq": item["seq"],
                  "metric_key": evidence.get("metric_key"), "unit": evidence.get("unit"),
                  "value": evidence.get("value"), "origin": evidence.get("origin"),
                  "source": evidence.get("source"), "locator": evidence.get("locator"),
                  "scope": evidence.get("scope"), "stale": item["stale"],
                  "contested": item["contested"], "issues": item["issues"]}
        comparisons = [("metric_key", metric), ("unit", unit)]
        mismatches = [field for field, expected in comparisons
                      if expected is not None and evidence.get(field) is not None
                      and evidence[field] != expected]
        exact = (metric is not None and unit is not None
                 and evidence.get("metric_key") == metric and evidence.get("unit") == unit)
        record["explicit_mismatches"] = mismatches
        group = ("explicit_mismatch_candidates" if mismatches else
                 "exact_typed_candidates" if exact else "provisional_metadata_candidates")
        candidates[group].append(record)
    return {"indicator": signature(indicator), **candidates,
            "classification_is_metadata_only": True,
            "full_engine_gate_support_not_asserted": True,
            "measurement_truth_or_normative_approval_not_asserted": True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    repo, output = args.repo.resolve(strict=True), args.output.absolute()
    require(sys.flags.isolated == 1, "run with Python -I")
    require(not output.exists(), "new output file required")
    require(output.parent.is_dir(), "existing output directory required")
    helper_path = repo / "scripts/probe_installed_signed_transports.py"
    spec = importlib.util.spec_from_file_location("installed_origin_check", helper_path)
    require(spec is not None and spec.loader is not None, "origin checker unavailable")
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    wheel = repo / WHEEL
    before = helper._installed(repo, wheel)
    require(len(before["modules"]) == 24, "expected24 installed production modules")
    # Read only public installed engine/ledger after verifying all module origins.
    from specorganon.engine import get_state
    from specorganon.ledger import read_project

    inputs = [repo / "GOAL.md", repo / "docs/protocolo_experimental.md", helper_path,
              Path(__file__).resolve(), wheel]
    inputs.extend(repo / path / "organon.json" for path, _, _ in CASES.values())
    inputs.extend(sorted((repo / "src/specorganon").glob("*.py")))
    pins_before = {str(path.relative_to(repo)): pin(path) for path in inputs}
    # Also compare repository production bytes with the installed wheel snapshot.
    for module_name, installed in before["modules"].items():
        source = (repo / "src" / module_name.replace(".", "/"))
        source = source / "__init__.py" if source.is_dir() else source.with_suffix(".py")
        require(pin(source)["sha256"] == installed["sha256"], f"repository module differs: {source}")
    results = {}
    for name, (relative, revision, targets) in CASES.items():
        path = repo / relative
        state, ledger = get_state(path), read_project(path)
        require(state["revision"] == len(ledger["events"]) == revision, "case revision changed")
        items = state["items"]
        selected = []
        for key in targets:
            nodes = closure(items, key)
            ancestors = [items[k] for k in sorted(nodes - {key})]
            indicators = [items[k] for k in sorted(nodes) if items[k]["kind"] == "indicator"]
            selected.append({
                "item": signature(items[key]),
                "ancestor_ids": sorted(nodes - {key}),
                "problems": [signature(i) for i in ancestors if i["kind"] == "problem"],
                "norms": [signature(i) for i in ancestors if i["kind"] == "norm"],
                "decisions": [signature(i) for i in ancestors if i["kind"] == "decision"],
                "protocols": [signature(i) for i in ancestors if i["kind"] == "protocol"],
                "linked_indicator_audits": [indicator_candidates(items, i) for i in indicators],
                "structural_problem_path": any(i["kind"] == "problem" for i in ancestors),
                "scientific_justification_verified": False,
                "authority_authenticated": False,
            })
        results[name] = {"ledger": relative + "/organon.json", "events": revision,
                         "head_hash": ledger["events"][-1]["hash"],
                         "selected": selected,
                         "accepted_phases": [p for p, g in state["phases"].items() if g["accepted"]]}
    after = helper._installed(repo, wheel)
    pins_after = {str(path.relative_to(repo)): pin(path) for path in inputs}
    require(before == after and pins_before == pins_after, "source or installed bytes changed")
    report = {"schema": 1, "study_id": "D104", "classification": "read-only exposed development metadata audit",
              "invocation": [sys.executable, "-I", str(Path(__file__).resolve()), str(repo), str(output)],
              "installed_before": before, "installed_after": after,
              "source_pins_before": pins_before, "source_pins_after": pins_after,
              "cases": results, "target_count": sum(len(c["selected"]) for c in results.values()),
              "case_ledgers_modified": False, "Q": None, "criteria2and5": "no_demostrado",
              "limits": ["graph paths do not prove semantic justification", "exact metric/unit metadata does not prove truth, population equivalence or field efficacy", "provisional classification only mirrors missing metadata permissiveness, not full protocol/norm/evidence gate validity", "unapproved norms and thresholds remain pending", "sameUID race after final source pin is not excluded"]}
    with output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"targets": report["target_count"], "source_pins_equal": True,
                      "output": str(output), "criteria2and5": "no_demostrado"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
