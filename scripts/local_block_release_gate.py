"""Cooperative host-local release order for an unsealed candidate schedule.

Every invoker must use the same private ``gate_root``. The registry records
attempt 1 only. Its events and terminal evidence are locally declared bytes:
neither provider telemetry nor an external custodian is authenticated here.
The effective UID can rewrite its own registry or move its directories, so
this is a coordination aid, not a confirmatory release seal.

CLI::

    python scripts/local_block_release_gate.py terminal SCHEDULE RUN_ID GATE_ROOT \
        completed TRACE_SHA256 EVIDENCE.json
    python scripts/local_block_release_gate.py verify SCHEDULE RUN_ID GATE_ROOT RELEASE_DIR

Terminal evidence is a strict JSON object containing schema=1,
schedule_sha256, run_id, run_sha256, attempt_number=1, release_dir, status,
and trace_sha256. Additional receipt fields may be present. Its path and
SHA-256 of its bytes are recorded and checked again before later releases.
``completed`` also declares artifact_sha256; ``external_failure`` declares
incident_sha256. These digests are not checked against artifact or provider
bytes by this local gate.
"""

from __future__ import annotations

import argparse
import copy
import fcntl
import hashlib
import json
import math
import os
import secrets
import stat
import sys
from contextlib import ExitStack, contextmanager
from pathlib import Path
from typing import Any, Iterator

from analyze_confirmatory import AnalysisError, _validate_schedule
from local_run_admission import AdmissionError, configured_root
from tool_policy import (
    ToolPolicyError,
    _check_directory_chain,
    _open_directory_chain,
    _same_file_state,
)


SCHEMA = 1
CLASSIFICATION = "development_local_block_release_gate_unsealed"
CLAIM_CLASSIFICATION = "development_local_block_release_claim_unsealed"
TERMINAL_CLASSIFICATION = "development_local_block_terminal_unsealed"
STATE_NAME = "state.json"
PENDING_NAME = ".pending.json"
MAX_STATE_BYTES = 8 * 1024 * 1024
MAX_EVIDENCE_BYTES = 1024 * 1024
MAX_SCHEDULE_BYTES = 16 * 1024 * 1024
MAX_MANIFEST_BYTES = 1024 * 1024
CHUNK_SIZE = 64 * 1024
FILE_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
SHA256_ZERO = "0" * 64
CLAIM_FIELDS = frozenset({
    "kind", "sequence", "schedule_sha256", "run_id", "run_sha256",
    "block_id", "release_block_order", "order_position", "attempt_number",
    "release_dir", "previous_event_sha256", "event_sha256",
})
PUBLISHED_FIELDS = frozenset({
    "kind", "sequence", "schedule_sha256", "run_id", "run_sha256",
    "block_id", "release_block_order", "order_position", "attempt_number",
    "release_dir", "manifest_sha256", "previous_event_sha256", "event_sha256",
})
TERMINAL_FIELDS = frozenset({
    "kind", "sequence", "schedule_sha256", "run_id", "run_sha256",
    "block_id", "release_block_order", "order_position", "attempt_number",
    "release_dir", "status", "trace_sha256", "evidence_path",
    "evidence_sha256", "previous_event_sha256", "event_sha256",
})
STATE_FIELDS = frozenset({
    "schema", "classification", "schedule_sha256", "sequence",
    "head_sha256", "events", "state_sha256",
})
TERMINAL_STATUSES = frozenset({"completed", "truncated", "external_failure"})


class BlockReleaseError(ValueError):
    """The local release registry, claim, or terminal proof is untrustworthy."""


