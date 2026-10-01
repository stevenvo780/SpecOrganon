"""Durable local observation of host callbacks, independent of D119 sources.

The cooperative locks and hash chain detect local inconsistency. They do not
authenticate custody, provider activity, human time, or a native runtime guard.
"""
from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import math
import os
import re
import secrets
import stat
import time
from pathlib import Path
from typing import Any, Iterator

from development_delivery_contract import parse_json
from tool_policy import _read_bounded_file

ROLES = ("leader", "worker-1", "worker-2", "reviewer")
KINDS = ("count_input", "send", "tool")
ERRORS = {"transport_error", "tool_error", "observation_error"}
BINDING_FIELDS = {"run_dir", "run_id", "plan_sha256", "schedule_sha256", "initial_checkpoint_sha256", "observer_source_digests"}
CALL_FIELDS = {"role", "request_id", "request_sha256", "count_payload_sha256", "send_payload_sha256"}
EVENT_FIELDS = {"schema", "seq", "type", "monotonic_ns", "wall_ns", "boot_sha256", "prev_sha256", "data"}
CLOCK_FIELDS = {"implementation", "monotonic", "adjustable", "resolution_seconds"}
SHA = re.compile(r"[0-9a-f]{64}\Z")
REQUEST = re.compile(r"(leader|worker-1|worker-2|reviewer)-turn-([0-9]{4})\Z")
MAX_EVENTS, MAX_BYTES = 50000, 32768
ZERO_SHA = "0" * 64


class ObservationError(ValueError):
    """A fixed, participant-free journal rejection."""


def _require(value: bool, message: str) -> None:
    if not value:
        raise ObservationError(message)


def _object(value: Any, fields: set[str], message: str) -> dict:
    _require(type(value) is dict and set(value) == fields, message)
    return value


def _integer(value: Any, minimum: int = 0) -> int:
    _require(type(value) is int and minimum <= value <= 2**63 - 1, "invalid observation integer")
    return value


def _digest(value: Any) -> str:
    _require(type(value) is str and SHA.fullmatch(value) is not None, "invalid observation digest")
    return value


def _identifier(value: Any) -> str:
    _require(type(value) is str and re.fullmatch(r"[A-Za-z0-9_.-]{1,256}", value) is not None,
             "invalid observation identifier")
    return value


def _canonical(value: Any) -> bytes:
    try:
        return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False) + "\n").encode()
    except (ValueError, TypeError, RecursionError):
        raise ObservationError("invalid observation JSON") from None


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _absolute(value: Any) -> Path:
    _require(type(value) is str and "\x00" not in value and len(value.encode()) <= 4096,
             "invalid observation path")
    path = Path(value)
    _require(path.is_absolute() and str(path) == value and ".." not in path.parts, "invalid observation path")
    return path


def _binding(value: Any) -> dict:
    source = _object(value, BINDING_FIELDS, "invalid observation binding")
    _absolute(source["run_dir"])
    _identifier(source["run_id"])
    for key in ("plan_sha256", "schedule_sha256", "initial_checkpoint_sha256"):
        _digest(source[key])
    sources = source["observer_source_digests"]
    _require(type(sources) is dict and 1 <= len(sources) <= 512, "invalid observer source inventory")
    for name, digest in sources.items():
        _require(type(name) is str and re.fullmatch(r"scripts/[A-Za-z0-9_]+\.py", name) is not None,
                 "invalid observer source path")
        _digest(digest)
    _require(len(_canonical(source)) <= MAX_BYTES, "observation binding exceeds byte limit")
    return json.loads(_canonical(source))


