"""Archive fresh D108 public artifacts exclusively, verifying reopened tar bytes."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import stat
import subprocess
import tarfile

DOSSIER = "experiments/development/bread_energy_derivation_2026-09-30"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def pin(raw):
    return {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def regular(path):
    require(stat.S_ISREG(path.lstat().st_mode), "only regular public artifacts allowed: " + str(path))
    return path.read_bytes()


def exclusive_copy(source, destination):
    raw = regular(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("xb") as stream:
        stream.write(raw)
    require(regular(destination) == raw, "archived public copy differs")
    return {"path": str(destination), **pin(raw)}


def archive(source, destination):
    rows = []
    with destination.open("xb") as fileobj, tarfile.open(fileobj=fileobj, mode="w:gz") as stored:
        for path in sorted(source.rglob("*")):
            require(not path.is_symlink(), "artifact symlink is forbidden")
            if path.is_dir():
                continue
            raw = regular(path)
            name = str(path.relative_to(source))
            require(not Path(name).is_absolute() and ".." not in Path(name).parts, "unsafe archive member name")
            row = {"path": name, **pin(raw)}
            rows.append(row)
            member = tarfile.TarInfo(name)
            member.size = len(raw)
            member.mode = 0o600
            stored.addfile(member, io.BytesIO(raw))
    with tarfile.open(destination, mode="r:gz") as reopened:
        members = reopened.getmembers()
        require(len(members) == len(rows), "archive member count differs")
        for member, row in zip(members, rows, strict=True):
            require(member.isfile() and member.name == row["path"], "archive member kind/name differs")
            raw = reopened.extractfile(member).read()
            require(pin(raw) == {k: row[k] for k in ("bytes", "sha256")}, "reopened tar member bytes differ")
    # Verify the observed source has not changed while materializing the tar.
    for row in rows:
        require(pin(regular(source / row["path"])) == {k: row[k] for k in ("bytes", "sha256")}, "source artifact changed during archive")
    return {"source_directory": str(source), "archive": destination.name, "archive_pin": pin(regular(destination)),
            "regular_files": len(rows), "symlinks": 0, "all_reopened_bytes_match": True, "files": rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo", type=Path)
    parser.add_argument("runtime", type=Path)
    parser.add_argument("env", choices=("311", "312"))
    args = parser.parse_args()
    repo = args.repo.resolve(strict=True)
    dossier = repo / DOSSIER
    freeze_raw = subprocess.check_output(["git", "--no-optional-locks", "show", "HEAD:" + DOSSIER + "/source_freeze.json"],
                                        cwd=repo, env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"})
    require(regular(dossier / "source_freeze.json") == freeze_raw, "archive freeze differs from committed HEAD")
    frozen = json.loads(freeze_raw)
    own_name = str(Path(__file__).resolve(strict=True).relative_to(repo))
    require(own_name in frozen["files"] and pin(regular(Path(__file__))) ==
            {k: frozen["files"][own_name][k] for k in ("bytes", "sha256")}, "archiver source is not frozen")
    runtime = args.runtime.resolve(strict=True)
    require(runtime == Path(frozen["runtime"]).resolve(strict=True) and not runtime.is_relative_to(repo), "wrong external runtime")
    source = runtime / args.env
    execution = json.loads(regular(runtime / (args.env + ".execution.json")))
    require(execution["freeze_pin"] == pin(freeze_raw), "execution belongs to a different freeze")
    passed = (execution.get("exit_code") == 0 and "error" not in execution
              and "report_error" not in execution and execution.get("timed_out") is False
              and execution.get("frozen_inputs_unchanged_after") is True
              and execution.get("probe_report_passed") is True)
    require(not source.is_symlink() and (not source.exists() or source.is_dir()), "unsafe external probe directory")
    require(not passed or source.is_dir(), "passed execution lacks probe directory")
    report_path = source / "report.json"
    has_report = report_path.exists()
    require(not passed or has_report, "passed execution lacks report")
    if has_report:
        require(execution.get("probe_report", {}).get("sha256") == pin(regular(report_path))["sha256"], "report differs from terminal execution receipt")
    destinations = [dossier / ("energy_" + args.env + ".tar.gz"),
                    dossier / ("energy_" + args.env + ".json"), dossier / ("archive_" + args.env + ".json")]
    for suffix in ("stdout.log", "stderr.log", "execution.json", "started.json"):
        destinations.append(dossier / "executions" / (args.env + "." + suffix))
    require(not any(path.exists() for path in destinations), "archive output already exists; no overwrite")
    record = archive(source, destinations[0])
    record.update(schema=1, study_id="D108", env=args.env, freeze_pin=pin(freeze_raw),
                  archived_at_utc=datetime.now(timezone.utc).isoformat(), passed_execution=passed,
                  probe_directory_present=source.exists(), report_present=has_report)
    if has_report:
        record["report_copy"] = exclusive_copy(report_path, destinations[1])
    record["execution_copies"] = []
    record["missing_execution_streams"] = []
    for suffix in ("stdout.log", "stderr.log", "execution.json", "started.json"):
        source_stream = runtime / (args.env + "." + suffix)
        if source_stream.exists():
            record["execution_copies"].append(exclusive_copy(source_stream,
                                                            dossier / "executions" / (args.env + "." + suffix)))
        else:
            record["missing_execution_streams"].append(suffix)
    require(not passed or not record["missing_execution_streams"], "passed execution has missing terminal streams")
    with destinations[2].open("x", encoding="utf-8") as stream:
        json.dump(record, stream, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"env": args.env, "regular_files": record["regular_files"], "archive": record["archive"],
                      "all_reopened_bytes_match": True, "passed_execution": record["passed_execution"]}))


if __name__ == "__main__":
    main()
