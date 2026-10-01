#!/tmp/specorganon-D107-deps-re8v1j45/venv-312/bin/python

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import sys
from pathlib import Path


MAX_SCRIPT_BYTES = 256 * 1024
SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def _unique(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate tool argument key")
        value[key] = item
    return value


def _canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)


def _script_bytes(path):
    before = path.lstat()
    if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
            or stat.S_IMODE(before.st_mode) != 0o600
            or not 0 < before.st_size <= MAX_SCRIPT_BYTES):
        raise ValueError("analysis.py is not a bounded private regular file")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        opened = os.fstat(fd)
        raw = b""
        while len(raw) <= MAX_SCRIPT_BYTES:
            part = os.read(fd, MAX_SCRIPT_BYTES - len(raw) + 1)
            if not part:
                break
            raw += part
        after = os.fstat(fd)
        named = path.lstat()
        identity = lambda item: (item.st_dev, item.st_ino, item.st_mode,
                                 item.st_nlink, item.st_size, item.st_mtime_ns,
                                 item.st_ctime_ns)
        if (len(raw) != before.st_size or len(raw) > MAX_SCRIPT_BYTES
                or identity(before) != identity(opened)
                or identity(opened) != identity(after)
                or identity(after) != identity(named)):
            raise ValueError("analysis.py changed during sealed read")
        return raw
    finally:
        os.close(fd)


def main():
    if len(sys.argv) != 5:
        raise ValueError("expected fixed case, inputs, work, and tool arguments")
    case, inputs, work = map(Path, sys.argv[1:4])
    for path, name in ((case, "case"), (inputs, "inputs"), (work, "work")):
        if (not path.is_absolute() or path.name != name
                or not stat.S_ISDIR(path.lstat().st_mode)):
            raise ValueError("stage directory identity differs")
    if case.parent != inputs.parent or case.parent != work.parent:
        raise ValueError("stage directories do not share one parent")
    raw_args = sys.argv[4]
    args = json.loads(raw_args, object_pairs_hook=_unique,
                      parse_constant=lambda _value: (_ for _ in ()).throw(
                          ValueError("nonfinite tool argument")))
    if (type(args) is not dict or set(args) != {"script_sha256"}
            or type(args["script_sha256"]) is not str
            or SHA256.fullmatch(args["script_sha256"]) is None
            or _canonical(args) != raw_args):
        raise ValueError("tool arguments do not match fixed script digest schema")
    script = work / "analysis.py"
    source = _script_bytes(script)
    if hashlib.sha256(source).hexdigest() != args["script_sha256"]:
        raise ValueError("analysis.py differs from reserved source digest")
    return script, source, case


if __name__ == "__main__":
    try:
        script, source, case = main()
    except (OSError, ValueError, TypeError, UnicodeError) as exc:
        print(f"analysis launcher rejected its sealed inputs: {type(exc).__name__}: {exc}",
              file=sys.stderr)
        raise SystemExit(79) from exc
    sys.dont_write_bytecode = True
    sys.argv = [str(script), str(case)]
    namespace = {"__name__": "__main__", "__file__": str(script),
                 "__package__": None, "__builtins__": __builtins__}
    exec(compile(source, str(script), "exec"), namespace)
