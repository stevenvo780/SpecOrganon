"""Check public development metrics independently; never execute participant code.

This prospective content contract uses D094 B metric names and units for bread
and D099 T names for building energy. It checks arithmetic and documentary
consistency, not normative approval, field efficacy, report quality or Q.
Execution/script provenance must be bound separately by the analysis supervisor.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import json
import math
import re
from decimal import Decimal
from pathlib import Path
from typing import Any

from development_analysis_inputs import (
    AnalysisInputsError, DOCUMENTS, ROOT, canonical, read_pinned, verify_text_inputs,
)


CLASSIFICATION = "independent_development_analysis_content_check_not_Q"
ABS_TOLERANCE = Decimal("1e-12")
REL_TOLERANCE = Decimal("1e-12")
CONTRACT = "experiments/development/bread_source_audit_2026-09-30/contract.json"
CONTRACT_SHA256 = "0c92095962c5078d4a9af5e49c47a480f1bad5f588b7ec53899cd680cc2d1a5b"
SOURCE_PINS = {
    "D-F": {
        "task.md": ("ab73075db2b4ee8c5e58dfc873ef14b75276dbcc0ba7afc9685c5b72b72add51", 6_887),
        "source_manifest.json": ("83bdf5e7bc584971ca2446cf0fe6bd83dd4b9ea624a433fc54c5e5b3f89c4f3a", 6_281),
        "source_claims.json": ("63ce5419981c0a3f7d7ba83218cac2dbb528f061b313cfdf4655400ac2e86abc", 9_162),
        "survey_table1.json": ("50361b4803226a6a387fb39f0289c0e708679f348b5081ccb0034242155a064f", 1_440),
        **{f"{name}.pdf": (info["pdf_sha256"], info["pdf_bytes"]) for name, info in DOCUMENTS.items()},
    },
    "D-E": {
        "task.md": ("f6fed29bc6ce18631cff30710b25f30b9662e04f889f336cccda2869f0789b64", 3_166),
        "source_manifest.json": ("0e18340d130c495201e68c1c869bc2c6f49b35663176040aebb0d0d7d7bd1ee1", 1_874),
        "sample_first_complete_week.csv": ("c7f66ffaadc4e38375a7edf03091bae4fc861880510867903487eec83f05e6ba", 612_074),
    },
}


class VerificationError(ValueError):
    """Trusted inputs or documentary relationships are inconsistent."""


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise VerificationError("duplicate JSON key")
        result[key] = value
    return result


def _constant(value):
    raise VerificationError(f"non-JSON numeric constant: {value}")


def _json(raw: bytes) -> dict:
    result = json.loads(raw, object_pairs_hook=_pairs, parse_constant=_constant)
    if type(result) is not dict:
        raise VerificationError("JSON input must be an object")
    return result


def _number(value: Any) -> Decimal:
    if type(value) not in (int, float) or (type(value) is float and not math.isfinite(value)):
        raise VerificationError("metric must be a finite JSON number, not bool or text")
    result = Decimal(str(value))
    if not result.is_finite():
        raise VerificationError("metric is not finite")
    return result


def _finite_tree(value: Any) -> None:
    if type(value) is dict:
        for key, item in value.items():
            if type(key) is not str:
                raise VerificationError("metric object keys must be strings")
            _finite_tree(item)
    elif type(value) is list:
        for item in value:
            _finite_tree(item)
    elif type(value) is float:
        _number(value)
    elif value is not None and type(value) not in (int, str, bool):
        raise VerificationError("metrics contain a non-JSON type")


def _normal(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


class _Checks:
    def __init__(self, metrics: dict):
        self.metrics = metrics
        self.rows: list[dict] = []
        self.diagnostics: list[dict] = []

    def check(self, path: str, condition: bool, code: str, message: str) -> None:
        self.rows.append({"path": path, "passed": bool(condition)})
        if not condition:
            self.diagnostics.append({"path": path, "code": code, "message": message})

    def get(self, path: str) -> Any:
        value = self.metrics
        for key in path.split("."):
            if type(value) is not dict or key not in value:
                self.check(path, False, "missing_metric", "required metric is missing")
                return None
            value = value[key]
        return value

    def number(self, path: str, value: Any, expected: Decimal | int) -> None:
        try:
            actual = _number(value)
            target = Decimal(expected)
            agrees = abs(actual - target) <= max(ABS_TOLERANCE, REL_TOLERANCE * abs(target))
        except (VerificationError, ArithmeticError):
            agrees = False
        self.check(path, agrees, "quantity_mismatch", "finite quantity differs from independent source calculation")

    def quantity(self, path: str, expected: Decimal | int | None, unit: str, base: str) -> None:
        item = self.get(path)
        if type(item) is not dict or not {"value", "unit", "base"} <= item.keys():
            self.check(path, False, "quantity_shape", "quantity must contain value, unit and base")
            return
        self.check(path + ".unit", type(item["unit"]) is str and item["unit"] == unit,
                   "unit_mismatch", "unit differs from the declared prospective metric contract")
        self.check(path + ".base", type(item["base"]) is str and _normal(item["base"]) == _normal(base),
                   "base_mismatch", "base differs from the declared prospective metric contract")
        if expected is None:
            self.check(path + ".value", item["value"] is None and type(item.get("reason")) is str
                       and bool(item["reason"].strip()), "unknown_quantity", "unidentified quantity requires null and reason")
        else:
            self.number(path + ".value", item["value"], expected)


def _energy(checks: _Checks, raw: dict[str, bytes], pins: dict[str, str]) -> None:
    manifest = _json(raw["source_manifest.json"])
    selection = manifest["selection"]
    reader = csv.DictReader(io.StringIO(raw["sample_first_complete_week.csv"].decode("utf-8-sig")))
    if reader.fieldnames != selection["columns"]:
        raise VerificationError("CSV headers differ from pinned selection")
    rows = list(reader)
    times = [dt.datetime.strptime(row["date"], "%Y-%m-%d %H:%M:%S") for row in rows]
    interval = dt.timedelta(minutes=selection["interval_minutes"])
    if (len(rows) != selection["rows"] or not rows
            or times[0] != dt.datetime.fromisoformat(selection["start_inclusive"])
            or times[-1] + interval != dt.datetime.fromisoformat(selection["end_exclusive"])
            or any(b - a != interval for a, b in zip(times, times[1:]))):
        raise VerificationError("CSV count, bounds or continuity differ from pinned selection")
    daily: dict[str, Decimal] = {}
    appliances = lights = Decimal(0)
    for timestamp, row in zip(times, rows, strict=True):
        a, light = Decimal(row["Appliances"]), Decimal(row["lights"])
        if not a.is_finite() or not light.is_finite() or a < 0 or light < 0:
            raise VerificationError("CSV contains invalid energy")
        appliances += a
        lights += light
        day = timestamp.date().isoformat()
        daily[day] = daily.get(day, Decimal(0)) + a / 1000
    for name, expected in (("rows", len(rows)), ("interval_minutes", selection["interval_minutes"])):
        value = checks.get(name)
        checks.check(name, type(value) is int and value == expected, "count_mismatch", "count/interval must exactly match source")
    for name, expected in (("first_timestamp", times[0].isoformat(" ")),
                           ("last_timestamp", times[-1].isoformat(" ")),
                           ("sample_sha256", pins["sample_first_complete_week.csv"]),
                           ("manifest_sha256", pins["source_manifest.json"])):
        value = checks.get(name)
        checks.check(name, type(value) is str and value == expected, "source_binding", "metric source identity or timestamp differs")
    checks.check("continuous", checks.get("continuous") is True, "continuity", "continuous must be true for the verified source")
    checks.number("appliances_total_kwh", checks.get("appliances_total_kwh"), appliances / 1000)
    checks.number("lights_total_kwh", checks.get("lights_total_kwh"), lights / 1000)
    actual_daily = checks.get("daily_appliances_kwh")
    checks.check("daily_appliances_kwh", type(actual_daily) is dict and set(actual_daily) == set(daily),
                 "daily_domain", "daily totals must contain exactly the seven source dates")
    if type(actual_daily) is dict:
        for day, expected in daily.items():
            checks.number(f"daily_appliances_kwh.{day}", actual_daily.get(day), expected)
    for name in ("appliances_total_kwh", "lights_total_kwh", "daily_appliances_kwh"):
        checks.check("units." + name, checks.get("units." + name) == "kWh", "unit_mismatch", "energy totals must be in kWh")


def _passages(case_dir: Path, claims: dict, table: dict) -> tuple[dict, dict]:
    """Apply the existing pinned D100 selectors to common text snapshots.

    This uses the reviewed selector/unit/base contract, not a numeric answer
    table. Only whitespace is normalized; values come from the pinned texts.
    """
    contract = _json(read_pinned(ROOT / CONTRACT, CONTRACT_SHA256))
    if (canonical(claims["sources"]) != canonical(contract["sources"])
            or canonical({key: claims[key] for key in contract["claim_document_metadata"]})
            != canonical(contract["claim_document_metadata"])):
        raise VerificationError("claim source/metadata differ from reviewed contract")
    documents = {
        source: read_pinned(case_dir / identity["visible_file"].replace(".pdf", ".txt"),
                            DOCUMENTS[f"source_{source}"]["text_sha256"],
                            DOCUMENTS[f"source_{source}"]["text_bytes"]).decode("utf-8").split("\f")
        for source, identity in contract["sources"].items()
    }
    passages = {}
    for name, selector in contract["selectors"].items():
        page = selector["page"]
        content = documents[selector["source"]][page - 1]
        if re.search(rf"\b{page} of \d+\b", content.splitlines()[0]) is None:
            raise VerificationError("printed and physical page differ")
        text = _normal(content)
        start, end = _normal(selector["start"]), _normal(selector["end"])
        if text.count(start) != 1 or text.count(end) != 1:
            raise VerificationError(f"passage locator missing or ambiguous: {name}")
        tail = text.split(start, 1)[1]
        if tail.count(end) != 1:
            raise VerificationError(f"passage end missing or ambiguous: {name}")
        passage = start + " " + tail.split(end, 1)[0].strip()
        if any(_normal(context) not in passage for context in selector["required"]):
            raise VerificationError(f"passage context missing: {name}")
        matches = list(re.finditer(selector["pattern"], passage))
        if len(matches) != 1 or not matches[0].groupdict() or any(value is None for value in matches[0].groupdict().values()):
            raise VerificationError(f"quantity passage missing or ambiguous: {name}")
        passages[name] = {"text": passage, "groups": matches[0].groupdict()}
    indexed = {item["key"]: item for item in claims["claims"]}
    if len(indexed) != len(claims["claims"]) or set(indexed) != set(contract["claims"]):
        raise VerificationError("claim set differs from reviewed contract")
    for key, binding in contract["claims"].items():
        claim = indexed[key]
        if canonical({field: claim[field] for field in binding["metadata"]}) != canonical(binding["metadata"]):
            raise VerificationError(f"claim unit/base/locator differs: {key}")
        if _number(claim["value"]) != Decimal(passages[binding["selector"]]["groups"][binding["group"]]):
            raise VerificationError(f"claim quantity differs from passage: {key}")
    expected_rows = contract["survey_categories"]
    if len(table["categories"]) != len(expected_rows):
        raise VerificationError("survey category set differs")
    for row, expected in zip(table["categories"], expected_rows, strict=True):
        if canonical({key: row[key] for key in expected}) != canonical(expected):
            raise VerificationError("survey category boundaries differ")
        groups = passages["survey_" + row["key"]]["groups"]
        if row["count"] != int(groups["count"]) or row["reported_percent"] != groups["percent"]:
            raise VerificationError("survey counts/percentages differ from passage")
    return contract, passages


def _bread_audit(checks: _Checks, claims: dict, table: dict, contract: dict, passages: dict) -> None:
    audit = checks.get("source_audit")
    if type(audit) is not dict:
        checks.check("source_audit", False, "source_audit", "source audit must be an object")
        return
    entries = audit.get("quantities")
    indexed = {item.get("key"): item for item in entries if type(item) is dict and type(item.get("key")) is str} if type(entries) is list else {}
    expected = {item["key"]: item for item in claims["claims"]}
    complete = type(entries) is list and len(entries) == len(indexed) == len(expected) and set(indexed) == set(expected)
    checks.check("source_audit.quantities", complete, "source_audit", "all 17 quantitative claims require unique audit entries")
    checks.check("source_audit.quantities_audited", type(audit.get("quantities_audited")) is int
                 and audit["quantities_audited"] == len(expected), "source_audit", "audit count differs")
    for key, claim in expected.items():
        item = indexed.get(key, {})
        identity = claims["sources"][claim["source"]]
        binding = contract["claims"][key]
        passage = passages[binding["selector"]]
        path = "source_audit.quantities." + key
        for field, expected_value in (("unit", claim["unit"]), ("base", claim["base"]),
                                      ("locator", claim["locator"]), ("file", identity["visible_file"]),
                                      ("sha256", identity["sha256"]), ("provenance", claim["provenance"])):
            checks.check(path + "." + field, canonical(item.get(field)) == canonical(expected_value),
                         "source_audit", "audit metadata differs from independently reviewed source")
        checks.number(path + ".reported_value", item.get("reported_value"), _number(claim["value"]))
        checks.number(path + ".observed_value", item.get("observed_value"), Decimal(passage["groups"][binding["group"]]))
        matched = item.get("matched_passage")
        checks.check(path + ".matched_passage", type(matched) is str and bool(matched.strip())
                     and _normal(matched) in passage["text"], "source_audit", "claimed match is absent from independently located passage")
    rows = audit.get("survey_rows")
    indexed_rows = {item.get("key"): item for item in rows if type(item) is dict and type(item.get("key")) is str} if type(rows) is list else {}
    checks.check("source_audit.survey_rows", type(rows) is list and len(rows) == len(indexed_rows) == len(table["categories"])
                 and set(indexed_rows) == {row["key"] for row in table["categories"]},
                 "source_audit", "all seven survey rows require independent passage audit")
    for row in table["categories"]:
        item = indexed_rows.get(row["key"], {})
        groups = passages["survey_" + row["key"]]["groups"]
        expected_match = _normal(f"{row['label']} {groups['count']} {groups['percent']}")
        matched = item.get("matched_passage")
        checks.check("source_audit.survey_rows." + row["key"], type(matched) is str and _normal(matched) == expected_match
                     and canonical(item.get("locator")) == canonical({"pdf_page": 4, "table": "1", "row": row["label"]}),
                     "source_audit", "survey citation, label, count or percentage differs")
    discrepancies = audit.get("discrepancies")
    required = {"file": "source_survey.pdf", "prose_locator": {"pdf_page": 3, "section": "3"},
                "table_locator": {"pdf_page": 4, "table": "1"},
                "prose_intervals": ["0", "1–3", "4–6", "7–10", ">10"],
                "table_intervals": ["0", "1–3", "4–6", "7–9", "10–12", ">12", "unknown"]}
    checks.check("source_audit.discrepancies", type(discrepancies) is list and any(
        type(item) is dict and all(canonical(item.get(key)) == canonical(value) for key, value in required.items())
        for item in discrepancies), "source_audit", "survey prose/table disagreement must remain explicit")


def _bread(checks: _Checks, raw: dict[str, bytes], case_dir: Path) -> None:
    claims, table = _json(raw["source_claims.json"]), _json(raw["survey_table1.json"])
    contract, passages = _passages(case_dir, claims, table)
    values = {item["key"]: _number(item["value"]) for item in claims["claims"]}
    indexed = {item["key"]: item for item in claims["claims"]}
    products = ("refined_flour", "whole_flour", "bran")
    checks.quantity("milling.wheat_input", 1000, "kg", "normalized 1 t wheat entering mill; analyst-selected base")
    masses = {product: 1000 * values[f"wheat_{product}_mass_share"] / 100 for product in products}
    for product in products:
        checks.quantity(f"milling.outputs.{product}", masses[product], "kg", "normalized 1 t wheat input")
        checks.quantity(f"milling.mass_fractions.{product}", values[f"wheat_{product}_mass_share"] / 100,
                        "kg/kg_wheat", "physical output fraction of wheat input")
        checks.quantity(f"milling.economic_allocation_factors.{product}", values[f"wheat_{product}_economic_allocation"] / 100,
                        "share", "economic allocation of milling inventory; not physical loss or market price")
    checks.quantity("milling.sum_outputs", sum(masses.values()), "kg", "normalized 1 t wheat input")
    checks.quantity("milling.balance_residual", 1000 - sum(masses.values()), "kg", "input minus reported output fractions; rounding-level accounting")
    checks.quantity("milling.electricity_original", values["mill_electricity"], "kWh/t_flour", indexed["mill_electricity"]["base"])
    checks.quantity("milling.electricity_per_t_wheat", None, "kWh/t_wheat", "normalized wheat input")
    loaf = values["piece_mass"] / 1000
    electricity, gas = values["bakery_electricity"], values["bakery_natural_gas"]
    checks.quantity("baking_energy.piece_mass_original", values["piece_mass"], "g/piece", indexed["piece_mass"]["base"])
    checks.quantity("baking_energy.piece_mass", loaf, "kg/piece", "commercial loaf after baking")
    for name, key in (("electricity", "bakery_electricity"), ("natural_gas", "bakery_natural_gas")):
        checks.quantity(f"baking_energy.{name}_per_piece", values[key], "kWh/piece", indexed[key]["base"])
        checks.quantity(f"baking_energy.{name}_per_kg", values[key] / loaf, "kWh/kg_bread", "mass of studied bread after baking")
    checks.quantity("baking_energy.sum_per_piece", electricity + gas, "kWh/piece", "sum of reported energy carriers; not primary energy or GHG")
    checks.quantity("baking_energy.sum_per_kg", (electricity + gas) / loaf, "kWh/kg_bread", "sum of reported energy carriers for studied bread")
    rows = table["categories"]
    total = table["reported_total"]
    unknown = next(row["count"] for row in rows if row["key"] == "do_not_know")
    open_count = next(row["count"] for row in rows if row["key"] == "more_than_twelve")
    closed_rows = [row for row in rows if row["max_slices"] is not None]
    closed_count = sum(row["count"] for row in closed_rows)
    known = total - unknown
    lower = sum(row["count"] * row["min_slices"] for row in rows if row["min_slices"] is not None)
    count_bases = {"total": "Table 1 total", "known": "Table 1 except Do not know", "unknown": "Table 1 Do not know",
                   "open_category": "Table 1 More than 12 slices", "closed_category": "Table 1 zero through 10–12"}
    for name, value in (("total", total), ("known", known), ("unknown", unknown), ("open_category", open_count), ("closed_category", closed_count)):
        checks.quantity(f"survey.{name}_respondents", value, "respondents", count_bases[name])
    for group, denominator, base in (
        ("all", total, "1000 surveyed respondents; household weekly discard, including unknown responses"),
        ("known", known, "967 respondents choosing a known category; household weekly discard"),
    ):
        checks.quantity(f"survey.lower_total_{group}", lower, "slices/week", base)
        checks.quantity(f"survey.lower_mean_{group}", Decimal(lower) / denominator, "slices/(respondent_household*week)", base)
        checks.check(f"survey.finite_upper_bound_{group}", checks.get(f"survey.finite_upper_bound_{group}") is False,
                     "unbounded_category", "open/unknown quantities do not provide a finite upper bound")
        checks.quantity(f"survey.upper_total_{group}", None, "slices/week", base)
        checks.quantity(f"survey.upper_mean_{group}", None, "slices/(respondent_household*week)", base)
    closed_base = "948 respondents in closed Table 1 categories; household weekly discard"
    for bound, field in (("lower", "min_slices"), ("upper", "max_slices")):
        bound_total = sum(row["count"] * row[field] for row in closed_rows)
        checks.quantity(f"survey.closed_total_interval.{bound}", bound_total, "slices/week", closed_base)
        checks.quantity(f"survey.closed_mean_interval.{bound}", Decimal(bound_total) / closed_count,
                        "slices/(respondent_household*week)", closed_base)
    _bread_audit(checks, claims, table, contract, passages)


def evaluate(case_id: str, metrics: dict, case_dir: Path) -> dict[str, Any]:
    """Return content diagnostics; source failures cannot yield passed=True."""
    result = {"passed": False, "classification": CLASSIFICATION, "diagnostics": [], "checks": [],
              "source_pins": {}, "numeric_tolerance": {"relative": str(REL_TOLERANCE), "absolute": str(ABS_TOLERANCE)},
              "scope": "source-bound arithmetic and documentary consistency; execution provenance is checked separately"}
    checks = _Checks(metrics)
    try:
        if type(case_id) is not str or case_id not in SOURCE_PINS or type(metrics) is not dict:
            raise VerificationError("only D-F/D-E metric objects are supported")
        _finite_tree(metrics)
        case_dir = Path(case_dir)
        raw = {name: read_pinned(case_dir / name, digest, size) for name, (digest, size) in SOURCE_PINS[case_id].items()}
        result["source_pins"] = {name: digest for name, (digest, _) in SOURCE_PINS[case_id].items()}
        if case_id == "D-F":
            result["source_pins"].update(verify_text_inputs(case_dir))
            result["source_pins"]["reviewed_passage_contract"] = CONTRACT_SHA256
            _bread(checks, raw, case_dir)
        else:
            _energy(checks, raw, result["source_pins"])
        # Re-read after all calculations, including each derived text artifact.
        for name, (digest, size) in SOURCE_PINS[case_id].items():
            read_pinned(case_dir / name, digest, size)
        if case_id == "D-F":
            verify_text_inputs(case_dir)
            read_pinned(ROOT / CONTRACT, CONTRACT_SHA256)
    except (AnalysisInputsError, VerificationError, OSError, UnicodeError, json.JSONDecodeError,
            KeyError, IndexError, TypeError, ArithmeticError, RecursionError, ValueError) as exc:
        checks.diagnostics.append({"path": "inputs_or_metrics", "code": "verification_failed", "message": str(exc)})
    result["checks"], result["diagnostics"] = checks.rows, checks.diagnostics
    result["passed"] = not checks.diagnostics
    return result
