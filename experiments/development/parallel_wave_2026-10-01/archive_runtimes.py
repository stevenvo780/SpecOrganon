"""Archive completed public fixture workspaces; never follow symlinks."""

from __future__ import annotations

import hashlib
import io
import json
import os
import stat
import tarfile
from pathlib import Path


def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    dossier = Path(__file__).resolve().parent
    roots = {}
    for name in ("integration_01", "integration_02", "integration_03", "final311", "final312"):
        data = json.loads((dossier / "checks" / name / "report.json").read_text())
        roots["root-" + name] = Path(data["runtime_root"])
    handoff = json.loads((dossier / "worker_checks/engine/handoff.json").read_text())
    for index, root in enumerate(handoff["public_fixture_workspaces"]):
        roots[f"engine-{index}"] = Path(root)
    for root in roots.values():
        if not str(root).startswith("/tmp/specorganon-D114-") or root.name != "cases":
            raise ValueError("unexpected runtime root")
        if any(parent.is_symlink() for parent in (root, *root.parents)) or not root.is_dir():
            raise ValueError("runtime root unavailable or symlinked")
    target = dossier / "archives"
    target.mkdir(exist_ok=False)
    archive = target / "runtimes.tar.gz"
    members, metadata = [], []
    with archive.open("xb") as output, tarfile.open(fileobj=output, mode="w:gz") as tar:
        for label, root in roots.items():
            pending = [root]
            while pending:
                current = pending.pop()
                for entry in sorted(os.scandir(current), key=lambda item: item.name):
                    path = Path(entry.path)
                    info = path.lstat()
                    relative = str(path.relative_to(root))
                    mode = stat.S_IMODE(info.st_mode)
                    if stat.S_ISDIR(info.st_mode):
                        metadata.append({"root": label, "path": relative, "kind": "directory", "mode": mode})
                        pending.append(path)
                    elif stat.S_ISREG(info.st_mode):
                        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
                        with os.fdopen(fd, "rb") as stream:
                            before = os.fstat(stream.fileno())
                            if not stat.S_ISREG(before.st_mode) or before.st_size > 1024**3:
                                raise ValueError("runtime member is not bounded regular data")
                            raw = stream.read()
                            after = os.fstat(stream.fileno())
                        fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
                        if any(getattr(before, key) != getattr(after, key) for key in fields):
                            raise ValueError("runtime member changed while reading")
                        name = f"runtimes/{label}/{relative}"
                        item = tarfile.TarInfo(name)
                        item.size, item.mode = len(raw), mode
                        tar.addfile(item, io.BytesIO(raw))
                        members.append({"root": label, "path": relative, "member": name,
                                        "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
                                        "mode": mode})
                    else:
                        record = {"root": label, "path": relative,
                                  "kind": "symlink" if stat.S_ISLNK(info.st_mode) else "nonregular",
                                  "mode": mode}
                        if stat.S_ISLNK(info.st_mode):
                            record["target"] = os.readlink(path)
                        metadata.append(record)
    expected = {row["member"]: row for row in members}
    seen = set()
    with tarfile.open(archive, "r:gz") as tar:
        for item in tar:
            if not item.isfile() or item.name not in expected or item.name in seen:
                raise ValueError("archive has an unexpected member")
            row = expected[item.name]
            raw = tar.extractfile(item).read()
            if len(raw) != row["bytes"] or hashlib.sha256(raw).hexdigest() != row["sha256"]:
                raise ValueError("archive member differs")
            original = roots[row["root"]] / row["path"]
            if original.is_symlink() or sha(original) != row["sha256"]:
                raise ValueError("preserved runtime changed")
            seen.add(item.name)
    if seen != set(expected):
        raise ValueError("archive missing members")
    report = {"classification": "public_synthetic_fixture_regular_files_only",
              "roots": {label: str(path) for label, path in roots.items()},
              "archive": str(archive.relative_to(dossier)), "archive_bytes": archive.stat().st_size,
              "archive_sha256": sha(archive), "members": members, "metadata_only": metadata,
              "regular_files": len(members), "uncompressed_bytes": sum(row["bytes"] for row in members),
              "reopened_verified": True, "full_session_restore": False,
              "excluded_runtime_scope": "default pytest roots of early ledger/context unit attempts; source/streams retained",
              "formal_cells_executed": 0}
    (target / "runtime_manifest.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({key: report[key] for key in ("regular_files", "archive_bytes", "archive_sha256", "reopened_verified")}))


if __name__ == "__main__":
    main()
