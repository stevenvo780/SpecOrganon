"""Verify the archived synthetic native-agent overlap development trial.

Run from any directory with ``python3 scripts/check_native_overlap.py``. The
default command checks both source ledgers and worker logs against the saved
report. Use ``--write-report`` to regenerate that report after reviewing new
source evidence. This verifier reads files only unless that flag is supplied.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = Path("experiments/development/native_overlap_2026-09-26.json")
ROUND_ONE = Path("cases/synthetic_overlap/organon.json")
ROUND_TWO = Path("cases/synthetic_overlap_round2/organon.json")
WORKER_LOGS = {
    prefix: Path(f"experiments/development/native_overlap_round2_{prefix}.json")
    for prefix in ("a", "b")
}
WRITER_SCRIPT = Path("scripts/concurrent_agent_writer.py")
ACTORS = {prefix: f"agent:overlap_writer_{prefix}" for prefix in ("a", "b")}
EXPECTED_HEADS = {
    1: "c4ab239fe5cfbb20fe355dfb31c172f767ecc0e6e3d5c5c2f42fe651fab432ee",
    2: "d92e5f9e1914989e6386b85982eb1c8339860ff53d7464b14b5732b00f6ba968",
}
EXPECTED_CONFLICTS = {"a": 39, "b": 40}
EXPECTED_OVERLAP_NS = 487_098_218
ZERO_HASH = "0" * 64


class VerificationError(ValueError):
    """Archived trial evidence differs from the expected fixture."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise VerificationError(message)


def load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VerificationError(f"cannot read {path}: {exc}") from exc
    require(isinstance(data, dict), f"{path}: expected JSON object")
    return data


def file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_digest(value: Any) -> str:
    canonical = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def expected_ids(prefix: str) -> list[str]:
    return [f"{prefix}_{number:03d}" for number in range(1, 41)]


def check_ledger(root: Path, relative_path: Path, round_number: int) -> dict[str, Any]:
    path = root / relative_path
    ledger = load_json(path)
    require(ledger.get("schema") == 1, f"{relative_path}: schema mismatch")
    project = ledger.get("project")
    require(isinstance(project, dict), f"{relative_path}: missing project")
    require(project.get("created_by") == "agent:controller", f"{relative_path}: controller mismatch")
    require(project.get("approval_policy") == "fixture", f"{relative_path}: policy mismatch")
    require(project.get("domain") == "fixture", f"{relative_path}: domain mismatch")
    events = ledger.get("events")
    expected_count = 41 if round_number == 1 else 81
    require(isinstance(events, list) and len(events) == expected_count,
            f"{relative_path}: expected {expected_count} events")

    prior_hash = ZERO_HASH
    actual_ids: dict[str, list[str]] = {"a": [], "b": []}
    actors: list[str] = []
    all_ids: list[str] = []
    for sequence, event in enumerate(events, start=1):
        require(isinstance(event, dict), f"{relative_path}: event {sequence} is not an object")
        require(type(event.get("seq")) is int and event["seq"] == sequence,
                f"{relative_path}: sequence mismatch at {sequence}")
        require(event.get("prev_hash") == prior_hash,
                f"{relative_path}: broken previous hash at {sequence}")
        supplied_hash = event.get("hash")
        require(isinstance(supplied_hash, str) and len(supplied_hash) == 64,
                f"{relative_path}: missing digest at {sequence}")
        digest = canonical_digest({key: value for key, value in event.items() if key != "hash"})
        require(supplied_hash == digest, f"{relative_path}: digest mismatch at {sequence}")
        prior_hash = supplied_hash

        actor = event.get("actor")
        payload = event.get("payload")
        require(event.get("kind") == "item_put" and isinstance(payload, dict),
                f"{relative_path}: unexpected event at {sequence}")
        item_id = payload.get("id")
        require(isinstance(item_id, str), f"{relative_path}: missing ID at {sequence}")
        actors.append(actor)
        all_ids.append(item_id)
        if sequence == 1:
            require(actor == "agent:controller" and item_id == "p1",
                    f"{relative_path}: controller event mismatch")
            require(payload.get("kind") == "problem" and payload.get("version") == 1
                    and payload.get("deps") == {} and payload.get("data") == {},
                    f"{relative_path}: controller payload mismatch")
        else:
            prefix = next((key for key, value in ACTORS.items() if value == actor), None)
            require(prefix is not None, f"{relative_path}: unexpected actor at {sequence}")
            actual_ids[prefix].append(item_id)
            require(payload.get("kind") == "actor" and payload.get("version") == 1
                    and payload.get("deps") == {"p1": 1}
                    and payload.get("data") == {"origin": "synthetic_concurrency_trial"},
                    f"{relative_path}: worker payload mismatch at {sequence}")

    require(len(set(all_ids)) == len(all_ids), f"{relative_path}: duplicate item ID")
    require(actual_ids["a"] == expected_ids("a"), f"{relative_path}: writer A IDs differ")
    require(actual_ids["b"] == ([] if round_number == 1 else expected_ids("b")),
            f"{relative_path}: writer B IDs differ")
    require(prior_hash == EXPECTED_HEADS[round_number], f"{relative_path}: head hash differs")
    actor_switches = sum(left != right for left, right in zip(actors, actors[1:]))
    require(actor_switches == (1 if round_number == 1 else 80),
            f"{relative_path}: unexpected actor switches")
    if round_number == 2:
        expected_actors = ["agent:controller"] + [
            ACTORS[prefix] for _ in range(40) for prefix in ("a", "b")
        ]
        require(actors == expected_actors, f"{relative_path}: actor order differs")

    return {
        "path": relative_path.as_posix(),
        "file_sha256": file_digest(path),
        "event_count": len(events),
        "item_count": len(all_ids),
        "actor_counts": dict(sorted(Counter(actors).items())),
        "actor_switches": actor_switches,
        "head_hash": prior_hash,
        "hash_chain_verified": True,
        "exact_ids_verified": True,
    }