def _clock_info(value: Any = None) -> dict:
    if value is None:
        info = time.get_clock_info("monotonic")
        value = {"implementation": info.implementation, "monotonic": info.monotonic,
                 "adjustable": info.adjustable, "resolution_seconds": info.resolution}
    _object(value, CLOCK_FIELDS, "invalid monotonic clock information")
    _require(type(value["implementation"]) is str and 1 <= len(value["implementation"].encode()) <= 256,
             "missing monotonic clock implementation")
    _require(value["monotonic"] is True and value["adjustable"] is False, "clock is not fixed monotonic")
    resolution = value["resolution_seconds"]
    _require(type(resolution) in (float, int) and math.isfinite(resolution) and resolution > 0,
             "invalid monotonic clock resolution")
    return dict(value)


def _boot_digest() -> str:
    try:
        fd = os.open("/proc/sys/kernel/random/boot_id", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            raw = os.read(fd, 129)
        finally:
            os.close(fd)
        _require(re.fullmatch(rb"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\n?", raw) is not None,
                 "boot identity is unavailable")
        return _sha(raw.strip())
    except OSError:
        raise ObservationError("boot identity is unavailable") from None


def _sample() -> dict:
    return {"monotonic_ns": _integer(time.monotonic_ns()), "wall_ns": _integer(time.time_ns()),
            "boot_sha256": _digest(_boot_digest())}


def _chain(path: Path) -> None:
    current = Path("/")
    for part in path.parts[1:]:
        current /= part
        info = current.lstat()
        _require(stat.S_ISDIR(info.st_mode) and not stat.S_ISLNK(info.st_mode), "observation directory chain changed")


def _private(path: Path, directory: bool = False) -> os.stat_result:
    info = path.lstat()
    _require(info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) == (0o700 if directory else 0o600)
             and (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode))
             and (directory or info.st_nlink == 1), "observation artifact is not private")
    return info


def _read(path: Path) -> tuple[dict, bytes]:
    _private(path)
    try:
        raw = _read_bounded_file(path, "observation artifact", MAX_BYTES)
        value = parse_json(raw)
    except (ValueError, UnicodeError, RecursionError, OverflowError):
        raise ObservationError("invalid observation artifact JSON") from None
    _require(type(value) is dict and raw == _canonical(value), "observation artifact is not canonical")
    return value, raw


def _publish(directory: Path, name: str, raw: bytes) -> None:
    """Publish a new file without overwriting; retain interrupted artifacts."""
    _require(len(raw) <= MAX_BYTES, "observation event exceeds byte limit")
    _chain(directory)
    _private(directory, True)
    directory_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    temporary = ".pending-" + secrets.token_hex(12)
    try:
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory_fd)
        try:
            offset = 0
            while offset < len(raw):
                offset += os.write(fd, raw[offset:])
            os.fsync(fd)
        finally:
            os.close(fd)
        os.link(temporary, name, src_dir_fd=directory_fd, dst_dir_fd=directory_fd, follow_symlinks=False)
        os.unlink(temporary, dir_fd=directory_fd)
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def _calls(value: Any, turns: dict[str, int]) -> dict[str, dict]:
    _require(type(value) is list and 1 <= len(value) <= len(ROLES), "invalid expected call inventory")
    result, roles = {}, set()
    for raw in value:
        call = _object(raw, CALL_FIELDS, "invalid expected call fields")
        role, request_id = call["role"], call["request_id"]
        _require(role in ROLES and type(request_id) is str, "invalid expected call role")
        match = REQUEST.fullmatch(request_id)
        _require(match is not None and match.group(1) == role and int(match.group(2)) == turns[role] + 1
                 and request_id not in result and role not in roles, "expected request identity or turn changed")
        for key in ("request_sha256", "count_payload_sha256", "send_payload_sha256"):
            _digest(call[key])
        result[request_id] = dict(call)
        roles.add(role)
    return result


def _end_fields(data: dict, operation: dict) -> None:
    error = data["error"]
    _require(error is None or type(error) is str and error in ERRORS, "invalid observation error category")
    _require(data["result_sha256"] is not None or error is not None, "operation result digest is missing")
    if data["result_sha256"] is not None:
        _digest(data["result_sha256"])
    if operation["kind"] == "count_input" and error is None:
        _integer(data["input_tokens"], 1)
    else:
        _require(data["input_tokens"] is None, "unexpected input count on operation")


