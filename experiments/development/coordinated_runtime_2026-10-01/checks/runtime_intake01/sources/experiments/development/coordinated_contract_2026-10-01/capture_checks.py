"""Capture bounded D118 checks and exact source bytes; never run providers."""

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
import prepare_coordinated_development as preparer  # noqa: E402

PUBLIC = DOSSIER / "public_contract"
AFFECTED = ["scripts/plan_coordinated_development.py", "scripts/prepare_coordinated_development.py",
            "scripts/development_delivery_contract.py", "tests/test_plan_coordinated_development.py",
            "tests/test_prepare_coordinated_development.py", "tests/test_development_delivery_contract.py"]


def source_records(tests: list[str]) -> list[dict]:
    paths = {Path(row["path"]) for row in preparer._source_records(PUBLIC)}
    paths.update(ROOT / path for path in [*AFFECTED, *tests, "GOAL.md", "docs/protocolo_experimental.md"])
    paths.update(path for path in DOSSIER.iterdir() if path.is_file()
                 and (path.suffix == ".py" or path.name in {"plan.md", "baseline_pins.json", "source_freeze.json",
                                                          "fixture_configuration.json"}))
    return [{"path": str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path),
             "bytes": len(raw := preparer._read(path)), "sha256": hashlib.sha256(raw).hexdigest()}
            for path in sorted(paths)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", required=True)
    parser.add_argument("--python", required=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--tests", nargs="+")
    group.add_argument("--integration", action="store_true")
    args = parser.parse_args()
    target = DOSSIER / "checks" / args.name
    target.mkdir(parents=True, exist_ok=False)
    before = source_records(args.tests or [])
    for row in before:
        source = ROOT / row["path"]
        if source.is_relative_to(ROOT):
            destination = target / "sources" / row["path"]
            destination.parent.mkdir(parents=True, exist_ok=True)
            raw = preparer._read(source)
            if hashlib.sha256(raw).hexdigest() != row["sha256"]:
                raise ValueError("source changed before snapshot")
            destination.write_bytes(raw)
    metadata = subprocess.check_output([args.python, "-I", "-B", "-c",
        "import json,sys;print(json.dumps({'version':sys.version,'executable':sys.executable}))"], cwd=ROOT)
    (target / "python_metadata.json").write_bytes(metadata)
    runtime = Path(tempfile.mkdtemp(prefix="specorganon-D118-" + args.name + "-"))
    helpers = [str(path.relative_to(ROOT)) for path in DOSSIER.glob("*.py")]
    first = ([args.python, "-I", "-B", str(DOSSIER / "integration_checks.py"),
              "--destination", str(runtime), "--source-freeze", str(DOSSIER / "source_freeze.json")]
             if args.integration else [args.python, "-B", "-m", "pytest", "-q", "-p", "no:cacheprovider",
                                       *args.tests, "--basetemp", str(runtime / "cases")])
    commands = [first, ["ruff", "check", *AFFECTED, *helpers],
                [args.python, "-I", "-B", "-c",
                 "import pathlib,sys;[compile(pathlib.Path(p).read_bytes(),p,'exec') for p in sys.argv[1:]];print('syntax OK')",
                 *AFFECTED, *helpers], ["git", "diff", "--check", "--", *AFFECTED, *helpers]]
    results = []
    for number, argv in enumerate(commands, 1):
        started = time.monotonic()
        with (target / f"{number}.stdout").open("xb") as stdout, (target / f"{number}.stderr").open("xb") as stderr:
            process = subprocess.run(argv, cwd=ROOT, stdout=stdout, stderr=stderr, timeout=1200, check=False)
        result = {"argv": argv, "exit_code": process.returncode, "wall_seconds": time.monotonic() - started,
                  "stdout": f"{number}.stdout", "stderr": f"{number}.stderr"}
        results.append(result)
        (target / f"{number}.json").write_text(json.dumps(result, indent=2) + "\n")
    after = source_records(args.tests or [])
    report = {"schema": 1, "classification": "offline_structure_and_preparation_not_model_quality",
              "head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip(),
              "interpreter": json.loads(metadata), "runtime_root": str(runtime), "sources_before": before,
              "sources_after": after, "source_unchanged": before == after, "commands": results,
              "all_exit_zero": all(row["exit_code"] == 0 for row in results), "formal_cells_executed": 0}
    (target / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({key: report[key] for key in ("runtime_root", "source_unchanged", "all_exit_zero")}))
    return 0 if report["source_unchanged"] and report["all_exit_zero"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
