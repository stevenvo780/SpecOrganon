"""Development-only, sequential text conversations on the measured Responses path.

One prepared run may be executed once. A crash or uncertain provider outcome is
terminal for that run. The local deadline covers this single process; there is
no human-approval pause, tool execution, dollar cap, or independent custody.
"""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import json
import os
import secrets
import signal
import stat
import sys
import time
from pathlib import Path
from typing import Any, Iterator

from managed_token_ledger import BudgetError, TokenLedger
from run_managed_response import (
    MAX_JSON_BYTES, DispatchError, OpenAIResponsesHTTP, ResponseTransport,
    _json_bytes, _validated_request, dispatch_response,
)


class ConversationError(ValueError):
    """A prepared conversation cannot safely proceed."""


class ActiveDeadlineExceeded(ConversationError):
    """The process-wide active deadline expired."""


class _DeadlineTransport:
    """Check the run deadline around both provider operations.

    The SIGALRM bounds the normal synchronous path; post-call checks prevent a
    transport that catches that exception from starting another request or
    turning an overrun into a completed run after it eventually returns.
    """

    def __init__(self, transport: ResponseTransport, deadline: float) -> None:
        self.transport = transport
        self.deadline = deadline

    def check(self) -> None:
        if time.monotonic() >= self.deadline:
            raise ActiveDeadlineExceeded("active deadline expired")

    def count_input(self, payload: dict[str, Any]) -> int:
        self.check()
        count = self.transport.count_input(payload)
        self.check()
        return count

    def send(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.check()
        response = self.transport.send(payload)
        self.check()
        return response


_MAX_TOKENS = 80_000
_MAX_ACTIVE_SECONDS = 5_400
_MAX_TURNS = 32
_STATES = {"prepared", "started", "completed", "truncated", "indeterminate"}
_STATE_KEYS = {
    "schema", "state", "plan_sha256", "limit_tokens", "active_limit_seconds",
    "turns_total", "turns_completed", "active_seconds", "reason",
}


def _canonical(value: Any) -> bytes:
    return _json_bytes(value) + b"\n"


def _new_private_file(path: Path, data: bytes) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb", closefd=False) as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        os.close(fd)
    _fsync_dir(path.parent)


def _fsync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _private_dir(path: Path) -> None:
    info = path.lstat()
    if (not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode)
            or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700):
        raise ConversationError("run directories must be owned by this user with mode 0700")


def _private_file(path: Path) -> None:
    info = path.lstat()
    if (not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode)
            or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600):
        raise ConversationError("run files must be owned by this user with mode 0600")


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ConversationError("JSON contains a duplicate key")
        value[key] = item
    return value


def _reject_constant(_value: str) -> None:
    raise ConversationError("JSON contains a nonfinite number")


def _read_json(path: Path) -> dict[str, Any]:
    _private_file(path)
    raw = path.read_bytes()
    if len(raw) > MAX_JSON_BYTES:
        raise ConversationError("run JSON exceeds the byte limit")
    try:
        value = json.loads(raw, object_pairs_hook=_unique_pairs,
                           parse_constant=_reject_constant)
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise ConversationError("run JSON is invalid") from exc
    if type(value) is not dict or raw != _canonical(value):
        raise ConversationError("run JSON is not canonical")
    return value


def _write_state(run_dir: Path, state: dict[str, Any]) -> None:
    target = run_dir / "run.json"
    _private_file(target)
    temporary = run_dir / f".run.{secrets.token_hex(16)}.tmp"
    _new_private_file(temporary, _canonical(state))
    os.replace(temporary, target)
    _fsync_dir(run_dir)


def _validated_plan(raw: Any) -> dict[str, Any]:
    if (type(raw) is not dict or not {"schema", "model", "turns"} <= raw.keys()
            or not raw.keys() <= {"schema", "model", "instructions", "reasoning", "turns"}
            or type(raw["schema"]) is not int or raw["schema"] != 1):
        raise ConversationError("plan schema or fields are invalid")
    turns = raw["turns"]
    if type(turns) is not list or not 2 <= len(turns) <= _MAX_TURNS:
        raise ConversationError("plan needs between 2 and 32 text turns")
    for turn in turns:
        if (type(turn) is not dict or set(turn) != {"user", "max_output_tokens"}
                or type(turn["user"]) is not str or not turn["user"]
                or type(turn["max_output_tokens"]) is not int
                or turn["max_output_tokens"] < 1):
            raise ConversationError("each turn needs text and a positive output cap")
    first = {"model": raw["model"], "input": [{"role": "user", "content": turns[0]["user"]}],
             "max_output_tokens": turns[0]["max_output_tokens"]}
    for optional in ("instructions", "reasoning"):
        if optional in raw:
            first[optional] = raw[optional]
    _validated_request(first)
    if len(_canonical(raw)) > MAX_JSON_BYTES:
        raise ConversationError("plan exceeds the byte limit")
    return json.loads(_json_bytes(raw))


