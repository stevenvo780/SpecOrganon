"""Read retained D124 originals, archives and CLI streams without model calls."""
import hashlib
import importlib.util
import json
from pathlib import Path
import stat
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[4]
DOSSIER = Path(__file__).resolve().parents[1]
REVIEW = DOSSIER / "review"
COMMIT = "4459ae24337cdf2cdd5a094e087ca8700dae8d9a"
FREEZE_SHA = "d2103281db40e959451d018984d9e9786caba78f7edb0a91e1a7d98963c30113"
ENV = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "TZ": "UTC", "PYTHONDONTWRITEBYTECODE": "1"}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def load(path):
    return json.loads(path.read_bytes())


def git(commit, name):
    return subprocess.run(["git", "show", commit + ":" + name], cwd=ROOT,
                          capture_output=True, check=True).stdout


def pin(path):
    raw = path.read_bytes()
    return {"path": str(path.relative_to(ROOT)), "bytes": len(raw), "sha256": sha(raw)}


def inventory(root):
    rows = {}
    for path in sorted(root.rglob("*")):
        info = path.lstat()
        assert stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)
        row = {"path": path.relative_to(root).as_posix(), "mode": stat.S_IMODE(info.st_mode),
               "kind": "directory" if stat.S_ISDIR(info.st_mode) else "file"}
        if row["kind"] == "file":
            assert info.st_nlink == 1
            raw = path.read_bytes()
            row.update(bytes=len(raw), sha256=sha(raw))
        rows[row["path"]] = row
    return rows


def private_snapshot(root):
    result = {}
    for path in sorted(root.iterdir()):
        info = path.lstat()
        assert stat.S_ISREG(info.st_mode)
        raw = path.read_bytes()
        result[path.name] = {"mode": stat.S_IMODE(info.st_mode),
                             "identity": [info.st_dev, info.st_ino, info.st_uid, info.st_nlink,
                                          info.st_size, info.st_mtime_ns, info.st_ctime_ns],
                             "bytes": len(raw), "sha256": sha(raw)}
    return result


def archive_check(archive, manifest, root, expected_count):
    rows = load(manifest)["entries"]
    expected = {row["path"]: row for row in rows}
    assert len(expected) == len(rows) == expected_count
    assert expected == inventory(root)
    with tarfile.open(archive, "r:gz") as stream:
        members = stream.getmembers()
        assert len(members) == len({m.name for m in members}) == expected_count
        assert {m.name for m in members} == set(expected)
        for member in members:
            assert not Path(member.name).is_absolute() and ".." not in Path(member.name).parts
            row = expected[member.name]
            origin = (root / member.name).lstat()
            assert member.mode == row["mode"]
            assert member.uid == origin.st_uid and member.gid == origin.st_gid
            if row["kind"] == "directory":
                assert member.isdir()
            else:
                assert member.isfile() and member.size == row["bytes"]
                assert sha(stream.extractfile(member).read()) == row["sha256"]
    raw = archive.read_bytes()
    return {"members": expected_count, "bytes": len(raw), "sha256": sha(raw),
            "membership_headers_modes_content_and_current_origins_equal": True}


