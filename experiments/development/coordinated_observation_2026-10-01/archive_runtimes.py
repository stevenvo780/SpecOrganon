"""Preserve finite public synthetic runtime artifacts; no restore authority."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import tarfile

from capture_checks import runtime_inventory, sha, write


def verify(archive_path, inventory_path):
    inventory = json.loads(inventory_path.read_bytes())
    records = {row["path"]: row for row in inventory["entries"]}
    with tarfile.open(archive_path, "r:gz") as archive:
        members = archive.getmembers()
        assert len(members) == len(records) == len({member.name for member in members})
        for member in members:
            row = records[member.name]
            assert member.mode == row["mode"]
            if row["kind"] == "directory":
                assert member.isdir()
            else:
                assert member.isfile() and member.size == row["bytes"]
                raw = archive.extractfile(member).read()
                assert sha(raw) == row["sha256"]
    return {"entries_verified": len(records), "archive_bytes": archive_path.stat().st_size, "archive_sha256": sha(archive_path.read_bytes())}


def archive(root, output, inventory_path):
    before = runtime_inventory(root)
    write(inventory_path, before)
    assert not output.exists()
    with tarfile.open(output, "x:gz") as bundle:
        for row in before["entries"]:
            bundle.add(root / row["path"], arcname=row["path"], recursive=False)
    assert before == runtime_inventory(root)
    result = verify(output, inventory_path)
    return result | {"original_unchanged": True, "classification": "public_synthetic_runtime_artifact_archive_no_restore_authority"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(verify(args.archive, args.inventory)))
