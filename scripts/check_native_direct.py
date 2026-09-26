"""Read-only verification of the archived native direct synthetic trial.

Run ``python3 scripts/check_native_direct.py`` from any directory, or pass
``--root`` for a separate checkout. Receipts and actor labels are self-declared
evidence; these checks do not authenticate the agents or prove model identity.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
LEDGER = Path("cases/synthetic_native_direct/organon.json")
RECEIPTS = {
    (round_name, worker): Path(
        f"experiments/development/native_direct_{'overlap_' if round_name == 'overlap' else ''}"
        f"{worker}_2026-09-26.json"
    )
    for round_name in ("first", "overlap")
    for worker in ("a", "b")
}
ACTORS = {worker: f"agent:native_direct_{worker}" for worker in ("a", "b")}
HEAD_HASH = "1499d0aade0dd3300fd90551e309e50b55fee228259a136c3833df8397e9fa96"
ZERO_HASH = "0" * 64
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
ARCHIVED_CASE = "/workspace/SpecOrganon/cases/synthetic_native_direct"
WHEEL_SHA256 = "30318e4c8efbd77c9ca10953d018bad9e0d207ff4bafe8bc0369e599b2bfa8f4"
WHEEL = Path("dist/specorganon-0.1.0-py3-none-any.whl")
# UTC stamps have microsecond precision; 1 ms covers rounding and observed
# clock-read skew (under 30 us) while rejecting material timeline changes.
CLOCK_TOLERANCE_NS = 1_000_000


class VerificationError(ValueError):
    """An archived ledger or receipt violates the expected trial record."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise VerificationError(message)


def load_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise VerificationError(f"{path}: cannot load JSON: {exc}") from exc
    require(isinstance(value, dict), f"{path}: expected JSON object")
    return value


def canonical_hash(value: dict[str, Any]) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def expected_events() -> list[tuple[str, str, str, str]]:
    events = [("p1", "agent:controller", "problem", "Synthetic shared problem for native direct writers")]
    for worker in ("a", "b"):
        kind = "actor" if worker == "a" else "boundary"
        events.extend(
            (f"{worker}{number}", ACTORS[worker], kind, f"Synthetic native {kind} {worker}{number}")
            for number in range(1, 5)
        )
    for number in range(1, 11):
        for worker in ("a", "b"):
            item_id = f"{worker * 2}{number:02d}"
            kind = "actor" if worker == "a" else "boundary"
            events.append(
                (item_id, ACTORS[worker], kind, f"Synthetic native overlap {kind} {item_id}")
            )
    return events


def check_ledger(root: Path) -> dict[str, dict[str, Any]]:
    ledger = load_object(root / LEDGER)
    require(ledger.get("schema") == 1, f"{LEDGER}: schema mismatch")
    project = ledger.get("project")
    require(isinstance(project, dict), f"{LEDGER}: missing project")
    require(
        project.get("created_by") == "agent:controller"
        and project.get("approval_policy") == "fixture"
        and project.get("domain") == "fixture",
        f"{LEDGER}: project fixture metadata mismatch",
    )
    events = ledger.get("events")
    expected = expected_events()
    require(isinstance(events, list) and len(events) == len(expected), f"{LEDGER}: expected 29 events")

    by_id: dict[str, dict[str, Any]] = {}
    previous_hash = ZERO_HASH
    for sequence, (event, (item_id, actor, kind, item_text)) in enumerate(
        zip(events, expected, strict=True), start=1
    ):
        label = f"{LEDGER}: event {sequence}"
        require(isinstance(event, dict), f"{label}: expected object")
        require(
            set(event) == {"actor", "at", "hash", "kind", "payload", "prev_hash", "seq"},
            f"{label}: event fields mismatch",
        )
        require(type(event["seq"]) is int and event["seq"] == sequence, f"{label}: sequence mismatch")
        require(event["prev_hash"] == previous_hash, f"{label}: previous hash mismatch")
        digest = event["hash"]
        require(isinstance(digest, str) and SHA256_RE.fullmatch(digest) is not None, f"{label}: invalid hash")
        calculated = canonical_hash({key: value for key, value in event.items() if key != "hash"})
        require(digest == calculated, f"{label}: canonical hash mismatch")
        previous_hash = digest
        parse_utc(event["at"], f"{label} at")
        require(event["kind"] == "item_put" and event["actor"] == actor, f"{label}: actor or kind mismatch")
        payload = event["payload"]
        require(isinstance(payload, dict), f"{label}: payload must be an object")
        require(
            set(payload) == {"data", "deps", "id", "kind", "text", "version"},
            f"{label}: payload fields mismatch",
        )
        require(
            payload["id"] == item_id
            and payload["kind"] == kind
            and payload["text"] == item_text
            and type(payload["version"]) is int
            and payload["version"] == 1
            and payload["deps"] == ({} if sequence == 1 else {"p1": 1})
            and payload["data"] == {},
            f"{label}: item ID, kind, text, version, deps, or data mismatch",
        )
        by_id[item_id] = event
    require(previous_hash == HEAD_HASH, f"{LEDGER}: archived head hash mismatch")
    require(len(by_id) == 29, f"{LEDGER}: duplicate item ID")
    return by_id