def _canonical(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, ensure_ascii=True,
                       separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _digest(value: Any) -> str:
    return _sha(_canonical(value))


def _is_sha256(value: Any) -> bool:
    return type(value) is str and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise BlockReleaseError("duplicate JSON object key")
        result[key] = value
    return result


def _reject_constant(_value: str) -> None:
    raise BlockReleaseError("non-JSON numeric constant")


def _finite_float(value: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise BlockReleaseError("nonfinite JSON number")
    return result


def _strict_json(data: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(data.decode("utf-8"), object_pairs_hook=_unique_pairs,
                           parse_constant=_reject_constant, parse_float=_finite_float)
    except BlockReleaseError:
        raise
    except (UnicodeError, ValueError, OverflowError, RecursionError) as exc:
        raise BlockReleaseError(f"{label} is not strict JSON") from exc
    if type(value) is not dict:
        raise BlockReleaseError(f"{label} must be an object")
    return value


def _absolute_path(raw: Path | str, label: str) -> Path:
    try:
        value = os.fspath(raw)
    except TypeError as exc:
        raise BlockReleaseError(f"{label} must be an absolute path without dot components") from exc
    if (type(value) is not str or not value.startswith("/") or value == "/"
        or value.endswith("/") or "\x00" in value
        or any(part in ("", ".", "..") for part in value.split("/")[1:])):
        raise BlockReleaseError(f"{label} must be an absolute path without dot components")
    return Path(value)


def _schedule(raw: Any) -> dict[str, Any]:
    try:
        snapshot = copy.deepcopy(raw)
        schedule, _, _ = _validate_schedule(snapshot)
        if schedule["study_limits"]["max_simultaneous_runs"] != 4:
            raise BlockReleaseError("schedule simultaneous release cap must be four")
        return schedule
    except BlockReleaseError:
        raise
    except (AnalysisError, KeyError, TypeError, ValueError, RuntimeError,
            RecursionError) as exc:
        raise BlockReleaseError("invalid candidate schedule") from exc


def _run(schedule: dict[str, Any], run_id: str) -> dict[str, Any]:
    if type(run_id) is not str:
        raise BlockReleaseError("run_id must be a string")
    for run in schedule["runs"]:
        if run["run_id"] == run_id:
            return run
    raise BlockReleaseError("run_id is absent from schedule")


def _read_named_file(directory_fd: int, name: str, maximum: int,
                     label: str, *, private: bool, durable: bool = False) -> bytes:
    fd = os.open(name, FILE_FLAGS, dir_fd=directory_fd)
    try:
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_uid != os.geteuid()
            or before.st_nlink != 1 or before.st_size > maximum
            or before.st_mode & 0o022
            or (private and stat.S_IMODE(before.st_mode) != 0o600)):
            raise BlockReleaseError(f"{label} is not an owned bounded regular file")
        chunks: list[bytes] = []
        remaining = maximum + 1
        while remaining:
            part = os.read(fd, min(CHUNK_SIZE, remaining))
            if not part:
                break
            chunks.append(part)
            remaining -= len(part)
        data = b"".join(chunks)
        after = os.fstat(fd)
        named = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        if (len(data) != before.st_size or len(data) > maximum
            or not _same_file_state(before, after)
            or not _same_file_state(before, named)):
            raise BlockReleaseError(f"{label} changed while reading")
        if durable:
            os.fsync(fd)
            os.fsync(directory_fd)
        return data
    finally:
        os.close(fd)


def _read_external_file(path: Path, maximum: int, label: str,
                        *, durable: bool = False) -> bytes:
    with ExitStack() as stack:
        parent_fd, name, chain = _open_directory_chain(path, label, stack)
        _check_directory_chain(chain, label)
        data = _read_named_file(parent_fd, name, maximum, label,
                                private=False, durable=durable)
        _check_directory_chain(chain, label)
        return data


def _validate_release_path(path: Path, *, must_exist: bool) -> None:
    with ExitStack() as stack:
        parent_fd, name, chain = _open_directory_chain(path, "release directory", stack)
        _check_directory_chain(chain, "release directory")
        parent = os.fstat(parent_fd)
        if parent.st_uid != os.geteuid() or parent.st_mode & 0o022:
            raise BlockReleaseError("release parent must be owned and not writable by others")
        if must_exist:
            fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                         dir_fd=parent_fd)
            stack.callback(os.close, fd)
            opened = os.fstat(fd)
            named = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
            if (not stat.S_ISDIR(opened.st_mode) or not _same_file_state(opened, named)
                or opened.st_uid != os.geteuid()
                or stat.S_IMODE(opened.st_mode) != 0o700):
                raise BlockReleaseError("release directory is not private and unchanged")
        else:
            try:
                os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                raise BlockReleaseError("release directory already exists")
        _check_directory_chain(chain, "release directory")


def _evidence(path: Path, expected: dict[str, Any], *, durable: bool = False) -> str:
    data = _read_external_file(path, MAX_EVIDENCE_BYTES, "terminal evidence",
                               durable=durable)
    item = _strict_json(data, "terminal evidence")
    for key, value in expected.items():
        if type(item.get(key)) is not type(value) or item.get(key) != value:
            raise BlockReleaseError(f"terminal evidence {key} differs from claim")
    if type(item.get("schema")) is not int or item["schema"] != 1:
        raise BlockReleaseError("terminal evidence schema must be integer 1")
    status = expected["status"]
    if status == "completed":
        if not _is_sha256(item.get("artifact_sha256")) or "incident_sha256" in item:
            raise BlockReleaseError("completed terminal evidence needs an artifact digest")
    elif status == "truncated":
        if ("artifact_sha256" in item and not _is_sha256(item["artifact_sha256"])) or "incident_sha256" in item:
            raise BlockReleaseError("truncated terminal evidence has invalid artifact or incident")
    elif (not _is_sha256(item.get("incident_sha256"))
          or "artifact_sha256" in item):
        raise BlockReleaseError("external failure evidence needs an incident digest")
    return _sha(data)


def _manifest_digest(release_dir: str) -> str:
    manifest = _absolute_path(Path(release_dir) / "manifest.json", "release manifest")
    return _sha(_read_external_file(manifest, MAX_MANIFEST_BYTES, "release manifest"))


def _empty_state(schedule_sha256: str) -> dict[str, Any]:
    body = {"schema": SCHEMA, "classification": CLASSIFICATION,
            "schedule_sha256": schedule_sha256, "sequence": 0,
            "head_sha256": SHA256_ZERO, "events": []}
    return {**body, "state_sha256": _digest(body)}


def _event(body: dict[str, Any]) -> dict[str, Any]:
    return {**body, "event_sha256": _digest(body)}


def _append(state: dict[str, Any], event: dict[str, Any]) -> dict[str, Any]:
    body = {key: value for key, value in state.items() if key != "state_sha256"}
    body["events"] = [*state["events"], event]
    body["sequence"] = event["sequence"]
    body["head_sha256"] = event["event_sha256"]
    return {**body, "state_sha256": _digest(body)}


def _event_body(run: dict[str, Any], schedule_sha256: str,
                release_dir: str, state: dict[str, Any], kind: str) -> dict[str, Any]:
    return {"kind": kind, "sequence": state["sequence"] + 1,
            "schedule_sha256": schedule_sha256,
            "run_id": run["run_id"], "run_sha256": run["run_sha256"],
            "block_id": run["block_id"],
            "release_block_order": run["release_block_order"],
            "order_position": run["order_position"], "attempt_number": 1,
            "release_dir": release_dir,
            "previous_event_sha256": state["head_sha256"]}


def _assert_claim_allowed(run: dict[str, Any], claims: dict[str, dict[str, Any]],
                          publications: dict[str, dict[str, Any]],
                          terminals: dict[str, dict[str, Any]],
                          schedule: dict[str, Any]) -> None:
    if run["run_id"] in claims:
        raise BlockReleaseError("scheduled run already has a release claim")
    if sum(run_id not in terminals for run_id in claims) >= 4:
        raise BlockReleaseError("four releases are already active")
    if run["order_position"] == 1:
        blocks: dict[str, dict[int, dict[str, Any]]] = {}
        for item in schedule["runs"]:
            blocks.setdefault(item["block_id"], {})[item["order_position"]] = item
        open_blocks = 0
        for positions in blocks.values():
            if positions[1]["run_id"] not in claims:
                continue
            if any(terminals.get(item["run_id"], {}).get("status") == "external_failure"
                   for item in positions.values()):
                continue
            if terminals.get(positions[3]["run_id"], {}).get("status") in ("completed", "truncated"):
                continue
            open_blocks += 1
        if open_blocks >= 4:
            raise BlockReleaseError("four blocks are already open")
        for previous in schedule["runs"]:
            if (previous["order_position"] == 1
                and previous["release_block_order"] < run["release_block_order"]
                and previous["run_id"] not in publications):
                raise BlockReleaseError("earlier block first release is not published")
    else:
        prior = next(item for item in schedule["runs"]
                     if item["block_id"] == run["block_id"]
                     and item["order_position"] == run["order_position"] - 1)
        terminal = terminals.get(prior["run_id"])
        if terminal is None or terminal["status"] not in ("completed", "truncated"):
            raise BlockReleaseError("prior arm lacks a completed or truncated terminal")


def _replay(state: dict[str, Any], schedule: dict[str, Any]) -> tuple[
    dict[str, dict[str, Any]], dict[str, dict[str, Any]], dict[str, dict[str, Any]]
]:
    claims: dict[str, dict[str, Any]] = {}
    publications: dict[str, dict[str, Any]] = {}
    terminals: dict[str, dict[str, Any]] = {}
    paths: set[str] = set()
    previous_sha = SHA256_ZERO
    by_run = {run["run_id"]: run for run in schedule["runs"]}
    for sequence, event in enumerate(state["events"], start=1):
        if type(event) is not dict or event.get("kind") not in ("claim", "published", "terminal"):
            raise BlockReleaseError("registry contains an unknown event")
        expected_keys = {"claim": CLAIM_FIELDS, "published": PUBLISHED_FIELDS,
                         "terminal": TERMINAL_FIELDS}[event["kind"]]
        if set(event) != expected_keys:
            raise BlockReleaseError("registry event fields are incomplete")
        if (type(event["sequence"]) is not int or event["sequence"] != sequence
            or event["previous_event_sha256"] != previous_sha
            or not _is_sha256(event["event_sha256"])):
            raise BlockReleaseError("registry event sequence or chain is damaged")
        body = {key: value for key, value in event.items() if key != "event_sha256"}
        if event["event_sha256"] != _digest(body):
            raise BlockReleaseError("registry event digest differs")
        previous_sha = event["event_sha256"]
        if (type(event["run_id"]) is not str or type(event["run_sha256"]) is not str
            or type(event["schedule_sha256"]) is not str
            or type(event["block_id"]) is not str
            or type(event["release_dir"]) is not str):
            raise BlockReleaseError("registry event identity has invalid types")
        run = by_run.get(event["run_id"])
        if run is None:
            raise BlockReleaseError("registry event names an unscheduled run")
        for key in ("run_sha256", "block_id", "release_block_order", "order_position"):
            if type(event[key]) is not type(run[key]) or event[key] != run[key]:
                raise BlockReleaseError("registry event differs from schedule")
        if (event["schedule_sha256"] != schedule["schedule_sha256"]
            or type(event["attempt_number"]) is not int
            or event["attempt_number"] != 1):
            raise BlockReleaseError("registry event has wrong schedule or attempt")
        release_dir = str(_absolute_path(event["release_dir"], "release directory"))
        if event["kind"] == "claim":
            _assert_claim_allowed(run, claims, publications, terminals, schedule)
            if release_dir in paths:
                raise BlockReleaseError("release directory is already claimed")
            paths.add(release_dir)
            claims[run["run_id"]] = event
        elif event["kind"] == "published":
            claim = claims.get(run["run_id"])
            if claim is None or run["run_id"] in publications or run["run_id"] in terminals:
                raise BlockReleaseError("publication lacks one pending release claim")
            if release_dir != claim["release_dir"]:
                raise BlockReleaseError("publication release directory differs from claim")
            if not _is_sha256(event["manifest_sha256"]):
                raise BlockReleaseError("published manifest digest is invalid")
            if _manifest_digest(release_dir) != event["manifest_sha256"]:
                raise BlockReleaseError("published manifest bytes changed")
            publications[run["run_id"]] = event
        else:
            claim = claims.get(run["run_id"])
            if claim is None or run["run_id"] not in publications or run["run_id"] in terminals:
                raise BlockReleaseError("terminal lacks one published active release claim")
            if release_dir != claim["release_dir"]:
                raise BlockReleaseError("terminal release directory differs from claim")
            if (type(event["status"]) is not str
                or event["status"] not in TERMINAL_STATUSES
                or not _is_sha256(event["trace_sha256"])):
                raise BlockReleaseError("terminal status or trace digest is invalid")
            evidence_path = _absolute_path(event["evidence_path"], "terminal evidence")
            if not _is_sha256(event["evidence_sha256"]):
                raise BlockReleaseError("terminal evidence digest is invalid")
            expected = {"schedule_sha256": schedule["schedule_sha256"],
                        "run_id": run["run_id"], "run_sha256": run["run_sha256"],
                        "attempt_number": 1, "release_dir": release_dir,
                        "status": event["status"], "trace_sha256": event["trace_sha256"]}
            if _evidence(evidence_path, expected) != event["evidence_sha256"]:
                raise BlockReleaseError("terminal evidence bytes changed")
            terminals[run["run_id"]] = event
    if state["sequence"] != len(state["events"]) or state["head_sha256"] != previous_sha:
        raise BlockReleaseError("registry head differs from events")
    return claims, publications, terminals


def _load_state(fd: int, schedule: dict[str, Any], *, allow_empty: bool) -> tuple[
    dict[str, Any], dict[str, dict[str, Any]], dict[str, dict[str, Any]],
    dict[str, dict[str, Any]]
]:
    entries = set(os.listdir(fd))
    if entries == set() and allow_empty:
        state = _empty_state(schedule["schedule_sha256"])
        return state, {}, {}, {}
    if entries != {STATE_NAME}:
        raise BlockReleaseError("registry is missing, pending, or has unexpected entries")
    data = _read_named_file(fd, STATE_NAME, MAX_STATE_BYTES, "registry state", private=True)
    state = _strict_json(data, "registry state")
    if (set(state) != STATE_FIELDS or type(state["schema"]) is not int
        or state["schema"] != SCHEMA or state["classification"] != CLASSIFICATION
        or state["schedule_sha256"] != schedule["schedule_sha256"]
        or type(state["sequence"]) is not int or state["sequence"] < 0
        or type(state["events"]) is not list or len(state["events"]) > 3 * len(schedule["runs"])
        or not _is_sha256(state["head_sha256"])
        or not _is_sha256(state["state_sha256"])):
        raise BlockReleaseError("registry state schema or schedule differs")
    body = {key: value for key, value in state.items() if key != "state_sha256"}
    if data != _canonical(state) or state["state_sha256"] != _digest(body):
        raise BlockReleaseError("registry state is noncanonical or has a wrong digest")
    claims, publications, terminals = _replay(state, schedule)
    if set(os.listdir(fd)) != {STATE_NAME}:
        raise BlockReleaseError("registry entries changed while reading")
    return state, claims, publications, terminals


def _write_all(fd: int, data: bytes) -> None:
    remaining = memoryview(data)
    while remaining:
        count = os.write(fd, remaining)
        if count <= 0:
            raise OSError("registry write made no progress")
        remaining = remaining[count:]


def _commit(fd: int, state: dict[str, Any]) -> None:
    data = _canonical(state)
    if len(data) > MAX_STATE_BYTES:
        raise BlockReleaseError("registry state exceeds byte limit")
    temp = f".state.{secrets.token_hex(16)}.tmp"
    pending_created = False
    try:
        pending_fd = os.open(PENDING_NAME, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                             0o600, dir_fd=fd)
        pending_created = True
        try:
            _write_all(pending_fd, _canonical({"next_state_sha256": state["state_sha256"]}))
            os.fsync(pending_fd)
        finally:
            os.close(pending_fd)
        os.fsync(fd)
        temp_fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                          0o600, dir_fd=fd)
        try:
            _write_all(temp_fd, data)
            os.fsync(temp_fd)
        finally:
            os.close(temp_fd)
        os.replace(temp, STATE_NAME, src_dir_fd=fd, dst_dir_fd=fd)
        os.fsync(fd)
        os.unlink(PENDING_NAME, dir_fd=fd)
        os.fsync(fd)
    except BaseException:
        # An error after removing the marker can otherwise look committed to
        # the next process, although the final directory fsync failed.
        if pending_created:
            try:
                repair_fd = os.open(PENDING_NAME,
                                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                                    0o600, dir_fd=fd)
            except FileExistsError:
                pass
            except OSError:
                pass
            else:
                try:
                    os.fsync(repair_fd)
                except OSError:
                    pass
                finally:
                    os.close(repair_fd)
                try:
                    os.fsync(fd)
                except OSError:
                    pass
        raise


