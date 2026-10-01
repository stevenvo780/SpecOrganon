"""PURE rejection probe: no tree inspection, delegate or original IO allowed."""
import hashlib
import json
from pathlib import Path
import types
from unittest.mock import patch

DOSSIER = Path(__file__).resolve().parents[1]
SOURCE = DOSSIER / "archive_originals.py"
EXPECTED_SHA = "f02f5329b16e9341d766d0328f06b015af5223952e7ae9aa7051aacf7c69aa9b"


def main():
    raw = SOURCE.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == EXPECTED_SHA
    module = types.ModuleType("independent_archive_rejection_PURE")
    module.__file__ = str(SOURCE)
    exec(compile(raw, str(SOURCE), "exec"), module.__dict__)
    root = Path("/tmp/D124-DECLARED-ORIGINAL")
    alias = Path("/tmp/D124-DECLARED-ALIAS/../D124-DECLARED-ORIGINAL")
    output = Path("/tmp/D124-DECLARED-OUTPUT/archive.tar.gz")
    inventory = Path("/tmp/D124-DECLARED-OUTPUT/inventory.json")
    cases = [
        ("archive", (alias, output, inventory)),
        ("archive", (root, alias / "archive.tar.gz", inventory)),
        ("archive", (root, output, alias / "inventory.json")),
        ("archive", (root, alias / "archive.tar.gz", alias / "inventory.json")),
        ("verify", (alias / "archive.tar.gz", inventory)),
        ("verify", (output, alias / "inventory.json")),
        ("verify", (alias / "archive.tar.gz", alias / "inventory.json")),
    ]
    callbacks, results = [], []

    def forbidden(*_args):
        callbacks.append("forbidden_tree_directory_or_helper_callback")
        raise AssertionError("rejection must precede IO")

    with patch.object(module, "_tree", forbidden), patch.object(module, "_directory", forbidden), patch.object(module, "_helper", forbidden):
        for kind, args in cases:
            try:
                (module.archive_originals if kind == "archive" else module.verify_originals)(*args)
            except module.ArchiveOriginalsError as error:
                assert str(error) == "archive_or_verification_rejected"
                results.append({"operation": kind, "arguments": [str(a) for a in args], "fixed_error": str(error)})
            else:
                raise AssertionError("parent component accepted")
    assert not callbacks and len(results) == 7
    print(json.dumps({"classification": "PURE_mock_path_rejection_no_original_IO", "source_sha256": EXPECTED_SHA,
                      "rejected_cases": results, "callbacks": callbacks, "originals_created_or_changed": False,
                      "archived_participant_code_executed": False}, sort_keys=True))


if __name__ == "__main__":
    main()
