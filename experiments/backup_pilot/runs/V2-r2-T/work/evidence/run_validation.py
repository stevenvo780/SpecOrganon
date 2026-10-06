"""Run and preserve a measured command receipt, with no ledger writes."""
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent.parent
EVIDENCE = ROOT / "evidence" / "v2"
EVIDENCE.mkdir(parents=True, exist_ok=True)
argv = [sys.executable, str(ROOT / "solution" / "test_backup.py")]
start = time.monotonic()
timed_out = False
try:
    process = subprocess.run(argv, cwd=ROOT, capture_output=True, timeout=120)
    stdout, stderr, code = process.stdout, process.stderr, process.returncode
except subprocess.TimeoutExpired as error:
    stdout, stderr, code = error.stdout or b"", error.stderr or b"", -1
    timed_out = True
(EVIDENCE / "tests.stdout").write_bytes(stdout)
(EVIDENCE / "tests.stderr").write_bytes(stderr)
receipt = {"argv": argv, "exit_code": code, "timed_out": timed_out,
           "stdout_sha256": hashlib.sha256(stdout).hexdigest(),
           "stderr_sha256": hashlib.sha256(stderr).hexdigest()}
data = {"argv": argv, "command": shlex.join(argv),
        "passed": code == 0 and not timed_out, "receipt": receipt,
        "timeout_seconds": 120, "elapsed_seconds": time.monotonic() - start}
# Canonical declared result; the MCP gate independently checks the binding.
declared_result = {key: data[key] for key in ("passed", "command", "argv")}
receipt["result_sha256"] = hashlib.sha256(json.dumps(
    declared_result, sort_keys=True, separators=(",", ":"), ensure_ascii=False
).encode("utf-8")).hexdigest()
(EVIDENCE / "test_receipt.json").write_text(json.dumps(data, indent=2) + "\n")
print(stderr.decode(), end="")
print(json.dumps(data))
sys.exit(code if code >= 0 else 1)
