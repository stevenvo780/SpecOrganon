"""Opaque, uncredentialed Docker invocations for the reserved evaluator draft.

No evaluator, expected outputs, ledger, study method, profiles or Docker socket
is mounted in subjects. Owned launch handles and raw streams remain on the host.
Admission/receipt helpers are shared with the production controller; there are
no provider calls. A lost receipt never causes a second subject invocation.
"""
from __future__ import annotations

from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import posixpath
import re
import stat

from specorganon.docker_roles import DockerRoles
from specorganon.role_jobs import JobStore, UncertainJob, canonical, digest, _json, _write, _safe
from specorganon.software_controller import safe_file
from .evaluator import materialize, judge, encoded, exact_json, same_typed


class EvaluationError(ValueError):
    pass


def delivery_inventory(root):
    result = {}
    for path in root.rglob("*"):
        mode = path.lstat().st_mode
        if stat.S_ISLNK(mode) or not (stat.S_ISREG(mode) or stat.S_ISDIR(mode)):
            raise EvaluationError("subject snapshot contains special files")
        if stat.S_ISREG(mode):
            result[str(path.relative_to(root))] = path.read_text(encoding="utf-8")
    return result


def fixture_inventory(root, entries):
    result = []
    for entry in entries:
        path = (os.fsencode(root) + b"/" + bytes.fromhex(entry["path_bytes_hex"])
                if "path_bytes_hex" in entry else root / entry["path"])
        info = os.lstat(path)
        # Content is deliberately irrelevant for metadata-only inventory tasks.
        # Container mounts enforce no writes; this hash is not custody proof.
        result.append({"path_hex": os.fsencode(path).hex(), "mode": info.st_mode,
                       "size": info.st_size, "ino": info.st_ino,
                       "mtime_ns": info.st_mtime_ns, "ctime_ns": info.st_ctime_ns})
    return result


def link_target_observations(raw):
    """Resolve controlled link probes with observed cwd/dirfd information.

    Unknown relative resolution is inconclusive, never inferred clean. Complex
    unfinished clone traces are intentionally not interpreted as custody proof.
    """
    cwd = {"main": "/input/delivery"}
    violations = []
    uncertain = []
    quoted = r'("(?:[^"\\]|\\.)*")'
    shared_fs = 'CLONE_FS' in raw
    for original in raw.splitlines():
        prefix = re.match(r'^\[pid\s+(\d+)\]\s+(.*)$', original)
        pid, line = (prefix.group(1), prefix.group(2)) if prefix else ("main", original)
        base = cwd.get(pid)
        child = re.match(r'(?:clone|clone3|fork|vfork)\(.*\)\s*=\s*(\d+)\s*$', line)
        if child:
            cwd[child.group(1)] = base
        change = re.match(r'chdir\(' + quoted + r'\)\s*=\s*0\s*$', line)
        if change:
            try:
                path = exact_json(change.group(1).encode())
            except (ValueError, UnicodeError):
                path = None
            cwd[pid] = (posixpath.normpath(path if path.startswith('/') else posixpath.join(base, path))
                        if path is not None and (path.startswith('/') or base is not None) else None)
            base = cwd[pid]
        descriptor = re.match(r'fchdir\([^<]*<([^>]+)>\)\s*=\s*0\s*$', line)
        if descriptor:
            cwd[pid] = descriptor.group(1)
            base = cwd[pid]
        elif line.startswith('fchdir(') and re.search(r'=\s*0\s*$', line):
            cwd[pid] = None
            base = None
        read = re.match(r'readlink\(' + quoted + r',', line)
        at = re.match(r'readlinkat\(([^,]+),\s*' + quoted + r',', line)
        if read is None and at is None:
            continue
        token = read.group(1) if read else at.group(2)
        try:
            path = exact_json(token.encode())
        except (ValueError, UnicodeError):
            uncertain.append(original)
            continue
        if at and not path.startswith('/'):
            fd = at.group(1)
            if '<' in fd and fd.endswith('>'):
                base = fd[fd.index('<') + 1:-1]
            elif fd.startswith('AT_FDCWD'):
                base = None if shared_fs else base
            else:
                base = None
        elif not path.startswith('/') and shared_fs:
            # Until a shared-cwd trace parser is verified, refuse to infer a
            # relative target from per-thread state. Absolute/decoded dirfd
            # paths remain observable.
            base = None
        resolved = (posixpath.normpath(path if path.startswith('/') else posixpath.join(base, path))
                    if path.startswith('/') or base is not None else None)
        if resolved == '/fixture/root/link':
            violations.append(original)
        elif resolved is None and not re.search(r'=\s*-1\s', line):
            uncertain.append(original)
    return violations, uncertain