def run():
    frozen = (DOSSIER / "source_freeze.json").read_bytes()
    assert sha(frozen) == FREEZE_SHA
    assert frozen == git(COMMIT, str((DOSSIER / "source_freeze.json").relative_to(ROOT)))
    freeze = json.loads(frozen)
    assert len(freeze["sources"]) == 8
    root_summary = load(DOSSIER / "root_reopen_report.json")
    reports = []
    for label in ("311", "312"):
        folder = DOSSIER / "checks" / ("final02_py" + label)
        report = load(folder / "report.json")
        assert report["head_before"] == report["head_after"] == COMMIT
        assert report["source_freeze_sha256"] == FREEZE_SHA
        assert all(report[key] for key in ("all_exit_zero", "source_unchanged", "source_freeze_unchanged", "preservation_unchanged"))
        assert len(report["commands"]) == 6
        for i, call in enumerate(report["commands"]):
            assert call["exit_code"] == 0
            assert call["argv"][0] == report["python"] or i in (1, 3)
            for name in ("stdout", "stderr"):
                assert sha((folder / f"{i}.{name}").read_bytes()) == call[name + "_sha256"]
        assert b"87 passed" in (folder / "0.stdout").read_bytes()
        for source in freeze["sources"]:
            raw = (ROOT / source["path"]).read_bytes()
            assert sha(raw) == source["sha256"] == report["source_sha256"][source["path"]]
            assert len(raw) == source["bytes"]
            assert raw == (folder / "sources" / source["path"]).read_bytes() == git(COMMIT, source["path"])
        integration = load(folder / "cli/integration_result.json")
        assert integration == report["integration"]
        assert integration["actual_cli_calls"] == len(integration["commands"]) == 7
        assert integration["accepted_controls"] == 3 and integration["rejected_controls"] == 4
        assert integration["python"] == report["python"] and not integration["key_environment_inherited"]
        origin = Path(integration["original_root"])
        before = inventory(origin)
        archive = archive_check(folder / "originals.tar.gz", folder / "originals_inventory.json", origin, 21)
        assert archive["bytes"] == report["original_archive"]["archive_bytes"]
        assert archive["sha256"] == report["original_archive"]["archive_sha256"]
        reopened = []
        for i, call in enumerate(integration["commands"]):
            assert call["argv"][:3] == [report["python"], "-I", "-B"]
            assert call["exit_code"] == call["expected_exit"] == (0 if i < 3 else 2)
            assert call["original_snapshots_before"] == call["original_snapshots_after"] == private_snapshot(origin / call["name"])
            out, err = (folder / f"cli/{i}.stdout").read_bytes(), (folder / f"cli/{i}.stderr").read_bytes()
            assert sha(out) == call["stdout_sha256"] and sha(err) == call["stderr_sha256"] and err == b""
            assert b"PUBLIC-SYNTHETIC-SENTINEL" not in out
            output = json.loads(out)
            assert output == call["report"] and not output["Q_demonstrated"] and not output["quality_verified"] and not output["acceptance_assessed"]
            rating_raw = (origin / call["name"] / "rating.json").read_bytes()
            assert sha(rating_raw) == call["raw_rating_sha256"]
            if i < 3:
                assert output["binding"]["raw_rating_sha256"] == sha(rating_raw)
                assert output["binding"]["blinded_delivery_sha256"] == sha((origin / call["name"] / "blinded-delivery.bin").read_bytes())
                for key, value in output.items():
                    if key.endswith("_verified") or key in ("formal_cell_executed", "confirmatory_rating_rules_applied"):
                        assert value is False
                if i < 2:
                    assert output["declared_component_total"] == 100 and output["declared_incident_count"] == 1
                    assert output["critical_incidents"][0]["type"] == "false_test_result"
                else:
                    assert output["declared_component_total"] == 45
                    assert output["declarations"] and all(v is None for v in output["declarations"].values())
            result = subprocess.run(call["argv"], cwd=ROOT, env=ENV, capture_output=True, timeout=30)
            name = f"reopen_final02_{label}_{i}"
            for stream, raw in (("stdout", result.stdout), ("stderr", result.stderr)):
                (REVIEW / (name + "." + stream)).write_bytes(raw)
            meta = {"argv": call["argv"], "exit_code": result.returncode,
                    "stdout_sha256": sha(result.stdout), "stderr_sha256": sha(result.stderr)}
            (REVIEW / (name + ".command.json")).write_text(json.dumps(meta, indent=2) + "\n")
            assert result.returncode == call["expected_exit"] and result.stdout == out and result.stderr == err
            assert private_snapshot(origin / call["name"]) == call["original_snapshots_after"]
            reopened.append({"name": call["name"], **meta})
        pretty = (origin / "high_critical_pretty/rating.json").read_bytes()
        compact = (origin / "high_critical_compact/rating.json").read_bytes()
        assert sha(pretty) != sha(compact) and json.loads(pretty) == json.loads(compact)
        assert inventory(origin) == before
        root_check = next(v for v in root_summary["checks"] if v["python"] == label)
        assert root_check["report_sha256"] == pin(folder / "report.json")["sha256"]
        reports.append({"python": report["python"], "version_label": label, "report_pin": pin(folder / "report.json"),
                        "recorded_tests": 87, "captured_commands": 6, "CLI": 7, "accepted": 3, "rejected": 4,
                        "archive": archive, "all_original_snapshots_equal_current_before_and_after_reopens": True,
                        "all_reopened_stdout_bytes_identical": True, "reopens": reopened})
    provenance = load(DOSSIER / "provenance/staging_scope.json")
    assert provenance["file_count"] == len(provenance["files"]) == 19
    draft_bytes = 0
    for source in provenance["files"]:
        left, right = Path(source["source"]), ROOT / source["destination"]
        assert left.read_bytes() == right.read_bytes()
        assert pin(right)["sha256"] == source["sha256"] and pin(right)["bytes"] == source["bytes"]
        assert stat.S_IMODE(left.lstat().st_mode) == stat.S_IMODE(right.lstat().st_mode) == source["mode"]
        draft_bytes += source["bytes"]
    assert draft_bytes == 70888
    draft_archive = archive_check(DOSSIER / "provenance/staging_originals.tar.gz",
                                  DOSSIER / "provenance/staging_originals.inventory.json",
                                  DOSSIER / "provenance/staging_originals", 22)
    spec = importlib.util.spec_from_file_location("reviewed_D124_sealer", DOSSIER / "seal_evidence.py")
    sealer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sealer)
    preservation = sealer.preserve_baseline()
    assert preservation == load(DOSSIER / "preservation_after_docs.json")
    for report in reports:
        recorded = load(DOSSIER / "checks" / ("final02_py" + report["version_label"]) / "report.json")
        assert preservation == recorded["preserved_before"] == recorded["preserved_after"]
    for path in DOSSIER.rglob("*"):
        info = path.lstat()
        assert stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)
        if stat.S_ISREG(info.st_mode):
            assert info.st_nlink == 1
    result = {"classification": "independent_D124_final_captures_reopening_not_human_quality", "source_freeze_commit": COMMIT,
              "source_freeze_sha256": FREEZE_SHA, "frozen_sources": 8, "environments": reports,
              "draft_original_files": 19, "draft_original_bytes": draft_bytes, "draft_archive": draft_archive,
              "preservation": preservation, "sealer_scope_name_count_before_final_review": len(sealer.names()),
              "root_receipt_not_yet_created": not (DOSSIER / "receipt.json").exists(),
              "reviewer_new_readonly_CLI_calls": 14, "actual_human_evaluations": 0, "formal_cells_executed": 0,
              "paid_provider_requests": 0, "originals_written_by_reviewer": False}
    (REVIEW / "final_capture_audit.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"archives_verified_members": [21, 21, 22], "reopens": 14, "originals_changed": False,
                      "prior_preservation": preservation}))


if __name__ == "__main__":
    run()
