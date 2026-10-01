"""Original-source structural deliveries never become quality or efficacy results."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import development_delivery_contract as delivery  # noqa: E402
from prepare_development_round import _capsules  # noqa: E402


@pytest.fixture(scope="module")
def original_cases(tmp_path_factory):
    root = tmp_path_factory.mktemp("original-public-cases")
    _capsules(root, analysis=True)
    return root


def quantity():
    return {"value": None, "unit": "fixture_pending", "base": "structural fixture, not a measurement",
            "reason": "Independent calculation and review have not occurred in this fixture"}


def structural_fixture(case: Path, work: Path) -> dict:
    """Prepare deliberately incomplete synthetic content against actual case bytes."""
    contract = delivery.delivery_contract_template()
    case_id = json.loads((case / "case.json").read_bytes())["case_id"]
    (work / "analysis.py").write_text("from pathlib import Path\nPath('execution-marker').write_text('never execute')\n")
    (work / "report.md").write_text("Synthetic structure only. No independently judged result or field observation.\n")
    if case_id == "D-F":
        metrics = {section: {name: quantity() for name in names}
                   for section, names in contract["quantity_fields"].items()}
        metrics["milling"].update(mass_fractions={"pending": "fixture"}, economic_allocation={"pending": "fixture"},
                                  original_electricity_base="pending passage verification")
        metrics["baking_energy"]["conversion"] = "pending calculation"
        metrics["survey"].update(closed_mean_interval={key: quantity() for key in ["lower", "upper", "denominator"]},
                                 finite_upper_all={"finite": False, "reason": "synthetic flag, not a finding"},
                                 finite_upper_known={"finite": False, "reason": "synthetic flag, not a finding"},
                                 category_and_missing_rules="pending substantive review")
        claim = {"id": "pending-claim", "claim": "Synthetic pending claim, not a reported observation",
                 "classification": "pending", "sources": [{"file": "task.md", "sha256": delivery.TASK_PINS[case_id], "locator": "delivery section"}],
                 "unit": "pending", "base": "fixture only", "formula": None, "inputs": [], "author": None,
                 "reason": "Independent review pending"}
        (work / "sources.json").write_text(json.dumps({"schema": 1, "claims": [claim]}))
    else:
        metrics = {"intervals": {"count": 0, "continuity_checked": False, "issues": ["synthetic pending check"]},
                   "appliances_weekly": quantity(), "appliances_daily": {"1900-01-01": quantity()},
                   "additional_observation": "Synthetic pending observation, not an inference from the actual period"}
    metrics["source_audit"] = ["Synthetic pending passage audit, not a hash-based factual finding"]
    (work / "metrics.json").write_text(json.dumps(metrics))
    return contract


@pytest.fixture
def df(tmp_path, original_cases):
    case, work = tmp_path / "case", tmp_path / "work"
    shutil.copytree(original_cases / "D-F", case)
    work.mkdir()
    return case, work, structural_fixture(case, work)


@pytest.mark.parametrize("case_id", ["D-F", "D-E"])
def test_original_sources_and_pending_structure_do_not_assess_quality(tmp_path, original_cases, case_id):
    case, work = original_cases / case_id, tmp_path / "work"
    work.mkdir()
    result = delivery.check_delivery(case, work, structural_fixture(case, work))
    assert result["structural_checks_passed"] and result["unresolved_quantity_fields"] > 0
    for key in ["participant_executed", "metric_generation_authenticated", "semantic_completeness_assessed",
                "source_passages_verified", "quality_assessed", "normative_approval", "formal_cell_executed", "causal_impact_assessed"]:
        assert result[key] is False
    assert not (work / "execution-marker").exists()


@pytest.mark.parametrize("name", ["analysis.py", "metrics.json", "sources.json", "report.md"])
def test_absent_deliverable_is_explicit(df, name):
    case, work, contract = df
    (work / name).unlink()
    result = delivery.check_delivery(case, work, contract)
    assert not result["structural_checks_passed"]
    assert any(item["artifact"] == name for item in result["issues"])


@pytest.mark.parametrize("raw", [b'{"source_audit":[],"source_audit":[]}', b'{"x":NaN}', b'{"x":Infinity}', b'{"x":1e309}'])
def test_strict_json_errors_are_preserved_as_failures(df, raw):
    case, work, contract = df
    (work / "metrics.json").write_bytes(raw)
    result = delivery.check_delivery(case, work, contract)
    assert not result["structural_checks_passed"]
    assert (work / "metrics.json").read_bytes() == raw


@pytest.mark.parametrize("mutation", ["no_unit", "null_no_reason", "bool_value", "interval_denominator", "bad_allocation"])
def test_quantities_and_denominators_cannot_be_omitted(df, mutation):
    case, work, contract = df
    metrics = json.loads((work / "metrics.json").read_bytes())
    if mutation == "no_unit":
        del metrics["milling"]["wheat_input"]["unit"]
    elif mutation == "null_no_reason":
        del metrics["survey"]["lower_mean_known"]["reason"]
    elif mutation == "bool_value":
        metrics["milling"]["wheat_input"]["value"] = True
    elif mutation == "interval_denominator":
        del metrics["survey"]["closed_mean_interval"]["denominator"]
    else:
        metrics["milling"]["economic_allocation"] = None
    (work / "metrics.json").write_text(json.dumps(metrics))
    assert not delivery.check_delivery(case, work, contract)["structural_checks_passed"]


def test_huge_exact_integer_is_not_coerced_to_float_or_scored(df):
    case, work, contract = df
    metrics = json.loads((work / "metrics.json").read_bytes())
    metrics["milling"]["wheat_input"]["value"] = 10**1000
    (work / "metrics.json").write_text(json.dumps(metrics))
    result = delivery.check_delivery(case, work, contract)
    assert result["structural_checks_passed"] and result["quality_assessed"] is False


def test_report_word_limit_and_python_syntax(df):
    case, work, contract = df
    (work / "report.md").write_text("word " * 1201)
    (work / "analysis.py").write_text("if (\n")
    result = delivery.check_delivery(case, work, contract)
    assert {row["artifact"] for row in result["issues"]} == {"analysis.py", "report.md"}


@pytest.mark.parametrize("mutation", ["digest", "locator", "file_type", "absent_input", "cycle", "unknown_pending", "assumption_author", "derived_formula"])
def test_source_provenance_is_structurally_checked(df, mutation):
    case, work, contract = df
    mapping = json.loads((work / "sources.json").read_bytes())
    claim = mapping["claims"][0]
    if mutation == "digest":
        claim["sources"][0]["sha256"] = "0" * 64
    elif mutation == "locator":
        claim["sources"][0]["locator"] = ""
    elif mutation == "file_type":
        claim["sources"][0]["file"] = []
    elif mutation == "absent_input":
        claim["inputs"] = ["absent"]
    elif mutation == "cycle":
        claim["inputs"] = [claim["id"]]
    elif mutation == "unknown_pending":
        claim["reason"] = None
    elif mutation == "assumption_author":
        claim.update(classification="assumption", author=None)
    else:
        claim.update(classification="derived", formula=None)
    (work / "sources.json").write_text(json.dumps(mapping))
    assert not delivery.check_delivery(case, work, contract)["structural_checks_passed"]


def test_original_source_cannot_be_omitted_from_rehashed_inventory(df):
    case, work, contract = df
    (case / "source_lca.pdf").unlink()
    metadata = json.loads((case / "case.json").read_bytes())
    metadata["files"] = [row for row in metadata["files"] if row["path"] != "source_lca.pdf"]
    (case / "case.json").write_text(json.dumps(metadata))
    with pytest.raises(delivery.DeliveryContractError, match="omits or substitutes"):
        delivery.check_delivery(case, work, contract)


def test_rehashed_substitute_source_is_not_an_original(df):
    case, work, contract = df
    body = b"synthetic substitute"
    (case / "source_lca.pdf").write_bytes(body)
    metadata = json.loads((case / "case.json").read_bytes())
    for row in metadata["files"]:
        if row["path"] == "source_lca.pdf":
            row.update(bytes=len(body), sha256=hashlib.sha256(body).hexdigest())
    (case / "case.json").write_text(json.dumps(metadata))
    with pytest.raises(delivery.DeliveryContractError, match="omits or substitutes"):
        delivery.check_delivery(case, work, contract)


def test_sources_changed_during_check_are_rejected(df, monkeypatch):
    case, work, contract = df
    original_parse = delivery.ast.parse

    def changed(*args, **kwargs):
        (case / "source_survey.pdf").write_bytes(b"changed after initial inventory verification")
        return original_parse(*args, **kwargs)

    monkeypatch.setattr(delivery.ast, "parse", changed)
    with pytest.raises(delivery.DeliveryContractError, match="changed during"):
        delivery.check_delivery(case, work, contract)


def test_symlink_artifact_and_source_root_are_rejected(df, tmp_path):
    case, work, contract = df
    (work / "report.md").unlink()
    (work / "report.md").symlink_to(case / "task.md")
    assert not delivery.check_delivery(case, work, contract)["structural_checks_passed"]
    alias = tmp_path / "case-alias"
    alias.symlink_to(case, target_is_directory=True)
    with pytest.raises(delivery.DeliveryContractError, match="symlink"):
        delivery.check_delivery(alias, work, contract)


def test_common_contracts_cannot_be_extended_with_answers_or_weakened():
    rubric = delivery.rubric_template()
    rubric["reference_answers"] = {"D-E": "synthetic forbidden answer field"}
    with pytest.raises(delivery.DeliveryContractError):
        delivery.validate_rubric(rubric)
    contract = delivery.delivery_contract_template()
    contract["cases"][0]["artifacts"][2]["max_words"] = 1201
    with pytest.raises(delivery.DeliveryContractError):
        delivery.validate_delivery_contract(contract)
    valid = delivery.delivery_contract_template()
    detached = delivery.validate_delivery_contract(valid)
    detached["cases"].clear()
    assert valid["cases"]
    assert delivery.validate_rubric(copy.deepcopy(delivery.rubric_template()))["automated_Q"] is False


def test_cli_validate_and_structural_check_use_fresh_process(df, tmp_path):
    case, work, contract = df
    path, rubric = tmp_path / "contract.json", tmp_path / "rubric.json"
    path.write_text(json.dumps(contract))
    rubric.write_text(json.dumps(delivery.rubric_template()))
    script = ROOT / "scripts/development_delivery_contract.py"
    for args in [["validate", str(path), "--rubric", str(rubric)], ["check", str(path), str(case), str(work)]]:
        process = subprocess.run([sys.executable, "-I", "-B", str(script), *args], capture_output=True, check=False)
        assert process.returncode == 0, process.stderr
        assert json.loads(process.stdout)["quality_assessed"] is False
    assert not (work / "execution-marker").exists()
