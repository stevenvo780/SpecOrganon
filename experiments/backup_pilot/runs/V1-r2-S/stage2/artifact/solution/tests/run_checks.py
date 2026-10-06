"""Run local verification and persist exact commands, outputs and exit codes."""

from datetime import datetime, timezone
import hashlib
from pathlib import Path
import shlex
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "solution" / "evidence"
CONTRACT_HASH = "8adcc50d4a0b8411195837403c0f8cbc5327e1e3e8da3ac943ec4d708a0019c1"


def main():
    EVIDENCE.mkdir(exist_ok=True)
    commands = [
        ("tests-max-bytes.txt", [sys.executable, "-m", "unittest", "discover",
                                 "-s", "solution/tests", "-p", "test_*.py", "-v"]),
        ("example-max-bytes.txt", [sys.executable, "solution/tests/example.py"]),
        ("compile-max-bytes.txt", [sys.executable, "-m", "py_compile",
                                   "solution/backup.py", "solution/tests/test_backup.py",
                                   "solution/tests/example.py", "solution/tests/run_checks.py"]),
    ]
    failed = False
    for filename, command in commands:
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=180)
        report = (f"UTC: {datetime.now(timezone.utc).isoformat()}\n"
                  f"CWD: {ROOT}\nPYTHON: {sys.version}\n"
                  f"COMMAND: {shlex.join(command)}\nEXIT: {result.returncode}\n"
                  f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}")
        (EVIDENCE / filename).write_text(report, encoding="utf-8")
        print(report, flush=True)
        failed |= result.returncode != 0
    actual = hashlib.sha256((ROOT / "CONTRACT.md").read_bytes()).hexdigest()
    report = f"CONTRACT SHA256: {actual}\nUNCHANGED: {actual == CONTRACT_HASH}\n"
    (EVIDENCE / "contract-max-bytes.txt").write_text(report, encoding="utf-8")
    print(report, flush=True)
    return int(failed or actual != CONTRACT_HASH)


if __name__ == "__main__":
    sys.exit(main())
