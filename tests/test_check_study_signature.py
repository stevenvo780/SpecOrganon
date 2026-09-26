"""Real CLI checks for an offline, unsealed matrix-design signature."""

from __future__ import annotations

import base64
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
SCRIPT = SCRIPTS / "check_study_signature.py"
sys.path.insert(0, str(SCRIPTS))
from plan_confirmatory import canonical_bytes, compile_schedule  # noqa: E402
from check_study_signature import SignatureCheckError, verify_attestation  # noqa: E402


STUDY_GOAL = Path(__file__).resolve().parents[1] / "GOAL.md"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")


@pytest.fixture
def study(tmp_path: Path) -> dict[str, Any]:
    source = tmp_path / "source"
    source.mkdir()
    goal = tmp_path / "GOAL.md"
    protocol = tmp_path / "protocol.md"
    goal.write_bytes(STUDY_GOAL.read_bytes())
    protocol.write_bytes(b"Synthetic preregistered protocol for cryptographic test.\n")

    case_paths: dict[str, Any] = {}
    cases = []
    for case_id in ("R-F", "R-M", "R-S"):
        case_paths[case_id] = {}
        record = {"case_id": case_id}
        for role in ("package", "reference"):
            data = f"{case_id}-{role}-secret-test-bytes\n".encode()
            path = source / f"{case_id}_{role}.bin"
            path.write_bytes(data)
            case_paths[case_id][role] = str(path)
            record[f"{role}_sha256"] = _sha(data)
        cases.append(record)

    input_paths: dict[str, Any] = {}
    manifest_inputs: dict[str, Any] = {}
    for role in ("task_contract", "common_prompt", "rubric", "tool_policy", "sdd_guide", "toolkit"):
        data = f"{role}-synthetic-test-bytes\n".encode()
        path = source / role
        path.write_bytes(data)
        input_paths[role] = str(path)
        manifest_inputs[role] = {"ref": f"synthetic/{role}", "sha256": _sha(data)}
    input_paths["arm_prompts"] = {}
    manifest_inputs["arm_prompts"] = {}
    for arm in ("N", "S", "T"):
        data = f"prompt-{arm}-synthetic-test-bytes\n".encode()
        path = source / f"prompt_{arm}"
        path.write_bytes(data)
        input_paths["arm_prompts"][arm] = str(path)
        manifest_inputs["arm_prompts"][arm] = {
            "ref": f"synthetic/prompt_{arm}", "sha256": _sha(data),
        }

    models = []
    for family in ("family-a", "family-b"):
        for tier in ("lower", "higher"):
            controlled = tier == "higher"
            models.append({
                "family": family,
                "tier": tier,
                "model_id": f"{family}/{tier}",
                "version": "synthetic-v1",
                "effort_control": controlled,
                "efforts": ([
                    {"label": "low", "provider_value": "low"},
                    {"label": "high", "provider_value": "high"},
                ] if controlled else [{"label": "default"}]),
            })
    manifest = {
        "schema": 1,
        "seed": 101,
        "protocol_sha256": _sha(protocol.read_bytes()),
        "tool_call_cap": 20,
        "models": models,
        "cases": cases,
        "inputs": manifest_inputs,
    }
    schedule = compile_schedule(manifest)
    assets = {
        "schema": 1,
        "schedule_sha256": schedule["schedule_sha256"],
        "input_sha256": schedule["input_sha256"],
        "cases": case_paths,
        "inputs": input_paths,
    }
    schedule_path = tmp_path / "schedule.json"
    assets_path = tmp_path / "assets.json"
    _write_json(schedule_path, schedule)
    _write_json(assets_path, assets)
    return {
        "root": tmp_path,
        "manifest": manifest,
        "schedule": schedule,
        "assets": assets,
        "schedule_path": schedule_path,
        "assets_path": assets_path,
        "goal": goal,
        "protocol": protocol,
    }


