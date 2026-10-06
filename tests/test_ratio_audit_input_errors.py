"""Bounded synthetic JSON parser failures must stay inside the audit API."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from specorganon.ratio_audit import RatioAuditError, audit_derived_ratio


ROOT = Path(__file__).resolve().parents[1]


def _encode(value):
    return json.dumps(value, sort_keys=True).encode("utf-8")


def _inputs():
    scope = {"id": "synthetic", "start_utc": "2026-01-01T00:00:00Z",
             "end_utc": "2026-01-01T00:00:00Z"}
    source = {"kind": "synthetic", "start": scope["start_utc"],
              "end": scope["end_utc"], "part": 2, "whole": 8}
    quantity = {"value_type": "integer_count", "unit": "rows",
                "observation_unit": "row", "population": "synthetic",
                "time_scope": scope}
    target = {"metric": "synthetic_share", "unit": "fraction",
              "observation_unit": "row", "population": "synthetic",
              "time_scope": scope}
    contract = {
        "schema": 1, "classification": "synthetic_test_contract",
        "source_sha256": hashlib.sha256(_encode(source)).hexdigest(),
        "source_assertions": {"kind": "synthetic"},
        "source_window": {"start_locator": "start", "end_locator": "end"},
        "quantities": {"part": {**quantity, "locator": "part"},
                       "whole": {**quantity, "locator": "whole"}},
        "targets": {"share": {**target, "numerator_quantity": "part",
                              "denominator_quantity": "whole", "relation": "subset_fraction"}},
    }
    return {"source": _encode(source), "contract": _encode(contract),
            "claim": _encode({"schema": 1, "target_id": "share", **target})}


def _invalid_inputs(role, failure):
    inputs = _inputs()
    if failure == "depth":
        raw = b'{"nested":' + b"[" * 10000 + b"0" + b"]" * 10000 + b"}"
    else:
        raw = b'{"integer":' + b"1" * 5000 + b"}"
    assert len(raw) < 21000
    inputs[role] = raw
    if role == "source":
        contract = json.loads(inputs["contract"])
        contract["source_sha256"] = hashlib.sha256(raw).hexdigest()
        inputs["contract"] = _encode(contract)
    return inputs


def _audit(inputs):
    return audit_derived_ratio(inputs["source"], inputs["contract"], inputs["claim"],
                               hashlib.sha256(inputs["contract"]).hexdigest())


def _cli(tmp_path, inputs, entrypoint="module"):
    paths = {role: tmp_path / f"{role}.json" for role in inputs}
    for role, raw in inputs.items():
        paths[role].write_bytes(raw)
    protected = {path: path.read_bytes() for path in paths.values()}
    command = [sys.executable, "-X", "int_max_str_digits=4300"]
    command += (["-m", "specorganon.ratio_audit"] if entrypoint == "module"
                else [str(ROOT / "scripts/audit_derived_ratio.py")])
    command += ["--source", str(paths["source"]), "--contract", str(paths["contract"]),
                "--contract-sha256", hashlib.sha256(inputs["contract"]).hexdigest(),
                "--claim", str(paths["claim"])]
    completed = subprocess.run(command, cwd=ROOT, capture_output=True, timeout=15,
                               env={**os.environ, "PYTHONPATH": str(ROOT / "src")})
    assert {path: path.read_bytes() for path in protected} == protected
    return completed


@pytest.mark.parametrize("role", ("source", "contract", "claim"))
@pytest.mark.parametrize("failure", ("depth", "integer"))
def test_api_normalizes_json_parser_limits_without_changing_inputs(role, failure):
    inputs = _invalid_inputs(role, failure)
    before = inputs.copy()
    limit = sys.get_int_max_str_digits()
    try:
        sys.set_int_max_str_digits(4300)
        with pytest.raises(RatioAuditError, match=rf"^{role} must be a UTF-8 JSON object$") as error:
            _audit(inputs)
    finally:
        sys.set_int_max_str_digits(limit)
    assert inputs == before
    expected = RecursionError if failure == "depth" else ValueError
    assert type(error.value.__cause__) is expected


@pytest.mark.parametrize("entrypoint", ("module", "script"))
@pytest.mark.parametrize("role", ("source", "contract", "claim"))
@pytest.mark.parametrize("failure", ("depth", "integer"))
def test_cli_rejects_json_parser_limits_without_traceback(tmp_path, entrypoint, role, failure):
    completed = _cli(tmp_path, _invalid_inputs(role, failure), entrypoint)
    assert completed.returncode == 2
    assert completed.stdout == b""
    assert completed.stderr == f"derived ratio audit failed: {role} must be a UTF-8 JSON object\n".encode()
    assert len(completed.stderr) < 200
    assert b"Traceback" not in completed.stderr


@pytest.mark.parametrize(("raw", "message"), (
    (b'{"same":1,"same":2}', "duplicate JSON key: same"),
    (b'{"value":NaN}', "non-finite JSON value: NaN"),
))
def test_existing_specific_json_errors_keep_their_diagnostics(raw, message):
    inputs = _inputs()
    inputs["claim"] = raw
    with pytest.raises(RatioAuditError, match=message) as error:
        _audit(inputs)
    assert error.value.__cause__ is None


@pytest.mark.parametrize(("raw", "cause"), (
    (b'{"value":', json.JSONDecodeError),
    (b'{"value":"\xff"}', UnicodeDecodeError),
))
def test_existing_json_and_utf8_errors_remain_normalized(raw, cause):
    inputs = _inputs()
    inputs["claim"] = raw
    with pytest.raises(RatioAuditError, match="^claim must be a UTF-8 JSON object$") as error:
        _audit(inputs)
    assert type(error.value.__cause__) is cause


def test_valid_synthetic_receipt_matches_api_and_both_cli_entrypoints(tmp_path):
    inputs = _inputs()
    before = inputs.copy()
    result = _audit(inputs)
    assert result["exact_ratio"] == {"numerator": 1, "denominator": 4}
    module = _cli(tmp_path, inputs)
    script = _cli(tmp_path, inputs, "script")
    assert module.returncode == script.returncode == 0
    assert module.stderr == script.stderr == b""
    assert module.stdout == script.stdout
    assert json.loads(module.stdout) == {
        "classification": "derived_ratio_audit_batch", "results": [result],
    }
    assert inputs == before