def _validated_state(value: dict[str, Any], plan: dict[str, Any], raw_plan: bytes) -> None:
    if (set(value) != _STATE_KEYS or type(value["schema"]) is not int
            or value["schema"] != 1 or type(value["state"]) is not str
            or value["state"] not in _STATES
            or type(value["plan_sha256"]) is not str
            or value["plan_sha256"] != hashlib.sha256(raw_plan).hexdigest()
            or type(value["limit_tokens"]) is not int
            or not 1 <= value["limit_tokens"] <= _MAX_TOKENS
            or type(value["active_limit_seconds"]) is not int
            or not 1 <= value["active_limit_seconds"] <= _MAX_ACTIVE_SECONDS
            or type(value["turns_total"]) is not int
            or value["turns_total"] != len(plan["turns"])
            or type(value["turns_completed"]) is not int
            or not 0 <= value["turns_completed"] <= len(plan["turns"])
            or type(value["active_seconds"]) not in (int, float)
            or value["active_seconds"] < 0
            or value["reason"] is not None and type(value["reason"]) is not str):
        raise ConversationError("run state is inconsistent")


def _load(run_dir: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    _private_dir(run_dir)
    for name in ("requests", "responses", "receipts", "ledger"):
        _private_dir(run_dir / name)
    _private_file(run_dir / ".lock")
    plan = _validated_plan(_read_json(run_dir / "plan.json"))
    raw_plan = (run_dir / "plan.json").read_bytes()
    state = _read_json(run_dir / "run.json")
    _validated_state(state, plan, raw_plan)
    return plan, state


@contextlib.contextmanager
def _run_lock(run_dir: Path) -> Iterator[None]:
    _private_dir(run_dir)
    lock_path = run_dir / ".lock"
    _private_file(lock_path)
    fd = os.open(lock_path, os.O_RDWR | os.O_NOFOLLOW)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        _private_dir(run_dir)
        _private_file(lock_path)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def prepare_conversation(
    run_dir: Path, plan: dict[str, Any], limit_tokens: int = _MAX_TOKENS,
    active_limit_seconds: int = _MAX_ACTIVE_SECONDS,
) -> dict[str, Any]:
    """Create a new private, immutable plan and shared ledger without provider calls."""
    validated = _validated_plan(plan)
    if type(limit_tokens) is not int or not 1 <= limit_tokens <= _MAX_TOKENS:
        raise ConversationError("token cap must be between 1 and 80000")
    if (type(active_limit_seconds) is not int
            or not 1 <= active_limit_seconds <= _MAX_ACTIVE_SECONDS):
        raise ConversationError("active cap must be between 1 and 5400 seconds")
    run_dir = Path(run_dir)
    run_dir.mkdir(mode=0o700)
    run_dir.chmod(0o700)
    _private_dir(run_dir)
    for name in ("requests", "responses", "receipts"):
        (run_dir / name).mkdir(mode=0o700)
        (run_dir / name).chmod(0o700)
    TokenLedger.create(run_dir / "ledger", limit_tokens, len(validated["turns"]))
    raw_plan = _canonical(validated)
    _new_private_file(run_dir / "plan.json", raw_plan)
    _new_private_file(run_dir / ".lock", b"")
    state = {
        "schema": 1, "state": "prepared",
        "plan_sha256": hashlib.sha256(raw_plan).hexdigest(),
        "limit_tokens": limit_tokens, "active_limit_seconds": active_limit_seconds,
        "turns_total": len(validated["turns"]), "turns_completed": 0,
        "active_seconds": 0, "reason": None,
    }
    _new_private_file(run_dir / "run.json", _canonical(state))
    _fsync_dir(run_dir)
    _fsync_dir(run_dir.parent)
    return read_conversation_status(run_dir)


def _assistant_text(response: dict[str, Any]) -> str:
    output = response.get("output")
    if type(output) is not list:
        raise ConversationError("response has no text output array")
    texts: list[str] = []
    for item in output:
        if type(item) is not dict:
            raise ConversationError("response output item is invalid")
        if item.get("type") == "reasoning":
            if (type(item.get("encrypted_content")) is not str
                    or not item["encrypted_content"]):
                raise ConversationError("reasoning item cannot be preserved")
            continue
        if item.get("type") != "message" or item.get("role") != "assistant":
            raise ConversationError("response output is not a plain assistant message")
        content = item.get("content")
        if type(content) is not list:
            raise ConversationError("assistant message content is invalid")
        for part in content:
            if (type(part) is not dict or part.get("type") != "output_text"
                    or type(part.get("text")) is not str):
                raise ConversationError("assistant message is not plain text")
            if part["text"]:
                texts.append(part["text"])
    if not texts:
        raise ConversationError("assistant response contains no text")
    return "\n".join(texts)


@contextlib.contextmanager
def _deadline(seconds: int) -> Iterator[None]:
    if signal.getitimer(signal.ITIMER_REAL) != (0.0, 0.0):
        raise ConversationError("an existing process alarm prevents a bounded run")
    old_handler = signal.getsignal(signal.SIGALRM)

    def expire(_number: int, _frame: Any) -> None:
        raise ActiveDeadlineExceeded("active deadline expired")

    signal.signal(signal.SIGALRM, expire)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old_handler)


