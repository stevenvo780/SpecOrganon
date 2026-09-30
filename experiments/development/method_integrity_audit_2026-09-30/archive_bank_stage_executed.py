"""Archive only fresh D104 probe directories and original streams, no credentials."""

from __future__ import annotations

import argparse
import hashlib
import json
import tarfile
from pathlib import Path


def pin(raw: bytes) -> dict:
    return {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def copy(source: Path, target: Path) -> None:
    assert source.is_file() and not source.is_symlink(), source
    raw = source.read_bytes()
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("xb") as stream:
        stream.write(raw)
    assert target.read_bytes() == raw


def archive(source: Path, target: Path) -> dict:
    files = []
    for path in sorted(source.rglob("*")):
        assert not path.is_symlink(), path
        if path.is_file():
            files.append({"path": str(path.relative_to(source)), **pin(path.read_bytes())})
        else:
            assert path.is_dir(), path
    with tarfile.open(target, "x:gz") as output:
        for row in files:
            output.add(source / row["path"], arcname=row["path"], recursive=False)
    with tarfile.open(target, "r:gz") as stored:
        members = stored.getmembers()
        assert len(members) == len(files)
        for member, row in zip(members, files, strict=True):
            assert member.isfile() and member.name == row["path"]
            raw = stored.extractfile(member).read()
            assert pin(raw) == {key: row[key] for key in ("bytes", "sha256")}
    return {"source_directory": str(source), "archive": target.name,
            "archive_pin": pin(target.read_bytes()), "regular_files": len(files),
            "symlinks": 0, "files": files, "all_reopened_member_bytes_match": True}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo", type=Path)
    parser.add_argument("runtime", type=Path)
    parser.add_argument("stage", choices=["banks", "programs"])
    args = parser.parse_args()
    repo, runtime = args.repo.resolve(strict=True), args.runtime.resolve(strict=True)
    dossier = repo / "experiments/development/method_integrity_audit_2026-09-30"
    frozen = json.loads((dossier / "source_freeze.json").read_text())
    assert runtime == Path(frozen["runtime"]) and not runtime.is_relative_to(repo)
    records = {}
    jobs = ["311", "312", "lineage"] if args.stage == "banks" else ["programs"]
    for job in jobs:
        for suffix in ("stdout.log", "stderr.log", "execution.json"):
            copy(runtime / f"{job}.{suffix}", dossier / "executions" / f"{job}.{suffix}")
    if args.stage == "banks":
        copy(runtime / "lineage.json", dossier / "lineage.json")
        for env in ("311", "312"):
            source = runtime / f"bank_{env}"
            records[env] = archive(source, dossier / f"bank_{env}.tar.gz")
            copy(source / "results.json", dossier / f"bank_{env}.json")
    else:
        source = runtime / "programs"
        records["programs"] = archive(source, dossier / "programs.tar.gz")
        copy(source / "results.json", dossier / "programs.json")
    with (dossier / f"archives_{args.stage}.json").open("x") as stream:
        json.dump(records, stream, indent=2, sort_keys=True)
        stream.write("\n")
    print(json.dumps({"stage": args.stage, "archives": len(records),
                      "files": sum(row["regular_files"] for row in records.values()),
                      "byte_exact": True}))


if __name__ == "__main__":
    main()
