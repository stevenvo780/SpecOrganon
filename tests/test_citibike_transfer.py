"""Replay the documented Citi Bike revision through the public toolkit CLI."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT / "cases" / "citibike"
CLI = Path(sys.executable).with_name("organon")


def _cli(env: dict[str, str], *args: str) -> dict:
    result = subprocess.run(
        [str(CLI), *args],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=True,
        timeout=15,
    )
    return json.loads(result.stdout)


def test_documented_citibike_revision_propagates_through_signed_case(
    tmp_path: Path,
) -> None:
    source_file = CASE / "organon.json"
    source_bytes = source_file.read_bytes()
    source = json.loads(source_bytes)
    seed = json.loads((CASE / "seed.json").read_text(encoding="utf-8"))
    expected = json.loads((CASE / "revision_check.json").read_text(encoding="utf-8"))

    assert len(seed["items"]) == expected["source_revision"] == 30
    recorded = source["events"][expected["revised_item"]["event_seq"] - 1]
    payload = recorded["payload"]
    assert recorded["kind"] == "item_put"
    assert (payload["id"], payload["version"]) == (expected["revised_item"]["id"], 2)
    assert payload["kind"] == "assumption"
    assert payload["text"] != next(
        item["text"] for item in seed["items"] if item["id"] == "s_proxy"
    )

    # Keep this documentary replay independent of local approval and anchor settings.
    env = os.environ.copy()
    for key in (
        "ORGANON_APPROVERS_FILE",
        "ORGANON_ALLOW_FIXTURES",
        "ORGANON_LEDGER_ANCHORS_FILE",
    ):
        env.pop(key, None)

    case = tmp_path / "citibike-replay"
    seeded = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "seed_case.py"),
            str(CASE / "seed.json"),
            str(case),
        ],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=True,
        timeout=15,
    )
    assert json.loads(seeded.stdout)["revision"] == expected["source_revision"]
    before = _cli(env, "status", str(case))
    assert before["project"]["approval_policy"] == "signed"
    assert before["revision"] == expected["source_revision"]
    assert set(before["items"]) == {item["id"] for item in seed["items"]}
    assert before["items"]["s_proxy"]["version"] == 1
    assert not {item_id for item_id, item in before["items"].items() if item["stale"]}

    args = [
        "put",
        str(case),
        payload["id"],
        "--kind",
        payload["kind"],
        "--text",
        payload["text"],
        "--data",
        json.dumps(payload["data"], ensure_ascii=False),
        "--actor",
        recorded["actor"],
        "--expected-version",
        "1",
        "--expected-deps",
        json.dumps(payload["deps"]),
    ]
    for ref in payload["deps"]:
        args.extend(("--ref", ref))
    revised = _cli(env, *args)
    assert {key: revised[key] for key in payload} == payload
    assert revised["seq"] == expected["revised_item"]["event_seq"]
    assert revised["author"] == recorded["actor"]
    replay_event = json.loads((case / "organon.json").read_text(encoding="utf-8"))[
        "events"
    ][-1]
    assert (
        replay_event["seq"],
        replay_event["kind"],
        replay_event["actor"],
        replay_event["payload"],
    ) == (
        recorded["seq"],
        recorded["kind"],
        recorded["actor"],
        payload,
    )

    state = _cli(env, "status", str(case))
    stale = {item_id for item_id, item in state["items"].items() if item["stale"]}
    assert state["revision"] == expected["revised_revision"]
    assert stale == set(expected["stale_after"])
    assert len(stale) == expected["stale_count"] == 12
    assert (
        state["items"]["d_candidate"]["stale"] is expected["candidate_decision_stale"]
    )
    assert (
        state["items"]["req_archive"]["stale"]
        is expected["candidate_requirement_stale"]
    )
    assert {
        phase: status["ready"] for phase, status in state["phases"].items()
    } == expected["phase_ready_after"]
    assert {
        phase: status["accepted"] for phase, status in state["phases"].items()
    } == expected["phase_accepted_after"]

    trace = _cli(env, "trace", str(case), "req_archive")
    assert trace["item"]["id"] == "req_archive" and trace["item"]["stale"]
    assert any(
        item["id"] == "s_proxy" and item["version"] == 2 for item in trace["ancestors"]
    )

    review = _cli(
        env,
        "review-phase",
        str(case),
        "frame",
        "--verdict",
        "accept",
        "--reason",
        "Independent review of documentary scope and corrected proxy",
        "--actor",
        "agent:citibike_reviewer",
    )
    assert review["payload"]["independent"] is True
    advance = _cli(
        env, "advance", str(case), "frame", "--actor", "agent:citibike_reviewer"
    )
    assert advance["payload"]["review_seq"] == review["seq"]
    advanced = _cli(env, "status", str(case))
    assert (
        advanced["phases"]["frame"]["ready"] and advanced["phases"]["frame"]["accepted"]
    )
    assert advanced["phases"]["frame"]["independent_review"]

    critique = _cli(env, "gate", str(case), "critique")
    assert not critique["ready"] and not critique["accepted"]
    assert not advanced["items"]["n_fair_access"]["approved"]
    assert any(
        "n_fair_access" in blocker and "human" in blocker and "approval" in blocker
        for blocker in critique["blockers"]
    )
    specify = _cli(env, "gate", str(case), "specify")
    assert not specify["ready"] and not specify["accepted"]
    assert {
        f"{item_id} depends on an older revision"
        for item_id in ("d_candidate", "req_archive")
    } <= set(specify["blockers"])

    replay_bytes = (case / "organon.json").read_bytes()
    refused = subprocess.run(
        [
            str(CLI),
            "approve",
            str(case),
            "n_fair_access",
            "--reason",
            "No signed decision",
            "--actor",
            "human:unverified",
        ],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
        timeout=15,
    )
    assert refused.returncode == 1
    assert "signature" in refused.stderr
    assert (case / "organon.json").read_bytes() == replay_bytes
    assert not any(
        event["kind"] == "approval" for event in json.loads(replay_bytes)["events"]
    )
    assert source_file.read_bytes() == source_bytes
