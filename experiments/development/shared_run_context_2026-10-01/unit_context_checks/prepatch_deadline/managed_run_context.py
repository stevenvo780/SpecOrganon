"""Local durable lifecycle around one existing token ledger and its journals.

Roles are labels, prices are declared, and an uncertain active interval cannot
be resumed. This module does not authenticate identities or provider spending.
"""

from __future__ import annotations

import hashlib
import math
import os
import re
import secrets
import stat
import time
from pathlib import Path
from typing import Any

from managed_token_ledger import TokenLedger
from run_managed_conversation import (
    _canonical, _fsync_dir, _new_private_file, _private_dir, _read_json,
    _run_lock, _write_state,
)

MAX_ENTRIES = 10_000
MAX_FILE_BYTES = 16 * 1024 * 1024
MAX_TOTAL_BYTES = 64 * 1024 * 1024
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_ROLE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}\Z")
_STATES = {"prepared", "active", "paused", "completed", "indeterminate", "exhausted"}
_KEYS = {
    "schema", "state", "revision", "cursor", "bindings", "bindings_sha256",
    "ledger_dir", "roles", "journal_roots", "active_limit_seconds", "max_tool_calls",
    "active_seconds", "paused_seconds", "paused_at_wall", "role", "lease_nonce",
    "held_active_seconds", "reason_sha256", "ledger_sha256", "inventory_sha256",
    "checkpoint_sha256",
}


class RunContextError(ValueError):
    """A context transition cannot safely authorize another local effect."""


ContextError = RunContextError


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _finite(value: Any, label: str, *, positive: bool = False) -> float:
    if (type(value) not in (int, float) or not math.isfinite(value)
            or value < 0 or positive and value == 0):
        raise RunContextError(f"{label} must be finite and nonnegative")
    return float(value)


def _bindings(value: Any) -> dict:
    if type(value) is not dict:
        raise RunContextError("bindings must be a JSON object")

    def check(item: Any, depth: int = 0) -> None:
        if depth > 32:
            raise RunContextError("bindings are too deeply nested")
        if type(item) is dict:
            for key, child in item.items():
                if type(key) is not str:
                    raise RunContextError("binding keys must be strings")
                if key.endswith("_sha256") and (
                    type(child) is not str or _DIGEST.fullmatch(child) is None
                ):
                    raise RunContextError("binding digest is invalid")
                check(child, depth + 1)
        elif type(item) is list:
            for child in item:
                check(child, depth + 1)
        elif type(item) not in (str, int, float, bool, type(None)):
            raise RunContextError("binding values must be JSON values")
        elif type(item) is float and not math.isfinite(item):
            raise RunContextError("binding number is nonfinite")

    check(value)
    if len(_canonical(value)) > 64 * 1024:
        raise RunContextError("bindings exceed byte limit")
    # Detach caller-owned mutable containers without accepting lossy JSON types.
    import json
    return json.loads(_canonical(value))


def _path(value: Any) -> Path:
    if not isinstance(value, (str, Path)):
        raise RunContextError("paths must be absolute strings or Paths")
    path = Path(value)
    if not path.is_absolute() or ".." in path.parts or len(str(path)) > 4096:
        raise RunContextError("paths must be absolute without parent traversal")
    for parent in (*reversed(path.parents), path):
        if parent.is_symlink():
            raise RunContextError("symlink paths are forbidden")
    return path


def _roots(context_dir: Path, values: Any) -> list[str]:
    if type(values) is not list or not 1 <= len(values) <= 64:
        raise RunContextError("journal_roots must contain between 1 and 64 paths")
    paths = [_path(value) for value in values]
    for index, path in enumerate(paths):
        if path == context_dir or path in context_dir.parents or context_dir in path.parents:
            raise RunContextError("journal root overlaps the context")
        if any(path == other or path in other.parents or other in path.parents
               for other in paths[:index]):
            raise RunContextError("journal roots overlap or repeat")
    return sorted(str(path) for path in paths)


