"""Build one self-contained, sealable development prototype tool.

The emitted executable carries the exact bytes of ``prototypes/core.py``. Its
JSON interface is deliberately narrower than that core's CLI: no model request
can issue a normative approval or select another workflow mode.
"""

from __future__ import annotations

import base64
import hashlib
import os
import stat
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CORE = ROOT / "prototypes" / "core.py"
MAX_CORE_BYTES = 1024 * 1024


_RUNTIME = r'''
from __future__ import annotations

import base64
import contextlib
import hashlib
import io
import json
import os
import re
import stat
import sys
import types
from pathlib import Path


CORE_BYTES = base64.b64decode("__EMBEDDED_CORE_B64__", validate=True)
CORE_SHA256 = "__EMBEDDED_CORE_SHA256__"
if hashlib.sha256(CORE_BYTES).hexdigest() != CORE_SHA256:
    raise SystemExit("embedded prototype core digest differs")
_core = types.ModuleType("embedded_development_prototype_core")
_core.__file__ = "<embedded prototypes/core.py>"
exec(compile(CORE_BYTES, _core.__file__, "exec"), _core.__dict__)

MODE = {"A": "sequential", "B": "graph", "C": "risk"}
WRITABLE = {"analysis.py", "report.md", "sources.json"}
MAX_REQUEST = 16 * 1024
MAX_FILE = 256 * 1024
MAX_PUBLIC_FILE = 4 * 1024 * 1024
MAX_CHUNK = 8192
MAX_CORE_OUTPUT = 128 * 1024
MAX_STDERR = 8192


class ToolError(ValueError):
    pass


class MethodRejected(ValueError):
    pass


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ToolError("duplicate JSON key")
        result[key] = value
    return result


def strict_json(raw):
    try:
        return json.loads(raw, object_pairs_hook=pairs,
                          parse_constant=lambda _value: (_ for _ in ()).throw(
                              ToolError("nonfinite JSON value")))
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise ToolError("invalid strict JSON") from exc


def canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("ascii")


def exact(value, keys):
    if type(value) is not dict or set(value) != set(keys):
        raise ToolError("request fields differ from operation schema")


def directory(path: Path, name: str):
    if not path.is_absolute() or path.name != name:
        raise ToolError("tool directory identity is invalid")
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode):
        raise ToolError("tool directory is not a real directory")


def file_state(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_nlink,
            info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def regular(path: Path, maximum: int, *, optional=False):
    try:
        info = path.lstat()
    except FileNotFoundError:
        if optional:
            return None
        raise ToolError("required regular file is absent") from None
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > maximum:
        raise ToolError("file is linked, nonregular, or too large")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        observed = os.fstat(fd)
        if not stat.S_ISREG(observed.st_mode) or observed.st_nlink != 1:
            raise ToolError("file identity changed")
        raw = b""
        while len(raw) <= maximum:
            chunk = os.read(fd, maximum - len(raw) + 1)
            if not chunk:
                break
            raw += chunk
        if (len(raw) > maximum or file_state(os.fstat(fd)) != file_state(observed)
                or file_state(path.lstat()) != file_state(observed)):
            raise ToolError("file changed or exceeded limit during read")
        return raw
    finally:
        os.close(fd)


def private_new(path: Path, raw: bytes):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600:
            raise ToolError("private method file was not created with mode 0600")
        with os.fdopen(fd, "wb", closefd=False) as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        os.close(fd)
    folder = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(folder)
    finally:
        os.close(folder)


def safe_name(name):
    if (type(name) is not str or not name or name in {".", ".."}
            or "/" in name or "\\" in name or "\x00" in name
            or len(name.encode("utf-8")) > 160):
        raise ToolError("file name is not a flat public name")
    return name


def identity(case: Path, inputs: Path):
    manifest_raw = regular(case / "case.json", 1024 * 1024)
    prompt_raw = regular(inputs / "arm_prompt", 64 * 1024)
    manifest, prompt = strict_json(manifest_raw), strict_json(prompt_raw)
    if type(manifest) is not dict or type(manifest.get("case_id")) is not str or not manifest["case_id"]:
        raise ToolError("case manifest lacks a case identity")
    files, deliverables = manifest.get("files"), manifest.get("deliverables")
    if (type(files) is not list or not 1 <= len(files) <= 64
            or type(deliverables) is not list):
        raise ToolError("case manifest lacks public files or deliverables")
    public = {}
    for item in files:
        if (type(item) is not dict or set(item) != {"path", "sha256", "bytes"}
                or type(item["sha256"]) is not str
                or re.fullmatch(r"[0-9a-f]{64}", item["sha256"]) is None
                or type(item["bytes"]) is not int
                or not 0 <= item["bytes"] <= MAX_PUBLIC_FILE):
            raise ToolError("case manifest file record is invalid")
        name = safe_name(item["path"])
        if name in public:
            raise ToolError("duplicate public file name")
        public[name] = item
    if (any(type(name) is not str or safe_name(name) not in WRITABLE | {"metrics.json"}
            for name in deliverables) or len(set(deliverables)) != len(deliverables)):
        raise ToolError("deliverables are not supported")
    exact(prompt, ("alternative", "mode", "instructions"))
    alternative, mode = prompt["alternative"], prompt["mode"]
    if (alternative not in MODE or mode != MODE[alternative]
            or type(prompt["instructions"]) is not str or not prompt["instructions"].strip()):
        raise ToolError("alternative, mode, or instructions are invalid")
    return manifest, public, set(deliverables), alternative, mode, sha(manifest_raw), sha(prompt_raw)


def state_digest(work: Path):
    raw = regular(work / "method_state.json", MAX_FILE, optional=True)
    return None if raw is None else sha(raw)


def proposal_digest(work: Path):
    raw = regular(work / "proposal.json", MAX_FILE, optional=True)
    return None if raw is None else sha(raw)


def result_base(op, manifest, alternative, mode, manifest_sha, prompt_sha, work):
    return {"schema": 1, "operation": op, "alternative": alternative,
            "mode": mode, "case_id": manifest["case_id"],
            "case_manifest_sha256": manifest_sha, "arm_prompt_sha256": prompt_sha,
            "embedded_core_sha256": CORE_SHA256,
            "method_state_sha256": state_digest(work),
            "proposal_sha256": proposal_digest(work),
            "parallel_work_executed": False}


def run_core(mode, args):
    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        code = _core.run(mode, args)
    if code not in {0, 2}:
        raise ToolError("prototype core returned an unexpected exit code")
    raw = stdout.getvalue()
    if len(raw.encode("utf-8")) > MAX_CORE_OUTPUT or len(stderr.getvalue().encode("utf-8")) > MAX_STDERR:
        raise ToolError("prototype core output exceeded its bound")
    outcome = strict_json(raw)
    if type(outcome) is not dict or outcome.get("ok") is not (code == 0):
        raise ToolError("prototype core output disagrees with exit code")
    return code, outcome, stderr.getvalue()


def prototype_operation(request, manifest, mode, work):
    op = request["op"]
    state = work / "method_state.json"
    if op == "init":
        exact(request, ("op", "nodes"))
        nodes = request["nodes"]
        if type(nodes) is not list or not 4 <= len(nodes) <= 64:
            raise MethodRejected("prototype proposal needs 4 to 64 nodes")
        if any(type(node) is not dict or node.get("status") != "pending"
               or not {"id", "kind", "phase", "status", "claim", "depends_on"} <= set(node)
               or set(node) - {"id", "kind", "phase", "status", "claim", "depends_on", "risk"}
               for node in nodes):
            raise MethodRejected("prototype nodes must begin pending with exact fields")
        proposal = {"case_id": manifest["case_id"], "nodes": nodes}
        try:
            validated = _core.validate_case(proposal)
        except _core.WorkflowError as exc:
            raise MethodRejected(str(exc)) from exc
        normative = [key for key, node in validated.items() if node["kind"] == "normative"]
        if not any(node["kind"] == "requirement" and node["phase"] == "engineering"
                   and any(key in _core.closure_versions(validated, [node_id]) for key in normative)
                   for node_id, node in validated.items()):
            raise MethodRejected("engineering requirement lacks pending normative dependency")
        if proposal_digest(work) is not None or state_digest(work) is not None:
            raise MethodRejected("prototype is already initialized")
        private_new(work / "proposal.json", canonical(proposal) + b"\n")
        return run_core(mode, ["init", "--case", str(work / "proposal.json"),
                               "--state", str(state)])
    if state_digest(work) is None:
        raise MethodRejected("prototype is not initialized")
    if op == "status":
        exact(request, ("op",))
        args = ["status"]
    elif op == "revise":
        exact(request, ("op", "id", "status", "reason"))
        if (type(request["id"]) is not str or not request["id"]
                or request["status"] not in {"pending", "supported", "contradicted"}
                or type(request["reason"]) is not str or not request["reason"].strip()):
            raise ToolError("revise arguments are invalid")
        args = ["revise", "--id", request["id"], "--status", request["status"],
                "--reason", request["reason"]]
    elif op == "review":
        exact(request, ("op", "id"))
        if type(request["id"]) is not str or not request["id"]:
            raise ToolError("review id is invalid")
        args = ["review", "--id", request["id"]]
    elif op == "advance":
        exact(request, ("op", "phase"))
        if request["phase"] not in _core.PHASES:
            raise ToolError("advance phase is invalid")
        args = ["advance", "--phase", request["phase"]]
    elif op == "plan":
        exact(request, ("op", "budget"))
        if type(request["budget"]) is not int or not 1 <= request["budget"] <= 64:
            raise ToolError("plan task budget is invalid")
        args = ["plan", "--budget", str(request["budget"])]
    else:
        raise ToolError("prototype operation is not allowed")
    args += ["--state", str(state)]
    return run_core(mode, args)


def read_public(request, case, public):
    exact(request, ("op", "path", "offset", "length"))
    name = safe_name(request["path"])
    if name not in public:
        raise ToolError("public file is not enumerated in case manifest")
    offset, length = request["offset"], request["length"]
    if type(offset) is not int or offset < 0 or type(length) is not int or not 1 <= length <= MAX_CHUNK:
        raise ToolError("read offset or length is invalid")
    record = public[name]
    raw = regular(case / name, MAX_PUBLIC_FILE)
    if len(raw) != record["bytes"] or sha(raw) != record["sha256"]:
        raise ToolError("public source differs from case manifest")
    try:
        raw.decode("utf-8")
    except UnicodeError as exc:
        raise ToolError("public file is not UTF-8 text") from exc
    if offset > len(raw):
        raise ToolError("read offset exceeds file")
    end = min(len(raw), offset + length)
    while end > offset:
        try:
            content = raw[offset:end].decode("utf-8")
            break
        except UnicodeError:
            end -= 1
    else:
        if offset == len(raw):
            content = ""
        else:
            raise ToolError("read range splits a UTF-8 character")
    return {"path": name, "offset": offset, "next_offset": end,
            "eof": end == len(raw), "content": content,
            "source_sha256": record["sha256"]}


def write_deliverable(request, work, deliverables):
    exact(request, ("op", "path", "offset", "content"))
    name = safe_name(request["path"])
    if name not in WRITABLE or name not in deliverables:
        raise ToolError("write path is not an allowed deliverable")
    offset, content = request["offset"], request["content"]
    if type(offset) is not int or offset < 0 or type(content) is not str:
        raise ToolError("write offset or content is invalid")
    raw = content.encode("utf-8")
    if not raw or len(raw) > MAX_CHUNK or offset + len(raw) > MAX_FILE:
        raise ToolError("write chunk or total file exceeds limit")
    path = work / name
    try:
        fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_NOFOLLOW)
    except FileNotFoundError:
        if offset != 0:
            raise ToolError("new deliverable requires offset zero") from None
        fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                or stat.S_IMODE(info.st_mode) != 0o600 or info.st_size != offset):
            raise ToolError("deliverable offset or file identity differs")
        written = os.write(fd, raw)
        if written != len(raw):
            raise ToolError("deliverable write was partial")
        os.fsync(fd)
    finally:
        os.close(fd)
    return {"path": name, "bytes": offset + len(raw),
            "sha256": sha(regular(path, MAX_FILE))}


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    try:
        if len(argv) != 4 or len(argv[3].encode("ascii")) > MAX_REQUEST:
            raise ToolError("expected case, inputs, work, and bounded canonical tool args")
        case, inputs, work = map(Path, argv[:3])
        for path, name in ((case, "case"), (inputs, "inputs"), (work, "work")):
            directory(path, name)
        if case.parent != inputs.parent or case.parent != work.parent:
            raise ToolError("tool directories do not share one stage")
        outer = strict_json(argv[3])
        exact(outer, ("request",))
        if type(outer["request"]) is not str or canonical(outer).decode("ascii") != argv[3]:
            raise ToolError("tool args are not canonical or request is not a string")
        request = strict_json(outer["request"])
        if type(request) is not dict or type(request.get("op")) is not str:
            raise ToolError("request must be an operation object")
        manifest, public, deliverables, alternative, mode, manifest_sha, prompt_sha = identity(case, inputs)
        op = request["op"]
        base = result_base(op, manifest, alternative, mode, manifest_sha, prompt_sha, work)
        if op in {"init", "status", "revise", "review", "advance", "plan"}:
            try:
                code, result, stderr = prototype_operation(request, manifest, mode, work)
                details = {"method_result": result, "method_stderr": stderr}
            except MethodRejected as exc:
                code, details = 2, {"method_error": str(exc)}
        elif op == "read":
            code, details = 0, read_public(request, case, public)
        elif op == "write":
            code, details = 0, write_deliverable(request, work, deliverables)
        elif op == "analyze":
            raise ToolError("analysis execution is disabled; use an independently isolated evaluator")
        else:
            raise ToolError("operation is not allowed")
        base.update(ok=code == 0, method_exit_code=code, details=details,
                    method_state_sha256=state_digest(work),
                    proposal_sha256=proposal_digest(work))
        print(json.dumps(base, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False))
        return 0
    except (ToolError, OSError, TypeError, KeyError, OverflowError, UnicodeError) as exc:
        print(f"development method tool failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
'''