def probe_open_observations(raw):
    matches = []
    for original in raw.splitlines():
        line = re.sub(r'^\[pid\s+\d+\]\s+', '', original)
        if not re.match(r'(?:open|openat|openat2|creat)\(', line):
            continue
        descriptor = re.search(r'=\s*\d+<([^>]+)>', line)
        quoted = re.search(r'"(?:[^"\\]|\\.)*"', line)
        try:
            argument = exact_json(quoted.group(0).encode()) if quoted else None
        except (ValueError, UnicodeError):
            argument = None
        if (descriptor is not None and descriptor.group(1) == '/fixture/root/probe.txt'
                or argument == '/fixture/root/probe.txt'):
            matches.append(original)
    return matches


def content_audit(case, result):
    """Single controlled regular-file probe under actual strace -yy.

    This checks observed opens of this fixture, not a proof over all possible
    inputs or resistance to a hostile program controlling its tracer parent.
    Ordinary stderr framing is tested separately without tracing.
    """
    if result.get("infrastructure_error"):
        return {"status": "inconclusive", "reason": result["infrastructure_error"]}
    if result.get("timed_out") or result.get("truncated_streams") or result["exit_code"]:
        return {"status": "fail", "reason": "audit subject did not close successfully"}
    # A subject can forge trace-looking lines on stderr. Never parse that
    # shared stream as trusted tracer evidence. Separate collector is pending;
    # the current Docker trace path therefore returns inconclusive.
    if type(result.get('trace')) is not bytes:
        return {"status": "inconclusive", "reason": "isolated tracer stream not collected"}
    raw = result['trace'].decode("utf-8", errors="replace")
    if not re.search(r'execve\("/opt/specorganon/venv/bin/python".*= 0', raw):
        return {"status": "inconclusive", "reason": "tracer did not observe Python launch"}
    if not re.search(r'\bexit_group\(0\)', raw):
        return {"status": "inconclusive", "reason": "tracer did not observe successful subject exit"}
    try:
        value = exact_json(result["stdout"])
    except (ValueError, UnicodeError, RecursionError):
        return {"status": "fail", "reason": "audit output JSON"}
    if not result["stdout"].endswith(b"\n") or not same_typed(value, case["expected"]):
        return {"status": "fail", "reason": "audit output contract"}
    opened = probe_open_observations(raw)
    link_reads, uncertain = link_target_observations(raw)
    violations = opened + link_reads
    if uncertain and not violations:
        return {"status": "inconclusive", "reason": "relative link resolution not observed",
                "uncertain_syscalls": uncertain}
    return {"status": "fail" if violations else "pass",
            "reason": "observed content/link-target access" if violations else "no forbidden probe access observed",
            "matching_syscalls": violations}


def audit_case():
    return {"id": "content-probe", "task": "treemap", "group": "content-access",
            "entries": [{"kind": "file", "path": "probe.txt", "size": 3},
                        {"kind": "link", "path": "link", "target": "probe.txt"}],
            "argv": ["--root", "/fixture/root"], "stdin_hex": "",
            "expected": {"files": [{"path": "probe.txt", "bytes": 3}],
                         "total_bytes": 3, "symlinks": ["link"]}, "trace": True}


