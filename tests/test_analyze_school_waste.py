"""Contract and arithmetic tests for the fixed school-meal workbook analysis."""

from __future__ import annotations

import copy
import hashlib
import json
import sys
from datetime import date, timedelta
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import analyze_school_waste as school_waste  # noqa: E402
from analyze_school_waste import (  # noqa: E402
    DOC_REL_NS,
    HEADERS,
    NS,
    PLAN_SHA256,
    REL_NS,
    SHEET,
    SOURCE_SHA256,
    SchoolWasteError,
    analyze_xlsx,
    main,
)


def _rows() -> list[dict[str, str | tuple[str, str]]]:
    rows = []
    for index in range(155):
        baseline = index < 135
        pw = "1" if baseline else "2"
        ksw = "4" if baseline else "1"
        row = {
            "A": str((date(2024, 8, 1) + timedelta(days=index) - date(1899, 12, 30)).days),
            "B": str(index % 25 + 1),
            "C": ksw,
            "D": pw,
            "E": str(int(pw) * 1000),
            "F": "100",
            "G": str(int(pw) * 10),
            "H": str(int(ksw) * 10),
        }
        rows.append(row)
    rows[0].pop("C")
    rows[0].pop("H")
    return rows


def _book(
    path: Path,
    rows: list[dict[str, str | tuple[str, str]]],
    *,
    headers: tuple[str, ...] = HEADERS,
    sheet_name: str = SHEET,
    date1904: bool = False,
) -> str:
    main_ns = NS["m"]
    workbook = ET.Element(f"{{{main_ns}}}workbook")
    if date1904:
        ET.SubElement(workbook, f"{{{main_ns}}}workbookPr", {"date1904": "1"})
    sheets = ET.SubElement(workbook, f"{{{main_ns}}}sheets")
    ET.SubElement(sheets, f"{{{main_ns}}}sheet", {
        "name": sheet_name, "sheetId": "1", f"{{{DOC_REL_NS}}}id": "rId1",
    })
    rels = ET.Element(f"{{{REL_NS}}}Relationships")
    ET.SubElement(rels, f"{{{REL_NS}}}Relationship", {
        "Id": "rId1", "Type": f"{DOC_REL_NS}/worksheet", "Target": "worksheets/sheet1.xml",
    })
    shared = ET.Element(f"{{{main_ns}}}sst")
    for header in headers:
        item = ET.SubElement(shared, f"{{{main_ns}}}si")
        ET.SubElement(item, f"{{{main_ns}}}t").text = header
    worksheet = ET.Element(f"{{{main_ns}}}worksheet")
    sheet_data = ET.SubElement(worksheet, f"{{{main_ns}}}sheetData")
    header_row = ET.SubElement(sheet_data, f"{{{main_ns}}}row", {"r": "1"})
    for index, column in enumerate("ABCDEFGH"):
        cell = ET.SubElement(header_row, f"{{{main_ns}}}c", {"r": f"{column}1", "t": "s"})
        ET.SubElement(cell, f"{{{main_ns}}}v").text = str(index)
    for index, row_values in enumerate(rows, 2):
        row = ET.SubElement(sheet_data, f"{{{main_ns}}}row", {"r": str(index)})
        for column in "ABCDEFGH":
            if column not in row_values:
                continue
            datum = row_values[column]
            if isinstance(datum, tuple):
                kind, value = datum
                cell = ET.SubElement(row, f"{{{main_ns}}}c", {
                    "r": f"{column}{index}", "t": kind,
                })
                if kind == "inlineStr":
                    inline = ET.SubElement(cell, f"{{{main_ns}}}is")
                    ET.SubElement(inline, f"{{{main_ns}}}t").text = value
                else:
                    ET.SubElement(cell, f"{{{main_ns}}}v").text = value
            else:
                cell = ET.SubElement(row, f"{{{main_ns}}}c", {"r": f"{column}{index}"})
                ET.SubElement(cell, f"{{{main_ns}}}v").text = datum
    with ZipFile(path, "w", compression=ZIP_DEFLATED) as zipped:
        zipped.writestr("xl/workbook.xml", ET.tostring(workbook))
        zipped.writestr("xl/_rels/workbook.xml.rels", ET.tostring(rels))
        zipped.writestr("xl/sharedStrings.xml", ET.tostring(shared))
        zipped.writestr("xl/worksheets/sheet1.xml", ET.tostring(worksheet))
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _analyze(tmp_path: Path, rows: list[dict[str, str | tuple[str, str]]], **kwargs: object) -> dict:
    path = tmp_path / "school.xlsx"
    digest = _book(path, rows, **kwargs)
    return analyze_xlsx(path, expected_sha256=digest)