def build_tool(destination: Path, *, core_path: Path = DEFAULT_CORE) -> dict[str, str | int]:
    """Create a new executable with exact embedded prototype core bytes."""
    destination = Path(destination)
    core_path = Path(core_path)
    info = core_path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > MAX_CORE_BYTES:
        raise ValueError("prototype core must be a bounded, single-link regular file")
    core = core_path.read_bytes()
    if len(core) != info.st_size:
        raise ValueError("prototype core changed during build")
    core_sha = hashlib.sha256(core).hexdigest()
    encoded = base64.b64encode(core).decode("ascii")
    runtime = _RUNTIME.replace("__EMBEDDED_CORE_B64__", encoded).replace(
        "__EMBEDDED_CORE_SHA256__", core_sha)
    script = (f"#!{sys.executable}\n" + runtime).encode("utf-8")
    if not destination.parent.is_dir() or destination.exists() or destination.is_symlink():
        raise FileExistsError("tool destination must be new under an existing directory")
    fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o500)
    try:
        os.fchmod(fd, 0o500)
        with os.fdopen(fd, "wb", closefd=False) as stream:
            stream.write(script)
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        os.close(fd)
    folder = os.open(destination.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(folder)
    finally:
        os.close(folder)
    return {"path": str(destination), "sha256": hashlib.sha256(script).hexdigest(),
            "bytes": len(script), "embedded_core_sha256": core_sha, "mode": 0o500}
