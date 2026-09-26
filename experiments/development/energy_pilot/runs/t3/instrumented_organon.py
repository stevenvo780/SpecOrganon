#!/usr/bin/env python3
"""Development-only local CLI trace; this file is not an authentication boundary."""
import datetime
import hashlib
import json
import os
import pathlib
import subprocess
import sys

script = pathlib.Path(__file__).resolve()
real = script.with_name("organon.real")
log = script.parent.parent.parent / "cli_invocations.jsonl"
started = datetime.datetime.now(datetime.timezone.utc).isoformat()
result = subprocess.run([str(real), *sys.argv[1:]], capture_output=True, check=False)
ended = datetime.datetime.now(datetime.timezone.utc).isoformat()
entry = {
    "started_utc": started,
    "ended_utc": ended,
    "argv": sys.argv[1:],
    "cwd": os.getcwd(),
    "returncode": result.returncode,
    "stdout": result.stdout.decode("utf-8", errors="replace"),
    "stderr": result.stderr.decode("utf-8", errors="replace"),
    "stdout_sha256": hashlib.sha256(result.stdout).hexdigest(),
    "stderr_sha256": hashlib.sha256(result.stderr).hexdigest(),
}
with log.open("a", encoding="utf-8") as handle:
    handle.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")
    handle.flush()
    os.fsync(handle.fileno())
sys.stdout.buffer.write(result.stdout)
sys.stderr.buffer.write(result.stderr)
raise SystemExit(result.returncode)
