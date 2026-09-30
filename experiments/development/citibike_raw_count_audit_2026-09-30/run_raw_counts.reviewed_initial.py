"""Reproduce the pinned historical Citi Bike report from a sealed raw sample.

The original analyzer is executed without edits from verified bytes supplied
through stdin. Its repeated reads resolve a sealed Linux memfd. This verifies
reproducibility on archived rows, not field truth, access or intervention effects.
"""

from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import time


ANALYZER = "cases/citibike/analyze_sample_status.py"
PUBLISHED = "experiments/development/citibike_sample_status_2026-09-27.json"
MAX_BYTES = 12 * 1024 * 1024


def pin(raw: bytes) -> dict:
    return {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def read_once(path: Path) -> bytes:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_BYTES:
            raise ValueError(f"not a bounded regular file: {path}")
        data = bytearray()
        while len(data) <= MAX_BYTES:
            chunk = os.read(fd, min(65536, MAX_BYTES + 1 - len(data)))
            if not chunk:
                break
            data.extend(chunk)
        if len(data) > MAX_BYTES:
            raise ValueError("input exceeds bound")
        return bytes(data)
    finally:
        os.close(fd)


def verify(repo: Path, files: dict) -> None:
    for name, expected in files.items():
        if pin(read_once(repo / name)) != expected:
            raise ValueError(f"frozen file changed: {name}")


def verify_environment(manifest: dict) -> None:
    venv = Path(manifest["venv"]).resolve(strict=True)
    for name, expected in manifest["files"].items():
        path = venv / name
        if not path.resolve(strict=True).is_relative_to(venv) or path.is_symlink():
            raise ValueError(f"unexpected environment path: {name}")
        raw = path.read_bytes()
        if pin(raw) != expected:
            raise ValueError(f"dependency file changed: {name}")


def write(path: Path, raw: bytes) -> None:
    with path.open("xb") as stream:
        stream.write(raw)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo", type=Path)
    args = parser.parse_args()
    repo = args.repo.resolve(strict=True)
    dossier = repo / "experiments/development/citibike_raw_count_audit_2026-09-30"
    freeze_raw = read_once(dossier / "source_freeze.json")
    frozen = json.loads(freeze_raw)
    plan = json.loads(read_once(dossier / "plan.json"))
    verify(repo, frozen["files"])
    manifest = json.loads(read_once(dossier / "environment_manifest.json"))
    verify_environment(manifest)
    runtime = Path(plan["runtime"]).resolve(strict=True)
    if runtime.is_relative_to(repo):
        raise ValueError("runtime must be external")
    marker = runtime / "raw_analysis.started.json"
    if marker.exists() or (dossier / "execution.json").exists():
        raise ValueError("analysis already started; no retry or overwrite")
    original = read_once(repo / ANALYZER)
    expected = json.loads(read_once(repo / PUBLISHED))
    raw = read_once(Path(plan["raw_source"]["path"]))
    raw_pin = pin(raw)
    blob_hash = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
    if raw_pin != {key: plan["raw_source"][key] for key in ("bytes", "sha256")}:
        raise ValueError("raw dataset differs from prospective pin")
    if blob_hash != plan["raw_source"]["git_blob_sha1"]:
        raise ValueError("raw Git blob hash differs")
    fd = os.memfd_create("D106-public-citibike", os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING)
    try:
        with os.fdopen(os.dup(fd), "wb", closefd=True) as stream:
            stream.write(raw)
        required_seals = (fcntl.F_SEAL_WRITE | fcntl.F_SEAL_GROW |
                          fcntl.F_SEAL_SHRINK | fcntl.F_SEAL_SEAL)
        fcntl.fcntl(fd, fcntl.F_ADD_SEALS, required_seals)
        seals = fcntl.fcntl(fd, fcntl.F_GET_SEALS)
        if seals & required_seals != required_seals:
            raise ValueError("raw sample memfd not sealed")
        if pin(os.pread(fd, len(raw) + 1, 0)) != raw_pin:
            raise ValueError("sealed descriptor bytes differ")
        child = (
            "import sys,importlib.metadata as md,zoneinfo; sys.dont_write_bytecode=True; "
            "assert sys.version_info[:2]==(3,11); "
            "assert md.version('pyarrow')=='21.0.0'; "
            "assert md.version('tzdata')=='2026.4'; "
            "zoneinfo.reset_tzpath(()); import pyarrow as pa; "
            "pa.set_cpu_count(2); pa.set_io_thread_count(2); "
            "raw=sys.stdin.buffer.read(); fd=int(sys.argv[1]); name=sys.argv[2]; "
            "sys.argv=[name,'/proc/self/fd/'+str(fd)]; "
            "exec(compile(raw,name,'exec'),"
            "{'__name__':'__main__','__file__':name,'__package__':None})"
        )
        python = str(Path(manifest["venv"]) / "bin/python")
        argv = [python, "-I", "-c", child, str(fd), str(repo / ANALYZER)]
        record = {
            "schema": 1, "classification": plan["classification"], "argv": argv,
            "freeze_pin": pin(freeze_raw), "input_pin": raw_pin,
            "input_git_blob_sha1": blob_hash, "input_seals": seals,
            "executed_analysis_source_pin": pin(original),
            "source_code_executed_from_verified_stdin": True,
            "all_repeated_dataset_reads_use_same_sealed_bytes": True,
            "started_at_utc": dt.datetime.now(dt.UTC).isoformat(),
            "exit_code": None, "timeout_seconds": 60, "automatic_retry": False,
            "source_truth_authenticated": False, "field_impact_assessed": False,
            "subset_membership_verified_from_rows": False, "Q": None,
        }
        write(marker, (json.dumps(record, indent=2, sort_keys=True) + "\n").encode())
        write(dossier / "analysis_source.executed.py", original)
        began = time.monotonic()
        env = {"PATH": str(Path(python).parent) + ":/usr/bin:/bin", "LANG": "C.UTF-8",
               "LC_ALL": "C.UTF-8", "TZ": "UTC", "TMPDIR": str(runtime)}
        try:
            result = subprocess.run(argv, input=original, cwd=runtime, env=env,
                                    pass_fds=(fd,), capture_output=True, check=False, timeout=60)
            record["exit_code"] = result.returncode
            write(dossier / "analysis.stdout.log", result.stdout)
            write(dossier / "analysis.stderr.log", result.stderr)
            record["stdout_pin"], record["stderr_pin"] = pin(result.stdout), pin(result.stderr)
            if result.returncode:
                raise ValueError("historical analyzer failed; inspect retained streams")
            report = json.loads(result.stdout)
            if report != expected:
                raise ValueError("raw row reproduction differs from published report")
            verify(repo, frozen["files"])
            verify_environment(manifest)
            if pin(read_once(Path(plan["raw_source"]["path"]))) != raw_pin:
                raise ValueError("original raw path changed after analysis")
            record.update(full_report_equal=True, original_sources_unchanged=True,
                          dependency_files_unchanged=True, row_analysis_executed=True,
                          subset_membership_verified_from_rows=True)
            record["counts"] = {"rows": report["rows"], "quality": report["quality"],
                                "snapshot_row_service": report["snapshot_row_service"],
                                "snapshot_count": report["snapshot_count"],
                                "station_id_count": report["station_id_count"]}
            write(dossier / "report.json", result.stdout)
        except Exception as exc:
            record["error"] = f"{type(exc).__name__}: {exc}"
            if isinstance(exc, subprocess.TimeoutExpired):
                write(dossier / "analysis.stdout.log", exc.stdout or b"")
                write(dossier / "analysis.stderr.log", exc.stderr or b"")
        finally:
            record["wall_seconds"] = time.monotonic() - began
            record["finished_at_utc"] = dt.datetime.now(dt.UTC).isoformat()
            write(dossier / "execution.json", (json.dumps(record, indent=2, sort_keys=True) + "\n").encode())
        print(json.dumps({key: record.get(key) for key in
                          ("exit_code", "wall_seconds", "full_report_equal", "error")}))
        return 0 if record.get("full_report_equal") and "error" not in record else 2
    finally:
        os.close(fd)


if __name__ == "__main__":
    raise SystemExit(main())
