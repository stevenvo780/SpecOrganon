"""Adversarial approval tests with ephemeral keys and an external trust file."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from mcp.client import Client
from mcp.client.stdio import StdioServerParameters

from specorganon import engine
from specorganon.ledger import LedgerError, read_project


BIN = Path(sys.executable).parent
CLI = BIN / "organon"
MCP = BIN / "organon-mcp"
ACTOR = "human:owner"
REASON = "I authorize this exact normative commitment"


@pytest.fixture
def signer(tmp_path, monkeypatch):
    key = Ed25519PrivateKey.generate()
    trust_file = tmp_path / "trusted-approvers.json"
    trust_file.write_text(json.dumps({"schema": 2, "cases": {}}), encoding="utf-8")
    monkeypatch.setenv("ORGANON_APPROVERS_FILE", str(trust_file))
    return key, trust_file


def _canonical(value: dict) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _register(case: Path, signer) -> None:
    key, trust_file = signer
    public_key = key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    project = read_project(case)["project"]
    project_sha256 = hashlib.sha256(_canonical(project)).hexdigest()
    assert engine.get_state(case)["project_sha256"] == project_sha256
    registry = json.loads(trust_file.read_text(encoding="utf-8"))
    registry["cases"][project["case_id"]] = {
        "path": str(case.resolve(strict=True)),
        "project_sha256": project_sha256,
        "approvers": {ACTOR: base64.b64encode(public_key).decode("ascii")},
    }
    trust_file.write_text(json.dumps(registry), encoding="utf-8")


def _write_rehashed_ledger(case: Path, ledger: dict) -> None:
    prior = "0" * 64
    for seq, event in enumerate(ledger["events"], start=1):
        event["seq"] = seq
        event["prev_hash"] = prior
        event["hash"] = hashlib.sha256(_canonical({k: v for k, v in event.items() if k != "hash"})).hexdigest()
        prior = event["hash"]
    (case / "organon.json").write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _sign(key: Ed25519PrivateKey, challenge: dict) -> str:
    message = base64.b64decode(challenge["message_base64"], validate=True)
    assert hashlib.sha256(message).hexdigest() == challenge["message_sha256"]
    return base64.b64encode(key.sign(message)).decode("ascii")


def _case(tmp_path: Path, signer, name: str = "case") -> Path:
    case = tmp_path / name
    state = engine.create_case(case, "Signed approval control", "test", ACTOR)
    assert state["project"]["approval_policy"] == "signed"
    _register(case, signer)
    engine.put_item(case, "p1", "problem", "A stated problem", [], {}, "agent:writer")
    engine.put_item(case, "a1", "actor", "Affected group", ["p1"], {}, "agent:writer")
    engine.put_item(case, "n1", "norm", "Protect the affected group", ["p1", "a1"], {}, "agent:writer")
    return case


def _challenge(case: Path, id: str = "n1", reason: str = REASON, actor: str = ACTOR) -> dict:
    before = (case / "organon.json").read_bytes()
    challenge = engine.approval_challenge(case, id, reason, actor)
    assert (case / "organon.json").read_bytes() == before
    assert challenge["case_path"] == str(case.resolve(strict=True))
    assert challenge["project_sha256"] == engine.get_state(case)["project_sha256"]
    assert challenge["ledger_head_sha256"] == read_project(case)["events"][-1]["hash"]
    return challenge


def _cli(*args: str) -> dict:
    result = subprocess.run([str(CLI), *args], text=True, capture_output=True, check=True)
    return json.loads(result.stdout)


def _mcp_data(result) -> dict:
    assert not result.is_error, result.content
    return result.structured_content or json.loads(result.content[0].text)


def test_signed_policy_rejects_spoofed_human_label_without_signature(tmp_path, signer):
    case = _case(tmp_path, signer)
    before = (case / "organon.json").read_bytes()
    with pytest.raises(engine.MethodError):
        engine.approve(case, "n1", REASON, ACTOR)
    assert (case / "organon.json").read_bytes() == before
    assert not engine.get_state(case)["items"]["n1"]["approved"]


def test_fixture_approval_is_explicitly_synthetic(tmp_path, enable_fixture_policy, monkeypatch):
    case = tmp_path / "fixture-case"
    engine.create_case(case, "Synthetic control", "fixture", "human:fixture", approval_policy="fixture")
    engine.put_item(case, "n1", "norm", "Synthetic norm", [], {}, "agent:writer")
    before = (case / "organon.json").read_bytes()
    with pytest.raises(engine.MethodError):
        engine.approve(case, "n1", "Spoofed decision", ACTOR)
    assert (case / "organon.json").read_bytes() == before
    monkeypatch.delenv("ORGANON_ALLOW_FIXTURES")
    with pytest.raises(engine.MethodError):
        engine.approve(case, "n1", "Disabled fixture decision", "human:fixture")
    assert (case / "organon.json").read_bytes() == before
    monkeypatch.setenv("ORGANON_ALLOW_FIXTURES", "1")
    engine.approve(case, "n1", "Only a fixture decision", "human:fixture")
    item = engine.get_state(case)["items"]["n1"]
    assert item["approved"]
    assert item["approval_status"] == "fixture"


def test_valid_signature_approves_exact_item_and_records_proof(tmp_path, signer):
    key, _ = signer
    case = _case(tmp_path, signer)
    challenge = _challenge(case)
    message = json.loads(base64.b64decode(challenge["message_base64"], validate=True))
    assert message["actor"] == ACTOR
    assert message["item_id"] == "n1"
    assert message["item_version"] == 1
    assert message["reason"] == REASON
    assert message["case_id"] == engine.get_state(case)["project"]["case_id"]
    assert message["case_path"] == str(case.resolve(strict=True))
    assert message["project_sha256"] == challenge["project_sha256"]
    assert message["ledger_head_sha256"] == challenge["ledger_head_sha256"]
    signature = _sign(key, challenge)
    event = engine.approve(case, "n1", REASON, ACTOR, signature=signature)
    assert event["actor"] == ACTOR
    assert engine.get_state(case)["items"]["n1"]["approved"]
    assert read_project(case)["events"][-1]["kind"] == "approval"


def test_wrong_key_reason_item_and_version_never_append_approval(tmp_path, signer):
    key, _ = signer
    case = _case(tmp_path, signer)
    engine.put_item(case, "n2", "norm", "Another commitment", ["p1", "a1"], {}, "agent:writer")
    signature = _sign(key, _challenge(case))

    wrong_key = Ed25519PrivateKey.generate()
    wrong_signature = _sign(wrong_key, _challenge(case))
    for id, reason, proof in (
        ("n1", REASON, wrong_signature),
        ("n1", "A different reason", signature),
        ("n2", REASON, signature),
    ):
        before = (case / "organon.json").read_bytes()
        with pytest.raises(engine.MethodError):
            engine.approve(case, id, reason, ACTOR, signature=proof)
        assert (case / "organon.json").read_bytes() == before

    engine.put_item(case, "n1", "norm", "Revised commitment", ["p1", "a1"], {}, "agent:writer")
    before = (case / "organon.json").read_bytes()
    with pytest.raises(engine.MethodError):
        engine.approve(case, "n1", REASON, ACTOR, signature=signature)
    assert (case / "organon.json").read_bytes() == before
    assert not engine.get_state(case)["items"]["n1"]["approved"]


def test_signature_cannot_replay_into_another_case(tmp_path, signer):
    key, _ = signer
    first = _case(tmp_path, signer, "first")
    second = _case(tmp_path, signer, "second")
    signature = _sign(key, _challenge(first))
    before = (second / "organon.json").read_bytes()
    with pytest.raises(engine.MethodError):
        engine.approve(second, "n1", REASON, ACTOR, signature=signature)
    assert (second / "organon.json").read_bytes() == before


def test_copied_signed_ledger_cannot_approve_at_a_second_path(tmp_path, signer):
    key, _ = signer
    first = _case(tmp_path, signer, "first")
    second = _case(tmp_path, signer, "second")
    engine.approve(first, "n1", REASON, ACTOR, signature=_sign(key, _challenge(first)))
    assert engine.get_state(first)["items"]["n1"]["approved"]
    shutil.copyfile(first / "organon.json", second / "organon.json")
    assert not engine.get_state(second)["items"]["n1"]["approved"]


def test_signed_case_metadata_cannot_be_downgraded_to_fixture(tmp_path, signer, monkeypatch):
    case = _case(tmp_path, signer)
    ledger = read_project(case)
    ledger["project"]["approval_policy"] = "fixture"
    (case / "organon.json").write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    monkeypatch.setenv("ORGANON_ALLOW_FIXTURES", "1")
    before = (case / "organon.json").read_bytes()
    with pytest.raises(engine.MethodError):
        engine.approve(case, "n1", "Forged fixture decision", "human:fixture")
    assert (case / "organon.json").read_bytes() == before
    assert not engine.get_state(case)["items"]["n1"]["approved"]


def test_rehashed_dependency_history_invalidates_existing_signature(tmp_path, signer):
    key, _ = signer
    case = _case(tmp_path, signer)
    engine.approve(case, "n1", REASON, ACTOR, signature=_sign(key, _challenge(case)))
    assert engine.get_state(case)["items"]["n1"]["approved"]

    ledger = read_project(case)
    ledger["events"][0]["payload"]["text"] = "An attacker changed the original problem"
    _write_rehashed_ledger(case, ledger)
    assert read_project(case)["events"][0]["payload"]["text"].startswith("An attacker")
    item = engine.get_state(case)["items"]["n1"]
    assert not item["approved"]
    assert item["approval_status"] != "signed_verified"


def test_forged_same_version_ancestor_replacement_is_malformed(tmp_path, signer):
    key, _ = signer
    case = _case(tmp_path, signer)
    engine.approve(case, "n1", REASON, ACTOR, signature=_sign(key, _challenge(case)))
    ledger = read_project(case)
    replacement = dict(ledger["events"][0])
    replacement["payload"] = {**replacement["payload"], "text": "Forged later problem"}
    replacement["actor"] = "agent:attacker"
    ledger["events"].append(replacement)
    _write_rehashed_ledger(case, ledger)
    with pytest.raises(LedgerError):
        engine.get_state(case)


def test_intervening_event_invalidates_old_challenge(tmp_path, signer):
    key, _ = signer
    case = _case(tmp_path, signer)
    stale_challenge = _challenge(case)
    engine.put_item(case, "b2", "boundary", "Unrelated new context", ["p1"], {}, "agent:writer")
    before = (case / "organon.json").read_bytes()
    with pytest.raises(engine.MethodError):
        engine.approve(case, "n1", REASON, ACTOR, signature=_sign(key, stale_challenge))
    assert (case / "organon.json").read_bytes() == before
    fresh_challenge = _challenge(case)
    assert fresh_challenge["ledger_head_sha256"] != stale_challenge["ledger_head_sha256"]
    engine.approve(case, "n1", REASON, ACTOR, signature=_sign(key, fresh_challenge))
    assert engine.get_state(case)["items"]["n1"]["approved"]


def test_removing_trust_reopens_an_accepted_phase(tmp_path, signer):
    key, trust_file = signer
    case = _case(tmp_path, signer)
    engine.put_item(case, "b1", "boundary", "Case boundary", ["p1"], {}, "agent:writer")
    engine.review_phase(case, "frame", "accept", "Fixture review of framing", "agent:reviewer")
    engine.advance(case, "frame", "agent:lead")
    engine.put_item(case, "c1", "concept", "Relevant concept", ["p1"], {}, "agent:writer")
    engine.put_item(case, "s1", "assumption", "An explicit assumption", ["p1"], {}, "agent:writer")
    engine.put_item(case, "f1", "frame_option", "First framing", ["p1"], {}, "agent:writer")
    engine.put_item(case, "f2", "frame_option", "Second framing", ["p1"], {}, "agent:writer")
    signature = _sign(key, _challenge(case))
    engine.approve(case, "n1", REASON, ACTOR, signature=signature)
    assert engine.gate(case, "critique")["ready"]
    engine.review_phase(case, "critique", "accept", "Independent review", "agent:reviewer")
    engine.advance(case, "critique", "agent:lead")
    assert engine.gate(case, "critique")["accepted"]

    trust_file.write_text(json.dumps({"schema": 2, "cases": {}}), encoding="utf-8")
    status = engine.gate(case, "critique")
    assert not status["ready"]
    assert not status["accepted"]
    assert not engine.get_state(case)["items"]["n1"]["approved"]
    assert any("approval" in blocker for blocker in status["blockers"])


def test_signed_cli_and_mcp_share_challenge_and_rejection(tmp_path, signer):
    key, trust_file = signer
    case = tmp_path / "interface-case"
    path = str(case)
    _cli("init", path, "--title", "Interface signature control", "--domain", "test", "--actor", ACTOR)
    assert _cli("status", path)["project"]["approval_policy"] == "signed"
    _register(case, signer)
    _cli("put", path, "p1", "--kind", "problem", "--text", "Problem", "--actor", "agent:writer")
    _cli("put", path, "a1", "--kind", "actor", "--text", "Affected group", "--ref", "p1", "--actor", "agent:writer")
    _cli("put", path, "n1", "--kind", "norm", "--text", "Commitment", "--ref", "p1", "--ref", "a1", "--actor", "agent:writer")

    async def exercise() -> None:
        params = StdioServerParameters(
            command=str(MCP), cwd=str(tmp_path),
            env={"ORGANON_ROOT": str(tmp_path), "ORGANON_APPROVERS_FILE": str(trust_file)},
        )
        async with Client(params, mode="legacy") as client:
            tools = {tool.name for tool in (await client.list_tools()).tools}
            assert {"approval_challenge", "approve"} <= tools
            args = {"path": path, "id": "n1", "reason": REASON, "actor": ACTOR}
            cli_challenge = _cli("approval-challenge", path, "n1", "--reason", REASON, "--actor", ACTOR)
            mcp_challenge = _mcp_data(await client.call_tool("approval_challenge", args))
            assert mcp_challenge == cli_challenge

            before = (case / "organon.json").read_bytes()
            rejected = await client.call_tool("approve", args)
            assert rejected.is_error
            assert (case / "organon.json").read_bytes() == before
            signature = _sign(key, cli_challenge)
            _mcp_data(await client.call_tool("approve", {**args, "signature": signature}))
            assert _mcp_data(await client.call_tool("status", {"path": path})) == _cli("status", path)
            assert _cli("status", path)["items"]["n1"]["approved"]

            _cli("put", path, "n1", "--kind", "norm", "--text", "Revised commitment",
                 "--ref", "p1", "--ref", "a1", "--actor", "agent:writer")
            assert not _cli("status", path)["items"]["n1"]["approved"]
            new_challenge = _mcp_data(await client.call_tool("approval_challenge", args))
            _cli("approve", path, "n1", "--reason", REASON, "--actor", ACTOR,
                 "--signature", _sign(key, new_challenge))
            assert _mcp_data(await client.call_tool("status", {"path": path})) == _cli("status", path)
            assert _cli("status", path)["items"]["n1"]["approved"]

    asyncio.run(exercise())
