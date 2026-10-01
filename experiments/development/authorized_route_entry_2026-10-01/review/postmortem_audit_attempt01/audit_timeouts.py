"""Finite read-only checks of the two closed timeout archives and prior pins."""

import hashlib
import json
from pathlib import Path
import stat
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[4]
DOSSIER = Path(__file__).resolve().parents[1]
OLD_FREEZE = "d452b8f"
NEW_FREEZE = "7246936"
DOCS = {"docs/estado.md", "docs/validacion_actual.md", "docs/activacion_validacion.md", "docs/decisiones.md"}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read(path):
    metadata = path.lstat()
    assert stat.S_ISREG(metadata.st_mode), str(path)
    return path.read_bytes()


def git_blob(commit, path):
    return subprocess.run(["git", "show", f"{commit}:{path}"], cwd=ROOT,
                          capture_output=True, check=True).stdout


def run():
    reports = []
    frozen_old = json.loads(git_blob(OLD_FREEZE, str(DOSSIER.relative_to(ROOT) / "source_freeze.json")))
    for label, expected_entries in (("311", 1433), ("312", 1355)):
        folder = DOSSIER / "checks" / f"final_attempt02_py{label}"
        post = json.loads(read(folder / "postmortem.json"))
        assert post["exit_code"] == 124 and post["timeout_seconds"] == 600
        origin = Path(post["runtime_dir"])
        archive = folder / "runtimes.tar.gz"
        manifest = json.loads(read(folder / "runtimes_inventory.json"))
        expected = {row["path"]: row for row in manifest["entries"]}
        assert len(expected) == len(manifest["entries"]) == expected_entries
        archive_raw = read(archive)
        assert len(archive_raw) == post["archive"]["archive_bytes"]
        assert sha(archive_raw) == post["archive"]["archive_sha256"]
        with tarfile.open(archive, "r:gz") as stream:
            members = stream.getmembers()
            assert len(members) == len(expected)
            assert {member.name for member in members} == set(expected)
            assert len({member.name for member in members}) == len(members)
            for member in members:
                row = expected[member.name]
                path = origin / member.name
                assert not Path(member.name).is_absolute() and ".." not in Path(member.name).parts
                metadata = path.lstat()
                assert member.mode == row["mode"] == stat.S_IMODE(metadata.st_mode)
                if row["kind"] == "directory":
                    assert member.isdir() and stat.S_ISDIR(metadata.st_mode)
                else:
                    assert row["kind"] == "file" and member.isfile() and stat.S_ISREG(metadata.st_mode)
                    assert metadata.st_nlink == 1
                    raw = stream.extractfile(member).read()
                    assert member.size == len(raw) == row["bytes"]
                    assert sha(raw) == row["sha256"] == sha(read(path))
        assert {p.relative_to(origin).as_posix() for p in origin.rglob("*")} == set(expected)
        cli_calls = json.loads(read(origin / "cli_calls.json"))
        assert len(cli_calls) == post["partial_cli_calls"]
        for call in cli_calls:
            assert call["exit_code"] == call["expected_exit_code"]
            for name in ("stdout", "stderr"):
                assert sha(read(origin / call[name])) == call[name + "_sha256"]
        sources = []
        for pin in frozen_old["sources"]:
            raw = read(folder / "sources" / pin["path"])
            assert len(raw) == pin["bytes"] and sha(raw) == pin["sha256"]
            assert raw == git_blob(OLD_FREEZE, pin["path"])
            sources.append(pin)
        reports.append({"label": label, "archive": post["archive"], "all_members_headers_bytes_modes_verified": True,
                        "whole_live_origin_equal_to_archive_and_manifest": True, "partial_cli_calls": len(cli_calls),
                        "all_partial_cli_command_stream_digests_verified": True,
                        "old_source_snapshot_verified_against_Git_d452b8f": sources,
                        "scope": "closed600s timeout; no PASS or full integration completion inferred",
                        "missing_final_integration_streams_disclosed": post["original_integration_streams"]})
    preservation = []
    for dossier, commit, expected_count, expected_sha in (
        ("real_route_proposal_2026-10-01", "cd97b23c979f30d9e451f9064e70e334224e7143", 125,
         "32176ad8fbf0ebbca9b4244bcdd32f1b7677ba1563a410a7245e8a9dfefa4606"),
        ("coordinated_observation_2026-10-01", "9f90b79b75c087ea5e9c6ab87f270880e7fb684a", 5879,
         "76c59b7597884ee0517a88836dffc377658a5bf1fe91e512e9dd1d6f0f35ec22"),
    ):
        receipt_path = ROOT / "experiments/development" / dossier / "receipt.json"
        raw = read(receipt_path)
        assert sha(raw) == expected_sha
        prior = json.loads(raw)
        assert len(prior["records"]) == expected_count
        for pin in prior["records"]:
            body = git_blob(commit, pin["path"]) if pin["path"] in DOCS else read(ROOT / pin["path"])
            assert len(body) == pin["bytes"] and sha(body) == pin["sha256"]
            if pin["path"] not in DOCS:
                assert stat.S_IMODE((ROOT / pin["path"]).lstat().st_mode) & 0o111 == 0
        preservation.append({"dossier": dossier, "non_active_doc_live_pins": expected_count - 4,
                             "fixed_root_receipt_sha256": expected_sha, "four_historical_doc_blobs_verified_at": commit})
    current_freeze_raw = read(DOSSIER / "source_freeze.json")
    assert current_freeze_raw == git_blob(NEW_FREEZE, str(DOSSIER.relative_to(ROOT) / "source_freeze.json"))
    frozen = json.loads(current_freeze_raw)
    for pin in frozen["sources"]:
        raw = read(ROOT / pin["path"])
        assert len(raw) == pin["bytes"] and sha(raw) == pin["sha256"]
        assert raw == git_blob(NEW_FREEZE, pin["path"])
    output = {"schema": 1, "classification": "independent_timeout_archive_audit_not_final_PASS",
              "postmortems": reports, "prior_preservation": preservation,
              "current_source_freeze": {"commit": NEW_FREEZE, "sha256": sha(current_freeze_raw), "records": len(frozen["sources"])},
              "controller_and_accounting_unchanged_from_d452b8f": all(
                  read(ROOT / name) == git_blob(OLD_FREEZE, name)
                  for name in ("scripts/authorized_coordinated_runtime.py", "scripts/provider_outcome_accounting.py")),
              "sealer_static_scope": "D123 dossier+four code/testpaths+four active docs, exact root receipt excluded; inherited D122/D121 live pins and historical docs preserved; no root receipt yet built or verified",
              "README_pending_update": "Current README refers to final_attempt02 and omits the two600s wrapper timeouts; final docs must identify actual completed final gates and disclose these failed attempts.",
              "final_attempt03_not_polled_or_audited": True, "final_acceptance_verdict": False,
              "formal_cells_executed": 0, "paid_provider_requests_by_reviewer": 0}
    target = DOSSIER / "review/postmortem_review.json"
    target.write_text(json.dumps(output, indent=2) + "\n")
    return {"report": str(target), "archive_entries": [1433, 1355], "partial_CLI_calls": [104, 96], "final_PASS": False}


if __name__ == "__main__":
    print(json.dumps(run(), sort_keys=True))
