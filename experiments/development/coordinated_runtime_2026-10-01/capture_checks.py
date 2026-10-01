"""Retain exact D119 source bytes, commands and isolated runtime evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time

DOSSIER = Path(__file__).resolve().parent
ROOT = DOSSIER.parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import coordinated_prototype_runtime as runtime  # noqa: E402

AFFECTED = ["scripts/coordinated_prototype_kernel.py", "scripts/coordinated_prototype_broker.py",
            "scripts/managed_coordinated_prototype.py", "scripts/coordinated_prototype_runtime.py",
            "tests/test_coordinated_prototype_kernel.py", "tests/test_coordinated_prototype_broker.py",
            "tests/test_managed_coordinated_prototype.py", "tests/test_coordinated_prototype_runtime.py",
            "tests/coordinated_runtime_fixture.py"]


def source_records(tests, affected=None):
    paths = set(runtime._runtime_sources()) | set(AFFECTED if affected is None else affected)
    paths.update(value.split("::", 1)[0] for value in tests)
    paths.update(row["path"] for row in runtime._publication()["records"])
    paths.update(str(path.relative_to(ROOT)) for path in DOSSIER.iterdir() if path.is_file()
                 and (path.suffix == ".py" or path.name in {"plan.md", "baseline_pins.json", "fixture_configuration.json", "source_freeze.json"}))
    paths.update(["GOAL.md", "docs/protocolo_experimental.md"])
    return [{"path": name, "bytes": len(raw := runtime.preparation._read(ROOT / name)),
             "sha256": hashlib.sha256(raw).hexdigest()} for name in sorted(paths)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", required=True)
    parser.add_argument("--python", required=True)
    parser.add_argument("--scope", nargs="+")
    parser.add_argument("--timeout-seconds", type=int, default=2400)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--tests", nargs="+")
    group.add_argument("--integration", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.timeout_seconds <= 7200:
        parser.error("timeout must be between 1 and 7200 seconds")
    target = DOSSIER / "checks" / args.name
    target.mkdir(parents=True, exist_ok=False)
    affected = args.scope or AFFECTED
    before = source_records(args.tests or [], affected)
    for row in before:
        path = ROOT / row["path"]
        raw = runtime.preparation._read(path)
        assert hashlib.sha256(raw).hexdigest() == row["sha256"]
        destination = target / "sources" / row["path"]
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(raw)
    metadata = subprocess.check_output([args.python, "-I", "-B", "-c",
        "import json,sys;print(json.dumps({'version':sys.version,'executable':sys.executable}))"], cwd=ROOT)
    (target / "python_metadata.json").write_bytes(metadata)
    root = Path(tempfile.mkdtemp(prefix="specorganon-D119-" + args.name + "-"))
    helpers = sorted(str(path.relative_to(ROOT)) for path in DOSSIER.glob("*.py"))
    first = ([args.python, "-I", "-B", str(DOSSIER / "integration_checks.py"), "--destination", str(root)]
             if args.integration else [args.python, "-B", "-m", "pytest", "-q", "-p", "no:cacheprovider",
                                       *args.tests, "--basetemp", str(root / "cases")])
    commands = [first, ["ruff", "check", *affected, *helpers],
                [args.python, "-I", "-B", "-c",
                 "import pathlib,sys;[compile(pathlib.Path(p).read_bytes(),p,'exec') for p in sys.argv[1:]];print('syntax OK')",
                 *affected, *helpers], ["git", "diff", "--check", "--", *affected, *helpers]]
    results = []
    for number, argv in enumerate(commands, 1):
        started = time.monotonic()
        timeout_error = None
        with (target / f"{number}.stdout").open("xb") as stdout, (target / f"{number}.stderr").open("xb") as stderr:
            try:
                process = subprocess.run(argv, cwd=ROOT, stdout=stdout, stderr=stderr,
                                         timeout=args.timeout_seconds, check=False)
                exit_code = process.returncode
            except subprocess.TimeoutExpired as exc:
                exit_code = 124
                timeout_error = str(exc)
                stderr.write(("\nTimeoutExpired: " + timeout_error + "\n").encode())
        row = {"argv": argv, "exit_code": exit_code, "wall_seconds": time.monotonic() - started,
               "timeout_seconds": args.timeout_seconds, "timeout_error": timeout_error,
               "stdout": f"{number}.stdout", "stderr": f"{number}.stderr"}
        results.append(row)
        (target / f"{number}.json").write_text(json.dumps(row, indent=2) + "\n")
    after = source_records(args.tests or [], affected)
    result = {"schema": 1, "classification": "synthetic_persistent_original_mode_runtime_not_model_quality",
              "head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip(),
              "interpreter": json.loads(metadata), "runtime_root": str(root), "sources_before": before,
              "command_timeout_seconds": args.timeout_seconds,
              "sources_after": after, "source_unchanged": before == after, "commands": results,
              "all_exit_zero": all(row["exit_code"] == 0 for row in results), "formal_cells_executed": 0}
    (target / "report.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({key: result[key] for key in ("runtime_root", "source_unchanged", "all_exit_zero")}))
    return 0 if result["source_unchanged"] and result["all_exit_zero"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
