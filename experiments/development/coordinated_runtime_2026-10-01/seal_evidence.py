"""Seal D119 source, failed attempts, runtime archive and scoped gate evidence."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

DOSSIER = Path(__file__).resolve().parent
ROOT = DOSSIER.parents[2]
PREFIX = DOSSIER.relative_to(ROOT).as_posix()
RECEIPT = PREFIX + "/receipt.json"
DOCS = ["docs/estado.md", "docs/decisiones.md", "docs/activacion_validacion.md", "docs/validacion_actual.md"]
spec = importlib.util.spec_from_file_location("d118_seal_primitives",
    ROOT / "experiments/development/coordinated_contract_2026-10-01/seal_evidence.py")
assert spec and spec.loader
lib = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lib)


def load(path):
    return json.loads((DOSSIER / path).read_bytes())


def build():
    assert not (ROOT / RECEIPT).exists(), "receipt is append-only"
    index = lib.index_paths()
    assert not lib.git("ls-files", "--others", "--exclude-standard", "--", PREFIX), "evidence must be staged"
    ignored = [path.decode() for path in lib.git("ls-files", "--others", "--ignored", "--exclude-standard", "-z", "--", PREFIX).split(b"\0") if path]
    assert all("__pycache__" in Path(path).parts or ".pytest_cache" in Path(path).parts for path in ignored)
    freeze, baseline = load("source_freeze.json"), load("baseline_pins.json")
    paths = {path for path in index if path.startswith(PREFIX + "/") and path != RECEIPT}
    paths.update(row["path"] for row in freeze["records"] + baseline["records"])
    paths.update(DOCS)
    records = [lib.pin(path) for path in sorted(paths)]
    lib.compare_blobs(records, index)
    by_path = {row["path"]: row for row in records}
    for row in freeze["records"] + baseline["records"]:
        assert by_path[row["path"]]["bytes"] == row["bytes"] and by_path[row["path"]]["sha256"] == row["sha256"]
    gates = {}
    for name in ("final311_02", "final312_02", "integration311_02", "integration312_02"):
        report = load("checks/" + name + "/report.json")
        assert report["source_unchanged"] and report["all_exit_zero"]
        assert report["head"] == lib.git("rev-parse", "HEAD").decode().strip()
        gates[name] = {"report": PREFIX + "/checks/" + name + "/report.json", "commands": report["commands"],
                       "runtime_root": report["runtime_root"], "sources_unchanged": True,
                       "source_count": len(report["sources_before"])}
    archive = load("archives/runtime_manifest.json")
    verification = load("checks/archive_verification.json")
    assert verification["all_original_bytes_modes_and_targets_equal"]
    archive_pin = by_path[PREFIX + "/archives/" + archive["archive"]]
    assert archive_pin["bytes"] == archive["archive_bytes"] and archive_pin["sha256"] == archive["archive_sha256"]
    assert load("checks/publication/report.json")["scoped_code_docs_whitespace_exit_code"] == 0
    assert load("review/verdict.json")["open_material_findings"] == []
    result = {"schema": 1, "classification": "synthetic_persistent_runtime_evidence_not_experimental_acceptance",
              "prospective_plan_commit": "5f5f44d95c2042526b195d7aa2a00f0361030f20",
              "source_freeze_commit": lib.git("rev-parse", "HEAD").decode().strip(),
              "source_freeze_sha256": by_path[PREFIX + "/source_freeze.json"]["sha256"],
              "baseline_prior_head": baseline["prior_head"], "formal_cells_executed": 0,
              "acceptance": {"C1": "technical_D107_preserved", "C2": "not_demonstrated", "C3": "not_demonstrated",
                             "C4": "not_demonstrated", "C5": "not_demonstrated"},
              "verification": {"source_freeze_pins": len(freeze["records"]), "baseline_pins": len(baseline["records"]),
                               "external_tools": freeze["external_tools"], "gates": gates},
              "archive": {"path": archive_pin["path"], "bytes": archive_pin["bytes"], "sha256": archive_pin["sha256"],
                          "roots": len(archive["roots"]), "regular_files": archive["regular_files"], "unique_blobs": archive["unique_blobs"],
                          "metadata_entries": len(archive["records"]) - archive["regular_files"], "restorable_authority": False},
              "independent_review": by_path[PREFIX + "/review/verdict.json"],
              "luna": {"requested_model": "gpt-6-luna", "scope": "baseline_inventory_only", "paths": 125,
                       "root_and_independent_reviewer_verified": True, "quality_comparison": False},
              "coverage": {"pin_count": len(records), "dossier_indexed_paths_excluding_only_root_receipt":
                           sum(row["path"].startswith(PREFIX + "/") for row in records), "excluded_exact_path": RECEIPT,
                           "included_nested_receipt_paths": sum(row["path"].startswith(PREFIX + "/") and Path(row["path"]).name == "receipt.json" for row in records),
                           "ignored_generated_cache": ignored},
              "limitations": ["synthetic responses and declared usage, not measured provider activity or invoices",
                              "structure only, no Q, field efficacy or normative approval",
                              "native phase completion remains separate from runtime delivery",
                              "generic direct engine requires wrapper guard to assert original D118 bundle binding",
                              "same-UID local cooperating processes, not hostile tenant isolation"],
              "records": records}
    (ROOT / RECEIPT).write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"built": RECEIPT, "pins": len(records), "receipt": lib.pin(RECEIPT)}))


def verify(head):
    receipt = load("receipt.json")
    records = receipt["records"]
    index = lib.index_paths()
    expected = {row["path"] for row in records if row["path"].startswith(PREFIX + "/")}
    actual = {path for path in index if path.startswith(PREFIX + "/") and path != RECEIPT}
    assert expected == actual
    assert len(records) == len({row["path"] for row in records}) == receipt["coverage"]["pin_count"]
    for row in records:
        assert lib.pin(row["path"]) == row
    self_pin = lib.pin(RECEIPT)
    lib.compare_blobs([*records, self_pin], index)
    for row in receipt["verification"]["external_tools"]:
        raw = Path(row["path"]).read_bytes()
        assert len(raw) == row["bytes"] and hashlib.sha256(raw).hexdigest() == row["sha256"]
    if head:
        mapping = {}
        for entry in lib.git("ls-tree", "-r", "-z", "HEAD").split(b"\0"):
            if entry:
                metadata, path = entry.split(b"\t", 1)
                mode, kind, oid = metadata.decode().split()
                assert kind == "blob"
                mapping[path.decode()] = (mode, oid)
        lib.compare_blobs([*records, self_pin], mapping)
        assert lib.git("status", "--porcelain=v1") == b"", "tree must be clean"
    print(json.dumps({"verified_pins": len(records), "live_index_equal": True, "coverage_equal": True,
                      "head_checked": head, "receipt": self_pin}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["build", "verify"])
    parser.add_argument("--head", action="store_true")
    args = parser.parse_args()
    build() if args.command == "build" else verify(args.head)