def _finish(run_dir: Path, state: dict[str, Any], *, outcome: str,
            completed: int, started_at: float, reason: str | None) -> None:
    state.update(state=outcome, turns_completed=completed,
                 active_seconds=time.monotonic() - started_at, reason=reason)
    _write_state(run_dir, state)


def execute_conversation(run_dir: Path, transport: ResponseTransport) -> dict[str, Any]:
    """Send planned turns once, serially, with one ledger and one active timer."""
    run_dir = Path(run_dir)
    with _run_lock(run_dir):
        plan, state = _load(run_dir)
        if state["state"] != "prepared":
            raise ConversationError("this run is terminal or already started; no retry")
        ledger = TokenLedger(run_dir / "ledger")
        if ledger.status()["request_count"] != 0 or any(
            any((run_dir / name).iterdir()) for name in ("requests", "responses", "receipts")
        ):
            raise ConversationError("prepared run contains unexpected prior work")
        state["state"] = "started"
        _write_state(run_dir, state)
        started_at = time.monotonic()
        bounded_transport = _DeadlineTransport(
            transport, started_at + state["active_limit_seconds"])
        completed = 0
        history: list[dict[str, str]] = []
        try:
            with _deadline(state["active_limit_seconds"]):
                for number, turn in enumerate(plan["turns"], start=1):
                    bounded_transport.check()
                    history.append({"role": "user", "content": turn["user"]})
                    request = {"model": plan["model"], "input": list(history),
                               "max_output_tokens": turn["max_output_tokens"]}
                    for optional in ("instructions", "reasoning"):
                        if optional in plan:
                            request[optional] = plan[optional]
                    request = _validated_request(request)
                    name = f"{number:04d}.json"
                    _new_private_file(run_dir / "requests" / name, _canonical(request))
                    try:
                        receipt = dispatch_response(
                            ledger, request_id=f"turn-{number:04d}", role="agent",
                            request=request, response_path=run_dir / "responses" / name,
                            transport=bounded_transport,
                        )
                    except BudgetError:
                        _finish(run_dir, state, outcome="truncated", completed=completed,
                                started_at=started_at, reason="token_budget")
                        return _snapshot(run_dir, plan, state, ledger)
                    _new_private_file(run_dir / "receipts" / name, _canonical({
                        "turn": number, "request_sha256": hashlib.sha256(
                            _json_bytes(request)).hexdigest(), **receipt,
                    }))
                    completed = number
                    if receipt["provider_status"] != "completed":
                        _finish(run_dir, state, outcome="truncated", completed=completed,
                                started_at=started_at, reason="provider_incomplete")
                        return _snapshot(run_dir, plan, state, ledger)
                    response = _read_json(run_dir / "responses" / name)
                    if hashlib.sha256(_canonical(response)).hexdigest() != receipt["response_sha256"]:
                        raise ConversationError("stored response digest changed")
                    try:
                        _assistant_text(response)
                    except ConversationError:
                        _finish(run_dir, state, outcome="truncated", completed=completed,
                                started_at=started_at, reason="nontext_response")
                        return _snapshot(run_dir, plan, state, ledger)
                    # Preserve opaque encrypted reasoning and assistant phase;
                    # synthesizing only visible text changes later reasoning.
                    history.extend(response["output"])
                bounded_transport.check()
                _finish(run_dir, state, outcome="completed", completed=completed,
                        started_at=started_at, reason=None)
                return _snapshot(run_dir, plan, state, ledger)
        except Exception as exc:
            # A deadline or crash after reservation cannot be safely retried.
            try:
                _finish(run_dir, state, outcome="indeterminate", completed=completed,
                        started_at=started_at, reason=type(exc).__name__)
            except (OSError, ConversationError, DispatchError):
                pass  # The durable started marker still blocks reexecution.
            raise ConversationError("run outcome indeterminate; no automatic retry") from exc


