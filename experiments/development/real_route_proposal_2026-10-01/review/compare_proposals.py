"""Compare the four independently verified declarations, not experimental results."""

import itertools
import json
from pathlib import Path
import subprocess

from audit_proposal import DOCS, DOSSIER, PRIOR, PRIOR_RECEIPT, ROOT, canonical, load, read, sha


def main() -> None:
    base = DOSSIER / "review"
    reports = [load(base / f"audit{label}_attempt02/report.json") for label in ("311", "312")]
    rows = [row for report in reports for row in report["results"]]
    assert len(rows) == 4
    comparisons = []
    for left, right in itertools.combinations(rows, 2):
        lmap, rmap = left["inventory"], right["inventory"]
        assert set(lmap) == set(rmap)
        for path in lmap:
            assert lmap[path]["mode"] == rmap[path]["mode"]
            assert lmap[path]["kind"] == rmap[path]["kind"]
        differences = {path for path in lmap if lmap[path] != rmap[path]}
        allowed = {"assets.json", "bundle.json", "schedule.json"}
        if left["option"] != right["option"]:
            allowed |= {"assets/runtime_policy.json", "configuration.json", "price_profile.json"}
        if left["label"] != right["label"]:
            allowed |= {"assets/method_tool", "assets/analysis_tool", "assets/tool_policy"}
        assert differences == allowed
        assert set(map(tuple, left["coordinates"])) == set(map(tuple, right["coordinates"]))
        assert left["source_records"] == right["source_records"]
        assert left["runtime_configuration"] == right["runtime_configuration"]
        assert left["semantic_runtime_policy"] == right["semantic_runtime_policy"]
        assert left["semantic_tool_policy"] == right["semantic_tool_policy"]
        assert not set(left["run_ids"]) & set(right["run_ids"])
        for name in ("assets/method_tool", "assets/analysis_tool"):
            lraw = read(Path(left["bundle"]) / name).split(b"\n", 1)
            rraw = read(Path(right["bundle"]) / name).split(b"\n", 1)
            assert lraw[1] == rraw[1]
            assert lraw[0] == ("#!" + reports[int(left["label"] == "312")]["python"]).encode()
            assert rraw[0] == ("#!" + reports[int(right["label"] == "312")]["python"]).encode()
        comparisons.append({"pair": [left["label"] + "/" + left["option"], right["label"] + "/" + right["option"]],
                            "different_files": sorted(differences), "same_materials_roles_resources": True,
                            "launchers_differ_only_in_interpreter_shebang": True,
                            "release_sequence_equal": left["release_sequence"] == right["release_sequence"],
                            "ids_disjoint": True})
    prior = load(PRIOR_RECEIPT)
    old_ids = set()
    old_schedules = []
    for pin in prior["records"]:
        if pin["path"].endswith("schedule.json"):
            schedule = load(ROOT / pin["path"])
            if isinstance(schedule.get("runs"), list):
                ids = {row["run_id"] for row in schedule["runs"] if "run_id" in row}
                old_ids |= ids
                old_schedules.append({"path": pin["path"], "run_ids": len(ids), "sha256": pin["sha256"]})
    new_ids = set().union(*(set(row["run_ids"]) for row in rows))
    assert len(new_ids) == 48 and not new_ids & old_ids
    docs = []
    for name in sorted(DOCS):
        old = subprocess.run(["git", "show", f"{PRIOR}:{name}"], cwd=ROOT, capture_output=True, check=True).stdout
        current = read(ROOT / name)
        if name == "docs/decisiones.md":
            assert current.startswith(old)
        else:
            prefix, tail = old.split(b"\n\n", 1)
            assert current.startswith(prefix + b"\n\n") and current.endswith(tail)
        docs.append({"path": name, "historical_sha256": sha(old), "current_sha256": sha(current),
                     "old_content_preserved_exactly_with_new_append_or_header": True})
    evidence = load(DOSSIER / "evidence.json")
    assert evidence["capture_runner_sha256"] == sha(read(DOSSIER / "capture_checks.py"))
    assert evidence["new_preparation_bundles"] == 4
    assert evidence["original_build_commands"] == evidence["original_verify_commands"] == 4
    assert evidence["formal_cells_executed"] == evidence["provider_requests"] == evidence["runtime_claims_or_releases_created"] == 0
    for key in ("full_cost_known", "quality_assessed", "real_route_ready", "paid_route_authorized"):
        assert evidence[key] is False
    for name in ("baseline_before", "baseline_after"):
        folder = DOSSIER / "checks" / name
        command = load(folder / "command.json")
        assert command["exit_code"] == 0
        assert command["stdout_sha256"] == sha(read(folder / "stdout"))
        assert command["stderr_sha256"] == sha(read(folder / "stderr"))
        assert read(folder / "stderr") == b""
        assert b"5879" in read(folder / "stdout")
    protected_changes = subprocess.run(["git", "diff", "--name-only", PRIOR], cwd=ROOT,
                                       capture_output=True, check=True).stdout.decode().splitlines()
    assert all(name in DOCS or name.startswith("experiments/development/real_route_proposal_2026-10-01/")
               for name in protected_changes)
    dossier_pins = []
    for path in sorted(DOSSIER.rglob("*")):
        if path.is_file() and not path.is_relative_to(base):
            raw = read(path)
            dossier_pins.append({"path": path.relative_to(ROOT).as_posix(), "bytes": len(raw), "sha256": sha(raw)})
    result = {"schema": 1, "comparisons": comparisons, "new_ids": len(new_ids),
              "prior_schedule_ids": len(old_ids), "prior_schedules": old_schedules,
              "new_ids_disjoint_from_pinned_prior_schedules": True, "docs": docs,
              "root_baseline_command_streams_verified": True, "protected_changes": protected_changes,
              "non_review_dossier_pins": dossier_pins, "non_review_dossier_sha256": sha(canonical(dossier_pins)),
              "formal_cells_executed": 0, "real_route_go": False}
    (base / "cross_comparison.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"pair_comparisons": 6, "new_ids": len(new_ids), "protected_scope_verified": True}, sort_keys=True))


if __name__ == "__main__":
    main()
