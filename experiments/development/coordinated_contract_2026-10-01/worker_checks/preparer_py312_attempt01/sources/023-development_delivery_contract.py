"""Public DEV delivery structure checks; never execute, score or approve a case."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
from typing import Any


DELIVERY_SCHEMA = "specorganon.development_delivery_contract.v1"
RUBRIC_SCHEMA = "specorganon.development_public_rubric.v1"
TASK_PINS = {
    "D-F": "ab73075db2b4ee8c5e58dfc873ef14b75276dbcc0ba7afc9685c5b72b72add51",
    "D-E": "f6fed29bc6ce18631cff30710b25f30b9662e04f889f336cccda2869f0789b64",
}
QUANTITY_FIELDS = {
    "milling": ["wheat_input", "refined_flour", "wholemeal_flour", "bran", "total_outputs", "balance_residual"],
    "baking_energy": ["piece_mass", "electricity_per_piece", "gas_per_piece", "electricity_per_kg", "gas_per_kg", "total_per_kg"],
    "survey": ["total_respondents", "known_respondents", "unknown_respondents", "open_category_respondents",
               "closed_category_respondents", "lower_total_slices", "lower_mean_all", "lower_mean_known"],
}
SECTION_FIELDS = {
    "milling": QUANTITY_FIELDS["milling"] + ["mass_fractions", "economic_allocation", "original_electricity_base"],
    "baking_energy": QUANTITY_FIELDS["baking_energy"] + ["conversion"],
    "survey": QUANTITY_FIELDS["survey"] + ["closed_mean_interval", "finite_upper_all", "finite_upper_known", "category_and_missing_rules"],
}
MAX_JSON = 131_072
MAX_SOURCE = 20_000_000
SHA_RE = re.compile(r"[0-9a-f]{64}\Z")


class DeliveryContractError(ValueError):
    """A public contract or local delivery cannot be read safely."""


def canonical(value: Any) -> bytes:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise DeliveryContractError("contract cannot be encoded as finite JSON") from exc


def _clone(value: Any) -> Any:
    return json.loads(canonical(value))


def delivery_contract_template() -> dict:
    artifacts = [
        {"path": "analysis.py", "kind": "python_source", "max_bytes": MAX_JSON, "producer": "participant"},
        {"path": "metrics.json", "kind": "finite_json_object", "max_bytes": MAX_JSON, "producer": "readonly_analysis_host"},
        {"path": "report.md", "kind": "utf8_report", "max_bytes": 65_536, "max_words": 1200, "producer": "participant"},
    ]
    cases = []
    for case_id in TASK_PINS:
        entries = _clone(artifacts)
        if case_id == "D-F":
            entries.append({"path": "sources.json", "kind": "source_claim_map", "max_bytes": MAX_JSON, "producer": "participant"})
        cases.append({"case_id": case_id, "task_sha256": TASK_PINS[case_id], "artifacts": entries,
                      "metrics_sections": ["milling", "baking_energy", "survey", "source_audit"] if case_id == "D-F"
                      else ["intervals", "appliances_weekly", "appliances_daily", "additional_observation", "source_audit"]})
    return {"schema": DELIVERY_SCHEMA, "classification": "public_development_structure_without_reference_answers",
            "cases": cases, "quantity_fields": _clone(QUANTITY_FIELDS), "section_fields": _clone(SECTION_FIELDS),
            "quantity": {"required": ["value", "unit", "base"], "null_requires": "reason", "finite_numbers_only": True},
            "metric_forms": {
                "source_audit": "nonempty list of explicit UTF-8 statements; passage verification remains independent",
                "closed_mean_interval": {"lower": "quantity", "upper": "quantity", "denominator": "quantity"},
                "finite_upper_all_and_known": {"finite": "boolean", "reason": "nonempty text"},
                "original_electricity_base_conversion_category_rules": "nonempty explanatory text",
                "mass_fractions_and_economic_allocation": "separate explicit objects, independently reviewed",
                "intervals": {"count": "nonnegative integer", "continuity_checked": "boolean", "issues": "list of nonempty text"},
                "appliances_weekly": "quantity", "appliances_daily": "nonempty YYYY-MM-DD to quantity object",
                "additional_observation": "nonempty justified observation text"},
            "source_claim": {"schema": 1, "fields": ["id", "claim", "classification", "sources", "unit", "base", "formula", "inputs", "author", "reason"],
                             "classifications": ["reported", "derived", "assumption", "pending"],
                             "source_fields": ["file", "sha256", "locator"], "derived_inputs": "existing_claim_ids"},
            "adaptations": ["D113_common_positional_case_dir_and_JSON_stdout_for_DE",
                            "D118_common_explicit_metric_field_names_and_source_map_schema"],
            "analysis_argv": ["analysis.py", "case_dir"], "report_word_count": "all_unicode_whitespace_separated_tokens",
            "normative_approval": "competent_external_human_only_pending", "checker_executes_participant": False,
            "checker_assigns_Q": False, "semantic_verification": "independent_review_pending"}


def rubric_template() -> dict:
    dimensions = [
        ("formulation", "Scope, actors, concepts, value conflicts and proposed human decisions",
         "No defensible framing or actor/value analysis", "Relevant framing with material omissions or unresolved conflicts",
         "Justified framing and actors, explicit value conflicts, competent decisions identified as pending"),
        ("evidence", "Sources, inference, units, uncertainty and missing data",
         "Unsupported factual claims or uncheckable calculations", "Partly checked evidence with explicit remaining gaps",
         "Independently checkable sources and calculations, justified inference, units and uncertainty, no invented observations"),
        ("intervention", "Substantial alternatives, mechanisms, feasibility and harms",
         "No justified alternative or intervention mechanism", "Two alternatives considered with incomplete feasibility or harm analysis",
         "Substantial alternatives compared with evidence, constraints, affected actors and a refutable recommendation or justified deferral"),
        ("technical", "Reproducibility and technical correctness",
         "Missing or incorrect implementation/calculations", "Reproducible partial result with material limitations",
         "Independent rerun confirms source integrity, required calculations, units and stated limitations"),
        ("validation", "Prospective comparator, outcomes, uncertainty, adverse effects and stopping",
         "No testable validation or false efficacy claim", "Prospective test identifies major elements but leaves material design gaps",
         "Defensible comparator and measurement design, missingness and uncertainty, safeguards and refutation/stopping criteria"),
    ]
    return {"schema": RUBRIC_SCHEMA, "classification": "public_development_rubric_no_reference_answers",
            "delivery_semantic_sha256": hashlib.sha256(canonical(delivery_contract_template())).hexdigest(),
            "dimensions": [{"id": key, "scope": scope, "range": [0, 20], "anchors": {"0": low, "10": mid, "20": high}}
                           for key, scope, low, mid, high in dimensions],
            "aggregation": "sum_five_integer_components_without_compensation_for_critical_errors",
            "critical_errors": ["invented_observation", "false_test_result", "unapproved_normative_commitment",
                                "unjustified_advance", "unfounded_requirement", "safety_harm"],
            "judging": "independent_human_review_pending", "reference_answers_included": False,
            "automated_Q": False, "task_sha256": dict(TASK_PINS),
            "limits": "Public DEV anchors are not reserved references, competent judgments, causal evidence or acceptance."}


def validate_delivery_contract(raw: Any) -> dict:
    if canonical(raw) != canonical(delivery_contract_template()):
        raise DeliveryContractError("delivery contract differs from the fixed public DEV v1 contract")
    return _clone(raw)


def validate_rubric(raw: Any) -> dict:
    if canonical(raw) != canonical(rubric_template()):
        raise DeliveryContractError("rubric differs from the fixed public DEV v1 rubric without answers")
    return _clone(raw)


def _pairs(pairs: list[tuple[str, Any]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise DeliveryContractError("duplicate JSON key")
        result[key] = value
    return result


def _constant(value: str) -> None:
    raise DeliveryContractError("nonfinite JSON constant")


def _float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise DeliveryContractError("overflowing JSON number")
    return parsed


def parse_json(raw: bytes) -> Any:
    try:
        return json.loads(raw, object_pairs_hook=_pairs, parse_constant=_constant, parse_float=_float)
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise DeliveryContractError("invalid strict finite JSON") from exc


def _safe_path(path: Path) -> None:
    path = path.absolute()
    for parent in [*reversed(path.parents), path]:
        if parent.is_symlink():
            raise DeliveryContractError("symlink path is not a delivery/source file")


def _read(path: Path, limit: int) -> bytes:
    _safe_path(path)
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode) or not 0 <= before.st_size <= limit:
                raise DeliveryContractError("file is not bounded regular data")
            raw = stream.read(limit + 1)
            after = os.fstat(stream.fileno())
        fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
        if len(raw) != before.st_size or any(getattr(before, field) != getattr(after, field) for field in fields):
            raise DeliveryContractError("file changed during read")
        return raw
    except OSError as exc:
        raise DeliveryContractError("cannot read regular delivery/source file") from exc


def _text(value: Any) -> bool:
    try:
        return type(value) is str and bool(value.strip()) and len(value.encode("utf-8")) <= MAX_JSON
    except UnicodeError:
        return False


def _quantity(value: Any) -> bool:
    return (type(value) is dict and {"value", "unit", "base"} <= value.keys()
            and _text(value["unit"]) and _text(value["base"])
            and (type(value["value"]) is int
                 or type(value["value"]) is float and math.isfinite(value["value"])
                 or value["value"] is None and _text(value.get("reason"))))


def _source_refs(value: Any, case: Path, known: dict) -> None:
    if type(value) is not list or len(value) > 128:
        raise DeliveryContractError("source refs must be a bounded list")
    for entry in value:
        if (type(entry) is not dict or set(entry) != {"file", "sha256", "locator"}
                or type(entry.get("file")) is not str or entry["file"] not in known or not _text(entry.get("locator"))
                or entry.get("sha256") != known[entry["file"]]):
            raise DeliveryContractError("source ref lacks a listed file, digest or locator")
        body = _read(case / entry["file"], MAX_SOURCE)
        if hashlib.sha256(body).hexdigest() != entry["sha256"]:
            raise DeliveryContractError("cited source bytes differ")


def _claims(raw: Any, case: Path, known: dict, contract: dict) -> None:
    if (type(raw) is not dict or set(raw) != {"schema", "claims"} or type(raw["schema"]) is not int
            or raw["schema"] != 1 or type(raw["claims"]) is not list or not 1 <= len(raw["claims"]) <= 256):
        raise DeliveryContractError("sources.json must contain schema1 and a nonempty bounded claim list")
    nodes = {}
    for entry in raw["claims"]:
        if type(entry) is not dict or set(entry) != set(contract["source_claim"]["fields"]):
            raise DeliveryContractError("source claim fields differ from public schema")
        if any(not _text(entry[key]) for key in ("id", "claim", "unit", "base")) or entry["id"] in nodes:
            raise DeliveryContractError("source claims need unique IDs, text, unit and base")
        kind = entry["classification"]
        if (kind not in contract["source_claim"]["classifications"] or type(entry["inputs"]) is not list
                or len(entry["inputs"]) > 256 or any(not _text(item) for item in entry["inputs"])):
            raise DeliveryContractError("source classification or inputs are invalid")
        _source_refs(entry["sources"], case, known)
        if kind in {"reported", "derived"} and not entry["sources"]:
            raise DeliveryContractError("reported/derived claim lacks source references")
        if kind == "derived" and (not _text(entry["formula"]) or not entry["inputs"]):
            raise DeliveryContractError("derived claim lacks formula or input claim IDs")
        if kind == "assumption" and not _text(entry["author"]):
            raise DeliveryContractError("assumption lacks identified author/proposal")
        if kind == "pending" and not _text(entry["reason"]):
            raise DeliveryContractError("pending claim lacks reason")
        nodes[entry["id"]] = entry["inputs"]
    active, done = set(), set()

    def visit(key: str) -> None:
        if key not in nodes or key in active:
            raise DeliveryContractError("source input IDs are absent or cyclic")
        if key in done:
            return
        active.add(key)
        for dependency in nodes[key]:
            visit(dependency)
        active.remove(key)
        done.add(key)

    for key in nodes:
        visit(key)


def _metrics(raw: Any, case_id: str, specification: dict, contract: dict) -> int:
    if type(raw) is not dict or not set(specification["metrics_sections"]) <= raw.keys():
        raise DeliveryContractError("metrics lack required public sections")
    if case_id == "D-F":
        for section, fields in contract["section_fields"].items():
            if type(raw[section]) is not dict or not set(fields) <= raw[section].keys():
                raise DeliveryContractError("metrics section lacks required field names")
            for name in contract["quantity_fields"][section]:
                if not _quantity(raw[section][name]):
                    raise DeliveryContractError("metric quantity lacks value/unit/base or justified null")
        interval = raw["survey"]["closed_mean_interval"]
        if type(interval) is not dict or set(interval) != {"lower", "upper", "denominator"} or not all(_quantity(value) for value in interval.values()):
            raise DeliveryContractError("closed survey interval needs its explicit quantities and denominator")
        for field in ("finite_upper_all", "finite_upper_known"):
            bound = raw["survey"][field]
            if type(bound) is not dict or set(bound) != {"finite", "reason"} or type(bound["finite"]) is not bool or not _text(bound["reason"]):
                raise DeliveryContractError("upper-bound identification needs boolean and reason")
        for section, field in (("milling", "original_electricity_base"), ("baking_energy", "conversion"), ("survey", "category_and_missing_rules")):
            if not _text(raw[section][field]):
                raise DeliveryContractError("base, conversion and category rules need text")
        for field in ("mass_fractions", "economic_allocation"):
            if type(raw["milling"][field]) is not dict or not raw["milling"][field]:
                raise DeliveryContractError("mass fractions and economic allocation need separate explicit objects")
    else:
        intervals = raw["intervals"]
        if (type(intervals) is not dict or set(intervals) != {"count", "continuity_checked", "issues"}
                or type(intervals["count"]) is not int or intervals["count"] < 0
                or type(intervals["continuity_checked"]) is not bool or type(intervals["issues"]) is not list
                or any(not _text(issue) for issue in intervals["issues"])):
            raise DeliveryContractError("intervals need a nonnegative count, check flag and issue list")
        if (not _quantity(raw["appliances_weekly"]) or type(raw["appliances_daily"]) is not dict
                or not raw["appliances_daily"] or any(not re.fullmatch(r"\d{4}-\d{2}-\d{2}", key)
                    or not _quantity(value) for key, value in raw["appliances_daily"].items())
                or not _text(raw["additional_observation"])):
            raise DeliveryContractError("energy metrics need weekly/daily quantities and an additional observation")
    if type(raw["source_audit"]) is not list or not raw["source_audit"] or any(not _text(item) for item in raw["source_audit"]):
        raise DeliveryContractError("source audit needs explicit statements, not a hash-only success flag")

    def count_null(value: Any) -> int:
        if type(value) is dict:
            own = int("value" in value and value["value"] is None)
            return own + sum(count_null(item) for item in value.values())
        return sum(count_null(item) for item in value) if type(value) is list else 0

    return count_null(raw)


def check_delivery(case_dir: Path, work_dir: Path, contract: Any) -> dict:
    contract = validate_delivery_contract(contract)
    case, work = Path(case_dir).absolute(), Path(work_dir).absolute()
    _safe_path(case)
    _safe_path(work)
    if not case.is_dir() or not work.is_dir():
        raise DeliveryContractError("case and work must be separate regular directories")
    case, work = case.resolve(strict=True), work.resolve(strict=True)
    if case == work or case in work.parents or work in case.parents:
        raise DeliveryContractError("case and work must be separate regular directories")
    metadata = parse_json(_read(case / "case.json", MAX_JSON))
    if type(metadata) is not dict or type(metadata.get("case_id")) is not str or metadata["case_id"] not in TASK_PINS:
        raise DeliveryContractError("only public D-F/D-E cases are supported")
    case_id = metadata["case_id"]
    specification = next(item for item in contract["cases"] if item["case_id"] == case_id)
    task = _read(case / "task.md", MAX_JSON)
    if hashlib.sha256(task).hexdigest() != specification["task_sha256"]:
        raise DeliveryContractError("task bytes differ from the public contract")
    if type(metadata.get("files")) is not list or not 1 <= len(metadata["files"]) <= 64:
        raise DeliveryContractError("case source inventory must be bounded and nonempty")
    known = {}
    for entry in metadata["files"]:
        if (type(entry) is not dict or set(entry) != {"path", "sha256", "bytes"}
                or type(entry["path"]) is not str or re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", entry["path"]) is None
                or entry["path"] in {"", ".", ".."} or entry["path"] in known
                or type(entry["sha256"]) is not str or SHA_RE.fullmatch(entry["sha256"]) is None
                or type(entry["bytes"]) is not int or not 0 <= entry["bytes"] <= MAX_SOURCE):
            raise DeliveryContractError("source inventory contains an unsafe, duplicate or invalid entry")
        body = _read(case / entry["path"], MAX_SOURCE)
        if len(body) != entry["bytes"] or hashlib.sha256(body).hexdigest() != entry["sha256"]:
            raise DeliveryContractError("case source inventory bytes differ")
        known[entry["path"]] = entry["sha256"]
    issues, pins, unresolved = [], [], 0
    for artifact in specification["artifacts"]:
        name = artifact["path"]
        try:
            body = _read(work / name, artifact["max_bytes"])
            pins.append({"path": name, "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest()})
            if artifact["kind"] == "python_source":
                ast.parse(body.decode("utf-8"))
            elif artifact["kind"] == "utf8_report":
                text = body.decode("utf-8")
                if not text.strip() or len(text.split()) > artifact["max_words"]:
                    raise DeliveryContractError("report empty or exceeds 1200 words")
            elif name == "sources.json":
                _claims(parse_json(body), case, known, contract)
            else:
                unresolved = _metrics(parse_json(body), case_id, specification, contract)
        except (DeliveryContractError, UnicodeError, SyntaxError, RecursionError) as exc:
            issues.append({"artifact": name, "reason": str(exc)})
    for entry in metadata["files"]:
        body = _read(case / entry["path"], MAX_SOURCE)
        if len(body) != entry["bytes"] or hashlib.sha256(body).hexdigest() != entry["sha256"]:
            raise DeliveryContractError("case source changed during delivery check")
    return {"schema": 1, "classification": "local_delivery_structure_not_quality_or_acceptance",
            "case_task_sha256": hashlib.sha256(task).hexdigest(),
            "case_source_inventory_sha256": hashlib.sha256(canonical(metadata["files"])).hexdigest(),
            "case_id": case_id, "structural_checks_passed": not issues, "issues": issues,
            "artifacts": pins, "unresolved_quantity_fields": unresolved, "participant_executed": False,
            "metric_generation_authenticated": False, "semantic_completeness_assessed": False,
            "source_passages_verified": False, "quality_assessed": False, "normative_approval": False,
            "formal_cell_executed": False, "causal_impact_assessed": False}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate")
    validate.add_argument("contract", type=Path)
    validate.add_argument("--rubric", type=Path)
    check = sub.add_parser("check")
    check.add_argument("contract", type=Path)
    check.add_argument("case_dir", type=Path)
    check.add_argument("work_dir", type=Path)
    args = parser.parse_args(argv)
    try:
        contract = validate_delivery_contract(parse_json(_read(args.contract, MAX_JSON)))
        if args.command == "validate":
            if args.rubric is not None:
                validate_rubric(parse_json(_read(args.rubric, MAX_JSON)))
            result = {"schema": 1, "public_contract_valid": True, "quality_assessed": False, "execution_authorized": False}
        else:
            result = check_delivery(args.case_dir, args.work_dir, contract)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, allow_nan=False))
        return 0 if result.get("structural_checks_passed", True) else 1
    except (DeliveryContractError, OSError) as exc:
        print(f"invalid delivery contract: {exc}", file=__import__("sys").stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
