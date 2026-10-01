"""Pin the offline D122 proposal and preserve the preceding D121 baseline."""

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
PRIOR = "experiments/development/coordinated_observation_2026-10-01/receipt.json"
PRIOR_SHA = "76c59b7597884ee0517a88836dffc377658a5bf1fe91e512e9dd1d6f0f35ec22"
PRIOR_COMMIT = "9f90b79b75c087ea5e9c6ab87f270880e7fb684a"
DOCS = {"docs/estado.md", "docs/validacion_actual.md", "docs/activacion_validacion.md", "docs/decisiones.md"}
spec = importlib.util.spec_from_file_location(
    "d118_sealing", ROOT / "experiments/development/coordinated_contract_2026-10-01/seal_evidence.py")
lib = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lib)


def preserve_baseline() -> int:
    raw = (ROOT / PRIOR).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == PRIOR_SHA
    rows = json.loads(raw)["records"]
    for row in rows:
        if row["path"] in DOCS:
            previous = lib.git("show", PRIOR_COMMIT + ":" + row["path"])
            assert len(previous) == row["bytes"]
            assert hashlib.sha256(previous).hexdigest() == row["sha256"]
        else:
            assert lib.pin(row["path"]) == row
    return len(rows) - len(DOCS)


def build() -> None:
    inherited = preserve_baseline()
    names = {path.relative_to(ROOT).as_posix() for path in DOSSIER.rglob("*") if path.is_file()}
    names.discard(RECEIPT)
    names.update(DOCS)
    review = json.loads((DOSSIER / "review/final_review.json").read_bytes())
    receipt = {"schema": 1, "classification": "offline_route_proposal_not_R1",
               "prior_commit": PRIOR_COMMIT, "prior_receipt_sha256": PRIOR_SHA,
               "inherited_live_pins_preserved": inherited,
               "historical_active_docs_preserved_in_git": sorted(DOCS),
               "review_verdict": review["verdict"], "formal_cells_executed": 0,
               "provider_requests": 0, "records": [lib.pin(name) for name in sorted(names)]}
    with (ROOT / RECEIPT).open("xb") as stream:
        stream.write(json.dumps(receipt, indent=2, allow_nan=False).encode() + b"\n")
    print(json.dumps({"records": len(receipt["records"]), "receipt": lib.pin(RECEIPT)}))


def verify(head: bool) -> None:
    receipt = json.loads((ROOT / RECEIPT).read_bytes())
    assert receipt["inherited_live_pins_preserved"] == preserve_baseline()
    rows = receipt["records"]
    expected = {path.relative_to(ROOT).as_posix() for path in DOSSIER.rglob("*") if path.is_file()}
    expected.discard(RECEIPT)
    expected.update(DOCS)
    assert {row["path"] for row in rows} == expected
    assert len(rows) == len(expected)
    for row in rows:
        assert lib.pin(row["path"]) == row
    pinned = rows + [lib.pin(RECEIPT)]
    lib.compare_blobs(pinned, lib.index_paths())
    if head:
        mapping = {}
        for raw in lib.git("ls-tree", "-r", "-z", "HEAD").split(b"\0"):
            if raw:
                metadata, path = raw.split(b"\t", 1)
                mode, kind, oid = metadata.decode().split()
                assert kind == "blob"
                mapping[path.decode()] = (mode, oid)
        lib.compare_blobs(pinned, mapping)
        assert lib.git("status", "--porcelain=v1") == b""
    print(json.dumps({"verified_records": len(rows), "head_checked": head,
                      "baseline_preserved": True, "receipt": lib.pin(RECEIPT)}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("build", "verify"))
    parser.add_argument("--head", action="store_true")
    args = parser.parse_args()
    build() if args.command == "build" else verify(args.head)
