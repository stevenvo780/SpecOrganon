"""Bounded external jobs with persistent, non-retrying execution receipts.

This journal does not authenticate reviewers, approve phases or sandbox commands.
The delivery controller supplies isolated transports and applies engine guards.
An interrupted job without a receipt is uncertain, even if its process later exits.
The operator must keep the journal private and outside role mounts. Hashes detect
divergence; a writer controlling all records can fabricate a coherent journal.
Process-group cleanup handles owned children, not descendants escaping the group
or SIGKILL of this owner. Isolated transports must enforce their own lifecycle.
"""
from __future__ import annotations

from contextlib import contextmanager
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import selectors
import signal
import stat
import subprocess
import time
import uuid

from .ledger import strict_json_loads


class JobError(ValueError):
    """A job cannot be admitted or its measured record has diverged."""


class UncertainJob(JobError):
    """Execution began but no closed receipt proves its process outcome."""


def canonical(value):
    try:
        return json.dumps(value, sort_keys=True, ensure_ascii=False,
                          separators=(",", ":"), allow_nan=False).encode()
    except (TypeError, ValueError, UnicodeError) as exc:
        raise JobError("job data is not finite JSON") from exc


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def _safe(path):
    path = Path(path).absolute()
    if any(p.is_symlink() for p in [path, *path.parents]):
        raise JobError("job path must not traverse a symlink")
    return path


def _parent(path, dir_fd=None):
    path = Path(path)
    if dir_fd is None:
        parts = path.absolute().parts[1:]
        fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    else:
        if path.is_absolute(): raise JobError("anchored record name must be relative")
        parts = path.parts; fd = os.dup(dir_fd)
    try:
        if not parts or any(part in {".", "..", ""} for part in parts):
            raise JobError("invalid record components")
        for part in parts[:-1]:
            next_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd); fd = next_fd
        return fd, parts[-1]
    except BaseException:
        os.close(fd); raise


def _read(path, limit=2_097_152, *, dir_fd=None):
    parent_fd = None
    try:
        parent_fd, name = _parent(path, dir_fd)
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent_fd)
        with os.fdopen(fd, "rb") as file:
            before = os.fstat(file.fileno())
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size > limit:
                raise JobError("job record must be bounded, singly linked regular data")
            raw = file.read(limit + 1)
            after = os.fstat(file.fileno())
        if len(raw) != before.st_size or (before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns):
            raise JobError("job record changed during read")
        return raw
    except OSError as exc:
        raise JobError(f"cannot read job record {Path(path).name}") from exc
    finally:
        if parent_fd is not None: os.close(parent_fd)


def _json(path, *, dir_fd=None):
    try:
        return strict_json_loads(_read(path, dir_fd=dir_fd).decode())
    except (ValueError, UnicodeError) as exc:
        raise JobError(f"invalid job JSON {Path(path).name}") from exc