def _inventory(roots: list[str]) -> str:
    records: list[dict] = []
    total = 0

    def visit(fd: int, root: str, relative: str) -> None:
        nonlocal total
        before = os.fstat(fd)
        if len(records) >= MAX_ENTRIES:
            raise RunContextError("journal inventory exceeds entry limit")
        base = {"root": root, "name": relative, "mode": stat.S_IMODE(before.st_mode)}
        if stat.S_ISDIR(before.st_mode):
            records.append(base | {"type": "directory"})
            for name in sorted(os.listdir(fd)):
                info = os.stat(name, dir_fd=fd, follow_symlinks=False)
                if not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)):
                    raise RunContextError("journal contains a symlink or nonregular entry")
                flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
                if stat.S_ISDIR(info.st_mode):
                    flags |= os.O_DIRECTORY
                child = os.open(name, flags, dir_fd=fd)
                try:
                    opened = os.fstat(child)
                    if (opened.st_dev, opened.st_ino) != (info.st_dev, info.st_ino):
                        raise RunContextError("journal entry changed while opening")
                    visit(child, root, f"{relative}/{name}" if relative else name)
                finally:
                    os.close(child)
        elif stat.S_ISREG(before.st_mode):
            if before.st_size > MAX_FILE_BYTES:
                raise RunContextError("journal file exceeds byte limit")
            digest = hashlib.sha256()
            size = 0
            while chunk := os.read(fd, 64 * 1024):
                size += len(chunk)
                total += len(chunk)
                if size > MAX_FILE_BYTES or total > MAX_TOTAL_BYTES:
                    raise RunContextError("journal inventory exceeds byte limit")
                digest.update(chunk)
            records.append(base | {"type": "file", "size": size, "sha256": digest.hexdigest()})
        else:
            raise RunContextError("journal root is not a regular file or directory")
        after = os.fstat(fd)
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
            after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns
        ):
            raise RunContextError("journal changed during inventory")

    try:
        for root in roots:
            path = _path(root)
            info = path.lstat()
            if not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)):
                raise RunContextError("journal root is not a regular file or directory")
            flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
            if stat.S_ISDIR(info.st_mode):
                flags |= os.O_DIRECTORY
            fd = os.open(path, flags)
            try:
                opened = os.fstat(fd)
                if (opened.st_dev, opened.st_ino) != (info.st_dev, info.st_ino):
                    raise RunContextError("journal root changed while opening")
                visit(fd, root, "")
            finally:
                os.close(fd)
    except OSError as exc:
        raise RunContextError("journal inventory is unavailable") from exc
    return _sha(_canonical(records))


def _checkpoint(state: dict) -> str:
    return _sha(_canonical({key: value for key, value in state.items()
                            if key != "checkpoint_sha256"}))


