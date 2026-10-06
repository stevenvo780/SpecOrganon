"""Capture actual commands, streams, exit status and digests. No ledger writes."""
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import sys
import time

root = Path(__file__).resolve().parents[1]
output = root / "testing" / "results"
output.mkdir(exist_ok=True)
reports = []
for name, argv, timeout in (
    ("examples", [sys.executable, str(root / "testing" / "examples.py")], 30),
    ("contract_tests", [sys.executable, str(root / "testing" / "test_backup.py")], 120),
):
    started = time.monotonic()
    timed_out = False
    try:
        proc = subprocess.run(argv, capture_output=True, timeout=timeout, cwd=root)
        stdout, stderr, exit_code = proc.stdout, proc.stderr, proc.returncode
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        stdout, stderr, exit_code = exc.stdout or b"", exc.stderr or b"", None
    (output / (name + ".stdout")).write_bytes(stdout)
    (output / (name + ".stderr")).write_bytes(stderr)
    receipt = {"argv": argv, "exit_code": exit_code, "timed_out": timed_out,
               "stdout_sha256": hashlib.sha256(stdout).hexdigest(),
               "stderr_sha256": hashlib.sha256(stderr).hexdigest()}
    report = {"name": name, "command": shlex.join(argv), "argv": argv,
              "timeout_seconds": timeout, "elapsed_seconds": time.monotonic() - started,
              "passed": exit_code == 0 and not timed_out, "receipt": receipt,
              "stdout_file": str(output / (name + ".stdout")),
              "stderr_file": str(output / (name + ".stderr")),
              "date": "2026-10-04"}
    reports.append(report)
    print(json.dumps(report))
    print(stdout.decode(errors="replace"), end="")
    print(stderr.decode(errors="replace"), end="")
(output / "runs.json").write_text(json.dumps(reports, indent=2) + "\n")
sys.exit(0 if all(r["passed"] for r in reports) else 1)
