"""Public fixture arithmetic and forged metrics are checked without approval/Q."""

from __future__ import annotations

import copy
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import development_analysis_inputs as inputs  # noqa: E402
import verify_development_analysis as oracle  # noqa: E402

FIXTURES = ROOT / "experiments/development/isolated_analysis_2026-10-01/fixtures"


@pytest.fixture(scope="module")
def cases(tmp_path_factory):
    root = tmp_path_factory.mktemp("D113-oracle-public-cases")
    prepared = {}
    for case_id, script in (("D-F", "bread_analysis.py"), ("D-E", "building_energy_analysis.py")):
        case = root / case_id
        case.mkdir()
        for name in oracle.SOURCE_PINS[case_id]:
            if case_id == "D-E":
                source = ROOT / "cases/building_energy" / name
            elif name in ("source_lca.pdf", "source_survey.pdf", "survey_table1.json"):
                source = ROOT / "cases/bread_norway" / name
            else:
                source = ROOT / "cases/bread_development" / name
            shutil.copyfile(source, case / name)
        if case_id == "D-F":
            text_root = root / "common-texts"
            metadata = inputs.build_text_inputs(text_root)
            for item in metadata["files"]:
                shutil.copyfile(text_root / item["path"], case / item["path"])
        argv = [sys.executable, "-I", "-B", str(FIXTURES / script), str(case)]
        # A normal offline process establishes fixture viability. Sandbox
        # enforcement is covered by the separately owned analyzer integration.
        response = subprocess.run(argv, cwd=root, capture_output=True, timeout=20, check=False)
        (root / f"{case_id}.stdout").write_bytes(response.stdout)
        (root / f"{case_id}.stderr").write_bytes(response.stderr)
        (root / f"{case_id}.receipt.json").write_text(json.dumps({"argv": argv, "exit_code": response.returncode,
            "script_sha256": hashlib.sha256((FIXTURES / script).read_bytes()).hexdigest(),
            "classification": "public_offline_fixture_process_not_a_model_trial"}) + "\n")
        assert response.returncode == 0, response.stderr.decode()
        prepared[case_id] = (case, json.loads(response.stdout))
    return prepared


def test_fixture_history_proves_exact_original_and_only_prospective_reader_adaptation() -> None:
    history = json.loads((FIXTURES / "fixture_history.json").read_bytes())
    assert history["participant_outputs_repaired"] is False
    assert history["fixture_code_in_visible_case"] is False
    assert history["original_sources_unchanged"] is True
    for item in history["fixtures"]:
        source = (ROOT / item["source"]).read_bytes()
        fixture = (FIXTURES / item["fixture"]).read_bytes()
        assert hashlib.sha256(source).hexdigest() == item["source_sha256"]
        assert hashlib.sha256(fixture).hexdigest() == item["sha256"]
        assert len(fixture) == item["bytes"]
        if item["case_id"] == "D-E":
            assert source == fixture and item["adaptations"] == []
        else:
            text = source.decode("utf-8")
            replacement = item["adaptations"][0]
            assert text.count(replacement["old"]) == 1
            text = text.replace(replacement["old"], replacement["new"])
            text = text.replace("import subprocess\n", "").replace(", subprocess.SubprocessError", "")
            assert text.encode() == fixture


@pytest.mark.parametrize("case_id", ["D-F", "D-E"])
def test_both_actual_fixture_outputs_pass_independent_read_only_oracle(cases, case_id, monkeypatch) -> None:
    case, metrics = cases[case_id]
    before = {path.name: path.read_bytes() for path in case.iterdir()}
    def unexpected(*args, **kwargs):
        pytest.fail("oracle must not run scripts or PDF extractors")
    monkeypatch.setattr(subprocess, "run", unexpected)
    result = oracle.evaluate(case_id, metrics, case)
    assert result["passed"] is True, result["diagnostics"]
    assert result["diagnostics"] == [] and all(check["passed"] for check in result["checks"])
    assert result["classification"] == "independent_development_analysis_content_check_not_Q"
    assert "Q" not in result and "normative_approval" not in result
    assert result["source_pins"]["source_manifest.json"] == oracle.SOURCE_PINS[case_id]["source_manifest.json"][0]
    assert {path.name: path.read_bytes() for path in case.iterdir()} == before