def _complete(state: dict) -> None:
    for request_id in state["calls"]:
        for kind in ("count_input", "send"):
            operation = state["by_request"].get((request_id, kind))
            _require(operation is not None and operation.get("end") is not None and operation["end"]["data"]["error"] is None,
                     "step has missing or failed count/send observations")
    _require(all(op.get("end") is not None and op["end"]["data"]["error"] is None
                 for op in state["operations"].values() if op["step_id"] == state["current_step_id"]),
             "step has missing or failed operation ends")


def _replay(binding: dict, events: list[dict], raws: list[bytes]) -> dict:
    state = {"state": "released", "checkpoint_sha256": binding["initial_checkpoint_sha256"], "current_step_id": None,
             "steps": 0, "operations": {}, "by_request": {}, "calls": {}, "turns": dict.fromkeys(ROLES, 0),
             "clock_info": None, "delivery": None, "last_event_sha256": ZERO_SHA}
    _require(events and len(events) <= MAX_EVENTS, "release event is missing")
    boot, previous_mono = None, -1
    for index, (event, raw) in enumerate(zip(events, raws, strict=True), 1):
        _object(event, EVENT_FIELDS, "invalid observation event fields")
        _require(type(event["schema"]) is int and event["schema"] == 1
                 and _integer(event["seq"], 1) == index and event["prev_sha256"] == state["last_event_sha256"],
                 "observation sequence or hash chain changed")
        mono, _ = _integer(event["monotonic_ns"]), _integer(event["wall_ns"])
        event_boot = _digest(event["boot_sha256"])
        _require(mono >= previous_mono and (boot is None or boot == event_boot), "monotonic clock regressed or boot changed")
        boot, previous_mono = event_boot, mono
        kind, data = event["type"], event["data"]
        _require(type(kind) is str and type(data) is dict and state["state"] != "delivered", "invalid or post-delivery event")
        if kind == "release":
            _object(data, {"binding_sha256", "clock_info"}, "invalid release event")
            _require(index == 1 and data["binding_sha256"] == _sha(_canonical(binding)), "release binding changed")
            state["clock_info"] = _clock_info(data["clock_info"])
        else:
            _require(index > 1, "first event is not release")
            if kind == "step_begin":
                _object(data, {"step_id", "expected_checkpoint", "expected_calls"}, "invalid step begin event")
                _require(state["state"] in {"released", "paused"} and data["expected_checkpoint"] == state["checkpoint_sha256"],
                         "step checkpoint or lifecycle changed")
                _digest(data["expected_checkpoint"])
                state["steps"] += 1
                _require(data["step_id"] == f"step-{state['steps']:04d}", "step identity changed")
                state["calls"] = _calls(data["expected_calls"], state["turns"])
                for call in state["calls"].values():
                    state["turns"][call["role"]] += 1
                state.update(state="active", current_step_id=data["step_id"])
            elif kind == "operation_begin":
                _object(data, {"step_id", "op_id", "kind", "role", "request_id", "payload_sha256"}, "invalid operation begin event")
                _require(state["state"] == "active" and data["step_id"] == state["current_step_id"]
                         and data["op_id"] == f"op-{len(state['operations']) + 1:04d}", "operation identity or step changed")
                _require(type(data["request_id"]) is str and type(data["role"]) is str and type(data["kind"]) is str,
                         "invalid operation identity type")
                call = state["calls"].get(data["request_id"])
                _require(call is not None and data["role"] == call["role"] and data["kind"] in KINDS
                         and (data["request_id"], data["kind"]) not in state["by_request"], "operation call is unexpected or duplicated")
                _digest(data["payload_sha256"])
                if data["kind"] != "tool":
                    key = "count_payload_sha256" if data["kind"] == "count_input" else "send_payload_sha256"
                    _require(data["payload_sha256"] == call[key], "operation payload digest changed")
                if data["kind"] != "count_input":
                    prior = state["by_request"].get((data["request_id"], "count_input" if data["kind"] == "send" else "send"))
                    _require(prior is not None and prior.get("end") is not None and prior["end"]["data"]["error"] is None,
                             "count/send ordering is incomplete")
                operation = {**data, "begin": event, "end": None}
                state["operations"][data["op_id"]] = operation
                state["by_request"][(data["request_id"], data["kind"])] = operation
            elif kind == "operation_end":
                _object(data, {"step_id", "op_id", "result_sha256", "input_tokens", "error"}, "invalid operation end event")
                _identifier(data["op_id"])
                operation = state["operations"].get(data["op_id"])
                _require(state["state"] == "active" and operation is not None and operation["end"] is None
                         and data["step_id"] == operation["step_id"] == state["current_step_id"], "operation end is unexpected or duplicated")
                _end_fields(data, operation)
                operation["end"] = event
            elif kind == "step_end":
                _object(data, {"step_id", "next_checkpoint", "native_state"}, "invalid step end event")
                _require(state["state"] == "active" and data["step_id"] == state["current_step_id"]
                         and type(data["native_state"]) is str and data["native_state"] in {"paused", "completed"}, "invalid native step outcome")
                _complete(state)
                state.update(state="ready" if data["native_state"] == "completed" else "paused",
                             checkpoint_sha256=_digest(data["next_checkpoint"]), current_step_id=None)
            elif kind == "step_fail":
                _object(data, {"step_id"}, "invalid step failure event")
                _require(state["state"] == "active" and data["step_id"] == state["current_step_id"], "invalid step failure lifecycle")
                state.update(state="uncertain", current_step_id=None)
            elif kind == "delivery":
                _object(data, {"measurement_sha256"}, "invalid delivery event")
                _require(state["state"] == "ready" and all(op["end"] is not None for op in state["operations"].values()),
                         "delivery has incomplete observations")
                _digest(data["measurement_sha256"])
                state.update(state="delivered", delivery=event)
            else:
                raise ObservationError("unknown observation event type")
        state["last_event_sha256"] = _sha(raw)
    return state


