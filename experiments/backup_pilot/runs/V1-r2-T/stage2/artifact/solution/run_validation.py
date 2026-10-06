"""Run real processes and preserve argv, streams, exit status and timeouts."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, help="New evidence directory")
    args = parser.parse_args()
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    solution = Path(__file__).resolve().parent
    env = dict(os.environ, BACKUP_TEST_LOG=str(output / "commands.jsonl"), PYTHONDONTWRITEBYTECODE="1")
    jobs = [
        ("suite", [sys.executable, "-m", "unittest", "discover", "-s", str(solution), "-p", "test_backup.py", "-v"], 180),
        ("examples", [sys.executable, str(solution / "examples.py")], 30),
    ]
    records = []
    for name, argv, timeout in jobs:
        started = time.monotonic()
        try:
            run = subprocess.run(argv, cwd="/trial", env=env, capture_output=True, timeout=timeout)
            exit_code, stdout, stderr, timed_out = run.returncode, run.stdout, run.stderr, False
        except subprocess.TimeoutExpired as exc:
            exit_code, stdout, stderr, timed_out = None, exc.stdout or b"", exc.stderr or b"", True
        (output / (name + ".stdout")).write_bytes(stdout)
        (output / (name + ".stderr")).write_bytes(stderr)
        receipt = {"argv": argv, "exit_code": exit_code, "timed_out": timed_out,
                   "stdout_sha256": hashlib.sha256(stdout).hexdigest(),
                   "stderr_sha256": hashlib.sha256(stderr).hexdigest()}
        record = {"name": name, "command": shlex.join(argv), "argv": argv,
                  "passed": exit_code == 0 and not timed_out, "receipt": receipt,
                  "timeout_seconds": timeout, "elapsed_seconds": time.monotonic() - started}
        records.append(record)
        print(json.dumps(record))
    data = {"python_version": sys.version, "cwd": "/trial", "runs": records,
            "artifacts_sha256": {name: hashlib.sha256((solution / name).read_bytes()).hexdigest()
                                 for name in ["backup.py", "test_backup.py", "examples.py", "run_validation.py"]}}
    (output / "execution.json").write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return 0 if all(r["passed"] for r in records) else 1


if __name__ == "__main__":
    sys.exit(main())