def _snapshot(run_dir: Path, plan: dict[str, Any], state: dict[str, Any],
              ledger: TokenLedger) -> dict[str, Any]:
    budget = ledger.status()
    for number in range(1, state["turns_completed"] + 1):
        name = f"{number:04d}.json"
        request = _read_json(run_dir / "requests" / name)
        response_path = run_dir / "responses" / name
        response = _read_json(response_path)
        receipt = _read_json(run_dir / "receipts" / name)
        record = budget["requests"].get(f"turn-{number:04d}")
        request_sha256 = hashlib.sha256(_json_bytes(request)).hexdigest()
        response_sha256 = hashlib.sha256(response_path.read_bytes()).hexdigest()
        if (record is None or record["state"] != "settled"
                or record["payload_sha256"] != request_sha256
                or receipt.get("turn") != number
                or receipt.get("request_sha256") != request_sha256
                or receipt.get("response_sha256") != response_sha256
                or receipt.get("usage") != response.get("usage")
                or type(receipt.get("usage")) is not dict
                or {key: receipt["usage"].get(key) for key in
                    ("input_tokens", "output_tokens", "total_tokens")} != record["usage"]
                or receipt.get("provider_response_id") != response.get("id")
                or receipt.get("provider_status") != response.get("status")):
            raise ConversationError("completed turn artifacts disagree")
    return {
            "classification": "development_text_conversation_unsealed",
            "state": "indeterminate" if state["state"] == "started" else state["state"],
            "stored_state": state["state"], "reason": state["reason"],
            "model": plan["model"], "plan_sha256": state["plan_sha256"],
            "turns_total": state["turns_total"],
            "turns_completed": state["turns_completed"],
            "active_seconds": state["active_seconds"],
            "active_limit_seconds": state["active_limit_seconds"],
            "budget": budget,
            "completed_artifacts_verified": True,
            "global_run_limits_enforced": False,
            "criterion_4": "not_assessed",
    }


def read_conversation_status(run_dir: Path) -> dict[str, Any]:
    run_dir = Path(run_dir)
    with _run_lock(run_dir):
        plan, state = _load(run_dir)
        return _snapshot(run_dir, plan, state, TokenLedger(run_dir / "ledger"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prepare = sub.add_parser("prepare", help="prepare a private run without sending")
    prepare.add_argument("plan_file", type=Path)
    prepare.add_argument("run_dir", type=Path)
    prepare.add_argument("--limit-tokens", type=int, default=_MAX_TOKENS)
    prepare.add_argument("--active-limit-seconds", type=int, default=_MAX_ACTIVE_SECONDS)
    execute = sub.add_parser("execute", help="execute one prepared run")
    execute.add_argument("run_dir", type=Path)
    execute.add_argument("--allow-paid-requests", action="store_true")
    status = sub.add_parser("status", help="inspect run metadata without sending")
    status.add_argument("run_dir", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            raw = args.plan_file.read_bytes()
            if len(raw) > MAX_JSON_BYTES:
                raise ConversationError("plan exceeds the byte limit")
            plan = json.loads(raw, object_pairs_hook=_unique_pairs)
            result = prepare_conversation(args.run_dir, plan, args.limit_tokens,
                                          args.active_limit_seconds)
        elif args.command == "status":
            result = read_conversation_status(args.run_dir)
        else:
            if not args.allow_paid_requests:
                raise ConversationError("execute requires --allow-paid-requests")
            api_key = os.environ.get("OPENAI_API_KEY")
            if not api_key:
                raise ConversationError("OPENAI_API_KEY is unavailable")
            result = execute_conversation(args.run_dir, OpenAIResponsesHTTP(api_key))
    except (OSError, ValueError, BudgetError, DispatchError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