def _interval_metrics(intervals: list[tuple[int, int]]) -> dict:
    total, union = sum(end - start for start, end in intervals), 0
    if intervals:
        left, right = sorted(intervals)[0]
        for start, end in sorted(intervals)[1:]:
            if start > right:
                union += right - left
                left, right = start, end
            else:
                right = max(right, end)
        union += right - left
    return {"sum_ns": total, "union_ns": union, "sum_seconds": total / 1_000_000_000,
            "union_seconds": union / 1_000_000_000, "completed_intervals": len(intervals)}


class ObservationJournal:
    def __init__(self, directory: Path):
        self.directory = _absolute(str(directory))
        self._token, self._token_pid = None, None
        with self._locked():
            _, events, _, _ = self._read()
            self._clock_check(events)

    @classmethod
    def create(cls, directory: Path, binding: dict) -> ObservationJournal:
        binding = _binding(binding)
        sample, clock = _sample(), _clock_info()
        path = _absolute(str(directory))
        _chain(path.parent)
        path.mkdir(mode=0o700)
        (path / "events").mkdir(mode=0o700)
        _publish(path, ".events.lock", b"")
        _publish(path, ".driver.lock", b"")
        _publish(path, "binding.json", _canonical(binding))
        event = {"schema": 1, "seq": 1, "type": "release", **sample, "prev_sha256": ZERO_SHA,
                 "data": {"binding_sha256": _sha(_canonical(binding)), "clock_info": clock}}
        _publish(path / "events", "000001.json", _canonical(event))
        fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        return cls(path)

    @contextlib.contextmanager
    def _locked(self, driver: bool = False) -> Iterator[None]:
        try:
            _chain(self.directory)
            _private(self.directory, True)
            name = self.directory / (".driver.lock" if driver else ".events.lock")
            before = _private(name)
            fd = os.open(name, os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK)
            try:
                opened = os.fstat(fd)
                _require((opened.st_dev, opened.st_ino) == (before.st_dev, before.st_ino), "observation lock changed")
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | (fcntl.LOCK_NB if driver else 0))
                except BlockingIOError:
                    raise ObservationError("another observation driver is active") from None
                after = _private(name)
                _require((opened.st_dev, opened.st_ino) == (after.st_dev, after.st_ino), "observation lock changed")
                yield
            finally:
                fcntl.flock(fd, fcntl.LOCK_UN)
                os.close(fd)
        except OSError:
            raise ObservationError("observation artifact or lock is unavailable") from None

    def driver_lock(self):
        return self._locked(driver=True)

    def _read(self) -> tuple[dict, list[dict], list[bytes], dict]:
        _require({path.name for path in self.directory.iterdir()} == {"binding.json", "events", ".events.lock", ".driver.lock"},
                 "unexpected observation artifact")
        binding, _ = _read(self.directory / "binding.json")
        binding = _binding(binding)
        _private(self.directory / "events", True)
        names = sorted(path.name for path in (self.directory / "events").iterdir())
        _require(1 <= len(names) <= MAX_EVENTS and names == [f"{index:06d}.json" for index in range(1, len(names) + 1)],
                 "observation event inventory is incomplete")
        values = [_read(self.directory / "events" / name) for name in names]
        events, raws = [row[0] for row in values], [row[1] for row in values]
        return binding, events, raws, _replay(binding, events, raws)

    @staticmethod
    def _clock_check(events: list[dict], sample: dict | None = None) -> dict:
        sample = _sample() if sample is None else sample
        _require(sample["boot_sha256"] == events[0]["boot_sha256"]
                 and sample["monotonic_ns"] >= events[-1]["monotonic_ns"], "monotonic clock regressed or boot changed")
        return sample

    def _append(self, kind: str, data: dict, binding: dict, events: list[dict], raws: list[bytes]) -> dict:
        _require(len(events) < MAX_EVENTS, "observation event limit reached")
        event = {"schema": 1, "seq": len(events) + 1, "type": kind, **self._clock_check(events),
                 "prev_sha256": _sha(raws[-1]), "data": data}
        raw = _canonical(event)
        state = _replay(binding, events + [event], raws + [raw])
        _publish(self.directory / "events", f"{len(events) + 1:06d}.json", raw)
        return state

    def _valid_token(self, token: Any, state: dict) -> bool:
        return (type(token) is str and SHA.fullmatch(token) is not None and self._token is not None and self._token_pid == os.getpid()
                and state["state"] == "active" and secrets.compare_digest(token, self._token))

    def begin_step(self, expected_checkpoint: str, expected_calls: list[dict]) -> str:
        with self._locked():
            binding, events, raws, state = self._read()
            _require(state["state"] in {"released", "paused"}, "active or terminal observation never resumes")
            _digest(expected_checkpoint)
            _calls(expected_calls, state["turns"])
            self._append("step_begin", {"step_id": f"step-{state['steps'] + 1:04d}", "expected_checkpoint": expected_checkpoint,
                                       "expected_calls": json.loads(_canonical(expected_calls))}, binding, events, raws)
            self._token, self._token_pid = secrets.token_hex(32), os.getpid()
            return self._token

    def begin_operation(self, token: str, kind: str, role: str, request_id: str, payload_sha256: str) -> str:
        with self._locked():
            binding, events, raws, state = self._read()
            _require(self._valid_token(token, state), "observation step token is not live")
            op_id = f"op-{len(state['operations']) + 1:04d}"
            self._append("operation_begin", {"step_id": state["current_step_id"], "op_id": op_id, "kind": kind,
                                             "role": role, "request_id": request_id, "payload_sha256": payload_sha256}, binding, events, raws)
            return op_id

    def end_operation(self, token: str, op_id: str, *, result_sha256: str | None,
                      input_tokens: int | None = None, error: str | None = None) -> bool:
        with self._locked():
            binding, events, raws, state = self._read()
            if not self._valid_token(token, state):
                return False
            self._append("operation_end", {"step_id": state["current_step_id"], "op_id": op_id, "result_sha256": result_sha256,
                                           "input_tokens": input_tokens, "error": error}, binding, events, raws)
            return True

    def end_step(self, token: str, next_checkpoint: str, native_state: str) -> None:
        with self._locked():
            binding, events, raws, state = self._read()
            _require(self._valid_token(token, state), "observation step token is not live")
            self._append("step_end", {"step_id": state["current_step_id"], "next_checkpoint": next_checkpoint,
                                      "native_state": native_state}, binding, events, raws)
            self._token, self._token_pid = None, None

    def fail_step(self, token: str) -> bool:
        with self._locked():
            binding, events, raws, state = self._read()
            if not self._valid_token(token, state):
                return False
            self._append("step_fail", {"step_id": state["current_step_id"]}, binding, events, raws)
            self._token, self._token_pid = None, None
            return True

    def finish(self, measurement_sha256: str) -> dict:
        with self._locked():
            binding, events, raws, _ = self._read()
            self._append("delivery", {"measurement_sha256": _digest(measurement_sha256)}, binding, events, raws)
        return self.report()

    def report(self) -> dict:
        with self._locked():
            binding, events, _, state = self._read()
            self._clock_check(events)
            operations = list(state["operations"].values())
            def intervals(role=None, kind=None):
                return [(op["begin"]["monotonic_ns"], op["end"]["monotonic_ns"]) for op in operations
                        if op["end"] is not None and (role is None or op["role"] == role) and (kind is None or op["kind"] == kind)]
            metrics = {"by_kind": {kind: _interval_metrics(intervals(kind=kind)) for kind in KINDS},
                       "all": _interval_metrics(intervals()),
                       "by_role": {role: {"by_kind": {kind: _interval_metrics(intervals(role, kind)) for kind in KINDS},
                                          "all": _interval_metrics(intervals(role))} for role in ROLES},
                       "incomplete_operations": sum(op["end"] is None for op in operations),
                       "failed_operations": sum(op["end"] is not None and op["end"]["data"]["error"] is not None for op in operations)}
            delivery = state["delivery"]
            elapsed = None if delivery is None else delivery["monotonic_ns"] - events[0]["monotonic_ns"]
            metrics["outside_operation_union_seconds"] = None if elapsed is None else (elapsed - metrics["all"]["union_ns"]) / 1_000_000_000
            return {"schema": 1, "classification": "development_coordinated_observation_local",
                    "binding": binding, "state": state["state"], "checkpoint_sha256": state["checkpoint_sha256"],
                    "current_step_id": state["current_step_id"], "events": events, "last_event_sha256": state["last_event_sha256"],
                    "clock_info": state["clock_info"], "W_local_elapsed_ns": elapsed,
                    "W_local_elapsed_seconds": None if elapsed is None else elapsed / 1_000_000_000,
                    "wall_delta_seconds": None if delivery is None else (delivery["wall_ns"] - events[0]["wall_ns"]) / 1_000_000_000,
                    "metrics": metrics, "native_guard_verified": False, "remote_activity_authenticated": False,
                    "identity_authenticated": False, "cost_authenticated": False, "bundle_custody_authenticated": False,
                    "paid_route_authorized": False, "formal_cell_executed": False, "comparable_development_cell": False,
                    "quality_assessed": False, "Q_demonstrated": False,
                    "scope": "same_boot_local_host_elapsed_including_observation_and_pauses_not_remote_CPU_or_human_time",
                    "missing": ["H_human_time", "authenticated_remote_compute", "provider_invoice", "human_review_cost",
                                "scoring_cost", "total_study_cost", "externally_authenticated_custody", "quality_scoring"]}
