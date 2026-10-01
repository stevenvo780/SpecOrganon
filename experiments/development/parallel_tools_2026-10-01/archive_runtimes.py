"""Preserve regular public fixture journals; never follow links or copy a session."""

from __future__ import annotations

import hashlib
import io
import json
import os
import stat
import tarfile
from pathlib import Path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    dossier = Path(__file__).resolve().parent
    roots = {}
    for path in sorted((dossier / "checks").glob("*/report.json")):
        roots["root-" + path.parent.name] = Path(json.loads(path.read_bytes())["runtime_root"])
    for path in sorted((dossier / "dossier/root_checks").glob("*/result.json")):
        roots["root-" + path.parent.name] = Path(json.loads(path.read_bytes())["runtime"]) / "cases"
    for path in sorted((dossier / "worker_checks").glob("engine_*/receipt.json")):
        data = json.loads(path.read_bytes())
        command = data["argv"]
        roots[path.parent.name] = Path(command[command.index("--basetemp") + 1])
    for root in roots.values():
        if (not str(root).startswith("/tmp/specorganon-D115-") or root.name != "cases"
                or any(path.is_symlink() for path in (root, *root.parents)) or not root.is_dir()):
            raise ValueError("fixture runtime root is missing, linked or unexpected")
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
                            if not stat.S_ISREG(before.st_mode) or before.st_size > 64 * 1024 * 1024:
                                raise ValueError("unbounded or nonregular fixture member")
                            raw = stream.read()
                            after = os.fstat(stream.fileno())
                        fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
                        if any(getattr(before, field) != getattr(after, field) for field in fields):
                            raise ValueError("fixture member changed while reading")
                        name = f"runtimes/{label}/{relative}"
                        item = tarfile.TarInfo(name)
                        item.size, item.mode = len(raw), mode
                        tar.addfile(item, io.BytesIO(raw))
                        members.append({"root": label, "path": relative, "member": name,
                                        "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(), "mode": mode})
                    else:
                        record = {"root": label, "path": relative, "kind": "symlink" if stat.S_ISLNK(info.st_mode)
                                  else "nonregular", "mode": mode}
                        if stat.S_ISLNK(info.st_mode):
                            record["target"] = os.readlink(path)
                        metadata.append(record)
    expected, seen = {row["member"]: row for row in members}, set()
    with tarfile.open(archive, "r:gz") as tar:
        for item in tar:
            if not item.isfile() or item.name not in expected or item.name in seen:
                raise ValueError("unexpected or repeated archive member")
            row = expected[item.name]
            raw = tar.extractfile(item).read()
            if (len(raw) != row["bytes"] or hashlib.sha256(raw).hexdigest() != row["sha256"]
                    or item.mode != row["mode"] or sha(roots[row["root"]] / row["path"]) != row["sha256"]):
                raise ValueError("archive bytes differ from fixture or manifest")
            seen.add(item.name)
    if seen != set(expected):
        raise ValueError("archive is incomplete")
    result = {"classification": "public_synthetic_fixture_regular_files_only", "roots": {
              key: str(value) for key, value in roots.items()}, "archive": str(archive.relative_to(dossier)),
              "archive_bytes": archive.stat().st_size, "archive_sha256": sha(archive),
              "regular_files": len(members), "members": members, "metadata_only": metadata,
              "uncompressed_bytes": sum(row["bytes"] for row in members), "reopened_verified": True,
              "full_session_restore": False, "formal_cells_executed": 0,
              "excluded_runtime_scope": "early broker unit default pytest roots; sources and streams retained"}
    (target / "runtime_manifest.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({key: result[key] for key in ("regular_files", "archive_bytes", "archive_sha256", "reopened_verified")}))


if __name__ == "__main__":
    main()
