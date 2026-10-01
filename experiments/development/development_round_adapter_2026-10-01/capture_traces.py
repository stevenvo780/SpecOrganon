"""Archive regular files of six completed public integration fixtures, byte for byte.

Identical bytes are stored once, with an explicit original-path mapping.
Absolute local paths in receipts remain unchanged. The archive is evidence,
not an authenticated provider receipt or a portable executable restore image.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import tarfile
from pathlib import Path


DOSSIER = Path(__file__).resolve().parent


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workspace", type=Path)
    parser.add_argument("label", choices=("final311", "final312"))
    args = parser.parse_args()
    selected = sorted(path for path in args.workspace.iterdir()
                      if path.name.startswith("test_original_cases_actual_met")
                      and stat.S_ISDIR(path.lstat().st_mode))
    if len(selected) != 6:
        raise ValueError("expected six distinct real integration directories")
    archive_dir = DOSSIER / "archives"
    archive_dir.mkdir(exist_ok=True)
    archive_path = archive_dir / f"{args.label}_blobs.tar.gz"
    pins, traces, metadata = [], [], []
    seen = set()
    blobs = {}
    with archive_path.open("xb") as stream, tarfile.open(fileobj=stream, mode="w:gz") as archive:
        for root in selected:
            stage = json.loads((root / "attempt/stage/stage.json").read_text())
            context = json.loads((root / "attempt/managed/context/run.json").read_text())
            if context["state"] != "completed" or context["cursor"] != 2:
                raise ValueError("integration context is not complete")
            coordinates = stage["coordinates"]
            seen.add((coordinates["arm"], coordinates["case_id"]))
            trace = {"directory": root.name, "run_id": stage["run_id"],
                     "coordinates": coordinates, "context_checkpoint": context,
                     "norm_status": json.loads((root / "attempt/stage/work/method_state.json").read_text())["nodes"]["N"]["status"],
                     "fake_provider": True, "formal_cell_executed": False}
            traces.append(trace)
            for folder, directories, files in os.walk(root, followlinks=False):
                directories.sort()
                files.sort()
                for name in list(directories):
                    path = Path(folder) / name
                    if not stat.S_ISDIR(path.lstat().st_mode):
                        directories.remove(name)
                        metadata.append({"path": path.relative_to(args.workspace).as_posix(), "kind": "non_regular_not_followed"})
                for name in files:
                    path = Path(folder) / name
                    info = path.lstat()
                    relative = path.relative_to(args.workspace).as_posix()
                    if not stat.S_ISREG(info.st_mode):
                        metadata.append({"path": relative, "kind": "non_regular_not_followed"})
                        continue
                    raw = path.read_bytes()
                    after = path.lstat()
                    if (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns) != (
                            after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns):
                        raise ValueError("fixture file changed during capture")
                    digest = sha(raw)
                    member_name = f"blobs/{digest}"
                    if digest not in blobs:
                        archive.add(path, arcname=member_name, recursive=False)
                        blobs[digest] = {"bytes": len(raw), "sha256": digest}
                    pins.append({"path": relative, "archive_member": member_name,
                                 "bytes": len(raw), "sha256": digest})
    if seen != {(arm, case_id) for arm in "ABC" for case_id in ("D-F", "D-E")}:
        raise ValueError("archive lacks a method or case")
    with tarfile.open(archive_path, "r:gz") as archive:
        members = archive.getmembers()
        if len(members) != len(blobs):
            raise ValueError("archive entry count differs")
        by_name = {pin["archive_member"]: pin for pin in pins}
        for member in members:
            if not member.isfile() or member.name not in by_name:
                raise ValueError("unexpected archive member")
            extracted = archive.extractfile(member)
            if extracted is None:
                raise ValueError("regular archive entry unreadable")
            raw = extracted.read()
            pin = by_name[member.name]
            if len(raw) != pin["bytes"] or sha(raw) != pin["sha256"]:
                raise ValueError("archive bytes differ from original")
    result = {"schema": 1, "classification": "public_cases_synthetic_workflow_fake_provider",
              "workspace": str(args.workspace), "archive": archive_path.name,
              "archive_bytes": archive_path.stat().st_size, "archive_sha256": sha(archive_path.read_bytes()),
              "regular_members": len(blobs), "source_regular_files": len(pins),
              "all_regular_members_reopened_and_verified": True,
              "full_session_restore_image": False, "empty_directories_archived": False,
              "other_entries_metadata_only": metadata, "traces": traces, "files": pins}
    (archive_dir / f"{args.label}_blobs.json").write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    print(json.dumps({key: result[key] for key in ("archive", "archive_bytes", "regular_members", "archive_sha256")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
