"""Exercise a denominator challenge on a temporary March 2024 Citi Bike ledger.

The wrong denominator is an injected development claim. The published result,
historical ledger, and seed are checked and copied byte for byte; this probe
does not ask a provider to judge the claim or grant human normative approval.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import probe_citibike_march_indicator_lineage as lineage


ROOT = lineage.ROOT
SOURCE_LEDGER = lineage.SOURCE_LEDGER
SEED = lineage.SEED
PUBLISHED_RESULT = lineage.PUBLISHED_RESULT
ANALYSIS_SCRIPT = lineage.ANALYSIS_SCRIPT
CLI = Path(sys.executable).with_name("organon")
AUTHOR = "agent:march_challenge_development_author"
REVIEWER = "agent:march_challenge_development_reviewer"
CHALLENGER = "agent:march_challenge_development_challenger"
INFERENCE = "inf_raw_denominator"
INDICATOR = "i_raw_fraction"
REQUIREMENT = "req_raw_fraction"
SYNTHESIS = "syn_denominator_correction"
DESCENDANTS = (INFERENCE, INDICATOR, REQUIREMENT)
PROTECTED = (SOURCE_LEDGER, SEED, PUBLISHED_RESULT, ANALYSIS_SCRIPT)


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _encode(value: Any) -> str:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )


def _cli(env: dict[str, str], *args: str) -> dict[str, Any]:
    process = subprocess.run(
        [str(CLI), *args], cwd=ROOT, env=env, text=True,
        capture_output=True, timeout=60, check=True,
    )
    return json.loads(process.stdout)


def _put(
    env: dict[str, str], case: Path, item_id: str, kind: str, description: str,
    refs: tuple[str, ...], data: dict[str, Any],
) -> dict[str, Any]:
    state = _cli(env, "status", str(case))
    current = state["items"].get(item_id)
    return _cli(
        env, "put", str(case), item_id, "--kind", kind, "--text", description,
        *(part for ref in refs for part in ("--ref", ref)),
        "--data", _encode(data), "--actor", AUTHOR,
        "--expected-version", str(current["version"] if current else 0),
        "--expected-deps", _encode({ref: state["items"][ref]["version"] for ref in refs}),
    )


def _expect_rejection(
    env: dict[str, str], case: Path, message: str, *args: str
) -> dict[str, Any]:
    before = (case / "organon.json").read_bytes()
    process = subprocess.run(
        [str(CLI), *args], cwd=ROOT, env=env, text=True,
        capture_output=True, timeout=60, check=False,
    )
    if (
        process.returncode != 1 or process.stdout or message not in process.stderr
        or (case / "organon.json").read_bytes() != before
    ):
        raise AssertionError(
            f"CLI did not reject {args[0]} without a ledger write: "
            f"exit={process.returncode}, stderr={process.stderr!r}"
        )
    return {"command": args[0], "error": process.stderr.strip(), "ledger_unchanged": True}


def _seed_matches_ledger(seed: dict[str, Any], ledger: dict[str, Any]) -> None:
    items = seed["items"]
    events = ledger["events"]
    if (
        len(items) != 22
        or len(events) != 24
        or ledger["project"]["approval_policy"] != "signed"
        or [event["kind"] for event in events[22:]] != ["phase_review", "phase_advance"]
        or any(event["kind"] == "approval" for event in events)
    ):
        raise AssertionError("March seed or historical signed ledger baseline changed")
    if (
        seed["title"] != ledger["project"]["title"]
        or seed["domain"] != ledger["project"]["domain"]
    ):
        raise AssertionError("March seed project differs from the historical ledger")
    for seeded, event in zip(items, events[:22], strict=True):
        payload = event["payload"]
        if event["kind"] != "item_put" or any(
            payload[key] != expected
            for key, expected in (
                ("id", seeded["id"]),
                ("kind", seeded["kind"]),
                ("text", seeded["text"]),
                ("data", seeded.get("data", {})),
                ("deps", {ref: 1 for ref in seeded.get("refs", [])}),
            )
        ):
            raise AssertionError(f"March seed item {seeded['id']} differs from ledger")


def _item(state: dict[str, Any], item_id: str) -> dict[str, Any]:
    item = state["items"][item_id]
    return {
        "version": item["version"],
        "stale": item["stale"],
        "contested": item["contested"],
        "denominator": item["data"].get("denominator"),
        "deps": item["deps"],
    }


def _snapshot(state: dict[str, Any], ids: tuple[str, ...]) -> dict[str, Any]:
    return {
        "revision": state["revision"],
        "open_challenge_seqs": [entry["seq"] for entry in state["open_challenges"]],
        "items": {item_id: _item(state, item_id) for item_id in ids},
    }


def _assert_blocker(env: dict[str, str], case: Path, phase: str, item_id: str) -> list[str]:
    gate = _cli(env, "gate", str(case), phase)
    blocker = f"{item_id} has an unresolved contradiction"
    if gate["ready"] or blocker not in gate["blockers"]:
        raise AssertionError(f"{phase} gate failed to block contested {item_id}")
    return gate["blockers"]


def _copy_case(work: Path, ledger_bytes: bytes, seed_bytes: bytes) -> Path:
    case = work / "case"
    case.mkdir()
    (case / "organon.json").write_bytes(ledger_bytes)
    (case / "seed.json").write_bytes(seed_bytes)
    if (
        (case / "organon.json").read_bytes() != ledger_bytes
        or (case / "seed.json").read_bytes() != seed_bytes
    ):
        raise AssertionError("temporary case is not a byte-identical source copy")
    return case


def _validate_destinations(output: Path | None, derived_case: Path | None) -> None:
    protected = {path.resolve() for path in PROTECTED}
    cases_root = (ROOT / "cases").resolve()
    for target in (output, derived_case):
        if target is None:
            continue
        resolved = target.resolve()
        if resolved in protected or resolved.is_relative_to(cases_root):
            raise ValueError(f"destination cannot replace or enter historical case sources: {target}")
    if output is not None and output.suffix != ".json":
        raise ValueError("--output must be a JSON file")
    if derived_case is not None:
        if derived_case.exists():
            raise FileExistsError(f"derived case already exists: {derived_case}")
        if output is not None and output.resolve() in {
            (derived_case / name).resolve()
            for name in ("organon.json", "seed.json", "manifest.json")
        }:
            raise ValueError("--output collides with a derived-case artifact")


def run_probe(derived_case: Path | None = None) -> dict[str, Any]:
    """Run public CLI operations against a fresh temporary historical copy."""
    if not CLI.is_file():
        raise FileNotFoundError("installed organon executable is required")
    if derived_case is not None:
        _validate_destinations(None, derived_case)
    original_bytes = {path: path.read_bytes() for path in PROTECTED}
    source = json.loads(original_bytes[SOURCE_LEDGER])
    seed = json.loads(original_bytes[SEED])
    published = json.loads(original_bytes[PUBLISHED_RESULT])
    _seed_matches_ledger(seed, source)
    source_hashes = lineage._check_sources(source, published)
    raw = published["rows"]
    eligible = lineage.check_eligible_denominator(
        published["snapshot_row_service"]["denominator"], published
    )
    excluded = published["quality"]["excluded_rows"]
    if raw == eligible:
        raise AssertionError("the published raw and eligible denominators do not differ")

    with tempfile.TemporaryDirectory(prefix="organon-march-challenge-") as temporary:
        work = Path(temporary)
        case = _copy_case(work, original_bytes[SOURCE_LEDGER], original_bytes[SEED])
        env = os.environ.copy()
        for key in (
            "ORGANON_APPROVERS_FILE", "ORGANON_ALLOW_FIXTURES", "ORGANON_LEDGER_ANCHORS_FILE"
        ):
            env.pop(key, None)
        env["ORGANON_ROOT"] = str(work)
        baseline = _cli(env, "status", str(case))
        if (
            baseline["revision"] != 24 or baseline["open_challenges"]
            or baseline["project"]["approval_policy"] != "signed"
            or baseline["items"]["n_scope"]["approved"]
        ):
            raise AssertionError("temporary March case does not have the expected baseline")

        _put(
            env, case, INFERENCE, "inference",
            f"Adversarial development claim: use all {raw} raw snapshot rows as the service denominator; "
            f"this ignores the {excluded} rows excluded by the conservative check.",
            ("e_archive", "e_eligible", "pr_reanalysis"),
            {"denominator": raw, "classification": "synthetic_adversarial_claim"},
        )
        _put(
            env, case, INDICATOR, "indicator",
            f"Candidate service fractions with the erroneous raw denominator {raw}.",
            ("p_access", "n_scope", "pr_reanalysis", "e_eligible", INFERENCE),
            {"metric": "station_snapshot_row_service_fraction_by_action", "unit": "fraction [0,1]",
             "denominator": raw, "classification": "synthetic_adversarial_candidate"},
        )
        _put(
            env, case, REQUIREMENT, "requirement",
            f"Draft report would divide rental and return counts by {raw} raw rows.",
            ("p_access", "n_scope", INDICATOR, INFERENCE),
            {"denominator": raw, "classification": "synthetic_adversarial_candidate"},
        )
        before_challenge = _cli(env, "status", str(case))
        if any(before_challenge["items"][item_id]["contested"] for item_id in DESCENDANTS):
            raise AssertionError("new candidate was contested before a challenge")
        challenge = _cli(
            env, "challenge", str(case), "e_eligible", INFERENCE,
            "--reason", f"Published exclusions require {eligible}, not raw {raw}, as denominator",
            "--actor", CHALLENGER,
        )
        challenged = _cli(env, "status", str(case))
        challenge_seq = challenge["seq"]
        if (
            challenged["open_challenges"][0]["seq"] != challenge_seq
            or any(not challenged["items"][item_id]["contested"] for item_id in DESCENDANTS)
            or not challenged["items"]["e_eligible"]["contested"]
        ):
            raise AssertionError("challenge did not contest evidence and every candidate descendant")
        challenged_blockers = {
            "study": _assert_blocker(env, case, "study", INDICATOR),
            "observe": _assert_blocker(env, case, "observe", INFERENCE),
            "specify": _assert_blocker(env, case, "specify", REQUIREMENT),
        }
        rejected_early = _expect_rejection(
            env, case, "resolution needs a later synthesis or assessment item",
            "resolve-challenge", str(case), str(challenge_seq), "syn_limit", "--actor", AUTHOR,
        )

        _put(
            env, case, INFERENCE, "inference",
            f"Correction: the earlier {raw} denominator claim is rejected; "
            f"{raw} - {excluded} = {eligible} eligible snapshot rows.",
            ("e_archive", "e_eligible", "e_excluded", "pr_reanalysis"),
            {"denominator": eligible, "rejected_raw_denominator": raw,
             "classification": "development_correction", "disposition": "rejected_raw_claim"},
        )
        invalidated = _cli(env, "status", str(case))
        if (
            not invalidated["items"][INDICATOR]["stale"]
            or not invalidated["items"][REQUIREMENT]["stale"]
            or challenge_seq not in [entry["seq"] for entry in invalidated["open_challenges"]]
        ):
            raise AssertionError("correcting the disputed inference did not invalidate descendants")

        _put(
            env, case, SYNTHESIS, "synthesis",
            f"The adversarial branch claimed {raw} raw rows. Published e_eligible and e_excluded "
            f"show {excluded} exclusions, so only {eligible} rows enter both descriptive fractions. "
            "Retain the rejected claim for audit; neither count measures lived access or impact.",
            (INFERENCE, "e_eligible", "e_excluded", "pr_reanalysis", "p_access", "n_scope"),
            {"denominator": eligible, "rejected_raw_denominator": raw,
             "excluded_rows": excluded, "classification": "development_reviewed_correction"},
        )
        rejected_unreviewed = _expect_rejection(
            env, case, "resolution needs an independent accepted item review",
            "resolve-challenge", str(case), str(challenge_seq), SYNTHESIS, "--actor", AUTHOR,
        )
        rejected_self_review = _expect_rejection(
            env, case, "item reviewer must differ from its author",
            "review", str(case), SYNTHESIS, "--verdict", "accept",
            "--reason", "Self review must be refused", "--actor", AUTHOR,
        )
        review = _cli(
            env, "review", str(case), SYNTHESIS, "--verdict", "accept",
            "--reason", "Checked both branches and the pinned exclusion arithmetic",
            "--actor", REVIEWER,
        )
        ancestors = {
            item["id"] for item in _cli(env, "trace", str(case), SYNTHESIS)["ancestors"]
        }
        if not {INFERENCE, "e_eligible", "e_excluded"} <= ancestors:
            raise AssertionError("corrected synthesis did not preserve both challenged branches")

        _put(
            env, case, INDICATOR, "indicator",
            f"Two descriptive service fractions over {eligible} eligible snapshot rows; "
            f"the earlier raw denominator {raw} is rejected.",
            ("p_access", "n_scope", "pr_reanalysis", "e_eligible", "e_rental", "e_return", SYNTHESIS),
            {"metric": "station_snapshot_row_service_fraction_by_action", "unit": "fraction [0,1]",
             "denominator": eligible, "rejected_raw_denominator": raw,
             "classification": "development_corrected_candidate"},
        )
        _put(
            env, case, REQUIREMENT, "requirement",
            f"Draft report must divide rental and return counts by {eligible} eligible rows, "
            f"disclose {excluded} exclusions, and label the {raw} raw-row claim rejected.",
            ("p_access", "n_scope", INDICATOR, SYNTHESIS, "e_eligible", "e_excluded"),
            {"denominator": eligible, "rejected_raw_denominator": raw,
             "classification": "development_corrected_candidate", "decision_status": "pending"},
        )
        before_resolution = _cli(env, "status", str(case))
        if any(
            before_resolution["items"][item_id]["stale"]
            or not before_resolution["items"][item_id]["contested"]
            or before_resolution["items"][item_id]["data"]["denominator"] != eligible
            for item_id in (*DESCENDANTS, SYNTHESIS)
        ):
            raise AssertionError("corrected current descendants must remain blocked until resolution")

        resolution = _cli(
            env, "resolve-challenge", str(case), str(challenge_seq), SYNTHESIS,
            "--actor", AUTHOR,
        )
        resolved = _cli(env, "status", str(case))
        if resolved["open_challenges"] or any(
            resolved["items"][item_id]["stale"]
            or resolved["items"][item_id]["contested"]
            or resolved["items"][item_id]["data"]["denominator"] != eligible
            for item_id in (*DESCENDANTS, SYNTHESIS)
        ):
            raise AssertionError("resolution left a false or blocked current candidate")
        resolved_study = _cli(env, "gate", str(case), "study")
        resolved_observe = _cli(env, "gate", str(case), "observe")
        resolved_specify = _cli(env, "gate", str(case), "specify")
        if any(
            "has an unresolved contradiction" in blocker
            for gate in (resolved_study, resolved_observe, resolved_specify)
            for blocker in gate["blockers"]
        ):
            raise AssertionError("resolved challenge still blocks a phase")
        critique = _cli(env, "gate", str(case), "critique")
        if (
            resolved["items"]["n_scope"]["approved"]
            or "n_scope requires a verified human approval" not in critique["blockers"]
        ):
            raise AssertionError("challenge probe bypassed the normative approval gate")

        evidence = resolved["items"]["e_eligible"]
        _put(
            env, case, "e_eligible", "evidence",
            evidence["text"] + " Metadata clarification on the same pinned bytes; no new observation.",
            tuple(evidence["deps"]), evidence["data"],
        )
        reopened = _cli(env, "status", str(case))
        reopened_blockers = {
            "study": _assert_blocker(env, case, "study", INDICATOR),
            "observe": _assert_blocker(env, case, "observe", INFERENCE),
            "specify": _assert_blocker(env, case, "specify", REQUIREMENT),
        }
        if (
            challenge_seq not in [entry["seq"] for entry in reopened["open_challenges"]]
            or any(not reopened["items"][item_id]["stale"] for item_id in (*DESCENDANTS, SYNTHESIS))
            or any(not reopened["items"][item_id]["contested"] for item_id in (*DESCENDANTS, SYNTHESIS))
            or reopened["items"]["e_eligible"]["data"] != evidence["data"]
        ):
            raise AssertionError("same-byte evidence revision did not reopen reviewed resolution")

        final_bytes = (case / "organon.json").read_bytes()
        final = json.loads(final_bytes)
        initial_events = source["events"]
        if final["project"] != source["project"] or final["events"][:24] != initial_events:
            raise AssertionError("derived ledger lost the historical event prefix")
        appended_kinds = [event["kind"] for event in final["events"][24:]]
        if set(appended_kinds) - {"item_put", "challenge", "item_review", "challenge_resolved"}:
            raise AssertionError("probe wrote an approval, phase advance, or other unexpected event")
        protected_unchanged = all(path.read_bytes() == original_bytes[path] for path in PROTECTED)
        if not protected_unchanged:
            raise AssertionError("a published or historical source changed during the probe")
        if derived_case is not None:
            derived_case.mkdir(parents=True)
            (derived_case / "organon.json").write_bytes(final_bytes)
            (derived_case / "seed.json").write_bytes(original_bytes[SEED])
            manifest = {
                "schema": 1,
                "classification": "development_adversarial_challenge_derivative",
                "source": str(SOURCE_LEDGER.relative_to(ROOT)),
                "source_sha256": _sha256(original_bytes[SOURCE_LEDGER]),
                "seed_sha256": _sha256(original_bytes[SEED]),
                "derived_sha256": _sha256(final_bytes),
                "source_event_count": 24,
                "derived_event_count": len(final["events"]),
                "historical_prefix_head_hash": source["events"][23]["hash"],
                "human_approval": "absent",
                "criterion_5": "not_assessed",
            }
            (derived_case / "manifest.json").write_text(
                json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                encoding="utf-8",
            )

        return {
            "schema": 1,
            "classification": "public_development_adversarial_challenge_probe",
            "transport": "installed_organon_cli",
            "source": str(SOURCE_LEDGER.relative_to(ROOT)),
            "source_sha256": {
                "historical_ledger": _sha256(original_bytes[SOURCE_LEDGER]),
                "seed": _sha256(original_bytes[SEED]),
                **source_hashes,
            },
            "denominator_source_check": {
                "raw_rows": raw, "excluded_rows": excluded, "eligible_rows": eligible,
                "published_denominator": published["snapshot_row_service"]["denominator"],
                "detection": "manual_challenge_after_pinned_source_assertion",
            },
            "adversarial_claim": {
                "classification": "synthetic_on_authentic_published_counts",
                "inference": INFERENCE, "indicator": INDICATOR, "requirement": REQUIREMENT,
                "wrong_denominator": raw,
            },
            "baseline": {
                "revision": baseline["revision"],
                "approval_policy": baseline["project"]["approval_policy"],
                "norm_approved": baseline["items"]["n_scope"]["approved"],
            },
            "challenged": {
                **_snapshot(challenged, ("e_eligible", *DESCENDANTS)),
                "challenge_seq": challenge_seq,
                "phase_blockers": challenged_blockers,
            },
            "rejected_operations": {
                "premature_synthesis": rejected_early,
                "unreviewed_synthesis": rejected_unreviewed,
                "self_review": rejected_self_review,
            },
            "corrected_inference_invalidated": _snapshot(invalidated, DESCENDANTS),
            "reviewed_synthesis": {
                "id": SYNTHESIS, "version": review["payload"]["version"],
                "review_seq": review["seq"], "review_actor": REVIEWER,
                "review_scope": "actor_separation_only_no_external_human_review",
                "ancestors": sorted(ancestors),
                "selected_denominator": eligible,
                "rejected_raw_denominator": raw,
            },
            "before_resolution": _snapshot(before_resolution, (*DESCENDANTS, SYNTHESIS)),
            "resolved": {
                **_snapshot(resolved, (*DESCENDANTS, SYNTHESIS)),
                "resolution_seq": resolution["seq"],
                "norm_approved": resolved["items"]["n_scope"]["approved"],
                "critique_blockers": critique["blockers"],
                "specify_blockers": resolved_specify["blockers"],
            },
            "reopened": {
                **_snapshot(reopened, ("e_eligible", *DESCENDANTS, SYNTHESIS)),
                "phase_blockers": reopened_blockers,
                "evidence_revision_scope": "metadata_clarification_same_pinned_bytes",
            },
            "derived_ledger": {
                "sha256": _sha256(final_bytes),
                "event_count": len(final["events"]),
                "historical_prefix_preserved": True,
                "appended_event_kinds": appended_kinds,
            },
            "protected_sources_unchanged": protected_unchanged,
            "human_approval": "absent",
            "criterion_5": "not_assessed",
            "field_impact": "not_assessed",
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Write the JSON receipt in addition to stdout")
    parser.add_argument("--derived-case", type=Path, help="Save an append-only development derivative")
    args = parser.parse_args()
    try:
        _validate_destinations(args.output, args.derived_case)
    except (ValueError, FileExistsError) as exc:
        parser.error(str(exc))
    receipt = run_probe(args.derived_case)
    encoded = json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if args.output is not None:
        lineage._write_receipt_atomic(args.output, encoded)
    print(encoded, end="")


if __name__ == "__main__":
    main()
