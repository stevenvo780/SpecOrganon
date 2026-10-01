"""Seal D120 indexed evidence and preserve historical D119 bindings."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path


DOSSIER = Path(__file__).resolve().parent
ROOT = DOSSIER.parents[2]
PREFIX = DOSSIER.relative_to(ROOT).as_posix()
RECEIPT = PREFIX + "/receipt.json"
DOCS = {"docs/estado.md", "docs/decisiones.md", "docs/activacion_validacion.md", "docs/validacion_actual.md"}
D119 = "experiments/development/coordinated_runtime_2026-10-01/receipt.json"
D119_COMMIT = "c64169c15c5cbe6dd35c5fc4c25704fc042332a7"
D119_SHA = "cd41baa29e59e1e75d7ed9e46412e0885b13c0b02e72629ea1af1dc55ab28b07"
spec = importlib.util.spec_from_file_location("d118_sealing", ROOT / "experiments/development/coordinated_contract_2026-10-01/seal_evidence.py")
lib = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lib)


def load(name: str) -> dict:
    return json.loads((DOSSIER / name).read_bytes())


def tree(revision: str) -> dict:
    result = {}
    for raw in lib.git("ls-tree", "-r", "-z", revision).split(b"\0"):
        if raw:
            metadata, path = raw.split(b"\t", 1)
            mode, kind, oid = metadata.decode().split()
            assert kind == "blob"
            result[os.fsdecode(path)] = (mode, oid)
    return result


def preserve_d119() -> list[dict]:
    raw = (ROOT / D119).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == D119_SHA
    old = json.loads(raw)["records"]
    for row in old:
        if row["path"] not in DOCS:
            assert lib.pin(row["path"]) == row, (row["path"], "historical D119 pin changed")
    lib.compare_blobs([row for row in old if row["path"] in DOCS], tree(D119_COMMIT))
    return [row for row in old if row["path"] not in DOCS] + [lib.pin(D119)]


def build() -> None:
    assert not (ROOT / RECEIPT).exists(), "receipt must be new"
    index = lib.index_paths()
    assert not lib.git("ls-files", "--others", "--exclude-standard", "--", PREFIX), "stage new evidence first"
    paths = {name for name in index if name.startswith(PREFIX + "/") and name != RECEIPT} | DOCS
    historical = preserve_d119()
    freeze = load("source_freeze.json")
    paths.update(row["path"] for row in historical + freeze["records"])
    records = [lib.pin(name) for name in sorted(paths)]
    lib.compare_blobs(records, index)
    frozen = {row["path"]: row for row in records}
    for row in freeze["records"]:
        assert (frozen[row["path"]]["bytes"], frozen[row["path"]]["sha256"]) == (row["bytes"], row["sha256"])
    source_commit = load("evidence.json")["source_freeze_commit"]
    gates = {name: load("checks/" + name + "/report.json") for name in ("final311", "final312", "integration02")}
    for gate in gates.values():
        assert gate["all_exit_zero"] is True and gate["D119_unchanged"] is True
        assert gate["head"] == gate["head_before"] == source_commit and gate["sources_unchanged"] is True
        assert gate["formal_cells_executed"] == gate["model_requests_sent"] == gate["tools_executed"] == 0
    integration = gates["integration02"]
    matrix = {(interpreter, arm, case) for interpreter in ("311", "312")
              for arm in ("A", "B", "C") for case in ("D-F", "D-E")}
    assert len(integration["commands"]) == len(integration["measurements"]) == 12
    assert {(row["interpreter"], row["arm"], row["case"]) for row in integration["commands"]} == matrix
    assert {(row["interpreter"], row["arm"], row["case"]) for row in integration["measurements"]} == matrix
    for row in integration["measurements"]:
        measured = json.loads((ROOT / row["report"]).read_bytes())
        assert measured["native_D119_guard_replay_publication_verified"] is True
        assert measured["formal_cell_executed"] is False and measured["quality_assessed"] is False
        assert measured["coordinates"]["arm"] == row["arm"] and measured["coordinates"]["case_id"] == row["case"]
        assert row["original_runtime_unchanged"] is True
    review = load("review/final_review.json")
    assert review["open_material_findings"] == [] and review["verdict"] == "PASS_local_scope"
    receipt = {"schema": 1, "classification": "local_measurement_reconciliation_not_experimental_acceptance",
               "prospective_plan_commit": "357ac439736de621e1d21dbb7f86d8a473ee4854",
               "source_freeze_commit": source_commit,
               "source_freeze_sha256": lib.pin(PREFIX + "/source_freeze.json")["sha256"],
               "prior_D119_commit": D119_COMMIT, "prior_D119_receipt_sha256": D119_SHA,
               "historical_D119_pins_preserved_live": len(historical),
               "active_docs_historical_blobs_preserved": sorted(DOCS),
               "gate_names": list(gates), "existing_runtimes_read": 12,
               "formal_cells_executed": 0, "new_model_requests": 0, "tools_executed": 0,
               "acceptance": {"C1": "cumplido_tecnico_D107_preservado", "C2": "no_demostrado",
                              "C3": "no_demostrado", "C4": "no_demostrado", "C5": "no_demostrado"},
               "coverage": {"pin_count": len(records), "dossier_paths_excluding_exact_root_receipt":
                            sum(row["path"].startswith(PREFIX + "/") for row in records)},
               "limitations": ["responses and token declarations are synthetic historical fixtures",
                               "prices are declared local ceilings, not authenticated invoices",
                               "W, H, remote activity and total study costs remain missing",
                               "same UID cooperating locks and digests do not authenticate custody"],
               "records": records}
    with (ROOT / RECEIPT).open("xb") as stream:
        stream.write(json.dumps(receipt, indent=2, ensure_ascii=False, allow_nan=False).encode() + b"\n")
    print(json.dumps({"receipt": lib.pin(RECEIPT), "pins": len(records)}))


def verify(head: bool) -> None:
    receipt = load("receipt.json")
    records = receipt["records"]
    assert len(records) == len({row["path"] for row in records}) == receipt["coverage"]["pin_count"]
    index = lib.index_paths()
    expected = {row["path"] for row in records if row["path"].startswith(PREFIX + "/")}
    actual = {name for name in index if name.startswith(PREFIX + "/") and name != RECEIPT}
    assert expected == actual, "dossier coverage changed"
    for row in records:
        assert lib.pin(row["path"]) == row, (row["path"], "live pin changed")
    preserve_d119()
    pinned = records + [lib.pin(RECEIPT)]
    lib.compare_blobs(pinned, index)
    if head:
        lib.compare_blobs(pinned, tree("HEAD"))
        assert lib.git("status", "--porcelain=v1") == b"", "tree must be clean"
    print(json.dumps({"verified_pins": len(records), "live_index_equal": True, "head_checked": head,
                      "prior_D119_preserved": True, "receipt": lib.pin(RECEIPT)}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["build", "verify"])
    parser.add_argument("--head", action="store_true")
    args = parser.parse_args()
    build() if args.command == "build" else verify(args.head)