def _gate_root(gate_root: Path | str) -> Path:
    if gate_root is None:
        raise BlockReleaseError("gate root must be explicit")
    try:
        return configured_root(gate_root)
    except (AdmissionError, OSError, TypeError) as exc:
        raise BlockReleaseError("invalid gate root") from exc


@contextmanager
def _registry_root(path: Path, *, create: bool) -> Iterator[tuple[int, bool]]:
    """Open a private root and report whether this call actually created it."""
    with ExitStack() as stack:
        parent_fd, name, chain = _open_directory_chain(path, "gate root", stack)
        _check_directory_chain(chain, "gate root")
        parent = os.fstat(parent_fd)
        if (not stat.S_ISDIR(parent.st_mode) or parent.st_uid != os.geteuid()
            or parent.st_mode & 0o022):
            raise BlockReleaseError("gate root parent must be owned and not writable by others")
        created = False
        if create:
            try:
                os.mkdir(name, 0o700, dir_fd=parent_fd)
            except FileExistsError:
                pass
            else:
                created = True
                os.fsync(parent_fd)
        fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                     dir_fd=parent_fd)
        stack.callback(os.close, fd)
        opened = os.fstat(fd)
        named = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        if (not stat.S_ISDIR(opened.st_mode) or not _same_file_state(opened, named)
            or opened.st_uid != os.geteuid()
            or stat.S_IMODE(opened.st_mode) != 0o700):
            raise BlockReleaseError("gate root is not a private unchanged directory")
        _check_directory_chain(chain, "gate root")
        yield fd, created
        if not _same_file_state(os.fstat(fd),
                                os.stat(name, dir_fd=parent_fd, follow_symlinks=False)):
            raise BlockReleaseError("gate root changed during operation")
        _check_directory_chain(chain, "gate root")


