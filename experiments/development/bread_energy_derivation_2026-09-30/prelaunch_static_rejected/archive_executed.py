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
    require(source.is_dir() and not source.is_symlink(), "missing regular external probe directory")
    execution = json.loads(regular(runtime / (args.env + ".execution.json")))
    require(execution["freeze_pin"] == pin(freeze_raw), "execution belongs to a different freeze")
    require(execution.get("probe_report", {}).get("sha256") == pin(regular(source / "report.json"))["sha256"], "report differs from terminal execution receipt")
    destinations = [dossier / ("energy_" + args.env + ".tar.gz"),
                    dossier / ("energy_" + args.env + ".json"), dossier / ("archive_" + args.env + ".json")]
    for suffix in ("stdout.log", "stderr.log", "execution.json", "started.json"):
        destinations.append(dossier / "executions" / (args.env + "." + suffix))
    require(not any(path.exists() for path in destinations), "archive output already exists; no overwrite")
    record = archive(source, destinations[0])
    record.update(schema=1, study_id="D108", env=args.env, freeze_pin=pin(freeze_raw),
                  archived_at_utc=datetime.now(timezone.utc).isoformat(), passed_execution=execution["exit_code"] == 0)
    record["report_copy"] = exclusive_copy(source / "report.json", destinations[1])
    record["execution_copies"] = []
    for suffix in ("stdout.log", "stderr.log", "execution.json", "started.json"):
        record["execution_copies"].append(exclusive_copy(runtime / (args.env + "." + suffix),
                                                         dossier / "executions" / (args.env + "." + suffix)))
    with destinations[2].open("x", encoding="utf-8") as stream:
        json.dump(record, stream, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"env": args.env, "regular_files": record["regular_files"], "archive": record["archive"],
                      "all_reopened_bytes_match": True, "passed_execution": record["passed_execution"]}))


if __name__ == "__main__":
    main()
