"""Audit one exposed, locally recorded A/B by N/S/T development pilot.

Usage: python scripts/audit_development_triplet.py --expected-plan-sha256 SHA256 [RUN_DIR ...]

This reads at most six run directories through observe_run_dir(). It does not
call a provider, run generated code, or establish criterion 4. The plan digest
is supplied by the caller; neither its prelaunch custody nor the provider's
effective settings can be authenticated from these local files.
Exit 0 means six recorded local runs are ready for inspection, 1 means the
completed audit found gaps or mismatches, and 2 means invalid CLI arguments.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable

from observe_development_run import ObservationError, observe_run_dir
from run_development_arm import MAX_ACTIVE_BUDGET_SECONDS


SHA256 = re.compile(r"[0-9a-f]{64}\Z")
CELLS = tuple((family, arm) for family in ("A", "B") for arm in ("N", "S", "T"))
SUCCESS_STATUSES = frozenset({"artifacts_ready_for_inspection", "output_replayed"})
INPUT_NAMES = (
    "work/task.md", "work/source_manifest.json",
    "work/sample_first_complete_week.csv", "work/common.md",
    "work/arm.md", "prompt.txt",
)
COMMON_INPUT_NAMES = INPUT_NAMES[:4]
ARM_INPUT_NAMES = INPUT_NAMES[4:]


def _label(cell: tuple[str, str]) -> str:
    return f"{cell[0]}/{cell[1]}"


def _sha256(value: Any) -> bool:
    return type(value) is str and SHA256.fullmatch(value) is not None


def _verified_hashes(observation: dict[str, Any]) -> dict[str, str | None]:
    inputs = observation.get("verified_inputs")
    if type(inputs) is not dict:
        inputs = {}
    hashes: dict[str, str | None] = {}
    for name in INPUT_NAMES:
        record = inputs.get(name)
        hashes[name] = (record["sha256"] if type(record) is dict
                        and _sha256(record.get("sha256")) else None)
    return hashes


def _local_usage(observation: dict[str, Any]) -> dict[str, Any] | None:
    # A failed or partial run remains in its assigned cell, but has no
    # completed local usage result for the six-cell audit.
    if observation.get("execution_status") not in SUCCESS_STATUSES:
        return None
    usage = observation.get("cli_usage")
    if (type(usage) is not dict or usage.get("complete") is not True
            or usage.get("terminal_success") is not True
            or type(usage.get("final_usage")) is not dict):
        return None
    return usage["final_usage"]


def _record(run_dir: Path, index: int) -> tuple[dict[str, Any], dict[str, Any] | None]:
    record: dict[str, Any] = {
        "input_index": index,
        "run_dir": str(run_dir),
        "cell": None,
        "execution_status": None,
        "observation_state": None,
        "run_json_sha256": None,
        "pilot_plan_sha256": None,
        "activation_dossier_sha256": None,
        "requested_provider_cli": None,
        "requested_model": None,
        "requested_effort": None,
        "requested_tool_policy": None,
        "requested_local_budget_seconds": None,
        "local_usage": None,
        "verified_input_sha256": {name: None for name in INPUT_NAMES},
        "invalid_reasons": [],
    }
    try:
        observation = observe_run_dir(run_dir)
    except (ObservationError, OSError) as exc:
        record["invalid_reasons"].append(f"observation_rejected: {exc}")
        return record, None

    record["execution_status"] = observation.get("execution_status")
    record["observation_state"] = observation.get("observation_state")
    record["run_json_sha256"] = observation.get("run_json_sha256")
    record["requested_provider_cli"] = observation.get("provider_cli")
    record["requested_model"] = observation.get("requested_model")
    record["requested_effort"] = observation.get("requested_effort")
    record["requested_tool_policy"] = observation.get("tool_policy")
    record["verified_input_sha256"] = _verified_hashes(observation)
    budget = observation.get("run_time_budget")
    if type(budget) is dict:
        record["requested_local_budget_seconds"] = budget.get("active_budget_seconds")
    record["local_usage"] = _local_usage(observation)
    binding = observation.get("pilot_triplet_binding")
    if observation.get("pilot_mode") != "explicit_triplet" or type(binding) is not dict:
        record["invalid_reasons"].append("generic_run_without_explicit_triplet_binding")
        return record, observation
    record["pilot_plan_sha256"] = binding.get("plan_sha256")
    record["activation_dossier_sha256"] = binding.get("activation_dossier_sha256")
    cell = binding.get("cell")
    if type(cell) is dict and (cell.get("family_slot"), cell.get("arm")) in CELLS:
        record["cell"] = {"family_slot": cell["family_slot"], "arm": cell["arm"]}
    else:
        record["invalid_reasons"].append("invalid_pilot_cell")
    if binding.get("plan_schema") != 2:
        record["invalid_reasons"].append("pilot_plan_is_not_schema_2")
    if not _sha256(binding.get("activation_dossier_sha256")):
        record["invalid_reasons"].append("invalid_activation_dossier_sha256")
    if (type(record["requested_local_budget_seconds"]) is not int
            or record["requested_local_budget_seconds"] < 1
            or record["requested_local_budget_seconds"] > MAX_ACTIVE_BUDGET_SECONDS
            or binding.get("active_budget_seconds")
            != record["requested_local_budget_seconds"]):
        record["invalid_reasons"].append("invalid_requested_local_budget")
    return record, observation


def _comparison(
    by_cell: dict[tuple[str, str], list[dict[str, Any]]],
    cells: tuple[tuple[str, str], ...], scope: str, field: str,
    value: Callable[[dict[str, Any]], Any],
) -> dict[str, Any]:
    values: dict[str, Any] = {}
    missing: list[str] = []
    duplicates: list[str] = []
    for cell in cells:
        label = _label(cell)
        entries = by_cell[cell]
        if len(entries) > 1:
            duplicates.append(label)
        if len(entries) != 1:
            missing.append(label)
            continue
        item = value(entries[0])
        values[label] = item
        if item is None:
            missing.append(label)
    distinct = {json.dumps(item, sort_keys=True) for item in values.values() if item is not None}
    status = ("mismatch" if len(distinct) > 1 else
              "match" if not missing and not duplicates and len(distinct) == 1 else
              "insufficient_data")
    return {
        "scope": scope, "field": field, "status": status,
        "values_by_cell": values,
        "missing_or_unavailable_cells": missing,
        "duplicate_cells": duplicates,
    }


def audit_development_triplet(
    run_dirs: list[Path | str], expected_plan_sha256: str,
) -> dict[str, Any]:
    """Combine byte-checked observations without upgrading their evidence."""
    if not _sha256(expected_plan_sha256):
        raise ValueError("expected plan SHA-256 must be 64 lowercase hexadecimal characters")
    if len(run_dirs) > len(CELLS):
        raise ValueError("at most six run directories may be audited")

    runs: list[dict[str, Any]] = []
    observations: list[dict[str, Any] | None] = []
    for index, supplied in enumerate(run_dirs):
        path = Path(supplied).absolute()
        record, observed = _record(path, index)
        runs.append(record)
        observations.append(observed)

    for record, observed in zip(runs, observations, strict=True):
        if observed is None:
            continue
        binding = observed.get("pilot_triplet_binding")
        if type(binding) is not dict:
            continue
        if binding.get("plan_sha256") != expected_plan_sha256:
            record["invalid_reasons"].append("plan_sha256_differs_from_expected")

    by_cell: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    dossier_hashes: set[str] = set()
    record_hashes: dict[str, list[int]] = defaultdict(list)
    for record, observed in zip(runs, observations, strict=True):
        if _sha256(record["run_json_sha256"]):
            record_hashes[record["run_json_sha256"]].append(record["input_index"])
        if record["invalid_reasons"] or observed is None:
            continue
        assert record["cell"] is not None
        cell = record["cell"]
        by_cell[(cell["family_slot"], cell["arm"])].append(record)
        binding = observed["pilot_triplet_binding"]
        dossier_hashes.add(binding["activation_dossier_sha256"])

    cells = []
    for cell in CELLS:
        entries = by_cell[cell]
        single = entries[0] if len(entries) == 1 else None
        cells.append({
            "family_slot": cell[0], "arm": cell[1],
            "run_indexes": [item["input_index"] for item in entries],
            "execution_status": single["execution_status"] if single else None,
            "local_usage": single["local_usage"] if single else None,
        })

    checks = []
    for name in COMMON_INPUT_NAMES:
        checks.append(_comparison(
            by_cell, CELLS, "all_cells", name,
            lambda item, key=name: item["verified_input_sha256"][key],
        ))
    for arm in ("N", "S", "T"):
        arm_cells = (("A", arm), ("B", arm))
        for name in ARM_INPUT_NAMES:
            checks.append(_comparison(
                by_cell, arm_cells, f"arm_{arm}", name,
                lambda item, key=name: item["verified_input_sha256"][key],
            ))
    for family in ("A", "B"):
        family_cells = tuple((family, arm) for arm in ("N", "S", "T"))
        for field in (
            "requested_provider_cli", "requested_model", "requested_effort",
            "requested_tool_policy",
        ):
            checks.append(_comparison(
                by_cell, family_cells, f"family_{family}", field,
                lambda item, key=field: item[key],
            ))
    checks.append(_comparison(
        by_cell, CELLS, "all_cells", "activation_dossier_sha256",
        lambda item: item["activation_dossier_sha256"],
    ))
    checks.append(_comparison(
        by_cell, CELLS, "all_cells", "requested_local_budget_seconds",
        lambda item: item["requested_local_budget_seconds"],
    ))

    missing_cells = [_label(cell) for cell in CELLS if not by_cell[cell]]
    duplicate_cells = [_label(cell) for cell in CELLS if len(by_cell[cell]) > 1]
    duplicate_run_records = [indexes for indexes in record_hashes.values() if len(indexes) > 1]
    invalid_indexes = [item["input_index"] for item in runs if item["invalid_reasons"]]
    invalid_cells = [
        {
            "run_index": item["input_index"],
            "cell": (_label((item["cell"]["family_slot"], item["cell"]["arm"]))
                     if item["cell"] is not None else None),
            "reasons": item["invalid_reasons"],
        }
        for item in runs if item["invalid_reasons"]
    ]
    six_unique_cells_present = (
        len(runs) == len(CELLS) and not missing_cells and not duplicate_cells
        and not invalid_indexes and not duplicate_run_records
        and len(dossier_hashes) == 1
    )
    completed = (six_unique_cells_present
                 and all(cell["execution_status"] in SUCCESS_STATUSES for cell in cells)
                 and all(cell["local_usage"] is not None for cell in cells)
                 and all(check["status"] == "match" for check in checks))
    return {
        "schema": 1,
        "classification": "development_six_cell_local_audit_unsealed",
        "expected_plan_sha256": expected_plan_sha256,
        "provided_run_count": len(runs),
        "activation_dossier_sha256": next(iter(dossier_hashes)) if len(dossier_hashes) == 1 else None,
        "activation_dossier_sha256s": sorted(dossier_hashes),
        "runs": runs,
        "cells": cells,
        "missing_cells": missing_cells,
        "duplicate_cells": duplicate_cells,
        "invalid_cells": invalid_cells,
        "duplicate_run_record_indexes": duplicate_run_records,
        "invalid_run_indexes": invalid_indexes,
        "comparability_checks": checks,
        "six_unique_cells_present": six_unique_cells_present,
        "six_cell_recorded_local_completion": completed,
        "six_cell_recorded_local_completion_scope": (
            "recorded artifacts and complete local usage ready for inspection only"
        ),
        "signed_toolkit_workflow_verified": False,
        "effective_tool_parity_proven": False,
        "authenticated_tokens": None,
        "authenticated_cost_usd": None,
        "controlled_comparison_eligible": False,
        "criterion_4": "not_assessed",
        "limitations": [
            "All inputs and telemetry are local same-UID records; prelaunch custody and provider identity are not authenticated.",
            "Local completion means only that six byte-checked run records have ready-for-inspection artifacts, complete local usage and matching requested inputs/configuration.",
            "T's local signed_policy value and event count do not verify Ed25519 signatures, approval authority or a complete signed toolkit workflow.",
            "The common task, packet and prompt hashes are compared where observed; assembled prompts are compared between families within each arm because arms intentionally differ.",
            "The budget is a requested local wall-time limit for one invocation, not an authenticated shared token, tool, agent or retry cap.",
            "Six recorded folders, even when locally complete, do not establish an independent controlled comparison or criterion 4.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-plan-sha256", required=True)
    parser.add_argument("run_dirs", nargs="*", type=Path)
    args = parser.parse_args(argv)
    try:
        report = audit_development_triplet(args.run_dirs, args.expected_plan_sha256)
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if report["six_cell_recorded_local_completion"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