def _cli(study: dict[str, Any], command: str, *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable, str(SCRIPT), command,
            str(study["schedule_path"]), str(study["assets_path"]),
            "--goal", str(study["goal"]), "--protocol", str(study["protocol"]),
            *extra,
        ],
        capture_output=True, text=True, check=False,
    )


def _challenge(study: dict[str, Any]) -> dict[str, Any]:
    result = _cli(study, "challenge")
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def _signed_files(study: dict[str, Any], challenge: dict[str, Any]) -> tuple[Path, Path]:
    private = Ed25519PrivateKey.generate()
    message = base64.b64decode(challenge["message_base64"], validate=True)
    signature = private.sign(message)
    public = private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    attestation_path = study["root"] / "attestation.json"
    trust_path = study["root"] / "trust.json"
    _write_json(attestation_path, {
        "schema": 1,
        "key_id": "custodian:ephemeral-test",
        "message_sha256": challenge["message_sha256"],
        "signature_base64": base64.b64encode(signature).decode("ascii"),
    })
    _write_json(trust_path, {
        "schema": 1,
        "keys": {"custodian:ephemeral-test": base64.b64encode(public).decode("ascii")},
    })
    return attestation_path, trust_path


def _verify(study: dict[str, Any], attestation: Path, trust: Path | str) -> subprocess.CompletedProcess[str]:
    return _cli(study, "verify", "--attestation", str(attestation), "--trust", str(trust))


def _assert_sanitized(study: dict[str, Any], process: subprocess.CompletedProcess[str]) -> None:
    combined = process.stdout + process.stderr
    assert str(study["root"]) not in combined
    assert "reference-secret-test-bytes" not in combined
    assert "R-F_reference.bin" not in combined
    assert "rubric-synthetic-test-bytes" not in combined


def test_challenge_cli_is_canonical_bound_to_all_current_bytes_and_unsealed(study: dict[str, Any]) -> None:
    before = set(study["root"].rglob("*"))
    result = _cli(study, "challenge")
    assert result.returncode == 0, result.stderr
    challenge = json.loads(result.stdout)
    assert set(challenge) == {
        "schema", "classification", "message_base64", "message_sha256", "notice",
    }
    assert challenge["schema"] == 1
    assert challenge["classification"] == "development_registry_challenge_unsealed"
    assert "only control" in challenge["notice"]
    assert "independently held" in challenge["notice"]
    message_bytes = base64.b64decode(challenge["message_base64"], validate=True)
    message = json.loads(message_bytes)
    assert message_bytes == canonical_bytes(message)
    assert challenge["message_sha256"] == _sha(message_bytes)
    assert message == {
        "purpose": "specorganon.matrix-design.v1",
        "schema": 1,
        "goal_sha256": _sha(study["goal"].read_bytes()),
        "protocol_sha256": _sha(study["protocol"].read_bytes()),
        "schedule_sha256": study["schedule"]["schedule_sha256"],
        "input_sha256": study["schedule"]["input_sha256"],
        "asset_digest_binding_sha256": message["asset_digest_binding_sha256"],
    }
    assert len(message["asset_digest_binding_sha256"]) == 64
    assert set(study["root"].rglob("*")) == before
    _assert_sanitized(study, result)
    assert str(study["root"]) not in message_bytes.decode("utf-8")


def test_verify_cli_accepts_real_ed25519_signature_without_claiming_reservation(study: dict[str, Any]) -> None:
    challenge = _challenge(study)
    attestation, trust = _signed_files(study, challenge)
    process = _verify(study, attestation, trust)
    assert process.returncode == 0, process.stderr
    trust_json = json.loads(trust.read_text(encoding="utf-8"))
    public = base64.b64decode(trust_json["keys"]["custodian:ephemeral-test"])
    assert json.loads(process.stdout) == {
        "schema": 1,
        "classification": "development_registry_signature_verified_unsealed",
        "message_sha256": challenge["message_sha256"],
        "key_id": "custodian:ephemeral-test",
        "public_key_sha256": _sha(public),
        "trust_sha256": _sha(canonical_bytes(trust_json)),
        "notice": challenge["notice"],
    }
    _assert_sanitized(study, process)


