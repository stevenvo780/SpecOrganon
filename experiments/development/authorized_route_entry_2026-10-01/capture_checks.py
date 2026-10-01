"""Capture proportional D123 local gates with source bytes and exact argv."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
SOURCES = ("scripts/authorized_coordinated_runtime.py", "scripts/provider_outcome_accounting.py",
           "tests/test_authorized_coordinated_runtime.py", "tests/test_provider_outcome_accounting.py")


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def capture(argv, output, name, *, timeout=240):
    result = subprocess.run(argv, cwd=ROOT, capture_output=True, timeout=timeout, check=False)
    (output / (name + ".stdout")).write_bytes(result.stdout)
    (output / (name + ".stderr")).write_bytes(result.stderr)
    return {"argv": argv, "exit_code": result.returncode, "stdout_sha256": sha(result.stdout),
            "stderr_sha256": sha(result.stderr)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--test", default="test_authorized_coordinated_runtime.py")
    parser.add_argument("--lint-only", action="store_true")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    saved = args.output / "sources"
    saved.mkdir()
    before = {}
    for name in SOURCES:
        path = ROOT / name
        if path.exists():
            raw = path.read_bytes()
            before[name] = raw
            target = saved / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
    commands = []
    if not args.lint_only:
        commands.append(capture([sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests", "-p", args.test, "-v"],
                                args.output, "tests"))
    commands.append(capture(["/home/dev/.local/bin/ruff", "check", *before], args.output, "ruff"))
    commands.append(capture(["git", "diff", "--check"], args.output, "diff"))
    report = {"python": sys.executable, "version": list(sys.version_info[:3]), "commands": commands,
              "sources": [{"path": name, "bytes": len(raw), "sha256": sha(raw)} for name, raw in before.items()],
              "sources_unchanged": all((ROOT / name).read_bytes() == raw for name, raw in before.items()),
              "all_exit_zero": all(row["exit_code"] == 0 for row in commands),
              "formal_cells_executed": 0, "paid_provider_requests": 0}
    (args.output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"report": str(args.output / "report.json"), "all_exit_zero": report["all_exit_zero"]}))


if __name__ == "__main__":
    main()
