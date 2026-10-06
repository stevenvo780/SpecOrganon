"""Run and retain the exact validation commands and their outputs."""

from datetime import datetime, timezone
from pathlib import Path
import shlex
import subprocess
import sys
import time


HERE = Path(__file__).absolute().parent
ROOT = HERE.parent
REPORT = HERE / "verification"


def main():
    REPORT.mkdir(exist_ok=True)
    commands = [
        [sys.executable, "--version"],
        [sys.executable, "-m", "py_compile", "solution/backup.py", "solution/test_backup.py", "solution/examples.py", "solution/run_checks.py"],
        [sys.executable, "-m", "unittest", "discover", "-s", "solution", "-p", "test_backup.py", "-v"],
        [sys.executable, "solution/examples.py"],
    ]
    failed = False
    with (REPORT / "commands.log").open("w", encoding="utf-8") as log:
        log.write(f"UTC: {datetime.now(timezone.utc).isoformat()}\ncwd: {ROOT}\n")
        for command in commands:
            printable = shlex.join(command)
            started = time.monotonic()
            result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=180)
            elapsed = time.monotonic() - started
            log.write(f"\n$ {printable}\nexit={result.returncode}; elapsed={elapsed:.3f}s\n")
            log.write(f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}\n")
            log.flush()
            print(f"exit={result.returncode}; elapsed={elapsed:.3f}s; {printable}", flush=True)
            if result.returncode != 0:
                failed = True
                print(result.stdout + result.stderr, flush=True)
    print(f"Retained log: {REPORT / 'commands.log'}")
    return int(failed)


if __name__ == "__main__":
    sys.exit(main())