def test_missing_ksw_stays_missing_and_uses_paired_denominators(tmp_path: Path) -> None:
    result = _analyze(tmp_path, _rows())
    assert result["source"]["active_days"] == 155
    assert result["periods"]["baseline"]["missing_ksw"] == [
        {"date": "2024-08-01", "xlsx_row": 2},
    ]
    assert result["excluded_from_ksw_and_total"] == [
        {"date": "2024-08-01", "period": "baseline", "xlsx_row": 2},
    ]
    assert result["excluded_from_ksw_and_total_count"] == 1
    assert result["periods"]["baseline"]["missing_ksw_count"] == 1
    assert result["periods"]["intervention"]["missing_ksw_count"] == 0
    assert result["metrics"]["pw"]["periods"]["baseline"] == {
        "days": 135, "denominator_diners": 13500,
        "sum_kg": "135.000000", "g_per_diner": "10.000000",
    }
    for metric, baseline_ratio, intervention_ratio, difference in (
        ("ksw", "40.000000", "10.000000", "-30.000000"),
        ("total", "50.000000", "30.000000", "-20.000000"),
    ):
        summary = result["metrics"][metric]
        assert summary["periods"]["baseline"]["days"] == 134
        assert summary["periods"]["baseline"]["denominator_diners"] == 13400
        assert summary["periods"]["baseline"]["g_per_diner"] == baseline_ratio
        assert summary["periods"]["intervention"]["g_per_diner"] == intervention_ratio
        assert summary["difference_intervention_minus_baseline_g_per_diner"] == difference
    assert result["metrics"]["pw"]["difference_intervention_minus_baseline_g_per_diner"] == "10.000000"
    assert result["total_decreases_while_pw_increases"] is True
    assert "PW per diner increased" in result["observed_component_shift"]
    assert result["criterion_3"] == "not_demonstrated"


def test_menu_sensitivity_uses_equal_menu_weight_not_pooled_diners(tmp_path: Path) -> None:
    rows = _rows()
    # Menu 11 has 20 g/diner in intervention; other intervention menus have 10.
    # Its mean receives one twentieth of the weight regardless of baseline repeats.
    rows[135]["D"] = "2"
    rows[135]["G"] = "20"
    for index in range(136, 155):
        rows[index]["D"] = "1"
        rows[index]["E"] = "1000"
        rows[index]["G"] = "10"
    result = _analyze(tmp_path, rows)
    sensitivity = result["paired_menu_sensitivity"]["pw"]
    assert sensitivity["matched_menu_count"] == 20
    assert sensitivity["equal_menu_mean_difference_g_per_diner"] == "0.500000"
    assert sensitivity["range_difference_g_per_diner"] == ["0.000000", "10.000000"]
    assert sensitivity["baseline_menus_without_intervention"] == [6, 7, 8, 9, 10]
    assert sensitivity["intervention_menus_without_baseline"] == []


def test_derived_discrepancies_do_not_replace_source_masses(tmp_path: Path) -> None:
    rows = _rows()
    rows[135]["E"] = "9999"
    rows[135]["G"] = "99"
    rows[135]["H"] = "88"
    result = _analyze(tmp_path, rows)
    assert result["metrics"]["pw"]["periods"]["intervention"]["g_per_diner"] == "20.000000"
    for column in ("PW g", "PW/g/diner", "KSW/g/diner"):
        discrepancies = result["derived_column_audit"][column]["beyond_tolerance"]
        assert len(discrepancies) == 1
        assert discrepancies[0]["xlsx_row"] == 137
    assert result["derived_column_audit"]["PW g"]["beyond_tolerance"][0]["recalculated"] == "2000.000000"


def test_missing_baseline_ksw_menu_is_unpaired_only_for_ksw_and_total(tmp_path: Path) -> None:
    rows = _rows()
    for row in rows[:135]:
        if row["B"] == "11":
            row.pop("C")
            row.pop("H")
    rows[1].pop("G")
    result = _analyze(tmp_path, rows)
    assert result["paired_menu_sensitivity"]["pw"]["matched_menu_count"] == 20
    for metric in ("ksw", "total"):
        sensitivity = result["paired_menu_sensitivity"][metric]
        assert sensitivity["matched_menu_count"] == 19
        assert sensitivity["intervention_menus_without_baseline"] == [11]
    assert result["derived_column_audit"]["PW/g/diner"]["missing_cached"] == [
        {"date": "2024-08-02", "xlsx_row": 3},
    ]


def test_zero_baseline_mass_makes_percentage_undefined(tmp_path: Path) -> None:
    rows = _rows()
    for row in rows[:135]:
        row["D"] = "0"
        row["E"] = "0"
        row["G"] = "0"
    result = _analyze(tmp_path, rows)
    assert result["metrics"]["pw"]["periods"]["baseline"]["g_per_diner"] == "0.000000"
    assert result["metrics"]["pw"]["percent_change_from_baseline"] is None


