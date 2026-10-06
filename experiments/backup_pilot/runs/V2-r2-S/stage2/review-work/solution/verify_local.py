"""Ejecutar verificaciones propias y conservar comandos, códigos y salidas."""

from __future__ import annotations

import hashlib
from pathlib import Path
import shlex
import subprocess
import sys


SOLUTION = Path(__file__).resolve().parent
ROOT = SOLUTION.parent
EVIDENCE = SOLUTION / "evidence"


def main() -> int:
    EVIDENCE.mkdir(exist_ok=True)
    (EVIDENCE / "environment.log").write_text(
        f"cwd: {ROOT}\nexecutable: {sys.executable}\nPython: {sys.version}\n",
        encoding="utf-8",
    )
    expected = {}
    for line in (EVIDENCE / "contract-before.sha256").read_text(encoding="ascii").splitlines():
        digest, name = line.split(maxsplit=1)
        expected[name] = digest
    checks = [
        ("compile.log", [sys.executable, "-m", "py_compile", "solution/backup.py",
                         "solution/tests/test_backup.py", "solution/examples/v2.py",
                         "solution/verify_local.py"]),
        ("tests.log", [sys.executable, "-m", "unittest", "discover", "-s", "solution/tests", "-v"]),
        ("example-v2.log", [sys.executable, "solution/examples/v2.py"]),
    ]
    failed = False
    for name, command in checks:
        completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=180)
        (EVIDENCE / name).write_text(
            f"$ {shlex.join(command)}\ncwd: {ROOT}\nexit_code: {completed.returncode}\n"
            f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}", encoding="utf-8",
        )
        print(f"{name}: exit_code={completed.returncode}", flush=True)
        if completed.returncode:
            failed = True
            print(completed.stdout + completed.stderr, flush=True)
    preserved = True
    lines = ["Comprobación de hashes registrados antes de editar la solución:"]
    for name, wanted in expected.items():
        actual = hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
        unchanged = actual == wanted
        preserved &= unchanged
        lines.append(f"{name}: {'OK' if unchanged else 'CHANGED'} sha256={actual}")
    (EVIDENCE / "contract-check.log").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"CONTRACT.md/AGENTS.md preserved: {preserved}", flush=True)
    return int(failed or not preserved)


if __name__ == "__main__":
    sys.exit(main())