def _write(path, value, *, dir_fd=None):
    parent_fd, name = _parent(path, dir_fd)
    temp = "." + name + "." + uuid.uuid4().hex
    try:
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent_fd)
        with os.fdopen(fd, "wb") as file:
            file.write(canonical(value)); file.flush(); os.fsync(file.fileno())
        os.replace(temp, name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
        os.fsync(parent_fd)
    finally:
        try: os.unlink(temp, dir_fd=parent_fd)
        except FileNotFoundError: pass
        os.close(parent_fd)


def _argv(value):
    if (type(value) is not list or not 1 <= len(value) <= 256
            or any(type(v) is not str or not v or "\0" in v for v in value)
            or not os.path.isabs(value[0]) or len(canonical(value)) > 131_072):
        raise JobError("job argv must be a bounded explicit vector with absolute executable")
    return value


def _positive(value, upper, name):
    if type(value) is not int or not 1 <= value <= upper:
        raise JobError(f"invalid {name} limit")
    return value


class JobStore:
    def __init__(self, root, *, max_jobs=40, max_elapsed_seconds=6000,
                 max_stream_bytes=2_097_152, max_request_bytes=128_000):
        self.root = _safe(root)
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        if not self.root.is_dir(): raise JobError("job root must be a directory")
        parent_fd, name = _parent(self.root)
        try: self._root_fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent_fd)
        finally: os.close(parent_fd)
        info = os.fstat(self._root_fd)
        if info.st_uid != os.geteuid() or info.st_mode & 0o022:
            raise JobError("journal root must be owned and not writable by other users")
        self.policy = {
            "schema": 3,
            "max_jobs": _positive(max_jobs, 1000, "job budget"),
            "max_elapsed_seconds": _positive(max_elapsed_seconds, 6000, "elapsed"),
            "max_stream_bytes": _positive(max_stream_bytes, 2_097_152, "stream"),
            "max_request_bytes": _positive(max_request_bytes, 128_000, "request"),
        }
        with self._lock():
            path = self.root / "policy.json"
            if path.exists():
                current = self._json(path)
                if type(current) is not dict or current.get("policy") != self.policy:
                    raise JobError("job policy changed; use a new explicitly versioned run")
            else:
                self._write(path, {"policy": self.policy, "created_epoch": time.time(),
                                  "created_monotonic": time.monotonic(), "boot_id_sha256": self._boot_id()})

    def __del__(self):
        fd = getattr(self, "_root_fd", None)
        if fd is not None:
            try: os.close(fd)
            except OSError: pass
            self._root_fd = None

    def _relative(self, path):
        return Path(path).relative_to(self.root)

    def _read(self, path, limit=2_097_152):
        return _read(self._relative(path), limit, dir_fd=self._root_fd)

    def _json(self, path):
        return _json(self._relative(path), dir_fd=self._root_fd)

    def _write(self, path, value):
        return _write(self._relative(path), value, dir_fd=self._root_fd)

    @staticmethod
    def _boot_id():
        # Linux monotonic timestamps survive process restarts, not host reboot.
        # An unknown/rebooted clock stops new admission; no silent reset.
        fd = os.open("/proc/sys/kernel/random/boot_id", os.O_RDONLY | os.O_NOFOLLOW)
        try: raw = os.read(fd, 128)
        finally: os.close(fd)
        # procfs reports size zero for this kernel-provided value; it is not a
        # persisted journal file. Validate the fixed, bounded UUID format.
        if re.fullmatch(rb"[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}\n", raw) is None:
            raise JobError("unknown kernel boot clock")
        return digest(raw)

    @contextmanager
    def _lock(self):
        fd = os.open(".jobs.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600, dir_fd=self._root_fd)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise JobError("job lock must be a singly linked regular file")
            fcntl.flock(fd, fcntl.LOCK_EX)
            named = os.stat(".jobs.lock", dir_fd=self._root_fd, follow_symlinks=False)
            if (named.st_dev, named.st_ino) != (info.st_dev, info.st_ino):
                raise JobError("job lock pathname replaced")
            yield
        finally:
            os.close(fd)

    def execute(self, job_id, argv, request, *, cwd, timeout_seconds=180, env=None,
                metadata=None, cancel_argv=None, stdin_bytes=None):
        if type(job_id) is not str or re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}", job_id) is None:
            raise JobError("invalid job ID")
        argv = _argv(argv)
        timeout_seconds = _positive(timeout_seconds, 180, "timeout")
        cwd = _safe(cwd)
        if not cwd.is_dir(): raise JobError("job cwd must exist")
        if env is not None and (type(env) is not dict or any(type(k) is not str or type(v) is not str or "\0" in k + v for k, v in env.items())):
            raise JobError("invalid process environment")
        if cancel_argv is not None: _argv(cancel_argv)
        if stdin_bytes is not None and (type(stdin_bytes) is not bytes or len(stdin_bytes) > 128_000):
            raise JobError("stdin must be bounded bytes")
        # Environment values can contain credentials: retain only their digest.
        effective_env = dict(os.environ) if env is None else dict(env)
        envelope = {"request": request, "argv": argv, "cwd": str(cwd),
                    "environment_sha256": digest(canonical(effective_env)),
                    "metadata": metadata, "timeout_seconds": timeout_seconds,
                    "cancel_argv": cancel_argv,
                    "stdin_sha256": digest(stdin_bytes) if stdin_bytes is not None else None}
        raw = canonical(envelope)
        if len(raw) > self.policy["max_request_bytes"]:
            raise JobError("job request exceeds budget")
        fingerprint = digest(raw)
        with self._lock():
            path = _safe(self.root / job_id)
            if path.exists() and not path.is_dir(): raise JobError("job path must be a directory")
            if (path / "receipt.json").exists():
                receipt = self._json(path / "receipt.json")
                if (type(receipt) is not dict or receipt.get("request_sha256") != fingerprint
                        or self._read(path / "request.json") != raw):
                    raise JobError("closed job inputs/argv changed")
                self._validate_receipt(path, job_id, receipt)
                measured = {}
                for name in ("stdout", "stderr"):
                    stream = self._read(path / (name + ".bin"), self.policy["max_stream_bytes"])
                    if digest(stream) != receipt.get(name + "_sha256") or len(stream) != receipt.get(name + "_bytes"):
                        raise JobError("closed job stream changed")
                    measured[name] = stream
                return {"reused": True, "receipt": receipt, **measured}
            if (path / "started.json").exists():
                raise UncertainJob(f"job {job_id} started without receipt; inspect its existing handle, do not restart")
            if path.exists(): raise JobError("job directory exists without admission record")
            policy = self._json(self.root / "policy.json")
            count = sum((p / "started.json").exists() for p in self.root.iterdir() if p.is_dir())
            if policy.get("boot_id_sha256") != self._boot_id():
                raise JobError("execution clock changed; new jobs require a versioned run")
            elapsed = time.monotonic() - policy["created_monotonic"]
            if elapsed < 0: raise JobError("invalid admission clock")
            remaining = self.policy["max_elapsed_seconds"] - elapsed
            # Reserve bounded cleanup before dispatch. This is a process budget,
            # not a guarantee against OS hangs or hostile journal writers.
            if count >= self.policy["max_jobs"] or remaining <= 10:
                raise JobError("job budget exhausted")
            os.mkdir(job_id, mode=0o700, dir_fd=self._root_fd)
            self._write(path / "request.json", envelope)
            started = {"schema": 1, "request_sha256": fingerprint, "started_epoch": time.time(),
                       "pid": None, "metadata": metadata}
            self._write(path / "started.json", started)
            receipt = self._run(path, argv, cwd, effective_env, min(timeout_seconds, remaining - 10), cancel_argv, started, stdin_bytes)
            receipt.update(schema=1, job_id=job_id, request_sha256=fingerprint,
                           argv=argv, cwd=str(cwd), metadata=metadata)
            receipt.setdefault("stdin_bytes_sent", 0)
            receipt.setdefault("stdin_bytes_expected", len(stdin_bytes or b""))
            receipt.setdefault("stdin_complete", receipt["stdin_bytes_sent"] == receipt["stdin_bytes_expected"])
            # Close/fsync both streams before the sole terminal checkpoint.
            self._write(self.root / (".complete-" + job_id + ".json"), {
                "schema": 1, "receipt_sha256": digest(canonical(receipt)),
                "started_sha256": digest(self._read(path / "started.json")),
                "request_sha256": fingerprint})
            self._write(path / "receipt.json", receipt)
            return {"reused": False, "receipt": receipt,
                    **{name: self._read(path / (name + ".bin")) for name in ("stdout", "stderr")}}

    def _validate_receipt(self, path, job_id, value):
        fields = {"schema", "job_id", "request_sha256", "argv", "cwd", "metadata", "exit_code",
                  "timed_out", "truncated_streams", "duration_seconds", "finished_epoch", "cancel_exit_code",
                  "stdin_bytes_sent", "stdin_bytes_expected", "stdin_complete", "stdout_bytes",
                  "stderr_bytes", "stdout_sha256", "stderr_sha256"}
        if (set(value) != fields or type(value["schema"]) is not int or value["schema"] != 1
                or value["job_id"] != job_id or type(value["exit_code"]) is not int
                or type(value["timed_out"]) is not bool or type(value["stdin_complete"]) is not bool
                or any(type(value[k]) is not int or value[k] < 0 for k in
                       ("stdin_bytes_sent", "stdin_bytes_expected", "stdout_bytes", "stderr_bytes"))
                or any(type(value[k]) not in (int, float) or not math.isfinite(value[k]) or value[k] < 0
                       for k in ("duration_seconds", "finished_epoch"))
                or type(value["truncated_streams"]) is not list
                or any(type(v) is not str or v not in {"stdout", "stderr"} for v in value["truncated_streams"])
                or len(set(value["truncated_streams"])) != len(value["truncated_streams"])
                or value["cancel_exit_code"] is not None and type(value["cancel_exit_code"]) is not int
                or value["stdin_bytes_sent"] > value["stdin_bytes_expected"]
                or value["stdin_complete"] != (value["stdin_bytes_sent"] == value["stdin_bytes_expected"])):
            raise JobError("invalid terminal receipt schema")
        admission = self._json(path / "started.json")
        closing = self._json(self.root / (".complete-" + job_id + ".json"))
        if (type(closing) is not dict or type(admission) is not dict
                or closing.get("receipt_sha256") != digest(canonical(value))
                or closing.get("started_sha256") != digest(self._read(path / "started.json"))
                or closing.get("request_sha256") != value["request_sha256"]
                or admission.get("request_sha256") != value["request_sha256"]
                or admission.get("metadata") != value["metadata"]):
            raise JobError("terminal receipt differs from admission/closing record")

    def _run(self, path, argv, cwd, env, timeout, cancel_argv, started, stdin_bytes):
        streams = {}; process = None; selector = None
        began = time.monotonic(); sizes = {"stdout": 0, "stderr": 0}
        timed_out = False; truncated = []; cancel_exit = None; sent = 0
        stopped_at = None
        try:
            for name in ("stdout", "stderr"):
                parent_fd, leaf = _parent(self._relative(path / (name + ".bin")), self._root_fd)
                try:
                    fd = os.open(leaf, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                                 0o600, dir_fd=parent_fd)
                finally: os.close(parent_fd)
                streams[name] = os.fdopen(fd, "wb")
            try:
                process = subprocess.Popen(argv, cwd=cwd, env=env,
                    stdin=subprocess.PIPE if stdin_bytes is not None else subprocess.DEVNULL,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
            except OSError as exc:
                message = f"{type(exc).__name__}: process could not start\n".encode()
                streams["stderr"].write(message[:self.policy["max_stream_bytes"]])
                if len(message) > self.policy["max_stream_bytes"]: truncated.append("stderr")
                return self._finish(streams, path, 127, False, truncated, began, None)
            # Every operation after spawn is covered by the cleanup finally.
            started["pid"] = process.pid
            self._write(path / "started.json", started)
            selector = selectors.DefaultSelector()
            for name in ("stdout", "stderr"):
                pipe = getattr(process, name); os.set_blocking(pipe.fileno(), False)
                selector.register(pipe, selectors.EVENT_READ, name)
            if stdin_bytes:
                os.set_blocking(process.stdin.fileno(), False)
                selector.register(process.stdin, selectors.EVENT_WRITE, "stdin")
            elif process.stdin is not None: process.stdin.close()
            # Pipe closure does not prove process termination. Conversely, a
            # descendant retaining pipes cannot extend the admitted deadline.
            while selector.get_map() or process.poll() is None:
                now = time.monotonic()
                if stopped_at is None and now - began >= timeout:
                    timed_out = True; stopped_at = now; self._terminate(process)
                if stopped_at is not None and cancel_argv is not None and cancel_exit is None:
                    cancel_exit = self._cancel(cancel_argv, cwd, env)
                if stopped_at is not None and time.monotonic() - stopped_at >= 2:
                    for key in list(selector.get_map().values()):
                        selector.unregister(key.fileobj); key.fileobj.close()
                    break
                for key, _ in selector.select(0.05):
                    if key.data == "stdin":
                        try:
                            if stopped_at is None:
                                sent += os.write(key.fileobj.fileno(), memoryview(stdin_bytes)[sent:sent + 8192])
                        except BrokenPipeError:
                            selector.unregister(key.fileobj); key.fileobj.close(); continue
                        except BlockingIOError: continue
                        if stopped_at is not None or sent == len(stdin_bytes):
                            selector.unregister(key.fileobj); key.fileobj.close()
                        continue
                    try: block = os.read(key.fileobj.fileno(), 8192)
                    except BlockingIOError: continue
                    if not block:
                        selector.unregister(key.fileobj); key.fileobj.close(); continue
                    name = key.data; room = self.policy["max_stream_bytes"] - sizes[name]
                    streams[name].write(block[:room]); sizes[name] += min(len(block), room)
                    # Keep observed prefixes inspectable when this owner is
                    # SIGKILLed before a terminal receipt. This is not closure.
                    streams[name].flush()
                    if len(block) > room and name not in truncated:
                        truncated.append(name)
                        if stopped_at is None:
                            stopped_at = time.monotonic(); self._terminate(process)
            code = process.wait(timeout=2)
            receipt = self._finish(streams, path, code, timed_out, truncated, began, cancel_exit)
            receipt.update(stdin_bytes_sent=sent, stdin_bytes_expected=len(stdin_bytes or b""),
                           stdin_complete=sent == len(stdin_bytes or b""))
            return receipt
        except BaseException:
            if process is not None and cancel_argv is not None and cancel_exit is None:
                self._terminate(process); self._cancel(cancel_argv, cwd, env)
            raise
        finally:
            if process is not None:
                self._terminate(process)
                try: process.wait(timeout=2)
                except subprocess.TimeoutExpired: pass
                for name in ("stdout", "stderr", "stdin"):
                    pipe = getattr(process, name)
                    if pipe is not None and not pipe.closed: pipe.close()
            if selector is not None: selector.close()
            for stream in streams.values():
                if not stream.closed: stream.close()

    @classmethod
    def _cancel(cls, argv, cwd, env):
        process = None
        try:
            process = subprocess.Popen(argv, stdin=subprocess.DEVNULL, cwd=cwd, env=env,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
            return process.wait(timeout=2)
        except (OSError, subprocess.TimeoutExpired): return -1
        finally:
            if process is not None:
                cls._terminate(process)
                try: process.wait(timeout=2)
                except subprocess.TimeoutExpired: pass

    @staticmethod
    def _terminate(process):
        try: os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError: pass

    def _finish(self, streams, path, code, timed_out, truncated, began, cancel_exit):
        for stream in streams.values():
            stream.flush(); os.fsync(stream.fileno()); stream.close()
        receipt = {"exit_code": code, "timed_out": timed_out, "truncated_streams": truncated,
                   "duration_seconds": time.monotonic() - began, "finished_epoch": time.time(),
                   "cancel_exit_code": cancel_exit}
        for name in ("stdout", "stderr"):
            raw = self._read(path / (name + ".bin"), self.policy["max_stream_bytes"])
            receipt[name + "_bytes"] = len(raw); receipt[name + "_sha256"] = digest(raw)
        return receipt
