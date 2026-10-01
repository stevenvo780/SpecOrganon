"""Seal D124 declared-rating controls, preserving D123 originals and history."""
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
PRIOR = "experiments/development/authorized_route_entry_2026-10-01/receipt.json"
PRIOR_SHA = "3092daf3333b209893a85b5ffca0cc2b72573b36add1fa800c264415879f6f35"
PRIOR_COMMIT = "7d5a7762918b19ebd581e0499f0a6407568c50a2"
DOCS = {"docs/estado.md", "docs/validacion_actual.md", "docs/activacion_validacion.md", "docs/decisiones.md"}
CODE = {"scripts/development_rating_ingress.py", "scripts/read_development_rating.py",
        "tests/test_development_rating_ingress.py", "tests/test_read_development_rating.py"}
spec = importlib.util.spec_from_file_location("d123_sealing", ROOT / PRIOR.replace("receipt.json", "seal_evidence.py"))
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
        current = lib.pin(row["path"])
        assert current["sha256"] == row["sha256"] and current["bytes"] == row["bytes"]
    return {"D123_inherited": inherited, "D123_live_records": len(rows) - len(DOCS),
            "D124_frozen_sources": len(freeze["sources"])}


def names():
    result = {p.relative_to(ROOT).as_posix() for p in DOSSIER.rglob("*") if p.is_file()}
    result.discard(RECEIPT)
    return result | DOCS | CODE


def build():
    preserved = preserve_baseline()
    review = json.loads((DOSSIER / "review/final_review.json").read_bytes())
    assert review["verdict"] == "PASS_local_scope"
    receipt = {"schema": 1, "classification": "declared_rating_ingress_synthetic_controls_not_verified_Q",
               "prior_commit": PRIOR_COMMIT, "prior_receipt_sha256": PRIOR_SHA, "preserved": preserved,
               "historical_active_docs_preserved_in_git": sorted(DOCS), "review_verdict": review["verdict"],
               "actual_human_evaluations": 0, "formal_cells_executed": 0, "paid_provider_requests": 0,
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