class ReservedDocker:
    """One private journal per opaque delivery, immutable inputs, no reruns."""
    def __init__(self, root, image):
        self.root = _safe(root)
        self.root.mkdir(parents=True, mode=0o700, exist_ok=True)
        self.image = DockerRoles._image(image)
        self.store = JobStore(self.root / "journal", max_jobs=512, max_elapsed_seconds=6000)
        policy = {"schema": 1, "image": self.image, "invocation_seconds": 3,
                  "attach_seconds": 10, "memory": "1g", "cpus": "2", "pids": 128,
                  "stream_cap_bytes": 2_097_152,
                  "scope": "reserved evaluator draft, never native generation"}
        path = self.root / "policy.json"
        if path.exists() and _json(path) != policy:
            raise EvaluationError("reserved policy changed; no silent migration")
        if not path.exists():
            _write(path, policy)

    @contextmanager
    def _lock(self):
        fd = os.open(self.root / ".lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            os.close(fd)

    def _inspect(self, plan):
        found = DockerRoles._cli(["inspect", plan["name"]], allow_failure=True)
        if found.returncode:
            return None
        value = exact_json(found.stdout)[0]
        if value["Config"]["Labels"].get("specorganon.reserved") != plan["label"] or value["Image"] != self.image:
            raise EvaluationError("owned container identity diverged")
        return value

    def _reconcile(self, folder, plan):
        value = self._inspect(plan)
        if value is not None and value["State"]["Running"]:
            DockerRoles._cli(["kill", value["Id"]], allow_failure=True)
            value = self._inspect(plan)
            if value is not None and value["State"]["Running"]:
                raise EvaluationError("owned subject still running")
        _write(folder / "uncertain.json", {"status": "inconclusive",
                                           "handle_missing": value is None, "restarted": False})

    def run(self, job_id, case, files):
        with self._lock():
            return self._run(job_id, case, files)

    def _run(self, job_id, case, files):
        if type(job_id) is not str or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", job_id) is None:
            raise EvaluationError("invalid opaque invocation ID")
        if case["task"] not in {"routeplan", "treemap"}:
            raise EvaluationError("unknown reserved task")
        if len(canonical(files)) > 20_000 or any(type(v) is not str for v in files.values()):
            raise EvaluationError("delivery exceeds common file envelope")
        for name in files:
            safe_file(name)
        folder = self.root / "invocations" / job_id
        request = {"schema": 1, "fixture_sha256": digest(encoded(case)),
                   "delivery_sha256": digest(canonical(files))}
        if folder.exists():
            if not (folder / "plan.json").exists():
                raise UncertainJob("fixture preparation interrupted; never replace")
            plan = _json(folder / "plan.json")
            if plan["request"] != request:
                raise EvaluationError("reserved invocation inputs changed")
        else:
            folder.mkdir(parents=True, mode=0o700)
            inp = folder / "input"
            inp.mkdir(mode=0o700)
            delivery = inp / "delivery"
            delivery.mkdir(mode=0o700)
            for name, text in files.items():
                path = delivery / name
                path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
                path.write_text(text, encoding="utf-8")
            fixture = folder / "fixture"
            fixture.mkdir(mode=0o755)
            if case["task"] == "treemap":
                materialize(fixture / "root", case["entries"])
            subject = ["/opt/specorganon/venv/bin/python", "-E", "-s", "-B",
                       "/input/delivery/" + case["task"] + ".py", *case["argv"]]
            traced = (["/usr/bin/strace", "-f", "-qq", "-yy", "-s", "4096", "-e",
                       "trace=%file,%network,%process,exit_group", *subject] if case.get("trace") else subject)
            command = ["/usr/bin/timeout", "--signal=KILL", "3s", *traced]
            label = digest(canonical({"root": str(self.root), "job": job_id}))[:24]
            name = "specorganon-eval-" + label
            args = ["create", "--name", name, "--label", "specorganon.reserved=" + label,
                    "--interactive", "--read-only", "--network", "none", "--cap-drop=ALL",
                    "--security-opt", "no-new-privileges", "--user", "1000:1000",
                    "--memory", "1g", "--cpus", "2", "--pids-limit", "128",
                    "--tmpfs", "/tmp:rw,nosuid,size=256m", "-e", "HOME=/tmp", "-e", "TMPDIR=/tmp",
                    "--mount", f"type=bind,src={inp},dst=/input,readonly",
                    "--mount", f"type=bind,src={fixture},dst=/fixture,readonly",
                    "-w", case.get("cwd", "/input/delivery"), "--entrypoint", "", self.image, *command]
            fixture_index = fixture_inventory(fixture / "root", case.get("entries", []))
            plan = {"schema": 1, "name": name, "label": label, "request": request,
                    "fixture_index": fixture_index,
                    "create_argv": args, "subject_argv": subject, "container_id": None}
            _write(folder / "plan.json", plan)
        # Delivery bytes are the only subject code available. Verify before and
        # after dispatch; expected values and journal stay physically unmounted.
        if delivery_inventory(folder / "input/delivery") != files:
            raise EvaluationError("prepared subject files diverged")
        if fixture_inventory(folder / "fixture/root", case.get("entries", [])) != plan["fixture_index"]:
            raise EvaluationError("prepared fixture metadata diverged")
        value = self._inspect(plan)
        if plan["container_id"] is None:
            if value is None:
                handle = DockerRoles._cli(plan["create_argv"]).stdout.decode().strip()
                if re.fullmatch(r"[0-9a-f]{64}", handle) is None:
                    raise EvaluationError("invalid created subject handle")
                plan["container_id"] = handle
            else:
                plan["container_id"] = value["Id"]
            _write(folder / "plan.json", plan)
            value = self._inspect(plan)
        if value is None or value["Id"] != plan["container_id"]:
            raise UncertainJob("recorded evaluator handle missing; never recreate")
        closed = (self.store.root / job_id / "receipt.json").exists()
        started = (self.store.root / job_id / "started.json").exists()
        if value["State"]["Status"] != "created" and not closed and not started:
            self._reconcile(folder, plan)
            raise UncertainJob("subject already started without journal; never restart")
        if value["Config"]["Cmd"] != plan["create_argv"][plan["create_argv"].index(self.image) + 1:]:
            raise EvaluationError("subject command diverged")
        try:
            job = self.store.execute(job_id, ["/usr/bin/docker", "start", "--attach", "--interactive", plan["container_id"]],
                                     request, cwd=self.root, timeout_seconds=10,
                                     metadata={"image": self.image, "container": plan["container_id"]},
                                     cancel_argv=["/usr/bin/docker", "kill", plan["container_id"]],
                                     stdin_bytes=bytes.fromhex(case["stdin_hex"]))
        except UncertainJob:
            self._reconcile(folder, plan)
            raise
        terminal = self._inspect(plan)
        if terminal is None or terminal["State"]["Running"]:
            self._reconcile(folder, plan)
            raise UncertainJob("subject closure uncertain")
        if delivery_inventory(folder / "input/delivery") != files:
            raise EvaluationError("subject bytes changed during invocation")
        if fixture_inventory(folder / "fixture/root", case.get("entries", [])) != plan["fixture_index"]:
            raise EvaluationError("fixture metadata changed during invocation")
        receipt = job["receipt"]
        code = terminal["State"]["ExitCode"]
        if code != receipt["exit_code"] and not (receipt["timed_out"] or receipt["truncated_streams"]):
            raise EvaluationError("subject and attachment codes diverged")
        result = {"exit_code": code, "stdout": job["stdout"], "stderr": job["stderr"],
                  "timed_out": code == 137 or receipt["timed_out"],
                  "truncated_streams": receipt["truncated_streams"],
                  "infrastructure_error": "attachment deadline" if receipt["timed_out"] else None}
        # OOM is an observed subject resource failure; it is not promoted to a
        # pass, even if an optimistic partial JSON was flushed first.
        verdict = content_audit(case, result) if case.get("trace") else judge(case, result)
        measured = {"schema": 1, "verdict": verdict, "subject_exit_code": code,
                    "subject_limit_exit_137": code == 137, "oom_killed": terminal["State"]["OOMKilled"],
                    "receipt_ref": str(self.store.root / job_id / "receipt.json"),
                    "stdout_sha256": receipt["stdout_sha256"], "stderr_sha256": receipt["stderr_sha256"],
                    "request": request, "subject_argv": plan["subject_argv"],
                    "reused_closed_receipt": job["reused"], "native_model_calls": 0}
        _write(folder / "verdict.json", measured)
        return measured
