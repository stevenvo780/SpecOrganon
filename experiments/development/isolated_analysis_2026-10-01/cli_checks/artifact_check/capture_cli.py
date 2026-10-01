"""Capture actual offline D113 build/prepare commands and retain public pins."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
import tempfile
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
DOSSIER = OUT.parent
FREEZE = "c7979a8ccbd97fbbee939ea61ec4839eb8489b52"
PYTHONS = {
    "311": Path("/tmp/specorganon-D107-deps-re8v1j45/venv-311/bin/python"),
    "312": Path("/tmp/specorganon-D107-deps-re8v1j45/venv-312/bin/python"),
}


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def write_json(path: Path, value: object) -> None:
    raw = (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False,
                      allow_nan=False) + "\n").encode()
    with path.open("xb") as stream:
        stream.write(raw)
    path.chmod(0o600)


def json_file(path: Path) -> dict:
    return json.loads(path.read_bytes())


def inventory(root: Path) -> list[dict]:
    result = []
    for directory, subdirs, files in os.walk(root, followlinks=False):
        for name in sorted(subdirs + files):
            path = Path(directory) / name
            metadata = path.lstat()
            record = {"path": str(path.relative_to(root)),
                      "mode": oct(stat.S_IMODE(metadata.st_mode))}
            if stat.S_ISREG(metadata.st_mode):
                raw = path.read_bytes()
                record.update(type="regular", bytes=len(raw), sha256=sha(raw))
            elif stat.S_ISDIR(metadata.st_mode):
                record["type"] = "directory"
            elif stat.S_ISLNK(metadata.st_mode):
                record.update(type="symlink", target=os.readlink(path))
            else:
                record["type"] = "other"
            result.append(record)
    return sorted(result, key=lambda item: item["path"])


def source_snapshot() -> dict[str, dict]:
    frozen = json_file(DOSSIER / "source_freeze.json")
    assert frozen["source_freeze_commit"] == FREEZE
    references = {item["path"]: item for item in frozen["files"]}
    references["scripts/stage_released_run.py"] = {
        "sha256": sha(subprocess.check_output(
            ["git", "show", f"{FREEZE}:scripts/stage_released_run.py"], cwd=ROOT))}
    result = {}
    for name, reference in sorted(references.items()):
        raw = (ROOT / name).read_bytes()
        assert sha(raw) == reference["sha256"], f"source differs from freeze: {name}"
        result[name] = {"sha256": sha(raw), "bytes": len(raw)}
    return result


def capture(label: str, argv: list[str]) -> dict:
    target = OUT / label
    target.mkdir(mode=0o700)
    before = source_snapshot()
    write_json(target / "sources_before.json", before)
    own_raw = Path(__file__).read_bytes()
    (target / "capture_cli.py").write_bytes(own_raw)
    environment = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8",
                   "PYTHONDONTWRITEBYTECODE": "1"}
    start_wall = time.time()
    start = time.monotonic()
    with (target / "stdout").open("xb") as stdout, (target / "stderr").open("xb") as stderr:
        try:
            child = subprocess.run(argv, cwd=ROOT, env=environment,
                                   stdout=stdout, stderr=stderr, timeout=120)
            code, error = child.returncode, None
        except subprocess.TimeoutExpired as exc:
            code, error = None, str(exc)
    elapsed = time.monotonic() - start
    after = source_snapshot()
    write_json(target / "sources_after.json", after)
    record = {
        "classification": "actual_offline_preparation_cli_not_model_execution",
        "argv": argv, "cwd": str(ROOT), "environment": environment,
        "started_unix_seconds": start_wall, "elapsed_seconds": elapsed,
        "exit_code": code, "error": error,
        "stdout_sha256": sha((target / "stdout").read_bytes()),
        "stderr_sha256": sha((target / "stderr").read_bytes()),
        "source_unchanged": before == after,
        "source_snapshot": str(OUT / "sources_before"),
        "capture_source_sha256": sha(own_raw),
        "passed": code == 0 and before == after,
    }
    write_json(target / "receipt.json", record)
    print(json.dumps({"command": label, "exit_code": code,
                      "elapsed_seconds": elapsed, "source_unchanged": before == after}), flush=True)
    return record


def main() -> int:
    os.umask(0o077)
    source = source_snapshot()
    snapshots = OUT / "sources_before"
    snapshots.mkdir(mode=0o700)
    for name in source:
        target = snapshots / name
        target.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        target.write_bytes((ROOT / name).read_bytes())
    write_json(OUT / "sources_before.json", source)
    configuration = {
        "schema": 2, "seed": 113, "analysis_profile": "read_only_v1",
        "model": {"model_id": "offline-fixture-model", "version": "offline-fixture-model",
                  "family": "fixture", "tier": "fixture", "effort": "default",
                  "effort_provider_value": None},
        "price_profile": {"model": "offline-fixture-model",
                          "input_rate_micro_usd_per_million": 1000000,
                          "cached_input_rate_micro_usd_per_million": 1000000,
                          "cache_write_rate_micro_usd_per_million": 1000000,
                          "output_rate_micro_usd_per_million": 1000000},
        "per_run_limits": {"measured_tokens": 1000, "active_seconds": 120, "tool_calls": 64},
        "max_model_requests": 128, "cost_limit_micro_usd": 1000,
    }
    config_path = OUT / "configuration.json"
    write_json(config_path, configuration)
    commands, runtimes = [], {}
    for label, python in PYTHONS.items():
        parent = Path(tempfile.mkdtemp(prefix=f"specorganon-D113-cli-{label}-"))
        assert stat.S_IMODE(parent.stat().st_mode) == 0o700
        bundle, prepared = parent / "bundle", parent / "prepared"
        runtimes[label] = {"parent": str(parent), "bundle": str(bundle),
                           "prepared": str(prepared), "python": str(python)}
        write_json(OUT / f"runtime_{label}.json", runtimes[label])
        command = capture(f"{label}_build", [str(python), "-B",
                          "scripts/prepare_development_round.py", "build",
                          str(config_path), str(bundle)])
        commands.append(command)
        if not command["passed"]:
            continue
        schedule = json_file(bundle / "schedule.json")
        selected = next(run for run in schedule["runs"]
                        if run["case_id"] == "D-F" and run["arm"] == "A")
        command = capture(f"{label}_prepare", [str(python), "-B",
                          "scripts/prepare_development_round.py", "prepare",
                          str(bundle), selected["run_id"], str(prepared)])
        commands.append(command)
        write_json(OUT / f"inventory_{label}.json", inventory(parent))
    write_json(OUT / "command_summary.json", {
        "source_freeze_commit": FREEZE, "commands": commands, "runtimes": runtimes,
        "passed": len(commands) == 4 and all(item["passed"] for item in commands),
        "formal_cells_executed": 0, "provider_requests": 0,
        "execution_authorized": False,
    })
    return 0 if len(commands) == 4 and all(item["passed"] for item in commands) else 1


if __name__ == "__main__":
    raise SystemExit(main())