def _claim_result(event: dict[str, Any],
                  publication: dict[str, Any] | None = None) -> dict[str, Any]:
    result = {"schema": SCHEMA, "classification": CLAIM_CLASSIFICATION,
              "schedule_sha256": event["schedule_sha256"],
              "run_id": event["run_id"], "run_sha256": event["run_sha256"],
              "release_dir": event["release_dir"], "attempt_number": 1,
              "sequence": event["sequence"], "claim_sha256": event["event_sha256"]}
    if publication is not None:
        result["publication_sha256"] = publication["event_sha256"]
        result["manifest_sha256"] = publication["manifest_sha256"]
    return result


def claim_release(schedule: Any, run_id: str, gate_root: Path | str,
                  release_dir: Path | str) -> dict[str, Any]:
    """Reserve one scheduled release durably before creating its output dir."""
    checked = _schedule(schedule)
    run = _run(checked, run_id)
    root = _gate_root(gate_root)
    output = _absolute_path(release_dir, "release directory")
    try:
        with _registry_root(root, create=True) as (fd, created):
            fcntl.flock(fd, fcntl.LOCK_EX)
            if created:
                if os.listdir(fd):
                    raise BlockReleaseError("new gate root has unexpected entries")
                # Initialize the registry before checking eligibility. A
                # rejected first request must not strand an empty root, while
                # a crash during initialization leaves a pending marker.
                _commit(fd, _empty_state(checked["schedule_sha256"]))
            state, claims, publications, terminals = _load_state(fd, checked, allow_empty=False)
            _assert_claim_allowed(run, claims, publications, terminals, checked)
            if str(output) in {event["release_dir"] for event in claims.values()}:
                raise BlockReleaseError("release directory is already claimed")
            _validate_release_path(output, must_exist=False)
            event = _event(_event_body(run, checked["schedule_sha256"], str(output), state, "claim"))
            _commit(fd, _append(state, event))
            return _claim_result(event)
    except BlockReleaseError:
        raise
    except (OSError, AdmissionError, ToolPolicyError) as exc:
        raise BlockReleaseError("release claim could not be durably recorded") from exc


