"""Build an opt-in development driver with fixed branch ownership.

The original development tool and prototype kernel keep their bytes and
contracts. This builder adds a closed guard before the original dispatcher.
Branch effects are proposals; no normative approval or phase advance is exposed.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import stat
import sys
from pathlib import Path

from development_method_tool import DEFAULT_CORE, MAX_CORE_BYTES, _RUNTIME
from run_managed_conversation import _fsync_dir


_ANCHOR = '        op = request["op"]\n        base = result_base('


def build_branch_tool(destination: Path, owned_node_ids: list[str], *,
                      core_path: Path = DEFAULT_CORE) -> dict:
    if (type(owned_node_ids) is not list or not owned_node_ids
            or any(type(node) is not str or not node.strip() for node in owned_node_ids)
            or len(set(owned_node_ids)) != len(owned_node_ids)):
        raise ValueError("branch ownership must be a nonempty unique list")
    core_path, destination = Path(core_path), Path(destination)
    fd = os.open(core_path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > MAX_CORE_BYTES:
            raise ValueError("prototype core must be a bounded single-link regular file")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            raw = stream.read(MAX_CORE_BYTES + 1)
        after = os.fstat(fd)
        if (len(raw) != info.st_size or
                (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns) !=
                (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)):
            raise ValueError("prototype core changed during build")
    finally:
        os.close(fd)
    core_sha = hashlib.sha256(raw).hexdigest()
    runtime = _RUNTIME.replace("__EMBEDDED_CORE_B64__", base64.b64encode(raw).decode()).replace(
        "__EMBEDDED_CORE_SHA256__", core_sha)
    guard = ('        op = request["op"]\n'
             '        if op in {"init", "advance", "approve"}:\n'
             '            raise ToolError("branch cannot initialize, approve or advance")\n'
             '        if op in {"revise", "review"}:\n'
             f'            if request.get("id") not in {json.dumps(owned_node_ids)}:\n'
             '                raise ToolError("operation is outside branch ownership")\n'
             '        base = result_base(')
    if runtime.count(_ANCHOR) != 1:
        raise ValueError("development dispatcher anchor changed; rebuild must be reviewed")
    script = (f"#!{sys.executable}\n" + runtime.replace(_ANCHOR, guard)).encode()
    if not destination.parent.is_dir():
        raise ValueError("branch tool parent must already exist")
    fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o500)
    try:
        os.fchmod(fd, 0o500)
        with os.fdopen(fd, "wb", closefd=False) as stream:
            stream.write(script)
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        os.close(fd)
    _fsync_dir(destination.parent)
    return {"path": str(destination), "sha256": hashlib.sha256(script).hexdigest(),
            "bytes": len(script), "embedded_core_sha256": core_sha,
            "owned_node_ids": list(owned_node_ids), "mode": 0o500}
