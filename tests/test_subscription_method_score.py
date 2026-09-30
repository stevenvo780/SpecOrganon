"""Numerical falsification checks for the independently frozen D099 projection."""
from __future__ import annotations

import copy
import importlib.util
from pathlib import Path

import pytest

PATH = Path(__file__).resolve().parents[1] / "experiments/development/subscription_method_trial_2026-09-30/score.py"
SPEC = importlib.util.spec_from_file_location("d099_score", PATH)
score = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(score)


def test_real_source_reference_checks_all_rows_dates_and_energy() -> None:
    expected = score.reference()
    assert expected["rows"] == 1008 and expected["continuous"] is True
    assert len(expected["daily_appliances_kwh"]) == 7
    assert sum(expected["daily_appliances_kwh"].values()) == pytest.approx(expected["appliances_total_kwh"])
    actual = copy.deepcopy(expected)
    actual["appliances_total_kwh"] *= 1000
    actual["units"]["lights_total_kwh"] = "W"
    actual["daily_appliances_kwh"].pop("2016-01-12")
    result = score.project(actual, expected)
    assert result["total"] == 18 and result["passed"] == 14
    assert result["checks"]["appliances_total_kwh"] is False
    assert result["checks"]["units.lights_total_kwh"] is False
    assert result["checks"]["daily_date_set"] is False
    assert result["checks"]["daily_appliances_kwh.2016-01-12"] is False
    assert result["report_quality_measured"] is False and result["Q"] is None


@pytest.mark.parametrize("bad", [True, "1", float("nan"), float("inf"), 10**10000],
                         ids=["boolean", "numeric_string", "nan", "infinity", "overflow_integer"])
def test_bad_numeric_values_fail_instead_of_becoming_favorable(bad) -> None:
    expected = score.reference()
    actual = copy.deepcopy(expected)
    actual["lights_total_kwh"] = bad
    assert score.project(actual, expected)["checks"]["lights_total_kwh"] is False


def test_missing_or_untyped_outputs_do_not_pass() -> None:
    expected = score.reference()
    result = score.project({}, expected)
    assert result["passed"] == 0 and result["total"] == 18
    with pytest.raises(ValueError, match="object"):
        score.project([], expected)


def test_reference_parses_verified_bytes_when_source_changes_after_read(tmp_path, monkeypatch) -> None:
    expected = score.reference()
    raw = score.CSV.read_bytes()
    target = tmp_path / "sample.csv"
    target.write_bytes(raw)
    lines = raw.splitlines(keepends=True)
    first = lines[1].split(b",")
    first[1] = b"1000000"
    lines[1] = b",".join(first)
    changed = b"".join(lines)
    read_bytes = Path.read_bytes

    def replace_after_read(path):
        captured = read_bytes(path)
        if path == target:
            target.write_bytes(changed)
        return captured

    monkeypatch.setattr(score, "CSV", target)
    monkeypatch.setattr(Path, "read_bytes", replace_after_read)
    assert score.reference() == expected
    assert read_bytes(target) == changed