def mark_published(schedule: Any, run_id: str, gate_root: Path | str,
                   release_dir: Path | str, manifest_sha256: str) -> dict[str, Any]:
    """Finish a claim only after a fully verified release is on disk."""
    checked = _schedule(schedule)
    run = _run(checked, run_id)
    root = _gate_root(gate_root)
    output = _absolute_path(release_dir, "release directory")
    if not _is_sha256(manifest_sha256):
        raise BlockReleaseError("published manifest digest is invalid")
    try:
        with _registry_root(root, create=False) as (fd, _created):
            fcntl.flock(fd, fcntl.LOCK_EX)
            state, claims, publications, terminals = _load_state(fd, checked, allow_empty=False)
            claim = claims.get(run["run_id"])
            if claim is None:
                raise BlockReleaseError("publication lacks a release claim")
            if run["run_id"] in publications or run["run_id"] in terminals:
                raise BlockReleaseError("release has already been published or closed")
            if claim["release_dir"] != str(output):
                raise BlockReleaseError("release directory differs from claim")
            _validate_release_path(output, must_exist=True)
            from verify_released_run import ReleaseVerificationError, verify_release

            try:
                verified = verify_release(checked, output)
            except ReleaseVerificationError as exc:
                raise BlockReleaseError("release payload cannot be verified for publication") from exc
            if (verified["run_id"] != run["run_id"]
                or verified["run_sha256"] != run["run_sha256"]
                or _manifest_digest(str(output)) != manifest_sha256):
                raise BlockReleaseError("published release differs from claim or manifest digest")
            body = _event_body(run, checked["schedule_sha256"], str(output), state, "published")
            body["manifest_sha256"] = manifest_sha256
            event = _event(body)
            _commit(fd, _append(state, event))
            return {"schema": SCHEMA, "classification": CLASSIFICATION,
                    "schedule_sha256": checked["schedule_sha256"],
                    "run_id": run["run_id"], "run_sha256": run["run_sha256"],
                    "release_dir": str(output), "attempt_number": 1,
                    "manifest_sha256": manifest_sha256,
                    "sequence": event["sequence"],
                    "publication_sha256": event["event_sha256"]}
    except BlockReleaseError:
        raise
    except (OSError, AdmissionError, ToolPolicyError) as exc:
        raise BlockReleaseError("release publication could not be durably recorded") from exc


