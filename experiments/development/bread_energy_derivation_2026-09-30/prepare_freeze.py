"""Print prospective D108 freeze after every candidate input is committed.

No probe, source preparation, installation or test is executed here. The caller
must preserve the printed JSON as source_freeze.json and commit it before runs.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import stat
import subprocess

DOSSIER = "experiments/development/bread_energy_derivation_2026-09-30"
INSTALL = "experiments/development/indicator_retirement_2026-09-30/environment_install_repaired.json"
PROBE = "scripts/probe_bread_energy_variant.py"
BUILDER = "scripts/build_bread_energy_variant.py"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def pin(raw):
    return {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def read(repo, name):
    relative = Path(name)
    require(not relative.is_absolute() and ".." not in relative.parts, "noncanonical public path")
    path = repo / relative
    require(path.resolve(strict=True).is_relative_to(repo), "public input escapes repository")
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode) and info.st_size <= 32 * 1024 * 1024, "not a bounded public file")
    return path.read_bytes()


def git(repo, *args):
    return subprocess.check_output(["git", "--no-optional-locks", *args], cwd=repo,
                                   env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"})


def prepare(repo):
    repo = repo.resolve(strict=True)
    inputs = json.loads(read(repo, DOSSIER + "/plan_inputs.json"))
    plan = json.loads(read(repo, DOSSIER + "/plan.json"))
    require(plan["study_id"] == "D108" and plan["real_runs"]["per_python"] == 1,
            "prospective plan changed")
    runtime = Path(inputs["runtime"])
    require(runtime.is_absolute() and runtime.is_dir() and not runtime.is_symlink()
            and not runtime.resolve(strict=True).is_relative_to(repo), "external reserved runtime required")
    require(not any(runtime.iterdir()), "reserved runtime is not empty; no retry")
    installed = json.loads(read(repo, INSTALL))
    names = set(inputs["files"]) | {PROBE, BUILDER, INSTALL}
    production = {str(p.relative_to(repo)) for p in (repo / "src/specorganon").rglob("*.py")}
    require(len(production) == 24, "expected exactly 24 production modules")
    names.update(production)
    for path in (repo / DOSSIER).rglob("*"):
        require(not path.is_symlink(), "prospective dossier must not contain symlinks")
        if path.is_file():
            require(path.name != "source_freeze.json", "freeze already exists")
            names.add(str(path.relative_to(repo)))
    optional_test = "tests/test_bread_energy_variant.py"
    if (repo / optional_test).exists():
        names.add(optional_test)
    names.add(installed["wheel"]["path"])
    for environment in installed["environments"].values():
        for key in ("inventory", "installed_inventory"):
            absolute = Path(environment[key]["path"])
            relative = str(absolute.relative_to(repo)) if absolute.is_absolute() else str(absolute)
            names.add(relative)
    head = git(repo, "rev-parse", "HEAD").decode().strip()
    files = {}
    for name in sorted(names):
        raw = read(repo, name)
        require(raw == git(repo, "show", head + ":" + name), "input not committed or differs: " + name)
        files[name] = pin(raw)
    for name, expected in inputs["files"].items():
        require(files[name] == expected, "original prospective input changed: " + name)
    return {"schema": 1, "study_id": "D108",
            "classification": "prospective development installed food documentary derivation, not final reserve",
            "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
            "source_commit_before_freeze": head, "files": files, "file_count": len(files),
            "all_files_match_committed_blobs": True,
            "plan_pin": files[DOSSIER + "/plan.json"], "input_record_pin": files[DOSSIER + "/plan_inputs.json"],
            "runtime": str(runtime), "probe": PROBE, "builder": BUILDER,
            "production_modules": {name: files[name] for name in sorted(production)},
            "environments": installed["environments"], "wheel": installed["wheel"],
            "pythons": {label: environment["python"] for label, environment in installed["environments"].items()},
            "attempts_each": 1, "automatic_retry": False, "rebuilds_or_installs": 0,
            "input_exposure": "known historical documentary inputs used in development",
            "new_paid_API_calls": 0, "experimental_model_generations": 0,
            "field_operations": 0, "counts_toward_required24": False, "C2_C5_PASS": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo", type=Path)
    args = parser.parse_args()
    print(json.dumps(prepare(args.repo), ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
