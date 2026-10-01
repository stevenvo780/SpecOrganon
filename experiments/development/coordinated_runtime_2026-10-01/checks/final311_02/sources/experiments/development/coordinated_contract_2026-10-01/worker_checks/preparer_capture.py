"""Capture one offline preparer gate with exact pre-test source snapshots."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "scripts"))
import prepare_coordinated_development as preparer  # noqa: E402


def canonical(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=False,
                       allow_nan=False, indent=2) + "\n").encode()


def write(path, raw):
    with path.open("xb") as stream:
        stream.write(raw)


def capture(python: str, attempt: Path, selection: list[str]) -> dict:
    attempt.mkdir(mode=0o700)
    sources = attempt / "sources"
    sources.mkdir(mode=0o700)
    contract_dir = ROOT / "experiments/development/coordinated_contract_2026-10-01/public_contract"
    before = preparer._source_records(contract_dir)
    extra = [ROOT / "tests/test_prepare_coordinated_development.py", Path(__file__).resolve()]
    for source in extra:
        raw = source.read_bytes()
        before.append({"path": str(source), "bytes": len(raw),
                       "sha256": hashlib.sha256(raw).hexdigest()})
    for index, row in enumerate(before):
        raw = preparer._read(Path(row["path"]))
        if hashlib.sha256(raw).hexdigest() != row["sha256"]:
            raise ValueError("source changed before snapshot")
        # Capture code and public contracts; original input data remains pinned in place.
        if Path(row["path"]).suffix == ".py" or Path(row["path"]).parent == contract_dir:
            write(sources / f"{index:03d}-{Path(row['path']).name}", raw)
    write(attempt / "source_before.json", canonical(before))
    runtime = Path(tempfile.mkdtemp(prefix="specorganon-D118-preparer-"))
    os.chmod(runtime, 0o700)
    commands = [
        [python, "-B", "-m", "pytest", "-q", "tests/test_prepare_coordinated_development.py",
         "--basetemp", str(runtime / "pytest"), *selection],
        ["ruff", "check", "scripts/prepare_coordinated_development.py",
         "tests/test_prepare_coordinated_development.py", str(Path(__file__).resolve())],
        [python, "-I", "-B", "-c",
         "import pathlib; [compile(pathlib.Path(p).read_bytes(), p, 'exec') for p in "
         "['scripts/prepare_coordinated_development.py', 'tests/test_prepare_coordinated_development.py']]"],
    ]
    records = []
    for index, command in enumerate(commands):
        start = time.monotonic()
        with (attempt / f"{index:02d}.stdout").open("xb") as stdout, \
                (attempt / f"{index:02d}.stderr").open("xb") as stderr:
            process = subprocess.run(command, cwd=ROOT, stdout=stdout, stderr=stderr,
                                     check=False)
        record = {"command": command, "exit_code": process.returncode,
                  "duration_seconds": time.monotonic() - start}
        records.append(record)
        write(attempt / f"{index:02d}.json", canonical(record))
    after = []
    for row in before:
        raw = preparer._read(Path(row["path"]))
        after.append({"path": row["path"], "bytes": len(raw),
                      "sha256": hashlib.sha256(raw).hexdigest()})
    write(attempt / "source_after.json", canonical(after))
    result = {"schema": 1, "scope": "offline_preparer_gate", "runtime_root": str(runtime),
              "records": records, "sources_unchanged": before == after,
              "passed": before == after and all(record["exit_code"] == 0 for record in records)}
    write(attempt / "receipt.json", canonical(result))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--python", required=True)
    parser.add_argument("--attempt", required=True, type=Path)
    parser.add_argument("selection", nargs="*")
    args = parser.parse_args()
    result = capture(args.python, args.attempt, args.selection)
    print(json.dumps(result, sort_keys=True))
    raise SystemExit(0 if result["passed"] else 1)