def verify_claim(schedule: Any, run_id: str, gate_root: Path | str,
                 release_dir: Path | str) -> dict[str, Any]:
    """Require an active published attempt-1 claim for this release."""
    checked = _schedule(schedule)
    run = _run(checked, run_id)
    root = _gate_root(gate_root)
    output = _absolute_path(release_dir, "release directory")
    try:
        with _registry_root(root, create=False) as (fd, _created):
            fcntl.flock(fd, fcntl.LOCK_SH)
            _state, claims, publications, terminals = _load_state(fd, checked, allow_empty=False)
            claim = claims.get(run["run_id"])
            if claim is None:
                raise BlockReleaseError("release claim is missing")
            if run["run_id"] in terminals:
                raise BlockReleaseError("release claim already has a terminal")
            if run["run_id"] not in publications:
                raise BlockReleaseError("release claim is pending publication")
            if claim["release_dir"] != str(output):
                raise BlockReleaseError("release directory differs from claim")
            _validate_release_path(output, must_exist=True)
            return _claim_result(claim, publications[run["run_id"]])
    except BlockReleaseError:
        raise
    except (OSError, AdmissionError, ToolPolicyError) as exc:
        raise BlockReleaseError("release claim could not be verified") from exc


def record_terminal(schedule: Any, run_id: str, gate_root: Path | str,
                    status: str, trace_sha256: str,
                    evidence_path: Path | str) -> dict[str, Any]:
    """Record a locally declared terminal; external_failure stops v1 block."""
    checked = _schedule(schedule)
    run = _run(checked, run_id)
    root = _gate_root(gate_root)
    evidence_file = _absolute_path(evidence_path, "terminal evidence")
    if type(status) is not str or status not in TERMINAL_STATUSES:
        raise BlockReleaseError("terminal status is invalid")
    if not _is_sha256(trace_sha256):
        raise BlockReleaseError("terminal trace digest is invalid")
    try:
        with _registry_root(root, create=False) as (fd, _created):
            fcntl.flock(fd, fcntl.LOCK_EX)
            state, claims, publications, terminals = _load_state(fd, checked, allow_empty=False)
            claim = claims.get(run["run_id"])
            if claim is None:
                raise BlockReleaseError("terminal lacks a release claim")
            if run["run_id"] in terminals:
                raise BlockReleaseError("release already has a terminal")
            if run["run_id"] not in publications:
                raise BlockReleaseError("release claim is pending publication")
            _validate_release_path(Path(claim["release_dir"]), must_exist=True)
            # A partially copied release may have a directory but no verified
            # manifest. It cannot close an arm and unlock its successor.
            from verify_released_run import ReleaseVerificationError, verify_release

            try:
                verified = verify_release(checked, claim["release_dir"])
            except ReleaseVerificationError as exc:
                raise BlockReleaseError("release payload cannot be verified for terminal") from exc
            if (verified["run_id"] != run["run_id"]
                or verified["run_sha256"] != run["run_sha256"]):
                raise BlockReleaseError("verified release differs from terminal claim")
            expected = {"schedule_sha256": checked["schedule_sha256"],
                        "run_id": run["run_id"], "run_sha256": run["run_sha256"],
                        "attempt_number": 1, "release_dir": claim["release_dir"],
                        "status": status, "trace_sha256": trace_sha256}
            evidence_sha256 = _evidence(evidence_file, expected, durable=True)
            body = _event_body(run, checked["schedule_sha256"], claim["release_dir"],
                               state, "terminal")
            body.update({"status": status, "trace_sha256": trace_sha256,
                         "evidence_path": str(evidence_file),
                         "evidence_sha256": evidence_sha256})
            event = _event(body)
            _commit(fd, _append(state, event))
            return {"schema": SCHEMA, "classification": TERMINAL_CLASSIFICATION,
                    "schedule_sha256": checked["schedule_sha256"],
                    "run_id": run["run_id"], "run_sha256": run["run_sha256"],
                    "release_dir": claim["release_dir"], "attempt_number": 1,
                    "status": status, "trace_sha256": trace_sha256,
                    "evidence_path": str(evidence_file),
                    "evidence_sha256": evidence_sha256,
                    "sequence": event["sequence"],
                    "terminal_sha256": event["event_sha256"]}
    except BlockReleaseError:
        raise
    except (OSError, AdmissionError, ToolPolicyError) as exc:
        raise BlockReleaseError("terminal could not be durably recorded") from exc


