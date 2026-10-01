"""Focused real private-directory controls; only synthetic original bytes."""
import importlib.util
import json
import os
from pathlib import Path
import stat
import tempfile

WRAPPER = Path(__file__).resolve().parents[2] / "archive_originals.py"
spec = importlib.util.spec_from_file_location("d124_archive_fix02_control", WRAPPER)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
root = Path(tempfile.mkdtemp(prefix="specorganon-D124-archive-fix02-"))
originals, alias = root / "originals", root / "alias"
originals.mkdir(mode=0o700)
alias.mkdir(mode=0o700)
source = originals / "synthetic_original"
source.write_bytes(b"synthetic finite original; no real rating")
source.chmod(0o600)
output, inventory = root / "originals.tar.gz", root / "inventory.json"


def snapshot(path):
    return {item.relative_to(path).as_posix(): {"mode": stat.S_IMODE(item.lstat().st_mode),
                                             "bytes": item.read_bytes() if item.is_file() else None}
            for item in path.rglob("*")}


before = snapshot(root)
calls = []
saved = {name: getattr(module, name) for name in ("_tree", "_directory", "_helper")}


def forbidden(*_):
    calls.append(True)
    raise AssertionError("path rejection must precede inspection and helper loading")


for name in saved:
    setattr(module, name, forbidden)
alias_originals = alias / ".." / "originals"
archive_cases = [(alias_originals, output, inventory),
                 (originals, alias_originals / "bad.tar.gz", inventory),
                 (originals, output, alias_originals / "bad.json"),
                 (originals, alias_originals / "bad.tar.gz", alias_originals / "bad.json")]
for arguments in archive_cases:
    try:
        module.archive_originals(*arguments)
    except module.ArchiveOriginalsError as error:
        assert str(error) == "archive_or_verification_rejected"
    else:
        raise AssertionError("archive accepted a parent-directory component")
verify_cases = [(alias / ".." / output.name, inventory),
                (output, alias / ".." / inventory.name),
                (alias / ".." / output.name, alias / ".." / inventory.name)]
for arguments in verify_cases:
    try:
        module.verify_originals(*arguments)
    except module.ArchiveOriginalsError as error:
        assert str(error) == "archive_or_verification_rejected"
    else:
        raise AssertionError("verify accepted a parent-directory component")
assert not calls and snapshot(root) == before
assert not output.exists() and not inventory.exists()
for name, value in saved.items():
    setattr(module, name, value)

receipt = module.archive_originals(originals, output, inventory)
assert receipt["original_unchanged"] and not receipt["restore_authority"]
assert module.verify_originals(output, inventory)["verified_entries"] == 1
after_archive = snapshot(root)
try:
    module.archive_originals(originals, output, inventory)
except module.ArchiveOriginalsError:
    pass
else:
    raise AssertionError("existing outputs accepted")
assert snapshot(root) == after_archive
link = originals / "link"
link.symlink_to(source)
try:
    module.archive_originals(originals, root / "bad.tar.gz", root / "bad.json")
except module.ArchiveOriginalsError:
    pass
else:
    raise AssertionError("symlink accepted")
assert not (root / "bad.tar.gz").exists() and not (root / "bad.json").exists()
link.unlink()
hardlink = originals / "hardlink"
os.link(source, hardlink)
try:
    module.archive_originals(originals, root / "hard.tar.gz", root / "hard.json")
except module.ArchiveOriginalsError:
    pass
else:
    raise AssertionError("hardlink accepted")
assert not (root / "hard.tar.gz").exists() and not (root / "hard.json").exists()
hardlink.unlink()
changed = json.loads(inventory.read_bytes())
changed["entries"][0]["sha256"] = "0" * 64
tampered = root / "tampered.json"
tampered.write_text(json.dumps(changed))
try:
    module.verify_originals(output, tampered)
except module.ArchiveOriginalsError:
    pass
else:
    raise AssertionError("digest tampering accepted")
assert snapshot(originals) == {source.name: before["originals/" + source.name]}
print(json.dumps({"runtime_root": str(root), "parent_component_rejections": 7,
                  "precheck_entered_tree_or_helper": False, "parent_component_cases_no_effects": True,
                  "previous_controls_passed": 6, "original_bytes_and_modes_unchanged": True,
                  "archive_extracted": False, "archived_code_executed": False}))
