"""Archive only fresh D105 public probe artifacts; verify each stored member."""

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
    target.parent.mkdir(parents=True, exist_ok=True)
    raw = source.read_bytes()
    with target.open("xb") as stream:
        stream.write(raw)
    assert target.read_bytes() == raw


def archive(source: Path, destination: Path) -> dict:
    files = []
    for path in sorted(source.rglob("*")):
        assert not path.is_symlink(), path
        if path.is_file():
            files.append({"path": str(path.relative_to(source)), **pin(path.read_bytes())})
        else:
            assert path.is_dir(), path
    with tarfile.open(destination, "x:gz") as output:
        for row in files:
            output.add(source / row["path"], arcname=row["path"], recursive=False)
    with tarfile.open(destination, "r:gz") as stored:
        members = stored.getmembers()
        assert len(members) == len(files)
        for member, row in zip(members, files, strict=True):
            assert member.isfile() and member.name == row["path"]
            raw = stored.extractfile(member).read()
            assert pin(raw) == {key: row[key] for key in ("bytes", "sha256")}
    return {"source_directory": str(source), "archive": destination.name,
            "archive_pin": pin(destination.read_bytes()), "regular_files": len(files),
            "symlinks": 0, "all_reopened_bytes_match": True, "files": files}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo", type=Path)
    parser.add_argument("runtime", type=Path)
    parser.add_argument("env", choices=["311", "312"])
    parser.add_argument("--freeze", choices=("source_freeze.json", "source_freeze_amendment.json"),
                        default="source_freeze.json")
    args = parser.parse_args()
    repo, runtime = args.repo.resolve(strict=True), args.runtime.resolve(strict=True)
    dossier = repo / "experiments/development/citibike_fraction_lineage_2026-09-30"
    frozen = json.loads((dossier / args.freeze).read_text())
    assert runtime == Path(frozen["runtime"]) and not runtime.is_relative_to(repo)
    source = runtime / args.env
    prefix = "installed" if args.freeze == "source_freeze.json" else "repaired"
    record = archive(source, dossier / f"{prefix}_{args.env}.tar.gz")
    copy(source / "report.json", dossier / f"{prefix}_{args.env}.json")
    for suffix in ("stdout.log", "stderr.log", "execution.json"):
        directory = "executions" if prefix == "installed" else "executions_repaired"
        copy(runtime / f"{args.env}.{suffix}", dossier / directory / f"{args.env}.{suffix}")
    archive_record = f"archive_{args.env}.json" if prefix == "installed" else f"archive_repaired_{args.env}.json"
    with (dossier / archive_record).open("x") as stream:
        json.dump(record, stream, indent=2, sort_keys=True)
        stream.write("\n")
    print(json.dumps({"env": args.env, "regular_files": len(record["files"]),
                      "archive": record["archive"], "byte_exact": True}))


if __name__ == "__main__":
    main()