def _read_schedule(path: Path | str) -> dict[str, Any]:
    schedule_path = _absolute_path(path, "candidate schedule")
    try:
        data = _read_external_file(schedule_path, MAX_SCHEDULE_BYTES, "candidate schedule")
        return _strict_json(data, "candidate schedule")
    except (OSError, ToolPolicyError) as exc:
        raise BlockReleaseError("candidate schedule cannot be read securely") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    terminal = commands.add_parser("terminal", help="record one locally declared terminal")
    terminal.add_argument("schedule")
    terminal.add_argument("run_id")
    terminal.add_argument("gate_root")
    terminal.add_argument("status", choices=sorted(TERMINAL_STATUSES))
    terminal.add_argument("trace_sha256")
    terminal.add_argument("evidence_path")
    verify = commands.add_parser("verify", help="verify an active release claim")
    verify.add_argument("schedule")
    verify.add_argument("run_id")
    verify.add_argument("gate_root")
    verify.add_argument("release_dir")
    args = parser.parse_args(argv)
    try:
        schedule = _read_schedule(args.schedule)
        if args.command == "terminal":
            result = record_terminal(schedule, args.run_id, args.gate_root,
                                     args.status, args.trace_sha256, args.evidence_path)
        else:
            result = verify_claim(schedule, args.run_id, args.gate_root, args.release_dir)
    except BlockReleaseError as exc:
        print(f"Local block release gate failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
