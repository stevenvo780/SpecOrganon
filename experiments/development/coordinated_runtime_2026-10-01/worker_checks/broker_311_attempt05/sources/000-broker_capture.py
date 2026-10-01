"""Preserve one offline broker gate's exact sources and process streams."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "scripts"))
import coordinated_prototype_broker as broker  # noqa: E402


def write(path, raw):
    with path.open("xb") as stream:
        stream.write(raw)


def canonical(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--python", required=True)
    parser.add_argument("--attempt", required=True, type=Path)
    parser.add_argument("selection", nargs="*")
    args = parser.parse_args()
    args.attempt.mkdir(mode=0o700)
    sources = args.attempt / "sources"
    sources.mkdir(mode=0o700)
    before = broker._sources()
    before[str(ROOT / "tests/test_coordinated_prototype_broker.py")] = hashlib.sha256(
        (ROOT / "tests/test_coordinated_prototype_broker.py").read_bytes()).hexdigest()
    before[str(Path(__file__).resolve())] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    for number, (name, digest) in enumerate(sorted(before.items())):
        raw = broker._raw(Path(name))
        if hashlib.sha256(raw).hexdigest() != digest:
            raise ValueError("source changed before gate")
        write(sources / f"{number:03d}-{Path(name).name}", raw)
    write(args.attempt / "source_before.json", canonical(before))
    runtime = Path(tempfile.mkdtemp(prefix="specorganon-D119-broker-"))
    runtime.chmod(0o700)
    command = [args.python, "-B", "-m", "pytest", "-q", "tests/test_coordinated_prototype_broker.py",
               "--basetemp", str(runtime / "pytest"), *args.selection]
    start = time.monotonic()
    with (args.attempt / "stdout").open("xb") as out, (args.attempt / "stderr").open("xb") as err:
        result = subprocess.run(command, cwd=ROOT, stdout=out, stderr=err, check=False)
    after = {name: hashlib.sha256(broker._raw(Path(name))).hexdigest() for name in before}
    write(args.attempt / "source_after.json", canonical(after))
    report = {"schema": 1, "scope": "offline_real_sandbox_broker_gate",
              "runtime_root": str(runtime), "command": command, "exit_code": result.returncode,
              "duration_seconds": time.monotonic() - start, "sources_unchanged": before == after,
              "passed": result.returncode == 0 and before == after}
    write(args.attempt / "receipt.json", canonical(report))
    print(json.dumps(report, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
