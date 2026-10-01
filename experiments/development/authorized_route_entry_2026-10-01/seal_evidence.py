"""Seal D123 local entry evidence while preserving the frozen D122 baseline."""
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
PRIOR = "experiments/development/real_route_proposal_2026-10-01/receipt.json"
PRIOR_SHA = "32176ad8fbf0ebbca9b4244bcdd32f1b7677ba1563a410a7245e8a9dfefa4606"
PRIOR_COMMIT = "cd97b23c979f30d9e451f9064e70e334224e7143"
DOCS = {"docs/estado.md", "docs/validacion_actual.md", "docs/activacion_validacion.md", "docs/decisiones.md"}
CODE = {"scripts/authorized_coordinated_runtime.py", "scripts/provider_outcome_accounting.py",
        "tests/test_authorized_coordinated_runtime.py", "tests/test_provider_outcome_accounting.py"}
spec = importlib.util.spec_from_file_location("d122_sealing", ROOT / PRIOR.replace("receipt.json", "seal_evidence.py"))
previous = importlib.util.module_from_spec(spec)
spec.loader.exec_module(previous)
lib = previous.lib


def preserve_baseline():
    inherited = previous.preserve_baseline()
    raw = (ROOT / PRIOR).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == PRIOR_SHA
    rows = json.loads(raw)["records"]
    for row in rows:
        if row["path"] in DOCS:
            old = lib.git("show", PRIOR_COMMIT + ":" + row["path"])
            assert len(old) == row["bytes"] and hashlib.sha256(old).hexdigest() == row["sha256"]
        else:
            assert lib.pin(row["path"]) == row
    freeze = json.loads((DOSSIER / "source_freeze.json").read_bytes())
    for row in freeze["sources"]:
        assert lib.pin(row["path"])["sha256"] == row["sha256"]
    return {"D121_live_pins": inherited, "D122_live_records": len(rows) - len(DOCS), "D123_frozen_sources": len(freeze["sources"])}


def names():
    result = {p.relative_to(ROOT).as_posix() for p in DOSSIER.rglob("*") if p.is_file()}
    result.discard(RECEIPT)
    return result | DOCS | CODE


def build():
    preserved = preserve_baseline()
    review = json.loads((DOSSIER / "review/final_review.json").read_bytes())
    assert review["verdict"] == "PASS_local_scope"
    receipt = {"schema": 1, "classification": "guarded_route_local_evidence_not_R1",
               "prior_commit": PRIOR_COMMIT, "prior_receipt_sha256": PRIOR_SHA, "preserved": preserved,
               "historical_active_docs_preserved_in_git": sorted(DOCS), "review_verdict": review["verdict"],
               "formal_cells_executed": 0, "paid_provider_requests": 0,
               "records": [lib.pin(name) for name in sorted(names())]}
    with (ROOT / RECEIPT).open("xb") as stream:
        stream.write(json.dumps(receipt, indent=2, allow_nan=False).encode() + b"\n")
    print(json.dumps({"records": len(receipt["records"]), "receipt": lib.pin(RECEIPT)}))


def verify(head):
    receipt = json.loads((ROOT / RECEIPT).read_bytes())
    assert receipt["preserved"] == preserve_baseline()
    rows = receipt["records"]
    assert len(rows) == len(names()) and {row["path"] for row in rows} == names()
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
                      "preserved": receipt["preserved"], "receipt": lib.pin(RECEIPT)}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("build", "verify"))
    parser.add_argument("--head", action="store_true")
    args = parser.parse_args()
    build() if args.command == "build" else verify(args.head)
