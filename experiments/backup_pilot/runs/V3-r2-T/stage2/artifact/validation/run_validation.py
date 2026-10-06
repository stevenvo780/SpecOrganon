"""Execute a bounded argv and retain the actual streams and receipt."""
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
argv = [sys.executable, str(ROOT / "tests" / "test_backup.py")]
started = time.monotonic()
timed_out = False
try:
    process = subprocess.run(argv, cwd=ROOT, capture_output=True, timeout=180)
    stdout, stderr, exit_code = process.stdout, process.stderr, process.returncode
except subprocess.TimeoutExpired as error:
    stdout, stderr, exit_code = error.stdout or b"", error.stderr or b"", None
    timed_out = True
out = ROOT / "validation"
(out / "tests.stdout").write_bytes(stdout)
(out / "tests.stderr").write_bytes(stderr)
data = {"passed": exit_code == 0 and not timed_out, "argv": argv,
        "command": shlex.join(argv), "receipt": {
            "argv": argv, "exit_code": exit_code, "timed_out": timed_out,
            "stdout_sha256": hashlib.sha256(stdout).hexdigest(),
            "stderr_sha256": hashlib.sha256(stderr).hexdigest()}}
# The CLI/module is not available in this shell. Keep canonical receipt bytes
# and ask the actual MCP engine to validate the digest when registering the test.
try:
    from specorganon.engine import local_test_result_sha256
except ModuleNotFoundError:
    canonical = json.dumps(data["receipt"], sort_keys=True, separators=(",", ":"),
                           ensure_ascii=False).encode("utf-8")
    result_sha256 = hashlib.sha256(canonical).hexdigest()
    hash_method = "independent canonical receipt; MCP validation pending"
else:
    result_sha256 = local_test_result_sha256(data)
    hash_method = "specorganon.engine.local_test_result_sha256"
data["receipt"]["result_sha256"] = result_sha256
record = {"data": data, "timeout_seconds": 180, "elapsed_seconds": time.monotonic() - started}
record["hash_method"] = hash_method
(out / "tests.execution.json").write_text(json.dumps(record, indent=2) + "\n")
sys.stdout.buffer.write(stdout)
sys.stderr.buffer.write(stderr)
sys.exit(0 if data["passed"] else 1)
