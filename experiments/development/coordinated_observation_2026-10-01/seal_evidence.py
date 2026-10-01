"""Seal D121 local evidence; preserve prior D120 and D119 historical pins."""
from __future__ import annotations

import argparse
import importlib.util
import json
import os

from capture_checks import DOCS, DOSSIER, ROOT, preserve_baseline, sha

PREFIX = DOSSIER.relative_to(ROOT).as_posix()
RECEIPT = PREFIX + "/receipt.json"
PRIOR = "experiments/development/coordinated_measurement_2026-10-01/receipt.json"
PRIOR_COMMIT = "f05bb9ca00914ac5b17b2e05c95d726522bb0a2b"
PRIOR_SHA = "87ed0c79a38e35bb6f0788b95ef1ef81029062ba68ff67e2827960e923313cdd"
spec = importlib.util.spec_from_file_location("d118_sealing", ROOT / "experiments/development/coordinated_contract_2026-10-01/seal_evidence.py")
lib = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lib)


def load(name):
    return json.loads((DOSSIER / name).read_bytes())


def tree(revision):
    result = {}
    for raw in lib.git("ls-tree", "-r", "-z", revision).split(b"\0"):
        if raw:
            metadata, path = raw.split(b"\t", 1)
            mode, kind, oid = metadata.decode().split()
            assert kind == "blob"
            result[os.fsdecode(path)] = (mode, oid)
    return result


def prior_pins():
    raw = (ROOT / PRIOR).read_bytes()
    assert sha(raw) == PRIOR_SHA
    records = json.loads(raw)["records"]
    for row in records:
        if row["path"] not in DOCS:
            assert lib.pin(row["path"]) == row, row["path"]
    lib.compare_blobs([row for row in records if row["path"] in DOCS], tree(PRIOR_COMMIT))
    return [row for row in records if row["path"] not in DOCS] + [lib.pin(PRIOR)]


def build():
    assert not (ROOT / RECEIPT).exists()
    index = lib.index_paths()
    assert not lib.git("ls-files", "--others", "--exclude-standard", "--", PREFIX)
    historical = prior_pins()
    freeze, evidence = load("source_freeze.json"), load("evidence.json")
    paths = {name for name in index if name.startswith(PREFIX + "/") and name != RECEIPT} | DOCS
    paths.update(row["path"] for row in historical + freeze["records"])
    records = [lib.pin(name) for name in sorted(paths)]
    lib.compare_blobs(records, index)
    pins = {row["path"]: row for row in records}
    for row in freeze["records"]:
        assert (pins[row["path"]]["bytes"], pins[row["path"]]["sha256"]) == (row["bytes"], row["sha256"])
    gates = {name: load("checks/" + name + "/report.json") for name in ("final311", "final312", "integration311", "integration312")}
    for gate in gates.values():
        assert gate["head"] == gate["head_before"] == evidence["source_freeze_commit"]
        assert gate["sources_unchanged"] is True and gate["baseline_unchanged"] is True and gate["all_exit_zero"] is True
        assert gate["formal_cells_executed"] == gate["paid_model_requests"] == 0
    runs = []
    for name in ("integration311", "integration312"):
        gate = gates[name]
        assert gate["archive"]["original_unchanged"] is True
        rows = gate["integration_result"]["runs"]
        assert len(rows) == 3 and {row["arm"] for row in rows} == set("ABC")
        assert all(row["case_id"] == "D-E" and row["formal_cell_executed"] is False and row["quality_assessed"] is False for row in rows)
        assert all(row["W_local_elapsed_seconds"] > 0 and row["metrics"]["incomplete_operations"] == 0 for row in rows)
        runs.extend(rows)
    assert len({row["run_id"] for row in runs}) == 6
    review = load("review/final_review.json")
    assert review["verdict"] == "PASS_local_scope" and review["open_material_findings"] == []
    preserve_baseline()
    result = {"schema": 1, "classification": "prospective_local_observation_not_experimental_acceptance",
              "prospective_plan_commit": evidence["plan_commit"], "source_freeze_commit": evidence["source_freeze_commit"],
              "source_freeze_sha256": pins[PREFIX + "/source_freeze.json"]["sha256"],
              "prior_D120_commit": PRIOR_COMMIT, "prior_D120_receipt_sha256": PRIOR_SHA,
              "historical_pins_preserved_live": len(historical), "active_docs_historical_blobs_preserved": sorted(DOCS),
              "gate_names": list(gates), "fresh_synthetic_runtimes": len(runs),
              "synthetic_requests": sum(row["native_requests"] for row in runs),
              "native_tool_calls": sum(row["native_tools"] for row in runs),
              "formal_cells_executed": 0, "paid_model_requests": 0, "quality_assessed": False,
              "acceptance": {"C1": "cumplido_tecnico_D107_preservado", "C2": "no_demostrado", "C3": "no_demostrado", "C4": "no_demostrado", "C5": "no_demostrado"},
              "coverage": {"pin_count": len(records), "dossier_paths_excluding_exact_root_receipt": sum(row["path"].startswith(PREFIX + "/") for row in records)},
              "limitations": ["W and callback intervals observed only on this Linux host", "usage and prices synthetic declarations", "H, remote compute, total study costs and Q pending", "cooperative locks and local hashes do not authenticate custody"],
              "records": records}
    with (ROOT / RECEIPT).open("xb") as stream:
        stream.write(json.dumps(result, indent=2, allow_nan=False).encode() + b"\n")
    print(json.dumps({"receipt": lib.pin(RECEIPT), "pins": len(records)}))


def verify(head):
    receipt = load("receipt.json")
    records = receipt["records"]
    assert len(records) == len({row["path"] for row in records}) == receipt["coverage"]["pin_count"]
    index = lib.index_paths()
    expected = {row["path"] for row in records if row["path"].startswith(PREFIX + "/")}
    assert expected == {name for name in index if name.startswith(PREFIX + "/") and name != RECEIPT}
    for row in records:
        assert lib.pin(row["path"]) == row
    prior_pins()
    preserve_baseline()
    pinned = records + [lib.pin(RECEIPT)]
    lib.compare_blobs(pinned, index)
    if head:
        lib.compare_blobs(pinned, tree("HEAD"))
        assert lib.git("status", "--porcelain=v1") == b""
    print(json.dumps({"verified_pins": len(records), "head_checked": head, "historical_baseline_preserved": True, "receipt": lib.pin(RECEIPT)}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("build", "verify"))
    parser.add_argument("--head", action="store_true")
    args = parser.parse_args()
    build() if args.command == "build" else verify(args.head)