@pytest.mark.parametrize("mutation", ["schedule", "asset", "goal", "protocol"])
def test_verify_rejects_changed_design_inputs(study: dict[str, Any], mutation: str) -> None:
    challenge = _challenge(study)
    attestation, trust = _signed_files(study, challenge)
    if mutation == "schedule":
        manifest = {**study["manifest"], "seed": study["manifest"]["seed"] + 1}
        new_schedule = compile_schedule(manifest)
        _write_json(study["schedule_path"], new_schedule)
        assets = dict(study["assets"])
        assets["schedule_sha256"] = new_schedule["schedule_sha256"]
        assets["input_sha256"] = new_schedule["input_sha256"]
        _write_json(study["assets_path"], assets)
    elif mutation == "asset":
        Path(study["assets"]["cases"]["R-S"]["reference"]).write_bytes(b"changed hidden reference")
    elif mutation == "goal":
        study["goal"].write_bytes(study["goal"].read_bytes() + b"changed\n")
    else:
        study["protocol"].write_bytes(study["protocol"].read_bytes() + b"changed\n")
    process = _verify(study, attestation, trust)
    assert process.returncode == 2
    assert process.stdout == ""
    _assert_sanitized(study, process)


def test_challenge_rejects_missing_hidden_reference_before_output(study: dict[str, Any]) -> None:
    Path(study["assets"]["cases"]["R-M"]["reference"]).unlink()
    process = _cli(study, "challenge")
    assert process.returncode == 2
    assert process.stdout == ""
    _assert_sanitized(study, process)


def test_challenge_rejects_other_goal_even_when_supplied_by_goal_flag(study: dict[str, Any]) -> None:
    study["goal"].write_bytes(b"Different GOAL.md under caller control.\n")
    process = _cli(study, "challenge")
    assert process.returncode == 2
    assert "required study baseline" in process.stderr
    assert process.stdout == ""
    _assert_sanitized(study, process)


def test_challenge_rejects_rehashed_arm_order_inconsistent_with_seed(study: dict[str, Any]) -> None:
    schedule = json.loads(study["schedule_path"].read_text(encoding="utf-8"))
    first = schedule["runs"][0]
    stratum = (first["model_id"], first["effort"], first["agents"], first["case_id"])
    for replica in (1, 2, 3):
        pair = [
            run for run in schedule["runs"]
            if (run["model_id"], run["effort"], run["agents"], run["case_id"]) == stratum
            and run["replica"] == replica and run["arm"] in ("N", "S")
        ]
        assert len(pair) == 2
        pair[0]["order_position"], pair[1]["order_position"] = (
            pair[1]["order_position"], pair[0]["order_position"]
        )
        for run in pair:
            run["run_sha256"] = _sha(canonical_bytes({
                key: value for key, value in run.items() if key not in ("run_id", "run_sha256")
            }))
            run["run_id"] = "conf-" + run["run_sha256"][:24]
    schedule["schedule_sha256"] = _sha(canonical_bytes({
        key: value for key, value in schedule.items() if key != "schedule_sha256"
    }))
    _write_json(study["schedule_path"], schedule)
    assets = dict(study["assets"])
    assets["schedule_sha256"] = schedule["schedule_sha256"]
    _write_json(study["assets_path"], assets)

    process = _cli(study, "challenge")
    assert process.returncode == 2
    assert process.stdout == ""
    _assert_sanitized(study, process)


def test_direct_verifier_rejects_challenge_digest_inconsistent_with_signed_bytes(
    study: dict[str, Any]
) -> None:
    challenge = _challenge(study)
    attestation_path, trust_path = _signed_files(study, challenge)
    attestation = json.loads(attestation_path.read_text(encoding="utf-8"))
    trust = json.loads(trust_path.read_text(encoding="utf-8"))
    challenge["message_sha256"] = _sha(b"foreign message A")
    attestation["message_sha256"] = challenge["message_sha256"]
    with pytest.raises(SignatureCheckError, match="digest differs from its bytes"):
        verify_attestation(challenge, attestation, trust)