@pytest.mark.parametrize(("change", "error"), [
    ("short", "exactly 155"),
    ("duplicate_date", "unique and later"),
    ("reverse_date", "unique and later"),
    ("menu_zero", "positive integer"),
    ("menu_26", "positive integer"),
    ("menu_fraction", "positive integer"),
    ("diners_zero", "positive integer"),
    ("diners_fraction", "positive integer"),
    ("pw_negative", "finite and nonnegative"),
    ("ksw_negative", "finite and nonnegative"),
    ("pw_text", "numeric cell"),
    ("derived_text", "numeric cell"),
    ("date_fraction", "whole Excel date"),
])
def test_schema_violations_stop_before_effects(tmp_path: Path, change: str, error: str) -> None:
    rows = _rows()
    if change == "short":
        rows.pop()
    elif change == "duplicate_date":
        rows[1]["A"] = rows[0]["A"]
    elif change == "reverse_date":
        rows[1]["A"] = "45500"
    elif change == "menu_zero":
        rows[1]["B"] = "0"
    elif change == "menu_26":
        rows[1]["B"] = "26"
    elif change == "menu_fraction":
        rows[1]["B"] = "1.5"
    elif change == "diners_zero":
        rows[1]["F"] = "0"
    elif change == "diners_fraction":
        rows[1]["F"] = "100.5"
    elif change == "pw_negative":
        rows[1]["D"] = "-1"
    elif change == "ksw_negative":
        rows[1]["C"] = "-1"
    elif change == "pw_text":
        rows[1]["D"] = ("inlineStr", "1")
    elif change == "derived_text":
        rows[1]["G"] = ("inlineStr", "10")
    elif change == "date_fraction":
        rows[1]["A"] = "45512.5"
    with pytest.raises(SchoolWasteError, match=error):
        _analyze(tmp_path, rows)


def test_header_sheet_and_date_system_are_bound(tmp_path: Path) -> None:
    rows = _rows()
    for options, error in (
        ({"headers": ("WRONG", *HEADERS[1:])}, "first eight headers"),
        ({"sheet_name": "other"}, "expected exactly one worksheet"),
        ({"date1904": True}, "1904 date system"),
    ):
        with pytest.raises(SchoolWasteError, match=error):
            _analyze(tmp_path, copy.deepcopy(rows), **options)


def test_hash_mismatch_stops_before_reading(tmp_path: Path) -> None:
    path = tmp_path / "school.xlsx"
    _book(path, _rows())
    with pytest.raises(SchoolWasteError, match="SHA-256 differs"):
        analyze_xlsx(path)


def test_modified_prior_plan_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    original_plan = ROOT / "docs/plan_escuela_residuos.md"
    assert hashlib.sha256(original_plan.read_bytes()).hexdigest() == PLAN_SHA256
    modified_plan = tmp_path / "changed-plan.md"
    modified_plan.write_bytes(original_plan.read_bytes() + b"\nchanged after outcome inspection\n")
    monkeypatch.setattr(school_waste, "PLAN", modified_plan)
    source = ROOT / "cases/school_waste/source.xlsx"
    with pytest.raises(SchoolWasteError, match="prior plan SHA-256 differs from committed plan"):
        analyze_xlsx(source)


def test_cli_output_is_idempotent_and_refuses_different_existing_bytes(tmp_path: Path) -> None:
    output = tmp_path / "result.json"
    assert main(["--output", str(output)]) == 0
    expected = output.read_bytes()
    previous_mtime = output.stat().st_mtime_ns
    assert main(["--output", str(output)]) == 0
    assert output.read_bytes() == expected
    assert output.stat().st_mtime_ns == previous_mtime
    output.write_bytes(b"different prior result\n")
    with pytest.raises(SystemExit) as failure:
        main(["--output", str(output)])
    assert failure.value.code == 2
    assert output.read_bytes() == b"different prior result\n"


def test_real_source_and_committed_development_result_are_reproducible() -> None:
    source = ROOT / "cases/school_waste/source.xlsx"
    assert hashlib.sha256(source.read_bytes()).hexdigest() == SOURCE_SHA256
    result = analyze_xlsx(source)
    assert result == json.loads((ROOT / "experiments/development/school_waste_2026-09-26.json")
                                .read_text(encoding="utf-8"))
    assert result["periods"]["baseline"]["missing_ksw"] == [
        {"date": "2024-09-02", "xlsx_row": 19},
    ]
    assert result["metrics"]["total"]["periods"]["baseline"]["denominator_diners"] == 53818
    assert result["metrics"]["total"]["periods"]["intervention"]["denominator_diners"] == 7415
    assert result["derived_column_audit"]["PW g"]["beyond_tolerance"][0]["xlsx_row"] == 152
    assert [row["xlsx_row"] for row in result["derived_column_audit"]["PW/g/diner"]["beyond_tolerance"]] == [137, 152]
    assert result["derived_column_audit"]["KSW/g/diner"]["beyond_tolerance"][0]["xlsx_row"] == 137
