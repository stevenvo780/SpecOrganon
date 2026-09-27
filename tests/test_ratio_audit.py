"""Exact, semantic audit of declared ratios from pinned JSON bytes."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from copy import deepcopy
from fractions import Fraction
from pathlib import Path

import pytest

from specorganon.ratio_audit import (
    MAX_CLAIM_BYTES,
    MAX_CONTRACT_BYTES,
    RatioAuditError,
    audit_derived_ratio,
)


ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT / "cases/citibike_march2024"
SOURCE = ROOT / "experiments/development/citibike_sample_status_2026-09-27.json"
CONTRACT = CASE / "ratio_contract_2026-09-27.json"
RENTAL = CASE / "ratio_claim_rental_2026-09-27.json"
RETURN = CASE / "ratio_claim_return_2026-09-27.json"
SCRIPT = ROOT / "scripts/audit_derived_ratio.py"
RECEIPT = ROOT / "experiments/development/citibike_march_ratio_audit_2026-09-27.json"
CONTRACT_SHA256 = "44f016ce11b3e07ad0309221a5f9f285ea3d0b16c643328a5fc0f37dec705255"


def _encode(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n").encode(
        "utf-8"
    )


def _audit(
    source_bytes: bytes,
    contract_bytes: bytes,
    claim_bytes: bytes,
    *,
    contract_sha256: str = CONTRACT_SHA256,
) -> dict:
    return audit_derived_ratio(
        source_bytes,
        contract_bytes,
        claim_bytes,
        contract_sha256,
    )


def _changed_source_contract(
    source: dict,
    contract: dict,
) -> tuple[bytes, bytes]:
    source_bytes = _encode(source)
    contract["source_sha256"] = hashlib.sha256(source_bytes).hexdigest()
    return source_bytes, _encode(contract)


def test_citibike_rental_and_return_are_distinct_exact_fractions() -> None:
    source_bytes = SOURCE.read_bytes()
    contract_bytes = CONTRACT.read_bytes()
    assert hashlib.sha256(contract_bytes).hexdigest() == CONTRACT_SHA256
    assert hashlib.sha256(source_bytes).hexdigest() == (
        "352ef988b91813912d15c465ba1e597c76eedc1461c33b29afc928c9f88c7ee1"
    )
    rental = _audit(source_bytes, contract_bytes, RENTAL.read_bytes())
    returning = _audit(source_bytes, contract_bytes, RETURN.read_bytes())

    assert (
        rental["classification"] == returning["classification"] == "derived_ratio_audit"
    )
    assert rental["source_truth_authenticated"] is False
    assert rental["subset_membership_verified_from_rows"] is False
    assert "criterion_5" not in rental and "field_impact" not in rental
    assert rental["numerator"]["value"] == 1_725_248
    assert returning["numerator"]["value"] == 1_682_386
    assert (
        rental["denominator"]["value"] == returning["denominator"]["value"] == 1_809_036
    )
    assert rental["metric"] != returning["metric"]
    for result, count in ((rental, 1_725_248), (returning, 1_682_386)):
        exact = Fraction(count, 1_809_036)
        assert result["exact_ratio"] == {
            "numerator": exact.numerator,
            "denominator": exact.denominator,
        }
        assert result["observation_unit"] == "station_snapshot_row"
        assert result["time_scope"]["id"] == "citibike_sample_march_2024"
        assert result["source_sha256"] == hashlib.sha256(source_bytes).hexdigest()
        assert result["contract_sha256"] == hashlib.sha256(contract_bytes).hexdigest()
    assert SOURCE.read_bytes() == source_bytes


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        (
            lambda claim: claim.update(
                observation_unit="station_minute",
                metric="rental_enabled_station_minutes_share",
            ),
            "claim.observation_unit",
        ),
        (
            lambda claim: claim.update(
                time_scope={
                    "id": "citibike_access_june_2026",
                    "start_utc": "2026-06-01T00:00:00Z",
                    "end_utc": "2026-06-30T23:59:59Z",
                },
                metric="realized_user_access_june_2026",
            ),
            "claim.time_scope",
        ),
    ],
)
def test_same_source_bytes_and_counts_cannot_be_relabelled(
    mutate: object,
    expected: str,
) -> None:
    source_bytes = SOURCE.read_bytes()
    contract_bytes = CONTRACT.read_bytes()
    claim = json.loads(RENTAL.read_bytes())
    mutate(claim)
    with pytest.raises(RatioAuditError, match=expected):
        _audit(source_bytes, contract_bytes, _encode(claim))
    assert (
        hashlib.sha256(source_bytes).hexdigest()
        == json.loads(contract_bytes)["source_sha256"]
    )


@pytest.mark.parametrize(
    ("field", "changed", "expected"),
    [
        ("observation_unit", "station_minute", "observation_unit"),
        ("population", "all_citibike_rows", "population"),
        (
            "time_scope",
            {
                "id": "june_2026",
                "start_utc": "2026-06-01T00:00:00Z",
                "end_utc": "2026-06-30T23:59:59Z",
            },
            "time_scope",
        ),
    ],
)
def test_denominator_must_match_numerator_and_target_scope(
    field: str,
    changed: object,
    expected: str,
) -> None:
    contract = json.loads(CONTRACT.read_bytes())
    contract["quantities"]["eligible_rows"][field] = changed
    contract_bytes = _encode(contract)
    with pytest.raises(RatioAuditError, match=expected):
        _audit(
            SOURCE.read_bytes(),
            contract_bytes,
            RENTAL.read_bytes(),
            contract_sha256=hashlib.sha256(contract_bytes).hexdigest(),
        )


def test_zero_denominator_rejected_even_with_matching_new_source_digest() -> None:
    source = json.loads(SOURCE.read_bytes())
    contract = json.loads(CONTRACT.read_bytes())
    source["snapshot_row_service"]["denominator"] = 0
    source["snapshot_row_service"]["rental_enabled_with_bike"] = 0
    source_bytes, contract_bytes = _changed_source_contract(source, contract)
    with pytest.raises(RatioAuditError, match="denominator must be positive"):
        _audit(
            source_bytes,
            contract_bytes,
            RENTAL.read_bytes(),
            contract_sha256=hashlib.sha256(contract_bytes).hexdigest(),
        )


def test_rewritten_target_scope_cannot_escape_source_window() -> None:
    contract = json.loads(CONTRACT.read_bytes())
    contract["targets"]["rental_service_fraction"]["time_scope"] = {
        "id": "june_2026",
        "start_utc": "2026-06-01T00:00:00Z",
        "end_utc": "2026-06-30T23:59:59Z",
    }
    contract_bytes = _encode(contract)
    with pytest.raises(RatioAuditError, match="time_scope differs from source window"):
        _audit(
            SOURCE.read_bytes(),
            contract_bytes,
            RENTAL.read_bytes(),
            contract_sha256=hashlib.sha256(contract_bytes).hexdigest(),
        )


def test_bool_and_float_are_not_integer_counts() -> None:
    for invalid in (True, 1.5):
        source = json.loads(SOURCE.read_bytes())
        contract = json.loads(CONTRACT.read_bytes())
        source["snapshot_row_service"]["denominator"] = invalid
        source_bytes, contract_bytes = _changed_source_contract(source, contract)
        with pytest.raises(RatioAuditError, match="nonnegative integer count"):
            _audit(
                source_bytes,
                contract_bytes,
                RENTAL.read_bytes(),
                contract_sha256=hashlib.sha256(contract_bytes).hexdigest(),
            )


def test_digest_and_duplicate_keys_are_rejected() -> None:
    source_bytes = SOURCE.read_bytes()
    with pytest.raises(RatioAuditError, match="source SHA-256 differs"):
        _audit(source_bytes + b" ", CONTRACT.read_bytes(), RENTAL.read_bytes())
    claim = RENTAL.read_text(encoding="utf-8").replace(
        '"schema": 1,',
        '"schema": 1, "schema": 1,',
        1,
    )
    with pytest.raises(RatioAuditError, match="duplicate JSON key"):
        _audit(source_bytes, CONTRACT.read_bytes(), claim.encode("utf-8"))


def test_coordinated_source_and_contract_rewrite_fails_old_contract_pin() -> None:
    source = json.loads(SOURCE.read_bytes())
    contract = json.loads(CONTRACT.read_bytes())
    source["snapshot_row_service"]["rental_enabled_with_bike"] = 1_700_000
    source_bytes, contract_bytes = _changed_source_contract(source, contract)
    with pytest.raises(RatioAuditError, match="contract SHA-256 differs"):
        _audit(source_bytes, contract_bytes, RENTAL.read_bytes())


def test_generic_decimal_quantity_uses_exact_arithmetic() -> None:
    scope = {
        "id": "batch_one",
        "start_utc": "2025-01-01T00:00:00Z",
        "end_utc": "2025-01-01T00:00:00Z",
    }
    source = {
        "sample": {"part": "0.25", "whole": "1.00"},
        "kind": "generic_mass_sample",
        "start": scope["start_utc"],
        "end": scope["end_utc"],
    }
    source_bytes = _encode(source)
    quantity = {
        "value_type": "decimal_quantity",
        "unit": "kg",
        "observation_unit": "batch",
        "population": "one_batch",
        "time_scope": scope,
    }
    contract = {
        "schema": 1,
        "classification": "generic_development_contract",
        "source_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "source_assertions": {"kind": "generic_mass_sample"},
        "source_window": {"start_locator": "start", "end_locator": "end"},
        "quantities": {
            "part": {**deepcopy(quantity), "locator": "sample.part"},
            "whole": {**deepcopy(quantity), "locator": "sample.whole"},
        },
        "targets": {
            "part_share": {
                "metric": "part_mass_share",
                "unit": "fraction",
                "observation_unit": "batch",
                "population": "one_batch",
                "time_scope": scope,
                "numerator_quantity": "part",
                "denominator_quantity": "whole",
                "relation": "subset_fraction",
            },
        },
    }
    claim = {
        "schema": 1,
        "target_id": "part_share",
        "metric": "part_mass_share",
        "unit": "fraction",
        "observation_unit": "batch",
        "population": "one_batch",
        "time_scope": scope,
    }
    contract_bytes = _encode(contract)
    result = _audit(
        source_bytes,
        contract_bytes,
        _encode(claim),
        contract_sha256=hashlib.sha256(contract_bytes).hexdigest(),
    )
    assert result["exact_ratio"] == {"numerator": 1, "denominator": 4}
    assert result["numerator"]["value_type"] == "decimal_quantity"


def test_cli_audits_both_claims_without_writing_sources() -> None:
    protected = {path: path.read_bytes() for path in (SOURCE, CONTRACT, RENTAL, RETURN)}
    arguments = [
        "--source",
        str(SOURCE),
        "--contract",
        str(CONTRACT),
        "--contract-sha256",
        CONTRACT_SHA256,
        "--claim",
        str(RENTAL),
        "--claim",
        str(RETURN),
    ]
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), *arguments],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
        timeout=15,
    )
    module = subprocess.run(
        [sys.executable, "-m", "specorganon.ratio_audit", *arguments],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
        timeout=15,
    )
    assert module.stdout == completed.stdout
    receipt = json.loads(completed.stdout)
    assert receipt["classification"] == "derived_ratio_audit_batch"
    assert {item["target_id"] for item in receipt["results"]} == {
        "rental_service_fraction",
        "return_service_fraction",
    }
    development_receipt = json.loads(RECEIPT.read_bytes())
    assert development_receipt["criterion_5"] == "not_assessed"
    assert development_receipt["field_impact"] == "not_assessed"
    assert development_receipt["results"] == receipt["results"]
    assert {path: path.read_bytes() for path in protected} == protected


def _limit_address_space() -> None:
    import resource

    limit = 64 * 1024 * 1024
    resource.setrlimit(resource.RLIMIT_AS, (limit, limit))


@pytest.mark.parametrize(
    ("role", "size"),
    [
        ("source", 64 * 1024 * 1024),
        ("contract", MAX_CONTRACT_BYTES + 1),
        ("claim", MAX_CLAIM_BYTES + 1),
    ],
)
def test_cli_rejects_oversized_inputs_without_traceback(
    tmp_path: Path,
    role: str,
    size: int,
) -> None:
    large = tmp_path / f"oversized-{role}.json"
    with large.open("wb") as stream:
        stream.truncate(size)
    paths = {"source": SOURCE, "contract": CONTRACT, "claim": RENTAL}
    paths[role] = large
    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--source",
            str(paths["source"]),
            "--contract",
            str(paths["contract"]),
            "--contract-sha256",
            CONTRACT_SHA256,
            "--claim",
            str(paths["claim"]),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=15,
        preexec_fn=_limit_address_space if sys.platform == "linux" else None,
    )
    assert completed.returncode == 2
    assert completed.stdout == ""
    assert f"{role} exceeds" in completed.stderr
    assert "Traceback" not in completed.stderr
    assert "MemoryError" not in completed.stderr