def test_direct_verifier_rejects_foreign_purpose_even_with_valid_signature(
    study: dict[str, Any]
) -> None:
    challenge = _challenge(study)
    message = json.loads(base64.b64decode(challenge["message_base64"]))
    message["purpose"] = "other-study.v1"
    message_bytes = canonical_bytes(message)
    challenge["message_base64"] = base64.b64encode(message_bytes).decode("ascii")
    challenge["message_sha256"] = _sha(message_bytes)
    attestation_path, trust_path = _signed_files(study, challenge)
    attestation = json.loads(attestation_path.read_text(encoding="utf-8"))
    trust = json.loads(trust_path.read_text(encoding="utf-8"))
    with pytest.raises(SignatureCheckError, match="purpose or schema"):
        verify_attestation(challenge, attestation, trust)


@pytest.mark.parametrize("mutation", [
    "unknown_key", "wrong_signature", "wrong_public_key", "extra_attestation_field",
    "extra_trust_field", "invalid_extra_trust_key", "noncanonical_signature",
    "message_digest", "bad_key_id", "bool_schema",
])
def test_verify_rejects_invalid_attestation_or_trust(study: dict[str, Any], mutation: str) -> None:
    challenge = _challenge(study)
    attestation, trust = _signed_files(study, challenge)
    att = json.loads(attestation.read_text(encoding="utf-8"))
    trusted = json.loads(trust.read_text(encoding="utf-8"))
    if mutation == "unknown_key":
        att["key_id"] = "unknown-key"
    elif mutation == "wrong_signature":
        signature = bytearray(base64.b64decode(att["signature_base64"]))
        signature[0] ^= 1
        att["signature_base64"] = base64.b64encode(signature).decode("ascii")
    elif mutation == "wrong_public_key":
        other = Ed25519PrivateKey.generate().public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        trusted["keys"][att["key_id"]] = base64.b64encode(other).decode("ascii")
    elif mutation == "extra_attestation_field":
        att["private_key"] = "should-not-be-here"
    elif mutation == "extra_trust_field":
        trusted["extra"] = "not allowed"
    elif mutation == "invalid_extra_trust_key":
        trusted["keys"]["other"] = "invalid"
    elif mutation == "noncanonical_signature":
        att["signature_base64"] = att["signature_base64"] + "\n"
    elif mutation == "message_digest":
        att["message_sha256"] = "0" * 64
    elif mutation == "bad_key_id":
        att["key_id"] = "/tmp/looks-like-path"
    else:
        trusted["schema"] = True
    _write_json(attestation, att)
    _write_json(trust, trusted)
    process = _verify(study, attestation, trust)
    assert process.returncode == 2
    assert process.stdout == ""
    _assert_sanitized(study, process)


@pytest.mark.parametrize("file_key", ["schedule_path", "assets_path", "attestation", "trust"])
def test_cli_rejects_duplicate_json_keys(study: dict[str, Any], file_key: str) -> None:
    challenge = _challenge(study)
    attestation, trust = _signed_files(study, challenge)
    path = {"attestation": attestation, "trust": trust}.get(file_key, study.get(file_key))
    assert path is not None
    original = path.read_text(encoding="utf-8")
    path.write_text('{"schema":1,"schema":1,"payload":' + json.dumps(original) + "}", encoding="utf-8")
    process = _verify(study, attestation, trust)
    assert process.returncode == 2
    assert process.stdout == ""
    _assert_sanitized(study, process)


def test_verify_requires_absolute_trust_path(study: dict[str, Any]) -> None:
    challenge = _challenge(study)
    attestation, _ = _signed_files(study, challenge)
    process = _verify(study, attestation, "relative-trust.json")
    assert process.returncode == 2
    assert "trust path must be absolute" in process.stderr
    _assert_sanitized(study, process)
