"""Reproduce the predeclared descriptive school-meal waste analysis.

Usage: ``python3 scripts/analyze_school_waste.py [--input XLSX] [--output JSON]``.
Only Python's standard library is needed. The script reads the named OOXML
worksheet's first eight columns and uses cached spreadsheet values only to
audit calculated columns. The source SHA-256 is pinned to the prior plan.
Output decimal strings have six places, rounded half-even; calculations use
50-place Decimal arithmetic before output rounding. This is development
evidence, not a causal test or a test of the food-chain intervention.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import posixpath
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN, localcontext
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET
from zipfile import BadZipFile, ZipFile


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "cases/school_waste/source.xlsx"
DEFAULT_OUTPUT = ROOT / "experiments/development/school_waste_2026-09-26.json"
PLAN = ROOT / "docs/plan_escuela_residuos.md"
SOURCE_SHA256 = "2ffad746b7ed5d536a0c99c37d8e249230d95d5fb2d041d85d01b69499f99624"
PLAN_SHA256 = "49ce977aebb5fa6ddbd26bc008b9ffa4e094a4d81e4fe5f4785ee3e3895e9f66"
SHEET = "food waste school meals 2024-25"
HEADERS = ("DATE", "MENU", "KSW kg", "PW kg", "PW g", "DINERS", "PW/g/diner", "KSW/g/diner")
NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
DOC_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
WORKSHEET_REL = f"{DOC_REL_NS}/worksheet"
CELL_REF = re.compile(r"([A-Z]+)([1-9][0-9]*)\Z")
SIX = Decimal("0.000001")
TOLERANCE = Decimal("0.000001")


class SchoolWasteError(ValueError):
    """The workbook does not satisfy the fixed analysis contract."""


@dataclass(frozen=True)
class Cell:
    value: str
    kind: str


@dataclass(frozen=True)
class Day:
    xlsx_row: int
    day: date
    menu: int
    diners: int
    pw_kg: Decimal
    ksw_kg: Decimal | None
    derived: tuple[Decimal | None, Decimal | None, Decimal | None]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _label(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def _decimal_string(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return format(value.quantize(SIX, rounding=ROUND_HALF_EVEN), ".6f")


def _xml(zipped: ZipFile, name: str) -> ET.Element:
    try:
        return ET.fromstring(zipped.read(name))
    except (KeyError, ET.ParseError) as exc:
        raise SchoolWasteError(f"missing or invalid OOXML part: {name}") from exc


def _worksheet_path(zipped: ZipFile) -> str:
    workbook = _xml(zipped, "xl/workbook.xml")
    properties = workbook.find("m:workbookPr", NS)
    if properties is not None and properties.get("date1904", "false").lower() in ("1", "true"):
        raise SchoolWasteError("1904 date system is outside the pinned workbook contract")
    matches = [sheet for sheet in workbook.findall("m:sheets/m:sheet", NS)
               if sheet.get("name") == SHEET]
    if len(matches) != 1:
        raise SchoolWasteError(f"expected exactly one worksheet named {SHEET!r}")
    relationship_id = matches[0].get(f"{{{DOC_REL_NS}}}id")
    relationships = _xml(zipped, "xl/_rels/workbook.xml.rels")
    matches = [relation for relation in relationships.findall(f"{{{REL_NS}}}Relationship")
               if relation.get("Id") == relationship_id]
    if len(matches) != 1 or matches[0].get("Type") != WORKSHEET_REL:
        raise SchoolWasteError("named worksheet has no unique worksheet relationship")
    relation = matches[0]
    if relation.get("TargetMode") == "External" or not relation.get("Target"):
        raise SchoolWasteError("named worksheet must be stored inside the workbook")
    target = relation.get("Target", "")
    part = (target.lstrip("/") if target.startswith("/") else posixpath.join("xl", target))
    part = posixpath.normpath(part)
    if not part.startswith("xl/worksheets/") or part not in zipped.namelist():
        raise SchoolWasteError("named worksheet relationship has an invalid target")
    return part


def _shared_strings(zipped: ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in zipped.namelist():
        return []
    root = _xml(zipped, "xl/sharedStrings.xml")
    return ["".join(node.text or "" for node in item.findall(".//m:t", NS))
            for item in root.findall("m:si", NS)]


def _cell(cell: ET.Element, strings: list[str], address: str) -> Cell | None:
    cell_type = cell.get("t", "n")
    if cell_type == "inlineStr":
        inline = cell.find("m:is", NS)
        if inline is None:
            return None
        value = "".join(node.text or "" for node in inline.findall(".//m:t", NS))
        return Cell(value, "text") if value else None
    value_node = cell.find("m:v", NS)
    if value_node is None or value_node.text is None or value_node.text == "":
        return None
    value = value_node.text
    if cell_type == "s":
        try:
            value = strings[int(value)]
        except (ValueError, IndexError) as exc:
            raise SchoolWasteError(f"{address} has an invalid shared-string index") from exc
        return Cell(value, "text")
    if cell_type in ("str", "d"):
        return Cell(value, "date" if cell_type == "d" else "text")
    if cell_type in ("n", ""):
        return Cell(value, "number")
    raise SchoolWasteError(f"{address} has unsupported cell type {cell_type!r}")


def _first_eight_rows(zipped: ZipFile) -> list[tuple[int, dict[str, Cell]]]:
    root = _xml(zipped, _worksheet_path(zipped))
    strings = _shared_strings(zipped)
    rows: list[tuple[int, dict[str, Cell]]] = []
    seen_rows: set[int] = set()
    for row in root.findall("m:sheetData/m:row", NS):
        try:
            number = int(row.get("r", ""))
        except ValueError as exc:
            raise SchoolWasteError("worksheet has a row without a numeric index") from exc
        if number < 1 or number in seen_rows:
            raise SchoolWasteError(f"worksheet has duplicate or invalid row {number}")
        seen_rows.add(number)
        values: dict[str, Cell] = {}
        seen_refs: set[str] = set()
        for element in row.findall("m:c", NS):
            address = element.get("r", "")
            match = CELL_REF.fullmatch(address)
            if match is None or int(match.group(2)) != number:
                raise SchoolWasteError(f"invalid cell reference {address!r} in row {number}")
            column = match.group(1)
            if column not in "ABCDEFGH" or len(column) != 1:
                continue
            if column in seen_refs:
                raise SchoolWasteError(f"duplicate cell {address}")
            seen_refs.add(column)
            value = _cell(element, strings, address)
            if value is not None:
                values[column] = value
        if values or number == 1:
            rows.append((number, values))
    rows.sort(key=lambda item: item[0])
    return rows


def _numeric(cell: Cell | None, address: str, *, optional: bool = False) -> Decimal | None:
    if cell is None:
        if optional:
            return None
        raise SchoolWasteError(f"{address} is missing")
    if cell.kind != "number":
        raise SchoolWasteError(f"{address} must be a numeric cell")
    try:
        value = Decimal(cell.value)
    except InvalidOperation as exc:
        raise SchoolWasteError(f"{address} is not a decimal number") from exc
    if not value.is_finite() or value < 0:
        raise SchoolWasteError(f"{address} must be finite and nonnegative")
    return value


def _positive_integer(cell: Cell | None, address: str, *, maximum: int | None = None) -> int:
    value = _numeric(cell, address)
    assert value is not None
    if value != value.to_integral_value() or value < 1 or (maximum is not None and value > maximum):
        bound = f" through {maximum}" if maximum is not None else ""
        raise SchoolWasteError(f"{address} must be a positive integer{bound}")
    return int(value)


def _date(cell: Cell | None, address: str) -> date:
    if cell is None:
        raise SchoolWasteError(f"{address} is missing")
    if cell.kind == "date":
        if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", cell.value) is None:
            raise SchoolWasteError(f"{address} must be a whole date")
        try:
            return date.fromisoformat(cell.value)
        except ValueError as exc:
            raise SchoolWasteError(f"{address} is not a valid date") from exc
    serial = _numeric(cell, address)
    assert serial is not None
    if serial != serial.to_integral_value() or serial < 61:
        raise SchoolWasteError(f"{address} must be a whole Excel date after 1900-02-28")
    try:
        return date(1899, 12, 30) + timedelta(days=int(serial))
    except OverflowError as exc:
        raise SchoolWasteError(f"{address} is outside supported dates") from exc


def read_days(path: Path) -> list[Day]:
    try:
        with ZipFile(path) as zipped:
            rows = _first_eight_rows(zipped)
    except (OSError, BadZipFile) as exc:
        raise SchoolWasteError(f"cannot read XLSX: {path}") from exc
    if not rows or rows[0][0] != 1:
        raise SchoolWasteError("worksheet must have a header in row 1")
    headers = tuple(rows[0][1].get(column) for column in "ABCDEFGH")
    if headers != tuple(Cell(header, "text") for header in HEADERS):
        raise SchoolWasteError(f"first eight headers must be {HEADERS!r}")
    active = rows[1:]
    if len(active) != 155:
        raise SchoolWasteError(f"expected exactly 155 active data rows; found {len(active)}")
    days: list[Day] = []
    for number, values in active:
        day = _date(values.get("A"), f"A{number}")
        if days and day <= days[-1].day:
            raise SchoolWasteError(f"A{number} date must be unique and later than preceding dates")
        menu = _positive_integer(values.get("B"), f"B{number}", maximum=25)
        ksw = _numeric(values.get("C"), f"C{number}", optional=True)
        pw = _numeric(values.get("D"), f"D{number}")
        diners = _positive_integer(values.get("F"), f"F{number}")
        assert pw is not None
        derived = tuple(_numeric(values.get(column), f"{column}{number}", optional=True)
                        for column in "EGH")
        days.append(Day(number, day, menu, diners, pw, ksw, derived))
    return days


def _metric_days(days: list[Day], metric: str) -> list[Day]:
    return days if metric == "pw" else [day for day in days if day.ksw_kg is not None]


def _mass(day: Day, metric: str) -> Decimal:
    if metric == "pw":
        return day.pw_kg
    assert day.ksw_kg is not None
    return day.ksw_kg if metric == "ksw" else day.pw_kg + day.ksw_kg


def _period_summary(days: list[Day]) -> dict[str, Any]:
    diner_counts = sorted(day.diners for day in days)
    count = len(diner_counts)
    median = (Decimal(diner_counts[(count - 1) // 2]) + Decimal(diner_counts[count // 2])) / 2
    return {
        "days": count,
        "first_date": days[0].day.isoformat(),
        "last_date": days[-1].day.isoformat(),
        "menus": sorted({day.menu for day in days}),
        "diners": {
            "min": diner_counts[0],
            "max": diner_counts[-1],
            "median": _decimal_string(median),
            "mean": _decimal_string(Decimal(sum(diner_counts)) / count),
            "sum_all_days": sum(diner_counts),
        },
        "missing_ksw": [{"date": day.day.isoformat(), "xlsx_row": day.xlsx_row}
                        for day in days if day.ksw_kg is None],
        "missing_ksw_count": sum(day.ksw_kg is None for day in days),
    }


def _ratio(days: list[Day], metric: str) -> tuple[Decimal, int, Decimal]:
    kilograms = sum((_mass(day, metric) for day in days), Decimal(0))
    diners = sum(day.diners for day in days)
    return kilograms, diners, Decimal(1000) * kilograms / diners


def _metric(baseline: list[Day], intervention: list[Day], metric: str) -> dict[str, Any]:
    periods = {}
    ratios = {}
    for name, all_days in (("baseline", baseline), ("intervention", intervention)):
        valid = _metric_days(all_days, metric)
        if not valid:
            raise SchoolWasteError(f"{metric} has no eligible days in {name}")
        kilograms, diners, ratio = _ratio(valid, metric)
        periods[name] = {
            "days": len(valid),
            "denominator_diners": diners,
            "sum_kg": _decimal_string(kilograms),
            "g_per_diner": _decimal_string(ratio),
        }
        ratios[name] = ratio
    difference = ratios["intervention"] - ratios["baseline"]
    percent = (Decimal(100) * difference / ratios["baseline"]
               if ratios["baseline"] != 0 else None)
    return {
        "periods": periods,
        "difference_intervention_minus_baseline_g_per_diner": _decimal_string(difference),
        "percent_change_from_baseline": _decimal_string(percent),
    }


def _menu_sensitivity(baseline: list[Day], intervention: list[Day], metric: str) -> dict[str, Any]:
    groups: dict[str, dict[int, list[Day]]] = {"baseline": defaultdict(list),
                                               "intervention": defaultdict(list)}
    for name, all_days in (("baseline", baseline), ("intervention", intervention)):
        for day in _metric_days(all_days, metric):
            groups[name][day.menu].append(day)
    baseline_menus = set(groups["baseline"])
    intervention_menus = set(groups["intervention"])
    matched = sorted(baseline_menus & intervention_menus)
    details = []
    differences = []
    for menu in matched:
        one = groups["baseline"][menu]
        two = groups["intervention"][menu]
        one_mean = sum((Decimal(1000) * _mass(day, metric) / day.diners for day in one),
                       Decimal(0)) / len(one)
        two_mean = sum((Decimal(1000) * _mass(day, metric) / day.diners for day in two),
                       Decimal(0)) / len(two)
        difference = two_mean - one_mean
        differences.append(difference)
        details.append({
            "menu": menu,
            "baseline_days": len(one),
            "intervention_days": len(two),
            "baseline_mean_daily_g_per_diner": _decimal_string(one_mean),
            "intervention_mean_daily_g_per_diner": _decimal_string(two_mean),
            "difference_g_per_diner": _decimal_string(difference),
        })
    return {
        "matched_menu_count": len(matched),
        "matched_menu_details": details,
        "intervention_menus_without_baseline": sorted(intervention_menus - baseline_menus),
        "baseline_menus_without_intervention": sorted(baseline_menus - intervention_menus),
        "equal_menu_mean_difference_g_per_diner": (
            _decimal_string(sum(differences, Decimal(0)) / len(differences)) if differences else None),
        "range_difference_g_per_diner": (
            [_decimal_string(min(differences)), _decimal_string(max(differences))]
            if differences else None),
    }


def _derived_audit(days: list[Day]) -> dict[str, Any]:
    result = {}
    for index, name in enumerate(("PW g", "PW/g/diner", "KSW/g/diner")):
        compared = 0
        missing = []
        unexpected = []
        discrepancies = []
        max_difference = Decimal(0)
        for day in days:
            expected = (day.pw_kg * 1000 if index == 0 else
                        day.pw_kg * 1000 / day.diners if index == 1 else
                        day.ksw_kg * 1000 / day.diners if day.ksw_kg is not None else None)
            cached = day.derived[index]
            where = {"date": day.day.isoformat(), "xlsx_row": day.xlsx_row}
            if expected is None:
                if cached is not None:
                    unexpected.append({**where, "cached": _decimal_string(cached)})
            elif cached is None:
                missing.append(where)
            else:
                compared += 1
                difference = abs(cached - expected)
                max_difference = max(max_difference, difference)
                if difference > TOLERANCE:
                    discrepancies.append({
                        **where,
                        "cached": _decimal_string(cached),
                        "recalculated": _decimal_string(expected),
                        "absolute_difference": _decimal_string(difference),
                    })
        result[name] = {
            "compared": compared,
            "missing_cached": missing,
            "unexpected_cached_without_source": unexpected,
            "max_absolute_difference": _decimal_string(max_difference),
            "beyond_tolerance": discrepancies,
        }
    return result


def analyze_xlsx(path: Path, *, expected_sha256: str = SOURCE_SHA256) -> dict[str, Any]:
    digest = _sha256(path)
    if digest != expected_sha256:
        raise SchoolWasteError(f"source SHA-256 differs from fixed plan: {digest}")
    plan_digest = _sha256(PLAN)
    if plan_digest != PLAN_SHA256:
        raise SchoolWasteError(f"prior plan SHA-256 differs from committed plan: {plan_digest}")
    with localcontext() as context:
        context.prec = 50
        days = read_days(path)
        baseline, intervention = days[:135], days[135:]
        metrics = {metric: _metric(baseline, intervention, metric)
                   for metric in ("pw", "ksw", "total")}
        sensitivity = {metric: _menu_sensitivity(baseline, intervention, metric)
                       for metric in ("pw", "ksw", "total")}
        derived = _derived_audit(days)
        displacement = (
            _ratio(_metric_days(intervention, "total"), "total")[2]
            < _ratio(_metric_days(baseline, "total"), "total")[2]
            and _ratio(intervention, "pw")[2] > _ratio(baseline, "pw")[2]
        )
    return {
        "schema": 1,
        "classification": "development_descriptive_analysis",
        "source": {"path": _label(path), "sha256": digest, "worksheet": SHEET,
                   "first_eight_columns": list(HEADERS), "active_days": len(days)},
        "prior_plan": {"path": _label(PLAN), "sha256": plan_digest},
        "rules": {
            "period_cut": {"baseline_first_rows": 135, "intervention_last_rows": 20},
            "primary_estimator": "1000 * sum(component kg) / sum(diners) on eligible days",
            "pw_eligibility": "all days with PW and diners",
            "ksw_and_total_eligibility": "days with both PW and KSW; no imputation",
            "menu_sensitivity": "equal weight across shared menus; period mean of daily g/diner",
            "decimal_output_places": 6,
            "rounding": "ROUND_HALF_EVEN after Decimal calculations",
            "derived_column_tolerance_g": _decimal_string(TOLERANCE),
        },
        "periods": {"baseline": _period_summary(baseline),
                    "intervention": _period_summary(intervention)},
        "excluded_from_ksw_and_total": [
            {"period": "baseline" if index < 135 else "intervention",
             "date": day.day.isoformat(), "xlsx_row": day.xlsx_row}
            for index, day in enumerate(days) if day.ksw_kg is None
        ],
        "excluded_from_ksw_and_total_count": sum(day.ksw_kg is None for day in days),
        "metrics": metrics,
        "paired_menu_sensitivity": sensitivity,
        "derived_column_audit": derived,
        "total_decreases_while_pw_increases": displacement,
        "observed_component_shift": (
            "Total per diner decreased while PW per diner increased; component changes "
            "moved in opposite directions." if displacement else None),
        "limits": [
            "Single school and 20 intervention days; temporal and seasonal confounding remain.",
            "No untreated contemporary comparison, causal p-values, or causal intervals.",
            "Menu contrasts are descriptive sensitivity, not complete causal uncertainty.",
            "No production, storage, transport, purchase, safety, cost, or full-chain outcomes.",
            "Criterion 3 for the proposed food-chain intervention remains not demonstrated.",
        ],
        "criterion_3": "not_demonstrated",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    try:
        result = analyze_xlsx(args.input)
    except (OSError, SchoolWasteError) as exc:
        parser.exit(2, f"school-waste analysis failed: {exc}\n")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    output = (json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    try:
        with args.output.open("xb") as destination:
            destination.write(output)
    except FileExistsError:
        if args.output.read_bytes() != output:
            parser.exit(2, f"school-waste analysis failed: refusing to replace different bytes at {args.output}\n")
    print(args.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
