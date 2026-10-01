"""Capture bounded D120 gates with exact source checks before and after."""

from __future__ import annotations

import argparse
import subprocess
from capture_measurements import DOSSIER, PYTHONS, ROOT, capture, preserve_d119, sources, write


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", required=True)
    parser.add_argument("--python", choices=PYTHONS, required=True)
    args = parser.parse_args(argv)
    if not args.name.isalnum():
        raise ValueError("capture name must be alphanumeric")
    output = DOSSIER / "checks" / args.name
    output.mkdir(parents=True, exist_ok=False)
    head_before = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip()
    before, old = sources(), preserve_d119()
    write(output / "sources_before.json", before)
    write(output / "D119_before.json", old)
    python = str(PYTHONS[args.python])
    affected = ["scripts/measure_coordinated_runtime.py", "tests/test_measure_coordinated_runtime.py"]
    helpers = [str(DOSSIER.relative_to(ROOT) / name) for name in
               ("capture_measurements.py", "capture_checks.py", "seal_evidence.py")]
    commands = [
        [python, "-B", "-m", "pytest", "-q", "-p", "no:cacheprovider", affected[1]],
        ["ruff", "check", *affected, *helpers],
        [python, "-B", "-c", "import pathlib,sys;[compile(pathlib.Path(p).read_bytes(),p,'exec') for p in sys.argv[1:]];print('syntax OK')", *affected, *helpers],
        ["git", "diff", "--check"],
    ]
    results = [capture(command, output / str(index), timeout=300)
               for index, command in enumerate(commands, start=1)]
    after, new = sources(), preserve_d119()
    write(output / "sources_after.json", after)
    write(output / "D119_after.json", new)
    head_after = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip()
    if head_before != head_after:
        raise ValueError("HEAD changed during gate capture")
    report = {"schema": 1, "interpreter": python, "commands": results,
              "head": head_after, "head_before": head_before,
              "sources_unchanged": before == after, "D119_unchanged": old == new,
              "all_exit_zero": all(row["exit_code"] == 0 for row in results),
              "formal_cells_executed": 0, "model_requests_sent": 0, "tools_executed": 0}
    write(output / "report.json", report)
    return 0 if report["all_exit_zero"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