class RunContext:
    """One serial lease and durable checkpoints around an existing ledger."""

    def __init__(self, context_dir: Path):
        self.directory = _path(context_dir)
        self._lease: tuple[int, str, int] | None = None
        self._started: float | None = None
        self.deadline: float | None = None
        with _run_lock(self.directory):
            self._read()

    @classmethod
    def create(cls, context_dir: Path, ledger_dir: Path, bindings: dict, *,
               active_limit_seconds: float, max_tool_calls: int, roles: list[str],
               journal_roots: list[Path]) -> RunContext:
        context_dir, ledger_dir = _path(context_dir), _path(ledger_dir)
        limit = _finite(active_limit_seconds, "active limit", positive=True)
        if (type(max_tool_calls) is not int or max_tool_calls < 0
                or type(roles) is not list or not 1 <= len(roles) <= 64
                or any(type(role) is not str or _ROLE.fullmatch(role) is None for role in roles)
                or len(set(roles)) != len(roles)):
            raise RunContextError("tool cap or roles are invalid")
        pinned = _bindings(bindings)
        roots = _roots(context_dir, journal_roots)
        budget = TokenLedger(ledger_dir).status()
        if budget["blocked"]:
            raise RunContextError("cannot attach a blocked ledger")
        state = {
            "schema": 1, "state": "prepared", "revision": 0, "cursor": 0,
            "bindings": pinned, "bindings_sha256": _sha(_canonical(pinned)),
            "ledger_dir": str(ledger_dir), "roles": list(roles), "journal_roots": roots,
            "active_limit_seconds": limit, "max_tool_calls": max_tool_calls,
            "active_seconds": 0.0, "paused_seconds": 0.0, "paused_at_wall": None,
            "role": None, "lease_nonce": None, "held_active_seconds": 0.0,
            "reason_sha256": None, "ledger_sha256": _sha((ledger_dir / "ledger.json").read_bytes()),
            "inventory_sha256": _inventory(roots), "checkpoint_sha256": "",
        }
        tools = cls._tools(context_dir.parent, max_tool_calls, reconcile=True)
        if tools > max_tool_calls:
            raise RunContextError("tool cap already exceeded")
        state["checkpoint_sha256"] = _checkpoint(state)
        context_dir.mkdir(mode=0o700)
        context_dir.chmod(0o700)
        _new_private_file(context_dir / ".lock", b"")
        _new_private_file(context_dir / "run.json", _canonical(state))
        _fsync_dir(context_dir)
        _fsync_dir(context_dir.parent)
        return cls(context_dir)

    def _read(self) -> dict:
        state = _read_json(self.directory / "run.json")
        if (set(state) != _KEYS or type(state["schema"]) is not int or state["schema"] != 1
                or type(state["state"]) is not str or state["state"] not in _STATES
                or any(type(state[key]) is not int or state[key] < 0
                       for key in ("revision", "cursor", "max_tool_calls"))):
            raise RunContextError("context state has an invalid shape")
        for key in ("bindings_sha256", "ledger_sha256", "inventory_sha256", "checkpoint_sha256"):
            if type(state[key]) is not str or _DIGEST.fullmatch(state[key]) is None:
                raise RunContextError("context digest is invalid")
        if (_bindings(state["bindings"]) != state["bindings"]
                or state["bindings_sha256"] != _sha(_canonical(state["bindings"]))
                or state["checkpoint_sha256"] != _checkpoint(state)):
            raise RunContextError("context binding or checkpoint digest changed")
        _path(state["ledger_dir"])
        if _roots(self.directory, state["journal_roots"]) != state["journal_roots"]:
            raise RunContextError("context journal roots changed")
        roles = state["roles"]
        if (type(roles) is not list or not 1 <= len(roles) <= 64 or len(set(roles)) != len(roles)
                or any(type(role) is not str or _ROLE.fullmatch(role) is None for role in roles)):
            raise RunContextError("context roles are invalid")
        limit = _finite(state["active_limit_seconds"], "active limit", positive=True)
        active = _finite(state["active_seconds"], "active seconds")
        held = _finite(state["held_active_seconds"], "held active seconds")
        _finite(state["paused_seconds"], "paused seconds")
        if active > limit or held > limit - active:
            raise RunContextError("context active time exceeds its cap")
        if state["role"] is not None and state["role"] not in roles:
            raise RunContextError("context role is invalid")
        if state["state"] == "active":
            if (type(state["lease_nonce"]) is not str
                    or re.fullmatch(r"[0-9a-f]{32}", state["lease_nonce"]) is None
                    or state["role"] is None or held != limit - active):
                raise RunContextError("active context lacks a valid lease")
        elif state["lease_nonce"] is not None:
            raise RunContextError("inactive context retains a lease")
        if state["state"] == "paused":
            _finite(state["paused_at_wall"], "pause wall time")
        elif state["paused_at_wall"] is not None:
            raise RunContextError("nonpaused context retains pause wall time")
        if state["state"] == "indeterminate":
            if type(state["reason_sha256"]) is not str or _DIGEST.fullmatch(state["reason_sha256"]) is None:
                raise RunContextError("indeterminate context lacks a reason digest")
        elif state["reason_sha256"] is not None or state["state"] != "active" and held != 0:
            raise RunContextError("context lifecycle is inconsistent")
        return state

    @staticmethod
    def _tools(parent: Path, cap: int, *, reconcile: bool) -> int:
        names = []
        for folder in ("tool_reservations", "tool_receipts"):
            path = parent / folder
            _private_dir(path)
            entries = set()
            for item in path.iterdir():
                if not stat.S_ISREG(item.lstat().st_mode):
                    raise RunContextError("tool journal contains a nonregular entry")
                entries.add(item.name)
            names.append(entries)
        if len(names[0]) > cap or not names[1] <= names[0]:
            raise RunContextError("tool journal exceeds cap or lacks reservations")
        if reconcile and names[0] != names[1]:
            raise RunContextError("tool reservation has no reconciled receipt")
        return len(names[0])

    def _capture(self, state: dict, *, frozen: bool, reconcile: bool) -> tuple[dict, int]:
        ledger = TokenLedger(Path(state["ledger_dir"]))
        # Keep the ledger lock across its status and raw-byte digest.
        with ledger._locked():
            raw = ledger._read_unlocked()
            ledger_sha = _sha(_canonical(raw))
        budget = ledger.status()
        inventory = _inventory(state["journal_roots"])
        tools = self._tools(self.directory.parent, state["max_tool_calls"], reconcile=reconcile)
        if reconcile and budget["blocked"]:
            raise RunContextError("ledger has an unresolved or indeterminate request")
        if frozen and (state["ledger_sha256"] != ledger_sha or state["inventory_sha256"] != inventory):
            raise RunContextError("checkpoint journals or ledger changed")
        state.update(ledger_sha256=ledger_sha, inventory_sha256=inventory)
        return budget, tools

    def _owns(self, state: dict) -> None:
        if (state["state"] != "active" or self._lease != (
            state["revision"], state["lease_nonce"], os.getpid()
        )):
            raise RunContextError("instance does not own the current active lease")

    def _check_deadline(self) -> None:
        now = time.monotonic()
        if (self.deadline is None or self._started is None or not math.isfinite(now)
                or now < self._started or now >= self.deadline):
            raise RunContextError("active deadline expired or monotonic clock changed")

    def _view(self, state: dict, budget: dict, tools: int) -> dict:
        exposed = state["state"]
        if exposed == "active" and self._lease != (state["revision"], state["lease_nonce"], os.getpid()):
            exposed = "indeterminate"
        return {
            "state": exposed, "stored_state": state["state"],
            "checkpoint_sha256": state["checkpoint_sha256"], "cursor": state["cursor"],
            "revision": state["revision"], "role": state["role"],
            "active_seconds": state["active_seconds"], "paused_seconds": state["paused_seconds"],
            "held_active_seconds": state["held_active_seconds"],
            "remaining_active_seconds": max(0.0, state["active_limit_seconds"]
                                             - state["active_seconds"] - state["held_active_seconds"]),
            "active_limit_seconds": state["active_limit_seconds"],
            "tools_reserved": tools, "max_tool_calls": state["max_tool_calls"], "budget": budget,
            "identity_authenticated": False, "cost_authenticated": False,
        }

    def status(self) -> dict:
        with _run_lock(self.directory):
            state = self._read()
            frozen = state["state"] not in {"active", "indeterminate"}
            budget, tools = self._capture(state, frozen=frozen, reconcile=frozen)
            return self._view(state, budget, tools)

    def begin(self, expected_checkpoint: str, role: str) -> dict:
        with _run_lock(self.directory):
            state = self._read()
            if (type(expected_checkpoint) is not str or _DIGEST.fullmatch(expected_checkpoint) is None
                    or state["checkpoint_sha256"] != expected_checkpoint):
                raise RunContextError("expected checkpoint is stale or invalid")
            if state["state"] not in {"prepared", "paused"} or self._lease is not None:
                raise RunContextError("context cannot begin; active or terminal contexts never resume")
            if type(role) is not str or role not in state["roles"]:
                raise RunContextError("role is not allowed")
            budget, tools = self._capture(state, frozen=True, reconcile=True)
            wall = _finite(time.time(), "wall clock")
            if state["state"] == "paused":
                if wall < state["paused_at_wall"]:
                    raise RunContextError("wall clock rolled back during pause")
                state["paused_seconds"] += wall - state["paused_at_wall"]
            remaining = state["active_limit_seconds"] - state["active_seconds"]
            if remaining <= 0:
                state.update(state="exhausted", revision=state["revision"] + 1, paused_at_wall=None)
                state["checkpoint_sha256"] = _checkpoint(state)
                _write_state(self.directory, state)
                raise RunContextError("active time budget exhausted")
            started = _finite(time.monotonic(), "monotonic clock")
            state.update(state="active", revision=state["revision"] + 1, role=role,
                         lease_nonce=secrets.token_hex(16), held_active_seconds=remaining,
                         paused_at_wall=None)
            state["checkpoint_sha256"] = _checkpoint(state)
            _write_state(self.directory, state)
            self._lease = (state["revision"], state["lease_nonce"], os.getpid())
            self._started, self.deadline = started, started + remaining
            self._check_deadline()
            return self._view(state, budget, tools)

    def require_active(self) -> None:
        with _run_lock(self.directory):
            state = self._read()
            self._owns(state)
            self._check_deadline()
            self._capture(state, frozen=False, reconcile=False)
            self._check_deadline()

    def _end(self, cursor: int, outcome: str) -> dict:
        with _run_lock(self.directory):
            state = self._read()
            self._owns(state)
            self._check_deadline()
            if type(cursor) is not int or cursor < state["cursor"]:
                raise RunContextError("cursor must be a nondecreasing integer")
            budget, tools = self._capture(state, frozen=False, reconcile=True)
            self._check_deadline()
            elapsed = time.monotonic() - self._started
            state.update(state=outcome, revision=state["revision"] + 1, cursor=cursor,
                         active_seconds=state["active_seconds"] + elapsed,
                         held_active_seconds=0.0, lease_nonce=None,
                         paused_at_wall=_finite(time.time(), "wall clock") if outcome == "paused" else None)
            state["checkpoint_sha256"] = _checkpoint(state)
            try:
                _write_state(self.directory, state)
                self._check_deadline()
            except BaseException:
                state.update(state="indeterminate", revision=state["revision"] + 1,
                             held_active_seconds=max(0.0, state["active_limit_seconds"] - state["active_seconds"]),
                             lease_nonce=None, paused_at_wall=None,
                             reason_sha256=_sha(b"checkpoint commit outcome uncertain"))
                state["checkpoint_sha256"] = _checkpoint(state)
                _write_state(self.directory, state)
                self._lease = None
                raise
            self._lease = None
            return self._view(state, budget, tools)

    def pause(self, cursor: int) -> dict:
        return self._end(cursor, "paused")

    def finish(self, cursor: int) -> dict:
        return self._end(cursor, "completed")

    def abort(self, reason: str) -> dict:
        if type(reason) is not str or not reason:
            raise RunContextError("abort requires a nonempty reason")
        with _run_lock(self.directory):
            state = self._read()
            self._owns(state)
            budget, tools = self._capture(state, frozen=False, reconcile=False)
            state.update(state="indeterminate", revision=state["revision"] + 1,
                         lease_nonce=None, paused_at_wall=None,
                         reason_sha256=_sha(reason.encode("utf-8")))
            state["checkpoint_sha256"] = _checkpoint(state)
            _write_state(self.directory, state)
            self._lease = None
            return self._view(state, budget, tools)
