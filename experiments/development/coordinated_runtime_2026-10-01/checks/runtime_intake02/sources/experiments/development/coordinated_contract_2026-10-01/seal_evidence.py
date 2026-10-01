"""Pin exact indexed D118 evidence; compare live/index/HEAD without publishing."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess

DOSSIER = Path(__file__).resolve().parent
ROOT = DOSSIER.parents[2]
PREFIX = DOSSIER.relative_to(ROOT).as_posix()
RECEIPT = PREFIX + "/receipt.json"
DOCS = ["docs/estado.md", "docs/decisiones.md", "docs/activacion_validacion.md", "docs/validacion_actual.md"]


def git(*args: str) -> bytes:
    return subprocess.check_output(["git", *args], cwd=ROOT)


def load(path: str) -> dict:
    return json.loads((DOSSIER / path).read_bytes())


def index_paths() -> dict:
    result = {}
    for item in git("ls-files", "--stage", "-z").split(b"\0"):
        if item:
            metadata, path = item.split(b"\t", 1)
            mode, oid, stage = metadata.decode().split()
            assert stage == "0", "unmerged index"
            result[os.fsdecode(path)] = (mode, oid)
    return result


def pin(path: str) -> dict:
    full = ROOT / path
    info = full.lstat()
    if stat.S_ISLNK(info.st_mode):
        raw = os.fsencode(os.readlink(full))
        return {"path": path, "kind": "symlink", "mode": "120000", "target": os.fsdecode(raw),
                "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
    assert stat.S_ISREG(info.st_mode), path
    raw = full.read_bytes()
    return {"path": path, "kind": "regular", "mode": "100755" if info.st_mode & 0o111 else "100644",
            "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def compare_blobs(records: list[dict], mapping: dict) -> None:
    child = subprocess.Popen(["git", "cat-file", "--batch"], cwd=ROOT,
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    try:
        for row in records:
            mode, oid = mapping[row["path"]]
            assert mode == row["mode"], (row["path"], "mode")
            child.stdin.write((oid + "\n").encode())
            child.stdin.flush()
            header = child.stdout.readline().decode().split()
            assert len(header) == 3 and header[1] == "blob", header
            count = int(header[2])
            assert count == row["bytes"], (row["path"], "bytes")
            body = child.stdout.read(count)
            assert len(body) == count and child.stdout.read(1) == b"\n"
            assert hashlib.sha256(body).hexdigest() == row["sha256"], (row["path"], "sha256")
    finally:
        child.stdin.close()
        child.stdout.close()
        assert child.wait() == 0


def build() -> None:
    assert not (ROOT / RECEIPT).exists(), "never overwrite a previous receipt"
    index = index_paths()
    assert not git("ls-files", "--others", "--exclude-standard", "--", PREFIX), "unstaged evidence exists"
    ignored = [os.fsdecode(path) for path in git("ls-files", "--others", "--ignored",
               "--exclude-standard", "-z", "--", PREFIX).split(b"\0") if path]
    assert all("__pycache__" in Path(path).parts or ".pytest_cache" in Path(path).parts
               for path in ignored), "an ignored evidence path needs explicit staging"
    freeze, baseline = load("source_freeze.json"), load("baseline_pins.json")
    paths = {path for path in index if path.startswith(PREFIX + "/") and path != RECEIPT}
    paths.update(row["path"] for row in freeze["records"] + baseline["records"])
    paths.update(DOCS)
    records = [pin(path) for path in sorted(paths)]
    compare_blobs(records, index)
    by_path = {row["path"]: row for row in records}
    for source in freeze["records"] + baseline["records"]:
        current = by_path[source["path"]]
        assert current["bytes"] == source["bytes"] and current["sha256"] == source["sha256"], source["path"]
    gates = {}
    for name in ["final311", "final312", "integration311", "integration312"]:
        report = load("checks/" + name + "/report.json")
        assert report["source_unchanged"] and report["all_exit_zero"]
        assert report["head"] == git("rev-parse", "HEAD").decode().strip()
        gates[name] = {"report": PREFIX + "/checks/" + name + "/report.json",
                       "runtime_root": report["runtime_root"], "commands": report["commands"],
                       "sources_unchanged": True, "source_count": len(report["sources_before"])}
    archive = load("archives/runtime_manifest.json")
    comparison = load("checks/archive_verification.json")
    assert comparison["all_original_bytes_modes_and_targets_equal"]
    archive_pin = by_path[PREFIX + "/archives/" + archive["archive"]]
    assert archive_pin["bytes"] == archive["archive_bytes"] and archive_pin["sha256"] == archive["archive_sha256"]
    publication = load("checks/publication/report.json")
    assert publication["scoped_code_docs_whitespace_exit_code"] == 0
    receipt = {"schema": 1, "classification": "offline_coordinated_contract_evidence_not_experimental_acceptance",
               "prospective_plan_commit": "4abc46f27977f3e245eef0cbd20ce91da2dee916",
               "source_freeze_commit": git("rev-parse", "HEAD").decode().strip(),
               "source_freeze_sha256": by_path[PREFIX + "/source_freeze.json"]["sha256"],
               "baseline_prior_head": baseline["prior_head"], "formal_cells_executed": 0,
               "acceptance": {"C1": "technical_D107_preserved", "C2": "not_demonstrated", "C3": "not_demonstrated",
                              "C4": "not_demonstrated", "C5": "not_demonstrated"},
               "verification": {"source_freeze_pins": len(freeze["records"]), "baseline_pins": len(baseline["records"]),
                                "external_tools": freeze["external_tools"], "gates": gates,
                                "original_source_cli_preparation": "two interpreters, 12 R1 identities each; no cell executed",
                                "structural_fixtures": "six per interpreter; pending quantities, no participant execution or Q"},
               "archive": {"path": archive_pin["path"], "bytes": archive_pin["bytes"], "sha256": archive_pin["sha256"],
                           "roots": len(archive["roots"]), "regular_files": archive["regular_files"],
                           "unique_blobs": archive["unique_blobs"], "metadata_entries": len(archive["records"]) - archive["regular_files"],
                           "restorable_authority": False}, "independent_review": by_path[PREFIX + "/review.md"],
               "luna": {"requested_model": "gpt-6-luna", "scope": "baseline_inventory_only", "paths": 103,
                        "root_and_independent_reviewer_verified": True, "quality_comparison": False},
               "publication_checks": publication,
               "coverage": {"pin_count": len(records), "dossier_indexed_paths_excluding_only_root_receipt":
                            sum(row["path"].startswith(PREFIX + "/") for row in records),
                            "included_nested_receipt_paths": sum(row["path"].startswith(PREFIX + "/") and
                             Path(row["path"]).name == "receipt.json" for row in records),
                            "excluded_exact_path": RECEIPT, "ignored_generated_cache": ignored,
                            "symlink_pins_use_target_bytes_without_following": True},
               "next_dependency": "coordinated A/B/C runtimes and authenticated effective usage/activity; authorized R1 then adaptation/freeze and R2",
               "records": records}
    (ROOT / RECEIPT).write_text(json.dumps(receipt, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"built": RECEIPT, "pins": len(records), "receipt": pin(RECEIPT)}))


def verify(head: bool) -> None:
    receipt = load("receipt.json")
    records = receipt["records"]
    index = index_paths()
    expected = {row["path"] for row in records if row["path"].startswith(PREFIX + "/")}
    actual = {path for path in index if path.startswith(PREFIX + "/") and path != RECEIPT}
    assert expected == actual, {"missing": sorted(expected - actual), "extra": sorted(actual - expected)}
    assert len(records) == len({row["path"] for row in records}) == receipt["coverage"]["pin_count"]
    for row in records:
        assert pin(row["path"]) == row, row["path"]
    self_pin = pin(RECEIPT)
    compare_blobs([*records, self_pin], index)
    for row in receipt["verification"]["external_tools"]:
        raw = Path(row["path"]).read_bytes()
        assert len(raw) == row["bytes"] and hashlib.sha256(raw).hexdigest() == row["sha256"]
    if head:
        mapping = {}
        for entry in git("ls-tree", "-r", "-z", "HEAD").split(b"\0"):
            if entry:
                metadata, path = entry.split(b"\t", 1)
                mode, kind, oid = metadata.decode().split()
                assert kind == "blob"
                mapping[os.fsdecode(path)] = (mode, oid)
        compare_blobs([*records, self_pin], mapping)
        assert git("status", "--porcelain=v1") == b"", "tree is not clean"
    print(json.dumps({"verified_pins": len(records), "live_index_equal": True,
                      "head_checked": head, "coverage_equal": True, "receipt": self_pin}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["build", "verify"])
    parser.add_argument("--head", action="store_true")
    args = parser.parse_args()
    build() if args.command == "build" else verify(args.head)
