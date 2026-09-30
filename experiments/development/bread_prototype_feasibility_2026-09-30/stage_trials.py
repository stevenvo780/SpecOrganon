"""Stage identical public source bytes for three native prototype trials.

The directories and contexts are separate by convention. This does not enforce
native filesystem isolation, token/cost caps or independent source custody.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path


def pin(path: Path) -> dict:
    raw = path.read_bytes()
    return {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}


def stage(repo: Path, destination: Path) -> dict:
    location = repo / "experiments/development/bread_prototype_feasibility_2026-09-30"
    plan = json.loads((location / "plan.json").read_text())
    sys.path.insert(0, str(repo / "scripts"))
    from case_package import extract_package, inspect_package, pack_package

    origins = {
        "task.md": "cases/bread_development/task.md",
        "source_claims.json": "cases/bread_development/source_claims.json",
        "source_manifest.json": "cases/bread_development/source_manifest.json",
        "source_lca.pdf": "cases/bread_norway/source_lca.pdf",
        "source_survey.pdf": "cases/bread_norway/source_survey.pdf",
        "survey_table1.json": "cases/bread_norway/survey_table1.json",
    }
    manifest_raw = (repo / origins["source_manifest.json"]).read_bytes()
    source_manifest = json.loads(manifest_raw)
    expected_names = set(origins) - {"source_manifest.json"}
    frozen_sources = {}
    for item in source_manifest["files"]:
        name = item["visible_file"]
        if name not in expected_names or name in frozen_sources or origins[name] != item["repository_source_path"]:
            raise ValueError("source manifest paths do not match the visible package")
        expected = {"sha256": item["sha256"], "bytes": item["bytes"]}
        if pin(repo / origins[name]) != expected:
            raise ValueError(f"{name} differs from the frozen source manifest")
        frozen_sources[name] = expected
    if set(frozen_sources) != expected_names:
        raise ValueError("source manifest files are incomplete")
    frozen_sources["source_manifest.json"] = {
        "sha256": hashlib.sha256(manifest_raw).hexdigest(), "bytes": len(manifest_raw),
    }
    frozen_paths = list(origins.values())
    frozen_paths += ["prototypes/" + name for name in ["core.py", "sequential.py", "graph.py", "risk.py"]]
    relative_location = location.relative_to(repo)
    frozen_paths += [str(relative_location / name) for name in [
        "plan.json", "rubric.md", "reference.json", "executor_brief.md",
        "capture_prototype.py", "stage_trials.py",
    ]]
    frozen_paths += ["scripts/case_package.py"]
    commit = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                            capture_output=True, text=True, check=True).stdout.strip()
    frozen_git_files = {}
    for path in frozen_paths:
        committed = subprocess.run(["git", "-C", str(repo), "show", f"{commit}:{path}"],
                                   capture_output=True, check=True).stdout
        if (repo / path).read_bytes() != committed:
            raise ValueError(f"{path} differs from frozen Git revision {commit}")
        frozen_git_files[path] = {"sha256": hashlib.sha256(committed).hexdigest(), "bytes": len(committed)}

    destination.mkdir(mode=0o700, parents=False, exist_ok=False)
    visible = destination / "visible-source"
    visible.mkdir(mode=0o700)
    for name, origin in origins.items():
        shutil.copyfile(repo / origin, visible / name)
        if pin(visible / name) != frozen_sources[name]:
            raise ValueError(f"{name} changed during staging; partial destination is untrusted")
    package_manifest = {
        "schema": 1, "classification": "executor_visible_case_package", "case_id": plan["case_id"],
        "task_file": "task.md",
        "files": [{"path": name, **pin(visible / name)} for name in origins],
        "deliverables": ["analysis.py", "metrics.json", "sources.json", "report.md",
                         "prototype_case.json", "state.json", "prototype_calls.jsonl"],
    }
    (visible / "case.json").write_text(json.dumps(package_manifest, sort_keys=True, indent=2) + "\n")
    archive = destination / "visible.zip"
    pack_package(visible, archive)
    assert inspect_package(archive, plan["case_id"]) == package_manifest
    trials = []
    harness = ["core.py", "sequential.py", "graph.py", "risk.py"]
    for trial in plan["planned_trials"]:
        work = destination / trial["trial_id"]
        work.mkdir(mode=0o700)
        extract_package(archive, work / "input", plan["case_id"])
        (work / "harness").mkdir(mode=0o700)
        for name in harness:
            shutil.copyfile(repo / "prototypes" / name, work / "harness" / name)
            if pin(work / "harness" / name) != frozen_git_files["prototypes/" + name]:
                raise ValueError("prototype code changed during staging; partial destination is untrusted")
        for name in ["capture_prototype.py", "executor_brief.md"]:
            shutil.copyfile(location / name, work / name)
            if pin(work / name) != frozen_git_files[str(relative_location / name)]:
                raise ValueError("trial instructions changed during staging; partial destination is untrusted")
        (work / "profile.json").write_text(json.dumps(trial, sort_keys=True, indent=2) + "\n")
        fixed = ["profile.json", "capture_prototype.py", "executor_brief.md"]
        fixed += ["harness/" + name for name in harness]
        fixed += ["input/case.json", *["input/" + name for name in origins]]
        trials.append({**trial, "directory": str(work),
                       "fixed_files": {name: pin(work / name) for name in fixed}})
    result = {
        "schema": 1, "classification": plan["classification"],
        "case_id": plan["case_id"], "visible_package": pin(archive),
        "frozen_commit": commit, "frozen_git_files": frozen_git_files,
        "source_origins": {name: {"repository_path": origin, **pin(repo / origin)}
                           for name, origin in origins.items()},
        "plan": pin(location / "plan.json"), "rubric": pin(location / "rubric.md"),
        "stager": pin(Path(__file__)), "trials": trials,
        "filesystem_isolation_enforced": False, "global_run_limits_enforced": False,
        "counts_toward_required_24_runs": False,
    }
    (destination / "staging.json").write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo", type=Path)
    parser.add_argument("new_destination", type=Path)
    args = parser.parse_args()
    print(json.dumps(stage(args.repo.resolve(strict=True), args.new_destination.absolute()), sort_keys=True))


if __name__ == "__main__":
    main()