def positive_interval(record: dict[str, Any], start_key: str, end_key: str, label: str) -> tuple[int, int]:
    start, end = record.get(start_key), record.get(end_key)
    require(
        type(start) is int and type(end) is int and 0 < start < end,
        f"{label}: invalid monotonic interval",
    )
    return start, end


def parse_utc(value: Any, label: str) -> datetime:
    require(isinstance(value, str), f"{label}: missing UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise VerificationError(f"{label}: invalid UTC timestamp") from exc
    require(
        parsed.tzinfo is not None and parsed.utcoffset() == timedelta(0),
        f"{label}: timestamp must have UTC offset zero",
    )
    return parsed.astimezone(timezone.utc)


def utc_delta_ns(start: datetime, end: datetime) -> int:
    delta = end - start
    return (delta.days * 86_400 + delta.seconds) * 1_000_000_000 + delta.microseconds * 1_000


def positive_utc_interval(
    record: dict[str, Any], start_key: str, end_key: str, label: str
) -> tuple[datetime, datetime]:
    start = parse_utc(record.get(start_key), f"{label} {start_key}")
    end = parse_utc(record.get(end_key), f"{label} {end_key}")
    require(start < end, f"{label}: invalid UTC interval")
    return start, end


def check_clock_duration(
    utc_interval: tuple[datetime, datetime], monotonic_interval: tuple[int, int], label: str
) -> None:
    utc_ns = utc_delta_ns(*utc_interval)
    monotonic_ns = monotonic_interval[1] - monotonic_interval[0]
    require(
        abs(utc_ns - monotonic_ns) <= CLOCK_TOLERANCE_NS,
        f"{label}: UTC and monotonic durations differ by more than {CLOCK_TOLERANCE_NS} ns",
    )


def expected_ids(round_name: str, worker: str) -> list[str]:
    if round_name == "first":
        return [f"{worker}{number}" for number in range(1, 5)]
    return [f"{worker * 2}{number:02d}" for number in range(1, 11)]


def check_receipt(
    root: Path, round_name: str, worker: str, by_id: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    relative_path = RECEIPTS[round_name, worker]
    receipt = load_object(root / relative_path)
    label = str(relative_path)
    actor = ACTORS[worker]
    require(receipt.get("actor_label") == actor, f"{label}: actor label mismatch")
    require(receipt.get("actor_label_is_self_declared") is True, f"{label}: actor label caveat missing")
    require(receipt.get("fixtures_allowed", receipt.get("fixture_allowed")) is True, f"{label}: fixture flag mismatch")
    if worker == "a":
        expected_trial = "synthetic_native_direct" + ("_overlap" if round_name == "overlap" else "")
        require(
            receipt.get("trial") == expected_trial and receipt.get("worker") == "native_direct_a",
            f"{label}: trial or worker mismatch",
        )

    case = receipt.get("case")
    require(case == ARCHIVED_CASE, f"{label}: archived case path mismatch")
    wheel_sha = receipt.get("wheel_sha256")
    require(wheel_sha == WHEEL_SHA256, f"{label}: archived wheel SHA-256 mismatch")
    interval_keys = {
        ("first", "a"): ("sequence_started_monotonic_ns", "sequence_ended_monotonic_ns"),
        ("first", "b"): ("sequence_start_monotonic_ns", "sequence_end_monotonic_ns"),
        ("overlap", "a"): ("release_monotonic_ns", "ended_monotonic_ns"),
        ("overlap", "b"): ("release_monotonic_ns", "end_monotonic_ns"),
    }
    interval = positive_interval(receipt, *interval_keys[round_name, worker], label)
    utc_interval_keys = {
        ("first", "a"): ("sequence_started_utc", "sequence_ended_utc"),
        ("first", "b"): ("sequence_start_utc", "sequence_end_utc"),
        ("overlap", "a"): ("release_utc", "ended_utc"),
        ("overlap", "b"): ("release_utc", "end_utc"),
    }
    utc_interval = positive_utc_interval(receipt, *utc_interval_keys[round_name, worker], label)
    check_clock_duration(utc_interval, interval, label)
    duration_key = "sequence_duration_ns" if round_name == "first" else "release_to_end_duration_ns"
    if duration_key in receipt:
        require(
            type(receipt[duration_key]) is int and receipt[duration_key] == interval[1] - interval[0],
            f"{label}: sequence duration mismatch",
        )

    entries_key = "commands" if worker == "a" else "results"
    argv_key = "argv" if worker == "a" else "command"
    start_key = "started_monotonic_ns" if worker == "a" else "start_monotonic_ns"
    end_key = "ended_monotonic_ns" if worker == "a" else "end_monotonic_ns"
    entries = receipt.get(entries_key)
    ids = expected_ids(round_name, worker)
    require(isinstance(entries, list) and len(entries) == len(ids), f"{label}: command count mismatch")
    command_intervals: list[tuple[int, int]] = []
    command_utc_intervals: list[tuple[datetime, datetime]] = []
    binary: str | None = None
    for index, (entry, item_id) in enumerate(zip(entries, ids, strict=True), start=1):
        entry_label = f"{label}: command {index}"
        require(isinstance(entry, dict) and entry.get("id") == item_id, f"{entry_label}: ID mismatch")
        event = by_id[item_id]
        payload = event["payload"]
        argv = entry.get(argv_key)
        require(isinstance(argv, list) and len(argv) == 16, f"{entry_label}: malformed CLI argv")
        command_binary = argv[0]
        require(
            isinstance(command_binary, str) and Path(command_binary).name == "organon",
            f"{entry_label}: CLI binary mismatch",
        )
        binary = binary or command_binary
        require(command_binary == binary, f"{entry_label}: CLI binary changed within receipt")
        require(
            argv == [
                binary, "put", case, item_id, "--kind", payload["kind"], "--text", payload["text"],
                "--ref", "p1", "--actor", actor, "--expected-version", "0",
                "--expected-deps", '{"p1":1}',
            ],
            f"{entry_label}: CLI argv or optimistic guards mismatch",
        )
        command_interval = positive_interval(entry, start_key, end_key, entry_label)
        command_utc_interval = positive_utc_interval(
            entry,
            "started_utc" if worker == "a" else "start_utc",
            "ended_utc" if worker == "a" else "end_utc",
            entry_label,
        )
        check_clock_duration(command_utc_interval, command_interval, entry_label)
        require(
            interval[0] <= command_interval[0] < command_interval[1] <= interval[1],
            f"{entry_label}: command outside receipt interval",
        )
        require(
            utc_interval[0] <= command_utc_interval[0] < command_utc_interval[1] <= utc_interval[1],
            f"{entry_label}: command outside receipt UTC interval",
        )
        if command_intervals:
            require(
                command_intervals[-1][1] <= command_interval[0],
                f"{entry_label}: worker command intervals out of order",
            )
            require(
                command_utc_intervals[-1][1] <= command_utc_interval[0],
                f"{entry_label}: worker UTC command intervals out of order",
            )
        command_intervals.append(command_interval)
        command_utc_intervals.append(command_utc_interval)
        ledger_at = parse_utc(event["at"], f"{entry_label} ledger at")
        require(
            command_utc_interval[0] < ledger_at + timedelta(seconds=1)
            and command_utc_interval[1] >= ledger_at,
            f"{entry_label}: ledger event time outside command UTC window (1 s resolution)",
        )
        if "duration_ns" in entry:
            require(
                type(entry["duration_ns"]) is int
                and entry["duration_ns"] == command_interval[1] - command_interval[0],
                f"{entry_label}: command duration mismatch",
            )
        require(type(entry.get("exit_code")) is int and entry["exit_code"] == 0, f"{entry_label}: exit not zero")
        require(entry.get("stderr") == "" and entry.get("error") is None, f"{entry_label}: reported error")
        stdout = entry.get("stdout")
        require(isinstance(stdout, str), f"{entry_label}: missing stdout")
        try:
            result = json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise VerificationError(f"{entry_label}: stdout is not JSON: {exc}") from exc
        require(
            result == {"author": actor, "seq": event["seq"], **payload},
            f"{entry_label}: parsed CLI result differs from ledger",
        )
        require(
            type(entry.get("stdout_event_seq")) is int
            and entry["stdout_event_seq"] == event["seq"]
            and entry.get("stdout_event_id") == item_id,
            f"{entry_label}: recorded stdout event pointer mismatch",
        )
    if "cli_binary" in receipt:
        require(receipt["cli_binary"] == binary, f"{label}: declared CLI binary mismatch")
    return {
        "interval": interval,
        "utc_interval": utc_interval,
        "command_intervals": command_intervals,
        "case": case,
        "binary": binary,
        "wheel_sha256": wheel_sha,
        "count": len(entries),
    }


def verify(root: Path) -> dict[str, Any]:
    by_id = check_ledger(root)
    wheel_path = root / WHEEL
    wheel_file_verified = False
    if wheel_path.exists():
        require(wheel_path.is_file(), f"{WHEEL}: expected a wheel file")
        try:
            digest = hashlib.sha256(wheel_path.read_bytes()).hexdigest()
        except OSError as exc:
            raise VerificationError(f"{WHEEL}: cannot read wheel: {exc}") from exc
        require(digest == WHEEL_SHA256, f"{WHEEL}: wheel bytes SHA-256 mismatch")
        wheel_file_verified = True
    receipts = {
        (round_name, worker): check_receipt(root, round_name, worker, by_id)
        for round_name in ("first", "overlap")
        for worker in ("a", "b")
    }


    require(len({record["case"] for record in receipts.values()}) == 1, "receipt case paths differ")
    require(len({record["binary"] for record in receipts.values()}) == 1, "receipt CLI binaries differ")
    require(len({record["wheel_sha256"] for record in receipts.values()}) == 1, "declared wheel hashes differ")

    first_a = receipts["first", "a"]["interval"]
    first_b = receipts["first", "b"]["interval"]
    require(first_a[1] < first_b[0], "first round: A did not finish before B began")
    first_a_utc = receipts["first", "a"]["utc_interval"]
    first_b_utc = receipts["first", "b"]["utc_interval"]
    require(first_a_utc[1] < first_b_utc[0], "first round: UTC intervals are out of order")
    overlap_a = receipts["overlap", "a"]["interval"]
    overlap_b = receipts["overlap", "b"]["interval"]
    overlap_ns = min(overlap_a[1], overlap_b[1]) - max(overlap_a[0], overlap_b[0])
    require(overlap_ns > 0, "overlap round: worker intervals did not overlap")
    overlap_a_utc = receipts["overlap", "a"]["utc_interval"]
    overlap_b_utc = receipts["overlap", "b"]["utc_interval"]
    release_utc_delta_ns = utc_delta_ns(overlap_a_utc[0], overlap_b_utc[0])
    release_monotonic_delta_ns = overlap_b[0] - overlap_a[0]
    require(
        abs(release_utc_delta_ns - release_monotonic_delta_ns) <= CLOCK_TOLERANCE_NS,
        "overlap round: A/B UTC release delta disagrees with monotonic delta",
    )
    require(
        min(overlap_a_utc[1], overlap_b_utc[1]) > max(overlap_a_utc[0], overlap_b_utc[0]),
        "overlap round: UTC intervals did not overlap",
    )
    command_overlap_count = sum(
        min(a_end, b_end) > max(a_start, b_start)
        for a_start, a_end in receipts["overlap", "a"]["command_intervals"]
        for b_start, b_end in receipts["overlap", "b"]["command_intervals"]
    )
    require(command_overlap_count > 0, "overlap round: no CLI command intervals overlap")
    return {
        "status": "ok",
        "ledger_events": len(by_id),
        "hash_chain_verified": True,
        "head_hash": HEAD_HASH,
        "receipt_commands": sum(record["count"] for record in receipts.values()),
        "first_round_a_before_b": True,
        "alternating_overlap_events": 20,
        "overlap_interval_ns": overlap_ns,
        "overlapping_command_pairs": command_overlap_count,
        "wheel_sha256_declared_equal": True,
        "wheel_file_verified": wheel_file_verified,
        "agent_identity_authenticated": False,
    }


def negative_self_check(root: Path) -> None:
    """Exercise UTC cross-checks on copies, including a checkout without dist."""
    with tempfile.TemporaryDirectory(prefix="specorganon-native-direct-check-") as temporary:
        copy_root = Path(temporary)
        for relative_path in (LEDGER, *RECEIPTS.values()):
            copied = copy_root / relative_path
            copied.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(root / relative_path, copied)
        require(
            verify(copy_root)["wheel_file_verified"] is False,
            "negative self-check: checkout without dist was not accepted",
        )
        shifted_path = copy_root / RECEIPTS["overlap", "b"]
        shifted = load_object(shifted_path)
        entries = shifted.get("results")
        require(isinstance(entries, list), f"{shifted_path}: missing results")

        def shift_b_utc(amount: timedelta) -> None:
            for record in (shifted, *entries):
                require(isinstance(record, dict), f"{shifted_path}: malformed result")
                for key, value in record.items():
                    if key.endswith("_utc"):
                        shifted_time = parse_utc(value, f"{shifted_path} {key}") + amount
                        record[key] = shifted_time.isoformat()
            shifted_path.write_text(json.dumps(shifted), encoding="utf-8")

        shift_b_utc(timedelta(milliseconds=2))
        try:
            verify(copy_root)
        except VerificationError as exc:
            require(
                "A/B UTC release delta" in str(exc),
                f"negative self-check did not reach the cross-release check: {exc}",
            )
        else:
            raise VerificationError("negative self-check accepted B release UTC shifted by 2 ms")

        shift_b_utc(timedelta(minutes=10) - timedelta(milliseconds=2))
        try:
            verify(copy_root)
        except VerificationError as exc:
            require("UTC" in str(exc), f"negative self-check failed for an unrelated reason: {exc}")
        else:
            raise VerificationError("negative self-check accepted B overlap UTC shifted by ten minutes")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT, help="checkout root containing cases and experiments")
    parser.add_argument(
        "--self-check", action="store_true", help="test rejection of shifted UTC using temporary copies"
    )
    args = parser.parse_args()
    try:
        root = args.root.resolve()
        result = verify(root)
        if args.self_check:
            negative_self_check(root)
            result["negative_utc_self_check"] = True
    except VerificationError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