@pytest.mark.parametrize("path,replacement", [
    (("milling", "outputs", "refined_flour", "value"), 999),
    (("milling", "economic_allocation_factors", "bran", "value"), .191),
    (("milling", "wheat_input", "base"), "one tonne of flour output"),
    (("milling", "electricity_original", "unit"), "kWh/t_wheat"),
    (("baking_energy", "electricity_per_kg", "value"), True),
    (("baking_energy", "sum_per_kg", "value"), float("nan")),
    (("survey", "closed_mean_interval", "lower", "base"), "all 1000 respondents"),
    (("survey", "lower_mean_known", "value"), 1.72),
    (("survey", "finite_upper_bound_all"), True),
    (("survey", "upper_total_known", "value"), 12),
    (("source_audit",), {"passed": True}),
    (("source_audit", "quantities", 0, "observed_value"), 737),
    (("source_audit", "quantities", 0, "matched_passage"), "invented bread observation"),
    (("source_audit", "quantities", 0, "matched_passage"), "4.2. Composition of Bread"),
    (("source_audit", "survey_rows", 0, "matched_passage"), "Zero slices 428 42.8"),
    (("source_audit", "discrepancies"), []),
])
def test_false_bread_quantity_base_units_passage_and_passed_flags_reject(cases, path, replacement) -> None:
    case, original = cases["D-F"]
    metrics = copy.deepcopy(original)
    target = metrics
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = replacement
    result = oracle.evaluate("D-F", metrics, case)
    assert result["passed"] is False and result["diagnostics"]


@pytest.mark.parametrize("field,value", [
    ("appliances_total_kwh", 1), ("lights_total_kwh", 0), ("rows", True),
    ("continuous", "true"), ("sample_sha256", "0" * 64),
    ("manifest_sha256", "0" * 64), ("last_timestamp", "2016-01-19 00:00:00"),
    ("daily_appliances_kwh", {"2016-01-12": 118.28}),
    ("units", {"appliances_total_kwh": "W", "lights_total_kwh": "kWh", "daily_appliances_kwh": "kWh"}),
])
def test_false_energy_quantity_stale_source_binding_and_daily_domain_reject(cases, field, value) -> None:
    case, original = cases["D-E"]
    metrics = copy.deepcopy(original)
    metrics[field] = value
    result = oracle.evaluate("D-E", metrics, case)
    assert result["passed"] is False and result["diagnostics"]


@pytest.mark.parametrize("case_id,name", [
    ("D-E", "sample_first_complete_week.csv"), ("D-E", "source_manifest.json"),
    ("D-F", "source_claims.json"), ("D-F", "source_lca.pdf"),
    ("D-F", "source_survey_page_04.txt"), ("D-F", "text_extract_manifest.json"),
])
def test_source_and_extraction_tampering_cannot_validate_old_metrics(cases, tmp_path, case_id, name) -> None:
    case, metrics = cases[case_id]
    changed = tmp_path / "case"
    shutil.copytree(case, changed)
    path = changed / name
    path.write_bytes(path.read_bytes() + b"\n")
    before = path.read_bytes()
    result = oracle.evaluate(case_id, metrics, changed)
    assert result["passed"] is False and result["diagnostics"]
    assert path.read_bytes() == before


def test_rejected_claim_and_passage_are_independent_of_self_reported_success(cases) -> None:
    case, _ = cases["D-F"]
    claims = json.loads((case / "source_claims.json").read_bytes())
    table = json.loads((case / "survey_table1.json").read_bytes())
    claims["claims"][0]["value"] = 737
    with pytest.raises(oracle.VerificationError, match="differs from passage"):
        oracle._passages(case, claims, table)
    claims["claims"][0]["value"] = 736
    claims["claims"][0]["base"] = "a different product population"
    with pytest.raises(oracle.VerificationError, match="unit/base/locator"):
        oracle._passages(case, claims, table)


def test_post_calculation_source_replacement_is_detected(cases, monkeypatch) -> None:
    case, metrics = cases["D-E"]
    original = oracle.read_pinned
    csv_reads = 0
    def read(path, digest, size=None):
        nonlocal csv_reads
        if path.name == "sample_first_complete_week.csv":
            csv_reads += 1
            if csv_reads == 2:
                raise inputs.AnalysisInputsError("injected source replacement after calculation")
        return original(path, digest, size)
    monkeypatch.setattr(oracle, "read_pinned", read)
    result = oracle.evaluate("D-E", metrics, case)
    assert result["passed"] is False
    assert any("after calculation" in item["message"] for item in result["diagnostics"])


@pytest.mark.parametrize("case_id,metrics", [("R-F", {}), ("D-F", []), ("D-E", {"extra": float("inf")})])
def test_reserved_case_nonobject_and_nonfinite_metrics_reject_before_interpretation(case_id, metrics, tmp_path) -> None:
    result = oracle.evaluate(case_id, metrics, tmp_path)
    assert result["passed"] is False and result["diagnostics"]
