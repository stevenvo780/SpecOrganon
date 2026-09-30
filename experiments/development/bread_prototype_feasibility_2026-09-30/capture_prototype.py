"""Capture actual local prototype commands in an exposed native-agent pilot.

This helper records observations under the same UID; it is neither a custody
service nor a global native-agent budget controller. Run inside a staged trial.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


def digest(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def main() -> int:
    root = Path(__file__).resolve().parent
    profile = json.loads((root / "profile.json").read_text())
    mode = profile["mode"]
    scripts = {"sequential": "sequential.py", "graph": "graph.py", "risk": "risk.py"}
    if mode not in scripts:
        raise ValueError("unknown prototype mode")
    arguments = sys.argv[1:]
    journal = root / "prototype_calls.jsonl"
    previous = journal.read_text().splitlines() if journal.exists() else []
    if len(previous) >= 20:
        print("prototype call allowance exhausted", file=sys.stderr)
        return 2
    before = digest(root / "state.json")
    started = time.monotonic()
    stamp = datetime.now(timezone.utc).isoformat()
    allowed = {"init", "status", "advance", "revise", "review", "plan"}
    if (not arguments or arguments[0] not in allowed
            or arguments.count("--state") != 1
            or arguments[arguments.index("--state") + 1:] == []
            or arguments[arguments.index("--state") + 1] != "state.json"
            or (arguments[0] == "init" and (arguments.count("--case") != 1
                or arguments[arguments.index("--case") + 1:] == []
                or arguments[arguments.index("--case") + 1] != "prototype_case.json"))):
        code, stdout, stderr = 2, "", "Only scoped prototype operations without normative approval are allowed.\n"
    else:
        environment = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8",
                       "PYTHONNOUSERSITE": "1", "PYTHONDONTWRITEBYTECODE": "1"}
        try:
            result = subprocess.run(
                [sys.executable, "harness/" + scripts[mode], *arguments],
                cwd=root, env=environment, capture_output=True, text=True,
                timeout=10, check=False,
            )
            code, stdout, stderr = result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            code, stdout, stderr = 124, "", "prototype command exceeded 10 seconds\n"
    record = {"schema": 1, "seq": len(previous) + 1, "mode": mode,
              "started_utc_declared": stamp, "duration_seconds_local": time.monotonic() - started,
              "argv": ["python", "harness/" + scripts[mode], *arguments], "exit_code": code,
              "stdout": stdout, "stderr": stderr, "state_before_sha256": before,
              "state_after_sha256": digest(root / "state.json"),
              "helper_sha256": digest(Path(__file__)), "custody_independent": False}
    with journal.open("a", encoding="utf-8") as output:
        output.write(json.dumps(record, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n")
        output.flush()
        os.fsync(output.fileno())
    sys.stdout.write(stdout)
    sys.stderr.write(stderr)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