def utc_time(value: Any, label: str) -> datetime:
    require(isinstance(value, str), f"{label}: missing timestamp")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise VerificationError(f"{label}: invalid timestamp") from exc
    require(parsed.tzinfo is not None and parsed.utcoffset().total_seconds() == 0,
            f"{label}: timestamp must be UTC")
    return parsed.astimezone(timezone.utc)


def check_worker_log(root: Path, prefix: str) -> dict[str, Any]:
    relative_path = WORKER_LOGS[prefix]
    path = root / relative_path
    log = load_json(path)
    require(log.get("schema") == 1 and log.get("prefix") == prefix,
            f"{relative_path}: schema or prefix mismatch")
    require(log.get("actor") == ACTORS[prefix] and log.get("count") == 40,
            f"{relative_path}: actor or count mismatch")
    require(log.get("ids") == expected_ids(prefix), f"{relative_path}: IDs differ")
    require(log.get("revision_conflicts_retried") == EXPECTED_CONFLICTS[prefix],
            f"{relative_path}: retry count differs")
    start = log.get("start_monotonic_ns")
    end = log.get("end_monotonic_ns")
    require(type(start) is int and type(end) is int and 0 < start < end,
            f"{relative_path}: invalid monotonic interval")
    ready_utc = utc_time(log.get("ready_at_utc"), f"{relative_path} ready")
    started_utc = utc_time(log.get("started_at_utc"), f"{relative_path} started")
    ended_utc = utc_time(log.get("ended_at_utc"), f"{relative_path} ended")
    require(ready_utc <= started_utc < ended_utc, f"{relative_path}: UTC timestamps out of order")
    return {
        "path": relative_path.as_posix(),
        "file_sha256": file_digest(path),
        "actor": log["actor"],
        "count": log["count"],
        "start_monotonic_ns": start,
        "end_monotonic_ns": end,
        "duration_ns": end - start,
        "revision_conflicts_retried": log["revision_conflicts_retried"],
    }


def build_report(root: Path) -> dict[str, Any]:
    first = check_ledger(root, ROUND_ONE, 1)
    second = check_ledger(root, ROUND_TWO, 2)
    logs = {prefix: check_worker_log(root, prefix) for prefix in ("a", "b")}
    overlap_start = max(logs["a"]["start_monotonic_ns"], logs["b"]["start_monotonic_ns"])
    overlap_end = min(logs["a"]["end_monotonic_ns"], logs["b"]["end_monotonic_ns"])
    overlap_ns = max(0, overlap_end - overlap_start)
    require(overlap_ns == EXPECTED_OVERLAP_NS, "round 2: interval overlap differs")
    return {
        "schema": 1,
        "date_utc": "2026-09-26",
        "kind": "native_agent_overlap_development_trial",
        "classification": "one synthetic development trial; not field or confirmatory validation",
        "verification_command": "python3 scripts/check_native_overlap.py",
        "writer_script": {
            "path": WRITER_SCRIPT.as_posix(),
            "file_sha256": file_digest(root / WRITER_SCRIPT),
            "max_attempts_per_item": 100,
            "backoff_initial_ms": 2,
            "backoff_multiplier": 1.4,
            "backoff_cap_ms": 15,
            "pacing_after_success_ms": 3,
        },
        "round_1": {
            "ledger": first,
            "reported_writer_b_failure": {
                "exit_code": 1,
                "error": "ConflictError: revision conflict: expected 40, current 41",
                "source": "original run observation; writer B stderr is not archived",
                "independently_rechecked_from_archived_files": False,
            },
            "writer_b_persisted_items": 0,
        },
        "round_2": {
            "ledger": second,
            "worker_logs": logs,
            "overlap_start_monotonic_ns": overlap_start,
            "overlap_end_monotonic_ns": overlap_end,
            "worker_interval_overlap_ns": overlap_ns,
            "worker_interval_overlap_seconds": overlap_ns / 1_000_000_000,
            "distinct_worker_items": 80,
        },
        "interpretation": [
            "Round 1 is a negative result: a stale revision ended writer B before it persisted an item.",
            "Round 2 used bounded ConflictError retries with backoff and 3 ms pacing after each successful write.",
            "The worker logs show overlapping active intervals; the ledger shows interleaved, serial commits without lost IDs.",
            "Actor labels and local logs do not authenticate the native agents or prove a speed, quality, or cost advantage.",
            "This synthetic development trial is neither field evidence nor sealed confirmatory validation.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT, help="repository root to check")
    parser.add_argument("--write-report", action="store_true", help="regenerate the saved JSON report")
    args = parser.parse_args()
    root = args.root.resolve()
    report = build_report(root)
    path = root / REPORT_PATH
    if args.write_report:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                        encoding="utf-8")
    else:
        require(load_json(path) == report, f"{REPORT_PATH}: report differs; review evidence before regeneration")
    print("PASS: round 1 41 events (A 40, B 0); round 2 81 events (A 40, B 40), "
          f"80 actor switches, {EXPECTED_OVERLAP_NS} ns interval overlap, retries A 39/B 40")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except VerificationError as exc:
        raise SystemExit(f"FAIL: {exc}") from exc
