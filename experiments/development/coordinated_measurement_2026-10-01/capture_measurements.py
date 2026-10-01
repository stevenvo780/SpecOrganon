"""Capture D120 read-only CLI measurements without replacing any prior evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import stat
import subprocess
import time


ROOT = Path(__file__).resolve().parents[3]
DOSSIER = Path(__file__).resolve().parent
D119 = ROOT / "experiments/development/coordinated_runtime_2026-10-01"
PYTHONS = {
    "311": Path("/tmp/specorganon-D107-deps-re8v1j45/venv-311/bin/python"),
    "312": Path("/tmp/specorganon-D107-deps-re8v1j45/venv-312/bin/python"),
}
RUNTIME_ROOTS = {
    "311": Path("/tmp/specorganon-D119-integration311_02-ddvo36cs"),
    "312": Path("/tmp/specorganon-D119-integration312_02-k5980jdd"),
}


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def write(path: Path, value) -> None:
    with path.open("xb") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                indent=2, allow_nan=False).encode() + b"\n")


def sources() -> list[dict]:
    raw = (DOSSIER / "source_freeze.json").read_bytes()
    rows = json.loads(raw)["records"]
    for row in rows:
        live = (ROOT / row["path"]).read_bytes()
        if (len(live), sha(live)) != (row["bytes"], row["sha256"]):
            raise ValueError("D120 frozen source changed")
    return rows + [{"path": (DOSSIER / "source_freeze.json").relative_to(ROOT).as_posix(),
                    "bytes": len(raw), "sha256": sha(raw)}]


def preserve_d119() -> dict:
    """Check all original repo pins and the exact root receipt, with no writes."""
    receipt_raw = (D119 / "receipt.json").read_bytes()
    receipt = json.loads(receipt_raw)
    if sha(receipt_raw) != "cd41baa29e59e1e75d7ed9e46412e0885b13c0b02e72629ea1af1dc55ab28b07":
        raise ValueError("D119 receipt differs from its sealed version")
    records = receipt["records"] + [{
        "path": (D119 / "receipt.json").relative_to(ROOT).as_posix(),
        "kind": "regular", "mode": "100644", "bytes": len(receipt_raw), "sha256": sha(receipt_raw),
    }]
    for row in records:
        path = ROOT / row["path"]
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode):
            raise ValueError("sealed D119 pin is not a regular file")
        raw = path.read_bytes()
        mode = "100755" if info.st_mode & 0o111 else "100644"
        if (len(raw), sha(raw), mode) != (row["bytes"], row["sha256"], row["mode"]):
            raise ValueError("sealed D119 pin changed")
    return {"records_verified": len(records), "receipt_sha256": sha(receipt_raw),
            "all_equal": True, "scope": "all_sealed_repo_pins_before_active_doc_updates"}


def runtime_inventory(path: Path) -> dict:
    """Hash local public fixture inputs, without copying their contents."""
    entries = []
    total = 0
    for child in sorted(path.rglob("*")):
        info = child.lstat()
        name = child.relative_to(path).as_posix()
        if stat.S_ISDIR(info.st_mode):
            entries.append({"path": name, "kind": "directory", "mode": stat.S_IMODE(info.st_mode)})
        elif stat.S_ISREG(info.st_mode):
            if info.st_size > 64 * 1024 * 1024:
                raise ValueError("runtime file exceeds capture bound")
            raw = child.read_bytes()
            total += len(raw)
            if total > 512 * 1024 * 1024:
                raise ValueError("runtime exceeds capture bound")
            entries.append({"path": name, "kind": "regular", "mode": stat.S_IMODE(info.st_mode),
                            "bytes": len(raw), "sha256": sha(raw)})
        else:
            raise ValueError("runtime contains an unsupported special entry")
        if len(entries) > 10000:
            raise ValueError("runtime exceeds entry bound")
    return {"root": str(path), "entries": entries, "regular_bytes": total}


def capture(command: list[str], output: Path, *, timeout: int) -> dict:
    start_wall, start = time.time_ns(), time.monotonic_ns()
    try:
        run = subprocess.run(command, cwd=ROOT, capture_output=True, timeout=timeout, check=False)
        stdout, stderr, code, timed_out = run.stdout, run.stderr, run.returncode, False
    except subprocess.TimeoutExpired as exc:
        stdout, stderr, code, timed_out = exc.stdout or b"", exc.stderr or b"", 124, True
    end, end_wall = time.monotonic_ns(), time.time_ns()
    output.with_suffix(".stdout").write_bytes(stdout)
    output.with_suffix(".stderr").write_bytes(stderr)
    return {"argv": command, "exit_code": code, "timed_out": timed_out,
            "capture_started_wall_ns": start_wall, "capture_ended_wall_ns": end_wall,
            "capture_duration_seconds": (end - start) / 1e9,
            "time_scope": "measurement_command_only_not_original_run_W",
            "stdout_bytes": len(stdout), "stdout_sha256": sha(stdout),
            "stderr_bytes": len(stderr), "stderr_sha256": sha(stderr)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", required=True)
    args = parser.parse_args(argv)
    if not args.name.isalnum():
        raise ValueError("capture name must be alphanumeric")
    output = DOSSIER / "checks" / args.name
    output.mkdir(parents=True, exist_ok=False)
    head_before = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip()
    sources_before = sources()
    write(output / "sources_before.json", sources_before)
    before = preserve_d119()
    write(output / "D119_before.json", before)
    commands, measurements = [], []
    for key, python in PYTHONS.items():
        directory = output / key
        directory.mkdir()
        for arm in ("A", "B", "C"):
            for case in ("D-F", "D-E"):
                label = f"{arm}-{case}"
                runtime = RUNTIME_ROOTS[key] / label / "run"
                old = runtime_inventory(runtime)
                write(directory / f"{label}.input_before.json", old)
                result = capture([str(python), "scripts/measure_coordinated_runtime.py",
                                  "--run-dir", str(runtime)], directory / label, timeout=240)
                commands.append(result | {"interpreter": key, "arm": arm, "case": case})
                new = runtime_inventory(runtime)
                write(directory / f"{label}.input_after.json", new)
                if old != new:
                    raise ValueError("read-only measurement changed its original runtime")
                if result["exit_code"] == 0:
                    raw = (directory / f"{label}.stdout").read_bytes()
                    report = json.loads(raw)
                    write(directory / f"{label}.measurement.json", report)
                    measurements.append({"interpreter": key, "arm": arm, "case": case,
                                         "report": (directory / f"{label}.measurement.json").relative_to(ROOT).as_posix(),
                                         "original_runtime_unchanged": True})
    after = preserve_d119()
    write(output / "D119_after.json", after)
    sources_after = sources()
    write(output / "sources_after.json", sources_after)
    head_after = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip()
    if sources_before != sources_after or head_before != head_after:
        raise ValueError("source freeze or HEAD changed during measurement capture")
    report = {"schema": 1, "classification": "local_measurement_reconciliation_not_R1",
              "head": head_after, "head_before": head_before, "sources_unchanged": True,
              "commands": commands, "measurements": measurements,
              "D119_unchanged": before == after,
              "all_exit_zero": all(row["exit_code"] == 0 for row in commands),
              "formal_cells_executed": 0, "model_requests_sent": 0,
              "tools_executed": 0, "external_spending_authorized": False}
    write(output / "report.json", report)
    return 0 if report["all_exit_zero"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
